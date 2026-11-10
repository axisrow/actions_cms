"""Collectors: raw material for articles, written to dated JSON files in the inbox."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..errors import ConfigError


def load_config(path: Path) -> object:
    if not path.is_file():
        raise ConfigError(f"{path}: collector config not found")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {' '.join(str(e).split())}") from e


def load_items(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_items(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
