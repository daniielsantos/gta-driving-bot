"""
Bot de direcao autonoma — Fase 1: seguir linha do GPS no minimapa.

Controles:
  F6 - liga/desliga o bot
  F7 - pausa navegacao (mantem captura)
  F9 - encerra o programa

Requisitos:
  - Windows (SendInput para W/A/S/D)
  - GTA/FiveM em borderless ou janela
  - Resolucao 2560x1440 (ou config.json recalibrado)
  - Rode calibrate_minimap.py antes
  - Jogo em foco ao usar F6
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

import cv2
import mss
import numpy as np
from pynput import keyboard

from bot_logger import bot_log, close_bot_log, init_bot_log
from config_loader import build_minimap_detector, get_minimap_roi, load_config
from control.vehicle import VehicleController
from debug.recorder import DebugRecorder
from keyboard_input import IS_WINDOWS, release_all_keys
from minimap.navigator import MinimapNavigator


class NavState(str, Enum):
    IDLE = "IDLE"
    NAVIGATING = "NAVIGATING"
    STOPPED = "STOPPED"


@dataclass
class RuntimeState:
    enabled: bool = False
    paused: bool = False
    running: bool = True
    nav_state: NavState = NavState.IDLE
    frames: int = 0
    gps_lost_streak: int = 0
    last_error: float | None = None
    last_action: str = "idle"


def resolve_hotkey(name: str) -> keyboard.Key:
    return keyboard.Key[name.lower()]


def main() -> None:
    if not IS_WINDOWS:
        bot_log("[aviso] SendInput indisponivel fora do Windows. Overlay funciona, mas sem controle.")

    log_path = init_bot_log()
    config = load_config()
    roi = get_minimap_roi(config)
    control_cfg = config["control"]

    detector = build_minimap_detector(config)
    navigator = MinimapNavigator(control_cfg)
    vehicle = VehicleController(control_cfg)

    debug_overlay = bool(control_cfg.get("debug_overlay", False))
    debug_record = bool(control_cfg.get("debug_record_frames", False))
    gps_lost_limit = int(control_cfg.get("gps_lost_frames", 15))
    target_dt = 1.0 / float(control_cfg.get("capture_fps", 30))

    recorder = DebugRecorder(enabled=debug_record)
    if debug_record:
        bot_log("[debug] Gravacao de frames habilitada -> captures/")

    state = RuntimeState()
    toggle_key = resolve_hotkey(config["hotkeys"]["toggle"])
    pause_key = resolve_hotkey(config["hotkeys"]["pause"])
    quit_key = resolve_hotkey(config["hotkeys"]["quit"])

    def stop_vehicle() -> None:
        vehicle.stop()
        state.nav_state = NavState.STOPPED

    def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
        if key == toggle_key:
            state.enabled = not state.enabled
            status = "LIGADO" if state.enabled else "DESLIGADO"
            bot_log(f"[bot] {status}")
            if state.enabled:
                navigator.reset()
                state.nav_state = NavState.IDLE
                state.gps_lost_streak = 0
            else:
                state.paused = False
                stop_vehicle()
                state.nav_state = NavState.IDLE
        elif key == pause_key and state.enabled:
            state.paused = not state.paused
            status = "PAUSADO" if state.paused else "RETOMADO"
            bot_log(f"[bot] Navegacao {status}")
            if state.paused:
                stop_vehicle()
        elif key == quit_key:
            state.running = False
            stop_vehicle()

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    fps_ema = 0.0
    last_logged_action = "idle"

    bot_log(__doc__)
    bot_log(f"[bot] Pressione F6 para ligar. Log em: {log_path}")

    with mss.mss() as sct:
        while state.running:
            loop_start = time.perf_counter()
            frame = np.array(sct.grab(roi))[:, :, :3]
            result = detector.detect(frame)
            nav = navigator.update(result)
            state.frames += 1
            state.last_error = nav.steer_error_deg

            if state.enabled and not state.paused:
                if result.active:
                    state.gps_lost_streak = 0
                    state.nav_state = NavState.NAVIGATING
                    state.last_action = vehicle.update(
                        nav.steer_command_deg,
                        throttle=True,
                        steer_error_deg=nav.steer_error_deg,
                    )
                else:
                    state.gps_lost_streak += 1
                    if state.gps_lost_streak >= gps_lost_limit:
                        if state.nav_state != NavState.STOPPED:
                            bot_log("[bot] GPS perdido — parando veiculo.")
                        stop_vehicle()
                    else:
                        state.last_action = vehicle.update(
                            nav.steer_command_deg,
                            throttle=state.nav_state == NavState.NAVIGATING,
                            steer_error_deg=nav.steer_error_deg,
                        )
            elif state.enabled and state.paused:
                state.last_action = "paused"
            else:
                state.nav_state = NavState.IDLE
                state.last_action = "idle"

            if state.last_action != last_logged_action:
                err = "-" if state.last_error is None else f"{state.last_error:.1f}"
                bot_log(
                    f"[acao] {state.last_action} | erro={err} | "
                    f"estado={state.nav_state.value} | gps_px={result.gps_pixels} | "
                    f"w={vehicle.throttle_active}"
                )
                last_logged_action = state.last_action

            if state.frames % 90 == 0 and state.enabled:
                err = "-" if state.last_error is None else f"{state.last_error:.1f}"
                bot_log(
                    f"[status] estado={state.nav_state.value} pausado={state.paused} "
                    f"acao={state.last_action} erro={err} gps_px={result.gps_pixels} "
                    f"rua={result.on_road}"
                )

            if debug_overlay and state.enabled:
                overlay = detector.debug_frame(frame, result)
                err_txt = "-" if state.last_error is None else f"{state.last_error:.1f}"
                lines = [
                    f"{state.nav_state.value} | acao={state.last_action}",
                    f"erro={err_txt} cmd={nav.steer_command_deg:.1f} | gps_px={result.gps_pixels}",
                    f"fps~{fps_ema:.0f} | pausado={state.paused} | W={vehicle.throttle_active}",
                ]
                for idx, line in enumerate(lines):
                    cv2.putText(
                        overlay,
                        line,
                        (8, overlay.shape[0] - 12 - (len(lines) - 1 - idx) * 16),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (0, 255, 0),
                        1,
                        cv2.LINE_AA,
                    )
                cv2.imshow("Drive Bot Debug", overlay)
                cv2.waitKey(1)

                if debug_record:
                    if recorder._session_dir is None:
                        session = recorder.start_session()
                        if session:
                            bot_log(f"[debug] Nova sessao: {session}")
                    recorder.save_frame(
                        overlay,
                        label=f"{state.last_action}_e{err_txt}",
                    )

            dt = max(time.perf_counter() - loop_start, 1e-6)
            fps_ema = fps_ema * 0.9 + (1.0 / dt) * 0.1
            elapsed = time.perf_counter() - loop_start
            sleep_time = target_dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    listener.stop()
    if IS_WINDOWS:
        release_all_keys()
    if debug_overlay:
        cv2.destroyAllWindows()
    bot_log("[bot] Encerrado.")
    close_bot_log()


if __name__ == "__main__":
    main()
