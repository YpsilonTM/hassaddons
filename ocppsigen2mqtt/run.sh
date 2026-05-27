#!/usr/bin/env bash
set -euo pipefail

if [ -f /data/options.json ]; then
    eval "$({
        python3 - <<'PY'
import json
import shlex
from pathlib import Path

options_path = Path('/data/options.json')
with options_path.open('r', encoding='utf-8') as fh:
    options = json.load(fh)

env_map = {
    'OCPP_HOST': options.get('ocpp_host', '0.0.0.0'),
    'OCPP_PORT': options.get('ocpp_port', 9200),
    'CHARGER_ID': options.get('charger_id', '120A64150210'),
    'OCPP_USABLE_PHASES': options.get('usable_phases', 2),
    'OCPP_AUTHORIZE_ENABLED': options.get('authorize_enabled', True),
    'MQTT_HOST': options.get('mqtt_host', 'core-mosquitto'),
    'MQTT_PORT': options.get('mqtt_port', 1883),
    'MQTT_USER': options.get('mqtt_username', ''),
    'MQTT_PASS': options.get('mqtt_password', ''),
    'MQTT_CLIENT_ID': options.get('mqtt_client_id', 'ocppsigen2mqtt-addon'),
    'MQTT_TOPIC_PREFIX': options.get('topic_prefix', 'ocpp'),
    'LOG_LEVEL': options.get('log_level', 'INFO'),
}

for key, value in env_map.items():
    print(f"export {key}={shlex.quote(str(value))}")
PY
    })"
fi

exec python3 /app/src/server.py
