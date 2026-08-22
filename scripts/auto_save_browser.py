#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Auto-Save Browser — 自创“保存型浏览器/保存型搜索引擎”

用 Playwright 打开网页后，自动把页面里出现的视频、音频、图片等媒体文件
直接保存到本地缓存目录。默认浏览器一般只是播放/临时缓存，不会主动存到本地；
这个脚本相当于一个“看到就保存、直接下载”的浏览器。

支持方式：
    chain   默认，自动按顺序尝试 direct -> ytdlp -> browser -> cache -> text
    direct  直链媒体直接下载
    browser 真实浏览器边播边缓存（自动播放/懒加载/206分段/合并/DOM收割）
    cache   专门抓 206 分段缓存（同样带 DOM 收割兜底）
    ytdlp   yt-dlp 直接下载完整视频
    auto    先 yt-dlp 直接下载，失败再真实浏览器缓存
    harvest DOM/元数据/内嵌JSON 收割 + 页面上下文下载（快，专抓照片/音频/防热链资源）
    text    提取页面正文并保存为 txt（文章/文档/帖子等纯文本内容）

媒体类型选择：
    --media-type video,audio,image   任意逗号组合，默认全部
    只要照片: --media-type image；只要音频: --media-type audio

用法：
    # 直接打开一个视频/网页并自动保存媒体（默认 chain）
    python auto_save_browser.py --url "https://v.douyin.com/xxxx"

    # 先用自带搜索引擎找结果，再自动打开第一个视频类结果并保存
    python auto_save_browser.py --query "抖音 猫 视频" --auto

    # 指定保存目录
    python auto_save_browser.py --url "https://v.douyin.com/xxxx" --output-dir "C:/Users/ioo/Downloads/缓存"

可靠性设计（针对抓包产物的已知坑）：
    - wait 自适应：还在出新分段就继续等（上限 --max-wait），不再因 wait 太短只抓到开头
    - 合并前按 URL 目录分组：正片/音频轨/推荐位视频天然分家，垃圾分段不拼接
    - 合并后 ffmpeg 解码验证真实时长，失败或 <3s 直接弃，绝不留坏文件
    - fMP4 moov 时长不可信，verified_duration_sec 一律来自解码实测
    - 垃圾资源（封面/图标/gif/bin）默认不落盘；合并成功后 cache_segments 自动清理
    - blob 抓取带 15s 硬超时，不会挂死
"""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
});
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".m4s", ".mkv", ".avi", ".flv", ".ts"}
AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".wma")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
MEDIA_EXTENSIONS = VIDEO_EXTS | set(AUDIO_EXTS) | set(IMAGE_EXTS)

CONTENT_TYPE_EXT = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/x-matroska": ".mkv",
    "video/mp2t": ".ts",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

VIDEO_LIKE_HOSTS = (
    "douyin.com",
    "iesdouyin.com",
    "tiktok.com",
    "bilibili.com",
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "weibo.com",
    "kuaishou.com",
    "ixigua.com",
    "xiaohongshu.com",
    "xhslink.com",
)

# 图片电路：只有这些图片站/图片直链才值得导航过去收割
IMAGE_LIKE_HOSTS = (
    "image.baidu.com",
    "pic.sogou.com",
    "image.so.com",
    "tuchong.com",
    "huaban.com",
    "pixabay.com",
    "unsplash.com",
    "pexels.com",
)

# 音频电路：音乐平台/播客站
AUDIO_LIKE_HOSTS = (
    "music.163.com",
    "y.qq.com",
    "kuwo.cn",
    "kugou.com",
    "ximalaya.com",
    "lizhi.fm",
    "qingting.fm",
    "soundcloud.com",
)

# 文件电路：压缩包/文档/表格/演示/电子书/安装包/文本等一切非视频照片音频的东西
FILE_EXTS = (
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".md", ".epub", ".mobi",
    ".apk", ".msi", ".exe", ".iso", ".dmg",
)

SEARCH_REDIRECT_HOSTS = (
    "so.com",
    "sogou.com",
    "baidu.com",
    "sm.cn",
    "bing.com",
    "cn.bing.com",
    "quark.com",
)


def _decode_redirect_url(url: str) -> str:
    """Try to extract the real target URL from search-engine redirect links."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.lower() not in SEARCH_REDIRECT_HOSTS and "link" not in parsed.path.lower():
            return ""
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "target", "m", "q", "link", "redirect", "u", "to"):
            vals = query.get(key)
            if vals:
                val = vals[0]
                if val.startswith(("http://", "https://")):
                    return val
                decoded = urllib.parse.unquote(val)
                if decoded.startswith(("http://", "https://")):
                    return decoded
    except Exception:
        pass
    return ""


def _is_media_url(url: str, content_type: str) -> bool:
    if url.startswith(("data:", "blob:")):
        return False
    ct = (content_type or "").lower()
    if ct.startswith(("video/", "audio/", "image/")):
        return True
    path = urllib.parse.urlparse(url).path.lower()
    ext = Path(path).suffix
    return ext in MEDIA_EXTENSIONS


def _media_kind(url: str, content_type: str) -> str:
    """判定 URL/响应属于哪类媒体：video / audio / image，非媒体返回空串。"""
    if url.startswith(("data:", "blob:")):
        return ""
    ct = (content_type or "").lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    if ct.startswith("image/"):
        return "image"
    path = urllib.parse.urlparse(url).path.lower()
    ext = Path(path).suffix
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    return ""


def _ext_from_content_type(content_type: str) -> str:
    ct = (content_type or "").lower().split(";")[0].strip()
    return CONTENT_TYPE_EXT.get(ct, "")


# ---------- ffmpeg/ffprobe 校验工具 ----------
# fMP4 抓包产物的 moov Duration 不可信（抖音 3.8MB 可标 95s 实际 31s），
# 判断真实时长必须解码验证：ffmpeg -i x -f null - 解到尾，看最后的 time=。


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


# ---------- 垃圾资源过滤 ----------
# 抓包会混入大量页面资源：UI 图、推荐位封面、gif、bin 残片。
# 默认直接跳过不落盘；--save-junk 时存到 junk/ 子目录。

JUNK_EXTENSIONS = {".gif", ".bin"}
JUNK_URL_HINTS = (
    "/static/", "/assets/", "/asset/", "/sprite", "/icon", "/emoji",
    "/logo", "/avatar", "/widget", "/common/", "/public/",
)

# ---- 安全模式（--safe）：访问可疑站点时保护本机 ----
# 可执行/安装包/脚本宏扩展名：导航命中即拦（页面自身的 .js 资源不拦，拦了网站全坏；
# 恶意脚本靠域名黑名单 + 落盘白名单 + Chromium 进程沙箱兜底）。
DANGEROUS_EXTS = {
    ".exe", ".msi", ".msix", ".msp", ".scr", ".bat", ".cmd", ".com", ".pif",
    ".ps1", ".psm1", ".vbs", ".vbe", ".jse", ".wsf", ".wsh", ".hta",
    ".jar", ".cpl", ".reg", ".lnk", ".app", ".dmg", ".pkg", ".deb", ".rpm",
    ".apk", ".appimage", ".sh", ".bash",
}
# 已知挖矿/矿池/恶意服务域名（含子域名匹配）
MINING_DOMAINS = {
    "coinhive.com", "authedmine.com", "cryptoloot.com", "crypto-loot.com",
    "jsecoin.com", "minero.cc", "minergate.com", "deepminer.site",
    "webminepool.com", "coinimp.com", "nanopool.org", "supportxmr.com",
    "c3pool.com", "moneroocean.stream", "minexmr.com", "xmrpool.eu",
    "nicehash.com", "2miners.com", "f2pool.com", "antpool.com",
}
# Stratum 挖矿协议常用端口（WebSocket/WebTransport 命中即拦）
STRATUM_PORTS = (":3333", ":4444", ":5555", ":7777", ":8888")
# 安全模式落盘扩展名白名单（媒体 + 文本产物），其余一律不落盘
SAFE_ALLOWED_EXTS = MEDIA_EXTENSIONS | {".txt", ".json"}
# 安全模式单文件大小上限（防磁盘填充）
SAFE_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024


def _safe_request_reason(url: str, resource_type: str) -> Optional[str]:
    """安全模式请求裁决：返回拦截原因字符串，None 表示放行。"""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host and any(host == d or host.endswith("." + d) for d in MINING_DOMAINS):
        return f"挖矿/恶意域名 {host}"
    if resource_type == "websocket" and any(p in url for p in STRATUM_PORTS):
        return f"矿池 Stratum 端口 {host}"
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext in DANGEROUS_EXTS and resource_type in ("document", "other", ""):
        return f"危险文件导航 {ext}"
    return None


def _safe_save_reason(filename: str, size: int) -> Optional[str]:
    """安全模式落盘裁决：返回拒绝原因字符串，None 表示放行。"""
    ext = Path(filename).suffix.lower()
    if ext not in SAFE_ALLOWED_EXTS:
        return f"非白名单扩展名 {ext or '(无扩展名)'}"
    if size > SAFE_MAX_FILE_BYTES:
        return f"超过 {SAFE_MAX_FILE_BYTES // (1024 * 1024)}MB 上限"
    return None


def _setup_safe_mode(context, page) -> Dict[str, int]:
    """安全模式浏览器加固：请求拦截 + 弹窗全关。返回 blocked 计数（闭包自增）。
    进程沙箱/站点隔离由 launch 参数控制（见 _browser_launch_args）。"""
    blocked = {"requests": 0, "popups": 0}

    def _route(route):
        try:
            reason = _safe_request_reason(route.request.url, route.request.resource_type)
            if reason:
                blocked["requests"] += 1
                sys.stderr.write(f"[safe-block] {reason}: {route.request.url[:120]}\n")
                route.abort()
                return
            route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    def _popup(popup):
        blocked["popups"] += 1
        try:
            sys.stderr.write(f"[safe-block] 弹窗已关闭: {popup.url[:120]}\n")
            popup.close()
        except Exception:
            pass

    context.route("**/*", _route)
    page.on("popup", _popup)
    return blocked


def _browser_launch_args(safe: bool) -> List[str]:
    """launch 参数：普通模式关沙箱换兼容性；安全模式恢复 Chromium 进程沙箱
    和站点隔离（每个站点独立进程，渲染进程逃逸也碰不到本机文件）。"""
    args = ["--disable-blink-features=AutomationControlled"]
    if not safe:
        args += ["--disable-features=IsolateOrigins,site-per-process", "--no-sandbox"]
    return args


def _is_junk_resource(url: str, content_type: str, size: int, size_strict: bool = True) -> bool:
    """判定垃圾资源。size_strict=False 时跳过尺寸阈值（图集收割场景：
    用户点名要图，几十 KB 的正片图不是垃圾；只按扩展名/URL 关键词滤真图标）。"""
    ct = (content_type or "").lower()
    path = urllib.parse.urlparse(url).path.lower()
    ext = Path(path).suffix
    if ext in JUNK_EXTENSIONS:
        return True
    if any(h in url.lower() for h in JUNK_URL_HINTS):
        return True
    if not size_strict:
        return False
    # 小图片基本都是封面/图标，不是内容
    if ct.startswith("image/") and size < 150 * 1024:
        return True
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp") and size < 150 * 1024:
        return True
    # 小音频残片（铃声/音效）
    if ct.startswith("audio/") and 0 < size < 30 * 1024:
        return True
    return False


def _safe_filename(url: str, content_type: str, index: int) -> str:
    parsed = urllib.parse.urlparse(url)
    base = os.path.basename(parsed.path)
    ext = Path(base).suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        ext = _ext_from_content_type(content_type)
    if not ext:
        ext = ".bin"
    stem = Path(base).stem[:80] if base and Path(base).stem else "media"
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip(" .")
    if not stem:
        stem = "media"
    return f"{int(time.time())}_{index:03d}_{stem}{ext}"


def _save_bytes(data: bytes, output_dir: Path, url: str, content_type: str, index: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(url, content_type, index)
    path = output_dir / filename
    path.write_bytes(data)
    return path


def _parse_netscape_cookies(cookie_file: str):
    """解析 Netscape cookies.txt（浏览器扩展导出的标准格式）→ Playwright add_cookies 列表。
    返回 (cookies, error)：error 非 None 表示文件不可用（不存在/格式坏/没有有效行）。"""
    p = Path(cookie_file)
    if not p.is_file():
        return None, f"cookies 文件不存在: {cookie_file}"
    cookies = []
    try:
        for ln in p.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln.startswith("//"):
                continue
            parts = ln.split("\t")
            if len(parts) != 7:
                continue
            domain, _, path_s, secure, expires, name, value = parts
            try:
                exp = int(expires)
            except ValueError:
                exp = -1
            if not name:
                continue
            c = {
                "name": name, "value": value,
                "domain": domain if domain.startswith(".") else "." + domain,
                "path": path_s or "/",
                "secure": secure.upper() == "TRUE",
            }
            # expires=0/-1 → 会话 cookie，Playwright 用 -1 表示
            c["expires"] = exp if exp > 0 else -1
            cookies.append(c)
    except Exception as exc:
        return None, f"cookies 文件读取失败: {exc}"
    if not cookies:
        return None, "cookies 文件里没有有效行（需要 Netscape 格式，'Get cookies.txt' 扩展导出的就是）"
    return cookies, None


def _add_cookies_to_context(context, cookie_file: str):
    """把 cookies.txt 注入浏览器上下文。返回 (True, n) 或 (False, error)。"""
    cookies, err = _parse_netscape_cookies(cookie_file)
    if err:
        return False, err
    try:
        context.add_cookies(cookies)
        return True, len(cookies)
    except Exception as exc:
        return False, f"cookie 注入失败: {exc}"


def _download_with_ytdlp(url: str, output_dir: Path, safe: bool = False,
                         cookie_file: str = "", cookies_from_browser: str = ""):
    """Try yt-dlp first. Returns (saved_list, error_string).
    cookie_file：Netscape cookies.txt 路径；cookies_from_browser：chrome/edge/firefox，
    两者都给时 cookie_file 优先（文件可以离线管理，浏览器 cookie 要本机登录过）。"""
    try:
        import yt_dlp
    except ImportError:
        return [], "yt-dlp not installed"
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(output_dir / "%(title).80s [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    }
    # 登录态 cookie：抖音/B站等强制登录才给视频流的站点靠这个过墙
    if cookie_file:
        if Path(cookie_file).is_file():
            ydl_opts["cookiefile"] = cookie_file
        else:
            return [], f"cookies 文件不存在: {cookie_file}"
    elif cookies_from_browser:
        # yt-dlp 原生支持从浏览器配置直接读（免导出，但本机浏览器得登录过）
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
    # 关键：yt-dlp 合并 B站等分离音视频流时用它自己的探测找 ffmpeg（不看我们的
    # _find_tool），找不到就中止。把探测结果显式喂给它——ffmpeg 同目录自带 ffprobe。
    ffmpeg = _ffmpeg_path()
    if ffmpeg:
        ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return [], "yt-dlp returned no info"
            entries = info.get("entries") or [info]
            saved = []
            for entry in entries:
                if not entry:
                    continue
                paths = []
                for item in entry.get("requested_downloads") or []:
                    fp = item.get("filepath")
                    if fp and os.path.exists(fp):
                        paths.append(fp)
                if not paths:
                    fp = ydl.prepare_filename(entry)
                    if os.path.exists(fp):
                        paths.append(fp)
                for fp in paths:
                    saved.append(
                        {
                            "url": url,
                            "path": fp,
                            "content_type": "",
                            "size": os.path.getsize(fp),
                            "kind": "yt-dlp",
                        }
                    )
            # Fallback: if path detection failed but files were actually written,
            # report recently-created files in the output directory.
            if not saved:
                now = time.time()
                for p in sorted(output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                    if p.name.startswith("."):
                        continue
                    if p.is_file() and now - p.stat().st_mtime < 120:
                        saved.append(
                            {
                                "url": url,
                                "path": str(p),
                                "content_type": "",
                                "size": p.stat().st_size,
                                "kind": "yt-dlp",
                            }
                        )
                        if len(saved) >= 10:
                            break
            # 安全模式：yt-dlp 产物过落盘白名单 + 大小上限，违规即删
            if safe:
                kept = []
                for item in saved:
                    reason = _safe_save_reason(os.path.basename(item["path"]), item.get("size", 0))
                    if reason:
                        sys.stderr.write(f"[safe-block] yt-dlp 产物拒绝 {reason}: {item['path']}\n")
                        try:
                            os.remove(item["path"])
                        except OSError:
                            pass
                    else:
                        kept.append(item)
                saved = kept
            return saved, None
    except Exception as exc:
        return [], str(exc)


def _download_direct(url: str, output_dir: Path, safe: bool = False):
    """Try to download a direct media file (mp4/jpg/mp3...) with a browser-like UA."""
    parsed = urllib.parse.urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENTS[0],
                "Referer": f"{parsed.scheme}://{parsed.netloc}/",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
        if ext not in MEDIA_EXTENSIONS:
            ext = _ext_from_content_type(content_type)
        if not ext:
            return [], "not a direct media URL or unknown content-type"
        if len(data) < 1024:
            return [], "file too small"
        if safe:
            reason = _safe_save_reason(f"x{ext}", len(data))
            if reason:
                return [], f"safe mode 拒绝: {reason}"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"direct_{int(time.time())}{ext}"
        path.write_bytes(data)
        saved = [
            {
                "url": url,
                "path": str(path),
                "content_type": content_type,
                "size": len(data),
                "kind": "direct",
            }
        ]
        return saved, None
    except Exception as exc:
        return [], str(exc)


def _pick_video_url(results: List[Dict[str, str]], query: str = "") -> str:
    """挑搜索结果里的视频链接。query 含平台词（抖音/B站等）时该平台结果优先；
    平台结果不存在时如实回退第一个视频类链接（不编造）。"""
    # query → 首选域名偏好（用户说“去抖音搜”就必须先挑抖音）
    PLATFORM_HINTS = {
        "抖音": ("douyin.com", "iesdouyin.com"),
        "tiktok": ("tiktok.com",),
        "b站": ("bilibili.com", "b23.tv"),
        "哔哩": ("bilibili.com", "b23.tv"),
        "bilibili": ("bilibili.com", "b23.tv"),
        "快手": ("kuaishou.com",),
        "西瓜": ("ixigua.com",),
        "小红书": ("xiaohongshu.com", "xhslink.com"),
        "微博": ("weibo.com",),
        "youtube": ("youtube.com", "youtu.be"),
        "油管": ("youtube.com", "youtu.be"),
    }
    preferred: tuple = ()
    q = (query or "").lower()
    for word, hosts in PLATFORM_HINTS.items():
        if word in q:
            preferred = hosts
            break

    def _host_of(u: str) -> str:
        return urllib.parse.urlparse(u).netloc.lower()

    # 第一轮：只挑首选平台的视频链接
    if preferred:
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            for cand in (_decode_redirect_url(url), url):
                if cand and any(h in _host_of(cand) for h in preferred):
                    return cand
    # 第二轮（无偏好或首选平台无结果）：第一个视频类链接
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        # Try the real URL hidden in redirect links.
        decoded = _decode_redirect_url(url)
        for cand in (decoded, url):
            if not cand:
                continue
            host = _host_of(cand)
            if any(vh in host for vh in VIDEO_LIKE_HOSTS):
                return cand
        # Search-engine redirect links are acceptable too: the browser can follow them.
        host = _host_of(url)
        if any(rh in host for rh in SEARCH_REDIRECT_HOSTS):
            return url
    return ""


def _detect_media_intent(query: str, media_types: str = "") -> str:
    """检测这次搜索要的媒体类型（导航决策，不是落盘过滤）。
    优先级：--media-type 单选 > query 关键词推断 > 默认 video。
    检测结果决定走哪条电路：图片找图片页、音频找音乐站，不再全挤到视频电路。"""
    types = [t.strip() for t in re.split(r"[,，]", (media_types or "").strip()) if t.strip()]
    if len(types) == 1 and types[0] in ("video", "audio", "image", "file", "text"):
        return types[0]
    q = (query or "").lower()
    if any(w in q for w in ("图片", "照片", "壁纸", "头像", "表情包", "原图", "插画", "写真")):
        return "image"
    if any(w in q for w in ("音乐", "歌曲", "音频", "铃声", "伴奏", "纯音乐", "播客", "广播剧")):
        return "audio"
    if any(w in q for w in ("文件", "压缩包", "文档", "课件", "报告", "电子书", "安装包",
                            "pdf", "zip", "rar", "7z", "docx", "xlsx", "pptx", "epub", "tar.gz")):
        return "file"
    if any(w in q for w in ("小说", "文章", "正文", "全文", "章节", "原文阅读")):
        return "text"
    return "video"


def _detect_url_media_type(url: str, media_types: str = "") -> str:
    """按 URL 特征识别目标媒体类型（--url 模式的专用电路选择）。
    优先级：视频站域名 > --media-type 单选 > URL 扩展名（图/音/文件）> 图/音站域名 > 默认 video。
    视频站一票否决：抖音/B站等"视频流+音频流分离"的站点，页面里的音频就是视频的
    伴音轨，必须整体走视频路（yt-dlp 下双流合并 / cache 分段合并），绝不能因为
    --media-type audio 被导去音频专用线只抓半条伴音流。"""
    u = (url or "").strip()
    parsed = urllib.parse.urlparse(u)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    # 第一优先：视频站域名。无论 --media-type 怎么单选，视频页永远走视频路。
    if any(vh in host for vh in VIDEO_LIKE_HOSTS):
        return "video"
    types = [t.strip() for t in re.split(r"[,，]", (media_types or "").strip()) if t.strip()]
    if len(types) == 1 and types[0] in ("video", "audio", "image", "file", "text"):
        return types[0]
    if path.endswith(IMAGE_EXTS):
        return "image"
    if path.endswith(AUDIO_EXTS):
        return "audio"
    if path.endswith(FILE_EXTS):
        return "file"
    if any(h in host for h in IMAGE_LIKE_HOSTS):
        return "image"
    if any(h in host for h in AUDIO_LIKE_HOSTS):
        return "audio"
    return "video"


def _route_method(url: str, media_types: str, explicit_method: Optional[str]) -> str:
    """--url 模式方法选路：显式 --method 原样尊重；未指定时按媒体类型自动选。
    照片/音频页面 → harvest 专用线；文件（直链或页面）→ files 专用线；
    文本（--media-type text）→ text 专用线；视频/媒体直链 → chain（原路不变）。"""
    if explicit_method:
        return explicit_method
    media_type = _detect_url_media_type(url, media_types)
    path = urllib.parse.urlparse((url or "").strip()).path.lower()
    direct_link = path.endswith(IMAGE_EXTS + AUDIO_EXTS + (".mp4", ".m4s", ".webm", ".mov", ".mkv", ".flv", ".ts"))
    if media_type == "file":
        return "files"
    if media_type == "text":
        return "text"
    if media_type in ("image", "audio") and not direct_link:
        return "harvest"
    return "chain"


def _pick_media_url(results: List[Dict[str, str]], query: str, media_type: str = "video") -> str:
    """按媒体类型挑目标页面。
    video → 原视频逻辑原样委托 _pick_video_url（视频电路不动）；
    image/audio → 只挑对应类型结果（图片站/音乐站/直链扩展名），
    明确跳过视频站和搜索引擎跳转壳，防止图片/音频需求误开视频页。
    file → 只挑文件直链（zip/pdf/docx 等扩展名结尾）。"""
    if media_type == "video":
        return _pick_video_url(results, query)

    if media_type == "file":
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            for cand in (_decode_redirect_url(url), url):
                if cand and urllib.parse.urlparse(cand).path.lower().endswith(FILE_EXTS):
                    return cand
        return ""

    if media_type == "text":
        # 文本：挑文章页——跳过视频站/图片站/音乐站；优先非跳转壳（解不出真实地址的壳链接只当兜底）
        def _host_of(u):
            return urllib.parse.urlparse(u).netloc.lower()

        fallback = ""
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            cand = _decode_redirect_url(url) or url
            host = _host_of(cand)
            if any(vh in host for vh in VIDEO_LIKE_HOSTS):
                continue
            if any(h in host for h in IMAGE_LIKE_HOSTS) or any(h in host for h in AUDIO_LIKE_HOSTS):
                continue
            # 文件直链（zip/pdf 等）是 file 电路的目标，文本电路跳过
            if urllib.parse.urlparse(cand).path.lower().endswith(FILE_EXTS):
                continue
            if not fallback:
                fallback = cand
            if cand == url and any(rh in host for rh in SEARCH_REDIRECT_HOSTS):
                continue
            return cand
        return fallback

    hosts = IMAGE_LIKE_HOSTS if media_type == "image" else AUDIO_LIKE_HOSTS
    exts = IMAGE_EXTS if media_type == "image" else AUDIO_EXTS

    def _host_of(u: str) -> str:
        return urllib.parse.urlparse(u).netloc.lower()

    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        for cand in (_decode_redirect_url(url), url):
            if not cand:
                continue
            if any(h in _host_of(cand) for h in hosts):
                return cand
            if urllib.parse.urlparse(cand).path.lower().endswith(exts):
                return cand
    return ""


def _baidu_image_search_url(query: str) -> str:
    """构造百度图片搜索页 URL。图片电路的外援：没有通用的图片搜索下载库，
    就像视频借力 yt-dlp 一样，图片借力百度图片站直接导航收割。"""
    return "https://image.baidu.com/search/index?tn=baiduimage&word=" + urllib.parse.quote(query)


def _search_first_media_url(
    query: str, max_results: int, media_type: str = "video", safe: bool = False
) -> str:
    """搜索并按媒体类型挑目标。
    video：原两级引擎逻辑（国内优先→通用兜底），行为不变；
    image：结果里没图片类链接时直奔百度图片搜索页（不再误开视频页）；
    audio：没挑到就换关键词(+mp3)重搜一次，再没有如实返回空。"""
    # Import lazily so this script can still show --help even if search_browser
    # has issues.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from search_browser import run_search

    # 国内优先：与 search_browser.DOMESTIC_FIRST 同口径（搜狗/360/百度/必应，不含 DDG 防超时）。
    domestic = ["sogou", "so360", "baidu", "bing"]

    if media_type == "video":
        data = run_search(query, max_results, domestic, safe=safe)
        url = _pick_media_url(data.get("results", []), query, "video")
        if url:
            return url
        # 国内引擎没找到时再退回通用引擎组合。
        from search_browser import _resolve_engines
        data = run_search(query, max_results, _resolve_engines("", "general"), safe=safe)
        return _pick_media_url(data.get("results", []), query, "video")

    if media_type == "image":
        data = run_search(query, max_results, domestic, safe=safe)
        url = _pick_media_url(data.get("results", []), query, "image")
        if url:
            return url
        # 搜索结果里没有图片类链接：直接导航百度图片搜索页再收割
        return _baidu_image_search_url(query)

    if media_type == "file":
        # 文件电路：先原词挑文件直链，挑不到换"关键词 下载"重搜一次
        for q in (query, f"{query} 下载"):
            data = run_search(q, max_results, domestic, safe=safe)
            url = _pick_media_url(data.get("results", []), query, "file")
            if url:
                return url
        return ""

    if media_type == "text":
        # 文本电路：挑第一个非视频站的结果（文章页优先，跳过视频站和跳转壳）
        data = run_search(query, max_results, domestic, safe=safe)
        url = _pick_media_url(data.get("results", []), query, "text")
        return url

    # audio：先按原词挑，挑不到换 "关键词 mp3" 重搜（只认音乐站/音频直链）
    for q in (query, f"{query} mp3"):
        data = run_search(q, max_results, domestic, safe=safe)
        url = _pick_media_url(data.get("results", []), query, "audio")
        if url:
            return url
    return ""


def _trigger_lazy_media(page):
    """Force lazy-loaded images/media to start real requests."""
    try:
        page.evaluate(
            """
            () => {
                const imgs = document.querySelectorAll('img[data-src], img[data-original], img[data-actualsrc], img[data-lazy-src]');
                imgs.forEach(img => {
                    const src = img.dataset.src || img.dataset.original || img.dataset.actualsrc || img.dataset.lazySrc;
                    if (src && !img.src.startsWith('data:')) img.src = src;
                });
                window.scrollTo(0, document.body.scrollHeight);
            }
            """
        )
    except Exception:
        pass


def _auto_play_videos(page):
    """Try to autoplay muted videos so MSE/segments start downloading."""
    try:
        page.evaluate(
            """
            () => {
                document.querySelectorAll('video, audio').forEach(el => {
                    el.muted = true;
                    el.play().catch(() => {});
                });
            }
            """
        )
    except Exception:
        pass


def _url_group_key(url: str) -> str:
    """分段分组键：scheme://host/目录路径。同一视频的分段共享目录前缀，
    推荐位视频来自不同目录，靠这个把正片和垃圾分开。"""
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        return f"{parsed.netloc.lower()}{directory}"
    except Exception:
        return url


def _merge_segments(saved: List[Dict], output_dir: Path, keep_segments: bool = False, safe: bool = False) -> Tuple[List[Dict], Dict]:
    """验证式合并：
    1. 只取 cache-segment，按 (扩展名, URL目录) 分组——正片/音频/推荐位天然分家；
    2. ffprobe 可用时剔除异分辨率（推荐位竖屏小段）与 <0.5s 残段；
    3. 每组按到达顺序拼接，ffmpeg 解码验证真实时长，<3s 或解码失败即弃；
    4. 多组通过时取真实时长最长的一组为正片；
    5. 无 ffmpeg 时只合并体量最大组并明确标注 unverified。
    返回 (merged_list, cleanup_info)。"""
    seg_items = [i for i in saved if i.get("kind") == "cache-segment"]
    cleanup = {"removed_segments": 0, "kept_segments": 0}
    if not seg_items:
        return [], cleanup

    # ---- 分组 ----
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for item in seg_items:
        ext = Path(item.get("path", "")).suffix.lower()
        key = (ext, _url_group_key(item.get("url", "")))
        groups.setdefault(key, []).append(item)

    # 弃掉总量的<5% 的碎组（范围请求残片/推荐位）
    total_bytes = sum(i.get("size", 0) for i in seg_items)
    candidates = []
    for key, items in groups.items():
        group_bytes = sum(i.get("size", 0) for i in items)
        if len(items) >= 2 and (total_bytes == 0 or group_bytes / total_bytes >= 0.05):
            candidates.append((group_bytes, key, items))
    if not candidates:
        return [], cleanup
    candidates.sort(key=lambda x: x[0], reverse=True)
    has_ffmpeg = _ffmpeg_path() is not None
    # 安全模式：合并产物同样受 2GB 上限（分段总和超标就不拼）
    if safe:
        candidates = [c for c in candidates if c[0] <= SAFE_MAX_FILE_BYTES]

    # ---- 逐组合并 + 验证（最多试前3大组） ----
    results = []
    for group_bytes, (ext, gkey), items in candidates[:3]:
        items.sort(key=lambda x: x.get("seq", 0))
        # ffprobe 剔除异分辨率/超短残段（每段只探测一次，缓存 info 复用）
        if _ffprobe_path():
            seg_infos = {i["path"]: _ffprobe_info(i.get("path", "")) for i in items}
            dominant_res = None
            res_votes: Dict[Tuple[int, int], int] = {}
            for i in items:
                res = _probe_resolution(seg_infos.get(i["path"]))
                if res:
                    res_votes[res] = res_votes.get(res, 0) + 1
            if res_votes:
                dominant_res = max(res_votes, key=res_votes.get)
            filtered = []
            for i in items:
                info = seg_infos.get(i["path"])
                res = _probe_resolution(info)
                if dominant_res and res and res != dominant_res:
                    continue  # 推荐位竖屏小段等异分辨率垃圾
                dur = None
                if info and info.get("format", {}).get("duration"):
                    try:
                        dur = float(info["format"]["duration"])
                    except Exception:
                        dur = None
                if dur is not None and dur < 0.5:
                    continue  # 范围请求残片
                filtered.append(i)
            if len(filtered) >= 2:
                items = filtered
        if len(items) < 2:
            continue

        out_path = output_dir / f"merged_{int(time.time())}_{len(items)}seg{ext}"
        try:
            with open(out_path, "wb") as f:
                for i in items:
                    f.write(Path(i["path"]).read_bytes())
        except Exception as exc:
            sys.stderr.write(f"[merge-segments] error: {exc}\n")
            continue

        entry = {
            "url": items[0].get("url", ""),
            "path": str(out_path),
            "content_type": "",
            "size": out_path.stat().st_size,
            "kind": "merged-segment",
            "ext": ext,
            "segments": len(items),
            "group_bytes": group_bytes,
        }
        if has_ffmpeg:
            real_dur = _decoded_duration(out_path)
            if real_dur is None or real_dur < 3:
                # 解码失败或真实时长过短 → 不可信拼接，直接弃
                try:
                    out_path.unlink()
                except Exception:
                    pass
                sys.stderr.write(
                    f"[merge-segments] 丢弃 {out_path.name}: 解码验证失败或时长 {real_dur}s < 3s\n"
                )
                continue
            entry["verified_duration_sec"] = round(real_dur, 2)
            entry["unverified"] = False
        else:
            entry["unverified"] = True
            entry["note"] = "无 ffmpeg，未做解码验证，文件可能不可播"
        results.append(entry)

    if not results:
        return [], cleanup

    # 多组通过验证 → 真实时长最长的是正片，其余降级为候选
    results.sort(key=lambda e: e.get("verified_duration_sec", e.get("size", 0)), reverse=True)
    main = results[0]
    for extra in results[1:]:
        extra["kind"] = "merged-segment-candidate"

    # ---- 清理：合并出可信正片后删除原始分段 ----
    if not keep_segments and not main.get("unverified"):
        removed = 0
        for i in seg_items:
            try:
                p = Path(i.get("path", ""))
                if p.exists():
                    p.unlink()
                    removed += 1
            except Exception:
                pass
        seg_dir = output_dir / "cache_segments"
        try:
            if seg_dir.exists() and not any(seg_dir.iterdir()):
                seg_dir.rmdir()
        except Exception:
            pass
        cleanup["removed_segments"] = removed
    cleanup["kept_segments"] = len(seg_items) - cleanup["removed_segments"]
    return [main] + results[1:], cleanup


def _has_video_or_audio(saved: List[Dict]) -> bool:
    for item in saved:
        path = item.get("path", "").lower()
        ct = item.get("content_type", "").lower()
        if ct.startswith(("video/", "audio/")):
            return True
        if path.endswith((".mp4", ".webm", ".mkv", ".mov", ".m4v", ".m4s", ".ts", ".mp3", ".m4a", ".aac", ".wav", ".flac")):
            return True
    return False


def _capture_blob_media(page, output_dir: Path, safe: bool = False) -> List[Dict]:
    """Best-effort capture of blob:/MSE media through the page itself.
    每个元素的 fetch 用 Promise.race 限时，整体限时，防止 evaluate 永久挂死。"""
    try:
        items = page.evaluate(
            """
            async () => {
                const withTimeout = (p, ms) => Promise.race([
                    p,
                    new Promise(r => setTimeout(() => r(null), ms))
                ]);
                const deadline = Date.now() + 15000;  // 整体硬上限 15s
                const out = [];
                const els = [...document.querySelectorAll('video, audio')];
                for (const el of els) {
                    if (Date.now() > deadline) break;
                    const src = el.currentSrc || el.src;
                    if (!src || !src.startsWith('blob:')) continue;
                    try {
                        const resp = await withTimeout(fetch(src), 8000);
                        if (!resp) continue;
                        const buf = await withTimeout(resp.arrayBuffer(), 8000);
                        if (!buf) continue;
                        const bytes = new Uint8Array(buf);
                        if (bytes.length > 100 * 1024 * 1024) continue;
                        let binary = '';
                        const chunk = 0x8000;
                        for (let i = 0; i < bytes.length; i += chunk) {
                            if (Date.now() > deadline) { binary = null; break; }
                            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                        }
                        if (binary === null) continue;
                        out.push({
                            src: src,
                            b64: btoa(binary),
                            size: bytes.length,
                            type: resp.headers.get('content-type') || el.type || 'video/mp4'
                        });
                    } catch (e) {}
                }
                return out;
            }
            """
        )
    except Exception as exc:
        sys.stderr.write(f"[blob-save] error: {exc}\n")
        return []

    import base64
    saved = []
    for idx, item in enumerate(items or []):
        b64 = item.get("b64")
        size = item.get("size", 0)
        if not b64 or size < 1024 or size > 100 * 1024 * 1024:
            continue
        try:
            data = base64.b64decode(b64)
        except Exception:
            continue
        ext = _ext_from_content_type(item.get("type", "")) or ".bin"
        # 安全模式：blob 产物也要过白名单（.bin 残片默认就被挡）
        if safe and _safe_save_reason(f"blob{ext}", len(data)):
            continue
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"blob_{int(time.time())}_{idx:03d}{ext}"
        path.write_bytes(data)
        saved.append(
            {
                "url": item.get("src", "blob:"),
                "path": str(path),
                "content_type": item.get("type", ""),
                "size": len(data),
                "kind": "blob",
            }
        )
    return saved


# ---------- 缓存方式3：DOM 收割 + 页面上下文下载 ----------
# 网络嗅探漏掉的媒体在这里补：懒加载前未请求的图、防热链的音频、
# 接口返回后才渲染的封面、藏在 script JSON 里的直链（抖音 _ROUTER_DATA 等）。
# 下载走页面上下文 fetch（带 cookie/referer），比脚本裸 HTTP 更难被拒。

HARVEST_JS = """
() => {
    const out = [];
    const push = (u, tag, kind) => {
        if (u && /^https?:/.test(u)) out.push({url: u, tag: tag, kind: kind});
    };
    document.querySelectorAll('img').forEach(el => {
        push(el.currentSrc || el.src, 'img', 'image');
        ['src', 'original', 'actualsrc', 'lazySrc'].forEach(k => push(el.dataset ? el.dataset[k] : '', 'img-' + k, 'image'));
        if (el.srcset) el.srcset.split(',').forEach(p => push(p.trim().split(' ')[0], 'img-srcset', 'image'));
    });
    document.querySelectorAll('video').forEach(el => {
        push(el.poster, 'video-poster', 'image');
        const s = el.currentSrc || el.src || '';
        if (!s.startsWith('blob:')) push(s, 'video', 'video');
        el.querySelectorAll('source').forEach(x => push(x.src, 'video-source', 'video'));
    });
    document.querySelectorAll('audio').forEach(el => {
        const s = el.currentSrc || el.src || '';
        if (!s.startsWith('blob:')) push(s, 'audio', 'audio');
        el.querySelectorAll('source').forEach(x => push(x.src, 'audio-source', 'audio'));
    });
    // CSS 背景图（画廊站常用）
    document.querySelectorAll('*').forEach(el => {
        try {
            const bg = getComputedStyle(el).backgroundImage;
            if (bg && bg.includes('url(')) {
                const m = bg.match(/url\\(["']?(https?:[^"')]+)["']?\\)/);
                if (m) push(m[1], 'css-bg', 'image');
            }
        } catch (e) {}
    });
    // og/twitter 元数据（封面/预览大图）
    document.querySelectorAll('meta[property],meta[name]').forEach(m => {
        const k = (m.getAttribute('property') || m.getAttribute('name') || '').toLowerCase();
        const c = (m.content || '').trim();
        if (!c || !/^https?:/.test(c)) return;
        if (k === 'og:image' || k === 'twitter:image' || k === 'og:image:secure_url') push(c, 'meta-image', 'image');
        if (k === 'og:video' || k === 'og:video:url' || k === 'og:video:secure_url') push(c, 'meta-video', 'video');
        if (k === 'og:audio' || k === 'og:audio:secure_url') push(c, 'meta-audio', 'audio');
    });
    return out;
}
"""


def _page_fetch(page, url: str) -> Optional[Dict]:
    """在页面上下文里 fetch 资源（带 cookie/referer），返回 {b64,size,ct} 或 None。"""
    try:
        return page.evaluate(
            """
            async (u) => {
                const t = (p, ms) => Promise.race([p, new Promise(r => setTimeout(() => r(null), ms))]);
                try {
                    const r = await t(fetch(u, {credentials: 'include'}), 10000);
                    if (!r || !r.ok) return null;
                    const buf = await t(r.arrayBuffer(), 10000);
                    if (!buf) return null;
                    const bytes = new Uint8Array(buf);
                    if (bytes.length > 80 * 1024 * 1024) return null;
                    let binary = '';
                    for (let i = 0; i < bytes.length; i += 0x8000)
                        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
                    return {b64: btoa(binary), size: bytes.length, ct: r.headers.get('content-type') || ''};
                } catch (e) { return null; }
            }
            """,
            url,
        )
    except Exception:
        return None


def _http_fetch_media(url: str, page_url: str = "", timeout: int = 20) -> Optional[Dict]:
    """脚本侧 HTTP 直下媒体（收割降级路线）：页面上下文 fetch 被跨域 CORS 拦时用。
    带浏览器 UA + 来源页 Referer（防热链基本够用），返回 {b64,size,ct} 或 None。"""
    import base64

    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if page_url:
            parsed = urllib.parse.urlparse(page_url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
        if not data or len(data) > 80 * 1024 * 1024:
            return None
        return {"b64": base64.b64encode(data).decode("ascii"), "size": len(data), "ct": ct}
    except Exception:
        return None


def _extract_shell_redirect(html_text: str) -> Optional[str]:
    """从跳转壳页 HTML 提取真实目标 URL（分享链接常见：api.xxx/share?link_id= 返回壳页）。
    识别 meta refresh / JS location 跳转 / redirect 类 JSON 字段 / og:url。拿不到返回 None。"""
    if not html_text:
        return None
    # meta refresh: <meta http-equiv="refresh" content="0;url=xxx">
    m = re.search(
        r'http-equiv=["\']?refresh["\']?[^>]*content=["\']?\d+;\s*url=([^"\'>\s]+)',
        html_text, re.I,
    )
    if m:
        return m.group(1).replace("&amp;", "&")
    # JS 跳转: location.href='x' / location.replace("x")
    m = re.search(r'location\.(?:href|replace)\s*[=(]\s*["\'](https?://[^"\']+)["\']', html_text)
    if m:
        return m.group(1).replace("&amp;", "&")
    # redirect 类 JSON 字段（redirect_data/share 数据里常带真实链接）
    for key in ("redirect", "redirect_url", "redirectUrl", "redirect_data",
                "link_url", "linkUrl", "share_url", "shareUrl", "jump_url", "target_url", "web_url"):
        m = re.search(key + r'["\']?\s*[:=]\s*["\'](https?://[^"\']+)["\']', html_text)
        if m:
            return m.group(1).replace("&amp;", "&")
    # og:url / canonical
    m = re.search(r'(?:property=["\']og:url["\']|rel=["\']canonical["\'])[^>]*(?:content|href)=["\'](https?://[^"\']+)["\']', html_text, re.I)
    if not m:
        m = re.search(r'(?:content|href)=["\'](https?://[^"\']+)["\'][^>]*(?:property=["\']og:url["\']|rel=["\']canonical["\'])', html_text, re.I)
    if m:
        return m.group(1).replace("&amp;", "&")
    return None


def _is_split_stream_fragment(url: str) -> bool:
    """m4s/ts 是视频站 MSE 分离流分段（视频轨/音频轨拆成两条流）。
    单独抓一条就是"只有画面没声音/只有声音没画面"的残件。"""
    return urllib.parse.urlparse((url or "").split("?")[0]).path.lower().endswith((".m4s", ".ts"))


SHELL_BODY_TEXT_LIMIT = 600  # 正文短于这个数且带跳转标记 → 判为落地页壳页


def _goto_pierce_shell(page, url: str, max_hops: int = 3) -> str:
    """落地页穿透（Landing Page Bypass）：调用方 goto 后，若当前页是壳页
    （正文极短 + 带跳转标记 meta refresh/JS 跳转/redirect_data/og:url），
    主动跟进到真实内容页，最多 max_hops 跳，visited 防循环。返回最终停留 URL。

    安全边界：只在"正文 < 600 字符"时才跟——正常文章/画廊页正文丰富，
    即使带 og:url/canonical/广告 meta refresh 也不会被误当壳页跳走。"""
    visited = {url}
    current = url
    for _ in range(max_hops):
        try:
            target = _extract_shell_redirect(page.content())
        except Exception:
            break
        if not target or target in visited:
            break
        try:
            body_len = page.evaluate(
                "() => document.body ? (document.body.innerText || '').length : 0"
            ) or 0
        except Exception:
            body_len = 0
        if body_len >= SHELL_BODY_TEXT_LIMIT:
            break  # 正文丰富：真页面，不是壳
        sys.stderr.write(f"[pierce] 跟进落地页壳: {target[:120]}\n")
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            sys.stderr.write(f"[pierce] 跟进失败: {exc}\n")
            break
        visited.add(target)
        current = target
    return current


def _wait_for_render(page, min_text: int = 50, max_wait_sec: float = 10.0) -> bool:
    """JS 渲染页自适应等待：SPA 在 domcontentloaded 后内容可能还没挂载（空页面），
    直接收割/提取只能拿到空白。轮询到页面真的渲染出东西为止：
    - 正文 ≥ min_text 字符，或媒体元素 ≥3 个（图库/播放器页正文少）即认为就绪；
    - 每轮 800ms 并滚动触发懒加载；静态页首轮即通过，零额外耗时；
    - 超时返回 False（真空白页），调用方按原逻辑继续（退 chain 兜底/如实报错）。"""
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        try:
            n = page.evaluate(
                "() => document.body ? (document.body.innerText || '').trim().length : 0"
            ) or 0
        except Exception:
            n = 0
        if n >= min_text:
            return True
        try:
            media = page.evaluate(
                "() => document.querySelectorAll('img,video,audio,source').length"
            ) or 0
        except Exception:
            media = 0
        if media >= 3:
            return True
        try:
            page.wait_for_timeout(800)
            page.mouse.wheel(0, 1200)
        except Exception:
            pass
    return False


def _harvest_lazy_all(page, url: str, output_dir: Path, allowed_kinds: set, seen: set,
                      save_junk: bool, safe: bool = False,
                      max_rounds: int = 30, stall_limit: int = 4,
                      step_px: int = 1400, pause_ms: int = 600,
                      max_total: int = 200) -> List[Dict]:
    """迭代滚动收割：逐段滚动→等懒加载挂载→收割本轮新图，直到收敛。

    修 SPA 图集抓不全（小黑盒这类）：懒加载图集初始只挂视口附近几张，
    旧逻辑"跳到底+固定滚3次+一次性收割"拿不到中段图片——
    IntersectionObserver 型懒加载必须让元素逐段经过视口才触发请求。
    收敛条件（满足其一）：滚到底且本轮无新增 / 连续 stall_limit 轮无新增 / 达轮数上限。
    每轮收割增量入库（seen 去重防重复下载），总收录 max_total 封顶防失控。"""
    saved_all: List[Dict] = []
    stall = 0
    for _ in range(max_rounds):
        if len(saved_all) >= max_total:
            break
        _trigger_lazy_media(page)
        batch = _harvest_dom_media(page, url, output_dir, allowed_kinds, seen,
                                   save_junk, limit=min(120, max_total - len(saved_all)),
                                   safe=safe)
        saved_all.extend(batch)
        stall = 0 if batch else stall + 1
        # 逐段滚动：模拟人翻页，让各段图片依次进入视口触发懒加载
        try:
            y = page.evaluate("window.scrollY || document.documentElement.scrollTop || 0") or 0
            ph = page.evaluate(
                "Math.max(document.documentElement.scrollHeight,"
                "document.body ? document.body.scrollHeight : 0)"
            ) or 0
            vh = page.evaluate("window.innerHeight") or 0
            page.evaluate(f"window.scrollTo(0, {y + step_px})")
            page.wait_for_timeout(pause_ms)
            y2 = page.evaluate("window.scrollY || document.documentElement.scrollTop || 0") or 0
        except Exception:
            break
        # 到底（位置不再前进或已贴底）且无新货 → 收敛；中部连续 stall_limit 轮空 → 也收敛
        at_bottom = (y2 + vh) >= (ph - 80) or y2 <= y
        if (at_bottom and stall >= 1) or stall >= stall_limit:
            break
    # 尾轮：停稳后再收一次（最后一段新挂载的图）
    try:
        page.wait_for_timeout(400)
        _trigger_lazy_media(page)
        tail = _harvest_dom_media(page, url, output_dir, allowed_kinds, seen,
                                  save_junk, limit=min(120, max(0, max_total - len(saved_all))),
                                  safe=safe)
        saved_all.extend(tail)
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    return saved_all


def _harvest_dom_media(
    page, url: str, output_dir: Path, allowed_kinds: set, seen: set, save_junk: bool,
    limit: int = 40, safe: bool = False,
) -> List[Dict]:
    """收集页面里所有媒体 URL（DOM/元数据/内嵌JSON），用页面上下文逐个下载。
    与网络嗅探互补：嗅探抓"浏览器请求过的"，收割抓"页面上存在但可能没请求/请求被拦的"。"""
    import base64

    candidates: List[Dict] = []
    try:
        dom_items = page.evaluate(HARVEST_JS) or []
    except Exception:
        dom_items = []
    for it in dom_items:
        candidates.append((it.get("url", ""), it.get("tag", "dom"), it.get("kind", "")))

    # 内嵌 JSON：抖音/B站把媒体直链藏在 script 变量里
    try:
        script_text = page.evaluate(
            "() => [...document.querySelectorAll('script')].map(s => s.textContent || '').join('\\n')"
        )
    except Exception:
        script_text = ""
    if script_text:
        urls = re.findall(
            r"https?://[^\s\"'\\<>]+?\.(?:mp4|m4s|mp3|m4a|aac|webm|mov|jpg|jpeg|png|webp)(?:\?[^\s\"'\\<>]*)?",
            script_text,
        )
        for u in urls[:120]:
            candidates.append((u, "script-json", _media_kind(u, "")))

    saved = []
    fetched = 0
    for u, tag, kind_hint in candidates:
        if fetched >= limit:
            break
        if not u:
            continue
        # 分离流防护：纯图片/纯音频收割时跳过 m4s/ts 分段——那是视频站拆流的
        # 半条流（伴音轨/画面轨），单独存就是残件。要完整视频请走视频路（chain）。
        if allowed_kinds in ({"image"}, {"audio"}) and _is_split_stream_fragment(u):
            continue
        kind = _media_kind(u, "") or kind_hint
        if kind not in allowed_kinds:
            continue
        if u in seen or u.split("?")[0] in seen:
            continue
        seen.add(u)
        item = _page_fetch(page, u)
        if not item:
            # 页面 fetch 被拦（跨域 CDN 无 CORS 头，如小黑盒 cdn.max-c.com）→
            # 降级脚本侧直连：带浏览器 UA + 页面 Referer，公开 CDN 基本都放行
            item = _http_fetch_media(u, page_url=url)
        if not item:
            continue
        data = base64.b64decode(item["b64"])
        if len(data) < 2048:
            continue
        ct = item.get("ct", "")
        # 防污染：URL 无媒体扩展名且响应是网页/接口（html/json/plain）→ 不是媒体本体，
        # 禁止落盘成 .bin（此前壳页 HTML、视频页 HTML 都这么混进产物）。
        url_ext = Path(urllib.parse.urlparse(u).path).suffix.lower()
        if url_ext not in MEDIA_EXTENSIONS and ct.split(";")[0].strip().lower() in (
            "text/html", "application/xhtml+xml", "text/plain", "application/json",
        ):
            continue
        kind = _media_kind(u, ct) or kind
        if kind not in allowed_kinds:
            continue
        if kind == "image" and _is_junk_resource(u, ct, len(data), size_strict=False):
            continue
        # 安全模式：落盘白名单 + 大小上限（URL 里的扩展名必须过白名单才落盘）
        if safe and _safe_save_reason(_safe_filename(u, ct, fetched), len(data)):
            continue
        path = _save_bytes(data, output_dir, u, ct, 10000 + fetched)
        saved.append(
            {
                "url": u,
                "path": str(path),
                "content_type": ct,
                "size": len(data),
                "kind": "pagefetch",
                "via": tag,
            }
        )
        fetched += 1
    return saved


def _save_page_text(page, url: str, output_dir: Path) -> Dict:
    """提取页面标题+正文文本，保存为 txt。返回 saved 条目或 {'error': ...}。"""
    try:
        title = page.title() or "page"
        body = page.inner_text("body")
    except Exception as exc:
        return {"error": str(exc)}
    body = (body or "").strip()
    if not body:
        return {"error": "page has no text content"}
    stem = re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip(" ._")[:80] or "page"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{int(time.time())}_{stem}.txt"
    content = (
        f"来源: {url}\n"
        f"标题: {title}\n"
        f"保存时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        + "=" * 40
        + "\n\n"
        + body
    )
    path.write_text(content, encoding="utf-8")
    return {
        "url": url,
        "path": str(path),
        "content_type": "text/plain",
        "size": path.stat().st_size,
        "kind": "text",
        "title": title,
    }


# ---------- 文件电路：压缩包/文档/表格/文本等非视频照片音频 ----------

FILE_LINKS_JS = """
() => {
    const exts = ['.zip','.rar','.7z','.tar','.gz','.bz2','.xz','.pdf','.doc','.docx',
                  '.xls','.xlsx','.ppt','.pptx','.txt','.csv','.md','.epub','.mobi',
                  '.apk','.msi','.exe','.iso','.dmg'];
    const out = [];
    document.querySelectorAll('a[href]').forEach(a => {
        try {
            const u = new URL(a.href, location.href);
            if (u.protocol !== 'http:' && u.protocol !== 'https:') return;
            const p = u.pathname.toLowerCase();
            if (exts.some(e => p.endsWith(e)) && !out.includes(u.href)) out.push(u.href);
        } catch (e) {}
    });
    return out;
}
"""


def _filename_from_disposition(resp, url: str) -> str:
    """从 Content-Disposition 提取文件名（支持 filename*=UTF-8'' 和 filename="），
    拿不到就用 URL 最后一段。"""
    cd = ""
    try:
        cd = resp.headers.get("Content-Disposition", "") or ""
    except Exception:
        pass
    if cd:
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I)
        if m:
            try:
                return urllib.parse.unquote(m.group(1).strip().strip('"'))
            except Exception:
                pass
        m = re.search(r'filename="?([^";]+)"?', cd, re.I)
        if m:
            name = m.group(1).strip()
            if name:
                return name
    base = os.path.basename(urllib.parse.urlparse(url).path) or "file"
    return base


def _file_direct_download(url: str, dest_dir: Path, safe: bool = False, referer: str = "") -> Optional[Dict]:
    """HTTP 流式直链下载（8MB 分块，不吃内存）。返回 saved 条目或 None（失败/是网页）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        **({"Referer": referer} if referer else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            ct = (resp.headers.get("Content-Type", "") or "").lower().split(";")[0].strip()
            # 网页不是文件本体（防壳页/错误页存成假文件）
            if ct in ("text/html", "application/xhtml+xml"):
                return None
            fname = _filename_from_disposition(resp, url)
            fname = re.sub(r'[\\/:*?"<>|]+', "_", fname).strip(" .") or "file"
            # 安全模式：可执行文件白名单拦截（下载前就挡）
            if safe and _safe_save_reason(fname, 0):
                sys.stderr.write(f"[safe-block] 文件下载拒绝: {fname}\n")
                return None
            dest_dir.mkdir(parents=True, exist_ok=True)
            path = dest_dir / fname
            size = 0
            with open(path, "wb") as f:
                while True:
                    chunk = resp.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    size += len(chunk)
            if size < 64:
                path.unlink(missing_ok=True)
                return None
            return {"url": url, "path": str(path), "size": size, "kind": "file",
                    "content_type": ct, "via": "direct"}
    except Exception as exc:
        sys.stderr.write(f"[file-dl] error: {exc} url={url[:120]}\n")
        return None


def _zip_bundle(folder: Path, output_dir: Path) -> Optional[str]:
    """把文件夹打包成单个 zip（用户的'合并'选项：多文件→一个压缩包）。"""
    import zipfile

    files = sorted(p for p in folder.rglob("*") if p.is_file())
    if not files:
        return None
    bundle = output_dir / f"{folder.name}.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(folder))
    return str(bundle)


# ---------- 点击式下载兜底（--click-download，默认关闭）----------
# 场景：分享页"点击下载"按钮跳转 APP/JS 处理，页面里没有文件直链。
# 策略（按序）：UA 伪装重试 → 找下载按钮点击 + 网络层嗅探真文件响应
# （Content-Type 是文件本体/URL 以文件扩展名结尾）→ expect_download 兜底
# → scheme 参数解码。抓到真 URL 后 HTTP 流式直下。

CLICK_DOWNLOAD_FILE_TYPES = (
    "application/vnd.android.package-archive",  # APK
    "application/zip", "application/x-zip-compressed",
    "application/x-rar-compressed", "application/vnd.rar",
    "application/x-7z-compressed",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",  # 通用二进制（很多站用它发 APK/zip）
)

DOWNLOAD_BUTTON_TEXTS = ("下载", "立即下载", "点击下载", "免费下载", "安装",
                         "download", "get apk", "get the app", "install")

# APP 商店域名：抓到这些链接说明是"引流装APP"陷阱——按钮抓到的"下载链接"
# 其实是下载那个 APP 本身（跳应用商店），不是用户要的文件。绝不存为成果。
APP_STORE_HOSTS = (
    "apps.apple.com", "appstore.com", "itunes.apple.com",
    "play.google.com", "market.android.com",
    "app.mi.com", "appgallery.huawei.com", "appgallery.cloud.huawei.com",
    "myapp.com", "android.myapp.com",
    "app.baidu.com", "shouji.baidu.com",
    "zhushou.360.cn", "app.360.cn",
    "wandoujia.com", "ppzhushou.com", "25pp.com",
    "appgallery", "samsungapps.com",
    "appgallery.market.xiaomi.com",
)


def _is_app_store_url(url: str) -> bool:
    """判定 URL 是否 APP 商店/引流装APP页面。"""
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(h in host for h in APP_STORE_HOSTS)


def _decode_scheme_target(href: str) -> str:
    """从 scheme 跳转链接里解出真 URL（theirapp://dl?url=https%3A%2F%2F...）。
    解不出 https 目标就返回空串。"""
    if not href or "://" not in href:
        return ""
    try:
        qs = urllib.parse.urlparse(href).query or href.split("?", 1)[-1]
        params = urllib.parse.parse_qs(qs, keep_blank_values=True)
    except Exception:
        return ""
    for key in ("url", "download", "download_url", "downloadUrl", "link", "target", "redirect"):
        if key in params:
            cand = params[key][0]
            cand = urllib.parse.unquote(cand)
            if cand.startswith(("http://", "https://")):
                return cand
    return ""


def _try_click_download(page, url: str, output_dir: Path, safe: bool = False) -> tuple:
    """点击式下载兜底（严格逐级降级链）：路线N失败自动降级路线N+1，拿到文件立即返回。
    返回 (saved_list, saw_app_funnel)：saw_app_funnel=True 表示抓到的全是 APP 商店
    引流链接（"下载"按钮其实是骗你装APP），该页面网页端无真文件，如实报告 app_only。
    路线1 按钮直链/scheme解码+全页扫 → 路线2 点击+网络嗅探(含新标签页) →
    路线3 原生下载事件 → 路线4 UA伪装重试 → 路线5 页面上下文fetch重试。"""
    saved: List[Dict] = []
    saw_app_funnel = False  # 见到过商店引流链接（最终没成果时用于 app_only 判定）

    def _note_app_funnel(u: str):
        nonlocal saw_app_funnel
        if _is_app_store_url(u):
            saw_app_funnel = True

    # ---------- 收集下载按钮（每级都要用）----------
    def _collect_buttons():
        btns = []
        try:
            for sel in ("a", "button"):
                for el in page.locator(sel).all()[:80]:
                    try:
                        text = (el.inner_text(timeout=500) or "").strip().lower()
                        href = el.get_attribute("href", timeout=500) or ""
                    except Exception:
                        continue
                    if not text or len(text) > 30:
                        continue
                    if any(t in text for t in DOWNLOAD_BUTTON_TEXTS):
                        btns.append((el, text, href))
        except Exception:
            pass
        return btns

    # ---------- 全页扫描文件直链（不限下载按钮：小字"直链下载/历史版本"也抓）----------
    def _collect_page_file_links() -> List[str]:
        links = []
        try:
            links = page.evaluate(FILE_LINKS_JS) or []
        except Exception:
            links = []
        return [u for u in links if not _is_app_store_url(u)]

    buttons = _collect_buttons()

    # ---------- 路线1：按钮直链 + scheme解码 + 全页文件直链（不点击，零副作用）----------
    for _el, _text, href in buttons:
        target = ""
        if href.startswith(("http://", "https://")):
            target = href
        elif "://" in href:
            target = _decode_scheme_target(href)
        if not target:
            continue
        if _is_app_store_url(target):
            _note_app_funnel(target)
            continue  # 商店链接不是成果，跳过但记账
        item = _file_direct_download(target, output_dir, safe, referer=url)
        if item:
            item["via"] = "click-route1-link"
            saved.append(item)
    # 全页扫的文件直链也一起试（很多站把真入口藏在"直链下载"小字里）
    for u in _collect_page_file_links():
        if any(u == s.get("url") for s in saved):
            continue
        item = _file_direct_download(u, output_dir, safe, referer=url)
        if item:
            item["via"] = "click-route1-page-scan"
            saved.append(item)
    if saved:
        sys.stderr.write(f"[click] 路线1命中：直链/scheme/全页扫描拿到 {len(saved)} 个文件\n")
        return saved, saw_app_funnel

    # ---------- 路线2：程序化点击 + 网络层嗅探（含新标签页响应）----------
    captured_urls: List[tuple] = []  # (url, content_type)
    watched_pages: List = [page]    # 点击可能 window.open 新页签，新页的响应也要监听

    def _close_extra_tabs():
        """清理点击开出的多余页签（保留主 page），防页签泄漏。"""
        for p in watched_pages[1:]:
            try:
                p.close()
            except Exception:
                pass
        del watched_pages[1:]

    def on_response(resp):
        try:
            ct = (resp.headers.get("content-type", "") or "").lower().split(";")[0].strip()
            u = resp.url
            path_ext = Path(urllib.parse.urlparse(u).path).suffix.lower()
            is_file_ct = ct in CLICK_DOWNLOAD_FILE_TYPES
            is_file_ext = path_ext in FILE_EXTS and ct not in ("text/html", "application/xhtml+xml", "application/json")
            # 视频/音频也要（用户要的可能不是APK而是视频），图片不收防广告图泛滥
            is_media = (ct.startswith(("video/", "audio/"))
                        or path_ext in VIDEO_EXTS or path_ext in AUDIO_EXTS)
            if (is_file_ct or is_file_ext or is_media) and u not in [c[0] for c in captured_urls]:
                if ct == "application/octet-stream" and not path_ext:
                    return
                captured_urls.append((u, ct))
        except Exception:
            pass

    def on_new_page(new_page):
        # 点击触发 window.open：新页签里的下载请求也挂监听
        watched_pages.append(new_page)
        try:
            new_page.on("response", on_response)
        except Exception:
            pass

    def on_download(dl):
        pending_downloads.append(dl)

    pending_downloads: List = []
    try:
        page.context.on("page", on_new_page)
    except Exception:
        pass
    # 原生下载监听提前挂（context 级含新页签和主页面）：路线2点击若直接
    # 触发 Content-Disposition: attachment 下载，事件不丢失，路线3直接收割。
    # 注意只挂 context 级——再挂 page 级会让同一下载进列表两次（重复落盘）
    try:
        page.context.on("download", on_download)
    except Exception:
        pass
    page.on("response", on_response)

    clicked = 0
    for el, text, href in buttons:
        if clicked >= 5:
            break
        if _is_app_store_url(href):
            continue  # 已知商店引流按钮，不浪费点击预算
        try:
            el.click(timeout=2000)
            clicked += 1
            page.wait_for_timeout(2500)  # 等窗加长：跳转链（点击→中转→真请求）要走完
        except Exception:
            continue
    # 新标签页可能刚开还在加载，多等一拍让它发请求
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass

    for u, ct in captured_urls:
        if _is_app_store_url(u):
            _note_app_funnel(u)
            continue  # 商店响应不是成果
        item = _file_direct_download(u, output_dir, safe, referer=url)
        if item:
            item["via"] = "click-route2-sniff"
            saved.append(item)
    n_watched = len(watched_pages)
    _close_extra_tabs()
    if saved:
        sys.stderr.write(f"[click] 路线2命中：网络嗅探拿到 {len(saved)} 个文件（点击{clicked}次，监听{n_watched}页）\n")
        return saved, saw_app_funnel

    # ---------- 路线3：原生下载事件（Content-Disposition: attachment）----------
    # 监听已在路线2前挂好，先收割路线2点击积累的下载事件；
    # 没有就重新收集按钮补点一轮（路线2的点击可能已导致页面导航，旧句柄全失效）
    if not pending_downloads:
        for el, text, href in _collect_buttons()[:2]:
            if _is_app_store_url(href):
                continue
            try:
                el.click(timeout=2000)
                page.wait_for_timeout(2000)
            except Exception:
                continue
        try:
            page.wait_for_timeout(2000)  # 等下载事件冒出来
        except Exception:
            pass
    for dl in list(pending_downloads):
        try:
            fname = dl.suggested_filename or f"click_dl_{int(time.time())}"
            fname = re.sub(r'[\\/:*?"<>|]+', "_", fname)
            if safe and _safe_save_reason(fname, 0):
                dl.cancel()
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            dest = output_dir / fname
            # 重名防覆盖：两个下载同名时第二个加序号
            seq = 1
            while dest.exists():
                dest = output_dir / f"{Path(fname).stem}_{seq}{Path(fname).suffix}"
                seq += 1
            dl.save_as(str(dest))
            saved.append({"url": getattr(dl, "url", "") or "browser-download",
                          "path": str(dest), "size": dest.stat().st_size,
                          "kind": "file", "via": "click-route3-download-event"})
        except Exception:
            continue
    pending_downloads.clear()
    _close_extra_tabs()  # 下载已全部落盘，新页签里的下载对象不再被引用，可以关了
    if saved:
        sys.stderr.write(f"[click] 路线3命中：原生下载事件拿到 {len(saved)} 个文件\n")
        return saved, saw_app_funnel

    # ---------- 路线4：UA 伪装重试（换手机UA重载，路线1+2再来一轮）----------
    try:
        mobile_ua = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
        try:
            cdp = page.context.new_cdp_session(page)
            cdp.send("Network.setUserAgentOverride", {"userAgent": mobile_ua})
        except Exception:
            pass
    except Exception:
        pass
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_render(page)
        buttons = _collect_buttons()  # 手机版页面按钮可能不同
        for _el, _text, href in buttons:
            target = href if href.startswith(("http://", "https://")) else (
                _decode_scheme_target(href) if "://" in href else "")
            if not target or _is_app_store_url(target):
                if target:
                    _note_app_funnel(target)
                continue
            item = _file_direct_download(target, output_dir, safe, referer=url)
            if item:
                item["via"] = "click-route4-mobile-ua"
                saved.append(item)
        if not saved:
            captured_urls.clear()
            clicked = 0
            for el, text, href in buttons[:5]:
                if _is_app_store_url(href):
                    continue  # 商店引流按钮不浪费点击预算
                try:
                    el.click(timeout=2000)
                    clicked += 1
                    page.wait_for_timeout(2500)
                except Exception:
                    continue
            for u, ct in captured_urls:
                if _is_app_store_url(u):
                    _note_app_funnel(u)
                    continue
                item = _file_direct_download(u, output_dir, safe, referer=url)
                if item:
                    item["via"] = "click-route4-mobile-ua"
                    saved.append(item)
    except Exception:
        pass
    _close_extra_tabs()
    if saved:
        sys.stderr.write(f"[click] 路线4命中：手机UA重试拿到 {len(saved)} 个文件\n")
        return saved, saw_app_funnel

    # ---------- 路线5：页面上下文 fetch 重试（带cookie/referer，防403）----------
    for u in _collect_page_file_links()[:10]:
        item = _page_fetch_download(page, u, output_dir, safe)
        if item:
            item["via"] = "click-route5-page-fetch"
            saved.append(item)
    _close_extra_tabs()
    if saved:
        sys.stderr.write(f"[click] 路线5命中：页面上下文fetch拿到 {len(saved)} 个文件\n")
        return saved, saw_app_funnel

    # ---------- 全部失败：如实返回（saw_app_funnel 供上层报 app_only）----------
    return saved, saw_app_funnel


def _page_fetch_download(page, url: str, output_dir: Path, safe: bool = False) -> Optional[Dict]:
    """页面上下文 fetch 下载文件（带 cookie/referer，裸 HTTP 403 的站也能拿）。
    返回 saved 条目或 None。文件名从 URL/Content-Disposition 取。"""
    item = _page_fetch(page, url)
    if not item:
        return None
    import base64

    data = base64.b64decode(item["b64"])
    if len(data) < 64:
        return None
    ct = item.get("ct", "")
    if ct.split(";")[0].strip().lower() in ("text/html", "application/xhtml+xml", "application/json"):
        return None  # 网页不是文件本体
    fname = _filename_from_disposition(type("R", (), {"headers": {}})(), url)
    fname = re.sub(r'[\\/:*?"<>|]+', "_", fname).strip(" .") or "file"
    if safe and _safe_save_reason(fname, len(data)):
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / fname
    path.write_bytes(data)
    return {"url": url, "path": str(path), "size": len(data), "kind": "file",
            "content_type": ct, "via": "page-fetch"}


# ---------- 视觉线：截图 + 屏幕信息 + 鼠标控制（多模态模型适配，v1.12.0）----------
# 官方依据（api-docs.deepseek.com/guides/vision）：
#   模型 deepseek-v4-flash-vision-exp：接受图片+文本混合输入（普通 V4-Flash/Pro 传图直接报错）
#   格式 JPEG/PNG/GIF/WebP（按文件实际内容判断）；单张图片 token 计费封顶 384
#   图片传入：base64 内联（48MiB 请求体限制）/ 外部 URL（≤8192 字符, 32MiB, 60s）/ Files API（64MiB）
#   detail 等级：low=压到 512×512 更省 / original=原图 / auto=原图；单次请求最多 600 张
#   图片只能出现在 user 消息里（Chat Completions / Anthropic Messages）

VISION_MODEL_NAME = "deepseek-v4-flash-vision-exp"
VISION_MAX_IMAGE_EDGE = 8192      # 官方图片最长边上限（px），超长页面必须分段
VISION_SEGMENT_MAX_PX = 6000      # 分段截图单段高度上限（留余量，每段原始分辨率比一张巨图看得清）
VISION_DEFAULT_MAX_SCREENS = 30   # 视觉会话单次截图数上限（成本防护：每张≤384 token）

# 鼠标位置跟踪（注入页面：视觉会话里模型操作后能读到"鼠标现在在哪"）
MOUSE_TRACK_JS = """
window.__mx = 0; window.__my = 0;
document.addEventListener('mousemove', e => { window.__mx = e.clientX; window.__my = e.clientY; });
"""


def _is_vision_model(model: str) -> bool:
    """判定模型是否支持视觉（多模态）。官方目前仅 deepseek-v4-flash-vision-exp
    接受图片输入（名称含 vision），普通模型传图会直接报错。"""
    return bool(model) and "vision" in model.lower()


def _vision_api_hint(detail: str = "original") -> Dict:
    """喂给调用方 AI 的官方 API 参数提示（照官方文档拼请求用）。"""
    return {
        "model": VISION_MODEL_NAME,
        "detail": detail,                       # low=512×512 更省 token / original=原图
        "max_tokens_per_image": 384,            # 单张 token 封顶（成本估算用）
        "image_formats": ["JPEG", "PNG", "GIF", "WebP"],
        "send_as": "base64 data URL 或 Files API file_id",
        "note": "图片只能放 user 消息；本工具产出的 PNG 直接 base64 内联即可",
    }


def _screen_info(page) -> Dict:
    """屏幕/页面/鼠标信息（让视觉模型知道屏幕多大、页面多长、鼠标在哪）。"""
    try:
        info = page.evaluate(
            """() => ({
                vw: window.innerWidth, vh: window.innerHeight,
                pw: Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0),
                ph: Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0),
                dpr: window.devicePixelRatio || 1,
                mx: window.__mx || 0, my: window.__my || 0,
                sy: window.scrollY || document.documentElement.scrollTop || 0,
                ae: (document.activeElement && document.activeElement.tagName)
                      ? document.activeElement.tagName.toLowerCase()
                        + (document.activeElement.id ? '#' + document.activeElement.id : '')
                      : '',
            })"""
        ) or {}
    except Exception:
        info = {}
    return {
        "viewport": {"width": info.get("vw", 0), "height": info.get("vh", 0)},
        "page": {"width": info.get("pw", 0), "height": info.get("ph", 0)},
        "device_pixel_ratio": info.get("dpr", 1),
        "mouse": {"x": info.get("mx", 0), "y": info.get("my", 0)},
        "scroll_y": info.get("sy", 0),
        "active_element": info.get("ae", ""),
        "url": page.url,
    }


def _scroll_page_to_bottom(page, step_px: int = 1200, pause_ms: int = 500, max_steps: int = 40) -> bool:
    """逐步滚到底触发懒加载（Playwright full_page 截图不会触发懒加载，必须先滚）。"""
    try:
        for _ in range(max_steps):
            before = page.evaluate("window.scrollY")
            page.mouse.wheel(0, step_px)
            page.wait_for_timeout(pause_ms)
            after = page.evaluate("window.scrollY")
            ph = page.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
            if after <= before or after >= ph - page.evaluate("window.innerHeight"):
                break
        return True
    except Exception:
        return False


def _capture_full_page(page, output_dir: Path, prefix: str = "page",
                       segment_max_px: int = VISION_SEGMENT_MAX_PX) -> List[str]:
    """整页截图：滚底触发懒加载 → 回顶 → 全页 PNG；页面超高（>8192px 官方上限）自动
    分段（每段原始分辨率）。返回截图路径列表。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    _scroll_page_to_bottom(page)
    try:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
    except Exception:
        pass
    try:
        ph = page.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
        vw = page.evaluate("window.innerWidth")
    except Exception:
        ph, vw = 0, 0
    stamp = int(time.time())
    paths: List[str] = []
    try:
        if 0 < ph <= VISION_MAX_IMAGE_EDGE:
            # 单张全页截图（高度在官方上限内）
            p = output_dir / f"{prefix}_{stamp}_full.png"
            page.screenshot(path=str(p), full_page=True)
            paths.append(str(p))
        elif ph > VISION_MAX_IMAGE_EDGE:
            # 超高页面：按 scroll 位置分段截（clip 顶部对齐滚动点），每段原始分辨率。
            # 必须 full_page=True：不带它 clip 会被钳到视口内（首段只剩一屏），
            # 且起点超出视口直接抛 "Clipped area outside"（后续段全部丢失）
            seg = 0
            y = 0
            while y < ph and seg < 20:
                h = min(segment_max_px, ph - y)
                p = output_dir / f"{prefix}_{stamp}_seg{seg}.png"
                page.screenshot(path=str(p), full_page=True, clip={"x": 0, "y": y, "width": vw, "height": h})
                paths.append(str(p))
                y += h
                seg += 1
    except Exception:
        pass
    return paths


def _shot_viewport(page, output_dir: Path, prefix: str = "screen") -> Optional[str]:
    """当前视口截图（视觉会话每步操作后的"屏幕快照"）。
    文件名时间戳+序号双保险，同毫秒多张不互相覆盖。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    _shot_viewport._seq = getattr(_shot_viewport, "_seq", 0) + 1
    p = output_dir / f"{prefix}_{int(time.time() * 1000)}_{_shot_viewport._seq:03d}.png"
    try:
        page.screenshot(path=str(p))
        return str(p)
    except Exception:
        return None


def _screenshot_standalone(url: str, output_dir: Path, headed: bool = False, safe: bool = False) -> Dict:
    """独立截图（--screenshot 标志，配任意模式）：打开页面→渲染等待→懒加载→整页/分段截图。
    不干扰原模式逻辑，截图结果合并进 JSON。"""
    result: Dict = {"screenshots": [], "screen": {}}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["error"] = "playwright not installed"
        return result
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed, args=_browser_launch_args(safe))
            try:
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN", timezone_id="Asia/Shanghai",
                    ignore_https_errors=True,
                    **({"service_workers": "block"} if safe else {}),
                )
                context.add_init_script(STEALTH_JS + MOUSE_TRACK_JS)
                page = context.new_page()
                if safe:
                    _setup_safe_mode(context, page)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                _wait_for_render(page)
                shot_dir = output_dir / "screenshots"
                result["screenshots"] = _capture_full_page(page, shot_dir)
                result["screen"] = _screen_info(page)
            finally:
                browser.close()
    except Exception as exc:
        result["error"] = f"screenshot error: {exc}"
    return result


# 视觉会话支持的鼠标/键盘动作（官方 Vision 模型 + Playwright 鼠标 API 对齐）
VISION_ACTIONS = ("click", "dblclick", "right_click", "move", "drag", "scroll",
                  "type", "press", "focus", "elements", "goto", "back",
                  "forward", "reload", "wait", "screenshot", "eval",
                  "viewport", "shot_policy", "quit")

# 页面元素标注 JS：收集所有可见可点元素 + 视口坐标（视觉模型点前先 elements 拿准坐标，
# 不用瞎猜截图里的像素位置）
ELEMENTS_JS = """
() => {
    const out = [];
    const sel = 'a, button, input, select, textarea, [role=button], [onclick], [tabindex]';
    document.querySelectorAll(sel).forEach(el => {
        try {
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return;              // 不可见
            if (r.bottom < 0 || r.top > innerHeight) return;      // 视口外
            const style = getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return;
            const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '')
                .replace(/\\s+/g, ' ').trim().slice(0, 40);
            out.push({
                tag: el.tagName.toLowerCase(),
                text: text,
                x: Math.round(r.x + r.width / 2),   // 中心点（直接喂给 click）
                y: Math.round(r.y + r.height / 2),
                w: Math.round(r.width),
                h: Math.round(r.height),
                type: el.type || '',
                name: el.name || '',
            });
        } catch (e) {}
    });
    return out.slice(0, 60);  // 上限 60 个防刷屏
}
"""

# 验证码检测 JS：识别常见验证码特征（geetest/recaptcha/hCaptcha/国内滑块/点选）。
# 检测到只上报不绕过——自动破解验证码违法且违反站点条款，正确姿势是人工接管。
CAPTCHA_JS = """
() => {
    const found = [];
    // 1. 已知验证码 iframe / class / id 特征
    const sigs = {
        geetest: ['.geetest_holder', '.geetest_widget', 'iframe[src*="geetest"]'],
        recaptcha: ['.recaptcha-checkbox', 'iframe[src*="recaptcha"]', '.g-recaptcha'],
        hcaptcha: ['iframe[src*="hcaptcha"]', '.h-captcha'],
        slider: ['.slider', '.slide-verify', '.nc_wrapper', '[class*="captcha"]'],
        rotate: ['.rotate-captcha', '[class*="rotate"]'],
    };
    for (const [kind, sels] of Object.entries(sigs)) {
        for (const s of sels) {
            try {
                const el = document.querySelector(s);
                if (el) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 10 && r.height > 10) { found.push(kind); break; }
                }
            } catch (e) {}
        }
    }
    // 2. 验证码关键词（中文站点常见文案）
    const body = (document.body ? document.body.innerText : '').slice(0, 20000);
    if (/请拖动滑块|拖动滑块完成|向右滑动|拖动到最右侧|点击验证|请点击图中|按顺序点击/.test(body)) {
        found.push('slider_or_click_captcha');
    }
    return [...new Set(found)];
}
"""


def _free_port() -> int:
    """挑一个本机空闲端口（视觉会话给浏览器开本地 DevTools 调试口用）。"""
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _eval_watchdog_thread(debug_port: int, timeout_s: float, cancelled, fired) -> None:
    """eval 看门狗：超时仍未被取消时，经 DevTools HTTP 端点强杀全部 page target。

    为什么走 HTTP /json/close：卡死的 renderer（如 while(true)）不响应任何
    协议消息，但浏览器进程本身还活着，直接处理 /json/list 和 /json/close；
    页面一关，主线程阻塞中的 page.evaluate 立刻以 "Target closed" 解卡。
    纯 stdlib 实现，不需要 renderer 配合，也不受 Playwright 跨线程限制。"""
    if cancelled.wait(timeout_s):
        return  # eval 已按时返回，看门狗无事可做
    base = f"http://127.0.0.1:{debug_port}"
    try:
        targets = json.load(urllib.request.urlopen(f"{base}/json/list", timeout=5))
        closed = 0
        for t in targets:
            if t.get("type") == "page":
                try:
                    urllib.request.urlopen(f"{base}/json/close/{t['id']}", timeout=5)
                    closed += 1
                except Exception:
                    pass
        if closed:
            fired.set()
    except Exception:
        pass  # 看门狗自身失败不影响主流程（退化为原始行为：eval 一直阻塞）


def _vision_exec_action(page, cmd: Dict, output_dir: Path, prefix: str,
                        wait_cap_ms: int = 0, debug_port: int = 0) -> Dict:
    """执行一条视觉会话指令，返回 {ok, note}。指令格式见 _vision_route 文档。
    wait_cap_ms>0 时 wait 指令的毫秒数被钳到该值（会话剩余预算），防长 wait 拖爆总超时。
    debug_port>0 时 eval 指令带死循环看门狗（超时强杀页面，会话保活）。"""
    act = (cmd.get("action") or "").strip().lower()
    # 坐标类动作必须显式给 x/y：缺坐标默认 (0,0) 会盲点到 BODY 上还"假成功"
    if act in ("click", "dblclick", "right_click", "move") and ("x" not in cmd or "y" not in cmd):
        return {"ok": False, "note": f"{act} 缺少 x/y 坐标（视口像素；先发 elements 指令拿准坐标）"}
    x, y = cmd.get("x", 0), cmd.get("y", 0)
    try:
        if act == "click":
            page.mouse.click(x, y)
        elif act == "dblclick":
            page.mouse.dblclick(x, y)
        elif act == "right_click":
            page.mouse.click(x, y, button="right")
        elif act == "move":
            page.mouse.move(x, y)
        elif act == "drag":
            # 拖动三件套：move→down→move(steps 分步插值)→up。
            # 覆盖滑块/画布类（mousedown-mousemove-mouseup 监听）；
            # HTML5 draggable 元素（dragstart 事件）此模拟不保证触发
            if any(k not in cmd for k in ("x", "y", "to_x", "to_y")):
                return {"ok": False, "note": "drag needs 'x','y'（起点）和 'to_x','to_y'（终点，视口像素）"}
            tx, ty = int(cmd["to_x"]), int(cmd["to_y"])
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(tx, ty, steps=12)
            page.mouse.up()
            return {"ok": True, "note": f"已拖动 ({x},{y}) → ({tx},{ty})"}
        elif act == "scroll":
            page.mouse.wheel(x, cmd.get("y", 600))  # x=横向增量, y=纵向增量（正=向下）
        elif act == "type":
            text = str(cmd.get("text", ""))
            if not text:
                return {"ok": False, "note": "type 缺少 text（要输入的内容）"}
            page.keyboard.type(text, delay=30)
            return {"ok": True, "note": f"已输入 {len(text)} 个字符"}
        elif act == "press":
            page.keyboard.press(str(cmd.get("key", "Enter")))
        elif act == "focus":
            # 按 CSS 选择器聚焦元素（比裸坐标点更可靠：盲点坐标会打到 BODY 上输入失效）
            sel = str(cmd.get("selector", ""))
            if not sel:
                return {"ok": False, "note": "focus 缺少 selector（CSS 选择器，如 input[name=q]）"}
            el = page.locator(sel).first
            el.focus(timeout=3000)
            tag = el.evaluate("e => e.tagName")
            return {"ok": True, "note": f"已聚焦 {tag}（选择器 {sel}）"}
        elif act == "goto":
            target = str(cmd.get("url", ""))
            if not target:
                return {"ok": False, "note": "goto 缺少 url（要打开的网址）"}
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
            _wait_for_render(page, max_wait_sec=4.0)  # 同启动：会话内可交互，不用等满 10s
            # 懒加载滚动后回顶：视觉会话依赖视口坐标，停在页底会让 elements 坐标全错
            try:
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(300)
            except Exception:
                pass
        elif act == "back":
            page.go_back(timeout=15000)
        elif act == "forward":
            page.go_forward(timeout=15000)
        elif act == "reload":
            page.reload(wait_until="domcontentloaded", timeout=30000)
        elif act == "viewport":
            # 改视口尺寸：DeepSeek 视觉原生 800×800（超范围官方会压糊）；
            # 改完坐标基准变了，AI 需重新 elements 拿新坐标
            try:
                w, h = int(cmd.get("width", 0)), int(cmd.get("height", 0))
            except (TypeError, ValueError):
                return {"ok": False, "note": "viewport 参数需为整数"}
            if not (200 <= w <= 3840 and 200 <= h <= 3840):
                return {"ok": False, "note": "viewport 缺少 width/height（各 200-3840 px）"}
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(300)  # 等重排稳定
            return {"ok": True, "note": f"viewport 已改为 {w}×{h}（坐标基准变了，建议重新 elements）"}
        elif act == "wait":
            ms = int(cmd.get("ms", 1000))
            if wait_cap_ms > 0:
                ms = max(0, min(ms, wait_cap_ms))  # 钳到剩余预算：长 wait 拖爆总超时
            page.wait_for_timeout(ms)
        elif act == "elements":
            # 元素标注：返回视口内所有可见可点元素（tag/text/中心坐标/尺寸）。
            # 视觉模型点按钮前先 elements 拿准坐标，不用从截图里猜像素
            els = page.evaluate(ELEMENTS_JS) or []
            return {"ok": True, "note": "", "elements": els}
        elif act == "eval":
            # 防死循环卡死会话：evaluate 必须在主线程跑（Playwright sync API
            # 禁止跨线程调用），另起看门狗线程盯梢——10s 不返回就经 DevTools
            # HTTP 端点强杀页面，阻塞中的 evaluate 随即抛 "Target closed" 解卡；
            # 调用方收到 _page_dead 后重建页面，会话保活（AI 重新 goto 即可）
            import threading as _th
            js = str(cmd.get("js", "1+1"))
            cancelled, fired = _th.Event(), _th.Event()
            wt = None
            if debug_port:
                wt = _th.Thread(target=_eval_watchdog_thread,
                                args=(debug_port, 10, cancelled, fired), daemon=True)
                wt.start()
            try:
                val = page.evaluate(js)
            except Exception as exc:
                cancelled.set()
                if wt:
                    wt.join(5)
                if fired.is_set():
                    return {"ok": False, "_page_dead": True,
                            "note": "eval 超时(>10s)：疑似死循环 JS，页面已重置（会话保留，请重新 goto）"}
                return {"ok": False, "note": f"eval 失败: {str(exc)}"[:300]}
            cancelled.set()
            if wt:
                wt.join(5)
            if fired.is_set() or page.is_closed():
                # 竞态兜底：eval 刚返回但看门狗已开杀 → 同样走页面重建
                return {"ok": False, "_page_dead": True,
                        "note": "eval 超时(>10s)：页面已重置（会话保留，请重新 goto）"}
            # data 字段给结构化结果（note 是纯文本给 AI 看的）
            return {"ok": True, "note": f"eval: {val}"[:400], "data": val}
        elif act in ("screenshot", "quit"):
            pass  # 由调用方处理
        else:
            return {"ok": False, "note": f"未知动作: {act}（支持: {', '.join(VISION_ACTIONS)}）"}
        return {"ok": True, "note": ""}
    except Exception as exc:
        return {"ok": False, "note": f"{act} 失败: {exc}"}


def _vision_route(url: str, output_dir: Path, headed: bool = False, safe: bool = False,
                  max_screens: int = VISION_DEFAULT_MAX_SCREENS,
                  detail: str = "original", model: str = "",
                  session_timeout_sec: int = 900,
                  viewport_w: int = 800, viewport_h: int = 800) -> Dict:
    """视觉会话模式（--method vision）：给多模态模型的"眼睛+手"。

    协议（stdin/stdout 各一行一个 JSON，AI Agent 驱动）：
      1. 启动后 stdout 输出初始状态（首屏截图 + 屏幕信息）
      2. AI 逐行往 stdin 写指令 JSON，例如：
         {"action":"click","x":100,"y":200}   左键点击（坐标=视口像素）
         {"action":"right_click","x":..,"y":..} 右键 / {"action":"dblclick",...} 双击
         {"action":"move","x":..,"y":..}        移动鼠标（视觉模型先看再点）
         {"action":"drag","x":..,"y":..,"to_x":..,"to_y":..}  拖动（滑块/画布类；HTML5 draggable 不保证触发）
         {"action":"scroll","x":0,"y":600}      滚动（y 正=向下）
         {"action":"type","text":"关键词"}       键盘输入
         {"action":"press","key":"Enter"}       按键
         {"action":"focus","selector":"input[name=q]"}  按 CSS 选择器聚焦（输入前先 focus 比裸坐标点更可靠）
         {"action":"elements"}                元素标注：返回视口内全部可点元素（tag/text/中心坐标/尺寸），点按钮前先拿这个
         {"action":"goto","url":"https://.."}   跳转 / back / forward / reload（启动 URL 失败会话也保活，可 goto 重试）
         {"action":"wait","ms":800}             等待（等动画/懒加载）
         {"action":"screenshot"}                主动重新截图
         {"action":"eval","js":"1+1"}           执行 JS（只读用途，结构化结果放 state 的 eval_result 字段）
         {"action":"viewport","width":1280,"height":800}  改视口（默认 800×800=DeepSeek 原生；改完重新 elements）
         {"action":"shot_policy","every":3}     截图节奏：每 3 个成功动作截 1 张（默认 1=动一次拍一次）
         {"action":"shot_policy","interval_ms":1000}      空闲时每秒自动截 1 张（默认 0=关；预算耗尽自动停）
         {"action":"quit"}                      结束会话
      3. 每条指令执行后 stdout 输出新状态（新截图 + 屏幕信息），直到 quit 或 stdin 关闭

    兜底（防 AI 侧故障拖死本进程）：
      - 会话总时长上限 session_timeout_sec（默认 900s）：超时自动收尾退出，
        绝不因 AI 卡死/不发 quit 变僵尸进程；
      - 指令间隔看门狗：连续 120s 收不到下一条指令视为 AI 断线，自动收尾退出；
      - 任何单条指令异常都返回 failed 状态继续会话，不会整体崩溃。

    状态 JSON 字段：
      event="state" | screenshot=最新截图路径 | screen=屏幕信息（视口/整页尺寸/DPR/鼠标/滚动）
      screenshots_used/max=截图计数（成本防护：单张≤384 token，超上限不再截图只报状态）
      api_hint=官方 API 调用参数（model/detail/384token 封顶等，照抄即可拼请求）
    """
    base = {"mode": "vision_session", "source_url": url, "output_dir": str(output_dir),
            "model": model or VISION_MODEL_NAME,
            "vision_capable": _is_vision_model(model) if model else True}
    shots_used = 0
    all_shots: List[str] = []
    last_auto_shot = time.time()  # 自动截图计时基准（任何一次截图都重置）

    def _emit_state(page, done: bool = False, note: str = "", extra: Optional[Dict] = None,
                    shoot: bool = True):
        nonlocal shots_used, last_auto_shot
        shot = None
        # shoot=False：坏JSON/失败指令页面没变化，不新截图（省配额），回退上一张
        if shoot and shots_used < max_screens:
            shot = _shot_viewport(page, output_dir)
            if shot:
                shots_used += 1
                all_shots.append(shot)
                last_auto_shot = time.time()  # 拍过就重置自动截图计时，避免动作拍完紧跟自动拍
        # 验证码自动检测（每步都查，检测到立即上报——不绕过，人工接管）
        captcha = []
        try:
            captcha = page.evaluate(CAPTCHA_JS) or []
        except Exception:
            pass
        state = {
            "event": "state",
            "done": done,
            "screenshot": shot or (all_shots[-1] if all_shots else None),
            "screen": _screen_info(page),
            "screenshots_used": shots_used,
            "screenshots_max": max_screens,
            "screenshot_budget_exhausted": shots_used >= max_screens,
            "api_hint": _vision_api_hint(detail),
        }
        if captcha:
            state["captcha_detected"] = captcha
            state["captcha_help"] = ("验证码只检测不绕过（合法合规）。人工接管：用 --headed 重开会话，"
                                     "人手动完成验证后 AI 发 wait 指令继续")
        if note:
            state["note"] = note
        if extra:
            state.update(extra)
        print(json.dumps(state, ensure_ascii=False), flush=True)
        return state

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {**base, "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            # 本地调试端口：eval 看门狗用它经 /json/close 强杀死循环页面
            # （仅绑 127.0.0.1，无对外暴露；其他路线不开，避免多余端口）
            debug_port = _free_port()
            browser = p.chromium.launch(
                headless=not headed,
                args=_browser_launch_args(safe) + [f"--remote-debugging-port={debug_port}"])
            try:
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    # 视口默认 800×800 = DeepSeek 视觉原生分辨率（超范围会被官方压糊）；
                    # AI 可用 viewport 指令或 --viewport 参数改（不局限于 DeepSeek）
                    viewport={"width": viewport_w, "height": viewport_h},
                    locale="zh-CN", timezone_id="Asia/Shanghai",
                    ignore_https_errors=True,
                    **({"service_workers": "block"} if safe else {}),
                )
                context.add_init_script(STEALTH_JS + MOUSE_TRACK_JS)
                page = context.new_page()
                if safe:
                    _setup_safe_mode(context, page)
                # 目录已有旧截图时提醒（自动清理有误删风险，只提示）
                try:
                    old_shots = len(list(output_dir.glob("screen_*.png")))
                    if old_shots:
                        print(f"[提示] 输出目录已有 {old_shots} 张旧截图，本次会话截图会继续追加",
                              file=sys.stderr)
                except Exception:
                    pass
                startup_failed = None
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    # 启动 URL 失败不杀会话：切空白页保活，AI 可发 goto 指令换 URL 重试
                    startup_failed = str(exc)
                    try:
                        page.goto("about:blank")
                    except Exception:
                        pass
                if startup_failed is None:
                    # 视觉会话等 4s 就够：会话可交互，AI 可自行 wait/reload；
                    # 共享版默认 10s 会让文字少的页面（图库等）白等
                    _wait_for_render(page, max_wait_sec=4.0)
                    # 懒加载滚动后回顶：视觉会话依赖视口坐标，停在页底会让 elements 坐标全错
                    try:
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_timeout(300)
                    except Exception:
                        pass
                # 首屏带上 vision_capable/model：AI 进会话第一眼就知道自己能不能看图
                # （此前只在 return 路径的 dict 里有，stdout 状态流里看不到）
                init_extra = {"vision_capable": base["vision_capable"], "model": base["model"]}
                # 重定向告警：请求 URL 与最终 URL 不一致时告知 AI
                if startup_failed is None and url and page.url != url and page.url != "about:blank":
                    init_extra["redirected_from"] = url
                _emit_state(page, note=(f"启动 URL 打不开：{startup_failed}"
                                        "（会话保留，可发 goto 指令换 URL）") if startup_failed else "",
                            extra=init_extra)
                # 指令循环：stdin 逐行 JSON → 执行 → 输出新状态（EOF/quit 退出）。
                # 看门狗兜底（跨平台方案：读线程+队列，Windows 的 stdin 不是 socket
                # 用不了 selectors）：AI 卡死不发指令（120s 断线）或会话超总时长
                # （默认 900s）都自动收尾退出——绝不因调用方故障变成挂死进程
                import queue as _queue
                import threading as _threading

                cmd_q: "queue.Queue[Optional[str]]" = _queue.Queue()

                def _stdin_reader():
                    try:
                        for ln in sys.stdin:
                            cmd_q.put(ln)
                    except Exception:
                        pass
                    finally:
                        cmd_q.put(None)  # EOF/异常统一哨兵

                reader = _threading.Thread(target=_stdin_reader, daemon=True)
                reader.start()
                session_start = time.time()
                idle_limit = 120  # 连续 120s 无下一条指令 = AI 断线
                # 截图节奏（shot_policy 指令可调）：默认动一次拍一张；空闲自动拍默认关
                shot_every = 1
                auto_interval_ms = 0
                actions_since_shot = 0
                last_cmd_time = session_start
                while True:
                    now = time.time()
                    if now - session_start > session_timeout_sec:
                        _emit_state(page, done=True, note="会话总时长到达上限，自动收尾")
                        break
                    # 等待切片：取「空闲看门狗剩余」「下次自动截图」两者最早的（每片上限 2s）
                    wait = (last_cmd_time + idle_limit) - now
                    if auto_interval_ms:
                        wait = min(wait, auto_interval_ms / 1000.0)
                    wait = max(0.05, min(wait, 2.0))
                    try:
                        line = cmd_q.get(timeout=wait)
                        last_cmd_time = time.time()
                    except _queue.Empty:
                        now2 = time.time()
                        if now2 - last_cmd_time >= idle_limit:
                            _emit_state(page, done=True, note="空闲看门狗：120s 未收到指令，判定 AI 侧断线，自动收尾")
                            break
                        # 空闲自动截图：到点且预算没耗尽才拍；耗尽则自动关并告知（防刷屏）
                        if auto_interval_ms and (now2 - last_auto_shot) * 1000 >= auto_interval_ms:
                            if shots_used < max_screens:
                                _emit_state(page, note="空闲自动截图")
                            else:
                                _emit_state(page, note="自动截图已停：截图预算耗尽", shoot=False)
                                auto_interval_ms = 0
                        continue
                    if line is None:  # EOF：stdin 关闭
                        _emit_state(page, done=True, note="stdin 已关闭（EOF），会话结束")
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd = json.loads(line)
                    except Exception:
                        _emit_state(page, note="指令不是合法 JSON，已忽略", shoot=False)
                        continue
                    act = (cmd.get("action") or "").strip().lower()
                    if act == "quit":
                        _emit_state(page, done=True, note="会话已关闭")
                        break
                    if act == "shot_policy":
                        # 截图节奏调整：every=每 N 个成功动作截一张（默认1）；
                        # interval_ms=空闲时自动截图间隔（默认0=关）。两者可只给其一
                        try:
                            shot_every = max(1, int(cmd.get("every", shot_every)))
                            auto_interval_ms = max(0, int(cmd.get("interval_ms", auto_interval_ms)))
                        except (TypeError, ValueError):
                            _emit_state(page, note="shot_policy 参数需为整数（every≥1，interval_ms≥0）", shoot=False)
                            continue
                        if auto_interval_ms:
                            last_auto_shot = time.time()  # 开启后从现在起计时，不追补历史
                        _emit_state(page, note=(f"截图节奏: 每 {shot_every} 个动作一张"
                                                + (f"，空闲每 {auto_interval_ms}ms 自动一张"
                                                   if auto_interval_ms else "，自动截图关")),
                                    shoot=False)
                        continue
                    # wait 钳到剩余预算：超时检查在指令间隙，长 wait 会拖爆总超时
                    remaining_ms = int((session_timeout_sec - (time.time() - session_start)) * 1000)
                    r = _vision_exec_action(page, cmd, output_dir, "vision",
                                            wait_cap_ms=max(0, remaining_ms),
                                            debug_port=debug_port)
                    if r.get("_page_dead"):
                        # eval 死循环兜底：看门狗已杀掉卡死页面，context 还活着，
                        # 这里直接重建空白页，会话保活（AI 重新 goto 即可）
                        try:
                            page = context.new_page()
                        except Exception:
                            # context 也没了：输出收尾状态后走异常路径，
                            # finally 里 browser.close() 正常清理，绝不挂死
                            print(json.dumps({
                                "event": "state", "done": True,
                                "screenshot": all_shots[-1] if all_shots else None,
                                "screenshots_used": shots_used, "screenshots_max": max_screens,
                                "note": "eval 死循环且页面无法重建，会话自动收尾",
                            }, ensure_ascii=False), flush=True)
                            raise
                        _emit_state(page, note=r.get("note", "页面已重置"), shoot=False)
                        continue
                    if act == "screenshot":
                        r = {"ok": True, "note": ""}
                    if act in ("goto", "reload", "back", "forward"):
                        page.wait_for_timeout(800)
                    # elements 指令的元素清单带进状态（视觉模型直接读坐标点按钮）
                    extra = {}
                    if r.get("elements"):
                        extra["elements"] = r["elements"]
                    if "data" in r:
                        extra["eval_result"] = r["data"]  # eval 结构化结果
                    extra = extra or None
                    # 截图节奏：screenshot 指令强制拍；成功动作每 every 张拍一次；失败不拍
                    if act == "screenshot":
                        shoot_now, actions_since_shot = True, 0
                    elif r.get("ok", True):
                        actions_since_shot += 1
                        shoot_now = actions_since_shot >= shot_every
                        if shoot_now:
                            actions_since_shot = 0
                    else:
                        shoot_now = False
                    _emit_state(page, note=r.get("note", ""), extra=extra, shoot=shoot_now)
            finally:
                browser.close()
        return {**base, "count": len(all_shots), "screenshots": all_shots,
                "screenshots_used": shots_used, "api_hint": _vision_api_hint(detail)}
    except Exception as exc:
        return {**base, "count": len(all_shots), "screenshots": all_shots,
                "screenshots_used": shots_used, "error": f"vision session error: {exc}"}


def _files_route(
    url: str, output_dir: Path, headed: bool = False, safe: bool = False,
    zip_bundle: bool = False, click_download: bool = False,
) -> Dict:
    """文件专用路线：
    1. URL 是文件直链（zip/pdf 等结尾）→ 流式直下（大文件不吃内存）；
    2. URL 是页面（网盘/文件夹列表/下载页）→ 打开页面收集所有文件链接，
       页面上下文逐个下载到独立子文件夹（用户的'整文件夹'选项）；
    3. zip_bundle=True → 全部下完打包成单个 zip 并清掉散文件（用户的'合并'选项）；
    4. click_download=True（--click-download 显式开启）→ 页面没有文件直链时，
       自动点下载按钮 + 网络嗅探真链接（APK 分享页"跳转自家 APP"场景）。
       激进模式默认关闭：会程序化点击页面按钮。"""
    base = {"mode": "url", "source_url": url, "output_dir": str(output_dir), "method": "files"}

    # 1) 文件直链
    if urllib.parse.urlparse(url).path.lower().endswith(FILE_EXTS):
        item = _file_direct_download(url, output_dir, safe)
        if item:
            return {**base, "saved": [item], "count": 1}
        return {**base, "saved": [], "count": 0,
                "error": "file direct download failed (link dead / is a webpage)"}

    # 2) 页面：收集文件链接逐个下载
    saved: List[Dict] = []
    files_error = None
    pierced_url = None
    click_used = False
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        files_error = "playwright not installed"
    else:
        try:
            with sync_playwright() as p:
                browser = None
                try:
                    browser = p.chromium.launch(headless=not headed, args=_browser_launch_args(safe))
                    context = browser.new_context(
                        user_agent=random.choice(USER_AGENTS),
                        viewport={"width": 1920, "height": 1080},
                        locale="zh-CN",
                        timezone_id="Asia/Shanghai",
                        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                        # 自动信任自签/过期证书：不少下载站用自签 HTTPS，
                        # 证书不过连页面都打不开就谈不上抓包（仅浏览器内忽略，不装系统证书）
                        ignore_https_errors=True,
                        **({"service_workers": "block"} if safe else {}),
                    )
                    context.add_init_script(STEALTH_JS)
                    page = context.new_page()
                    blocked = _setup_safe_mode(context, page) if safe else {}
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    # 落地页穿透：壳页（分享链接）先跟进到真实页面再收集文件链接
                    final_url = _goto_pierce_shell(page, url)
                    if final_url != url:
                        pierced_url = final_url
                    # JS 渲染等待：SPA 下载页的文件链接是 JS 挂载的，空白期收集=0 链接
                    _wait_for_render(page)
                    links = page.evaluate(FILE_LINKS_JS) or []
                    # 兜底：穿透后仍没链接，再被动提取一轮（双保险）
                    if not links:
                        try:
                            real_target = _extract_shell_redirect(page.content())
                        except Exception:
                            real_target = None
                        if real_target and real_target not in (url, final_url):
                            sys.stderr.write(f"[files] 跟进跳转壳: {real_target[:120]}\n")
                            page.goto(real_target, wait_until="domcontentloaded", timeout=30000)
                            final_url = real_target
                            links = page.evaluate(FILE_LINKS_JS) or []
                    links = links[:50]
                    if links:
                        sub_dir = output_dir / f"files_{int(time.time())}"
                        for u in links:
                            item = _file_direct_download(u, sub_dir, safe, referer=final_url)
                            if item:
                                saved.append(item)
                        # 3) 合并选项：打包成单个 zip
                        if saved and zip_bundle:
                            bundle_path = _zip_bundle(sub_dir, output_dir)
                            if bundle_path:
                                import shutil

                                shutil.rmtree(sub_dir, ignore_errors=True)
                                return {**base, "saved": saved, "count": len(saved),
                                        "zip_bundle": bundle_path}
                    elif click_download:
                        # 4) 点击式下载兜底（--click-download 显式开启）：
                        # 页面没有文件直链时点下载按钮 + 网络嗅探真链接
                        sys.stderr.write("[files] 无文件直链，启用点击式下载兜底（--click-download）\n")
                        saved, saw_funnel = _try_click_download(page, final_url, output_dir, safe)
                        click_used = True
                        if saw_funnel and not saved:
                            # 抓到的"下载链接"全是 APP 商店：这是引流装APP陷阱，如实报告
                            files_error = ("app_only: 页面的下载按钮只跳转 APP 商店（引流装APP），"
                                           "网页端没有真实文件可下载")
                    elif not links:
                        files_error = "no file links found on page"
                finally:
                    if browser is not None:
                        browser.close()
        except Exception as exc:
            files_error = f"browser error: {exc}"

    if saved:
        out = {**base, "saved": saved, "count": len(saved)}
        if pierced_url:
            out["pierced_to"] = pierced_url
        if click_used:
            out["click_download_used"] = True
        if safe:
            out["safe_mode"] = True
        return out
    out = {**base, "saved": [], "count": 0, "error": files_error or "files route got nothing"}
    if pierced_url:
        out["pierced_to"] = pierced_url
    if click_used:
        out["click_download_used"] = True
    if files_error and files_error.startswith("app_only"):
        out["app_only"] = True
    return out


# ---------- 文本电路：文章正文提取 + 小说目录逐章合并 + txt 直链直下 ----------

CHAPTER_LINKS_JS = """
() => {
    const pat = /^(第[0-9零一二三四五六七八九十百千万两]{1,12}\\s*[章节话卷回集部]|Chapter\\s*\\d+|序章|楔子|番外)/;
    const out = [];
    const seen = new Set();
    document.querySelectorAll('a[href]').forEach(a => {
        const t = (a.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!t || t.length > 60 || !pat.test(t)) return;
        let u;
        try { u = new URL(a.href, location.href); } catch (e) { return; }
        if (u.protocol !== 'http:' && u.protocol !== 'https:') return;
        const key = u.origin + u.pathname + u.search;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({url: u.href, title: t});
    });
    return out;
}
"""


def _extract_body_text(page) -> tuple:
    """提取当前页面标题+正文：优先正文容器（article/main/章节容器），兜底 body 全文。"""
    title = ""
    try:
        title = (page.title() or "").strip()
    except Exception:
        pass
    text = ""
    for sel in ("article", "main", ".content", "#content", ".article-content",
                "#chapter-content", ".chapter-content", "#txtContent", "body"):
        try:
            text = page.inner_text(sel) or ""
        except Exception:
            text = ""
        if len(text.strip()) > 200:
            break
    return title, (text or "").strip()


def _text_route(
    url: str, output_dir: Path, headed: bool = False, safe: bool = False,
    max_chapters: int = 100, allow_chapters: bool = True,
) -> Dict:
    """文本专用线：
    1. txt/md/csv 直链 → 委托 files 流式直下（文件本体原样保存）；
    2. 目录页（≥5 个"第X章/Chapter N"类链接，小说/长教程）→ 逐章抓正文，
       轻限速合并成单个 txt（含来源/书名/章节数头）；
    3. 普通文章页 → 滚动触发懒加载后正文提取存 txt。
    allow_chapters=False 时跳过逐章抓取（chain 兜底用，保持单页快速存正文）。"""
    base = {"mode": "url", "source_url": url, "output_dir": str(output_dir), "method": "text"}

    # 1) 文本文件直链：按文件本体直下（原样字节，不做提取）
    if urllib.parse.urlparse(url).path.lower().endswith((".txt", ".md", ".csv")):
        item = _file_direct_download(url, output_dir, safe)
        if item:
            return {**base, "saved": [item], "count": 1, "method": "text->files-direct"}
        # 直链失败（有些站直链返回 HTML 阅读页）→ 继续按页面打开

    # 2/3) 浏览器打开：目录检测 → 逐章合并 / 单页正文
    pierced_url = None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        item = {"error": "playwright not installed"}
    else:
        try:
            with sync_playwright() as p:
                browser = None
                try:
                    browser = p.chromium.launch(headless=not headed, args=_browser_launch_args(safe))
                    context = browser.new_context(
                        user_agent=random.choice(USER_AGENTS),
                        viewport={"width": 1920, "height": 1080},
                        locale="zh-CN",
                        timezone_id="Asia/Shanghai",
                        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                        **({"service_workers": "block"} if safe else {}),
                    )
                    context.add_init_script(STEALTH_JS)
                    page = context.new_page()
                    blocked = _setup_safe_mode(context, page) if safe else {}
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    # 落地页穿透：分享壳页先跟进到真实文章/目录页再提取正文
                    final_url = _goto_pierce_shell(page, url)
                    if final_url != url:
                        pierced_url = final_url
                    # JS 渲染等待：SPA 文章/目录页正文和章节链接都是 JS 挂载的
                    _wait_for_render(page)

                    chapters = page.evaluate(CHAPTER_LINKS_JS) or []
                    if allow_chapters and len(chapters) >= 5:
                        # 目录页：逐章抓正文合并成一个 txt
                        toc_title, _ = _extract_body_text(page)
                        book_name = re.sub(
                            r'[\\/:*?"<>|]+', "_",
                            (toc_title.split("-")[0].strip()[:40] or "novel"),
                        )
                        pieces = []
                        for ch in chapters[:max_chapters]:
                            try:
                                page.goto(ch["url"], wait_until="domcontentloaded", timeout=30000)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=5000)
                                except Exception:
                                    pass
                                _, body = _extract_body_text(page)
                                if len(body) > 200:
                                    pieces.append(f"{ch['title']}\n\n{body}")
                                    page.wait_for_timeout(400)  # 轻限速，别把站点打挂
                            except Exception:
                                continue
                        if len(pieces) >= 2:
                            output_dir.mkdir(parents=True, exist_ok=True)
                            path = output_dir / f"{book_name}_{int(time.time())}.txt"
                            content = (
                                f"来源: {final_url}\n书名: {toc_title}\n"
                                f"章节: 抓到 {len(pieces)}/{len(chapters)} 章（上限 {max_chapters}）\n"
                                + "=" * 40 + "\n\n" + "\n\n\n".join(pieces)
                            )
                            path.write_text(content, encoding="utf-8")
                            item = {
                                "url": final_url, "path": str(path), "kind": "text",
                                "size": path.stat().st_size, "title": toc_title,
                                "chapters_total": len(chapters), "chapters_saved": len(pieces),
                            }
                        else:
                            # 章节抓取几乎全失败：回到穿透后的页面滚动后单页保存
                            page.goto(final_url, wait_until="domcontentloaded", timeout=30000)
                            for _ in range(3):
                                page.mouse.wheel(0, 2000)
                                page.wait_for_timeout(600)
                            item = _save_page_text(page, final_url, output_dir)
                    else:
                        # 普通文章：滚动触发懒加载后单页保存
                        for _ in range(3):
                            page.mouse.wheel(0, 2000)
                            page.wait_for_timeout(600)
                        item = _save_page_text(page, final_url, output_dir)
                finally:
                    if browser is not None:
                        browser.close()
        except Exception as exc:
            # 页面打不开/超时：返回错误而不是崩溃，chain 能继续用其他方式
            item = {"error": f"browser error: {exc}"}

    if "error" in item:
        out = {**base, "saved": [], "count": 0, "yt_dlp_error": item["error"]}
    else:
        out = {**base, "saved": [item], "count": 1}
        if item.get("chapters_saved"):
            out["text_mode"] = "chapters-merged"
    if pierced_url:
        out["pierced_to"] = pierced_url
    if safe:
        out["safe_mode"] = True
        try:
            out["blocked"] = blocked
        except NameError:
            pass
    return out


def auto_save_url(
    url: str,
    output_dir: Path,
    wait_seconds: int = 8,
    method: str = "browser",
    headed: bool = False,
    max_wait: int = 180,
    auto_wait: bool = True,
    save_junk: bool = False,
    keep_segments: bool = False,
    media_types: str = "video,audio,image",
    safe: bool = False,
    zip_bundle: bool = False,
    max_chapters: int = 100,
    allow_chapters: bool = True,
    click_download: bool = False,
    vision_max_screens: int = VISION_DEFAULT_MAX_SCREENS,
    vision_detail: str = "original",
    model_name: str = "",
    vision_timeout: int = 900,
    vision_viewport: tuple = (800, 800),
    cookie_file: str = "",
    cookies_from_browser: str = "",
) -> Dict:
    """
    核心逻辑：
    1. auto 模式先试 yt-dlp 直接下载；失败再用真实浏览器边播边缓存。
    2. browser 模式默认用真实 Chromium 打开网页，像普通用户一样播放/加载。
    3. 视频/音频播放时经过浏览器网络层，脚本在“缓存”这一步保存媒体流。
    4. 额外尝试抓取 blob:/MSE 视频流（B站/抖音常见，带超时不会挂死）。
    5. wait 自适应：检测到视频还在出分段就自动延长等待（上限 max_wait）。
    6. 多种缓存方式互补：网络嗅探 + 206分段合并 + blob 抓取 + DOM/JSON 收割。
    7. media_types 控制只保存指定类型（video/audio/image），照片音频也能单独选。
    8. 保存到本地缓存后，由 AI / 用户决定保留还是删除。
    9. safe=True 安全模式：浏览器进程沙箱+站点隔离、拦挖矿/危险下载/弹窗、
       落盘扩展名白名单+2GB上限——访问可疑站点不伤本机。
    """
    # 如果是 so.com/sogou/baidu 等搜索跳转壳，先尝试解出真实地址，方便 yt-dlp 解析。
    url = _decode_redirect_url(url) or url
    yt_error = None

    # 媒体类型过滤：--media-type video,audio,image 任意组合，空则全部
    allowed_kinds = {t.strip() for t in re.split(r"[,，]", (media_types or "").strip()) if t.strip()}
    if not allowed_kinds:
        allowed_kinds = {"video", "audio", "image"}

    # 抖音图文帖（/note/…）预判：yt-dlp 不支持 note URL（直接 Unsupported URL 报错），
    # 自动转 harvest 图集收割——原图走页面上下文下载，不再白撞一墙
    if "/note/" in url and method in ("chain", "auto", "ytdlp"):
        try:
            r = auto_save_url(url, output_dir, wait_seconds, "harvest", headed, max_wait,
                              auto_wait, save_junk, keep_segments, media_types, safe,
                              cookie_file=cookie_file,
                              cookies_from_browser=cookies_from_browser)
            if r.get("saved"):
                r["method"] = f"{method}->harvest(note)"
                r["note_auto_rerouted"] = True
                return r
            # harvest 也空（图集被限制）：chain 继续走原链兜底，别直接失败
            if method in ("auto", "ytdlp"):
                return r
        except Exception:
            pass

    # chain：按顺序尝试多个下载/缓存方式，哪个成功用哪个；text 兜底保证纯文本页也能存。
    if method == "chain":
        attempts = []
        last_result = None
        # 兜底链扩容：direct → ytdlp → browser → cache → harvest(媒体页兜底) → text
        # 有 cookie 时追加 ytdlp+cookie 复试（第一遍未带 cookie 的 ytdlp 失败多半是登录墙）
        chain_methods = ["direct", "ytdlp", "browser", "cache", "harvest", "text"]
        for m in chain_methods:
            try:
                if m == "text":
                    # chain 兜底的 text 只做单页快速正文（目录逐章是 text 专用线的活，别拖死 chain）
                    result = auto_save_url(url, output_dir, wait_seconds, m, headed, max_wait,
                                           auto_wait, save_junk, keep_segments, media_types, safe,
                                           max_chapters=1, allow_chapters=False)
                elif m == "harvest":
                    # harvest 在 chain 里只收图片/音频（视频已由 browser/cache 干过一遍）
                    result = auto_save_url(url, output_dir, wait_seconds, m, headed, max_wait,
                                           auto_wait, save_junk, keep_segments, "image,audio", safe)
                else:
                    result = auto_save_url(url, output_dir, wait_seconds, m, headed, max_wait,
                                           auto_wait, save_junk, keep_segments, media_types, safe,
                                           cookie_file=cookie_file,
                                           cookies_from_browser=cookies_from_browser)
            except Exception as exc:
                # 某一环崩了（页面打不开/playwright 缺失等）不让 chain 整体死掉，继续试下一种
                result = {"saved": [], "count": 0, "method": m, "yt_dlp_error": f"crash: {exc}"}
            attempts.append(
                {
                    "method": m,
                    "count": result.get("count", 0),
                    "error": result.get("yt_dlp_error") or result.get("error"),
                }
            )
            if result.get("saved"):
                result["attempts"] = attempts
                result["method"] = f"chain->{m}"
                return result
            last_result = result
        # 全链失败且带 cookie 参数：ytdlp+cookie 最后一搏（前面各环没吃到 cookie 的场景）
        if cookie_file or cookies_from_browser:
            try:
                saved, yt_err = _download_with_ytdlp(url, output_dir, safe,
                                                     cookie_file=cookie_file,
                                                     cookies_from_browser=cookies_from_browser)
                attempts.append({"method": "ytdlp+cookies", "count": len(saved), "error": yt_err})
                if saved:
                    return {"mode": "url", "source_url": url, "output_dir": str(output_dir),
                            "saved": saved, "count": len(saved), "method": "chain->ytdlp+cookies",
                            "attempts": attempts}
            except Exception as exc:
                attempts.append({"method": "ytdlp+cookies", "count": 0, "error": f"crash: {exc}"})
        if last_result is None:
            last_result = {"saved": [], "count": 0, "method": "chain"}
        last_result["attempts"] = attempts
        return last_result

    # files：文件专用路线（压缩包/文档/表格/文本等，直链直下、页面批量下、可打包zip）
    if method == "files":
        return _files_route(url, output_dir, headed=headed, safe=safe,
                            zip_bundle=zip_bundle, click_download=click_download)

    # vision：视觉会话模式（多模态模型的"眼睛+手"，stdin/stdout JSON 协议驱动）
    if method == "vision":
        return _vision_route(url, output_dir, headed=headed, safe=safe,
                             max_screens=vision_max_screens, detail=vision_detail,
                             model=model_name, session_timeout_sec=vision_timeout,
                             viewport_w=vision_viewport[0], viewport_h=vision_viewport[1])

    # direct：只尝试直接下载直链媒体文件。
    if method == "direct":
        d_saved, d_error = _download_direct(url, output_dir, safe)
        base = {"mode": "url", "source_url": url, "output_dir": str(output_dir)}
        if safe:
            base["safe_mode"] = True
        if d_saved:
            return {**base, "saved": d_saved, "count": len(d_saved), "method": "direct"}
        return {**base, "saved": [], "count": 0, "method": "direct", "yt_dlp_error": d_error}

    # text：文本专用线（txt直链直下 / 小说目录逐章合并 / 单页正文提取）。
    if method == "text":
        return _text_route(url, output_dir, headed=headed, safe=safe,
                           max_chapters=max_chapters, allow_chapters=allow_chapters)

    # harvest：只走 DOM/元数据/JSON 收割 + 页面上下文下载，快（无长等待），适合照片/音频。
    if method == "harvest":
        saved: List[Dict] = []
        seen: set = set()
        harvest_error = None
        followed_redirect = None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            harvest_error = "playwright not installed"
        else:
            try:
                with sync_playwright() as p:
                    browser = None
                    try:
                        browser = p.chromium.launch(
                            headless=not headed,
                            args=_browser_launch_args(safe),
                        )
                        context = browser.new_context(
                            user_agent=random.choice(USER_AGENTS),
                            viewport={"width": 1920, "height": 1080},
                            locale="zh-CN",
                            timezone_id="Asia/Shanghai",
                            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                            **({"service_workers": "block"} if safe else {}),
                        )
                        context.add_init_script(STEALTH_JS)
                        # 登录态注入：抖音 note 图集原图等登录墙资源，带 cookie 才放行
                        if cookie_file:
                            ok_c, c_info = _add_cookies_to_context(context, cookie_file)
                            sys.stderr.write(
                                f"[cookies] harvest 注入{str(c_info) + ' 条' if ok_c else '失败: ' + str(c_info)}\n"
                            )
                        page = context.new_page()
                        blocked = _setup_safe_mode(context, page) if safe else {}
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        # 落地页穿透：壳页（分享链接）先跟进到真实页面再收割
                        final_url = _goto_pierce_shell(page, url)
                        if final_url != url:
                            followed_redirect = final_url
                        # JS 渲染等待：SPA 画廊/图库页媒体是 JS 挂载的，空白期收割=0
                        _wait_for_render(page)
                        # 迭代滚动收割：SPA 图集懒加载逐段触发（小黑盒这类只挂视口几张的页面）
                        saved = _harvest_lazy_all(page, final_url, output_dir, allowed_kinds,
                                                  seen, save_junk, safe=safe)
                        # 跳转壳页跟进：0 收割时提取真实目标 URL 再收割一轮（分享链接常见）
                        if not saved:
                            try:
                                real_target = _extract_shell_redirect(page.content())
                            except Exception:
                                real_target = None
                            if real_target and real_target not in (url, final_url):
                                sys.stderr.write(f"[harvest] 跟进跳转壳: {real_target[:120]}\n")
                                page.goto(real_target, wait_until="domcontentloaded", timeout=30000)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=8000)
                                except Exception:
                                    pass
                                saved = _harvest_lazy_all(page, real_target, output_dir,
                                                          allowed_kinds, seen, save_junk, safe=safe)
                                followed_redirect = real_target
                    finally:
                        if browser is not None:
                            browser.close()
            except Exception as exc:
                # 页面打不开/超时：返回错误而不是崩溃，chain 能继续用其他方式
                harvest_error = f"browser error: {exc}"
        if saved:
            out = {
                "mode": "url",
                "source_url": url,
                "output_dir": str(output_dir),
                "saved": saved,
                "count": len(saved),
                "method": "harvest",
            }
            if followed_redirect:
                out["followed_redirect"] = followed_redirect
        else:
            out = {
                "mode": "url",
                "source_url": url,
                "output_dir": str(output_dir),
                "saved": [],
                "count": 0,
                "method": "harvest",
                "yt_dlp_error": harvest_error or "no downloadable media found on page",
            }
            if followed_redirect:
                out["followed_redirect"] = followed_redirect
        if safe:
            out["safe_mode"] = True
            try:
                out["blocked"] = blocked
            except NameError:
                pass
        return out

    # auto / ytdlp：先试 yt-dlp 直接下载，失败再降级到浏览器。
    if method in ("ytdlp", "auto"):
        yt_saved, yt_error = _download_with_ytdlp(url, output_dir, safe,
                                                  cookie_file=cookie_file,
                                                  cookies_from_browser=cookies_from_browser)
        if yt_saved:
            out = {
                "mode": "url",
                "source_url": url,
                "output_dir": str(output_dir),
                "saved": yt_saved,
                "count": len(yt_saved),
                "method": "yt-dlp",
            }
            if safe:
                out["safe_mode"] = True
            return out
        if method == "ytdlp":
            out = {
                "mode": "url",
                "source_url": url,
                "output_dir": str(output_dir),
                "saved": [],
                "count": 0,
                "method": "ytdlp",
                "yt_dlp_error": yt_error or "yt-dlp returned no files",
            }
            if safe:
                out["safe_mode"] = True
            return out

    # browser / auto 的浏览器阶段：边播边缓存。
    saved: List[Dict] = []
    seen: set = set()
    counter = 0

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=not headed,
                args=_browser_launch_args(safe),
            )
            context = browser.new_context(
                accept_downloads=True,
                user_agent=random.choice(USER_AGENTS),
                viewport={
                    "width": random.randint(1280, 1920),
                    "height": random.randint(800, 1080),
                },
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                **({"service_workers": "block"} if safe else {}),
            )
            context.add_init_script(STEALTH_JS)
            # 登录态注入：抖音/B站登录墙站点，带 cookie 浏览器才放行视频流
            if cookie_file:
                ok_c, c_info = _add_cookies_to_context(context, cookie_file)
                sys.stderr.write(
                    f"[cookies] 浏览器路线注入{str(c_info) + ' 条' if ok_c else '失败: ' + str(c_info)}\n"
                )
            page = context.new_page()
            blocked = _setup_safe_mode(context, page) if safe else {}

            capture_cache = method in ("cache", "browser", "auto")

            def on_response(response):
                nonlocal counter
                try:
                    if capture_cache:
                        if response.status not in (200, 206):
                            return
                    elif response.status != 200:
                        return
                    content_type = response.headers.get("content-type", "")
                    kind = _media_kind(response.url, content_type)
                    if not kind or kind not in allowed_kinds:
                        return
                    # Skip already-seen URLs to avoid saving the same file repeatedly.
                    # 分段流经常同路径不同 query，缓存模式必须用完整 URL 区分每个分段。
                    key = response.url if capture_cache else response.url.split("?")[0]
                    if key in seen:
                        return
                    seen.add(key)
                    body = response.body()
                    if len(body) < 1024:
                        return
                    # 垃圾资源：图片图标任何模式都挡；视频/音频垃圾只在非分段模式挡（分段是正片不能误删）
                    is_junk = _is_junk_resource(response.url, content_type, len(body))
                    if (kind == "image" and is_junk) or (not capture_cache and is_junk):
                        if save_junk and not safe:
                            junk_dir = output_dir / "junk"
                            path = _save_bytes(body, junk_dir, response.url, content_type, counter)
                            counter += 1
                        return
                    # 安全模式：落盘白名单 + 大小上限（非媒体一律不落盘）
                    if safe:
                        fname = _safe_filename(response.url, content_type, counter)
                        reason = _safe_save_reason(fname, len(body))
                        if reason:
                            blocked["saved_rejects"] = blocked.get("saved_rejects", 0) + 1
                            sys.stderr.write(f"[safe-block] 落盘拒绝 {reason}: {response.url[:120]}\n")
                            return
                    if capture_cache:
                        # 缓存模式：连 206 分段也保存，放在 cache_segments 子目录。
                        seg_dir = output_dir / "cache_segments"
                        path = _save_bytes(body, seg_dir, response.url, content_type, counter)
                        saved.append(
                            {
                                "url": response.url,
                                "path": str(path),
                                "content_type": content_type,
                                "size": len(body),
                                "status": response.status,
                                "seq": counter,
                                "kind": "cache-segment",
                            }
                        )
                    else:
                        path = _save_bytes(body, output_dir, response.url, content_type, counter)
                        saved.append(
                            {
                                "url": response.url,
                                "path": str(path),
                                "content_type": content_type,
                                "size": len(body),
                                "kind": "network",
                            }
                        )
                    counter += 1
                except Exception as exc:
                    sys.stderr.write(f"[network-save] error: {exc}\n")

            def on_download(download):
                nonlocal counter
                try:
                    filename = download.suggested_filename or f"download_{int(time.time())}_{counter}"
                    filename = re.sub(r'[\\/:*?"<>|]+', "_", filename).strip(" .")
                    # 安全模式：下载文件名白名单（suggested_filename 站点完全可控，必须挡 exe 等）
                    if safe:
                        reason = _safe_save_reason(filename, 0)
                        if reason:
                            blocked["downloads"] = blocked.get("downloads", 0) + 1
                            sys.stderr.write(f"[safe-block] 下载拒绝 {reason}: {download.url[:120]}\n")
                            download.cancel()
                            return
                    output_dir.mkdir(parents=True, exist_ok=True)
                    path = output_dir / filename
                    download.save_as(str(path))
                    # 安全模式：落盘后大小复核，超限立即删
                    if safe and path.exists() and path.stat().st_size > SAFE_MAX_FILE_BYTES:
                        path.unlink()
                        blocked["downloads"] = blocked.get("downloads", 0) + 1
                        sys.stderr.write("[safe-block] 下载拒绝: 超过大小上限，已删除\n")
                        return
                    saved.append(
                        {
                            "url": download.url,
                            "path": str(path),
                            "content_type": "",
                            "size": path.stat().st_size if path.exists() else 0,
                            "kind": "download",
                        }
                    )
                    counter += 1
                except Exception as exc:
                    sys.stderr.write(f"[download-save] error: {exc}\n")

            page.on("response", on_response)
            page.on("download", on_download)

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # 页面标题尽力抓（抖音等反爬壳页可能拿不到，拿不到就是 None，不编造）
            try:
                page_title = page.title() or None
            except Exception:
                page_title = None

            # 强制触发懒加载图片/媒体，并尝试自动播放视频（触发分段下载）。
            _trigger_lazy_media(page)
            _auto_play_videos(page)

            # 模拟真实用户滚动，触发懒加载的视频/图片。
            for _ in range(5):
                page.mouse.move(random.randint(200, 1500), random.randint(200, 900))
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1200)
            # 再滚回顶部，重新触发一遍懒加载。
            page.mouse.wheel(0, -5000)
            page.wait_for_timeout(800)
            _trigger_lazy_media(page)
            _auto_play_videos(page)

            # ---- wait 自适应 ----
            # 页面有 video 元素时读真实时长，把 wait 拉到 时长+8s（封顶 max_wait）。
            target_wait = wait_seconds
            try:
                page_dur = page.evaluate(
                    "() => { const v = document.querySelector('video');"
                    " return (v && isFinite(v.duration) && v.duration > 0) ? v.duration : null; }"
                )
                if page_dur:
                    target_wait = max(wait_seconds, min(int(page_dur) + 8, max_wait))
            except Exception:
                pass

            if auto_wait:
                # 空闲检测循环：还在出新分段就继续等，连续 idle_wait 秒无新增才停。
                elapsed = 0
                idle = 0
                last_count = len(saved)
                idle_limit = 6
                while elapsed < max(target_wait, 1) and elapsed < max_wait:
                    time.sleep(2)
                    elapsed += 2
                    if len(saved) > last_count:
                        last_count = len(saved)
                        idle = 0
                    else:
                        idle += 2
                    if elapsed >= target_wait and idle >= idle_limit:
                        break
                actual_wait = elapsed
            else:
                time.sleep(target_wait)
                actual_wait = target_wait

            # 额外抓取 blob:/MSE 媒体（B站/抖音常见；JS 内部限时，不会挂死）。
            saved.extend(_capture_blob_media(page, output_dir, safe))

            # 缓存方式3：DOM/元数据/内嵌JSON 收割 + 页面上下文下载（照片/音频常靠这路拿到）。
            try:
                saved.extend(_harvest_dom_media(page, url, output_dir, allowed_kinds, seen, save_junk, safe=safe))
            except Exception as exc:
                sys.stderr.write(f"[harvest] error: {exc}\n")

            # 尝试把抓到的 206 分段合并成一个文件（URL分组+解码验证，垃圾分段不拼接）。
            merged, cleanup_info = _merge_segments(saved, output_dir, keep_segments, safe)
            if merged:
                if cleanup_info.get("removed_segments"):
                    # 分段已清理，结果里只留合并产物
                    saved = [i for i in saved if i.get("kind") != "cache-segment"] + merged
                else:
                    saved = saved + merged
        finally:
            if browser is not None:
                browser.close()

    if saved:
        has_media = _has_video_or_audio(saved)
        # browser/cache 模式如果只抓到图片/封面，没有视频本体，自动降级 yt-dlp。
        if method in ("browser", "cache") and not has_media:
            yt_fb, yt_error = _download_with_ytdlp(url, output_dir, safe)
            if yt_fb:
                out = {
                    "mode": "url",
                    "source_url": url,
                    "output_dir": str(output_dir),
                    "saved": yt_fb,
                    "count": len(yt_fb),
                    "method": "yt-dlp",
                    "note": "browser only captured non-video, yt-dlp fallback",
                }
                if safe:
                    out["safe_mode"] = True
                    try:
                        out["blocked"] = blocked
                    except NameError:
                        pass
                return out
        result = {
            "mode": "url",
            "source_url": url,
            "output_dir": str(output_dir),
            "saved": saved,
            "count": len(saved),
            "method": "playwright",
            "wait_actual_sec": actual_wait,
        }
        try:
            result["cleanup"] = cleanup_info
        except NameError:
            pass
        # 元数据来源声明：fMP4 抓包产物的容器时长不可信，verified_duration_sec 才是解码实测
        result["metadata_note"] = (
            "容器/fFMP4 moov 时长不可信；verified_duration_sec 为 ffmpeg 解码实测，"
            "未标 verified_duration_sec 的产物时长未知"
            if _ffmpeg_path()
            else "未安装 ffmpeg：无法验证时长与可播性，产物可能不完整"
        )
        # 页面元数据尽力而为（抖音接口全封时可能拿不到，如实标注）
        try:
            result["page_title"] = page_title
        except NameError:
            pass
        if safe:
            result["safe_mode"] = True
            result["blocked"] = blocked
        return result

    # browser/cache 模式什么都没抓到，再试 yt-dlp。
    if method in ("browser", "cache"):
        yt_saved, yt_error = _download_with_ytdlp(url, output_dir, safe)
        if yt_saved:
            out = {
                "mode": "url",
                "source_url": url,
                "output_dir": str(output_dir),
                "saved": yt_saved,
                "count": len(yt_saved),
                "method": "yt-dlp",
            }
            if safe:
                out["safe_mode"] = True
                try:
                    out["blocked"] = blocked
                except NameError:
                    pass
            return out

    out = {
        "mode": "url",
        "source_url": url,
        "output_dir": str(output_dir),
        "saved": saved,
        "count": len(saved),
        "method": "playwright",
        "yt_dlp_error": yt_error or "yt-dlp returned no files",
    }
    if safe:
        out["safe_mode"] = True
        try:
            out["blocked"] = blocked
        except NameError:
            pass
    return out


def _format_plain(data: Dict) -> str:
    lines = []
    lines.append(f"模式: {data.get('mode')}")
    if data.get("source_url"):
        lines.append(f"来源: {data['source_url']}")
    if data.get("picked_url"):
        lines.append(f"自动选择: {data['picked_url']}")
    if data.get("page_title"):
        lines.append(f"页面标题: {data['page_title']}")
    lines.append(f"保存目录: {data.get('output_dir')}")
    if data.get("wait_actual_sec") is not None:
        lines.append(f"实际等待: {data['wait_actual_sec']}s")
    if data.get("error"):
        lines.append(f"错误: {data['error']}")
    if data.get("safe_mode"):
        lines.append(f"安全模式: 开（拦截统计: {data.get('blocked', {})}）")
    cleanup = data.get("cleanup")
    if cleanup and cleanup.get("removed_segments"):
        lines.append(f"已清理分段: {cleanup['removed_segments']} 个（--keep-segments 可保留）")
    saved = data.get("saved", [])
    lines.append(f"已保存 {len(saved)} 个文件")
    for i, item in enumerate(saved, 1):
        dur = item.get("verified_duration_sec")
        dur_str = f", 实测时长 {dur}s" if dur else (", 时长未验证" if item.get("kind") in ("merged-segment", "merged-segment-candidate") else "")
        lines.append(f"{i}. {item.get('path')} ({item.get('size', 0)} bytes) [{item.get('kind', '')}]{dur_str}")
    if data.get("metadata_note"):
        lines.append(f"说明: {data['metadata_note']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DeepSeek Auto-Save Browser: open a URL and directly save media to cache."
    )
    parser.add_argument("--url", help="Direct URL to open (e.g. Douyin video link)")
    parser.add_argument("--query", help="Search query; auto-pick first result matched to media type (video/image/audio each has its own circuit)")
    parser.add_argument("--auto", action="store_true", help="With --query, automatically open and save the picked media result")
    parser.add_argument("--max-results", type=int, default=5, help="Max search results for --query")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Where to save media (default: <skill>/downloads/cache)",
    )
    parser.add_argument("--wait", type=int, default=8, help="基础等待秒数（auto-wait 开启时只是下限，会自动延长到视频抓完）")
    parser.add_argument("--max-wait", type=int, default=180, help="自动等待的硬上限秒数（默认 180）")
    parser.add_argument("--no-auto-wait", action="store_true", help="关闭 wait 自适应，只等 --wait 秒")
    parser.add_argument("--save-junk", action="store_true", help="保存垃圾资源（封面/图标等）到 junk/ 子目录（默认直接丢弃）")
    parser.add_argument("--keep-segments", action="store_true", help="合并成功后保留原始 cache_segments（默认自动清理）")
    parser.add_argument(
        "--media-type",
        default="video,audio,image",
        help="只保存指定媒体类型: video,audio,image,file,text 任意逗号组合（默认媒体全部）；单选时还决定 --query --auto 打开哪类页面（image→图片页, audio→音乐站, file→文件直链, text→文章/小说页）。例如只要照片: --media-type image",
    )
    parser.add_argument(
        "--method",
        choices=["chain", "direct", "browser", "cache", "ytdlp", "auto", "harvest", "files", "text", "vision"],
        default=None,
        help="不指定=自动选路(视频/直链→chain, 照片页/音频页→harvest, 文件→files, --media-type text→text); chain=自动按顺序尝试 direct→ytdlp→browser→cache→text; direct=直链下载; browser=真实浏览器边播边缓存; cache=额外抓206分段缓存; ytdlp=直接下载; auto=先yt-dlp,失败再浏览器; harvest=DOM/JSON收割+页面上下文下载(快,适合照片/音频); files=文件专用线(压缩包/文档,支持整页批量+--zip打包); text=文本专用线(文章正文提取/小说目录逐章合并/txt直链直下,--max-chapters控制章节数上限); vision=视觉会话(多模态模型的眼睛+手:截图+屏幕信息+鼠标键盘控制,stdin/stdout JSON协议)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="AI 告诉本工具自己用的模型名（如 deepseek-v4-flash-vision-exp）：名称含 vision 判定支持视觉，输出 vision_capable 供决策；普通模型传图会报错所以别开视觉功能",
    )
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="截图模式（配任意下载模式）：任务完成后独立打开页面→懒加载滚动→整页/分段截图(PNG)+屏幕信息，合并进 JSON。给多模态模型看页面用（每张≤384 token）",
    )
    parser.add_argument(
        "--shot-detail",
        choices=["low", "original", "auto"],
        default="original",
        help="视觉模式截图精细度（对应官方 API detail 参数）：low=512×512 更省 token；original=原图更清楚（默认）",
    )
    parser.add_argument(
        "--max-screenshots",
        type=int,
        default=VISION_DEFAULT_MAX_SCREENS,
        help=f"视觉会话单次截图数上限（成本防护，默认 {VISION_DEFAULT_MAX_SCREENS}：每张≤384 token，防失控烧钱）",
    )
    parser.add_argument(
        "--vision-timeout",
        type=int,
        default=900,
        help="视觉会话兜底：会话总时长上限秒数（默认 900=15分钟）。超时/AI 断线 120s 无指令都自动收尾退出，绝不挂死进程",
    )
    parser.add_argument(
        "--viewport",
        default="800x800",
        metavar="WxH",
        help="视觉会话视口尺寸（默认 800x800=DeepSeek 视觉原生分辨率，超范围官方压糊）。AI 也可在会话中发 {\"action\":\"viewport\",\"width\":W,\"height\":H} 动态改",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="files 路线专用：页面多个文件下载完后打包成单个 zip（默认保留散文件不打包）",
    )
    parser.add_argument(
        "--click-download",
        action="store_true",
        help="files 路线专用激进兜底（默认关闭）：页面没有文件直链时，自动点下载按钮+网络嗅探抓真实下载链接（Content-Type/下载事件/scheme参数解码），适合'点击下载跳转自家APP'的分享页。注意会程序化点击页面按钮",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=100,
        help="text 路线专用：小说/长文目录页最多抓多少章合并（默认 100）",
    )
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（默认无头）")
    parser.add_argument(
        "--safe",
        action="store_true",
        help="安全模式：恢复浏览器进程沙箱+站点隔离、拦挖矿/危险下载/弹窗、落盘白名单+2GB上限，产物隔离到 downloads/safe/（访问可疑站点时用）",
    )
    parser.add_argument(
        "--cookies",
        default="",
        help="Netscape 格式 cookies.txt 路径（浏览器扩展'Get cookies.txt'导出）。抖音/B站等登录墙站点带登录态下载，chain 里失败还会自动用 cookie 复试一次",
    )
    parser.add_argument(
        "--cookies-from-browser",
        default="",
        choices=["chrome", "edge", "firefox"],
        help="直接读本机浏览器的登录 cookie（免导出，但本机该浏览器得登录过目标站点）。--cookies 同时给时文件优先",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    if not args.url and not args.query:
        parser.print_help()
        return 2

    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    elif args.safe:
        # 安全模式：产物默认隔离到独立目录，与普通缓存分开
        output_dir = Path(__file__).resolve().parent.parent / "downloads" / "safe"
    else:
        output_dir = Path(__file__).resolve().parent.parent / "downloads" / "cache"

    if args.url:
        # --url 自动选路：照片页/音频页走 harvest 专用线，文件走 files 专用线，视频/直链走 chain（原路不变）。
        # 显式指定 --method 时完全尊重用户选择，不自动改。vision 视觉会话是交互模式，不参与自动选路。
        method = _route_method(args.url, args.media_type, args.method)
        auto_routed = args.method is None and method in ("harvest", "files", "text")
        if auto_routed:
            mt = _detect_url_media_type(args.url, args.media_type)
            line_name = {"image": "图片", "audio": "音频", "file": "文件", "video": "视频", "text": "文本"}[mt]
            print(f"[选路] 识别为{line_name}目标，走 {method} 专用线（失败自动退回 chain）", file=sys.stderr)
        try:
            # --viewport "WxH" 解析（vision 会话视口；坏格式回退默认 800x800）
            try:
                _vw, _vh = str(args.viewport).lower().split("x", 1)
                vision_vp = (max(200, min(3840, int(_vw))), max(200, min(3840, int(_vh))))
            except (ValueError, AttributeError):
                vision_vp = (800, 800)
                print(f"[提示] --viewport 格式应为 WxH（如 1280x800），已回退默认 800x800",
                      file=sys.stderr)
            data = auto_save_url(
                args.url,
                output_dir,
                args.wait,
                method=method,
                headed=args.headed,
                max_wait=args.max_wait,
                auto_wait=not args.no_auto_wait,
                save_junk=args.save_junk,
                keep_segments=args.keep_segments,
                media_types=args.media_type,
                safe=args.safe,
                zip_bundle=args.zip,
                max_chapters=args.max_chapters,
                click_download=args.click_download,
                vision_max_screens=args.max_screenshots,
                vision_detail=args.shot_detail,
                model_name=args.model or "",
                vision_timeout=args.vision_timeout,
                vision_viewport=vision_vp,
                cookie_file=args.cookies,
                cookies_from_browser=args.cookies_from_browser,
            )
            # 自动选到 harvest/files 但颗粒无收：退回通用链再试一次（chain 自带优雅降级）。
            if auto_routed and data.get("count", 0) == 0 and not args.click_download:
                print(f"[选路] {method} 无收获，退回 chain 通用链重试", file=sys.stderr)
                try:
                    data = auto_save_url(
                        args.url,
                        output_dir,
                        args.wait,
                        method="chain",
                        headed=args.headed,
                        max_wait=args.max_wait,
                        auto_wait=not args.no_auto_wait,
                        save_junk=args.save_junk,
                        keep_segments=args.keep_segments,
                        media_types=args.media_type,
                        safe=args.safe,
                        zip_bundle=args.zip,
                        cookie_file=args.cookies,
                        cookies_from_browser=args.cookies_from_browser,
                    )
                    data["method_fallback"] = f"{method}→chain"
                except Exception:
                    pass
        except Exception as exc:
            data = {
                "mode": "url",
                "source_url": args.url,
                "output_dir": str(output_dir),
                "saved": [],
                "count": 0,
                "method": method,
                "error": f"unexpected error: {exc}",
            }
    elif args.query and args.auto:
        # 媒体类型检测（--media-type 单选 > query 关键词 > 默认 video），
        # 检测结果决定导航电路：图片找图片页、音频找音乐站、文件挑文件直链、视频保持原逻辑。
        media_type = _detect_media_intent(args.query, args.media_type)
        # 图片/音频默认走 harvest（DOM 收割），文件走 files 专用线，文本走 text 专用线；视频保持 chain 不动。
        # 显式指定 --method 时完全尊重用户选择。
        method = args.method
        if method is None:
            method = {"image": "harvest", "audio": "harvest", "file": "files", "text": "text"}.get(media_type, "chain")
        label = {"image": "图片", "audio": "音频", "video": "视频", "file": "文件", "text": "文本"}[media_type]
        print(f"[搜索] 正在用自创搜索引擎找（{label}电路）：{args.query}", file=sys.stderr)
        url = _search_first_media_url(args.query, args.max_results, media_type, safe=args.safe)
        if not url:
            data = {
                "mode": "query",
                "query": args.query,
                "media_intent": media_type,
                "output_dir": str(output_dir),
                "saved": [],
                "count": 0,
                "error": f"没有找到{label}类结果，请用 --url 直接给链接",
            }
        else:
            print(f"[下载] 自动打开（{label}电路）：{url}", file=sys.stderr)
            try:
                data = auto_save_url(
                    url,
                    output_dir,
                    args.wait,
                    method=method,
                    headed=args.headed,
                    max_wait=args.max_wait,
                    auto_wait=not args.no_auto_wait,
                    save_junk=args.save_junk,
                    keep_segments=args.keep_segments,
                    media_types=args.media_type,
                    safe=args.safe,
                    zip_bundle=args.zip,
                    max_chapters=args.max_chapters,
                    cookie_file=args.cookies,
                    cookies_from_browser=args.cookies_from_browser,
                )
            except Exception as exc:
                data = {
                    "mode": "query",
                    "query": args.query,
                    "picked_url": url,
                    "media_intent": media_type,
                    "output_dir": str(output_dir),
                    "saved": [],
                    "count": 0,
                    "method": method,
                    "error": f"unexpected error: {exc}",
                }
            data["mode"] = "query"
            data["query"] = args.query
            data["picked_url"] = url
            data["media_intent"] = media_type
            # 与 --url 模式对齐：自动选到专用线（harvest/files/text）颗粒无收时
            # 退回 chain 通用链重试（chain 自带优雅降级），失败不再直接报"没有收获"
            if (method != "chain" and args.method is None
                    and data.get("count", 0) == 0 and not args.click_download):
                print(f"[选路] {method} 无收获，退回 chain 通用链重试", file=sys.stderr)
                try:
                    retry = auto_save_url(
                        url,
                        output_dir,
                        args.wait,
                        method="chain",
                        headed=args.headed,
                        max_wait=args.max_wait,
                        auto_wait=not args.no_auto_wait,
                        save_junk=args.save_junk,
                        keep_segments=args.keep_segments,
                        media_types=args.media_type,
                        safe=args.safe,
                        zip_bundle=args.zip,
                        max_chapters=args.max_chapters,
                    )
                    if retry.get("count", 0) > 0:
                        retry["mode"] = "query"
                        retry["query"] = args.query
                        retry["picked_url"] = url
                        retry["media_intent"] = media_type
                        retry["method_fallback"] = f"{method}→chain"
                        data = retry
                except Exception:
                    pass
    else:
        print("使用 --query 时必须加 --auto 才会自动打开并下载。", file=sys.stderr)
        return 2

    # --screenshot 后处理：任意模式跑完后独立截一组页面图（给多模态模型看）。
    # 不干扰原模式逻辑；vision 会话自带截图就不重复做了。
    if args.screenshot and args.method != "vision":
        shot_url = data.get("picked_url") or data.get("source_url") or args.url
        if shot_url:
            print(f"[截图] 打开页面截图（给多模态模型看）：{shot_url[:100]}", file=sys.stderr)
            shot = _screenshot_standalone(shot_url, output_dir, headed=args.headed, safe=args.safe)
            data["screenshots"] = shot.get("screenshots", [])
            data["screen"] = shot.get("screen", {})
            if shot.get("error"):
                data["screenshot_error"] = shot["error"]

    # --model 视觉能力检测：名称含 vision = 多模态（官方仅 vision 模型接受图片，普通模型传图报错）
    if args.model:
        data["model"] = args.model
        data["vision_capable"] = _is_vision_model(args.model)
        if _is_vision_model(args.model):
            data["api_hint"] = _vision_api_hint(args.shot_detail)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_format_plain(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
