from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    config_path = path or CONFIG_PATH
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


def get_minimap_roi(config: dict[str, Any]) -> dict[str, int]:
    return dict(config["minimap"]["roi"])
