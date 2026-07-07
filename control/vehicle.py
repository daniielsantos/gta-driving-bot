from __future__ import annotations

import time
from typing import Any

from keyboard_input import IS_WINDOWS, is_key_pressed, press_key, release_all_keys, release_key, tap_key


class VehicleController:
    """Controla W/A/S/D via SendInput com aceleracao sustentada e volante em pulsos."""

    def __init__(self, control_cfg: dict[str, Any]) -> None:
        self.deadband_deg = float(control_cfg.get("steer_deadband_deg", 3))
        self.max_pulse_ms = float(control_cfg.get("max_steer_pulse_ms", 80))
        self.min_pulse_ms = float(control_cfg.get("min_steer_pulse_ms", 25))
        self.gain_ms_per_deg = float(control_cfg.get("steer_gain_ms_per_deg", 1.5))
        self.steer_interval_ms = float(control_cfg.get("steer_interval_ms", 50))
        self.cruise_throttle = bool(control_cfg.get("cruise_throttle", True))
        self._last_steer_at = 0.0
        self._last_action = "idle"

    @property
    def last_action(self) -> str:
        return self._last_action

    @property
    def throttle_active(self) -> bool:
        return IS_WINDOWS and is_key_pressed("w")

    def stop(self) -> str:
        if IS_WINDOWS:
            release_all_keys()
        self._last_action = "idle"
        return self._last_action

    def set_throttle(self, active: bool) -> None:
        if not IS_WINDOWS:
            return
        if active and self.cruise_throttle:
            press_key("w")
        else:
            release_key("w")

    def steer(self, error_deg: float) -> str:
        if not IS_WINDOWS:
            self._last_action = "no-windows"
            return self._last_action

        now = time.perf_counter()
        if abs(error_deg) < self.deadband_deg:
            self._last_action = "center"
            return self._last_action

        if (now - self._last_steer_at) * 1000.0 < self.steer_interval_ms:
            return self._last_action

        key = "d" if error_deg > 0 else "a"
        pulse_ms = min(
            self.max_pulse_ms,
            max(self.min_pulse_ms, abs(error_deg) * self.gain_ms_per_deg),
        )
        tap_key(key, hold_ms=pulse_ms)
        self._last_steer_at = now
        self._last_action = f"steer-{key}"
        return self._last_action

    def update(self, error_deg: float | None, *, throttle: bool) -> str:
        self.set_throttle(throttle)
        if error_deg is None:
            self._last_action = "no-target"
            return self._last_action
        return self.steer(error_deg)
