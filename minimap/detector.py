from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class MinimapResult:
    active: bool
    gps_pixels: int
    road_pixels: int
    player_x: float
    player_y: float
    gps_target_x: float | None
    gps_target_y: float | None
    target_angle_deg: float | None
    on_road: bool | None
    road_gray_value: int | None
    arrow_angle_deg: float | None


class MinimapDetector:
    """Detecta linha do GPS, posicao do jogador e pixels de rua no minimapa."""

    def __init__(
        self,
        gps_hsv_lower: list[int],
        gps_hsv_upper: list[int],
        road_gray_range: list[int],
        player_center_ratio: tuple[float, float] = (0.5, 0.5),
        arrow_white_threshold: int = 200,
        min_gps_pixels: int = 40,
        target_distance_px: float = 50.0,
        target_smoothing: float = 0.4,
    ) -> None:
        self.gps_hsv_lower = np.array(gps_hsv_lower, dtype=np.uint8)
        self.gps_hsv_upper = np.array(gps_hsv_upper, dtype=np.uint8)
        self.road_gray_min = int(road_gray_range[0])
        self.road_gray_max = int(road_gray_range[1])
        self.player_center_ratio = player_center_ratio
        self.arrow_white_threshold = arrow_white_threshold
        self.min_gps_pixels = min_gps_pixels
        self.target_distance_px = target_distance_px
        self.target_smoothing = target_smoothing
        self._smooth_target_x: float | None = None
        self._smooth_target_y: float | None = None

    def reset(self) -> None:
        self._smooth_target_x = None
        self._smooth_target_y = None

    def player_position(self, frame_shape: tuple[int, ...]) -> tuple[float, float]:
        height, width = frame_shape[:2]
        return (
            width * self.player_center_ratio[0],
            height * self.player_center_ratio[1],
        )

    def gps_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        return cv2.inRange(hsv, self.gps_hsv_lower, self.gps_hsv_upper)

    def road_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        return cv2.inRange(gray, self.road_gray_min, self.road_gray_max)

    def _find_gps_target(
        self,
        gps_mask: np.ndarray,
        player_x: float,
        player_y: float,
    ) -> tuple[float | None, float | None]:
        ys, xs = np.where(gps_mask > 0)
        if xs.size == 0:
            return None, None

        dx = xs.astype(np.float32) - player_x
        dy = ys.astype(np.float32) - player_y
        dist = np.sqrt(dx * dx + dy * dy)

        # No minimapa rotativo, "frente" = y menor que o jogador (para cima na tela).
        forward = dy < -4
        if np.any(forward):
            use_forward = forward
        else:
            use_forward = dist >= 8

        if not np.any(use_forward):
            idx = int(np.argmin(dist))
            return float(xs[idx]), float(ys[idx])

        xs_f = xs[use_forward]
        ys_f = ys[use_forward]
        dist_f = dist[use_forward]
        dx_f = dx[use_forward]
        dy_f = dy[use_forward]

        # Prefere ponto a ~target_distance a frente, nao o mais distante (evita apontar para lado errado).
        ideal = self.target_distance_px
        score = np.abs(dist_f - ideal) + np.maximum(0.0, dy_f) * 2.5
        best = int(np.argmin(score))
        tx = float(xs_f[best])
        ty = float(ys_f[best])

        if self._smooth_target_x is None:
            self._smooth_target_x = tx
            self._smooth_target_y = ty
        else:
            alpha = self.target_smoothing
            self._smooth_target_x = alpha * tx + (1.0 - alpha) * self._smooth_target_x
            self._smooth_target_y = alpha * ty + (1.0 - alpha) * self._smooth_target_y

        return self._smooth_target_x, self._smooth_target_y

    def _estimate_arrow_angle(self, frame_bgr: np.ndarray, player_x: float, player_y: float) -> float | None:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        _, white = cv2.threshold(gray, self.arrow_white_threshold, 255, cv2.THRESH_BINARY)
        height, width = white.shape
        radius = max(8, int(min(width, height) * 0.12))
        x0 = int(max(0, player_x - radius))
        x1 = int(min(width, player_x + radius))
        y0 = int(max(0, player_y - radius))
        y1 = int(min(height, player_y + radius))
        patch = white[y0:y1, x0:x1]
        if patch.size == 0:
            return None

        moments = cv2.moments(patch)
        if moments["m00"] < 20:
            return None

        cx = moments["m10"] / moments["m00"] + x0
        cy = moments["m01"] / moments["m00"] + y0
        angle = np.degrees(np.arctan2(cy - player_y, cx - player_x))
        return float(angle)

    def detect(self, frame_bgr: np.ndarray) -> MinimapResult:
        gps_mask = self.gps_mask(frame_bgr)
        road_mask = self.road_mask(frame_bgr)
        gps_pixels = int(cv2.countNonZero(gps_mask))
        road_pixels = int(cv2.countNonZero(road_mask))

        player_x, player_y = self.player_position(frame_bgr.shape)
        px = int(np.clip(player_x, 0, frame_bgr.shape[1] - 1))
        py = int(np.clip(player_y, 0, frame_bgr.shape[0] - 1))

        gray_value = int(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)[py, px])
        on_road = self.road_gray_min <= gray_value <= self.road_gray_max

        target_x, target_y = self._find_gps_target(gps_mask, player_x, player_y)
        target_angle = None
        if target_x is not None and target_y is not None:
            target_angle = float(np.degrees(np.arctan2(target_y - player_y, target_x - player_x)))

        arrow_angle = self._estimate_arrow_angle(frame_bgr, player_x, player_y)

        return MinimapResult(
            active=gps_pixels >= self.min_gps_pixels,
            gps_pixels=gps_pixels,
            road_pixels=road_pixels,
            player_x=player_x,
            player_y=player_y,
            gps_target_x=target_x,
            gps_target_y=target_y,
            target_angle_deg=target_angle,
            on_road=on_road,
            road_gray_value=gray_value,
            arrow_angle_deg=arrow_angle,
        )

    def debug_frame(self, frame_bgr: np.ndarray, result: MinimapResult) -> np.ndarray:
        debug = frame_bgr.copy()
        height, width = debug.shape[:2]

        cv2.circle(debug, (int(result.player_x), int(result.player_y)), 5, (0, 255, 255), -1)
        cv2.drawMarker(
            debug,
            (int(result.player_x), int(result.player_y)),
            (0, 255, 255),
            cv2.MARKER_CROSS,
            18,
            2,
        )

        if result.gps_target_x is not None and result.gps_target_y is not None:
            cv2.circle(
                debug,
                (int(result.gps_target_x), int(result.gps_target_y)),
                6,
                (255, 0, 255),
                2,
            )
            cv2.line(
                debug,
                (int(result.player_x), int(result.player_y)),
                (int(result.gps_target_x), int(result.gps_target_y)),
                (0, 255, 0),
                2,
            )

        if result.target_angle_deg is not None:
            length = 42
            rad = np.radians(result.target_angle_deg)
            end_x = int(result.player_x + np.cos(rad) * length)
            end_y = int(result.player_y + np.sin(rad) * length)
            cv2.arrowedLine(
                debug,
                (int(result.player_x), int(result.player_y)),
                (end_x, end_y),
                (0, 255, 0),
                2,
                tipLength=0.35,
            )

        road_color = (0, 255, 0) if result.on_road else (0, 0, 255)
        cv2.rectangle(debug, (0, 0), (width - 1, height - 1), road_color, 2)
        return debug
