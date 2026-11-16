# -*- coding: utf-8 -*-
"""make_version_info.py —— 从 version.py 生成 PyInstaller 的 version_info.txt

这样 exe 的文件版本永远和程序内置的 APP_VERSION 一致，不会忘记手改。
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import version  # noqa: E402


def main() -> None:
    nums = [int(x) for x in re.findall(r"\d+", version.APP_VERSION)[:4]]
    while len(nums) < 4:
        nums.append(0)
    ver = ".".join(str(n) for n in nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({nums[0]}, {nums[1]}, {nums[2]}, {nums[3]}),
    prodvers=({nums[0]}, {nums[1]}, {nums[2]}, {nums[3]}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Personal'),
        StringStruct('FileDescription', 'Mouse and headset battery tray'),
        StringStruct('FileVersion', '{ver}'),
        StringStruct('InternalName', 'MyGearBatteryTray'),
        StringStruct('LegalCopyright', ''),
        StringStruct('OriginalFilename', 'MyGearBatteryTray.exe'),
        StringStruct('ProductName', 'MyGearBatteryTray'),
        StringStruct('ProductVersion', '{ver}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    out_dir = os.path.join(ROOT, "build")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "version_info.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("version info:", path, "->", ver)


if __name__ == "__main__":
    main()
