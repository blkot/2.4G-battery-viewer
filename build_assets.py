# -*- coding: utf-8 -*-
"""build_assets.py —— 生成安装包/程序图标（build/app.ico）"""
from __future__ import annotations

import os
import sys

import win_icon


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "build")
    os.makedirs(out_dir, exist_ok=True)
    sizes = (16, 24, 32, 48, 64, 128, 256)
    color = (93, 220, 138)
    imgs = [(s, win_icon.battery_rgba(s, color)) for s in sizes]
    path = os.path.join(out_dir, "app.ico")
    with open(path, "wb") as f:
        f.write(win_icon.build_ico(imgs))
    print("icon:", path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    sys.exit(main())
