from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from minimap.detector import MinimapResult


def normalize_angle_deg(angle: float) -> float:
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


@dataclass
class NavigationOutput:
    steer_error_deg: float | None
    steer_command_deg: float
    has_target: bool
    gps_active: bool


class MinimapNavigator:
    """Calcula erro angular para seguir a linha do GPS no minimapa rotativo."""

    def __init__(self, control_cfg: dict[str, Any]) -> None:
        self.kp = float(control_cfg.get("steer_kp", 0.9))
        self.kd = float(control_cfg.get("steer_kd", 0.3))
        self.error_smoothing = float(control_cfg.get("error_smoothing", 0.45))
        self._prev_error: float | None = None
        self._smooth_error: float | None = None

    def reset(self) -> None:
        self._prev_error = None
        self._smooth_error = None

    def compute_steer_error(self, result: MinimapResult) -> float | None:
        if result.gps_target_x is None or result.gps_target_y is None:
            return None

        dx = result.gps_target_x - result.player_x
        dy = result.gps_target_y - result.player_y
        if abs(dx) < 1e-3 and abs(dy) < 1e-3:
            return 0.0

        # No minimapa rotativo do GTA, "frente" aponta para cima (y negativo).
        return normalize_angle_deg(math.degrees(math.atan2(dx, -dy)))

    def update(self, result: MinimapResult) -> NavigationOutput:
        steer_error = self.compute_steer_error(result)
        has_target = steer_error is not None

        if steer_error is None:
            self._prev_error = None
            self._smooth_error = None
            return NavigationOutput(
                steer_error_deg=None,
                steer_command_deg=0.0,
                has_target=False,
                gps_active=result.active,
            )

        if self._smooth_error is None:
            self._smooth_error = steer_error
        else:
            alpha = self.error_smoothing
            self._smooth_error = alpha * steer_error + (1.0 - alpha) * self._smooth_error

        derivative = 0.0
        if self._prev_error is not None:
            derivative = self._smooth_error - self._prev_error
        self._prev_error = self._smooth_error

        command = self.kp * self._smooth_error + self.kd * derivative

        return NavigationOutput(
            steer_error_deg=self._smooth_error,
            steer_command_deg=command,
            has_target=has_target,
            gps_active=result.active,
        )
