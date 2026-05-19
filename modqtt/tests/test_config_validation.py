from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import load_config


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_minimal_valid_config(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "config.yml",
        """
profile: dev
read_only_mode: true
allow_writes: false
modbus:
  host: 192.168.1.10
mqtt:
  host: 192.168.1.20
  topic_prefix: dev/sungrow
readings:
  - name: pv_power
    label: PV Power
    icon: mdi:solar-power
    entityCategory: diagnostic
    topic_suffix: pv_power
    register_type: input
    address: 13001
    length_words: 2
    data_type: u32
    scale: 0.1
    offset: 0
    decimals: 1
    byte_order: big
    word_order: big
""".strip(),
    )

    cfg = load_config(config_path)

    assert cfg.profile == "dev"
    assert cfg.modbus.port == 502
    assert cfg.mqtt.topic_prefix == "dev/sungrow"
    assert len(cfg.readings) == 1


def test_dev_profile_rejects_prod_prefix(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path / "bad.yml",
        """
profile: dev
read_only_mode: true
allow_writes: false
modbus:
  host: inverter.local
mqtt:
  host: broker.local
  topic_prefix: prod/sungrow
readings:
  - name: test
    topic_suffix: test
    register_type: input
    address: 1
    length_words: 1
    data_type: u16
""".strip(),
    )

    with pytest.raises(ValidationError):
        load_config(config_path)


def test_environment_variables_do_not_override_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write(
        tmp_path / "env_ignored.yml",
        """
profile: dev
read_only_mode: true
allow_writes: false
modbus:
  host: inverter.local
mqtt:
  host: broker.local
  topic_prefix: dev/sungrow
readings:
  - name: test
    topic_suffix: test
    register_type: input
    address: 1
    length_words: 1
    data_type: u16
""".strip(),
    )

    monkeypatch.setenv("MODQTT_MODBUS_HOST", "should-not-be-used")
    monkeypatch.setenv("MODQTT_TOPIC_PREFIX", "prod/sungrow")

    cfg = load_config(config_path)

    assert cfg.modbus.host == "inverter.local"
    assert cfg.mqtt.topic_prefix == "dev/sungrow"


def test_load_readings_from_registers_file(tmp_path: Path) -> None:
    registers_path = _write(
        tmp_path / "registers.yml",
        """
readings:
  - name: grid_power
    topic_suffix: grid_power
    register_type: input
    address: 13033
    length_words: 2
    data_type: s32
    scale: 1.0
    offset: 0
    decimals: 0
    byte_order: big
    word_order: little
write_parameters:
  - name: ems_mode
    register_type: holding
    address: 13049
    length_words: 1
    data_type: u16
    scale: 1.0
    offset: 0
    decimals: 0
    byte_order: big
    word_order: big
""".strip(),
    )

    config_path = _write(
        tmp_path / "config.yml",
        f"""
profile: prod
read_only_mode: true
allow_writes: false
registers_file: {registers_path.name}
modbus:
  host: inverter.local
mqtt:
  host: broker.local
  topic_prefix: prod/sungrow
readings: []
write_parameters: []
""".strip(),
    )

    cfg = load_config(config_path)

    assert len(cfg.readings) == 1
    assert cfg.readings[0].name == "grid_power"
    assert len(cfg.write_parameters) == 1
    assert cfg.write_parameters[0].name == "ems_mode"


def test_registers_file_replaces_inline_readings(tmp_path: Path) -> None:
    _write(
        tmp_path / "registers.yml",
        """
readings:
  - name: from_file
    topic_suffix: from_file
    register_type: input
    address: 1
    length_words: 1
    data_type: u16
""".strip(),
    )

    config_path = _write(
        tmp_path / "config.yml",
        """
profile: prod
read_only_mode: true
allow_writes: false
registers_file: registers.yml
modbus:
  host: inverter.local
mqtt:
  host: broker.local
  topic_prefix: prod/sungrow
readings:
  - name: inline
    topic_suffix: inline
    register_type: input
    address: 2
    length_words: 1
    data_type: u16
write_parameters: []
""".strip(),
    )

    cfg = load_config(config_path)

    assert len(cfg.readings) == 1
    assert cfg.readings[0].name == "from_file"
