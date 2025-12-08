import bluetooth
from micropython import const
import uasyncio as asyncio

# ---------------------------------------------------------------------------
# CORC constants
# ---------------------------------------------------------------------------
CORC_DEVICE_NAME = "CORC"

CORC_SERVICE_UUID = bluetooth.UUID("B13A1000-9F2A-4F3B-9C8E-A7D4E3C8B125")
CORC_RX_CHAR_UUID = bluetooth.UUID("B13A1001-9F2A-4F3B-9C8E-A7D4E3C8B125")

# --- BLE IRQ event codes ---
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)
_IRQ_CONNECTION_UPDATE = const(27)
_IRQ_ENCRYPTION_UPDATE = const(28)

# Characteristic flags
_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESP = const(0x0004)

# Advertising constants
_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID128_FULL = const(0x07)

# ---------------------------------------------------------------------------
# Global connection map: conn_handle -> BleConnection
# ---------------------------------------------------------------------------
CONNECTIONS = {}  # type: dict[int, "BleConnection"]


class BleConnection:
    """
    Per-connection state for a BLE link (central <-> CORC peripheral).
    - conn_handle
    - addr_type
    - addr (bytes)
    - mtu
    - (interval/latency/timeout)
    - (encrypted/authenticated/bonded/key_size)
    """

    def __init__(self, conn_handle, addr_type, addr, initial_mtu=23):
        self.conn_handle = conn_handle
        self.addr_type = addr_type
        self.addr = bytes(addr)
        self.mtu = initial_mtu

        # Connection parameters (set via _IRQ_CONNECTION_UPDATE)
        self.conn_interval = None
        self.conn_latency = None
        self.supervision_timeout = None
        self.conn_status = None

        # Security state (set via _IRQ_ENCRYPTION_UPDATE)
        self.encrypted = False
        self.authenticated = False
        self.bonded = False
        self.key_size = None

    def update_mtu(self, mtu):
        self.mtu = mtu

    def update_connection_params(self, conn_interval, conn_latency, supervision_timeout, status):
        self.conn_interval = conn_interval
        self.conn_latency = conn_latency
        self.supervision_timeout = supervision_timeout
        self.conn_status = status

    def update_security(self, encrypted, authenticated, bonded, key_size):
        self.encrypted = bool(encrypted)
        self.authenticated = bool(authenticated)
        self.bonded = bool(bonded)
        self.key_size = key_size

    def short_addr(self):
        if not self.addr:
            return "??:??:??:??:??:??"
        return ":".join("{:02X}".format(b) for b in self.addr)

    def __repr__(self):
        return (
            "BleConnection(handle={h}, addr_type={t}, addr={a}, mtu={m}, enc={e}, auth={au}, bonded={b})"
        ).format(
            h=self.conn_handle,
            t=self.addr_type,
            a=self.short_addr(),
            m=self.mtu,
            e=self.encrypted,
            au=self.authenticated,
            b=self.bonded,
        )


class CorcBlePeripheral:
    """
    CORC BLE peripheral

    - Advertises CORC service.
    - Has RX characteristic (Android -> CORC), writes są ignorowane.
    - map CONNECTIONS: conn_handle -> BleConnection.
    """

    def __init__(self, name=CORC_DEVICE_NAME, preferred_mtu=247):
        self._name = name

        # BLE core
        self._ble = bluetooth.BLE()
        self._ble.active(True)

        self._ble.config(mtu=preferred_mtu)

        self._ble.irq(self._irq)

        # RX characteristic: Android -> CORC (ignore commands for now)
        self._rx_char = (
            CORC_RX_CHAR_UUID,
            _FLAG_WRITE | _FLAG_WRITE_NO_RESP,
        )

        # Single CORC service
        self._service = (
            CORC_SERVICE_UUID,
            (self._rx_char,),
        )

        # Register GATT service and get the RX handle
        ((self._rx_handle,),) = self._ble.gatts_register_services((self._service,))

        # Advertising payloads
        self._adv_payload = self._build_adv_name_payload(self._name)
        self._scan_resp_payload = self._build_scan_resp_payload([CORC_SERVICE_UUID])

        # Start advertising
        self._advertise()

    # -------------------------------------------------------------------------
    # Connection helpers
    # -------------------------------------------------------------------------
    def _add_connection(self, conn_handle, addr_type, addr):
        if conn_handle in CONNECTIONS:
            removed = CONNECTIONS.pop(conn_handle)
            print("CORC BLE: removing existing BleConnection for handle", conn_handle, removed)

        connection = BleConnection(conn_handle, addr_type, addr, initial_mtu=23)
        CONNECTIONS[conn_handle] = connection
        print("CORC BLE: new BleConnection:", connection)

    def _remove_connection(self, conn_handle):
        connection = CONNECTIONS.pop(conn_handle, None)
        if connection is not None:
            print("CORC BLE: BleConnection removed:", connection)

    def _get_connection(self, conn_handle):
        return CONNECTIONS.get(conn_handle, None)

    # -------------------------------------------------------------------------
    # IRQ HANDLER
    # -------------------------------------------------------------------------
    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            print("CORC BLE: CONNECT  handle =", conn_handle, "addr_type =", addr_type)
            self._add_connection(conn_handle, addr_type, addr)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            print("CORC BLE: DISCONNECT handle =", conn_handle)
            self._remove_connection(conn_handle)
            self._advertise()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle:
                # RX WRITE from Android – (just log)
                conn = self._get_connection(conn_handle)
                if conn is not None:
                    print("CORC BLE: RX write ignored from", conn.short_addr(), "handle", conn_handle)
                else:
                    print("CORC BLE: RX write ignored from unknown handle", conn_handle)

        elif event == _IRQ_MTU_EXCHANGED:
            conn_handle, mtu = data
            conn = self._get_connection(conn_handle)
            if conn is not None:
                conn.update_mtu(mtu)
                print("CORC BLE: MTU_EXCHANGED handle =", conn_handle, "mtu =", mtu, "addr =", conn.short_addr())
            else:
                print("CORC BLE: MTU_EXCHANGED for unknown handle", conn_handle, "mtu =", mtu)

        elif event == _IRQ_CONNECTION_UPDATE:
            conn_handle, conn_interval, conn_latency, supervision_timeout, status = data
            conn = self._get_connection(conn_handle)
            if conn is not None:
                conn.update_connection_params(conn_interval,
                                              conn_latency,
                                              supervision_timeout,
                                              status)
                print("CORC BLE: CONN_UPDATE handle =", conn_handle,
                      "interval =", conn_interval,
                      "latency =", conn_latency,
                      "timeout =", supervision_timeout,
                      "status =", status)
            else:
                print("CORC BLE: CONN_UPDATE for unknown handle", conn_handle)

        elif event == _IRQ_ENCRYPTION_UPDATE:
            conn_handle, encrypted, authenticated, bonded, key_size = data
            conn = self._get_connection(conn_handle)
            if conn is not None:
                conn.update_security(encrypted, authenticated, bonded, key_size)
                print("CORC BLE: ENC_UPDATE handle =", conn_handle,
                      "enc =", encrypted,
                      "auth =", authenticated,
                      "bonded =", bonded,
                      "key_size =", key_size)
            else:
                print("CORC BLE: ENC_UPDATE for unknown handle", conn_handle)

        else:
            print("CORC BLE: unknown IRQ event ", event)

    # -------------------------------------------------------------------------
    # PUBLIC API / MAIN LOOP
    # -------------------------------------------------------------------------
    async def run(self):
        print("CORC BLE: Async loop started")
        while True:
            await asyncio.sleep(1)

    # -------------------------------------------------------------------------
    # Advertising helpers
    # -------------------------------------------------------------------------
    def _build_adv_name_payload(self, name):
        """
        adv_data: flags + complete local name.
        Max 31 bytes total.
        """
        payload = bytearray()

        # Flags: general discoverable, BR/EDR not supported
        payload += bytes((2, _ADV_TYPE_FLAGS, 0x06))

        if name:
            name_bytes = name.encode("utf-8")
            # 31 bytes total - current payload length - 2 bytes (len + type)
            max_name_len = 31 - len(payload) - 2
            if max_name_len < 0:
                max_name_len = 0
            name_bytes = name_bytes[:max_name_len]
            payload += bytes((len(name_bytes) + 1, _ADV_TYPE_NAME)) + name_bytes

        return bytes(payload)

    def _build_scan_resp_payload(self, services):
        """
        scan_response: put 128-bit service UUID(s) here.
        """
        payload = bytearray()
        if services:
            for uuid in services:
                b = bytes(uuid)
                if len(b) == 16:
                    payload += bytes((len(b) + 1, _ADV_TYPE_UUID128_FULL)) + b
        return bytes(payload)

    def _advertise(self, interval_us=500_000):
        print("CORC BLE: Advertising as '{}'".format(self._name))
        self._ble.gap_advertise(
            interval_us,
            adv_data=self._adv_payload,
            resp_data=self._scan_resp_payload,
        )

# -------------------------------------------------------------------------
# Async entry point
# -------------------------------------------------------------------------
async def main():
    corc = CorcBlePeripheral()
    await corc.run()


asyncio.run(main())
