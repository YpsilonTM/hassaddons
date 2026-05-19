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

You can also use a separate YAML file for bulk register definitions.

- Set add-on option `registers_file` to a path (for example `/config/modqtt-registers.yml`).
- The file can contain `readings` and optional `write_parameters`.
- When `registers_file` is set, values from that file are used for these sections.

Example file structure (`/config/modqtt-registers.yml`):

```yaml
readings:
   - name: inverter_temperature
      label: Inverter temperature
      topic_suffix: inverter_temperature
      register_type: input
      address: 5007
      length_words: 1
      data_type: s16
      scale: 0.1
      offset: 0
      decimals: 1
      byte_order: big
      word_order: big
      unit: C
      device_class: temperature
      state_class: measurement
      entityCategory: diagnostic

write_parameters:
   - name: battery_max_soc
      label: Battery max SoC
      register_type: holding
      address: 13057
      length_words: 1
      data_type: u16
      scale: 0.1
      offset: 0
      decimals: 1
      byte_order: big
      word_order: big
      entityCategory: config
      min_value: 50.0
      max_value: 100.0
```

You can find a larger starter template in `registers.example.yml` in this add-on folder.

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

## Local app testing (Home Assistant)

Use this workflow to test changes before publishing:

1. Open this repository in VS Code and reopen in devcontainer.
2. Run the VS Code task `Start Home Assistant` (runs `supervisor_run`).
3. Open Home Assistant from the forwarded devcontainer port.
4. Install ModQTT from the local add-on repository.
5. Configure `modbus_host`, `mqtt_host`, and a minimal `readings` set.
6. Start the add-on and inspect logs for decode and MQTT publish behavior.
7. Validate published topics in MQTT Explorer and Home Assistant Developer Tools.

If you need physical hardware access on a remote Home Assistant host, copy the `modqtt` folder to `/addons` on that host (for example using Samba or SSH), and keep `image` disabled in add-on `config.yaml` so the add-on is built locally by Supervisor.
