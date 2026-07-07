"""
Calibra a ROI do minimapa, cores do GPS e faixa de cinza da rua.

Controles:
  Setas / IJKL  - move a ROI
  W / X / A / D - tamanho da ROI
  [ / ]         - H minimo do GPS
  9 / 0         - H maximo do GPS
  ; / '         - S minimo do GPS
  , / .         - V minimo do GPS
  - / =         - cinza minimo da rua
  R / F         - cinza maximo da rua
  CLIQUE        - pega HSV do pixel (painel esquerdo)
  S             - salva config.json
  Q / ESC       - sair

Objetivo: painel esquerdo = overlay | meio = GPS | direita = rua.
  Linha verde = vetor para o ponto-alvo do GPS.
  Borda verde = jogador sobre pixel de rua; vermelha = fora da rua.
"""

from __future__ import annotations

import time

import cv2
import mss
import numpy as np

from config_loader import load_config, save_config
from minimap.detector import MinimapDetector


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def pick_hsv_from_pixel(frame_bgr: np.ndarray, x: int, y: int) -> tuple[list[int], list[int]]:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = [int(c) for c in hsv[y, x]]
    lower = [clamp(h - 12, 0, 179), clamp(s - 40, 20, 255), clamp(v - 60, 30, 255)]
    upper = [clamp(h + 12, 0, 179), 255, 255]
    return lower, upper


def build_detector_from_config(config: dict) -> MinimapDetector:
    minimap = config["minimap"]
    center = minimap.get("player_center_ratio", {"x": 0.5, "y": 0.5})
    return MinimapDetector(
        gps_hsv_lower=list(minimap["gps_color_hsv"]["lower"]),
        gps_hsv_upper=list(minimap["gps_color_hsv"]["upper"]),
        road_gray_range=list(minimap["road_gray_range"]),
        player_center_ratio=(float(center["x"]), float(center["y"])),
        arrow_white_threshold=int(minimap.get("arrow_white_threshold", 200)),
        min_gps_pixels=int(minimap.get("min_gps_pixels", 40)),
    )


def main() -> None:
    config = load_config()
    roi = dict(config["minimap"]["roi"])
    gps_lower = list(config["minimap"]["gps_color_hsv"]["lower"])
    gps_upper = list(config["minimap"]["gps_color_hsv"]["upper"])
    road_gray = list(config["minimap"]["road_gray_range"])
    last_frame: np.ndarray | None = None

    print(__doc__)

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        nonlocal gps_lower, gps_upper, last_frame
        if event != cv2.EVENT_LBUTTONDOWN or last_frame is None:
            return
        panel_width = last_frame.shape[1]
        if x >= panel_width:
            return
        local_x = int(x * last_frame.shape[1] / panel_width)
        local_y = int(y * last_frame.shape[0] / max(last_frame.shape[0], 1))
        local_x = clamp(local_x, 0, last_frame.shape[1] - 1)
        local_y = clamp(local_y, 0, last_frame.shape[0] - 1)
        gps_lower, gps_upper = pick_hsv_from_pixel(last_frame, local_x, local_y)
        print(f"[pick] GPS HSV lower={gps_lower} upper={gps_upper}")

    cv2.namedWindow("Minimap Calibration")
    cv2.setMouseCallback("Minimap Calibration", on_mouse)

    fps_ema = 0.0

    with mss.mss() as sct:
        while True:
            loop_start = time.perf_counter()
            frame = np.array(sct.grab(roi))[:, :, :3]
            last_frame = frame

            config["minimap"]["gps_color_hsv"]["lower"] = gps_lower
            config["minimap"]["gps_color_hsv"]["upper"] = gps_upper
            config["minimap"]["road_gray_range"] = road_gray

            detector = build_detector_from_config(config)
            result = detector.detect(frame)
            debug = detector.debug_frame(frame, result)

            gps_mask = detector.gps_mask(frame)
            road_mask = detector.road_mask(frame)
            gps_view = cv2.cvtColor(gps_mask, cv2.COLOR_GRAY2BGR)
            road_view = cv2.cvtColor(road_mask, cv2.COLOR_GRAY2BGR)

            status = "ATIVO" if result.active else "inativo"
            road_status = "rua" if result.on_road else "fora"
            angle_text = (
                f"{result.target_angle_deg:.1f}"
                if result.target_angle_deg is not None
                else "-"
            )
            gray_text = (
                str(result.road_gray_value)
                if result.road_gray_value is not None
                else "-"
            )

            lines = [
                f"{status} | gps_px={result.gps_pixels} road_px={result.road_pixels}",
                f"jogador=({result.player_x:.0f},{result.player_y:.0f}) alvo_ang={angle_text}",
                f"rua={road_status} cinza={gray_text} faixa={road_gray}",
                f"fps~{fps_ema:.0f} | clique na rota roxa para HSV",
                "S = salvar | verde = vetor GPS | borda = rua",
            ]
            for idx, line in enumerate(lines):
                cv2.putText(
                    debug,
                    line,
                    (8, 16 + idx * 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

            cv2.putText(
                gps_view,
                "GPS Mask",
                (8, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                road_view,
                "Road Mask",
                (8, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

            combined = np.hstack([debug, gps_view, road_view])
            max_width = 1500
            if combined.shape[1] > max_width:
                scale = max_width / combined.shape[1]
                combined = cv2.resize(
                    combined,
                    (int(combined.shape[1] * scale), max(int(combined.shape[0] * scale), 80)),
                    interpolation=cv2.INTER_AREA,
                )

            cv2.imshow("Minimap Calibration", combined)

            dt = max(time.perf_counter() - loop_start, 1e-6)
            fps_ema = fps_ema * 0.9 + (1.0 / dt) * 0.1

            key = cv2.waitKeyEx(1)
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                config["minimap"]["roi"] = roi
                config["minimap"]["gps_color_hsv"]["lower"] = gps_lower
                config["minimap"]["gps_color_hsv"]["upper"] = gps_upper
                config["minimap"]["road_gray_range"] = road_gray
                save_config(config)
                print("Config salva em config.json")

            step = 5
            if key in (2424832, 2, ord("j")):
                roi["left"] -= step
            elif key in (2555904, 3, ord("l")):
                roi["left"] += step
            elif key in (2490368, 0, ord("i")):
                roi["top"] -= step
            elif key in (2621440, 1, ord("k")):
                roi["top"] += step
            elif key == ord("a"):
                roi["width"] = max(120, roi["width"] - step)
            elif key == ord("d"):
                roi["width"] += step
            elif key == ord("w"):
                roi["height"] = max(120, roi["height"] - step)
            elif key == ord("x"):
                roi["height"] += step
            elif key == ord("["):
                gps_lower[0] = clamp(gps_lower[0] - 1, 0, 179)
            elif key == ord("]"):
                gps_lower[0] = clamp(gps_lower[0] + 1, 0, 179)
            elif key == ord("9"):
                gps_upper[0] = clamp(gps_upper[0] - 1, 0, 179)
            elif key == ord("0"):
                gps_upper[0] = clamp(gps_upper[0] + 1, 0, 179)
            elif key == ord(";"):
                gps_lower[1] = clamp(gps_lower[1] - 5, 0, 255)
            elif key == ord("'"):
                gps_lower[1] = clamp(gps_lower[1] + 5, 0, 255)
            elif key == ord(","):
                gps_lower[2] = clamp(gps_lower[2] - 5, 0, 255)
            elif key == ord("."):
                gps_lower[2] = clamp(gps_lower[2] + 5, 0, 255)
            elif key == ord("-"):
                road_gray[0] = clamp(road_gray[0] - 5, 0, 255)
            elif key == ord("="):
                road_gray[0] = clamp(road_gray[0] + 5, 0, 255)
            elif key in (ord("r"), ord("R")):
                road_gray[1] = clamp(road_gray[1] - 5, 0, 255)
            elif key in (ord("f"), ord("F")):
                road_gray[1] = clamp(road_gray[1] + 5, 0, 255)

            time.sleep(0.005)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
