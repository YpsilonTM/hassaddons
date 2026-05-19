
# ModQTT

ModQTT is a general-purpose Modbus TCP to MQTT bridge. It reads values from any Modbus TCP device (such as inverters, meters, or industrial equipment) and publishes them to MQTT topics for integration with Home Assistant or other systems. While commonly used with Sungrow inverters, it is not limited to any specific device or manufacturer.


## Features

- Read Modbus input/holding registers from any Modbus TCP device
- Decode u16/s16/u32/s32/f32 with byte/word order control
- Publish to configurable MQTT topic prefix
- Optional write parameters with explicit safety flags


## Installation

1. In Home Assistant, go to Settings → Add-ons → Add-on Store.
2. Add this repository URL:
   - https://github.com/YpsilonTM/ModQTT
3. Install the ModQTT add-on.


## Basic configuration

Set at least these options:

- `modbus_host`: IP address of your Modbus TCP device
- `mqtt_host`: MQTT broker address
- `readings`: List of register definitions to read and publish

You can also use a separate YAML file for bulk register definitions:

- Set add-on option `registers_file` to a path (e.g., `/config/modqtt-registers.yml`).
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

Write mode is disabled by default for safety:

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
