# -*- coding: utf-8 -*-
"""make_update_manifest.py —— 生成 GitHub Release 的 update.json"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--installer", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--output", default="dist/update.json")
    args = p.parse_args()

    digest = sha256(args.installer)
    data = {
        "version": args.version,
        "url": args.url,
        "sha256": digest,
        "notes": args.notes,
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("manifest:", args.output)
    print("  version:", args.version)
    print("  sha256 :", digest)
    print("  url    :", args.url)


if __name__ == "__main__":
    main()
