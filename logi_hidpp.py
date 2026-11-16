# -*- coding: utf-8 -*-
"""logi_hidpp.py —— 罗技 HID++ 2.0 最小客户端（纯 ctypes，零第三方依赖）

只做这个工具需要的事：
  * 通过 Lightspeed / Unifying 接收器跟「设备索引 1..6」说话
  * 读设备名（Feature 0x0005）
  * 读电量：统一电池 0x1004 → 电池状态 0x1000 → 电池电压 0x1001

协议要点
--------
* 接收器的厂商接口是 usage page 0xFF00：
    - usage 0x0002：输入/输出各 20 字节，用 Report ID 0x11（长报文）
    - usage 0x0001：输入/输出各  7 字节，用 Report ID 0x10（短报文）
* 请求格式： [rid, devIndex, featureIndex, (function<<4)|swid, 参数...]
* 回复格式： [rid, devIndex, featureIndex, (function<<4)|swid, 数据...]
* 错误回复： 第 3 字节 bit7 置位（0x8F），第 4 字节是错误码。
* 设备索引：接在接收器上的设备是 1..6；0xFF 表示「当前设备 / 直连设备」。
* 读特性索引：向 Feature 0x0000（IRoot）发 function 0，参数是目标特性 ID，
  回复第 4 字节就是该特性的索引。

注意：罗技接收器的 HID 接口是共享的，可以正常以读写权限打开；
但**不要**在同一个句柄上并发阻塞读 + 写（会打崩进程），
所以这里复用 hid_win.HidDevice 的独立 overlapped 读句柄。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw
from hid_win import HidDevice, HidError

LOGITECH_VID = 0x046D

USAGE_PAGE = 0xFF00
USAGE_LONG = 0x0002
USAGE_SHORT = 0x0001

RID_LONG = 0x11
RID_SHORT = 0x10

FEATURE_ROOT = 0x0000
FEATURE_FEATURE_SET = 0x0001
FEATURE_DEVICE_NAME = 0x0005
FEATURE_BATTERY_STATUS = 0x1000
FEATURE_BATTERY_VOLTAGE = 0x1001
FEATURE_UNIFIED_BATTERY = 0x1004

# 0x1000 / 0x1004 的电池状态字节
BATTERY_STATUS = {
    0: ("discharging", "放电中"),
    1: ("charging", "充电中"),
    2: ("charging", "充电中（涓流）"),
    3: ("full", "已充满"),
    4: ("charging", "充电中（慢速）"),
    5: ("unknown", "电池类型无效"),
    6: ("unknown", "温度异常"),
    7: ("unknown", "充电异常"),
}

# 上次找到的设备索引（单进程内缓存，避免每次刷新都全量探测）
_LAST_PRESENT: list[int] = []


@dataclass
class LogitechDevice:
    """接收器上的一个罗技设备。"""

    index: int
    name: str = ""
    level: Optional[int] = None          # 0-100，设备没有电量计时为 None
    bucket: int = 0                      # 粗粒度电量档位 1/2/4/8
    percentage_supported: bool = False
    status: str = "unknown"
    external_power: int = 0
    voltage_mv: Optional[int] = None
    source: str = ""
    raw: bytes = b""
    error: str = ""

    @property
    def status_text(self) -> str:
        for _, (text, label) in BATTERY_STATUS.items():
            if text == self.status:
                return label
        return "未知"

    @property
    def bucket_text(self) -> str:
        return {1: "临界", 2: "低", 4: "良好", 8: "满"}.get(self.bucket, "")

    @property
    def display_level(self) -> Optional[int]:
        """优先用百分比；没有电量计时用固件档位给一个近似值。"""
        if self.level is not None:
            return self.level
        return {1: 5, 2: 20, 4: 50, 8: 90}.get(self.bucket)



def pick_receiver_interface() -> Optional[hw.HidInterface]:
    """挑一个能收发 HID++ 的罗技厂商接口（优先长报文）。"""
    candidates = [
        d for d in hw.enumerate_hid()
        if d.vid == LOGITECH_VID and d.usage_page == USAGE_PAGE and d.output_len
    ]
    if not candidates:
        return None
    # 20 字节的长报文接口优先；其次 7 字节短报文
    for usage in (USAGE_LONG, USAGE_SHORT):
        for d in candidates:
            if d.usage == usage and d.input_len and d.output_len:
                return d
    return candidates[0]


class Hidpp:
    """一个已打开的 HID++ 通道。"""

    def __init__(self, iface: hw.HidInterface, timeout_ms: int = 300):
        self.iface = iface
        self.dev: Optional[HidDevice] = None
        self.timeout_ms = timeout_ms
        # 长报文接口固定用 0x11；7 字节的小接口只能 0x10
        self.rid = RID_LONG if (iface.output_len or 0) >= 20 else RID_SHORT
        self.report_len = 20 if self.rid == RID_LONG else 7

    # -- 生命周期 ------------------------------------------------------
    def open(self) -> "Hidpp":
        self.dev = HidDevice(self.iface.path, write=True)
        if not self.dev.write_access:
            raise HidError("罗技厂商接口打不开写权限（被厂商软件独占？）")
        return self

    def close(self) -> None:
        if self.dev is not None:
            self.dev.close()
            self.dev = None

    def __enter__(self) -> "Hidpp":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- 一次请求/回复 --------------------------------------------------
    def call(self, dev_index: int, feature_index: int, function: int,
             params: list[int] = (), timeout_ms: Optional[int] = None) -> Optional[bytes]:
        if self.dev is None:
            return None
        body = [self.rid, dev_index, feature_index,
                ((function & 0x0F) << 4) | 0x01] + list(params)
        body = (body + [0] * self.report_len)[: self.report_len]
        try:
            self.dev.drain()
            self.dev.write_output(bytes(body))
        except HidError:
            return None

        timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        deadline = time.monotonic() + max(timeout, 1) / 1000.0
        while time.monotonic() < deadline:
            remain = deadline - time.monotonic()
            report = self.dev.read_input(timeout_ms=int(max(remain, 0.01) * 1000) or 1)
            if not report or len(report) < 4:
                continue
            if (report[0] != self.rid or report[1] != dev_index
                    or report[2] != feature_index):
                continue
            # 错误回复：function=0xF 且 bit7 置位
            if report[3] & 0x80:
                return None
            if ((report[3] >> 4) & 0x0F) != function:
                continue
            return report
        return None

    @staticmethod
    def _error_code(report: bytes) -> Optional[int]:
        if len(report) >= 5 and report[3] & 0x80:
            return report[4]
        return None

    # -- 特性索引 ------------------------------------------------------
    def feature_index(self, dev_index: int, feature_id: int,
                      timeout_ms: Optional[int] = None) -> Optional[int]:
        reply = self.call(dev_index, 0x00, 0x00,
                          [feature_id >> 8, feature_id & 0xFF],
                          timeout_ms=timeout_ms)
        if not reply or self._error_code(reply) is not None:
            return None
        # 标准位置是第 4 字节；个别设备/固件会放在 5/6，兜底试一下
        for pos in (4, 5, 6):
            if len(reply) > pos and reply[pos]:
                return reply[pos]
        return None

    # -- 设备名 --------------------------------------------------------
    def device_name(self, dev_index: int) -> str:
        fidx = self.feature_index(dev_index, FEATURE_DEVICE_NAME)
        if not fidx:
            return ""
        head = self.call(dev_index, fidx, 0x00)
        if not head or len(head) < 5:
            return ""
        count = head[4]
        if not 0 < count <= 64:
            return ""
        raw = bytearray()
        for offset in range(0, count, 16):
            chunk = self.call(dev_index, fidx, 0x01, [offset])
            if not chunk or len(chunk) <= 4:
                break
            raw += chunk[4:4 + 16]
            if len(raw) >= count:
                break
        return bytes(raw[:count]).decode("utf-8", errors="ignore").strip()

    # -- 电量 ----------------------------------------------------------
    def battery(self, dev_index: int) -> Optional[LogitechDevice]:
        info = LogitechDevice(index=dev_index)

        # 1) 统一电池（0x1004）
        #     fn0 = 能力：byte0 = 支持的档位, byte1 bit1 = 有百分比电量计
        #     fn1 = 状态：byte0 = 百分比, byte1 = 档位, byte2 = 充电状态,
        #                 byte3 = 外部供电
        fidx = self.feature_index(dev_index, FEATURE_UNIFIED_BATTERY)
        if fidx:
            caps = self.call(dev_index, fidx, 0x00)
            if caps and len(caps) >= 6:
                info.percentage_supported = bool(caps[5] & 0x02)

            reply = self.call(dev_index, fidx, 0x01)
            if reply and len(reply) >= 7:
                level = reply[4]
                bucket = reply[5]
                st = reply[6]
                info.bucket = bucket if bucket in (1, 2, 4, 8) else 0
                info.status = BATTERY_STATUS.get(st, ("unknown", ""))[0]
                info.external_power = reply[7] if len(reply) > 7 else 0
                if info.percentage_supported:
                    info.level = level if 0 <= level <= 100 else None
                info.source = "HID++ 0x1004 统一电池"
                info.raw = reply
                if info.level is not None or info.bucket:
                    return info

        # 2) 旧版电池状态（0x1000）：level, next_level, status
        fidx = self.feature_index(dev_index, FEATURE_BATTERY_STATUS)
        if fidx:
            reply = self.call(dev_index, fidx, 0x00)
            if reply and len(reply) >= 7:
                level, st = reply[4], reply[6]
                if 0 <= level <= 100:
                    info.level = level
                    info.status = BATTERY_STATUS.get(st, ("unknown", ""))[0]
                    info.source = "HID++ 0x1000 电池状态"
                    info.raw = reply
                    return info

        # 3) 电池电压（0x1001）：大端 16 位 mV + 标志位
        fidx = self.feature_index(dev_index, FEATURE_BATTERY_VOLTAGE)
        if fidx:
            reply = self.call(dev_index, fidx, 0x00)
            if reply and len(reply) >= 6:
                mv = (reply[4] << 8) | reply[5]
                if 2000 <= mv <= 5000:
                    info.voltage_mv = mv
                    info.source = "HID++ 0x1001 电池电压"
                    info.raw = reply
                    return info
        return None

    # -- 扫描 ----------------------------------------------------------
    def _present(self, index: int, timeout_ms: int) -> bool:
        """设备索引是否存在：查 FEATURE_SET（每个 HID++ 2.0 设备都有）。"""
        return self.feature_index(index, FEATURE_FEATURE_SET,
                                  timeout_ms=timeout_ms) is not None

    def scan(self) -> list[LogitechDevice]:
        """扫描接收器上的设备，返回有电量信息的那些。

        先试上次找到的索引（常见情况 ~30ms 一个）；都不在才全量探测。
        空索引不会回包，全量探测必须用很短的超时，否则一次要好几秒。
        """
        global _LAST_PRESENT
        # 只缓存真实设备索引；0xFF 可能只是接收器本身（没有电量），
        # 不能把它当成“找到了设备”，否则鼠标醒来后不会再扫描 1..6。
        candidates = [i for i in _LAST_PRESENT
                      if i != 0xFF and self._present(i, 150)]
        if not candidates:
            candidates = [i for i in (1, 2, 3, 4, 5, 6)
                          if self._present(i, 80)]
            if not candidates and self._present(0xFF, 100):
                candidates = [0xFF]          # 直连（USB 线 / 蓝牙）
            _LAST_PRESENT = [i for i in candidates if i != 0xFF]

        found: list[LogitechDevice] = []
        for index in candidates:
            info = self.battery(index)
            if info is None:
                continue
            info.name = self.device_name(index)
            found.append(info)
        return found


def read_logitech_devices() -> tuple[Optional[hw.HidInterface],
                                     list[LogitechDevice], str]:
    """打开罗技接收器并扫描。返回 (接口, 设备列表, 错误说明)。"""
    iface = pick_receiver_interface()
    if iface is None:
        return None, [], "没找到罗技接收器（请把 Lightspeed / Unifying 接收器插好）"
    try:
        with Hidpp(iface) as client:
            devs = client.scan()
    except HidError as e:
        return iface, [], f"打开罗技厂商接口失败：{e}"
    except Exception as e:                       # 驱动异常也不该让界面崩
        return iface, [], f"读取罗技设备出错：{e}"
    return iface, devs, ""


if __name__ == "__main__":
    iface, devs, err = read_logitech_devices()
    print("接口：", iface.vid_pid if iface else "-", iface.describe_usage() if iface else "")
    if err:
        print("错误：", err)
    for d in devs:
        level = d.display_level
        print(f"  索引 {d.index}: {d.name or '(无名)'}  "
              f"{level if level is not None else '--'}%  "
              f"{d.status_text}  {d.bucket_text}  {d.voltage_mv or ''}mV  [{d.source}]")
