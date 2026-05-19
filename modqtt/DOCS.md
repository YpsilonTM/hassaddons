# ModQTT

ModQTT is a Home Assistant add-on that reads Sungrow inverter values over Modbus TCP and publishes them to MQTT.

## Features

- Read Modbus input/holding registers
- Decode u16/s16/u32/s32/f32 with byte/word order control
- Publish to configurable MQTT topic prefix
- Optional write parameters with explicit safety flags

## Installation

1. In Home Assistant, go to Settings -> Add-ons -> Add-on Store.
2. Add this repository URL:
   - https://github.com/YpsilonTM/ModQTT
3. Install the ModQTT add-on.

## Basic configuration

Set at least these options:

- `modbus_host`
- `mqtt_host`
- `readings` (list of register definitions)

Default profile is production-safe topic routing:

- `profile: prod`
- `topic_prefix: prod/sungrow`

For development, switch to:

- `profile: dev`
- `topic_prefix: dev/sungrow`

## Safety for write operations

Write mode is disabled by default.

- `read_only_mode: true`
- `allow_writes: false`

To allow writes, both must be changed:

- `read_only_mode: false`
- `allow_writes: true`

Only parameters listed under `write_parameters` are writable.

## Notes

- Add-on options are stored in `/data/options.json`.
- The add-on generates runtime config at `/data/modqtt.runtime.yml`.
- Runtime logs are available in the add-on Log tab.
