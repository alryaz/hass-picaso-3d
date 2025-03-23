"""Barebones implementation of PICASO 3D Printer information API."""

import asyncio
import logging
import re
import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from functools import wraps, cached_property
from typing import List, NamedTuple, SupportsBytes, MutableMapping

_LOGGER = logging.getLogger(__name__)


class EventSeverity(IntEnum):
    UNKNOWN = -1
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3
    FATAL = 4


class EventSource(IntEnum):
    NONE = 0
    N1 = 1
    N2 = 2
    R = 3
    T = 4
    X = 5
    Y = 6
    Z = 7
    E = 8
    TZ = 9
    PH = 10
    XY = 11


class IPCResult(IntEnum):
    UNKNOWN = 0
    OK = 1
    OK_FINISHED = 2
    ERR_PLAYLIST_FULL = 3
    ERR_FILE_ACCESS = 4
    ERR_FILE_CORRUPTED = 5
    ERR_TASK_NAME = 6
    ERR_TASK_EXIST = 7
    ERR_TASK_NOT_FOUND = 8
    ERR_STATE_SET = 9
    ERR_USER_PREPARE_PRINTER = 10
    ERR_BUSY = 11
    ERR_FLASH_NOT_FOUND = 12
    ERR_INCORRECT_SIZE = 13
    ERR_PRINTLIST_NOT_FOUND = 14
    ERR_UNKNOWN_COMMAND = 15
    ERR_INVALID_PARAMETER = 16
    ERR_INCORRECT_PROTOCOL_VER = 17
    ERR_SERVICE_UNAVAILABLE = 18
    ERR_ACCESS_FORBIDDEN = 19
    ERR_DATA_NOT_FOUND = 20
    ERR_TIMEOUT = 21
    ERR_WRITE_FRAM = 22
    ERR_READ_FRAM = 23
    ERR_GET_DATA_WRONG_CRC = 24
    ERR_BAD_REQUEST = 25
    ERR_BAD_PARAM = 26
    ERR_EXEC = 27
    ERR_DIFFER_PRINTER_TYPE = 28
    ERR_NO_PROFILE_WITH_SUCH_GUID = 29
    ERR_PROFILE_WITH_SAME_GUID = 30
    ERR_UNSUPPORTED_TASK = 31
    ERR_MECHANIC = 32
    ERR_NO_FILAMENT_TOOL0 = 33
    ERR_NO_FILAMENT_TOOL1 = 34
    ERR_FRAM_OUT_OF_MEMORY = 35
    ERR_FRAM_TRY_REMOVE_DEFAULT = 36
    ERR_MECHANIC_OUT_OF_MEMORY = 37
    ERR_LED_STATE_SET_ERROR = 38
    ERR_OLD_PLGX_FILE_FORMAT = 39
    ERR_PROFILE_NOT_FOUND = 40
    ERR_VALIDATION_FAILED = 41
    ERR_VALIDATION_FAILED_WRITE_DONE = 42
    ERR_NO_FILAMENT_FOR_HOT_SWAP = 43
    OK_OLD_PROFILE_IMPORT = 44
    DXSERVER_ALREADY_PAUSED = 45
    TRY_PRINT_NOT_FULL_FILE = 46
    ERR_ENCODING = 47
    ERR_BUFF_SIZE = 48

    @property
    def is_error(self) -> bool:
        return self.name.startswith("ERR_")


class NetPrinterState(IntEnum):
    UNKNOWN = 0
    PRINTING = 1
    PAUSED = 2
    IDLE = 3
    SERVICE = 4
    PREPARE_FOR_PRINTING = 5
    PREPARE_FOR_PAUSE = 6
    PREPARE_FOR_STOP = 7
    PRE_PRINT = 8


class NetPrinterStatus(IntEnum):
    UNKNOWN = 0
    PRINT_PROBLEM = 1
    CRITICAL_ERROR = 2
    WAIT_USER = 3
    WAIT_NEW_TASK = 4
    SERVICE = 5
    MAIN_PRINT = 6
    PRINT_DONE = 7
    PRINT_PAUSED = 8
    ADJECTIVE_WARNING = 9
    UPDATE_DOWNLOAD = 10
    CONNECTION_ERROR = 0x80000000
    INITIAL_STATE = 0x80000004


class NozzleType(IntEnum):
    NONE = -1
    SIZE_0_2 = 20
    SIZE_0_3 = 30
    SIZE_0_4 = 40
    SIZE_0_5 = 50
    SIZE_0_6 = 60
    SIZE_0_8 = 80
    SIZE_1_0 = 100


class PauseReason(IntFlag):
    LAYER_TIME = 2**0
    BY_USER = 2**1
    NOZZLE_CLEAN = 2**2
    FIRST_NOZZLE_BLOCKED = 2**3
    RADIATOR_OVERHEAT = 2**4
    FIRST_NOZZLE_RUNOUT = 2**5
    HIT_Z_ENDSTOP = 2**6
    ZBOARD_ERROR = 2**7
    LAYER_PAUSE = 2**8
    SECOND_NOZZLE_BLOCKED = 2**9
    FIRST_NOZZLE_SLIPPAGE = 2**10
    SECOND_NOZZLE_SLIPPAGE = 2**11
    SECOND_NOZZLE_RUNOUT = 2**12
    WRONG_NOZZLE_EXTRUDES = 2**13


class StopReason(IntFlag):
    GCODE_ERROR = 2**1
    HARDWARE_ERROR = 2**4


_RE_SPACE_CAPITALS = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_RE_SPACE_FOLLOWS = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_RE_SPACE_DIGITS = re.compile(r"(?<=[A-Za-z])(?=\d)")


class PrinterType(IntEnum):
    UNKNOWN = -1
    DesignerXPro = 4
    DesignerPRO250 = 5
    Designer = 6
    DesignerX = 7
    DesignerXL = 8
    DesignerXLPro = 9
    DesignerClassic = 10
    DesignerClassicAdv = 11
    DesignerX2 = 12
    DesignerXL2 = 13
    DesignerXPro2 = 14
    DesignerXLPro2 = 15

    @property
    def friendly_name(self) -> str:
        name = self.name
        name = _RE_SPACE_CAPITALS.sub(" ", name)
        name = _RE_SPACE_FOLLOWS.sub(" ", name)
        name = _RE_SPACE_DIGITS.sub(" ", name)
        return name

    @property
    def is_xl(self):
        c = self.__class__
        return self in (c.DesignerXL, c.DesignerXLPro, c.DesignerXL2, c.DesignerXLPro2)

    @property
    def is_series_2(self):
        c = self.__class__
        return self in (c.DesignerX2, c.DesignerXL2, c.DesignerXPro2, c.DesignerXLPro2)

    @property
    def is_multi_nozzle(self):
        c = self.__class__
        return self in (
            c.DesignerPRO250,
            c.DesignerXPro,
            c.DesignerXPro2,
            c.DesignerXLPro,
            c.DesignerXLPro2,
        )

    @property
    def is_single_nozzle(self):
        return not self.is_multi_nozzle


class EventData(NamedTuple):
    code: int
    severity: EventSeverity | int
    source: EventSource | int
    timestamp: int


class ParsedPayload(NamedTuple):
    protocol_major: int
    protocol_minor: int
    command_code: int
    data: bytes


@dataclass(kw_only=True, frozen=False)
class PrinterState:
    state: NetPrinterState = NetPrinterState.IDLE
    status: NetPrinterStatus = NetPrinterStatus.INITIAL_STATE
    task_name: str = ""
    task_progress: int = 0
    task_remaining: float = 0
    first_nozzle_temperature: float = 0.0
    second_nozzle_temperature: float = 0.0
    chamber_temperature: float = 0.0
    bed_temperature: float = 0.0
    events: List[EventData] = field(default_factory=list)
    pause_reason: int = 0
    stop_reason: int = 0
    ready: bool = False
    preheat_state: bool = False

    events_require_upgrade: bool = False


class _PrinterSearchDataCollector(asyncio.DatagramProtocol):
    def __init__(self, target: MutableMapping[tuple[str, int], bytes]) -> None:
        self.target = target
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, payload: bytes, addr: tuple[str, int]):
        self.target[addr] = payload


class _PrinterResponseDataCollector(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport = None
        self.payload_queue = asyncio.Queue(10)

    def connection_made(self, transport):
        self.transport = transport

    async def read_payload(self, timeout: float | None = 5):
        async with asyncio.timeout(timeout):
            result = await self.payload_queue.get()
            if isinstance(result, Exception):
                _LOGGER.debug("Raising exception: %s", result)
                raise result
            return result

    def datagram_received(self, payload: bytes, addr: tuple[str, int]):
        self.payload_queue.put_nowait(payload)


def sequential_request_guard(method: Callable[["Picaso3DPrinter", ...], ...]):
    """Decorator to handle locking and exception catching for async methods."""

    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        async with self.request_lock:
            return await method(self, *args, **kwargs)

    return wrapper


DEFAULT_BROADCAST_PORT = 49149
DEFAULT_INTERACTION_PORT = 54321


class Picaso3DPrinter:
    UDP_RETRY_CNT = 3
    DEFAULT_READ_TIMEOUT = 5

    def __init__(self, host: str, port: int = DEFAULT_INTERACTION_PORT) -> None:
        self.host = host
        self.port = port
        self.searching = False
        self.request_lock = asyncio.Lock()

        self.protocol_major = 0
        self.protocol_minor = 0
        self.hw_version_minor = -1
        self.hw_version_major = -1
        self.fw_version_major = 0
        self.fw_version_minor = 0
        self.fw_version_revision = 0

        self._name = None
        self._serial = None
        self._mac = None
        self._first_nozzle_name = None
        self.first_nozzle_type = NozzleType.NONE
        self._second_nozzle_name = None
        self.second_nozzle_type = NozzleType.NONE
        self._first_profile_name = None
        self._second_profile_name = None

    @property
    def addr(self) -> tuple[str, int]:
        return self.host, self.port

    @cached_property
    def hardware_version(self) -> str | None:
        return f"{self.hw_version_major}.{self.hw_version_minor}"

    @cached_property
    def firmware_version(self) -> str | None:
        return (
            None
            if self.protocol_major != 1
            else (
                f"{self.fw_version_major}.{self.fw_version_minor}"
                if self.protocol_minor <= 1
                else f"{self.fw_version_major}.{self.fw_version_minor}.{self.fw_version_revision}"
            )
        )

    @cached_property
    def type(self) -> PrinterType:
        try:
            return PrinterType(self.hw_version_major)
        except ValueError:
            return PrinterType.UNKNOWN

    @cached_property
    def supports_utf8(self) -> bool:
        return self.protocol_major > 1 or (
            self.protocol_major == 1
            and (
                self.protocol_minor > 2
                or (
                    self.protocol_minor == 2
                    and (
                        self.fw_version_major > 5
                        or (self.fw_version_major == 5 and self.fw_version_minor >= 9)
                    )
                )
            )
        )

    @cached_property
    def supports_clean_filesystem(self) -> bool:
        return (
            self.protocol_major == 1
            and self.protocol_minor == 2
            and (
                self.fw_version_major > 5
                or (
                    self.fw_version_major == 5
                    and (
                        self.fw_version_minor > 9
                        or (
                            self.fw_version_minor == 9
                            and self.fw_version_revision >= 58
                        )
                    )
                )
            )
        )

    @cached_property
    def supports_preheat_journal(self) -> bool:
        return (
            self.protocol_major == 1
            and self.protocol_minor == 2
            and (
                self.fw_version_major > 6
                or (
                    self.fw_version_major == 6
                    and (
                        self.fw_version_minor > 1
                        or (
                            self.fw_version_minor == 1
                            and self.fw_version_revision >= 33
                        )
                    )
                )
            )
        )

    @cached_property
    def supports_profiles(self) -> bool:
        return self.protocol_major == 1 and (
            (
                self.protocol_minor <= 1
                and (
                    self.fw_version_major > 5
                    or (self.fw_version_major == 5 and self.fw_version_minor >= 220)
                )
            )
            or self.protocol_minor == 2
        )

    @property
    def name(self) -> str | None:
        return self._name or self.serial

    @name.setter
    def name(self, value: str | bytes) -> None:
        self._name = decode_standard_string(self.supports_utf8, value)

    @property
    def serial(self) -> str | None:
        return self._serial

    @serial.setter
    def serial(self, value: str | bytes) -> None:
        self._serial = decode_standard_string(self.supports_utf8, value)

    @property
    def mac(self) -> str | None:
        return self._mac

    @mac.setter
    def mac(self, value: str | bytes) -> None:
        if not isinstance(value, str):
            value = value.hex()
            value = ":".join(value[i : i + 2] for i in range(0, len(value), 2))
        self._mac = value

    @property
    def first_nozzle_name(self) -> str | None:
        return self._first_nozzle_name

    @first_nozzle_name.setter
    def first_nozzle_name(self, value: str | bytes) -> None:
        self._first_nozzle_name = decode_standard_string(self.supports_utf8, value)

    @property
    def second_nozzle_name(self) -> str | None:
        return self._second_nozzle_name

    @second_nozzle_name.setter
    def second_nozzle_name(self, value: str | bytes) -> None:
        self._second_nozzle_name = decode_standard_string(self.supports_utf8, value)

    @property
    def first_profile_name(self) -> str | None:
        return self._first_profile_name

    @first_profile_name.setter
    def first_profile_name(self, value: str | bytes) -> None:
        self._first_profile_name = decode_standard_string(self.supports_utf8, value)

    @property
    def second_profile_name(self) -> str | None:
        return self._second_profile_name

    @second_profile_name.setter
    def second_profile_name(self, value: str | bytes) -> None:
        self._second_profile_name = decode_standard_string(self.supports_utf8, value)

    @classmethod
    def _unpack_payload_header(cls, payload: bytes) -> tuple[int, int, int, int, int]:
        (
            parsed_protocol_major,
            parsed_protocol_minor,
            parsed_command_code,
            unknown_parameter,
            parsed_payload_size,
        ) = struct.unpack_from("BBHHH", payload, 0)

        return (
            parsed_protocol_major,
            parsed_protocol_minor,
            parsed_command_code,
            unknown_parameter,
            parsed_payload_size,
        )

    async def _read_single_response(
        self,
        protocol: _PrinterResponseDataCollector,
        read_timeout: int | None = DEFAULT_READ_TIMEOUT,
        total_timeout: int | None = None,
        payload_size: int | None = None,
        command_code: int | None = None,
        protocol_major: int | None = None,
        protocol_minor: int | None = None,
    ) -> ParsedPayload:
        """
        Read a response from the printer.

        :param command_code:
        :param read_timeout: Timeout for each read operation
        :param total_timeout: Total timeout for the entire operation
        :param payload_size: Validate the payload size (True, False, or an integer for a specific size)
        :return: A tuple containing the protocol major, protocol minor, command code, and payload
        """
        parsed_protocol_major = None
        parsed_protocol_minor = None
        parsed_command_code = None
        parsed_payload_size = None
        payload = b""

        async with asyncio.timeout(total_timeout):
            while parsed_payload_size is None or len(payload) < parsed_payload_size:

                payload += await protocol.read_payload(read_timeout)
                payload_hex = payload.hex()
                _LOGGER.debug(
                    "[%s:%d] UDP_Receive => Length=%d; Data=%s",
                    *self.addr,
                    len(payload),
                    "_".join(
                        payload_hex[i : i + 2] for i in range(0, len(payload_hex), 2)
                    ),
                )
                if parsed_payload_size is None and len(payload) >= 8:
                    (
                        parsed_protocol_major,
                        parsed_protocol_minor,
                        parsed_command_code,
                        _,
                        parsed_payload_size,
                    ) = self._unpack_payload_header(payload)

                    if payload_size is not None and parsed_payload_size != payload_size:
                        raise ValueError(
                            f"Payload size mismatch: {parsed_payload_size} != {payload_size}"
                        )
                    if command_code is not None and parsed_command_code != command_code:
                        raise ValueError(
                            f"Command code mismatch: {parsed_command_code} != {command_code}"
                        )
                    if (
                        protocol_major is not None
                        and parsed_protocol_major != protocol_major
                    ):
                        raise ValueError(
                            f"Protocol major mismatch: {parsed_protocol_major} != {protocol_major}"
                        )
                    if (
                        protocol_minor is not None
                        and parsed_protocol_minor != protocol_minor
                    ):
                        raise ValueError(
                            f"Protocol minor mismatch: {parsed_protocol_minor} != {protocol_minor}"
                        )

        if parsed_payload_size != len(payload):
            raise ValueError(
                f"Decoding mismatch on payload size: {parsed_payload_size} != {len(payload)}"
            )

        return ParsedPayload(
            parsed_protocol_major,
            parsed_protocol_minor,
            parsed_command_code,
            payload[8:],
        )

    async def send_request(
        self,
        protocol_major: int,
        protocol_minor: int,
        command_code: int,
        data: bytes | SupportsBytes | None = None,
        num_responses: int | None = None,
        expect_protocol_major: int | None = None,
        expect_protocol_minor: int | None = None,
        expect_command_code: int | None = None,
        expect_payload_size: int | None = None,
    ):
        data = bytes(data) if data is not None else b""
        header = struct.pack(
            "BBHHH",
            protocol_major,
            protocol_minor,
            command_code,
            0,
            len(data) + 8,
        )
        payload = header + data

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:

            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: _PrinterResponseDataCollector(), sock=sock
            )
            try:
                _LOGGER.debug(
                    "[%s:%d] UDP_Send => Length=%d; Data=%s",
                    *self.addr,
                    len(payload),
                    payload.hex(),
                )

                sock.sendto(payload, self.addr)

                responses = []
                while num_responses > len(responses):
                    try:
                        response = await self._read_single_response(
                            protocol,
                            command_code=expect_command_code,
                            protocol_major=expect_protocol_major,
                            protocol_minor=expect_protocol_minor,
                            payload_size=expect_payload_size,
                        )
                    except TimeoutError:
                        if num_responses is not None:
                            raise
                    else:
                        responses.append(response)
            finally:
                transport.close()
        finally:
            sock.close()

        return responses

    async def send_request_v1(
        self,
        command_code: int,
        data: bytes | SupportsBytes | None = None,
        num_responses: int | None = None,
        expect_protocol_major: int | None = None,
        expect_protocol_minor: int | None = None,
        expect_command_code: int | None = None,
        expect_payload_size: int | None = None,
    ):
        return await self.send_request(
            1,
            0,
            command_code,
            data,
            num_responses,
            expect_protocol_major,
            expect_protocol_minor,
            expect_command_code,
            expect_payload_size,
        )

    async def send_request_v1_atomic(
        self,
        command_code: int,
        data: bytes | SupportsBytes | None = None,
        expect_protocol_minor: int | None = None,
        expect_payload_size: int | None = None,
    ):
        return (
            await self.send_request(
                1,
                0,
                command_code,
                data,
                1,
                1,
                expect_protocol_minor,
                command_code,
                expect_payload_size,
            )
        )[0]

    @classmethod
    async def search_printers(
        cls,
        attempts: int = 3,
        send_interval: float = 2,
        broadcast_port: int = DEFAULT_BROADCAST_PORT,
        broadcast_ip: str = "255.255.255.255",
    ) -> list["Picaso3DPrinter"]:
        loop = asyncio.get_running_loop()

        _LOGGER.info(
            "Searching for printers (attempts=%d, send_interval=%d, port=%d)...",
            attempts,
            send_interval,
            broadcast_port,
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        sock.bind(("", 0))

        responses = {}

        transport, _ = await loop.create_datagram_endpoint(
            lambda: _PrinterSearchDataCollector(responses), sock=sock
        )

        message = "PICASO3D".encode("ascii")

        try:
            _LOGGER.debug("Broadcasting message...")

            for _ in range(attempts):
                transport.sendto(message, (broadcast_ip, broadcast_port))
                _LOGGER.debug("Broadcast message, waiting for next attempt (if any)...")
                await asyncio.sleep(send_interval)
        finally:
            transport.close()
            sock.close()

        printers_by_serial = {}
        printers_by_addr = {}
        for addr, data in responses.items():
            try:
                protocol_major, protocol_minor, command_code, _, payload_size = (
                    cls._unpack_payload_header(data)
                )
            except Exception as exc:
                _LOGGER.error(
                    "Failed to parse header from %s:%d, ignoring...",
                    *addr,
                    exc_info=exc,
                )
                _LOGGER.debug("Payload: %s", data.hex())
            else:
                _LOGGER.debug("Received valid payload: %s", data)

                if command_code != 0x000C:
                    _LOGGER.warning(
                        f"Invalid message type received from %s:%d, ignoring..."
                    )
                    continue

                printer = cls(addr[0])

                try:
                    printer._apply_printer_info(
                        protocol_major, protocol_minor, data[8:]
                    )
                except Exception as exc:
                    _LOGGER.error(
                        "Failed to apply discovery info from %s:%d, ignoring...",
                        *addr,
                        exc_info=exc,
                    )
                    del printer
                    continue

                key, holder = (printer.serial, printers_by_serial)
                if not key:
                    _LOGGER.warning(
                        "Printer without serial number detected at %s:%d", *addr
                    )
                    key, holder = (addr, printers_by_addr)

                if key in holder:
                    _LOGGER.debug("Multiple responses from printer %s", printer.serial)
                    del printer
                    continue

                holder[key] = printer

        return [*printers_by_serial.values(), *printers_by_addr.values()]

    def decode_string(self, value: bytes | str) -> str:
        return decode_standard_string(self.supports_utf8, value)

    def encode_string(self, value: bytes | str) -> bytes:
        return encode_standard_string(self.supports_utf8, value)

    def _apply_printer_info(
        self, protocol_major: int, protocol_minor: int, data: bytes
    ) -> None:

        self.protocol_major = protocol_major
        self.protocol_minor = protocol_minor

        current_pointer = 0

        def _unpack_incremental(fmt: str):
            nonlocal current_pointer

            value = struct.unpack_from(fmt, data, current_pointer)[0]
            current_pointer += struct.calcsize(fmt)
            return value

        try:

            self.hw_version_minor = _unpack_incremental("b")
            self.hw_version_major = _unpack_incremental("b")

            if protocol_minor == 0:
                self.fw_version_minor = _unpack_incremental("b")
            elif protocol_minor == 1:
                self.fw_version_minor = _unpack_incremental("h")
            elif protocol_minor == 2:
                self.fw_version_revision = _unpack_incremental("b")
                self.fw_version_minor = _unpack_incremental("b")
            self.fw_version_major = _unpack_incremental("b")

            self.name = _unpack_incremental("20s")
            self.serial = _unpack_incremental("50s")
            self.mac = _unpack_incremental("6s")

            for prefix in ("first", "second"):
                setattr(self, prefix + "_nozzle_name", _unpack_incremental("10s"))
                nozzle_type = _unpack_incremental("b")
                try:
                    nozzle_type = NozzleType(nozzle_type)
                except ValueError:
                    pass
                setattr(self, prefix + "_nozzle_type", nozzle_type)
                setattr(self, prefix + "_profile_name", _unpack_incremental("40s"))
        except Exception as exc:
            _LOGGER.error(
                "Severe decoding error when applying payload to printer: %s",
                exc,
                exc_info=exc,
            )
            _LOGGER.debug("Payload: %s", data.hex())
            _LOGGER.debug("Printer: %s", self)
            raise

    @sequential_request_guard
    async def update_printer_info(self):
        """Update basic printer information."""
        _LOGGER.debug("Refreshing printer information...")
        command_code = 0x000C
        response = (
            await self.send_request_v1(
                command_code, expect_command_code=command_code, num_responses=1
            )
        )[0]
        self._apply_printer_info(
            response.protocol_major, response.protocol_minor, response.data
        )
        return self

    @sequential_request_guard
    async def start_locating(self) -> None:
        _LOGGER.debug("Starting printer locate...")
        await self.send_request_v1_atomic(0x000E)

    @sequential_request_guard
    async def stop_locating(self):
        _LOGGER.debug("Stopping printer locate...")
        await self.send_request_v1_atomic(0x000F)

    @sequential_request_guard
    async def change_name(self, new_name: str) -> None:
        _LOGGER.debug("Changing printer name to %s...", new_name)
        new_name = encode_standard_string(self.supports_utf8, new_name)
        new_name = struct.pack("20s", new_name)
        await self.send_request_v1_atomic(0x000D, new_name)

    @sequential_request_guard
    async def clean_filesystem(self) -> None:
        _LOGGER.debug("Cleaning printer filesystem...")
        await self.send_request_v1_atomic(0x0024, expect_payload_size=12)

    @sequential_request_guard
    async def get_free_space(self) -> int:
        _LOGGER.debug("Getting free space...")
        response = await self.send_request_v1_atomic(0x0013, expect_payload_size=16)
        return struct.unpack("Q", response.data)[0]

    @sequential_request_guard
    async def pause(self) -> None:
        _LOGGER.debug("Pausing printer...")
        await self.send_request_v1_atomic(0x0009)

    @sequential_request_guard
    async def resume(self) -> None:
        _LOGGER.debug("Resuming printer...")
        await self.send_request_v1_atomic(0x000B)

    @sequential_request_guard
    async def stop(self) -> None:
        _LOGGER.debug("Stopping printer...")
        command_code = 0x000A
        await self.send_request_v1_atomic(0x000A)

    @sequential_request_guard
    async def get_printer_state(self) -> PrinterState:
        _LOGGER.debug("Getting printer state...")
        command_code = 0x0001
        response = (
            await self.send_request_v1(
                command_code,
                expect_protocol_minor=1,
                expect_command_code=command_code,
                num_responses=1,
            )
        )[0]

        def _check_payload_size(expected_size: int):
            payload_size = len(response.data) + 8
            if payload_size != expected_size:
                raise ValueError(
                    f"Payload size mismatch for given protocol version {response.protocol_major}: {payload_size} != {expected_size}"
                )

        state = PrinterState()
        event_count = 5
        event_length = 4

        def _parse_event(content: bytes) -> EventData | None:
            event_id = struct.unpack_from("i", content, 0)[0]
            if event_id <= 0:
                return None
            return EventData(
                event_id,
                EventSeverity(0),
                EventSource(0),
                0,
            )

        if response.protocol_major == 0:
            _check_payload_size(343)
            first_offset = 0

        elif response.protocol_major == 1:
            _check_payload_size(344)
            first_offset = 1

            state.ready = bool(response.data[16])

        elif response.protocol_major == 2:
            _check_payload_size(387)
            first_offset = 4

            value = struct.unpack_from("I", response.data, 8)[0]
            state.ready = bool(value & 1)
            state.preheat_state = bool(value & 2)

            event_count = 10
            event_length = 6

            def _parse_event(content: bytes) -> EventData | None:
                event_id = struct.unpack_from("H", content, 0)[0]
                if event_id == 0:
                    return None

                severity = event_id & 7
                try:
                    severity = EventSeverity(severity)
                except ValueError:
                    pass

                source = (event_id >> 10) & 63
                try:
                    source = EventSource(source)
                except ValueError:
                    pass

                timestamp = struct.unpack_from("I", content, 2)[0]

                event_id = (event_id >> 3) & 127

                return EventData(event_id, severity, source, timestamp)

        else:
            raise ValueError(f"Invalid protocol major: {response.protocol_major}")

        if response.protocol_major in (1, 2) and self.type.is_series_2:
            state.events_require_upgrade = True
            event_count = 0

        def _unp(fmt: str, offset: int):
            return struct.unpack_from(fmt, response.data, offset + first_offset - 8)[0]

        state.state = NetPrinterState(struct.unpack_from("i", response.data, 0)[0])
        state.status = NetPrinterStatus(struct.unpack_from("i", response.data, 4)[0])

        state.task_name = self.decode_string(_unp("255s", 16))
        state.task_progress = _unp("f", 275)
        state.task_remaining = float(_unp("I", 287))
        state.first_nozzle_temperature = _unp("f", 295)
        state.second_nozzle_temperature = _unp("f", 299)
        state.chamber_temperature = _unp("f", 303)
        state.bed_temperature = _unp("f", 307)

        # @TODO: unknown data may cause problems with direct conversion
        state.pause_reason = PauseReason(_unp("I", 335))
        state.stop_reason = StopReason(_unp("I", 339))

        events = []
        event_start = 315 + first_offset - 8
        for _ in range(event_count):
            event = _parse_event(
                response.data[event_start : event_start + event_length]
            )
            if event is not None:
                events.append(event)
            event_start += event_length

        return state

    async def reset_name(self):
        serial = self.serial
        if not serial:
            raise ValueError("Printer serial number is not set")
        return await self.change_name(serial)


def decode_standard_string(supports_utf8: bool, value: bytes | str) -> str:
    if not isinstance(value, str):
        value = value.decode("utf-8" if supports_utf8 else "cp1251")
    return value.rstrip("\x00\n\t\r ")


def encode_standard_string(supports_utf8: bool, value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.rstrip("\x00\n\t\r ").encode(
            "utf-8" if supports_utf8 else "cp1251"
        )
    return value
