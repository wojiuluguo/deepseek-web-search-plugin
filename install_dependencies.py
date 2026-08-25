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
    "playwright_stealth": "playwright-stealth>=1.0.0",  # 全套伪装（--stealth full 默认）
}


def check_package(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run(cmd):
    print(f"[执行] {' '.join(cmd)}")
    subprocess.check_call(cmd)


def find_pip():
    """找一个可用的 pip（v1.22.1 修裸崩）：
    当前解释器可能是裁剪过的 venv（如 OpenClaw/hermes 宿主，无 pip 模块），
    直接 `sys.executable -m pip` 会抛裸 CalledProcessError 崩溃且无任何提示。
    探测顺序：当前解释器 pip → ensurepip 补装 → 明确报错（装到别的解释器没用，
    本脚本检查的是当前解释器的 import，装偏了白装）。"""
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                           capture_output=True, timeout=30)
        if r.returncode == 0:
            return [sys.executable, "-m", "pip"]
    except (OSError, subprocess.TimeoutExpired):
        pass
    # 当前解释器没有 pip：ensurepip 补装一次再试
    print("[提示] 当前解释器缺少 pip 模块，尝试 ensurepip 引导安装...")
    try:
        r = subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                           capture_output=True, timeout=120)
        if r.returncode == 0:
            r2 = subprocess.run([sys.executable, "-m", "pip", "--version"],
                                capture_output=True, timeout=30)
            if r2.returncode == 0:
                return [sys.executable, "-m", "pip"]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


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
        pip_cmd = find_pip()
        if pip_cmd is None:
            print("\n[错误] 当前 Python 解释器没有可用的 pip，且 ensurepip 引导失败。")
            print(f"        当前解释器: {sys.executable}")
            print("        两种解法：")
            print("        1. 用带 pip 的解释器重跑本脚本（如: py -3 install_dependencies.py）")
            print("        2. 或给当前解释器装 pip: python -m ensurepip --upgrade")
            return 1
        print("\n[安装] 正在安装缺失的 Python 包...")
        try:
            run(pip_cmd + ["install", "--upgrade"] + missing)
        except subprocess.CalledProcessError as exc:
            print(f"\n[错误] 包安装失败: {exc}")
            print("       可手动执行: " + " ".join(pip_cmd + ["install"] + missing))
            return 1
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
