from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@dataclass
class MqttConfig:
    host: str = "core-mosquitto"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "ocppsigen2mqtt"
    topic_prefix: str = "ocpp"


@dataclass
class OcppConfig:
    host: str = "0.0.0.0"
    port: int = 9200


@dataclass
class Config:
    ocpp: OcppConfig = field(default_factory=OcppConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    charger_id: str = "CHARGER01"
    usable_phases: int = 2
    log_level: str = "INFO"
    authorize_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        cfg.ocpp.host = os.getenv("OCPP_HOST", cfg.ocpp.host)
        cfg.ocpp.port = int(os.getenv("OCPP_PORT", cfg.ocpp.port))
        cfg.mqtt.host = os.getenv("MQTT_HOST", cfg.mqtt.host)
        cfg.mqtt.port = int(os.getenv("MQTT_PORT", cfg.mqtt.port))
        cfg.mqtt.username = os.getenv("MQTT_USER") or cfg.mqtt.username
        cfg.mqtt.password = os.getenv("MQTT_PASS") or cfg.mqtt.password
        cfg.mqtt.client_id = os.getenv("MQTT_CLIENT_ID", cfg.mqtt.client_id)
        cfg.mqtt.topic_prefix = os.getenv("MQTT_TOPIC_PREFIX", cfg.mqtt.topic_prefix)
        cfg.charger_id = os.getenv("CHARGER_ID", cfg.charger_id)
        try:
            cfg.usable_phases = int(os.getenv("OCPP_USABLE_PHASES", str(cfg.usable_phases)))
        except ValueError:
            pass
        cfg.usable_phases = max(1, min(3, cfg.usable_phases))
        cfg.log_level = os.getenv("LOG_LEVEL", cfg.log_level)
        cfg.authorize_enabled = os.getenv("OCPP_AUTHORIZE_ENABLED", "true").lower() in ("true", "1", "yes")
        return cfg

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        cfg = cls.from_env()
        ocpp = data.get("ocpp", {})
        cfg.ocpp.host = ocpp.get("host", cfg.ocpp.host)
        cfg.ocpp.port = int(ocpp.get("port", cfg.ocpp.port))
        mqtt = data.get("mqtt", {})
        cfg.mqtt.host = mqtt.get("host", cfg.mqtt.host)
        cfg.mqtt.port = int(mqtt.get("port", cfg.mqtt.port))
        cfg.mqtt.username = mqtt.get("username") or cfg.mqtt.username
        cfg.mqtt.password = mqtt.get("password") or cfg.mqtt.password
        cfg.mqtt.client_id = mqtt.get("client_id", cfg.mqtt.client_id)
        cfg.mqtt.topic_prefix = mqtt.get("topic_prefix", cfg.mqtt.topic_prefix)
        cfg.charger_id = data.get("charger_id", cfg.charger_id)
        cfg.usable_phases = int(data.get("usable_phases", cfg.usable_phases))
        cfg.usable_phases = max(1, min(3, cfg.usable_phases))
        cfg.log_level = data.get("log_level", cfg.log_level)
        cfg.authorize_enabled = data.get("authorize_enabled", cfg.authorize_enabled)
        return cfg

    @classmethod
    def load(cls, config_file: str | Path | None = None) -> "Config":
        repo_root = Path(__file__).resolve().parents[1]
        _load_env_file(Path.cwd() / ".env")
        _load_env_file(repo_root / ".env")
        if config_file and Path(config_file).exists():
            return cls.from_yaml(config_file)
        return cls.from_env()
