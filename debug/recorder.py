from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


class DebugRecorder:
    """Grava frames de debug em captures/<timestamp>/."""

    def __init__(self, base_dir: Path | None = None, enabled: bool = False) -> None:
        self.enabled = enabled
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent / "captures"
        self._session_dir: Path | None = None
        self._frame_idx = 0

    def start_session(self) -> Path | None:
        if not self.enabled:
            return None
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = self.base_dir / stamp
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._frame_idx = 0
        return self._session_dir

    def save_frame(self, frame_bgr: np.ndarray, label: str = "frame") -> Path | None:
        if not self.enabled or self._session_dir is None:
            return None
        safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
        path = self._session_dir / f"{self._frame_idx:06d}_{safe_label}.png"
        cv2.imwrite(str(path), frame_bgr)
        self._frame_idx += 1
        return path

    def save_json_sidecar(self, payload: dict[str, Any], stem: str) -> Path | None:
        if not self.enabled or self._session_dir is None:
            return None
        import json

        path = self._session_dir / f"{stem}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        return path
