# -*- coding: utf-8 -*-
"""updater.py —— GitHub Release 远程更新（标准库 + 系统 PowerShell）

更新源是一个 JSON（默认 GitHub Releases 的 latest/download/update.json）：

    {
      "version": "1.1.0",
      "url": "https://github.com/.../MyGearBatteryTray-Setup-1.1.0.exe",
      "sha256": "....",
      "notes": "更新说明",
      "published_at": "2026-11-16T..."
    }

流程：
  1. 拉 manifest，比较版本；
  2. 下载安装包到临时目录，校验 SHA-256；
  3. 写一个 PowerShell 小助手：等当前进程退出 -> 静默运行安装包 -> 重新启动。

网络说明：
  Windows 上优先用系统自带的 PowerShell `Invoke-WebRequest`（走系统代理，
  兼容性比 Python urllib 好），失败再退回 urllib。所有请求只发往更新源。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

import version

MAX_MANIFEST_BYTES = 256 * 1024
MAX_UPDATE_BYTES = 120 * 1024 * 1024
USER_AGENT = f"MyGearBatteryTray/{version.APP_VERSION}"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
CREATE_NO_WINDOW = 0x08000000


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    url: str
    sha256: str
    notes: str = ""
    published_at: str = ""


def parse_version(text: str) -> tuple[int, int, int, int]:
    nums = [int(n) for n in re.findall(r"\d+", str(text))[:4]]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])  # type: ignore[return-value]


def is_newer(latest: str, current: str = version.APP_VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def _check_url(url: str, what: str = "更新包") -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and (parsed.hostname or "") in _LOCAL_HOSTS:
        return
    if parsed.scheme == "file":
        return
    raise UpdateError(f"{what}地址必须使用 HTTPS（本地测试可用 file:// 或 127.0.0.1）")


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"})


def _ps_download(url: str, dest: str, timeout: float) -> None:
    """用系统 PowerShell 下载（Windows 上比 urllib 更能走系统代理）。"""
    script = (
        "param([string]$Url,[string]$Out)\r\n"
        "$ErrorActionPreference = 'Stop'\r\n"
        "$ProgressPreference = 'SilentlyContinue'\r\n"
        f"Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec {int(timeout)} "
        f"-UserAgent '{USER_AGENT}' -OutFile $Out\r\n"
    )
    fd, spath = tempfile.mkstemp(prefix="my_gear_http_", suffix=".ps1")
    os.close(fd)
    try:
        with open(spath, "w", encoding="utf-8-sig", newline="") as f:
            f.write(script)
        cp = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
             "-File", spath, "-Url", url, "-Out", dest],
            capture_output=True, timeout=timeout + 20,
            creationflags=CREATE_NO_WINDOW)
        if cp.returncode != 0 or not os.path.isfile(dest) or os.path.getsize(dest) <= 0:
            msg = (cp.stderr or cp.stdout or b"").decode("utf-8", "replace").strip()
            raise UpdateError("PowerShell 下载失败：" + (msg[:300] or "未知错误"))
    finally:
        try:
            os.remove(spath)
        except OSError:
            pass


def _urllib_download(url: str, dest: str, timeout: float, max_bytes: int) -> None:
    h = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(_request(url), timeout=timeout) as resp:
        status = getattr(resp, "status", None)
        if status not in (None, 200):
            raise UpdateError(f"HTTP {status}")
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise UpdateError("文件超过大小限制")
                h.update(chunk)
                f.write(chunk)
    if size <= 0:
        raise UpdateError("下载到的文件为空")


def _download_to(url: str, dest: str, timeout: float, max_bytes: int) -> None:
    """下载到 dest。Windows http(s) 优先 PowerShell，失败回退 urllib。"""
    parsed = urllib.parse.urlparse(url)
    if sys.platform == "win32" and parsed.scheme in ("http", "https"):
        try:
            _ps_download(url, dest, timeout)
            size = os.path.getsize(dest) if os.path.isfile(dest) else 0
            if size <= 0 or size > max_bytes:
                raise UpdateError("下载文件大小异常")
            return
        except Exception:
            try:
                os.remove(dest)
            except OSError:
                pass
    try:
        _urllib_download(url, dest, timeout, max_bytes)
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise


def fetch_manifest(url: str, timeout: float = 20.0) -> UpdateInfo:
    _check_url(url, "更新信息")
    fd, tmp = tempfile.mkstemp(prefix="my_gear_manifest_", suffix=".json")
    os.close(fd)
    try:
        _download_to(url, tmp, timeout, MAX_MANIFEST_BYTES)
        data = open(tmp, "rb").read(MAX_MANIFEST_BYTES + 1)
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"无法获取更新信息：{e}") from e
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if len(data) > MAX_MANIFEST_BYTES:
        raise UpdateError("更新信息文件过大")
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception as e:
        raise UpdateError(f"更新信息不是有效 JSON：{e}") from e
    if not isinstance(obj, dict):
        raise UpdateError("更新信息格式不正确")
    ver = str(obj.get("version", "")).strip()
    url2 = str(obj.get("url", "")).strip()
    sha = str(obj.get("sha256", "")).strip().lower()
    if not ver or not url2 or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise UpdateError("更新信息缺少 version/url/sha256")
    _check_url(url2, "更新包")
    return UpdateInfo(
        version=ver,
        url=url2,
        sha256=sha,
        notes=str(obj.get("notes", "") or ""),
        published_at=str(obj.get("published_at", "") or ""),
    )


def check(url: Optional[str] = None) -> Optional[UpdateInfo]:
    """返回可用的新版本；已是最新返回 None；网络/格式错误抛 UpdateError。"""
    info = fetch_manifest(url or version.UPDATE_URL)
    return info if is_newer(info.version) else None


def download(info: UpdateInfo, directory: Optional[str] = None) -> str:
    """下载并校验安装包，返回本地路径。"""
    dest_dir = directory or os.path.join(tempfile.gettempdir(),
                                         "MyGearBatteryTray_update")
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(urllib.parse.urlparse(info.url).path) or "setup.exe"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    path = os.path.join(dest_dir, f"{info.version}_{name}")
    tmp = path + ".part"
    try:
        _download_to(info.url, tmp, 60.0, MAX_UPDATE_BYTES)
        h = hashlib.sha256()
        with open(tmp, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest().lower() != info.sha256:
            raise UpdateError("安装包 SHA-256 校验失败")
        os.replace(tmp, path)
    except UpdateError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise UpdateError(f"下载更新失败：{e}") from e
    return path


def launch_installer(installer: str, exe_path: str, pid: Optional[int] = None) -> None:
    """启动一个隐藏的 PowerShell 助手：等本进程退出 -> 静默安装 -> 重新启动。"""
    pid = pid or os.getpid()
    helper = os.path.join(tempfile.gettempdir(), f"my_gear_update_{pid}.ps1")
    script = r'''param(
  [int]$ProcessId,
  [string]$Installer,
  [string]$Exe
)
$ErrorActionPreference = "SilentlyContinue"
Wait-Process -Id $ProcessId -Timeout 30
Start-Process -FilePath $Installer `
  -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
if (Test-Path -LiteralPath $Exe) {
  Start-Process -FilePath $Exe
}
Remove-Item -LiteralPath $PSCommandPath -Force
'''
    with open(helper, "w", encoding="utf-8-sig", newline="") as f:
        f.write(script)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", helper,
         "-ProcessId", str(pid), "-Installer", installer, "-Exe", exe_path],
        close_fds=True, creationflags=CREATE_NO_WINDOW | 0x00000008)


def relaunch_path() -> str:
    """安装版回到当前 exe；免安装版回到默认安装目录的 exe。"""
    if not getattr(sys, "frozen", False):
        return sys.executable
    current = os.path.abspath(sys.executable)
    if os.path.exists(os.path.join(os.path.dirname(current), "unins000.exe")):
        return current
    local = os.environ.get("LOCALAPPDATA", "")
    return os.path.join(local, "Programs", "MyGearBatteryTray",
                        "MyGearBatteryTray.exe")
