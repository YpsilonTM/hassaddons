from __future__ import annotations

from src.models import MqttConfig, ReadingDefinition
import json
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


def build_discovery_topic(mqtt: MqttConfig, reading: ReadingDefinition) -> str:
    # Home Assistant expects: <discovery_prefix>/<component>/<object_id>/config
    # Default discovery_prefix is 'homeassistant'
    # We'll use sensor as component for all readings
    object_id = reading.topic_suffix
    return f"homeassistant/sensor/{object_id}/config"


def build_discovery_payload(mqtt: MqttConfig, reading: ReadingDefinition) -> dict:
    # Compose a Home Assistant MQTT discovery payload for a sensor
    unique_id = f"{mqtt.client_id}_{reading.topic_suffix}"
    state_topic = build_state_topic(mqtt, reading)
    payload = {
        "name": reading.label or reading.name,
        "unique_id": unique_id,
        "state_topic": state_topic,
        "availability_topic": mqtt.availability_topic,
        "device": {
            "identifiers": [mqtt.client_id],
            "name": "Sungrow Inverter",
            "manufacturer": "Sungrow",
            "model": "ModQTT Bridge",
        },
    }
    if reading.unit:
        payload["unit_of_measurement"] = reading.unit
    if reading.device_class:
        payload["device_class"] = reading.device_class
    if reading.state_class:
        payload["state_class"] = reading.state_class
    if reading.icon:
        payload["icon"] = reading.icon
    if reading.entity_category:
        payload["entity_category"] = reading.entity_category
    return payload


def publish_discovery(mqtt: MqttConfig, client: MqttPublisher, readings: list[ReadingDefinition]) -> None:
    for reading in readings:
        topic = build_discovery_topic(mqtt, reading)
        payload = build_discovery_payload(mqtt, reading)
        client.publish_state(topic=topic, payload=json.dumps(payload), retain=True)
