from __future__ import annotations

from pathlib import Path

import yaml

from src.models import AppConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle) or {}

    if not isinstance(parsed, dict):
        raise ValueError("Configuration file must contain a top-level mapping")

    return AppConfig.model_validate(parsed)
