from __future__ import annotations

# Test Home Assistant discovery payload generation
import math

import pytest
from src.models import MqttConfig, ReadingDefinition
from src.decoder import apply_transform, decode_raw_value
from src.publisher import build_discovery_payload

def test_build_discovery_payload_basic():
    mqtt = MqttConfig(
        host="localhost",
        port=1883,
        client_id="test-bridge",
        topic_prefix="dev/device",
        availability_topic="bridge/availability",
        retain_state=True,
        json_grouped_topics=False,
        discovery_enabled=True,
    )
    reading = ReadingDefinition(
        name="test_sensor",
        label="Test Sensor",
        topic_suffix="test_sensor",
        register_type="input",
        address=1,
        length_words=1,
        data_type="u16",
        scale=1.0,
        offset=0.0,
        decimals=0,
        byte_order="big",
        word_order="big",
        unit="V",
        device_class="voltage",
        state_class="measurement",
    )
    payload = build_discovery_payload(mqtt, reading)
    assert payload["name"] == "Test Sensor"
    assert payload["unique_id"] == "test-bridge_test_sensor"
    assert payload["state_topic"] == "dev/device/test_sensor/state"
    assert payload["availability_topic"] == "bridge/availability"
    assert payload["unit_of_measurement"] == "V"
    assert payload["device_class"] == "voltage"
    assert payload["state_class"] == "measurement"
    assert payload["device"]["identifiers"] == ["test-bridge"]


def test_build_discovery_payload_uses_configured_device_metadata():
    mqtt = MqttConfig(
        host="localhost",
        client_id="test-bridge",
        topic_prefix="dev/modqtt",
        availability_topic="bridge/availability",
        discovery_enabled=True,
        discovery_device_name="Battery Inverter",
        discovery_device_manufacturer="ACME Energy",
        discovery_device_model="Bridge X1",
    )
    reading = ReadingDefinition(
        name="test_sensor",
        topic_suffix="test_sensor",
        register_type="input",
        address=1,
        length_words=1,
        data_type="u16",
    )

    payload = build_discovery_payload(mqtt, reading)

    assert payload["device"] == {
        "identifiers": ["test-bridge"],
        "name": "Battery Inverter",
        "manufacturer": "ACME Energy",
        "model": "Bridge X1",
    }


@pytest.mark.parametrize(
    ("words", "expected"),
    [([0x1234], 0x1234), ([0xFFFF], 65535)],
)
def test_decode_u16(words: list[int], expected: int) -> None:
    assert decode_raw_value(words, data_type="u16", byte_order="big", word_order="big") == expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [([0x7FFF], 32767), ([0xFFFF], -1), ([0x8000], -32768)],
)
def test_decode_s16(words: list[int], expected: int) -> None:
    assert decode_raw_value(words, data_type="s16", byte_order="big", word_order="big") == expected


@pytest.mark.parametrize(
    ("byte_order", "word_order", "words", "expected"),
    [
        ("big", "big", [0x1234, 0x5678], 0x12345678),
        ("big", "little", [0x5678, 0x1234], 0x12345678),
        ("little", "big", [0x3412, 0x7856], 0x12345678),
        ("little", "little", [0x7856, 0x3412], 0x12345678),
    ],
)
def test_decode_u32_all_endian_paths(
    byte_order: str, word_order: str, words: list[int], expected: int
) -> None:
    assert (
        decode_raw_value(words, data_type="u32", byte_order=byte_order, word_order=word_order)
        == expected
    )


@pytest.mark.parametrize(
    ("byte_order", "word_order", "words", "expected"),
    [
        ("big", "big", [0xFFFF, 0xFFFF], -1),
        ("big", "little", [0xFFFF, 0xFFFF], -1),
        ("little", "big", [0xFFFF, 0xFFFF], -1),
        ("little", "little", [0xFFFF, 0xFFFF], -1),
    ],
)
def test_decode_s32_all_endian_paths(
    byte_order: str, word_order: str, words: list[int], expected: int
) -> None:
    assert (
        decode_raw_value(words, data_type="s32", byte_order=byte_order, word_order=word_order)
        == expected
    )


def test_decode_f32_example() -> None:
    value = decode_raw_value([0x3F80, 0x0000], data_type="f32", byte_order="big", word_order="big")
    assert math.isclose(value, 1.0)


def test_transform_order_scale_offset_round() -> None:
    assert apply_transform(100, scale=0.1, offset=-5, decimals=1) == 5.0


def test_invalid_word_length_raises() -> None:
    with pytest.raises(ValueError):
        decode_raw_value([0x0001], data_type="u32", byte_order="big", word_order="big")
