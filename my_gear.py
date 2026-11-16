# -*- coding: utf-8 -*-
"""my_gear.py —— 我的外设电量（鼠标 + 耳机读取层 + 命令行）

目标设备（都是本机实测过的）：
  * 罗技 G PRO X Superlight / GPW2 —— Lightspeed 接收器 046D:C547，HID++ 2.0
  * 索尼 WH-1000XM4 —— 蓝牙 HFP 电量属性（Windows 未公开 PnP 属性）

用法：
    python my_gear.py --once           命令行读一次就退出
    python my_gear.py --autostart on|off|status
    python my_gear.py --diagnose       打印 HID/蓝牙接口信息

托盘界面在 my_gear_tray.py（纯 Win32 右键菜单，不需要 tkinter）。

底层：hid_win.py（HID 枚举/异步读）、logi_hidpp.py（罗技协议）、
      bt_battery.py（蓝牙电量属性），全部只用标准库 + ctypes。
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw
import bt_battery
import logi_hidpp as lh
import my_gear_common as tc


# ==========================================================================
# 读取层
# ==========================================================================
@dataclass
class Reading:
    key: str
    title: str
    subtitle: str = ""
    level: Optional[int] = None
    status: str = ""
    detail: str = ""
    extra: str = ""
    error: str = ""
    stale: bool = False          # True = 设备休眠，数值是上一次读到的
    updated_at: float = 0.0

    @property
    def ok(self) -> bool:
        return self.level is not None

    @property
    def short_state(self) -> str:
        """托盘菜单右侧的短状态。"""
        if self.ok:
            return f"{self.level}%"
        if "未连接" in self.error:
            return "未连接"
        if "未上报" in self.error:
            return "未上报"
        return "不可读"

    def short_note(self) -> str:
        """托盘菜单里用的一行说明。"""
        if self.ok:
            bits = [x for x in (self.status,
                                "上次读数" if self.stale else "") if x]
            return " · ".join(bits) or self.detail
        return self.detail or self.error


HEADSET_NAME_HINTS = ("WH-1000XM4",)

# 鼠标休眠时 read_mouse() 会给出这些提示；托盘据此保留上次读数
MOUSE_SLEEP_HINTS = ("没有响应", "休眠", "没找到可读电量的罗技设备")


def _pick_mouse(devs: list[lh.LogitechDevice]) -> lh.LogitechDevice:
    """接收器上可能挂了多个罗技设备，优先挑名字像鼠标的那个。"""
    def score(d: lh.LogitechDevice) -> tuple:
        name = d.name.upper()
        preferred = 0 if ("SUPERLIGHT" in name or "PRO X" in name) else 1
        has_pct = 0 if d.level is not None else 1
        return (preferred, has_pct, d.index)

    return sorted(devs, key=score)[0]


def read_mouse() -> Reading:
    """罗技鼠标：HID++ 2.0（0x1004 / 0x1000 / 0x1001）。"""
    r = Reading("mouse", "罗技 G PRO X Superlight", "Lightspeed 接收器",
                updated_at=time.time())
    iface, devs, err = lh.read_logitech_devices()
    if iface is None:
        r.error = err or "没找到罗技接收器"
        return r
    r.subtitle = f"{iface.vid_pid} · Lightspeed 接收器"
    if not devs:
        r.error = "鼠标没有响应（可能已休眠或关机，动一下鼠标即可）"
        return r

    d = _pick_mouse(devs)
    r.level = d.display_level
    r.status = d.status_text if d.status != "unknown" else ""

    bits = [d.name or "罗技设备", f"设备索引 {d.index}", d.source]
    if d.percentage_supported and d.bucket_text:
        bits.append(f"固件档位 {d.bucket_text}")
    if d.voltage_mv:
        bits.append(f"{d.voltage_mv} mV")
    if d.external_power:
        bits.append("外部供电")
    r.detail = " · ".join(bits)

    if r.level is None:
        if d.voltage_mv:
            r.error = f"设备只上报电压 {d.voltage_mv} mV，没有百分比"
        else:
            r.error = "设备没有上报电量（可能正在休眠）"
    return r


def _matched_bluetooth(hints: tuple[str, ...]) -> list[bt_battery.BluetoothDevice]:
    """按名字找匹配的蓝牙节点，优先 Hands-Free / 有电量属性的节点。"""
    wanted = tuple(h.upper() for h in hints)
    found = []
    for d in bt_battery.list_bluetooth_devices():
        name = (d.name or "").upper()
        if any(h in name for h in wanted):
            found.append(d)
    found.sort(key=lambda d: (0 if d.is_handsfree else 1,
                              0 if (d.has_property and d.battery) else 1))
    return found


def read_headset() -> Reading:
    """索尼 WH-1000XM4：蓝牙 HFP 电量（未公开 PnP 属性）。

    未连接时不显示旧值：
      * 只有主设备节点、没有 HFP/电量节点 -> “已配对，但未连接”
      * HFP 节点在但属性为 0/缺失        -> “已连接，但还没有上报电量”
      * 连节点都没有                    -> “耳机未连接”
    """
    r = Reading("headset", "索尼 WH-1000XM4", "蓝牙", updated_at=time.time())
    try:
        devs = _matched_bluetooth(HEADSET_NAME_HINTS)
    except Exception as e:
        r.error = "读取蓝牙设备出错"
        r.detail = str(e)
        return r

    if not devs:
        r.subtitle = "蓝牙 · 未连接"
        r.error = "耳机未连接"
        r.detail = "请确认 WH-1000XM4 已开机，并在 Windows 蓝牙设置里连接"
        return r

    dev = devs[0]
    r.subtitle = "蓝牙 · " + (dev.name or "WH-1000XM4")

    if dev.is_handsfree and not dev.has_property:
        r.error = "耳机已连接，但未上报电量"
        r.detail = "Windows 还没收到 HFP 电量，稍等几秒或断开重连"
        return r
    if not dev.has_property:
        r.error = "耳机已配对，但未连接"
        r.detail = "请确认 WH-1000XM4 已开机，并已连接到 Windows 蓝牙"
        return r
    if dev.battery is None or dev.battery == 0:
        r.error = "耳机已连接，但未上报电量"
        r.detail = "Windows 还没收到 HFP 电量，稍等几秒或断开重连"
        return r

    r.level = min(100, int(dev.battery))
    r.detail = dev.reason or "来自蓝牙 HFP 电量上报"
    return r


def read_all() -> list[Reading]:
    return [read_mouse(), read_headset()]


# ==========================================================================
# 文本输出（命令行 / 托盘详情对话框共用）
# ==========================================================================
def format_details(readings: list[Reading]) -> str:
    lines = []
    for r in readings:
        head = f"{r.title}：{r.level}%" if r.ok else f"{r.title}：{r.error or '不可读'}"
        if r.ok and r.stale:
            head += "（上次读数）"
        lines.append(head)
        if r.ok:
            if r.status:
                lines.append(f"  状态：{r.status}")
            if r.detail:
                lines.append(f"  {r.detail}")
            if r.stale:
                lines.append("  设备当前休眠/无响应，数值来自上一次成功读取")
        else:
            if r.detail:
                lines.append(f"  {r.detail}")
        if r.extra:
            lines.append(f"  {r.extra}")
        lines.append("")
    return "\n".join(lines).rstrip()


def cli_once(verbose: bool = True) -> None:
    readings = read_all()
    if verbose:
        print(format_details(readings))
        print(f"读取时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        for r in readings:
            if r.ok:
                print(f"{r.title}: {r.level}%   {r.detail}")
            else:
                print(f"{r.title}: {r.error or '不可读'}")


def diagnose() -> None:
    print("=== HID 接口 ===")
    for d in hw.enumerate_hid():
        print(f"{d.vid_pid}  usage={d.describe_usage()}  "
              f"in={d.input_len} out={d.output_len} feat={d.feature_len}  "
              f"{d.manufacturer!r} {d.product!r}")
    print("\n=== 蓝牙节点（只列带电量属性的）===")
    for d in bt_battery.list_bluetooth_devices():
        if d.has_property:
            print(f"{d.name}  电量={d.battery}  {d.reason}")
    print("\n=== 读取结果 ===")
    cli_once(verbose=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="我的外设电量（鼠标 + 耳机）")
    parser.add_argument("--once", action="store_true", help="命令行读一次就退出")
    parser.add_argument("--diagnose", action="store_true",
                        help="打印 HID/蓝牙接口与读取结果（排查用）")
    parser.add_argument("--autostart", choices=["on", "off", "status"],
                        help="开机自启：on 打开 / off 关闭 / status 查看")
    args = parser.parse_args()

    if args.autostart:
        if args.autostart == "status":
            st = tc.autostart_status()
            print("开机自启：", "已启用" if st["enabled"] else "未启用")
            print("  快捷方式：", st["shortcut"],
                  "(存在)" if st["shortcut_exists"] else "(不存在)")
            print("  任务管理器状态：", st["taskmanager_state"])
            print("  目标：", st["target"])
        else:
            ok = tc.set_autostart(args.autostart == "on")
            print("已" + ("加入" if args.autostart == "on" else "取消") + "开机自启",
                  "" if ok else "（失败）")
        return

    if args.diagnose:
        diagnose()
        return

    if not args.once:
        print("（托盘界面：pythonw my_gear_tray.py   |   只看一次可加 --once）\n")
    cli_once(verbose=True)


if __name__ == "__main__":
    main()
