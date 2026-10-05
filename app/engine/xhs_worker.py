# -*- coding: utf-8 -*-
"""小红书下载子进程（便携版）。

必须在 XHS-Downloader 自己的 venv 下运行：

    <xhs venv python> xhs_worker.py --url <帖子链接> --stage <暂存目录> [--limit N]

XHS-Downloader 源码目录通过环境变量 XHS_DIR 传入（由「下载工作台」在拉起子进程时设置），
这样本脚本本身不写死任何机器路径。

输出：逐行日志；结束时追加一行
    __RESULT__{"author_name":..., "author_dir":..., "img_count":..., "vid_count":...}
失败时
    __ERROR__<错误信息>
"""
import argparse
import asyncio
import json
import os
import sys

XHS_DIR = os.environ.get("XHS_DIR", "").strip()
if not XHS_DIR or not os.path.isdir(XHS_DIR):
    sys.stdout.write("__ERROR__未配置 XHS-Downloader 目录（环境变量 XHS_DIR）\n")
    sys.stdout.flush()
    sys.exit(1)

if XHS_DIR not in sys.path:
    sys.path.insert(0, XHS_DIR)

from xhs_core import run_pipeline  # noqa: E402

_REAL_STDOUT = sys.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    def emit(line):
        _REAL_STDOUT.write(str(line).rstrip() + "\n")
        _REAL_STDOUT.flush()

    try:
        result = asyncio.run(
            run_pipeline(args.url, args.stage, limit=args.limit, emit=emit, dry_run=False)
        )
        _REAL_STDOUT.write("__RESULT__" + json.dumps(result, ensure_ascii=False) + "\n")
        _REAL_STDOUT.flush()
    except Exception as exc:  # noqa: BLE001
        _REAL_STDOUT.write("__ERROR__%s: %s\n" % (type(exc).__name__, exc))
        _REAL_STDOUT.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()