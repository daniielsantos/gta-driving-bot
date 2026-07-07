from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from minimap.detector import MinimapDetector

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


def build_minimap_detector(config: dict[str, Any]) -> MinimapDetector:
    minimap = config["minimap"]
    center = minimap.get("player_center_ratio", {"x": 0.5, "y": 0.5})
    return MinimapDetector(
        gps_hsv_lower=list(minimap["gps_color_hsv"]["lower"]),
        gps_hsv_upper=list(minimap["gps_color_hsv"]["upper"]),
        road_gray_range=list(minimap["road_gray_range"]),
        player_center_ratio=(float(center["x"]), float(center["y"])),
        arrow_white_threshold=int(minimap.get("arrow_white_threshold", 200)),
        min_gps_pixels=int(minimap.get("min_gps_pixels", 40)),
        target_distance_px=float(minimap.get("target_distance_px", 55.0)),
    )
