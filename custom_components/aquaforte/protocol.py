"""AquaForte binary protocol implementation (TCP port 12416, UDP port 12414).

Protocol reversed from https://github.com/geelenbert/aquaforte-mqtt
Packet format: [4-byte prefix 0x00000003][varint length][flag 0x00][2-byte BE type][payload]
"""
from __future__ import annotations

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass

from .const import (
    CONNECT_TIMEOUT,
    CTRL_CACHE_SIZE,
    DISCOVERY_TIMEOUT,
    FAULT_BYTE,
    MSG_DATA_CONTROL_REQ,
    MSG_DATA_CONTROL_RSP,
    MSG_DATA_TRANSMIT_REQ,
    MSG_DATA_TRANSMIT_RSP,
    MSG_DISCOVER_REQUEST,
    MSG_DISCOVER_RESPONSE,
    MSG_LOGIN_REQUEST,
    MSG_LOGIN_RESPONSE,
    MSG_PASSCODE_REQUEST,
    MSG_PASSCODE_RESPONSE,
    MSG_PING_REQUEST,
    MSG_PING_RESPONSE,
    P0_CONTROL_DEVICE,
    P0_READ_STATUS,
    P0_STATUS_REPLY,
    P0_STATUS_REPORT,
    PACKET_PREFIX,
    RESPONSE_TIMEOUT,
    TCP_PORT,
    UDP_PORT,
    WRITABLE_FLAG_SIZE,
    WRITABLE_VALUE_SIZE,
    ALL_ENDPOINTS,
    EndpointDef,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    device_id: str
    mac: bytes
    wifi_version: str
    product_key: str
    host: str


def encode_varint(n: int) -> bytes:
    """Encode integer as variable-length bytes (7 bits per byte, MSB = continuation)."""
    result = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            result.append(byte | 0x80)
        else:
            result.append(byte)
            break
    return bytes(result)


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode varint from data at offset. Returns (value, new_offset)."""
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return value, offset


def build_packet(msg_type: int, payload: bytes = b"") -> bytes:
    """Build a protocol packet."""
    body = b"\x00" + struct.pack(">H", msg_type) + payload
    return PACKET_PREFIX + encode_varint(len(body)) + body


def parse_packet(data: bytes) -> tuple[int, bytes] | None:
    """Parse a protocol packet. Returns (msg_type, payload) or None on error."""
    if len(data) < 7 or data[:4] != PACKET_PREFIX:
        return None
    _, offset = decode_varint(data, 4)
    if offset + 3 > len(data):
        return None
    # skip flag byte at offset
    msg_type = struct.unpack(">H", data[offset + 1: offset + 3])[0]
    payload = data[offset + 3:]
    return msg_type, payload


def _read_bit_field(buf: bytes, byte_offset: int, bit_offset: int, length: int) -> int:
    """Extract a bit-field value from buffer."""
    if byte_offset >= len(buf):
        return 0
    byte = buf[byte_offset]
    mask = (1 << length) - 1
    return (byte >> bit_offset) & mask


def _write_bit_field(buf: bytearray, byte_offset: int, bit_offset: int, length: int, value: int) -> None:
    """Write a bit-field into buffer in-place."""
    mask = ((1 << length) - 1) << bit_offset
    buf[byte_offset] = (buf[byte_offset] & ~mask) | ((value << bit_offset) & mask)


def parse_status_buffer(raw: bytes) -> dict[str, any]:
    """Parse raw status buffer into {endpoint_name: value} dict."""
    result: dict[str, any] = {}
    for ep in ALL_ENDPOINTS:
        if ep.byte_offset >= len(raw):
            continue
        if ep.unit == "bit":
            raw_val = _read_bit_field(raw, ep.byte_offset, ep.bit_offset, ep.length)
            if ep.data_type == "bool":
                result[ep.name] = bool(raw_val)
            elif ep.data_type == "enum" and ep.enum_values:
                idx = min(raw_val, len(ep.enum_values) - 1)
                result[ep.name] = ep.enum_values[idx]
        elif ep.unit == "byte":
            result[ep.name] = raw[ep.byte_offset]
    return result


def build_control_payload(
    endpoint: EndpointDef,
    value: any,
    ctrl_cache: bytes | None,
) -> bytes:
    """Build DATA_CONTROL_REQUEST payload for a single endpoint change.

    flags:  WRITABLE_FLAG_SIZE bytes, big-endian bitmask (bit = endpoint id)
    values: WRITABLE_VALUE_SIZE bytes — all zeros except the changed endpoint.
            Bytes 0..CTRL_CACHE_SIZE-1 are copied from ctrl_cache first so that
            bit-packed fields in byte 0 survive a read-modify-write correctly.
    """
    buf = bytearray(WRITABLE_VALUE_SIZE)
    # Seed the first CTRL_CACHE_SIZE bytes from cached pump state
    if ctrl_cache:
        n = min(len(ctrl_cache), CTRL_CACHE_SIZE)
        buf[:n] = ctrl_cache[:n]

    if endpoint.unit == "bit":
        if endpoint.data_type == "bool":
            _write_bit_field(buf, endpoint.byte_offset, endpoint.bit_offset, endpoint.length, int(bool(value)))
        elif endpoint.data_type == "enum" and endpoint.enum_values:
            idx = endpoint.enum_values.index(value) if value in endpoint.enum_values else 0
            _write_bit_field(buf, endpoint.byte_offset, endpoint.bit_offset, endpoint.length, idx)
    elif endpoint.unit == "byte":
        buf[endpoint.byte_offset] = int(value)

    # Flags: WRITABLE_FLAG_SIZE bytes, big-endian, bit position = endpoint id
    flags = (1 << endpoint.endpoint_id).to_bytes(WRITABLE_FLAG_SIZE, byteorder="big")

    return flags + bytes(buf)


class AquaForteProtocol:
    """Manages TCP connection and binary protocol with one AquaForte device."""

    def __init__(self, host: str) -> None:
        self._host = host
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._packet_counter = 0
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Open TCP connection to device."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, TCP_PORT),
            timeout=CONNECT_TIMEOUT,
        )
        self._connected = True
        _LOGGER.debug("Connected to %s:%d", self._host, TCP_PORT)

    async def disconnect(self) -> None:
        """Close TCP connection."""
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    async def _send(self, msg_type: int, payload: bytes = b"") -> None:
        """Send a packet."""
        if not self._writer:
            raise ConnectionError("Not connected")
        pkt = build_packet(msg_type, payload)
        self._writer.write(pkt)
        await self._writer.drain()

    async def _recv(self) -> tuple[int, bytes]:
        """Receive and parse one packet.

        Accepts both 0x00000003 (client→device) and 0xEEEEEEEE (device push)
        prefixes — both use the same varint+flag+type+payload body format.
        """
        if not self._reader:
            raise ConnectionError("Not connected")

        prefix = await asyncio.wait_for(self._reader.readexactly(4), timeout=RESPONSE_TIMEOUT)
        known = {b"\x00\x00\x00\x03", b"\xee\xee\xee\xee"}
        if prefix not in known:
            raise ValueError(f"Unknown packet prefix: {prefix.hex()}")

        # Read varint length byte-by-byte (status buffer is >127 bytes → 2-byte varint)
        varint_raw = bytearray()
        while True:
            byte_val = (await asyncio.wait_for(self._reader.readexactly(1), timeout=RESPONSE_TIMEOUT))[0]
            varint_raw.append(byte_val)
            if not (byte_val & 0x80):
                break
        body_len, _ = decode_varint(bytes(varint_raw), 0)

        body = await asyncio.wait_for(self._reader.readexactly(body_len), timeout=RESPONSE_TIMEOUT)
        if len(body) < 3:
            raise ValueError(f"Packet body too short: {len(body)}")
        # body = [flag 1B][type 2B BE][payload …]
        msg_type = struct.unpack(">H", body[1:3])[0]
        payload = body[3:]
        return msg_type, payload

    async def get_passcode(self) -> str:
        """Request passcode from device."""
        await self._send(MSG_PASSCODE_REQUEST)
        msg_type, payload = await self._recv()
        if msg_type != MSG_PASSCODE_RESPONSE:
            raise ValueError(f"Expected passcode response, got 0x{msg_type:04x}")
        # Passcode is length-prefixed UTF-8 string
        length = struct.unpack(">H", payload[:2])[0]
        return payload[2: 2 + length].decode("utf-8")

    async def login(self, passcode: str) -> bool:
        """Login with passcode. Returns True on success."""
        encoded = passcode.encode("utf-8")
        payload = struct.pack(">H", len(encoded)) + encoded
        await self._send(MSG_LOGIN_REQUEST, payload)
        msg_type, resp_payload = await self._recv()
        if msg_type != MSG_LOGIN_RESPONSE:
            raise ValueError(f"Expected login response, got 0x{msg_type:04x}")
        success = len(resp_payload) > 0 and resp_payload[0] == 0x00
        _LOGGER.debug("Login %s", "OK" if success else "FAILED")
        return success

    async def ping(self) -> None:
        """Send keepalive ping, skip any stale packets until PING_RESPONSE arrives."""
        await self._send(MSG_PING_REQUEST)
        while True:
            msg_type, _ = await self._recv()
            if msg_type == MSG_PING_RESPONSE:
                break
            # Consume stale packets (control responses, unsolicited status)
            _LOGGER.debug("Skipping stale packet 0x%04x during ping", msg_type)

    async def read_status(self) -> bytes:
        """Request full device status. Returns raw status buffer."""
        await self._send(MSG_DATA_TRANSMIT_REQ, bytes([P0_READ_STATUS]))
        while True:
            msg_type, payload = await self._recv()
            if msg_type == MSG_DATA_TRANSMIT_RSP:
                if not payload:
                    raise ValueError("Empty status response")
                p0 = payload[0]
                if p0 in (P0_STATUS_REPLY, P0_STATUS_REPORT):
                    return payload[1:]
                _LOGGER.debug("Ignoring status response with P0=0x%02x", p0)
            else:
                # Skip stale control responses, ping responses, etc.
                _LOGGER.debug("Skipping stale packet 0x%04x while waiting for status", msg_type)

    async def send_command(
        self,
        endpoint: EndpointDef,
        value: any,
        current_ctrl_bytes: bytes | None = None,
    ) -> None:
        """Send a control command (fire-and-forget).

        The pump processes commands independently. We don't wait for the
        control response (0x0094) to avoid stale-packet race conditions with
        the unsolicited status push (0xEEEEEEEE) the device sends after login
        and after each command. Confirmation happens implicitly via the next
        read_status() poll.
        """
        self._packet_counter += 1
        ctrl_payload = build_control_payload(endpoint, value, current_ctrl_bytes)
        payload = (
            struct.pack(">I", self._packet_counter)
            + bytes([P0_CONTROL_DEVICE])
            + ctrl_payload
        )
        _LOGGER.debug(
            "CMD %s=%s  counter=%d  flags=0x%02x  buf=%s",
            endpoint.name, value, self._packet_counter,
            ctrl_payload[0], ctrl_payload[1:].hex(),
        )
        await self._send(MSG_DATA_CONTROL_REQ, payload)


async def discover_devices(broadcast_ip: str = "255.255.255.255") -> list[DeviceInfo]:
    """Broadcast UDP discovery, return list of found DeviceInfo."""
    discovery_msg = build_packet(MSG_DISCOVER_REQUEST, b"\x03")
    devices: list[DeviceInfo] = []

    loop = asyncio.get_event_loop()

    def _run_discovery() -> list[tuple[bytes, str]]:
        responses: list[tuple[bytes, str]] = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(DISCOVERY_TIMEOUT)
        try:
            sock.sendto(discovery_msg, (broadcast_ip, UDP_PORT))
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    responses.append((data, addr[0]))
                except socket.timeout:
                    break
        finally:
            sock.close()
        return responses

    responses = await loop.run_in_executor(None, _run_discovery)

    for data, host in responses:
        parsed = parse_packet(data)
        if not parsed:
            continue
        msg_type, payload = parsed
        if msg_type != MSG_DISCOVER_RESPONSE:
            continue
        try:
            info = _parse_discover_response(payload, host)
            if info:
                devices.append(info)
        except Exception as exc:
            _LOGGER.debug("Failed to parse discovery response from %s: %s", host, exc)

    return devices


def _parse_discover_response(payload: bytes, host: str) -> DeviceInfo | None:
    """Parse discovery response payload into DeviceInfo."""
    offset = 0

    def read_length_prefixed() -> bytes:
        nonlocal offset
        if offset + 2 > len(payload):
            raise ValueError("Truncated discovery response")
        length = struct.unpack(">H", payload[offset: offset + 2])[0]
        offset += 2
        value = payload[offset: offset + length]
        offset += length
        return value

    device_id = read_length_prefixed().decode("ascii", errors="replace")
    mac = read_length_prefixed()
    wifi_version = read_length_prefixed().decode("ascii", errors="replace")
    product_key = read_length_prefixed().decode("ascii", errors="replace")

    return DeviceInfo(
        device_id=device_id,
        mac=mac,
        wifi_version=wifi_version,
        product_key=product_key,
        host=host,
    )
