"""
AnySupport Web - Windows Remote Control Agent (RemoteAgent.exe)
System Tray + UAC Administrator + Loopback WebSocket (127.0.0.1:8765) + Win32 SendInput
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
from ctypes import wintypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Any
import webbrowser

from PIL import Image, ImageDraw, ImageTk
import pystray
from pystray import MenuItem as Item
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

HOST = "127.0.0.1"
PORT = 8765
AGENT_VERSION = "2.2.0"
WINDOW_TITLE = "AnySupport RemoteAgent"
WEB_URL = os.environ.get("ANYSUPPORT_WEB_URL", "https://remote-support-desk-xi.vercel.app")
MUTEX_NAME = "Local\\AnySupportWebRemoteAgentMutex"

# Allowed browser origins by default (localhost, 127.0.0.1, Vercel, GitHub Pages, local file)
TRUSTED_ORIGIN_PATTERNS = (
    re.compile(r"^https?://localhost(:\d+)?$", re.IGNORECASE),
    re.compile(r"^https?://127\.0\.0\.1(:\d+)?$", re.IGNORECASE),
    re.compile(r"^https://[a-z0-9-]+(\.[a-z0-9-]+)*\.vercel\.app$", re.IGNORECASE),
    re.compile(r"^https://[a-z0-9-]+\.github\.io$", re.IGNORECASE),
)

# Win32 Constants
SM_CXSCREEN = 0
SM_CYSCREEN = 1

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MAPVK_VK_TO_VSC = 0
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

MB_YESNO = 0x00000004
MB_OK = 0x00000000
MB_ICONQUESTION = 0x00000020
MB_ICONINFORMATION = 0x00000040
MB_TOPMOST = 0x00040000
IDYES = 6

ERROR_ALREADY_EXISTS = 183

# Win32 API bindings
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
user32.MessageBoxW.restype = ctypes.c_int
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL

kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE

shell32.IsUserAnAdmin.argtypes = ()
shell32.IsUserAnAdmin.restype = wintypes.BOOL
shell32.ShellExecuteW.argtypes = (
    wintypes.HWND,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_int,
)
shell32.ShellExecuteW.restype = wintypes.HINSTANCE


# Virtual-Key mapping by DOM KeyboardEvent.code (physical key)
CODE_TO_VK: dict[str, int] = {
    **{f"Key{chr(c)}": c for c in range(ord("A"), ord("Z") + 1)},
    **{f"Digit{d}": 0x30 + d for d in range(10)},
    **{f"Numpad{d}": 0x60 + d for d in range(10)},
    **{f"F{n}": 0x6F + n for n in range(1, 13)},
    "Backspace": 0x08,
    "Tab": 0x09,
    "Enter": 0x0D,
    "NumpadEnter": 0x0D,
    "ShiftLeft": 0xA0,
    "ShiftRight": 0xA1,
    "ControlLeft": 0xA2,
    "ControlRight": 0xA3,
    "AltLeft": 0xA4,
    "AltRight": 0xA5,
    "Pause": 0x13,
    "CapsLock": 0x14,
    "Escape": 0x1B,
    "Space": 0x20,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "End": 0x23,
    "Home": 0x24,
    "ArrowLeft": 0x25,
    "ArrowUp": 0x26,
    "ArrowRight": 0x27,
    "ArrowDown": 0x28,
    "PrintScreen": 0x2C,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "MetaLeft": 0x5B,
    "MetaRight": 0x5C,
    "ContextMenu": 0x5D,
    "NumpadMultiply": 0x6A,
    "NumpadAdd": 0x6B,
    "NumpadSubtract": 0x6D,
    "NumpadDecimal": 0x6E,
    "NumpadDivide": 0x6F,
    "NumLock": 0x90,
    "ScrollLock": 0x91,
    "Semicolon": 0xBA,
    "Equal": 0xBB,
    "Comma": 0xBC,
    "Minus": 0xBD,
    "Period": 0xBE,
    "Slash": 0xBF,
    "Backquote": 0xC0,
    "BracketLeft": 0xDB,
    "Backslash": 0xDC,
    "BracketRight": 0xDD,
    "Quote": 0xDE,
}

# Fallback mapping by DOM KeyboardEvent.key or shortcut name
KEY_TO_VK: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "control": 0x11,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
    " ": 0x20,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "arrowleft": 0x25,
    "left": 0x25,
    "arrowup": 0x26,
    "up": 0x26,
    "arrowright": 0x27,
    "right": 0x27,
    "arrowdown": 0x28,
    "down": 0x28,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "meta": 0x5B,
    "win": 0x5B,
    "winleft": 0x5B,
    "winright": 0x5C,
    "contextmenu": 0x5D,
    "numlock": 0x90,
    "scrolllock": 0x91,
    **{f"f{n}": 0x6F + n for n in range(1, 13)},
    **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
}

EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90,
    0xA3, 0xA5,
}
EXTENDED_CODES = {"NumpadEnter", "NumpadDivide", "ControlRight", "AltRight", "MetaLeft", "MetaRight"}


def enable_dpi_awareness() -> None:
    """Configure Per-Monitor V2 DPI awareness so screen coordinates map 1:1."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def is_admin() -> bool:
    """Return True if the current process runs with Administrator privileges."""
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin_elevation() -> None:
    """Prompt UAC elevation when launched directly without Administrator rights."""
    if is_admin() or "--no-elevate" in sys.argv:
        return

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    else:
        executable = sys.executable
        script_path = os.path.abspath(__file__)
        extra = " ".join(f'"{arg}"' for arg in sys.argv[1:])
        params = f'"{script_path}" {extra}'.strip()

    ret = shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    if int(ret) > 32:
        sys.exit(0)


def get_desktop_dir() -> str:
    """Resolve the user's real Windows Desktop directory (including OneDrive redirection)."""
    buf = ctypes.create_unicode_buffer(260)
    if shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def install_desktop_shortcut() -> tuple[bool, str]:
    """Install RemoteAgent.exe into %LOCALAPPDATA%\\AnySupport and create a Desktop shortcut."""
    try:
        if getattr(sys, "frozen", False):
            local_app = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            install_dir = os.path.join(local_app, "AnySupport")
            os.makedirs(install_dir, exist_ok=True)
            target_exe = os.path.join(install_dir, "RemoteAgent.exe")
            current_exe = os.path.abspath(sys.executable)
            if current_exe.lower() != os.path.abspath(target_exe).lower():
                shutil.copy2(current_exe, target_exe)
        else:
            candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "RemoteAgent.exe"))
            if not os.path.isfile(candidate):
                return False, "ไม่พบไฟล์ RemoteAgent.exe สำหรับสร้างทางลัด"
            target_exe = candidate

        desktop_dir = get_desktop_dir()
        if not os.path.isdir(desktop_dir):
            return False, "ไม่พบโฟลเดอร์ Desktop"

        shortcut_path = os.path.join(desktop_dir, "AnySupport ช่วยเหลือระยะไกล.lnk")
        ps_script = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$sc = $ws.CreateShortcut('{shortcut_path.replace(chr(39), chr(39)*2)}'); "
            f"$sc.TargetPath = '{target_exe.replace(chr(39), chr(39)*2)}'; "
            f"$sc.WorkingDirectory = '{os.path.dirname(target_exe).replace(chr(39), chr(39)*2)}'; "
            f"$sc.IconLocation = '{target_exe.replace(chr(39), chr(39)*2)},0'; "
            "$sc.Description = 'AnySupport Web - ระบบช่วยเหลือและซ่อมคอมพิวเตอร์ระยะไกล'; "
            "$sc.Save()"
        )
        encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            timeout=10,
        )
        if res.returncode == 0 and os.path.isfile(shortcut_path):
            return True, shortcut_path
        return False, "สร้างทางลัดไม่สำเร็จ"
    except Exception as exc:
        return False, str(exc)


def open_web_portal() -> None:
    """Open the AnySupport Web portal in the default browser."""
    try:
        webbrowser.open(WEB_URL, new=2)
    except Exception:
        pass


def focus_existing_window() -> None:
    """Restore and focus an existing RemoteAgent control window if found."""
    try:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def acquire_single_instance() -> wintypes.HANDLE | None:
    """Ensure only one instance runs; if already open, focus window and open web."""
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        focus_existing_window()
        open_web_portal()
        return None
    return handle


def is_origin_trusted(origin: str | None) -> bool:
    """Check whether the browser Origin header belongs to a trusted host."""
    if not origin or origin == "null":
        return True
    if origin.lower().startswith("file://"):
        return True
    extra = os.environ.get("AGENT_ALLOWED_ORIGINS", "")
    if extra:
        allowed_set = {item.strip().lower() for item in extra.split(",") if item.strip()}
        if origin.lower() in allowed_set:
            return True
    return any(pattern.match(origin) for pattern in TRUSTED_ORIGIN_PATTERNS)


class Win32InputController:
    """Thread-safe Win32 SendInput mouse, keyboard, clipboard, and command controller."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pressed_buttons: set[str] = set()
        self._pressed_vks: set[int] = set()

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        width = max(1, int(user32.GetSystemMetrics(SM_CXSCREEN)))
        height = max(1, int(user32.GetSystemMetrics(SM_CYSCREEN)))
        return width, height

    @staticmethod
    def _norm_to_abs(x: float, y: float) -> tuple[int, int]:
        nx = max(0.0, min(1.0, float(x)))
        ny = max(0.0, min(1.0, float(y)))
        return int(round(nx * 65535)), int(round(ny * 65535))

    @staticmethod
    def _send_inputs(inputs: list[INPUT]) -> None:
        if not inputs:
            return
        arr = (INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

    @staticmethod
    def _make_mouse(dx: int, dy: int, flags: int, mouse_data: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi = MOUSEINPUT(
            dx=dx,
            dy=dy,
            mouseData=ctypes.c_uint32(mouse_data).value,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        )
        return inp

    @staticmethod
    def _make_key(vk: int, is_up: bool = False, extended: bool = False) -> INPUT:
        scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        flags = KEYEVENTF_KEYUP if is_up else 0
        if extended or vk in EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        return inp

    @staticmethod
    def _make_unicode_pair(ch: str) -> list[INPUT]:
        encoded = ch.encode("utf-16-le")
        items: list[INPUT] = []
        for idx in range(0, len(encoded), 2):
            code_unit = int.from_bytes(encoded[idx : idx + 2], "little")
            down = INPUT(type=INPUT_KEYBOARD)
            down.ki = KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
            up = INPUT(type=INPUT_KEYBOARD)
            up.ki = KEYBDINPUT(
                wVk=0,
                wScan=code_unit,
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            )
            items.extend((down, up))
        return items

    def move_mouse(self, x: float, y: float) -> None:
        ax, ay = self._norm_to_abs(x, y)
        with self._lock:
            self._send_inputs([self._make_mouse(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)])

    def mouse_button(self, x: float, y: float, button: str, down: bool) -> None:
        ax, ay = self._norm_to_abs(x, y)
        btn = button if button in ("left", "middle", "right") else "left"
        flag_map = {
            ("left", True): MOUSEEVENTF_LEFTDOWN,
            ("left", False): MOUSEEVENTF_LEFTUP,
            ("middle", True): MOUSEEVENTF_MIDDLEDOWN,
            ("middle", False): MOUSEEVENTF_MIDDLEUP,
            ("right", True): MOUSEEVENTF_RIGHTDOWN,
            ("right", False): MOUSEEVENTF_RIGHTUP,
        }
        with self._lock:
            if down:
                self._pressed_buttons.add(btn)
            else:
                self._pressed_buttons.discard(btn)
            self._send_inputs([
                self._make_mouse(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | flag_map[(btn, down)])
            ])

    def double_click(self, x: float, y: float) -> None:
        ax, ay = self._norm_to_abs(x, y)
        with self._lock:
            self._send_inputs([
                self._make_mouse(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN),
                self._make_mouse(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP),
                self._make_mouse(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN),
                self._make_mouse(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP),
            ])

    def scroll(self, dy: int) -> None:
        delta = max(-1200, min(1200, int(dy)))
        with self._lock:
            self._send_inputs([self._make_mouse(0, 0, MOUSEEVENTF_WHEEL, mouse_data=delta)])

    @staticmethod
    def _resolve_vk(key: str, code: str) -> tuple[int | None, bool]:
        if code and code in CODE_TO_VK:
            return CODE_TO_VK[code], code in EXTENDED_CODES
        lowered = (key or "").lower()
        if lowered in KEY_TO_VK:
            return KEY_TO_VK[lowered], False
        if len(key or "") == 1 and ord(key) < 128:
            # Handle shifted ASCII punctuation on US layout via VkKeyScanW
            res = user32.VkKeyScanW(ord(key))
            if res != -1:
                return res & 0xFF, False
        return None, False

    def handle_key(
        self,
        is_down: bool,
        key: str = "",
        code: str = "",
        ctrl: bool = False,
        alt: bool = False,
        shift: bool = False,
        meta: bool = False,
    ) -> None:
        with self._lock:
            has_shortcut_mod = ctrl or alt or meta
            # Direct Unicode injection for Thai / non-ASCII characters when no shortcut modifier is held
            if is_down and not has_shortcut_mod and len(key) == 1 and ord(key) > 127:
                self._send_inputs(self._make_unicode_pair(key))
                return

            vk, is_ext = self._resolve_vk(key, code)
            if vk is None:
                return

            inputs: list[INPUT] = []
            if is_down:
                # Ensure modifier state matches browser flags when sending combos
                mod_families = (
                    (0x11, ctrl, (0x11, 0xA2, 0xA3)),
                    (0x12, alt, (0x12, 0xA4, 0xA5)),
                    (0x10, shift, (0x10, 0xA0, 0xA1)),
                    (0x5B, meta, (0x5B, 0x5C)),
                )
                injected_mods: list[int] = []
                if vk not in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                    for mod_vk, active, family in mod_families:
                        already_held = any(v in self._pressed_vks for v in family)
                        if active and not already_held:
                            inputs.append(self._make_key(mod_vk, is_up=False))
                            injected_mods.append(mod_vk)
                self._pressed_vks.add(vk)
                inputs.append(self._make_key(vk, is_up=False, extended=is_ext))
                for mod_vk in reversed(injected_mods):
                    inputs.append(self._make_key(mod_vk, is_up=True))
            else:
                self._pressed_vks.discard(vk)
                inputs.append(self._make_key(vk, is_up=True, extended=is_ext))

            self._send_inputs(inputs)

    def send_hotkey(self, keys: list[str]) -> None:
        resolved: list[tuple[int, bool]] = []
        for raw in keys:
            vk, is_ext = self._resolve_vk(raw, raw)
            if vk is not None:
                resolved.append((vk, is_ext))
        if not resolved:
            return
        with self._lock:
            inputs = [self._make_key(vk, is_up=False, extended=ext) for vk, ext in resolved]
            self._send_inputs(inputs)
        time.sleep(0.025)
        with self._lock:
            inputs = [self._make_key(vk, is_up=True, extended=ext) for vk, ext in reversed(resolved)]
            self._send_inputs(inputs)

    def paste_text(self, text: str) -> bool:
        if not text:
            return False
        data = (text + "\0").encode("utf-16-le")
        opened = False
        for _ in range(10):
            if user32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.015)
        if not opened:
            return False

        try:
            user32.EmptyClipboard()
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_mem:
                return False
            ptr = kernel32.GlobalLock(h_mem)
            if not ptr:
                kernel32.GlobalFree(h_mem)
                return False
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h_mem)
            if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                kernel32.GlobalFree(h_mem)
                return False
        finally:
            user32.CloseClipboard()

        time.sleep(0.04)
        self.send_hotkey(["ctrl", "v"])
        return True

    @staticmethod
    def run_sys_command(cmd_name: str) -> bool:
        user_home = os.path.expanduser("~")
        temp_dir = os.environ.get("TEMP") or os.path.join(user_home, "AppData", "Local", "Temp")
        allowlist: dict[str, tuple[str, str | None, str | None]] = {
            "taskmgr": ("taskmgr.exe", None, None),
            "ncpa.cpl": ("control.exe", "ncpa.cpl", None),
            "devmgmt.msc": ("mmc.exe", "devmgmt.msc", None),
            "appwiz.cpl": ("control.exe", "appwiz.cpl", None),
            "temp": ("explorer.exe", temp_dir, None),
            "cmd": ("cmd.exe", None, user_home),
        }
        entry = allowlist.get(cmd_name)
        if not entry:
            return False
        exe, params, workdir = entry
        ret = shell32.ShellExecuteW(None, "open", exe, params, workdir, 1)
        return int(ret) > 32

    def release_all_inputs(self) -> None:
        """Safety cleanup to release any held mouse buttons or keys."""
        with self._lock:
            inputs: list[INPUT] = []
            up_flags = {
                "left": MOUSEEVENTF_LEFTUP,
                "middle": MOUSEEVENTF_MIDDLEUP,
                "right": MOUSEEVENTF_RIGHTUP,
            }
            for btn in list(self._pressed_buttons):
                inputs.append(self._make_mouse(0, 0, up_flags[btn]))
            self._pressed_buttons.clear()

            for vk in list(self._pressed_vks):
                inputs.append(self._make_key(vk, is_up=True))
            self._pressed_vks.clear()
            self._send_inputs(inputs)


def create_tray_icon_image(state: str = "waiting") -> Image.Image:
    """Render a crisp Navy & Gold tray icon with status dot (waiting / connected / paused)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Navy rounded square background (#1E3A8A)
    draw.rounded_rectangle([2, 2, 61, 61], radius=14, fill=(30, 58, 138, 255), outline=(251, 191, 36, 255), width=3)

    # Stylised crosshair / cursor motif in Gold (#FBBF24)
    draw.ellipse([16, 16, 48, 48], outline=(251, 191, 36, 255), width=4)
    draw.ellipse([27, 27, 37, 37], fill=(255, 255, 255, 255))

    # Bottom-right live status dot
    dot_colors = {
        "waiting": (251, 191, 36, 255),    # Amber
        "connected": (16, 185, 129, 255),  # Emerald
        "paused": (239, 68, 68, 255),      # Rose
    }
    dot_color = dot_colors.get(state, dot_colors["waiting"])
    draw.ellipse([42, 42, 60, 60], fill=dot_color, outline=(255, 255, 255, 255), width=2)
    return img


class RemoteAgentApp:
    """Coordinates the asyncio WebSocket server, mini control GUI, and System Tray UI."""

    def __init__(self) -> None:
        self.controller = Win32InputController()
        self.paused = False
        self.clients: set[ServerConnection] = set()
        self.session_approved_origins: set[str] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event: asyncio.Event | None = None
        self.tray_icon: pystray.Icon | None = None
        self.root: tk.Tk | None = None
        self._tk_icon: ImageTk.PhotoImage | None = None
        self._status_label: tk.Label | None = None
        self._pause_btn: tk.Button | None = None
        self._dot_label: tk.Label | None = None
        self._closing = False
        self._icon_cache = {
            "waiting": create_tray_icon_image("waiting"),
            "connected": create_tray_icon_image("connected"),
            "paused": create_tray_icon_image("paused"),
        }

    def _current_state(self) -> str:
        if self.paused:
            return "paused"
        if self.clients:
            return "connected"
        return "waiting"

    def _status_text(self) -> str:
        state = self._current_state()
        admin_label = "Admin" if is_admin() else "Standard"
        if state == "paused":
            return f"หยุดควบคุมชั่วคราว ({admin_label})"
        if state == "connected":
            return f"เชื่อมต่อหน้าเว็บแล้ว ({len(self.clients)} แท็บ, {admin_label})"
        return f"พร้อมเชื่อมต่อ ws://{HOST}:{PORT} ({admin_label})"

    def refresh_tray(self) -> None:
        if self.tray_icon:
            state = self._current_state()
            try:
                self.tray_icon.icon = self._icon_cache[state]
                self.tray_icon.title = f"AnySupport RemoteAgent - {self._status_text()}"
                self.tray_icon.update_menu()
            except Exception:
                pass
        self._schedule_ui_refresh()

    def _schedule_ui_refresh(self) -> None:
        if self.root and not self._closing:
            try:
                self.root.after(0, self._update_ui_widgets)
            except Exception:
                pass

    def _update_ui_widgets(self) -> None:
        if not self.root or self._closing:
            return
        state = self._current_state()
        color_map = {
            "waiting": "#D97706",    # Amber
            "connected": "#059669",  # Emerald
            "paused": "#DC2626",     # Rose
        }
        if self._dot_label:
            self._dot_label.config(fg=color_map.get(state, "#D97706"))
        if self._status_label:
            self._status_label.config(text=self._status_text())
        if self._pause_btn:
            if self.paused:
                self._pause_btn.config(
                    text="▶ เปิดรับควบคุมต่อ",
                    bg="#059669",
                    activebackground="#047857",
                )
            else:
                self._pause_btn.config(
                    text="⏸ หยุดควบคุมชั่วคราว",
                    bg="#D97706",
                    activebackground="#B45309",
                )

    async def _send_status(self, ws: ServerConnection) -> None:
        width, height = self.controller.get_screen_size()
        payload = {
            "type": "agent_status",
            "version": AGENT_VERSION,
            "isAdmin": is_admin(),
            "paused": self.paused,
            "screenWidth": width,
            "screenHeight": height,
        }
        try:
            await ws.send(json.dumps(payload))
        except Exception:
            pass

    def _prompt_origin_approval(self, origin: str) -> bool:
        result = user32.MessageBoxW(
            None,
            (
                f"เว็บไซต์ต่อไปนี้ต้องการเชื่อมต่อควบคุมเมาส์และคีย์บอร์ด:\n\n"
                f"{origin}\n\n"
                f"คุณต้องการอนุญาตให้เว็บไซต์นี้ควบคุมเครื่องหรือไม่?"
            ),
            "AnySupport RemoteAgent - ยืนยันความปลอดภัย",
            MB_YESNO | MB_ICONQUESTION | MB_TOPMOST,
        )
        return result == IDYES

    async def _ensure_origin_authorized(self, ws: ServerConnection, origin: str | None) -> bool:
        if is_origin_trusted(origin):
            return True
        assert origin is not None
        if origin in self.session_approved_origins:
            return True
        approved = await asyncio.to_thread(self._prompt_origin_approval, origin)
        if approved:
            self.session_approved_origins.add(origin)
            return True
        await ws.close(code=4003, reason="Origin rejected by user")
        return False

    async def handle_client(self, ws: ServerConnection) -> None:
        origin = ws.request.headers.get("Origin") if ws.request else None

        self.clients.add(ws)
        self.refresh_tray()
        await self._send_status(ws)

        try:
            async for raw in ws:
                if not isinstance(raw, str):
                    continue
                try:
                    msg: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue

                msg_type = msg.get("type")
                if msg_type == "ping":
                    await self._send_status(ws)
                    continue

                if msg_type == "release_all":
                    self.controller.release_all_inputs()
                    continue

                if self.paused:
                    continue

                # Verify browser Origin before accepting any system/input control event
                if not await self._ensure_origin_authorized(ws, origin):
                    break

                await self._dispatch_control_event(msg_type, msg)
        except ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)
            if not self.clients:
                self.controller.release_all_inputs()
            self.refresh_tray()

    async def _dispatch_control_event(self, msg_type: str | None, msg: dict[str, Any]) -> None:
        try:
            if msg_type == "mousemove":
                self.controller.move_mouse(float(msg.get("x", 0.5)), float(msg.get("y", 0.5)))
            elif msg_type == "mousedown":
                self.controller.mouse_button(
                    float(msg.get("x", 0.5)),
                    float(msg.get("y", 0.5)),
                    str(msg.get("button", "left")),
                    down=True,
                )
            elif msg_type == "mouseup":
                self.controller.mouse_button(
                    float(msg.get("x", 0.5)),
                    float(msg.get("y", 0.5)),
                    str(msg.get("button", "left")),
                    down=False,
                )
            elif msg_type == "dblclick":
                self.controller.double_click(float(msg.get("x", 0.5)), float(msg.get("y", 0.5)))
            elif msg_type == "scroll":
                self.controller.scroll(int(msg.get("dy", 0)))
            elif msg_type in ("keydown", "keyup"):
                self.controller.handle_key(
                    is_down=(msg_type == "keydown"),
                    key=str(msg.get("key", "")),
                    code=str(msg.get("code", "")),
                    ctrl=bool(msg.get("ctrl", False)),
                    alt=bool(msg.get("alt", False)),
                    shift=bool(msg.get("shift", False)),
                    meta=bool(msg.get("meta", False)),
                )
            elif msg_type == "hotkey":
                keys = msg.get("keys")
                if isinstance(keys, list):
                    self.controller.send_hotkey([str(k) for k in keys])
            elif msg_type == "paste_text":
                self.controller.paste_text(str(msg.get("text", "")))
            elif msg_type == "sys_cmd":
                self.controller.run_sys_command(str(msg.get("cmd", "")))
        except (TypeError, ValueError):
            return

    async def _ws_server_main(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.stop_event = asyncio.Event()
        async with serve(self.handle_client, HOST, PORT, ping_interval=20, ping_timeout=20):
            await self.stop_event.wait()

    def _run_ws_thread(self) -> None:
        try:
            asyncio.run(self._ws_server_main())
        except OSError:
            user32.MessageBoxW(
                None,
                f"ไม่สามารถเปิดพอร์ต {HOST}:{PORT} ได้\nอาจมีโปรแกรมอื่นใช้งานพอร์ตนี้อยู่",
                "AnySupport RemoteAgent - Error",
                MB_OK | MB_TOPMOST,
            )
            if self.tray_icon:
                self.tray_icon.stop()

    async def _broadcast_status(self) -> None:
        for ws in list(self.clients):
            await self._send_status(ws)

    async def _close_all_clients(self) -> None:
        for ws in list(self.clients):
            try:
                await ws.close(code=4001, reason="Disconnected from system tray")
            except Exception:
                pass

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self.controller.release_all_inputs()
        if self.loop and self.clients:
            asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop)
        self.refresh_tray()

    def _on_toggle_pause(self, icon: pystray.Icon, item: Item) -> None:
        self._toggle_pause()

    def _on_disconnect_client(self, icon: pystray.Icon, item: Item) -> None:
        self.controller.release_all_inputs()
        if self.loop and self.clients:
            asyncio.run_coroutine_threadsafe(self._close_all_clients(), self.loop)

    def _on_open_web(self, icon: pystray.Icon, item: Item) -> None:
        open_web_portal()

    def _show_window(self) -> None:
        if self.root and not self._closing:
            self.root.after(0, self._restore_window_on_main)

    def _restore_window_on_main(self) -> None:
        if not self.root or self._closing:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_to_tray(self) -> None:
        if self.root and not self._closing:
            self.root.withdraw()

    def _auto_open_web_if_no_client(self) -> None:
        if not self.clients and not self._closing:
            open_web_portal()

    def _on_tray_ready(self, icon: pystray.Icon) -> None:
        icon.visible = True
        if getattr(sys, "frozen", False):
            threading.Thread(target=install_desktop_shortcut, daemon=True).start()
        timer = threading.Timer(1.5, self._auto_open_web_if_no_client)
        timer.daemon = True
        timer.start()

    def _shutdown_all(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.controller.release_all_inputs()
        if self.loop and self.stop_event:
            try:
                self.loop.call_soon_threadsafe(self.stop_event.set)
            except Exception:
                pass
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass

    def _on_exit(self, icon: pystray.Icon, item: Item) -> None:
        self._shutdown_all()

    def _build_control_window(self) -> tk.Tk:
        root = tk.Tk()
        root.title(WINDOW_TITLE)
        root.configure(bg="#F8FAFC")
        root.resizable(False, False)

        # Center mini control card on screen
        win_w, win_h = 390, 305
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2)
        root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        self._tk_icon = ImageTk.PhotoImage(self._icon_cache["waiting"])
        root.iconphoto(True, self._tk_icon)
        root.protocol("WM_DELETE_WINDOW", self._shutdown_all)

        # Navy Header (#1E3A8A)
        header = tk.Frame(root, bg="#1E3A8A", padx=16, pady=12)
        header.pack(fill="x")

        tk.Label(
            header,
            text="AnySupport RemoteAgent",
            font=("Segoe UI", 12, "bold"),
            fg="#FFFFFF",
            bg="#1E3A8A",
        ).pack(side="left")

        admin_badge = "ADMIN" if is_admin() else "USER"
        tk.Label(
            header,
            text=admin_badge,
            font=("Segoe UI", 8, "bold"),
            fg="#1E3A8A",
            bg="#FBBF24",
            padx=8,
            pady=2,
        ).pack(side="right")

        # Status Card
        body = tk.Frame(root, bg="#F8FAFC", padx=16, pady=14)
        body.pack(fill="both", expand=True)

        status_card = tk.Frame(body, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1, padx=12, pady=10)
        status_card.pack(fill="x", pady=(0, 12))

        status_row = tk.Frame(status_card, bg="#FFFFFF")
        status_row.pack(fill="x")

        self._dot_label = tk.Label(status_row, text="●", font=("Segoe UI", 12), fg="#D97706", bg="#FFFFFF")
        self._dot_label.pack(side="left", padx=(0, 6))

        self._status_label = tk.Label(
            status_row,
            text=self._status_text(),
            font=("Segoe UI", 9, "bold"),
            fg="#0F172A",
            bg="#FFFFFF",
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True)

        tk.Label(
            status_card,
            text=f"เวอร์ชัน {AGENT_VERSION}  •  พอร์ต {HOST}:{PORT}",
            font=("Segoe UI", 8),
            fg="#64748B",
            bg="#FFFFFF",
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Action Buttons
        tk.Button(
            body,
            text="🌐  เปิดหน้าเว็บ AnySupport Web",
            command=open_web_portal,
            font=("Segoe UI", 10, "bold"),
            bg="#1E3A8A",
            fg="#FFFFFF",
            activebackground="#172554",
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            pady=8,
        ).pack(fill="x", pady=(0, 8))

        mid_row = tk.Frame(body, bg="#F8FAFC")
        mid_row.pack(fill="x", pady=(0, 8))

        self._pause_btn = tk.Button(
            mid_row,
            text="⏸ หยุดควบคุมชั่วคราว",
            command=self._toggle_pause,
            font=("Segoe UI", 9, "bold"),
            bg="#D97706",
            fg="#FFFFFF",
            activebackground="#B45309",
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            pady=6,
        )
        self._pause_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        tk.Button(
            mid_row,
            text="🔽 ซ่อนลงมุมขวาล่าง",
            command=self._hide_to_tray,
            font=("Segoe UI", 9),
            bg="#E2E8F0",
            fg="#1E293B",
            activebackground="#CBD5E1",
            relief="flat",
            cursor="hand2",
            pady=6,
        ).pack(side="right", fill="x", expand=True, padx=(4, 0))

        tk.Button(
            body,
            text="📌  สร้างไอคอนบนหน้าจอ (Desktop)",
            command=self._on_create_shortcut_clicked,
            font=("Segoe UI", 9),
            bg="#EFF6FF",
            fg="#1E3A8A",
            activebackground="#DBEAFE",
            relief="flat",
            cursor="hand2",
            pady=5,
        ).pack(fill="x", pady=(0, 8))

        tk.Button(
            body,
            text="❌  ปิดโปรแกรม RemoteAgent",
            command=self._shutdown_all,
            font=("Segoe UI", 9, "bold"),
            bg="#DC2626",
            fg="#FFFFFF",
            activebackground="#B91C1C",
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            pady=6,
        ).pack(fill="x")

        return root

    def _on_create_shortcut_clicked(self) -> None:
        ok, info = install_desktop_shortcut()
        if ok:
            user32.MessageBoxW(
                None,
                f"สร้างไอคอนไว้บน Desktop เรียบร้อยแล้ว:\n{info}",
                WINDOW_TITLE,
                MB_OK | MB_ICONINFORMATION | MB_TOPMOST,
            )
        else:
            user32.MessageBoxW(
                None,
                f"ไม่สามารถสร้างไอคอนบน Desktop ได้: {info}",
                WINDOW_TITLE,
                MB_OK | MB_TOPMOST,
            )

    def run(self) -> None:
        ws_thread = threading.Thread(target=self._run_ws_thread, daemon=True)
        ws_thread.start()

        self.root = self._build_control_window()

        menu = pystray.Menu(
            Item("🔼 แสดงหน้าต่างควบคุม", lambda icon, item: self._show_window(), default=True),
            Item("🌐 เปิดหน้าเว็บ AnySupport Web", self._on_open_web),
            pystray.Menu.SEPARATOR,
            Item(lambda item: f"สถานะ: {self._status_text()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item(
                lambda item: "เปิดรับการควบคุม (Resume)" if self.paused else "หยุดควบคุมชั่วคราว (Pause)",
                self._on_toggle_pause,
            ),
            Item(
                "ตัดการเชื่อมต่อทั้งหมด",
                self._on_disconnect_client,
                enabled=lambda item: bool(self.clients),
            ),
            pystray.Menu.SEPARATOR,
            Item("ออกจากโปรแกรม (Exit)", self._on_exit),
        )

        self.tray_icon = pystray.Icon(
            "AnySupportRemoteAgent",
            self._icon_cache["waiting"],
            f"AnySupport RemoteAgent - {self._status_text()}",
            menu,
        )
        self.tray_icon.run_detached(setup=self._on_tray_ready)
        self.root.mainloop()


def main() -> None:
    enable_dpi_awareness()
    ensure_admin_elevation()
    mutex_handle = acquire_single_instance()
    if not mutex_handle:
        sys.exit(0)

    app = RemoteAgentApp()
    app.run()


if __name__ == "__main__":
    main()
