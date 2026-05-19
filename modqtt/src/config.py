from __future__ import annotations

from pathlib import Path

import yaml

from src.models import AppConfig


def _load_register_definitions(base_config_path: Path, file_path: str) -> dict:
    registers_path = Path(file_path)
    if not registers_path.is_absolute():
        registers_path = (base_config_path.parent / registers_path).resolve()

    with registers_path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle) or {}

    if not isinstance(parsed, dict):
        raise ValueError("registers_file must contain a top-level mapping")

    return parsed


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Configuration file must contain a top-level mapping")

    registers_file = parsed.get("registers_file")
    if isinstance(registers_file, str) and registers_file.strip():
        registers_data = _load_register_definitions(config_path, registers_file)
        for key in ("readings", "write_parameters"):
            if key in registers_data:
                parsed[key] = registers_data[key]

    return AppConfig.model_validate(parsed)
