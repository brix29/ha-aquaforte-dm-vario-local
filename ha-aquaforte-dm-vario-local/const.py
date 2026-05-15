"""Constants for AquaForte DM-VARIO integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DOMAIN = "aquaforte"

TCP_PORT = 12416
UDP_PORT = 12414
KEEPALIVE_INTERVAL = 5       # seconds between pings
POLL_INTERVAL = 120          # seconds between status polls
CONNECT_TIMEOUT = 10         # seconds
RESPONSE_TIMEOUT = 5         # seconds
RECONNECT_INTERVAL = 10      # seconds
DISCOVERY_TIMEOUT = 2        # seconds waiting for UDP replies

CONF_HOST = "host"
CONF_DEVICE_ID = "device_id"
CONF_NAME = "name"

# Byte offsets in control/status buffer
FAULT_BYTE = 301        # All 7 fault bits packed here

# Writable payload sizes (from full endpoint JSON: 51 writable endpoints, ids 0–58)
# flags:  ceil(51 / 8) = 7 bytes — but use 8 to safely cover id=58 (AutoTime47)
# values: max(byte_offset + len) across all writable endpoints = 295 + 6 = 301 bytes
WRITABLE_FLAG_SIZE  = 8    # bytes for the attribute-flags bitmask
WRITABLE_VALUE_SIZE = 301  # bytes for the attribute-values buffer
CTRL_CACHE_SIZE     = 5    # bytes to cache from status (covers ids 0–8, byte offsets 0–4)

# Message types (big-endian 2-byte command codes)
MSG_PASSCODE_REQUEST  = 0x0006
MSG_PASSCODE_RESPONSE = 0x0007
MSG_LOGIN_REQUEST     = 0x0008
MSG_LOGIN_RESPONSE    = 0x0009
MSG_PING_REQUEST      = 0x0015
MSG_PING_RESPONSE     = 0x0016
MSG_DATA_TRANSMIT_REQ = 0x0090
MSG_DATA_TRANSMIT_RSP = 0x0091
MSG_DATA_CONTROL_REQ  = 0x0093
MSG_DATA_CONTROL_RSP  = 0x0094
MSG_DISCOVER_REQUEST  = 0x0003
MSG_DISCOVER_RESPONSE = 0x0004

PACKET_PREFIX = b"\x00\x00\x00\x03"
P0_READ_STATUS    = 0x02
P0_STATUS_REPLY   = 0x03
P0_STATUS_REPORT  = 0x04
P0_CONTROL_DEVICE = 0x01


@dataclass
class EndpointDef:
    name: str
    byte_offset: int
    bit_offset: int
    unit: str          # "bit" or "byte"
    length: int
    data_type: str     # "bool", "uint8", "enum"
    endpoint_id: int
    writable: bool
    enum_values: list[str] | None = None
    min_val: int | None = None
    max_val: int | None = None


# Writable control endpoints
EP_SWITCH_ON = EndpointDef(
    name="SwitchON",
    byte_offset=0, bit_offset=0, unit="bit", length=1,
    data_type="bool", endpoint_id=0, writable=True,
)
EP_FEED_SWITCH = EndpointDef(
    name="FeedSwitch",
    byte_offset=0, bit_offset=2, unit="bit", length=1,
    data_type="bool", endpoint_id=2, writable=True,
)
EP_AUTO_MODE = EndpointDef(
    name="AutoMode",
    byte_offset=0, bit_offset=4, unit="bit", length=2,
    data_type="enum", endpoint_id=4, writable=True,
    enum_values=["Shutdown", "Automatic", "Feed"],
)
EP_MOTOR_SPEED = EndpointDef(
    name="Motor_Speed",
    byte_offset=1, bit_offset=0, unit="byte", length=1,
    data_type="uint8", endpoint_id=5, writable=True,
    min_val=0, max_val=100,
)
EP_FEED_TIME = EndpointDef(
    name="FeedTime",
    byte_offset=2, bit_offset=0, unit="byte", length=1,
    data_type="uint8", endpoint_id=6, writable=True,
    min_val=1, max_val=60,
)

# Read-only fault endpoints (all in byte 301)
EP_FAULT_OVERCURRENT = EndpointDef(
    name="Fault_Overcurrent",
    byte_offset=301, bit_offset=0, unit="bit", length=1,
    data_type="bool", endpoint_id=59, writable=False,
)
EP_FAULT_OVERVOLTAGE = EndpointDef(
    name="Fault_Overvoltage",
    byte_offset=301, bit_offset=1, unit="bit", length=1,
    data_type="bool", endpoint_id=60, writable=False,
)
EP_FAULT_OVERTEMP = EndpointDef(
    name="Fault_OverTemp",
    byte_offset=301, bit_offset=2, unit="bit", length=1,
    data_type="bool", endpoint_id=61, writable=False,
)
EP_FAULT_UNDERVOLTAGE = EndpointDef(
    name="Fault_Undervoltage",
    byte_offset=301, bit_offset=3, unit="bit", length=1,
    data_type="bool", endpoint_id=62, writable=False,
)
EP_FAULT_LOCKED_ROTOR = EndpointDef(
    name="Fault_LockedRotor",
    byte_offset=301, bit_offset=4, unit="bit", length=1,
    data_type="bool", endpoint_id=63, writable=False,
)
EP_FAULT_NO_LOAD = EndpointDef(
    name="Fault_NoLoad",
    byte_offset=301, bit_offset=5, unit="bit", length=1,
    data_type="bool", endpoint_id=64, writable=False,
)
EP_FAULT_UART = EndpointDef(
    name="Fault_UART",
    byte_offset=301, bit_offset=6, unit="bit", length=1,
    data_type="bool", endpoint_id=65, writable=False,
)

WRITABLE_ENDPOINTS: list[EndpointDef] = [
    EP_SWITCH_ON,
    EP_FEED_SWITCH,
    EP_AUTO_MODE,
    EP_MOTOR_SPEED,
    EP_FEED_TIME,
]

FAULT_ENDPOINTS: list[EndpointDef] = [
    EP_FAULT_OVERCURRENT,
    EP_FAULT_OVERVOLTAGE,
    EP_FAULT_OVERTEMP,
    EP_FAULT_UNDERVOLTAGE,
    EP_FAULT_LOCKED_ROTOR,
    EP_FAULT_NO_LOAD,
    EP_FAULT_UART,
]

ALL_ENDPOINTS: list[EndpointDef] = WRITABLE_ENDPOINTS + FAULT_ENDPOINTS

AUTOMODE_OPTIONS = ["Shutdown", "Automatic", "Feed"]
AUTOMODE_SHUTDOWN  = "Shutdown"
AUTOMODE_AUTOMATIC = "Automatic"
AUTOMODE_FEED      = "Feed"
