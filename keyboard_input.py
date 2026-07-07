from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

VK_MAP = {
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "a": 0x41,
    "d": 0x44,
    "e": 0x45,
    "s": 0x53,
    "w": 0x57,
    "space": 0x20,
}

IS_WINDOWS = sys.platform == "win32"
_pressed_vk: set[int] = set()

if IS_WINDOWS:
    _user32 = ctypes.windll.user32
else:
    _user32 = None


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise RuntimeError("SendInput so funciona no Windows.")


def _vk_for(key: str) -> int:
    normalized = key.lower()
    if normalized not in VK_MAP:
        raise ValueError(f"Tecla nao suportada: {key}")
    return VK_MAP[normalized]


def _scan_for_vk(vk: int) -> int:
    _require_windows()
    return int(_user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)) & 0xFF


def _send_input_keyboard(ki: KEYBDINPUT) -> None:
    _require_windows()
    event = INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=ki))
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError(f"SendInput falhou (vk={ki.wVk}, scan={ki.wScan}, flags={ki.dwFlags})")


def _press_scan(scan: int) -> None:
    _send_input_keyboard(KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, None))


def _release_scan(scan: int) -> None:
    _send_input_keyboard(KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, None))


def press_key(key: str) -> None:
    """Pressiona tecla e mantem pressionada."""
    _require_windows()
    vk = _vk_for(key)
    if vk in _pressed_vk:
        return
    _press_scan(_scan_for_vk(vk))
    _pressed_vk.add(vk)


def release_key(key: str) -> None:
    """Solta tecla se estiver pressionada."""
    _require_windows()
    vk = _vk_for(key)
    if vk not in _pressed_vk:
        return
    _release_scan(_scan_for_vk(vk))
    _pressed_vk.discard(vk)


def release_all_keys() -> None:
    _require_windows()
    for vk in list(_pressed_vk):
        _release_scan(_scan_for_vk(vk))
    _pressed_vk.clear()


def hold_key(key: str, hold_ms: float = 50.0) -> None:
    """Segura tecla por hold_ms. Jogos DirectX preferem scancode."""
    _require_windows()
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)
    _press_scan(scan)
    time.sleep(max(hold_ms, 0) / 1000.0)
    _release_scan(scan)


def tap_key(key: str, hold_ms: float = 50.0) -> None:
    hold_key(key, hold_ms=hold_ms)


def is_key_pressed(key: str) -> bool:
    return _vk_for(key) in _pressed_vk


def debug_key_info(key: str) -> str:
    vk = _vk_for(key)
    if not IS_WINDOWS:
        return f"key={key!r} vk=0x{vk:02X} (nao-Windows)"
    scan = _scan_for_vk(vk)
    return f"key={key!r} vk=0x{vk:02X} scan=0x{scan:02X}"
