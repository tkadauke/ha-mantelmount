# MantelMount for Home Assistant

Local control of MantelMount motorized TV mounts with the network adapter, such as the
MM860 and MM850 families.

Developed against an adapter running firmware 693. Other models and firmware may differ.

## Features

- **Movement**: home (stow), recall presets 1–3, save presets 1–3, jog up/down/left/right, stop.
- **Position**: elevation and swivel in degrees, an "at home position" sensor, and a moving sensor.
- **ALPS** (auto lowering power sensing): see whether the mount detects the TV as on, the TV
  current it measures, and change the ALPS switch, the TV on/off current thresholds, and smooth start.
- **Diagnostics**: error code, position lost flag, last preset, temperature status, actuator and
  motor readings, firmware version.
- **Discovery**: adapters are discovered over DHCP by their `MantelMount_*` host name, and the
  configured address follows DHCP changes.

## Installation

1. In HACS, open the menu, choose **Custom repositories**, and add
   `https://github.com/tkadauke/ha-mantelmount` as an **Integration**.
2. Install **MantelMount** and restart Home Assistant.
3. Accept the discovered mount under **Settings → Devices & services**, or add it with
   **Add integration → MantelMount** and enter its address.

Home Assistant must reach the adapter on UDP port 81 and HTTP port 80. The adapter's
discovery broadcasts do not cross VLANs, but this integration only needs unicast access.

## Tuning ALPS

ALPS lowers the mount when the TV draws more than the *TV on threshold* and raises it once
the draw falls below the *TV off threshold*. Watch the **TV current** sensor while the TV is
off, on, and on with a dark picture. Pick an on threshold comfortably above the standby
current and below the lowest current the TV draws while on, and an off threshold between
standby and the on threshold. A TV whose power saving mode dips below the on threshold
will only lower the mount sometimes.

## Protocol

The adapter answers ASCII commands terminated by a carriage return on UDP port 81:

| Command | Meaning | Reply |
|---|---|---|
| `MMQ` | Status query | `MMQ` and 16 comma-separated fields |
| `MMR0` | Move to the home (stowed) position | `MMR` |
| `MMR1`–`MMR3` | Recall a preset | `MMR` |
| `MMS1`–`MMS3` | Save the current position as a preset | `MMS` |
| `MMJ0`–`MMJ4` | Jog: stop, right, up, left, down | `MMJ` |

The status fields are: error code, two position fields, left and right actuator, last preset,
temperature, TV state, last event source, firmware version, position lost flag, TV current,
left and right limit, and left and right motor current. Published drivers disagree on the
order of the two position fields, so the integration reads position, temperature status, and
the ALPS state from the web UI's `ajax.shtml` instead. ALPS settings come from the
`device.shtml` form, which posts to `save_device.xml`.

Commands are retried when the acknowledgement is lost, except jogs, which would otherwise
move the mount twice. The adapter is polled every 5 seconds, every second while it moves
or right after a command, and ALPS settings are re-read every 5 minutes.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install "pytest-homeassistant-custom-component==0.13.323" ruff
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

This project is not affiliated with or endorsed by MantelMount.
