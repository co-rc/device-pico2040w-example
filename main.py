import bluetooth
from micropython import const
import uasyncio as asyncio

# ---------------------------------------------------------------------------
# CORC constants
# ---------------------------------------------------------------------------
CORC_DEVICE_NAME = "CORC"

CORC_SERVICE_UUID = bluetooth.UUID("B13A1000-9F2A-4F3B-9C8E-A7D4E3C8B125")
CORC_RX_CHAR_UUID = bluetooth.UUID("B13A1001-9F2A-4F3B-9C8E-A7D4E3C8B125")
CORC_CONFIG_CHAR_UUID = bluetooth.UUID("B13A1002-9F2A-4F3B-9C8E-A7D4E3C8B125")

# --- BLE IRQ event codes ---
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)

# Characteristic flags
_FLAG_READ = const(0x0002)
_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESP = const(0x0004)
_FLAG_NOTIFY = const(0x0010)

# Advertising constants
_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID128_FULL = const(0x07)


class CorcBlePeripheral:
    """
    CORC BLE peripheral (MicroPython, Pico W).

    - advertises single CORC GATT service,
    - RX characteristic (Android -> CORC) present but writes are ignored,
    - CONFIG characteristic (CORC -> Android) sends config.json via NOTIFY,
      with CFG1 header and dynamic MTU-based chunking,
    - MTU is negotiated per connection (Android requests, CORC tracks result).
    """

    def __init__(self, name=CORC_DEVICE_NAME, preferred_mtu=247):
        self._name = name

        # BLE core
        self._ble = bluetooth.BLE()
        self._ble.active(True)

        # Preferred MTU for ATT exchange (upper bound on CORC side)
        self._ble.config(mtu=preferred_mtu)

        self._ble.irq(self._irq)

        # RX: Android -> CORC (ignored for now)
        self._rx_char = (
            CORC_RX_CHAR_UUID,
            _FLAG_WRITE | _FLAG_WRITE_NO_RESP,
        )

        # CONFIG: CORC -> Android (NOTIFY + READ)
        self._config_char = (
            CORC_CONFIG_CHAR_UUID,
            _FLAG_NOTIFY | _FLAG_READ,
        )

        # Single CORC service with two characteristics: RX + CONFIG
        self._service = (
            CORC_SERVICE_UUID,
            (self._rx_char, self._config_char),
        )

        # Register GATT service and obtain handles
        ((self._rx_handle, self._config_handle),) = self._ble.gatts_register_services(
            (self._service,)
        )

        # Connections and MTU tracking
        # For now we assume at most one central, but structure allows more.
        self._connections = set()
        self._default_mtu = 23
        self._mtu = self._default_mtu

        # Track which connections already got config.json
        self._config_sent = set()

        # Flag to trigger config sending from IRQ into asyncio context
        self._send_config_flag = asyncio.ThreadSafeFlag()

        # Build advertising payloads
        self._adv_payload = self._build_adv_name_payload(self._name)
        self._scan_resp_payload = self._build_scan_resp_payload([CORC_SERVICE_UUID])

        # Start advertising immediately
        self._advertise()

    # -------------------------------------------------------------------------
    # IRQ HANDLER (minimal)
    # -------------------------------------------------------------------------
    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            print("CORC BLE: Connected, conn_handle =", conn_handle)
            self._connections.add(conn_handle)
            # Reset config state for this connection
            self._config_sent.discard(conn_handle)
            # Trigger async task to send config after short delay
            self._send_config_flag.set()

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            print("CORC BLE: Disconnected, conn_handle =", conn_handle)
            self._connections.discard(conn_handle)
            self._config_sent.discard(conn_handle)
            # Restart advertising to allow new central to connect
            self._advertise()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle:
                # RX WRITE from Android – intentionally ignored (no parsing).
                print("CORC BLE: RX write ignored (conn_handle =", conn_handle, ")")

        elif event == _IRQ_MTU_EXCHANGED:
            conn_handle, mtu = data
            # This event is triggered when central (Android) performs MTU exchange.
            self._mtu = mtu
            print("CORC BLE: MTU exchanged, conn_handle =", conn_handle, "MTU =", mtu)
            # Optional: if chciałbyś wysłać config *dopiero po* MTU,
            # można tu zawołać self._send_config_flag.set() zamiast w CONNECT.

    # -------------------------------------------------------------------------
    # PUBLIC API / MAIN LOOP
    # -------------------------------------------------------------------------
    async def run(self):
        """
        Async main loop:
        - background task sending config.json to newly connected centrals,
        - placeholder for future periodic tasks.
        """
        asyncio.create_task(self._config_loop())
        print("CORC BLE: Async loop started (current MTU =", self._mtu, ")")
        while True:
            await asyncio.sleep(1)

    def current_mtu(self):
        return self._mtu

    # -------------------------------------------------------------------------
    # CONFIG SENDING LOGIC (NOTIFY on CORC_CONFIG_CHAR_UUID)
    # -------------------------------------------------------------------------
    async def _config_loop(self):
        """
        Waits for _send_config_flag and sends config.json once per connection.
        """
        while True:
            # Wait until IRQ signals a new connection (or other trigger)
            await self._send_config_flag.wait()

            # Small delay to give Android time to:
            # - request MTU,
            # - discover services,
            # - enable notifications on CONFIG characteristic.
            await asyncio.sleep_ms(200)

            if not self._connections:
                continue

            # Snapshot connection list to avoid concurrent modification issues
            conn_list = list(self._connections)
            for conn_handle in conn_list:
                if conn_handle not in self._connections:
                    continue
                if conn_handle in self._config_sent:
                    continue
                try:
                    await self._send_config_to_conn(conn_handle)
                    self._config_sent.add(conn_handle)
                except Exception as ex:
                    print("CORC BLE: send_config error for conn", conn_handle, ":", ex)

    def _calc_chunk_size(self):
        """
        Compute max payload size for a single NOTIFY packet based on current MTU.
        ATT header = 3 bytes (opcode + handle), we also cap application payload
        to 200 bytes for safety.
        """
        payload = self._mtu - 3
        if payload < 20:
            payload = 20
        if payload > 200:
            payload = 200
        return payload

    async def _send_config_to_conn(self, conn_handle):
        """
        Reads config.json from filesystem and sends it to given connection
        via NOTIFY on CORC_CONFIG_CHAR_UUID, using CFG1 header and MTU-aware
        chunking.
        """
        try:
            with open("config.json", "rb") as f:
                data = f.read()
        except OSError:
            print("CORC BLE: config.json not found")
            return

        total_len = len(data)
        if total_len == 0:
            print("CORC BLE: config.json is empty")
            return

        chunk_size = self._calc_chunk_size()

        print("CORC BLE: sending config to conn",
              conn_handle, "len =", total_len,
              "mtu =", self._mtu, "chunk =", chunk_size)

        # --- CFG1 header ---
        # [0..2] = 'C','F','G'
        # [3]    = version (0x01)
        # [4..7] = total_len (uint32 BE)
        header = bytearray(8)
        header[0] = ord("C")
        header[1] = ord("F")
        header[2] = ord("G")
        header[3] = 0x01
        header[4] = (total_len >> 24) & 0xFF
        header[5] = (total_len >> 16) & 0xFF
        header[6] = (total_len >> 8) & 0xFF
        header[7] = total_len & 0xFF

        # First packet: header + beginning of JSON payload
        first_room = chunk_size - len(header)
        if first_room < 0:
            first_room = 0

        first_payload = data[:first_room]
        packet0 = bytes(header) + first_payload
        offset = len(first_payload)

        self._ble.gatts_notify(conn_handle, self._config_handle, packet0)
        await asyncio.sleep_ms(10)

        # Subsequent packets: raw JSON payload
        while offset < total_len and conn_handle in self._connections:
            end = min(offset + chunk_size, total_len)
            chunk = data[offset:end]
            self._ble.gatts_notify(conn_handle, self._config_handle, chunk)
            offset = end
            await asyncio.sleep_ms(5)

        print("CORC BLE: config sent, bytes =", offset)

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
