# AquaForte DM-VARIO Local – Home Assistant Integration

> **⚠️ Beta – work in progress.** Tested by a limited number of users. Use at your own risk and please report issues.

Local-only Home Assistant integration for the **AquaForte DM-VARIO WIFI** pond/pool pump.  
Controls the pump directly over your local network — no cloud, no MQTT broker required.

## Features

| Entity | Type | Description |
|--------|------|-------------|
| Pump on/off | Switch | Power the pump on or off |
| Feed mode | Switch | Activate feeding pause mode |
| Operating mode | Select | Shutdown / Automatic / Feed |
| Pump speed | Number | Motor speed 30–100 % (slider) |
| Feed duration | Number | Feed pause duration 1–60 s |
| Fault sensors × 7 | Binary sensor | Overcurrent, Overvoltage, Overtemp, Undervoltage, Locked rotor, No load, UART (diagnostic) |

## Requirements

- AquaForte DM-VARIO WIFI pump on your local network
- Home Assistant 2024.1 or newer
- No external Python libraries needed

## Installation

1. Copy the `aquaforte_dm_vario_local/` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Integrations → Add integration** and search for **AquaForte**.
4. Choose **Discover** to auto-find the pump via UDP, or enter the IP address manually.

## Protocol

Communicates over the Gizwits LAN protocol:
- TCP port **12416** (control & status)
- UDP port **12414** (discovery)

Protocol reversed from [geelenbert/aquaforte-mqtt](https://github.com/geelenbert/aquaforte-mqtt).

## License

MIT
