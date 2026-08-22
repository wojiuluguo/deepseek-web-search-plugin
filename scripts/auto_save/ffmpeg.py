"""ffmpeg/ffprobe 探测与解码验证：自包含工具函数（输入路径→输出数字），
不碰浏览器不碰全局状态——拆分绝对安全级。
铁律：fMP4 抓包产物的 moov Duration 不可信（抖音 3.8MB 可标 95s 实际 31s），
判断真实时长必须解码验证。"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _find_tool(name: str) -> Optional[str]:
    """三保险找 ffmpeg/ffprobe：
    1. 环境变量显式指定：FFMPEG_PATH / FFPROBE_PATH / FFMPEGPATH / FFMPEG_LOCATION
       （yt-dlp 惯用 FFMPEG_LOCATION，一并认；可给 exe 全路径或所在目录）；
    2. PATH（shutil.which）；
    3. 常见安装位置扫描：winget/scoop/choco/ProgramFiles/C:\\ffmpeg/用户目录下 ffmpeg\\。
    找到即缓存，进程内不重复找。"""
    exe = f"{name}.exe" if os.name == "nt" else name
    # 1. 显式环境变量（允许指向 exe 文件或其所在目录）
    for var in (f"{name.upper()}_PATH", "FFMPEGPATH", "FFMPEG_LOCATION"):
        v = os.environ.get(var, "").strip().strip('"')
        if v:
            p = Path(v)
            if p.is_file():
                # 必须文件名匹配：FFMPEGPATH 指向 ffmpeg.exe 时不能被当成 ffprobe
                if p.name.lower() == exe.lower():
                    return str(p)
                continue
            if p.is_dir():
                cand = p / exe
                if cand.is_file():
                    return str(cand)
    # 2. PATH
    found = shutil.which(name)
    if found:
        return found
    # 3. 常见安装位置（Windows 为主；用户手放 ffmpeg 目录没加 PATH 也能找到）
    if os.name == "nt":
        candidates: List[Path] = [
            Path("C:\\ffmpeg") / f"{name}.exe",
            Path("C:\\ffmpeg") / "bin" / f"{name}.exe",
            Path.home() / "ffmpeg" / f"{name}.exe",            # 例 C:\Users\wqq\ffmpeg\ffmpeg.exe
            Path.home() / "ffmpeg" / "bin" / f"{name}.exe",
            Path.home() / "AppData" / "Local" / "ffmpeg" / "bin" / f"{name}.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "ffmpeg" / "bin" / f"{name}.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "ffmpeg" / "bin" / f"{name}.exe",
            Path("C:\\ProgramData\\chocolatey\\bin") / f"{name}.exe",
            Path.home() / "scoop" / "shims" / f"{name}.exe",
        ]
        # winget 安装：...\WinGet\Packages\*ffmpeg*\[子目录\]bin\
        winget = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
        if winget.is_dir():
            for pkg in winget.glob("*[Ff][Ff]mpeg*"):
                candidates.append(pkg / "bin" / f"{name}.exe")
                candidates.append(pkg / f"{name}.exe")
                try:
                    for sub in pkg.iterdir():
                        if sub.is_dir():
                            candidates.append(sub / "bin" / f"{name}.exe")
                            candidates.append(sub / f"{name}.exe")
                except OSError:
                    continue
        for c in candidates:
            try:
                if c.is_file():
                    return str(c)
            except OSError:
                continue
    return None


def _ffmpeg_path() -> Optional[str]:
    if not hasattr(_ffmpeg_path, "_cache"):
        _ffmpeg_path._cache = _find_tool("ffmpeg")
    return _ffmpeg_path._cache


def _ffprobe_path() -> Optional[str]:
    if not hasattr(_ffprobe_path, "_cache"):
        _ffprobe_path._cache = _find_tool("ffprobe")
    return _ffprobe_path._cache


def _decoded_duration(path) -> Optional[float]:
    """解码验证真实时长。ffmpeg 全程解到 null，取最后 time=。
    返回秒数；解码失败/无 ffmpeg 返回 None。"""
    ffmpeg = _ffmpeg_path()
    if not ffmpeg or not os.path.exists(path):
        return None
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=180,
        )
        times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
        if not times:
            return None
        h, m, s = times[-1]
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return None


def _ffprobe_info(path) -> Optional[Dict]:
    """ffprobe 拿流信息（分辨率/编码/标称时长）。失败返回 None。"""
    ffprobe = _ffprobe_path()
    if not ffprobe or not os.path.exists(path):
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=60,
        )
        return json.loads(proc.stdout) if proc.stdout.strip() else None
    except Exception:
        return None


def _probe_resolution(info: Optional[Dict]) -> Optional[Tuple[int, int]]:
    if not info:
        return None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and s.get("width") and s.get("height"):
            return (int(s["width"]), int(s["height"]))
    return None


__all__ = [
    '_find_tool',
    '_ffmpeg_path',
    '_ffprobe_path',
    '_decoded_duration',
    '_ffprobe_info',
    '_probe_resolution',
]
