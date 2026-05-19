#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
from pathlib import Path

import yaml

options_path = Path('/data/options.json')
if not options_path.exists():
    raise SystemExit('Missing /data/options.json (Home Assistant add-on options)')

with options_path.open('r', encoding='utf-8') as handle:
    options = json.load(handle)

config = {
    'profile': options.get('profile', 'dev'),
    'read_only_mode': options.get('read_only_mode', True),
    'allow_writes': options.get('allow_writes', False),
    'modbus': {
        'host': options.get('modbus_host', '127.0.0.1'),
        'port': options.get('modbus_port', 502),
        'unit_id': options.get('modbus_unit_id', 1),
        'timeout_seconds': options.get('modbus_timeout_seconds', 3.0),
        'poll_interval_seconds': options.get('poll_interval_seconds', 5.0),
    },
    'mqtt': {
        'host': options.get('mqtt_host', 'core-mosquitto'),
        'port': options.get('mqtt_port', 1883),
        'username': options.get('mqtt_username') or None,
        'password': options.get('mqtt_password') or None,
        'client_id': options.get('mqtt_client_id', 'modqtt-addon'),
        'topic_prefix': options.get('topic_prefix', 'dev/sungrow'),
        'availability_topic': options.get('availability_topic', 'bridge/availability'),
        'retain_state': options.get('retain_state', True),
        'json_grouped_topics': options.get('json_grouped_topics', False),
        'discovery_enabled': options.get('discovery_enabled', False),
    },
    'readings': options.get('readings', []),
    'write_parameters': options.get('write_parameters', []),
}

output_path = Path('/data/modqtt.runtime.yml')
with output_path.open('w', encoding='utf-8') as handle:
    yaml.safe_dump(config, handle, sort_keys=False)

print(f'Generated runtime config at {output_path}')
PY

exec python3 -m src.app --config /data/modqtt.runtime.yml
