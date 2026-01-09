import bluetooth
import uasyncio as asyncio
from micropython import const

from debug.debug_logging import BLE

# ---------------------------------------------------------------------------
# CORC constants
# ---------------------------------------------------------------------------
CORC_DEVICE_NAME = "CORC"

CORC_SERVICE_UUID = bluetooth.UUID("B13A1000-9F2A-4F3B-9C8E-A7D4E3C8B125")
CORC_RX_CHAR_UUID = bluetooth.UUID("B13A1001-9F2A-4F3B-9C8E-A7D4E3C8B125")
CORC_TX_CHAR_UUID = bluetooth.UUID("B13A1002-9F2A-4F3B-9C8E-A7D4E3C8B125")

# Protocol constants
PROTOCOL_BYTE_ORDER = "little"  # Little endian as per guidelines
CORC_PROTOCOL_MAGIC = 0xC07C

# Result Codes (matching Android BleResult.java)
RES_OK = 0x00
RES_REQUEST_NOT_SUPPORTED = 0x06
RES_INVALID_ATTRIBUTE_LENGTH = 0x0D
RES_UNSUPPORTED = 0x11
RES_BAD_PARAM = 0x12
RES_INVALID_STATE = 0x13
RES_BUSY = 0x14
RES_FAILURE = 0xFF

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
_FLAG_NOTIFY = const(0x0010)

# Advertising constants
_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID128_FULL = const(0x07)

# Protocol Opcodes
OPCODE_PING = const(0x01)
OPCODE_VERSION = const(0x02)
OPCODE_GET_DATA_MAX_LEN = const(0x03)

OPCODE_NAMES = {
    OPCODE_PING: "Ping",
    OPCODE_VERSION: "Version",
    OPCODE_GET_DATA_MAX_LEN: "Data Max Len",
}

MAX_PAYLOAD_LENGTH_FOR_DISPLAY = 16


def _payload_as_string(payload):
    result = "".join(chr(b) if 32 <= b <= 126 else "." for b in payload[:MAX_PAYLOAD_LENGTH_FOR_DISPLAY])
    if len(payload) > MAX_PAYLOAD_LENGTH_FOR_DISPLAY:
        result += "..."
    return "".join(("\"", result, "\""))


def _payload_as_hex(payload):
    result = " ".join("{:02x}".format(b) for b in payload[:MAX_PAYLOAD_LENGTH_FOR_DISPLAY])
    if len(payload) > MAX_PAYLOAD_LENGTH_FOR_DISPLAY:
        result = "{} bytes: {}".format(len(payload),result)
    return "".join(("[", result, "]"))


# const(---------------------------------------------------------------------------)
# BleConnection class
# ---------------------------------------------------------------------------
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
    - Has RX characteristic (Android -> CORC), writes are ignored.
    - self._connections: map conn_handle -> BleConnection.
    """

    def __init__(self, name=CORC_DEVICE_NAME, preferred_mtu=247):
        self._name = name
        # Even though PicoW typically supports one connection, we use a map
        # for portability to NRF/CircuitPython and to handle potential 
        # multi-connection scenarios in the future.
        self._connections = {}  # type: dict[int, BleConnection]

        # Hardware setup
        self._setup_hw()

        # Command queue for RX processing (to keep IRQ fast)
        self._cmd_queue = []
        self._cmd_event = asyncio.ThreadSafeFlag()

        # BLE core
        self._ble = bluetooth.BLE()
        self._ble.active(True)

        self._ble.config(mtu=preferred_mtu)

        self._ble.irq(self._irq)

        # RX characteristic: Android -> CORC
        self._rx_char = (
            CORC_RX_CHAR_UUID,
            _FLAG_WRITE,
        )

        # TX characteristic: CORC -> Android (Notifications)
        self._tx_char = (
            CORC_TX_CHAR_UUID,
            _FLAG_NOTIFY,
        )

        # Single CORC service
        self._service = (
            CORC_SERVICE_UUID,
            (self._rx_char, self._tx_char),
        )

        # Register GATT service and get handles
        ((self._rx_handle, self._tx_handle),) = self._ble.gatts_register_services((self._service,))

        # Advertising payloads
        self._adv_payload = self._build_adv_name_payload(self._name)
        self._scan_resp_payload = self._build_scan_resp_payload([CORC_SERVICE_UUID])

        # Flag to restart advertising from async loop (to avoid ENODEV in IRQ)
        self._should_advertise = False

        # Start advertising
        self._advertise()

    def _setup_hw(self):
        """
        Initialize IR and other hardware components.
        """
        # TODO: Initialize IR PWM pin (e.g. GPIO 17)
        # from machine import Pin, PWM
        # self._ir_pwm = PWM(Pin(17))
        # self._ir_pwm.duty_u16(0)
        BLE.info("Hardware setup initialized")

    # -------------------------------------------------------------------------
    # Connection helpers
    # -------------------------------------------------------------------------
    def _add_connection(self, conn_handle, addr_type, addr):
        if conn_handle in self._connections:
            removed = self._connections.pop(conn_handle)
            BLE.info("removing existing BleConnection for handle", conn_handle, removed)

        connection = BleConnection(conn_handle, addr_type, addr, initial_mtu=23)
        self._connections[conn_handle] = connection
        BLE.info("new BleConnection: ", connection)

    def _remove_connection(self, conn_handle):
        connection = self._connections.pop(conn_handle, None)
        if connection is not None:
            BLE.info("BleConnection removed:", connection)

    def _get_connection(self, conn_handle):
        return self._connections.get(conn_handle, None)

    def send_response(self, conn_handle, request_id, opcode, result, payload=None):
        """
        Sends a response frame as a notification according to ADR 0006.
        """
        if payload is None:
            payload = b""

        # Framing: Magic(2), RequestId(1), Opcode(1), Result(1), Len(1), Payload(N)
        frame = bytearray()
        frame.extend(CORC_PROTOCOL_MAGIC.to_bytes(2, PROTOCOL_BYTE_ORDER))
        frame.append(request_id)
        frame.append(opcode)
        frame.append(result)
        frame.append(len(payload))
        frame.extend(payload)

        self.send_notification(conn_handle, frame)
        BLE.info("  ==> opcode:0x{:02X}, ID:{}, payload:{} {}".format(opcode, request_id, _payload_as_string(payload), _payload_as_hex(payload)))

    def send_notification(self, conn_handle, data):
        """
        Sends a notification to a connected central.
        """
        if conn_handle in self._connections:
            try:
                self._ble.gatts_notify(conn_handle, self._tx_handle, data)
            except OSError as e:
                BLE.error("Failed to send notification:", e)
        else:
            BLE.warning("Cannot notify: unknown connection handle", conn_handle)

    # -------------------------------------------------------------------------
    # IRQ HANDLER
    # -------------------------------------------------------------------------
    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._add_connection(conn_handle, addr_type, addr)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            self._remove_connection(conn_handle)

            # Clear pending commands only for this connection
            self._cmd_queue = [c for c in self._cmd_queue if c[0] != conn_handle]

            self._should_advertise = True

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle:
                # Read the written value
                value = self._ble.gatts_read(self._rx_handle)
                # Offload to async layer
                self._cmd_queue.append((conn_handle, value))
                self._cmd_event.set()

        elif event == _IRQ_MTU_EXCHANGED:
            conn_handle, mtu = data
            conn = self._get_connection(conn_handle)
            if conn is not None:
                conn.update_mtu(mtu)
                BLE.info("MTU negotiation", mtu, conn)

        elif event == _IRQ_CONNECTION_UPDATE:
            conn_handle, conn_interval, conn_latency, supervision_timeout, status = data
            conn = self._get_connection(conn_handle)
            if conn is not None:
                conn.update_connection_params(conn_interval,
                                              conn_latency,
                                              supervision_timeout,
                                              status)

        elif event == _IRQ_ENCRYPTION_UPDATE:
            conn_handle, encrypted, authenticated, bonded, key_size = data
            conn = self._get_connection(conn_handle)
            if conn is not None:
                conn.update_security(encrypted, authenticated, bonded, key_size)

        else:
            BLE.info("unknown IRQ event ", event)

    # -------------------------------------------------------------------------
    # PUBLIC API / MAIN LOOP
    # -------------------------------------------------------------------------
    async def run(self):
        BLE.info("Async loop started")
        # Start the command processor task
        asyncio.create_task(self._process_commands())
        while True:
            if self._should_advertise:
                self._should_advertise = False
                try:
                    self._advertise()
                except OSError as e:
                    BLE.error("Failed to restart advertising:", e)
                    # If it failed, we might want to try again in the next loop iteration
                    self._should_advertise = True
            await asyncio.sleep(1)

    async def _process_commands(self):
        """
        Drains the command queue and processes RX data according to ADR 0006.
        """
        while True:
            await self._cmd_event.wait()
            while self._cmd_queue:
                conn_handle, value = self._cmd_queue.pop(0)
                conn = self._get_connection(conn_handle)
                addr = conn.short_addr() if conn else "unknown"
                BLE.info("RX frame from {}: {} {}".format(addr, _payload_as_string(value), _payload_as_hex(value)))

                if len(value) < 5:
                    BLE.warning("Frame too short: {} bytes".format(len(value)))
                    # Header is 5 bytes: Magic(2), ID(1), Opcode(1), Len(1)
                    continue

                # Parse Header: Magic(2), RequestId(1), Opcode(1), Len(1)
                magic = int.from_bytes(value[0:2], PROTOCOL_BYTE_ORDER)
                if magic != CORC_PROTOCOL_MAGIC:
                    BLE.warning("Invalid magic: 0x{:04X}".format(magic))
                    continue

                request_id = value[2]
                opcode = value[3]
                payload_len = value[4]
                payload = value[5: 5 + payload_len]

                if len(value) < 5 + payload_len:
                    BLE.warning("Incomplete payload: expected {}, got {}".format(payload_len, len(value) - 5))
                    self.send_response(conn_handle, request_id, opcode, RES_INVALID_ATTRIBUTE_LENGTH)
                    continue

                # Dispatch by Opcode
                msg = OPCODE_NAMES.get(opcode, "Unknown opcode 0x{:02x}".format(opcode))
                BLE.info("  {} (opcode:0x{:02X}, ID:{}, payload:{} {})".format(msg, opcode, request_id, _payload_as_string(payload), _payload_as_hex(payload)))

                if opcode == OPCODE_PING:
                    self.send_response(conn_handle, request_id, opcode, RES_OK)

                elif opcode == OPCODE_VERSION:
                    # Response: [Major, Minor, Patch] -> 1.0.0
                    self.send_response(conn_handle, request_id, opcode, RES_OK, b"\x01\x00\x00")

                elif opcode == OPCODE_GET_DATA_MAX_LEN:
                    max_len = (conn.mtu - 3) if conn else 20
                    # self.send_response already gets the opcode, and we logged it above.
                    # Reasonable default or calculated from negotiated MTU
                    # 3 bytes is the standard GATT Write/Notify overhead
                    self.send_response(conn_handle, request_id, opcode, RES_OK, bytes([max_len]))

                else:
                    BLE.warning("Unsupported opcode: 0x{:02x} (ID: {})".format(opcode, request_id))
                    self.send_response(conn_handle, request_id, opcode, RES_UNSUPPORTED)

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
        BLE.info("Advertising as '{}'".format(self._name))
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
