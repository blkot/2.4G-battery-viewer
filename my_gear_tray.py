# -*- coding: utf-8 -*-
"""my_gear_tray.py —— 鼠标 + 耳机托盘电量（纯 ctypes，零第三方依赖）

通知区域两个数字图标：
  * 罗技鼠标（无底板）
  * WH-1000XM4 耳机（紫色底板）

交互：
  * 右键任意图标 → 原生 Win32 菜单（电量 / 刷新 / 间隔 / 开机自启 / 详情 / 退出）
  * 左键 → 立刻刷新一次
  * 悬停 → 设备名 + 电量 / 未连接原因

行为：
  * SetTimer 驱动（默认 60 秒，菜单里可改 30 秒 ~ 30 分钟），空闲不轮询
  * 读取在后台线程，结果用窗口消息交回主线程
  * 鼠标休眠时保留上一次读数；耳机未连接时不显示旧值，只显示“未连接/未上报”
  * 不写日志文件：只有 --debug 时输出到控制台
  * 退出时 PostQuitMessage，不留僵尸进程

启动：
    pythonw my_gear_tray.py          # 静默驻留
    python  my_gear_tray.py --debug  # 前台运行 + 输出过程
    python  my_gear_tray.py --status
    python  my_gear_tray.py --quit
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import json
import sys
import threading
import time
import traceback
from ctypes import wintypes
from typing import Optional

import hid_win as hw
import my_gear
import my_gear_common as tc
import updater
import version
import win_icon

APP_NAME = tc.APP_NAME
MUTEX_NAME = tc.MUTEX_NAME
WND_CLASS = tc.WND_CLASS

USER32 = tc.USER32
KERNEL32 = tc.KERNEL32
SHELL32 = ctypes.WinDLL("shell32", use_last_error=True)

WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
MSG_TRAY_CALLBACK = WM_APP + 1
MSG_REFRESH_DONE = WM_APP + 2
MSG_UPDATE_RESULT = WM_APP + 3
MSG_UPDATE_DOWNLOADED = WM_APP + 4

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
NIF_INFO = 0x10
NIIF_INFO = 0x01

# 右键菜单
MF_STRING = 0x0000
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800
MF_POPUP = 0x0010
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100

MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONQUESTION = 0x00000020
MB_ICONINFORMATION = 0x00000040
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
IDYES = 6

ID_REFRESH = 101
ID_AUTOSTART = 102
ID_DETAILS = 103
ID_EXIT = 104
ID_UPDATE = 105
ID_CHECK_ON_START = 106
INTERVAL_ID_BASE = 201
INTERVAL_IDS = {
    INTERVAL_ID_BASE + i: sec for i, (sec, _) in enumerate(tc.INTERVAL_CHOICES)
}


# --------------------------------------------------------------------------
# Win32 结构体与原型
# --------------------------------------------------------------------------
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
                             ctypes.c_size_t, ctypes.c_ssize_t)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", ctypes.c_void_p),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", ctypes.c_void_p),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", hw.GUID),
        ("hBalloonIcon", ctypes.c_void_p),
    ]


class MSG(ctypes.Structure):
    _fields_ = [("hWnd", ctypes.c_void_p), ("message", wintypes.UINT),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", wintypes.DWORD), ("pt_x", wintypes.LONG),
                ("pt_y", wintypes.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


USER32.RegisterClassExW.restype = wintypes.WORD
USER32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
USER32.CreateWindowExW.restype = ctypes.c_void_p
USER32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
USER32.DefWindowProcW.restype = ctypes.c_ssize_t
USER32.DefWindowProcW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                  ctypes.c_size_t, ctypes.c_ssize_t]
USER32.DestroyWindow.restype = wintypes.BOOL
USER32.DestroyWindow.argtypes = [ctypes.c_void_p]
USER32.SetTimer.restype = ctypes.c_size_t
USER32.SetTimer.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.UINT,
                            ctypes.c_void_p]
USER32.KillTimer.restype = wintypes.BOOL
USER32.KillTimer.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
USER32.GetMessageW.restype = ctypes.c_int
USER32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p,
                               wintypes.UINT, wintypes.UINT]
USER32.PostQuitMessage.restype = None
USER32.PostQuitMessage.argtypes = [ctypes.c_int]
USER32.TranslateMessage.restype = wintypes.BOOL
USER32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
USER32.DispatchMessageW.restype = ctypes.c_ssize_t
USER32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]

USER32.CreatePopupMenu.restype = ctypes.c_void_p
USER32.AppendMenuW.restype = wintypes.BOOL
USER32.AppendMenuW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                               ctypes.c_size_t, wintypes.LPCWSTR]
USER32.DestroyMenu.restype = wintypes.BOOL
USER32.DestroyMenu.argtypes = [ctypes.c_void_p]
USER32.TrackPopupMenu.restype = ctypes.c_int
USER32.TrackPopupMenu.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                  ctypes.c_void_p]
USER32.GetCursorPos.restype = wintypes.BOOL
USER32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
USER32.MessageBoxW.restype = ctypes.c_int
USER32.MessageBoxW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                               wintypes.LPCWSTR, wintypes.UINT]

SHELL32.Shell_NotifyIconW.restype = wintypes.BOOL
SHELL32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                      ctypes.POINTER(NOTIFYICONDATAW)]

KERNEL32.GetModuleHandleW.restype = ctypes.c_void_p
KERNEL32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
KERNEL32.CreateMutexW.restype = ctypes.c_void_p
KERNEL32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                  wintypes.LPCWSTR]
KERNEL32.AllocConsole.restype = wintypes.BOOL
KERNEL32.GetConsoleWindow.restype = ctypes.c_void_p

# (uID, key, 提示名, 底板颜色；None = 无底板)
TRAY_ICONS = [
    (1, "mouse", "罗技鼠标", None),
    (2, "headset", "WH-1000XM4", (45, 30, 60, 235)),
]


def _say(text: str) -> None:
    """在 pythonw/无控制台的 exe 里安全地输出。"""
    if sys.stdout is not None:
        print(text, flush=True)


def _ensure_console() -> None:
    """给打包后的 --debug 模式分配一个控制台。"""
    if sys.stdout is not None:
        return
    try:
        if not KERNEL32.GetConsoleWindow():
            KERNEL32.AllocConsole()
    except Exception:
        pass
    try:
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
    except Exception:
        pass


# --------------------------------------------------------------------------
# 托盘程序
# --------------------------------------------------------------------------
class TrayApp:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.cfg = tc.load_config()
        self.hwnd: Optional[int] = None
        self.wndproc_ref = None
        self.busy = False
        self.readings: dict[str, Optional[my_gear.Reading]] = {
            key: None for _, key, _, _ in TRAY_ICONS
        }
        self.icons_added = False
        self.startup_retries = 0
        self.update_busy = False
        self.download_busy = False
        self.update_checked = False
        self.update_info: Optional[updater.UpdateInfo] = None
        self.update_error = ""
        self.downloaded_path = ""
        self.taskbar_created_msg = USER32.RegisterWindowMessageW("TaskbarCreated")
        self.msg_quit = USER32.RegisterWindowMessageW(tc.MSG_QUIT)
        self.msg_reload = USER32.RegisterWindowMessageW(tc.MSG_RELOAD)
        self.log("启动，配置 = " + json.dumps(self.cfg, ensure_ascii=False))

    # ---- 输出（默认不落盘）---------------------------------------------
    def log(self, msg: str) -> None:
        if self.debug and sys.stdout is not None:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)

    # ---- 图标 ----------------------------------------------------------
    @staticmethod
    def _color(level: Optional[int]) -> tuple[int, int, int]:
        if level is None:
            return (150, 155, 160)
        if level >= 60:
            return (93, 220, 138)
        if level >= 30:
            return (245, 196, 81)
        return (255, 107, 107)

    def _nid(self, uID: int):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = uID
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = MSG_TRAY_CALLBACK
        return nid

    def _apply_icon(self, action: int, uID: int, key: str, title: str,
                    plate) -> bool:
        r = self.readings.get(key)

        if r is None:
            level, tip = None, f"{title}：正在读取…"
        elif r.ok:
            level = r.level
            status = f" {r.status}" if r.status else ""
            if r.stale:
                tip = f"{title}：{level}%{status}（上次读数 · 设备休眠）"
            else:
                tip = (f"{title}：{level}%{status}"
                       f"（{time.strftime('%H:%M:%S')} 更新）")
        else:
            level, tip = None, f"{title}：{r.error or '读取失败'}"

        text = str(level) if level is not None else "?"
        nid = self._nid(uID)
        # 未知状态也给一个底板，避免 16px 的 "?" 看起来像空白
        has_plate = plate is not None or level is None
        plate_color = plate or ((64, 68, 74, 235) if level is None
                                else (28, 30, 34, 235))
        if level == 100:
            # 三位数 100 在 16px 下会被缩小，改用满电电池图标
            nid.hIcon = win_icon.make_battery_hicon(
                self._color(level), has_plate, plate_color)
        else:
            nid.hIcon = win_icon.make_hicon(
                text, self._color(level), has_plate, plate_color)
        nid.szTip = tip[:120]
        return bool(SHELL32.Shell_NotifyIconW(action, ctypes.byref(nid)))

    def notify(self, title: str, text: str) -> None:
        """在鼠标图标上弹一个气泡通知（Windows 11 通知关闭时可能不显示）。"""
        if not self.icons_added:
            return
        nid = self._nid(1)
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        nid.dwInfoFlags = NIIF_INFO
        nid.uVersion = 4
        SHELL32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def add_icons(self) -> None:
        for uID, key, title, plate in TRAY_ICONS:
            ok = self._apply_icon(NIM_ADD, uID, key, title, plate)
            self.log(f"NIM_ADD {title} -> {'ok' if ok else '失败'}")
        self.icons_added = True

    def update_icons(self) -> None:
        if not self.icons_added:
            self.add_icons()
            return
        for uID, key, title, plate in TRAY_ICONS:
            self._apply_icon(NIM_MODIFY, uID, key, title, plate)

    def remove_icons(self) -> None:
        for uID, _, _, _ in TRAY_ICONS:
            nid = self._nid(uID)
            nid.uFlags = 0
            SHELL32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self.icons_added = False

    # ---- 定时器 / 配置 --------------------------------------------------
    def apply_timer(self) -> None:
        if not self.hwnd:
            return
        USER32.KillTimer(self.hwnd, 1)
        USER32.SetTimer(self.hwnd, 1, int(self.cfg["interval"]) * 1000, None)

    def apply_config(self) -> None:
        """同步外部改过的配置；开机自启只读不改。"""
        new = tc.load_config()
        changed = new["interval"] != self.cfg["interval"]
        self.cfg = new
        if changed:
            self.log(f"刷新间隔 -> {new['interval']} 秒")
            self.apply_timer()

        actual = tc.is_autostart_enabled()
        if bool(self.cfg.get("autostart")) != actual:
            self.cfg["autostart"] = actual
            tc.save_config(self.cfg)
            self.log(f"开机自启实际为 {actual}，已同步到配置（未改动系统设置）")

    # ---- 刷新 ----------------------------------------------------------
    def refresh_now(self) -> None:
        if self.busy or not self.hwnd:
            return
        self.busy = True
        threading.Thread(target=self._worker, args=(self.hwnd,), daemon=True).start()

    def _merge(self, new: my_gear.Reading) -> my_gear.Reading:
        """鼠标休眠时，把上一次的成功读数保留下来。耳机不做这个，避免显示旧电量。"""
        prev = self.readings.get(new.key)
        if (not new.ok and new.key == "mouse" and prev is not None and prev.ok
                and any(h in new.error for h in my_gear.MOUSE_SLEEP_HINTS)):
            self.log(f"鼠标无响应，沿用上次读数 {prev.level}%")
            return dataclasses.replace(
                new, level=prev.level, status=prev.status, detail=prev.detail,
                extra=prev.extra, error="", stale=True,
                updated_at=prev.updated_at)
        return new

    def _worker(self, hwnd: int) -> None:
        try:
            for r in my_gear.read_all():
                self.readings[r.key] = self._merge(r)
        except Exception:
            self.log("读取异常:\n" + traceback.format_exc())
        USER32.PostMessageW(hwnd, MSG_REFRESH_DONE, 0, 0)

    def on_refresh_done(self) -> None:
        self.busy = False
        parts = []
        for _, key, _, _ in TRAY_ICONS:
            r = self.readings.get(key)
            if r is None:
                parts.append(f"{key}=?")
            elif r.ok:
                parts.append(f"{key}={r.level}{'*' if r.stale else ''}")
            else:
                parts.append(f"{key}=--")
        self.log("刷新完成：" + "  ".join(parts))
        self.update_icons()

        # 启动后如果鼠标还是空的，做几次短间隔重试（不改变 60 秒的常规轮询）
        mouse = self.readings.get("mouse")
        if mouse is not None and mouse.ok:
            if self.hwnd:
                USER32.KillTimer(self.hwnd, 2)
        elif self.startup_retries < 5 and self.hwnd:
            self.startup_retries += 1
            delay = min(1500 * self.startup_retries, 10000)
            USER32.KillTimer(self.hwnd, 2)
            USER32.SetTimer(self.hwnd, 2, delay, None)
            self.log(f"启动刷新未拿到鼠标电量，{delay}ms 后重试"
                     f"（{self.startup_retries}/5）")

        # 启动时检查一次 GitHub Release（可右键菜单关闭）
        if not self.update_checked:
            self.update_checked = True
            if self.cfg.get("check_updates", True):
                self.start_update_check(manual=False)

    # ---- 远程更新（GitHub Release）-------------------------------------
    def _msg(self, text: str, title: str,
             flags: int = MB_OK | MB_ICONINFORMATION) -> int:
        return USER32.MessageBoxW(
            None, text, title, flags | MB_SETFOREGROUND | MB_TOPMOST)

    def start_update_check(self, manual: bool) -> None:
        if self.update_busy or self.download_busy:
            if manual:
                self._msg("正在检查或下载更新，请稍候。", "检查更新")
            return
        self.update_busy = True
        self.update_error = ""
        url = (self.cfg.get("update_url") or version.UPDATE_URL)
        threading.Thread(target=self._update_worker,
                         args=(manual, url), daemon=True).start()

    def _update_worker(self, manual: bool, url: str) -> None:
        status = 2
        try:
            info = updater.check(url)
            self.update_info = info
            status = 1 if info is not None else 0
        except Exception as e:
            self.update_info = None
            self.update_error = str(e)
            status = 2
        if self.hwnd:
            USER32.PostMessageW(self.hwnd, MSG_UPDATE_RESULT,
                                1 if manual else 0, status)

    def on_update_result(self, manual: bool, status: int) -> None:
        self.update_busy = False
        if status == 1 and self.update_info is not None:
            info = self.update_info
            if manual:
                self.prompt_update()
            else:
                self.log(f"发现新版本 v{info.version}")
                self.notify("发现新版本",
                            f"外设电量 v{info.version} 可用，右键托盘图标更新")
        elif status == 0:
            if manual:
                self._msg(f"当前已是最新版本 v{version.APP_VERSION}。",
                          "检查更新")
        else:
            if manual:
                self._msg("检查更新失败：\n" + (self.update_error or "未知错误"),
                          "检查更新", MB_OK | MB_ICONQUESTION)

    def prompt_update(self) -> None:
        info = self.update_info
        if info is None:
            self.start_update_check(manual=True)
            return
        msg = (f"发现新版本 v{info.version}\n"
               f"当前版本 v{version.APP_VERSION}")
        if info.notes.strip():
            msg += "\n\n" + info.notes.strip()[:800]
        msg += "\n\n现在下载并安装吗？"
        if self._msg(msg, "检查更新",
                     MB_YESNO | MB_ICONQUESTION) == IDYES:
            self.start_update_download()

    def start_update_download(self) -> None:
        if self.download_busy or self.update_info is None:
            return
        self.download_busy = True
        self.update_error = ""
        info = self.update_info
        self.log(f"开始下载 v{info.version}")
        threading.Thread(target=self._download_worker,
                         args=(info,), daemon=True).start()

    def _download_worker(self, info: updater.UpdateInfo) -> None:
        ok = True
        try:
            self.downloaded_path = updater.download(info)
        except Exception as e:
            self.update_error = str(e)
            ok = False
        if self.hwnd:
            USER32.PostMessageW(self.hwnd, MSG_UPDATE_DOWNLOADED,
                                1 if ok else 0, 0)

    def on_update_downloaded(self, ok: bool) -> None:
        self.download_busy = False
        if not ok:
            self._msg("下载更新失败：\n" + (self.update_error or "未知错误"),
                      "下载更新", MB_OK | MB_ICONQUESTION)
            return
        if not getattr(sys, "frozen", False):
            self._msg("更新包已经下载，但当前是源码运行，不会自动安装。\n\n"
                      + self.downloaded_path, "更新包已下载")
            return
        ver = self.update_info.version if self.update_info else "新版本"
        if self._msg(f"v{ver} 已下载。\n\n现在退出并安装吗？",
                     "安装更新", MB_YESNO | MB_ICONQUESTION) == IDYES:
            self.launch_update()

    def launch_update(self) -> None:
        if not self.downloaded_path:
            return
        try:
            updater.launch_installer(self.downloaded_path,
                                     updater.relaunch_path())
        except Exception as e:
            self._msg("启动安装失败：\n" + str(e), "安装更新",
                      MB_OK | MB_ICONQUESTION)
            return
        self.quit()

    # ---- 右键菜单 ------------------------------------------------------
    def _menu_line(self, r: Optional[my_gear.Reading], title: str) -> tuple[str, str]:
        if r is None:
            return f"{title}\t…", "正在读取"
        if r.ok:
            right = f"{r.level}%" + ("（上次）" if r.stale else "")
            return f"{title}\t{right}", r.short_note()
        return f"{title}\t{r.short_state}", r.short_note() or "读取失败"

    def build_menu(self):
        """构造右键菜单。返回 (menu, submenus)；调用方负责 DestroyMenu。"""
        menu = USER32.CreatePopupMenu()
        submenus = []
        if not menu:
            return 0, submenus

        for _, key, title, _ in TRAY_ICONS:
            line, note = self._menu_line(self.readings.get(key), title)
            USER32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, line)
            if note:
                USER32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0,
                                   "   " + note[:60])

        USER32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0,
                           f"外设电量 v{version.APP_VERSION}")
        USER32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        USER32.AppendMenuW(menu, MF_STRING, ID_REFRESH, "刷新\t左键")

        sub = USER32.CreatePopupMenu()
        submenus.append(sub)
        current = int(self.cfg["interval"])
        for i, (sec, label) in enumerate(tc.INTERVAL_CHOICES):
            flags = MF_STRING | (MF_CHECKED if sec == current else 0)
            USER32.AppendMenuW(sub, flags, INTERVAL_ID_BASE + i, label)
        USER32.AppendMenuW(menu, MF_POPUP, sub, "刷新间隔")

        boot_flags = MF_STRING | (MF_CHECKED if tc.is_autostart_enabled() else 0)
        USER32.AppendMenuW(menu, boot_flags, ID_AUTOSTART, "开机自启")

        check_flags = MF_STRING | (
            MF_CHECKED if self.cfg.get("check_updates", True) else 0)
        USER32.AppendMenuW(menu, check_flags, ID_CHECK_ON_START,
                           "启动时检查更新")

        if self.update_busy:
            USER32.AppendMenuW(menu, MF_STRING | MF_GRAYED, ID_UPDATE,
                               "正在检查更新…")
        elif self.download_busy:
            USER32.AppendMenuW(menu, MF_STRING | MF_GRAYED, ID_UPDATE,
                               "正在下载更新…")
        elif self.update_info is not None:
            USER32.AppendMenuW(menu, MF_STRING, ID_UPDATE,
                               f"更新到 v{self.update_info.version}…")
        else:
            USER32.AppendMenuW(menu, MF_STRING, ID_UPDATE, "检查更新…")

        USER32.AppendMenuW(menu, MF_STRING, ID_DETAILS, "查看详情…")
        USER32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        USER32.AppendMenuW(menu, MF_STRING, ID_EXIT, "退出")
        return menu, submenus

    def show_menu(self) -> None:
        menu, submenus = self.build_menu()
        if not menu:
            return
        cmd = 0
        try:
            pt = POINT()
            USER32.GetCursorPos(ctypes.byref(pt))
            self.log(f"打开菜单：cursor=({pt.x},{pt.y})")
            USER32.SetForegroundWindow(self.hwnd)
            cmd = USER32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                pt.x, pt.y, 0, self.hwnd, None)
            USER32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            for sub in submenus:
                USER32.DestroyMenu(sub)
            USER32.DestroyMenu(menu)

        self.log(f"菜单选择：{cmd}")
        if cmd:
            self.on_menu(cmd)

    def on_menu(self, cmd: int) -> None:
        if cmd == ID_REFRESH:
            self.refresh_now()
        elif cmd == ID_AUTOSTART:
            want = not tc.is_autostart_enabled()
            ok = tc.set_autostart(want)
            self.cfg["autostart"] = want
            tc.save_config(self.cfg)
            self.log(f"开机自启 -> {want} ({'ok' if ok else '失败'})")
            if not ok:
                USER32.MessageBoxW(
                    None, "无法创建「启动」文件夹里的快捷方式。\n"
                          "可以手动把本程序放进启动文件夹。",
                    "外设电量", MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND)
        elif cmd == ID_CHECK_ON_START:
            self.cfg["check_updates"] = not bool(
                self.cfg.get("check_updates", True))
            tc.save_config(self.cfg)
            self.log(f"启动时检查更新 -> {self.cfg['check_updates']}")
            if self.cfg["check_updates"] and not self.update_checked:
                self.update_checked = True
                self.start_update_check(manual=False)
        elif cmd == ID_UPDATE:
            if self.update_info is not None:
                self.prompt_update()
            else:
                self.start_update_check(manual=True)
        elif cmd == ID_DETAILS:
            self.show_details()
        elif cmd == ID_EXIT:
            self.quit()
        elif cmd in INTERVAL_IDS:
            sec = INTERVAL_IDS[cmd]
            self.cfg["interval"] = sec
            tc.save_config(self.cfg)
            self.apply_timer()
            self.log(f"刷新间隔 -> {sec} 秒（菜单）")

    def show_details(self) -> None:
        readings = [r for r in (self.readings.get(key)
                                for _, key, _, _ in TRAY_ICONS) if r is not None]
        if len(readings) != len(TRAY_ICONS):
            text = "还在读取，请稍后再看。"
        else:
            text = my_gear.format_details(readings)
        text += f"\n\n外设电量 v{version.APP_VERSION}"
        if self.update_info is not None:
            text += f"\n发现新版本 v{self.update_info.version}（右键菜单可更新）"
        USER32.MessageBoxW(None, text, "外设电量详情",
                           MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND
                           | MB_TOPMOST)

    def quit(self) -> None:
        self.log("退出")
        self.remove_icons()
        try:
            win_icon.destroy_all()
            win_icon.cleanup_files()
        except Exception:
            self.log("清理图标时出错（忽略）：\n" + traceback.format_exc())
        if self.hwnd:
            USER32.DestroyWindow(self.hwnd)

    # ---- 窗口过程 ------------------------------------------------------
    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == MSG_TRAY_CALLBACK:
            event = int(lparam) & 0xFFFF
            if event == WM_RBUTTONUP:
                self.show_menu()
            elif event == WM_LBUTTONUP:
                self.refresh_now()
            return 0
        if msg == MSG_REFRESH_DONE:
            self.on_refresh_done()
            return 0
        if msg == MSG_UPDATE_RESULT:
            self.on_update_result(bool(wparam), int(lparam))
            return 0
        if msg == MSG_UPDATE_DOWNLOADED:
            self.on_update_downloaded(bool(wparam))
            return 0
        if msg == WM_TIMER:
            if int(wparam) == 2:
                # 启动后的鼠标补刷定时器（只跑一次）
                USER32.KillTimer(hwnd, 2)
                if not self.busy:
                    self.refresh_now()
                return 0
            self.apply_config()
            self.refresh_now()
            return 0
        if msg == self.msg_quit:
            self.quit()
            return 0
        if msg == self.msg_reload:
            self.apply_config()
            return 0
        if msg == self.taskbar_created_msg:
            self.log("任务栏重建，重新添加图标")
            self.add_icons()
            return 0
        if msg == WM_DESTROY:
            # 关键：让消息循环真正退出，避免留下没有窗口的僵尸进程
            USER32.PostQuitMessage(0)
            return 0
        return USER32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---- 启动 ----------------------------------------------------------
    def run(self) -> int:
        hinst = KERNEL32.GetModuleHandleW(None)
        self.wndproc_ref = WNDPROC(self.wnd_proc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self.wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = WND_CLASS
        if not USER32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err not in (0, 1410):
                self.log(f"RegisterClassExW 失败 err={err}")
                return 1

        hwnd = USER32.CreateWindowExW(0x00000080,  # WS_EX_TOOLWINDOW：不进任务栏
                                      WND_CLASS, APP_NAME, 0, 0, 0, 0, 0,
                                      None, None, hinst, None)
        if not hwnd:
            self.log(f"CreateWindowExW 失败 err={ctypes.get_last_error()}")
            return 1
        self.hwnd = hwnd

        self.add_icons()
        self.apply_config()
        self.apply_timer()
        self.refresh_now()

        msg = MSG()
        while USER32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            USER32.TranslateMessage(ctypes.byref(msg))
            USER32.DispatchMessageW(ctypes.byref(msg))
        self.log("消息循环结束")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="外设电量托盘（鼠标 + 耳机）")
    parser.add_argument("--debug", action="store_true", help="前台运行并输出日志")
    parser.add_argument("--status", action="store_true", help="打印当前状态")
    parser.add_argument("--quit", action="store_true", help="让正在运行的实例退出")
    parser.add_argument("--autostart", choices=["on", "off", "status"],
                        help="开机自启：on 打开 / off 关闭 / status 查看")
    args = parser.parse_args()

    if args.debug and getattr(sys, "frozen", False):
        _ensure_console()

    if args.autostart:
        if args.autostart == "status":
            st = tc.autostart_status()
            _say("开机自启：" + ("已启用" if st["enabled"] else "未启用"))
            _say("  快捷方式：" + st["shortcut"])
            _say("  目标：" + st["target"])
        else:
            ok = tc.set_autostart(args.autostart == "on")
            _say("已" + ("加入" if args.autostart == "on" else "取消") + "开机自启"
                 + ("" if ok else "（失败）"))
        return 0

    if args.status:
        _say("版本：" + version.APP_VERSION)
        _say("配置：" + json.dumps(tc.load_config(), ensure_ascii=False))
        _say("开机自启：" + str(tc.is_autostart_enabled()))
        _say("启动命令：" + tc.autostart_command())
        _say("托盘是否在运行：" + str(tc.is_tray_running()))
        return 0
    if args.quit:
        ok = tc.post_to_tray(tc.MSG_QUIT)
        if ok:
            # 等托盘真正退出，卸载器随后才能删除正在运行的 exe
            deadline = time.time() + 3.0
            while time.time() < deadline and tc.is_tray_running():
                time.sleep(0.05)
        _say("已通知托盘退出" if ok else "托盘没在运行")
        return 0

    KERNEL32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == 183:
        if tc.is_tray_running():
            tc.post_to_tray(tc.MSG_RELOAD)
            _say("已经在运行了（托盘里的数字图标就是它；右键图标打开菜单）")
        else:
            _say("单实例锁被占用，但没找到托盘窗口；请稍后重试")
        return 0

    try:
        USER32.SetProcessDPIAware()            # 图标不糊
    except Exception:
        pass

    app = TrayApp(debug=args.debug)
    try:
        return app.run()
    except Exception:
        if sys.stderr is not None:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
