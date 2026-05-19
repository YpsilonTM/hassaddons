from __future__ import annotations

from src.models import MqttConfig, ReadingDefinition
from src.mqtt_client import MqttPublisher


def build_state_topic(mqtt: MqttConfig, reading: ReadingDefinition) -> str:
    return f"{mqtt.topic_prefix}/{reading.topic_suffix}/state"


def serialize_value(value: int | float) -> str:
    return str(value)


def publish_reading(
    mqtt: MqttConfig,
    client: MqttPublisher,
    reading: ReadingDefinition,
    value: int | float,
) -> None:
    topic = build_state_topic(mqtt, reading)
    payload = serialize_value(value)
    client.publish_state(topic=topic, payload=payload, retain=mqtt.retain_state)
