# -*- coding: utf-8 -*-
"""my_gear_common.py —— 我的三台外设托盘工具的配置 / 开机自启 / 进程间通信

和项目里的 tray_common.py 是同一套思路，但**独立命名**：
这样“外设电量”托盘和原来的 ATK/DARKRIM 托盘可以同时运行，
不会互相抢单实例锁、也不会改到对方的启动项。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from typing import Optional

import win_shell

if getattr(sys, "frozen", False):
    # PyInstaller 单文件 exe：配置放在 exe 所在目录（安装到用户目录时可写）
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = bool(getattr(sys, "frozen", False))
CONFIG_PATH = os.path.join(BASE_DIR, "my_gear_config.json")

# 单独的名字：不和 DeviceBatteryTray 冲突
APP_NAME = "MyGearBatteryTray"
WND_CLASS = "MyGearBatteryTrayWnd"
MUTEX_NAME = r"Global\MyGearBatteryTray_single_instance"

TRAY_SCRIPT = "my_gear_tray.py"
STARTUP_LNK_NAME = "外设电量托盘.lnk"

DEFAULT_CONFIG = {
    "interval": 60,        # 托盘轮询间隔（秒）
    "autostart": True,     # 只记录用户意愿；真实状态以启动项为准
    "check_updates": True, # 启动时检查 GitHub Release
    "update_url": "",      # 空 = 使用 version.UPDATE_URL
}

INTERVAL_CHOICES = [(30, "30 秒"), (60, "1 分钟"), (120, "2 分钟"),
                    (300, "5 分钟"), (600, "10 分钟"), (1800, "30 分钟")]

STARTUP_APPROVED_FOLDER = (r"Software\Microsoft\Windows\CurrentVersion"
                           r"\Explorer\StartupApproved\StartupFolder")

USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

USER32.FindWindowW.restype = ctypes.c_void_p
USER32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
USER32.PostMessageW.restype = wintypes.BOOL
USER32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                ctypes.c_size_t, ctypes.c_ssize_t]
USER32.RegisterWindowMessageW.restype = wintypes.UINT
USER32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
USER32.ShowWindow.restype = wintypes.BOOL
USER32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
USER32.SetForegroundWindow.restype = wintypes.BOOL
USER32.SetForegroundWindow.argtypes = [ctypes.c_void_p]


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in DEFAULT_CONFIG:
                if key in data:
                    cfg[key] = data[key]
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    clean = {key: cfg.get(key, DEFAULT_CONFIG[key]) for key in DEFAULT_CONFIG}
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
def pythonw_path() -> str:
    if FROZEN:
        return sys.executable
    exe = sys.executable or ""
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def tray_script() -> str:
    if FROZEN:
        return ""
    return os.path.join(BASE_DIR, TRAY_SCRIPT)


def autostart_command() -> str:
    if FROZEN:
        return f'"{sys.executable}"'
    return f'"{pythonw_path()}" "{tray_script()}"'


def startup_lnk() -> str:
    return os.path.join(win_shell.startup_dir(), STARTUP_LNK_NAME)


# --------------------------------------------------------------------------
# 开机自启：启动文件夹 + StartupApproved（任务管理器可见、可禁用）
# --------------------------------------------------------------------------
def _startup_approved() -> Optional[bool]:
    """True 启用 / False 被任务管理器禁用 / None 没记录。"""
    import winreg
    base = os.path.basename(startup_lnk())
    names = (base, os.path.splitext(base)[0])
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER,
                            0, winreg.KEY_READ) as k:
            for name in names:
                try:
                    data, _ = winreg.QueryValueEx(k, name)
                except OSError:
                    continue
                if isinstance(data, (bytes, bytearray)) and data:
                    return data[0] != 0x03
    except OSError:
        pass
    return None


def _set_startup_approved(enabled: bool) -> None:
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER,
                                0, winreg.KEY_SET_VALUE) as k:
            data = bytes([0x02 if enabled else 0x03]) + bytes(11)
            winreg.SetValueEx(k, os.path.basename(startup_lnk()), 0,
                              winreg.REG_BINARY, data)
    except OSError:
        pass


def _clear_startup_approved() -> None:
    import winreg
    base = os.path.basename(startup_lnk())
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER,
                                0, winreg.KEY_SET_VALUE) as k:
            for name in (base, os.path.splitext(base)[0]):
                try:
                    winreg.DeleteValue(k, name)
                except OSError:
                    pass
    except OSError:
        pass


def is_autostart_enabled() -> bool:
    if win_shell.shortcut_exists(startup_lnk()):
        return _startup_approved() is not False
    return False


def set_autostart(enabled: bool) -> bool:
    if enabled:
        ok = win_shell.create_shortcut(
            startup_lnk(), pythonw_path(),
            arguments="" if FROZEN else f'"{tray_script()}"',
            workdir=BASE_DIR,
            description="外设电量托盘：罗技鼠标 / WH-1000XM4")
        _set_startup_approved(True)
        return ok
    _clear_startup_approved()
    win_shell.remove_shortcut(startup_lnk())
    return not win_shell.shortcut_exists(startup_lnk())


def autostart_status() -> dict:
    lnk = startup_lnk()
    approved = _startup_approved()
    return {
        "enabled": is_autostart_enabled(),
        "shortcut": lnk,
        "shortcut_exists": win_shell.shortcut_exists(lnk),
        "taskmanager_state": ("已启用" if approved is not False else "已被任务管理器禁用")
                              if approved is not None else "未记录（默认启用）",
        "target": autostart_command(),
    }


# --------------------------------------------------------------------------
# 进程间通信
# --------------------------------------------------------------------------
MSG_QUIT = "MyGearBatteryTray_Quit"
MSG_RELOAD = "MyGearBatteryTray_Reload"


def tray_hwnd() -> int:
    h = USER32.FindWindowW(WND_CLASS, None)
    return int(h) if h else 0


def is_tray_running() -> bool:
    return tray_hwnd() != 0


def post_to_tray(msg_name: str) -> bool:
    hwnd = tray_hwnd()
    if not hwnd:
        return False
    msg = USER32.RegisterWindowMessageW(msg_name)
    return bool(USER32.PostMessageW(hwnd, msg, 0, 0))


def start_tray_app(wait_timeout: float = 6.0) -> bool:
    """启动托盘（pythonw 静默进程），等它的窗口出现再返回。"""
    import subprocess
    import time
    if is_tray_running():
        return True
    try:
        cmd = [sys.executable] if FROZEN else [pythonw_path(), tray_script()]
        subprocess.Popen(cmd, cwd=BASE_DIR, creationflags=0x00000008)
    except Exception:
        return False
    deadline = time.time() + max(wait_timeout, 0)
    while time.time() < deadline:
        if is_tray_running():
            return True
        time.sleep(0.15)
    return is_tray_running()
