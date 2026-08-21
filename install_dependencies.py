#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Web Search Skill - 一键安装依赖

自动检查并安装本 Skill 所有脚本需要的依赖：
  - playwright          -> 浏览器模拟搜索 / 自创保存型浏览器
  - yt-dlp              -> 自动保存浏览器直接下载视频
  - Chromium            -> Playwright 浏览器内核

用法：
    python install_dependencies.py
    py -3 install_dependencies.py
"""

import importlib.util
import shutil
import subprocess
import sys

REQUIRED_PACKAGES = {
    "playwright": "playwright>=1.40.0",
    "yt_dlp": "yt-dlp>=2024.0.0",
}


def check_package(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run(cmd):
    print(f"[执行] {' '.join(cmd)}")
    subprocess.check_call(cmd)


def main():
    print("=" * 60)
    print("DeepSeek Web Search Skill - 依赖自动安装")
    print("=" * 60)

    missing = []
    for module, pip_name in REQUIRED_PACKAGES.items():
        if check_package(module):
            print(f"[已安装] {pip_name}")
        else:
            missing.append(pip_name)
            print(f"[缺少] {pip_name}")

    if missing:
        print("\n[安装] 正在安装缺失的 Python 包...")
        run([sys.executable, "-m", "pip", "install", "--upgrade"] + missing)
    else:
        print("\n[跳过] Python 依赖都已安装。")

    # Playwright Chromium 内核
    if check_package("playwright"):
        print("\n[检查] Playwright Chromium 内核...")
        try:
            run([sys.executable, "-m", "playwright", "install", "chromium"])
        except subprocess.CalledProcessError as exc:
            print(f"\n[警告] Chromium 自动安装失败：{exc}")
            print("你可以手动运行: python -m playwright install chromium")
    else:
        print("\n[跳过] Playwright 未安装，无法检查 Chromium。")

    # ffmpeg 检查（yt-dlp 合并视频时可选）
    if shutil.which("ffmpeg"):
        print("[检查] ffmpeg 已安装。")
    else:
        print("\n[提示] 未检测到 ffmpeg。")
        print("       yt-dlp 下载普通单视频通常不需要；")
        print("       如果需要合并高清视频+音频，建议安装 ffmpeg。")

    print("\n" + "=" * 60)
    print("依赖安装/检查完成。")
    print("如果之前 OpenClaw 正在运行，建议重启网关或新开会话。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
