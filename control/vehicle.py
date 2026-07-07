from __future__ import annotations

import time
from typing import Any

from keyboard_input import IS_WINDOWS, is_key_pressed, press_key, release_all_keys, release_key, tap_key


class VehicleController:
    """Controla W/A/S/D: W sustentado em reta, solta em curva, volante em pulsos."""

    def __init__(self, control_cfg: dict[str, Any]) -> None:
        self.deadband_deg = float(control_cfg.get("steer_deadband_deg", 3))
        self.max_pulse_ms = float(control_cfg.get("max_steer_pulse_ms", 60))
        self.min_pulse_ms = float(control_cfg.get("min_steer_pulse_ms", 22))
        self.gain_ms_per_deg = float(control_cfg.get("steer_gain_ms_per_deg", 1.1))
        self.steer_interval_ms = float(control_cfg.get("steer_interval_ms", 60))

        self.throttle_mode = str(control_cfg.get("throttle_mode", "smart"))
        self.throttle_pulse_ms = float(control_cfg.get("throttle_pulse_ms", 120))
        self.throttle_interval_ms = float(control_cfg.get("throttle_interval_ms", 200))
        self.throttle_cutoff_deg = float(control_cfg.get("throttle_cutoff_deg", 18))
        self.cruise_throttle = bool(control_cfg.get("cruise_throttle", True))

        self._last_steer_at = 0.0
        self._last_throttle_at = 0.0
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

    def _release_throttle(self) -> None:
        if IS_WINDOWS:
            release_key("w")

    def _update_throttle(self, steer_error_deg: float | None, *, enabled: bool) -> str:
        if not IS_WINDOWS or not enabled or not self.cruise_throttle:
            self._release_throttle()
            return "throttle-off"

        abs_error = abs(steer_error_deg or 0.0)
        if abs_error >= self.throttle_cutoff_deg:
            self._release_throttle()
            return "coast-turn"

        if self.throttle_mode == "pulse":
            now = time.perf_counter()
            if (now - self._last_throttle_at) * 1000.0 < self.throttle_interval_ms:
                return "throttle-wait"
            tap_key("w", hold_ms=self.throttle_pulse_ms)
            self._last_throttle_at = now
            return "throttle-pulse"

        # smart / hold: W sustentado enquanto a reta permite
        press_key("w")
        return "throttle-hold"

    def steer(self, error_deg: float) -> str:
        if not IS_WINDOWS:
            self._last_action = "no-windows"
            return self._last_action

        now = time.perf_counter()
        if abs(error_deg) < self.deadband_deg:
            return "center"

        if (now - self._last_steer_at) * 1000.0 < self.steer_interval_ms:
            return "steer-wait"

        key = "d" if error_deg > 0 else "a"
        pulse_ms = min(
            self.max_pulse_ms,
            max(self.min_pulse_ms, abs(error_deg) * self.gain_ms_per_deg),
        )
        tap_key(key, hold_ms=pulse_ms)
        self._last_steer_at = now
        return f"steer-{key}"

    def update(
        self,
        steer_command_deg: float | None,
        *,
        throttle: bool,
        steer_error_deg: float | None = None,
    ) -> str:
        throttle_action = self._update_throttle(steer_error_deg, enabled=throttle)

        if steer_command_deg is None:
            self._last_action = throttle_action
            return self._last_action

        steer_action = self.steer(steer_command_deg)
        self._last_action = f"{throttle_action}+{steer_action}"
        return self._last_action
