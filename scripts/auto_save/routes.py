"""下载路线层（v1.22.0 批 B 自 auto_save_browser.py 搬迁，零逻辑改动）：
- 直链/yt-dlp 下载、页面上下文下载、blob/MSE 抓取、DOM/JSON 收割、
  分段合并、文件/文本路线、点击下载、zip 打包
- _harvest_route/_browser_route 由 auto_save_url 神函数（683 行）的内联块提成
- 批 3 归一：四条路线的浏览器启动样板（约 150 行×差异）收敛为 browser_base._open_page()
- 调度器 auto_save_url 留在主文件（chain 递归 + 7 路 if 分派的薄壳）
依赖方向：routes → browser_base/urlrules/constants/ffmpeg/humanize（无环）。"""
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .browser_base import (
    _open_page, _save_bytes, _wait_for_render,
    _apply_stealth, _browser_launch_args, _launch_chromium,
    get_proxy, _proxy_urlopen,
)
from .constants import AUDIO_EXTS, FILE_EXTS, SAFE_MAX_FILE_BYTES, USER_AGENTS, VIDEO_EXTS
from .ffmpeg import (_decoded_duration, _ffmpeg_path, _ffprobe_info, _ffprobe_path,
                     _probe_resolution)
from .humanize import human_move, human_scroll
from .urlrules import (CLICK_DOWNLOAD_FILE_TYPES, DOWNLOAD_BUTTON_TEXTS,
                       MEDIA_EXTENSIONS, SHELL_BODY_TEXT_LIMIT, _assess_saved_quality,
                       _cap_filename, _decode_redirect_url, _decode_scheme_target,
                       _ext_from_content_type, _extract_shell_redirect,
                       _filename_from_disposition, _host_matches, _is_app_store_url,
                       _is_junk_resource, _is_media_url, _is_split_stream_fragment,
                       _is_static_asset_host, _media_kind, _safe_filename, _safe_save_reason,
                       _stream_basename, _stream_path_norm, _url_group_key, _url_identity)

__all__ = [
    "HARVEST_JS", "FILE_LINKS_JS", "CHAPTER_LINKS_JS",
    "set_ytdlp_opts", "_build_ydl_opts", "_ytdlp_format",
    "_download_direct", "_download_with_ytdlp", "_http_fetch_media", "_page_fetch",
    "_file_direct_download", "_goto_pierce_shell", "_trigger_lazy_media",
    "_auto_play_videos", "_wait_images_complete", "_extract_body_text",
    "_save_page_text", "_zip_bundle", "_try_click_download", "_page_fetch_download",
    "_files_route", "_text_route", "_capture_blob_media", "_harvest_dom_media",
    "_harvest_lazy_all", "_merge_segments", "_has_video_or_audio",
    "_harvest_route", "_browser_route",
]



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

# ---- yt-dlp 能力开关（v1.23.0）：播放列表 / 转音频 / 清晰度 ----
# 沿用 v1.22.0 行为开关模式（humanize/realheadless 先例）：落到模块级状态，
# 避免新参数层层穿透 auto_save_url（已有 25+ 形参）和 5 处调用点。
# 默认全部维持旧行为——noplaylist 单视频语义是刻意设计（用户给一条链接就只下
# 这一条），不改动；三个能力全部 opt-in（--playlist / --extract-audio / --quality）。
_YTDLP_OPTS = {
    "playlist": False,       # True = 合集/播放列表整单下载（--playlist）
    "playlist_max": 0,       # >0 = 最多下前 N 个（--playlist-max，映射 playlistend）
    "extract_audio": False,  # True = 下载后 ffmpeg 抽音频（--extract-audio）
    "audio_format": "mp3",   # 转音频目标格式（--audio-format）
    "quality": "best",       # best/1080p/720p/480p/360p（--quality）
}


def set_ytdlp_opts(playlist=None, playlist_max=None, extract_audio=None,
                   audio_format=None, quality=None) -> Dict:
    """设置 yt-dlp 能力开关（None = 保持不变）。main() 解析 CLI 后调用一次。
    返回当前生效配置（供诊断输出）。"""
    if playlist is not None:
        _YTDLP_OPTS["playlist"] = bool(playlist)
    if playlist_max is not None:
        _YTDLP_OPTS["playlist_max"] = max(0, int(playlist_max))
    if extract_audio is not None:
        _YTDLP_OPTS["extract_audio"] = bool(extract_audio)
    if audio_format is not None:
        _YTDLP_OPTS["audio_format"] = audio_format
    if quality is not None:
        _YTDLP_OPTS["quality"] = quality
    return dict(_YTDLP_OPTS)


def _ytdlp_format(quality: str) -> str:
    """--quality → yt-dlp format 串（纯函数，离线可测）。
    best 保持原串零变化；Np = 清晰度封顶，层层回退（低清源/纯DASH站不空手）。
    回退链实测依据（B站 BV1GJ411c7Ud）：
    - B站等站全是 DASH 分离流（video only/audio only，无渐进单文件）——
      `best` 只匹配音视频合一格式，纯 DASH 站上必落空，末端必须兜回
      bestvideo+bestaudio（合并分离流）；
    - 竖屏视频"高度"是长边（480P 档=480x852），按 height<=480 会全灭——
      补 width<={h} 一招，恰好命中竖屏的同名清晰度档。"""
    q = (quality or "best").lower().strip()
    if q in ("", "best"):
        return "bestvideo+bestaudio/best"
    m = re.match(r"^(\d{3,4})p$", q)
    if m:
        h = m.group(1)
        return (f"bestvideo[height<={h}]+bestaudio/"
                f"bestvideo[width<={h}]+bestaudio/"
                f"best[height<={h}]/"
                f"bestvideo+bestaudio/best")
    return "bestvideo+bestaudio/best"


def _build_ydl_opts(output_dir: Path, opts: Optional[Dict] = None) -> Dict:
    """_download_with_ytdlp 的 ydl_opts 组装（纯函数，opts 缺省读模块级状态）。
    独立成函数是为了离线单测：不发网络也能断言各开关的字典形态。
    cookie / ffmpeg 注入仍留在 _download_with_ytdlp（那两步有 IO 和错误语义）。"""
    o = dict(_YTDLP_OPTS) if opts is None else dict(opts)
    ydl_opts = {
        # 文件名限长（v1.22.0 压测修复）：无专用适配器的站点（汽水音乐等）generic
        # extractor 会把 URL 长参数（sec_sharer_id 长 base64 等）塞进 title/id，
        # Windows 路径超 260 上限 → .part 打开 Errno 2 三路全挂。
        # 三道保险：title 截 60 + id 截 30 + trim_file_name 清洗后再硬限 120。
        "outtmpl": str(output_dir / "%(title).60s [%(id).30s].%(ext)s"),
        "trim_file_name": 120,
        "quiet": True,
        "no_warnings": True,
        # 进度条污染 stdout（v1.22.1 网易云压测排雷）：quiet 只拦 to_screen，
        # 下载进度走 _multiline.print_at_line 直接写 stdout——--json 模式的
        # 标准输出被 [download] xx% 糊一脸，下游 JSON 解析全崩。noprogress 掐掉。
        "noprogress": True,
        "restrictfilenames": True,
        "format": _ytdlp_format(o.get("quality", "best")),
        "merge_output_format": "mp4",
    }
    if not o.get("playlist"):
        # 默认单视频语义（设计保留）：URL 属于合集时只下本条
        ydl_opts["noplaylist"] = True
    elif o.get("playlist_max", 0) > 0:
        ydl_opts["playlistend"] = int(o["playlist_max"])
    if o.get("extract_audio"):
        # 转音频只拉音轨（流量减半），ffmpeg 抽转目标格式；preferredquality 0 = 尽量原质
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": o.get("audio_format", "mp3"),
            "preferredquality": "0",
        }]
    return ydl_opts


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
    if _YTDLP_OPTS.get("extract_audio") and not _ffmpeg_path():
        sys.stderr.write("[ytdlp] --extract-audio 需要 ffmpeg 转码，未检测到 ffmpeg——"
                         "下载可成功但转码步会失败，建议先装 ffmpeg\n")
    ydl_opts = _build_ydl_opts(output_dir)
    # 全局代理（v1.23.0）：设了 --proxy 就连 yt-dlp 一起走
    if get_proxy():
        ydl_opts["proxy"] = get_proxy()
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
                    # v1.22.1 快手压测排雷：generic extractor 把 API 错误响应存成
                    # .unknown_video（实测 63B 的 {"result":2,...} JSON）——非媒体
                    # 扩展名 + <4KB 必是壳页/错误响应，删除不入产物（防假下载）。
                    try:
                        _sz = os.path.getsize(fp)
                        _ext = Path(fp).suffix.lower()
                        if _ext not in MEDIA_EXTENSIONS and _sz < 4096:
                            os.remove(fp)
                            sys.stderr.write(f"[ytdlp] 丢弃伪产物: {Path(fp).name} "
                                             f"({_sz}B 非媒体响应)\n")
                            continue
                    except OSError:
                        pass
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
    """Try to download a direct media file (mp4/jpg/mp3...) with a browser-like UA.
    v1.22.1：文件直链（URL 以文件扩展名结尾，zip/pdf/docx/exe…22 种）先走
    _file_direct_download 流式分块下载（8MB 块不吃内存，大文件友好）。
    门槛必须卡扩展名：无门槛会让普通页面/API 的 JSON 响应也被当文件存
    （实测排雷：任何非 HTML 响应都会落盘成垃圾"文件"）。无扩展名 URL
    多为页面/API，留给后面的路线处理。"""
    if urllib.parse.urlparse(url).path.lower().endswith(FILE_EXTS):
        item = _file_direct_download(url, output_dir, safe=safe)
        if not item:
            # 文件阶梯第 2 招：真 Chromium 指纹（治 JA3 拦 urllib 的站，w3.org 实测）
            item = _file_browser_fetch(url, output_dir, safe=safe)
        if item:
            return [item], None
        return [], "file direct download failed (link dead / TLS-blocked / is a webpage)"
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
        with _proxy_urlopen(req, timeout=30) as resp:
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



_MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")


def _refetch_personas(page_url: str) -> List[Dict]:
    """取流人设阶梯（v1.22.1，平台无关）：每招对应一类站点的验法。
    反馈驱动（_refetch_full_media 内）按响应特征跳招，不盲试。"""
    referer = ""
    if page_url:
        parsed = urllib.parse.urlparse(page_url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
    return [
        # 1 页签原生（cookie+referer 齐全，最像播放器自己）——由调用方 _page_fetch 承担
        {"id": "tab", "via": "page"},
        # 2 桌面 UA 直取（热链站只验 referer/UA）
        {"id": "desktop", "via": "http", "ua": None, "referer": referer or None},
        # 3 移动 UA（抖音/快手系 CDN 面向移动端，移动 UA 通过率高）
        {"id": "mobile", "via": "http", "ua": _MOBILE_UA, "referer": referer or None},
        # 4 裸取（不带 referer——部分站反着来，带了 referer 判定为爬虫）
        {"id": "bare", "via": "http", "ua": None, "referer": None},
    ]


def _refetch_full_media(page, page_url, stream_info, output_dir, safe, seen):
    """先要后抓（v1.22.1 范式升级，平台无关）——六招阶梯 + 反馈驱动：

    招式序列（成功即停，总尝试硬上限 6 防请求风暴触发风控）：
      1 tab      页签 fetch（cookie/referer 齐全，最像播放器自己）
      2 desktop  http 桌面 UA + referer
      3 mobile   http 移动 UA + referer（抖音/快手系 CDN 面向移动端）
      4 bare     http 裸取（部分站带 referer 反判爬虫）
      5 refresh  刷新页面换新鲜签名 URL 再走 1-2（签名过期是多数拦截主因，
                  换 UA 无用，刷新才是解药；限一次）
      6 range    Range: bytes=0- 变体（416/206 语义差异站）

    反馈驱动：403/401 → 跳 mobile（换身份）；截断 200 → 跳 refresh（换票）；
    全空 → 顺序下一招。缺斤短两（< Content-Range 总长）一律不要。
    候选判据/成功标准同前：total > max_seg + 4KB 才值得整取；拿到全量才存。"""
    import base64
    results: List[Dict] = []
    # 站点物料域一票否决（v1.22.1 抖音压测二次排雷）：uuu_265.mp4 这类
    # douyinstatic.com 推广物料经 body-不可读账本混进整取候选（实测 199KB
    # 下载入产物）——账本两个记入口（on_response 兜底/cache 分段）都不拦，
    # 在唯一消费口（这里）统一拦，一处管全部。
    ranked = sorted(
        ((u, i) for u, i in stream_info.items()
         if (i.get("total") or 0) > (i.get("max_seg") or 0) + 4096
         and not _is_static_asset_host(u)),
        key=lambda x: x[1].get("total") or 0, reverse=True,
    )[:5]
    # 镜像去重（v1.22.1 排雷）：B站 playinfo 的 baseUrl + backupUrl 是同一段流的
    # 不同 CDN 主机（路径相同）——media_streams 按完整 URL 记账会拆成多条候选，
    # 同一文件被 tab/desktop 各整取一份（实测 4.9MB×2）。按路径去重，镜像只取首个。
    # v1.22.1 二次排雷（B站实测 30216 音频×2）：mcdn PCDN 镜像带 /v1/resource
    # 路由前缀，裸 path 比较判成两条资源——用规范化路径（_stream_path_norm）。
    # v1.22.1 三次排雷（抖音实测 media.mp4×2）：镜像 URL 路径各不相同（tos hash
    # 不同）——路径尺失效，带媒体扩展名的流文件同名即同资源，basename 双尺去重。
    _seen_paths, _seen_names, _deduped = set(), set(), []
    for u, i in ranked:
        _p = _stream_path_norm(u)
        _b = _stream_basename(u)
        if _p in _seen_paths or (_b and _b in _seen_names):
            continue
        _seen_paths.add(_p)
        if _b:
            _seen_names.add(_b)
        _deduped.append((u, i))
    ranked = _deduped
    if not ranked:
        return results

    def _try_get(u: str, p: Dict) -> Optional[Dict]:
        if p["via"] == "page":
            return _page_fetch(page, u)
        return _http_fetch_media(u, page_url=page_url, persona=p)

    attempts = 0
    refreshed = False
    for u, info in ranked:
        personas = _refetch_personas(page_url)
        pi = 0
        round_after_refresh = False
        while pi < len(personas) and attempts < 6:
            p = personas[pi]
            attempts += 1
            seen.add(u)
            item = _try_get(u, p)
            if item and item.get("b64"):
                try:
                    data = base64.b64decode(item["b64"])
                except Exception:
                    data = b""
                total = info.get("total") or 0
                if data and total and len(data) >= total:
                    ct = item.get("ct", "") or ""
                    if safe:
                        reason = _safe_save_reason(_safe_filename(u, ct, 0), len(data))
                        if reason:
                            sys.stderr.write(f"[safe-block] 落盘拒绝 {reason}: {u[:120]}\n")
                            break
                    path = _save_bytes(data, output_dir, u, ct, 90000 + len(results))
                    results.append({
                        "url": u, "path": str(path), "content_type": ct,
                        "size": len(data), "kind": "full-refetch", "via": p["id"],
                    })
                    sys.stderr.write(f"[refetch:{p['id']}] 整文件重取成功: {Path(path).name} "
                                     f"({len(data)}B)——免分段拼装\n")
                    break  # 这条流要到了，下一条流
                if data:
                    # 200 但截断 → 签名票过期，刷新换弹药（限一次）
                    if not refreshed:
                        refreshed = True
                        try:
                            page.reload(timeout=15000)
                            time.sleep(1.0)
                            sys.stderr.write("[refetch] 截断响应，刷新页面换新鲜签名 URL\n")
                            pi = 0  # 重走 tab 招（新页面上下文）
                            continue
                        except Exception:
                            pass
                    sys.stderr.write(
                        f"[refetch:{p['id']}] 整取 {len(data)}B < 流总长 {total}B，弃\n")
            else:
                # 全空响应（CORS/网络断）：招式耗尽前刷一次页换新上下文再试一轮
                if not refreshed and pi == len(personas) - 1 and not round_after_refresh:
                    refreshed = True
                    round_after_refresh = True
                    try:
                        page.reload(timeout=15000)
                        time.sleep(1.0)
                        sys.stderr.write("[refetch] 全招无响应，刷新页面换上下文再试一轮\n")
                        pi = 0
                        continue
                    except Exception:
                        pass
            # 失败反馈：403 → 直跳 mobile（换身份）；否则顺序下一招
            pi = pi + 1 if p["id"] != "desktop" or not (item and item.get("status") in (403, 401)) else 2
            time.sleep(0.3)  # 招间隔：防短时高频触发风控
        if attempts >= 6:
            sys.stderr.write("[refetch] 达尝试上限 6，回退分段抓取\n")
            break
    return results


def _merge_segments(saved: List[Dict], output_dir: Path, keep_segments: bool = False, safe: bool = False) -> Tuple[List[Dict], Dict]:
    """验证式合并：
    1. 只取 cache-segment，按 (媒体家族, URL目录) 分组——正片/音频/推荐位天然分家；
       v1.22.1：.mp4/.m4s 归同一家族——fMP4 的 init.mp4(moov头) 与 seg-*.m4s 本是一条流，
       旧按扩展名分组把它们拆开，m4s 组拼出的文件必然无 moov 头解不开；
    2. ffprobe 可用时剔除异分辨率（推荐位竖屏小段）与 <0.5s 残段；
    3. 组内排序：有 206 偏移按文件内偏移排 + 同偏移去重（并行请求到达序≠文件序，
       旧按到达序拼=必然损坏）；无偏移时 init 段置首；
    4. ffmpeg 解码验证真实时长，<3s 或解码失败即弃；
    5. 多组通过时取真实时长最长的一组为正片；
    6. 无 ffmpeg 时只合并体量最大组并明确标注 unverified；
    7. 同资源完整文件已在产物中（pagefetch/network 拿过）→ 跳过分段合并，成果互认。
    返回 (merged_list, cleanup_info)。"""
    seg_items = [i for i in saved if i.get("kind") == "cache-segment"]
    cleanup = {"removed_segments": 0, "kept_segments": 0}
    if not seg_items:
        return [], cleanup

    # ---- 分组（v1.22.1：媒体家族维度，修 init/m4s 拆组） ----
    def _seg_family(ext: str) -> str:
        return ".mp4" if ext in (".mp4", ".m4s", ".m4v") else ext

    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for item in seg_items:
        ext = Path(item.get("path", "")).suffix.lower()
        key = (_seg_family(ext), _url_group_key(item.get("url", "")))
        groups.setdefault(key, []).append(item)

    # 成果互认（v1.22.1 修重复拉流对偶面）：pagefetch/network 已有同资源完整文件
    # → 不再拼分段（拼了也是第二份）。两套抓取机制从此互认，不再各干各的。
    complete_ids = {
        _url_identity(i.get("url", ""))
        for i in saved if i.get("kind") != "cache-segment" and i.get("url")
    }

    # 弃掉总量的<5% 的碎组（范围请求残片/推荐位）
    total_bytes = sum(i.get("size", 0) for i in seg_items)
    candidates = []
    for key, items in groups.items():
        group_bytes = sum(i.get("size", 0) for i in items)
        # 整文件已在产物（先要成功/pagefetch 已拿过）：该组分段全是冗余原料，
        # 清盘 + 剔条目（removed_paths 供调用方过滤 phantom），不再只是跳过。
        if any(_url_identity(i.get("url", "")) in complete_ids for i in items):
            for i in items:
                try:
                    p = Path(i.get("path", ""))
                    if p.exists():
                        p.unlink()
                        cleanup["removed_segments"] += 1
                        # v1.22.1 排雷：必须是 list——set 会进 result["cleanup"]，
                        # json.dumps 直接 TypeError（B站实测：下载全成功、输出层崩溃）
                        cleanup.setdefault("removed_paths", []).append(str(p))
                except Exception:
                    pass
            sys.stderr.write(f"[merge-segments] 清理 {len(items)} 个冗余分段: "
                             f"{key[1][:80]}（同资源完整文件已在产物中）\n")
            continue
        # v1.22.1：单段组也放行（快手式"整条流一个响应给全"），循环内单段转正
        # 逻辑负责甄别——完整可解码转正，残料丢弃；多段组照旧走拼接。
        if len(items) >= 1 and (total_bytes == 0 or group_bytes / total_bytes >= 0.05):
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
        # ---- 组内排序（v1.22.1 修合并失败根源①：到达序 → 文件序） ----
        ranged = [i for i in items if i.get("range_start") is not None]
        if len(ranged) == len(items):
            # 全带 206 偏移：按文件内偏移排（并行请求到达序 ≠ 文件序）
            items.sort(key=lambda x: x["range_start"])
        else:
            # 混合（init 200 小段 + 206 数据段，或纯 200）：init 置首，其余偏移/序号排。
            # 防损坏护栏：组里混进"无偏移大文件"（完整 200 响应）+ 偏移段同组时，
            # 字节序无法判定——放弃拼接（宁可不拼，不产废品）。
            big_plain = [i for i in items
                         if i.get("range_start") is None and i.get("size", 0) >= 262144]
            if big_plain and ranged:
                sys.stderr.write(f"[merge-segments] 跳过 {gkey[:80]}: 完整文件与分段混组，字节序不可判\n")
                continue

            def _seg_order(i):
                name = urllib.parse.urlparse(i.get("url", "")).path.rsplit("/", 1)[-1].lower()
                if ("init" in name) or (i.get("range_start") is None and i.get("size", 0) < 65536):
                    return (0, 0, 0)  # fMP4 init 段（moov 头）永远在最前
                if i.get("range_start") is not None:
                    return (1, i["range_start"], 0)
                return (2, 0, i.get("seq", 0))

            items.sort(key=_seg_order)
        # 同偏移重叠段去重（两条排序路径共用）：偏移相同 = 同一段重传，只留一个
        if ranged:
            seen_offs, deduped = set(), []
            for i in items:
                off = i.get("range_start")
                if off is not None:
                    if off in seen_offs:
                        continue
                    seen_offs.add(off)
                deduped.append(i)
            items = deduped
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
        if len(items) == 1:
            # v1.22.1 快手压测排雷：整条流单响应完整到达（快手 8.6MB/29s 正片
            # 一个 200/206 就给全，无 init/分段结构）——单段组不是残料。
            # ffprobe 能独立解码且时长 ≥3s = 完整成品，直接转正为最终产物；
            # 解不开/过短才是真残料（照旧弃）。
            i = items[0]
            if _ffprobe_path():
                info = _ffprobe_info(i.get("path", ""))
                try:
                    dur = float((info or {}).get("format", {}).get("duration") or 0)
                except (TypeError, ValueError):
                    dur = 0
                if dur >= 3:
                    # 完整性门（v1.22.1 快手压测二次排雷）：206 部分块也能解出
                    # 5.6s 时长（渐进 mp4 边缘可解码）——首块 1.2MB 曾被误判成品，
                    # 60s 正片全丢。只有 200 全量响应、或 206 覆盖到文件尾
                    # （range_start+size ≥ range_total）才算完整，可转正。
                    _rt = i.get("range_total")
                    _complete = (i.get("status") == 200) or (
                        _rt and (i.get("range_start") or 0) + i.get("size", 0) >= _rt)
                    if not _complete:
                        sys.stderr.write(
                            f"[merge-segments] 单段不完整（{i.get('size', 0)}B/"
                            f"总 {_rt or '?'}B），不转正，交由整取重试\n")
                        continue
                    try:
                        src = Path(i.get("path", ""))
                        if not src.exists():
                            continue
                        dst = output_dir / f"fullvideo_{int(time.time())}_{len(results)}{ext}"
                        src.replace(dst)
                        results.append({
                            "url": i.get("url", ""),
                            "path": str(dst),
                            "content_type": i.get("content_type", ""),
                            "size": dst.stat().st_size,
                            "kind": "merged-segment",
                            "ext": ext,
                            "segments": 1,
                            "group_bytes": group_bytes,
                            "verified_duration_sec": round(dur, 2),
                            "unverified": False,
                            "note": "单响应完整流，直接转正",
                        })
                        sys.stderr.write(f"[merge-segments] 单段完整流转正: "
                                         f"{dst.name} ({dur:.1f}s)\n")
                    except Exception as exc:
                        sys.stderr.write(f"[merge-segments] 单段转正失败: {exc}\n")
            continue
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
                dur_desc = "解码验证失败" if real_dur is None else f"时长 {real_dur:.1f}s < 3s"
                try:
                    out_path.unlink()
                except Exception:
                    pass
                sys.stderr.write(f"[merge-segments] 丢弃 {out_path.name}: {dur_desc}\n")
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
    """产物里有没有可用的视频/音频本体。
    v1.22.1：cache-segment 残件不算——.m4s 扩展名在 VIDEO_EXTS 里，合并失败后
    剩下的一堆残件曾骗过这道门（误判"有视频"→ 跳过 yt-dlp 降级 → 假成功）。"""
    for item in saved:
        if item.get("kind") == "cache-segment":
            continue  # 拼装残件：合并成功升格 merged-segment 才算数
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



def _page_fetch(page, url: str, persona: Optional[Dict] = None) -> Optional[Dict]:
    """在页面上下文里 fetch 资源（带 cookie/referer），返回 {b64,size,ct} 或 None。
    v1.22.1 人设参数：persona 可覆盖 UA（fetch 无法改 UA，仅绕过部分服务端
    UA 校验的场景无效——此路招式在 _refetch 阶梯里由 http 路承担），
    headers 可加 Referer/Range 等自定义头。"""
    try:
        return page.evaluate(
            """
            async (u, hdrs) => {
                const t = (p, ms) => Promise.race([p, new Promise(r => setTimeout(() => r(null), ms))]);
                try {
                    const r = await t(fetch(u, {credentials: 'include', headers: hdrs || {}}), 10000);
                    if (!r || !r.ok) return null;
                    const buf = await t(r.arrayBuffer(), 10000);
                    if (!buf) return null;
                    const bytes = new Uint8Array(buf);
                    if (bytes.length > 80 * 1024 * 1024) return null;
                    let binary = '';
                    for (let i = 0; i < bytes.length; i += 0x8000)
                        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
                    return {b64: btoa(binary), size: bytes.length, ct: r.headers.get('content-type') || '',
                            status: r.status};
                } catch (e) { return null; }
            }
            """,
            [url, (persona or {}).get("headers")],
        )
    except Exception:
        return None



def _http_fetch_media(url: str, page_url: str = "", timeout: int = 20,
                      persona: Optional[Dict] = None) -> Optional[Dict]:
    """脚本侧 HTTP 直下媒体（收割降级路线）：页面上下文 fetch 被跨域 CORS 拦时用。
    带浏览器 UA + 来源页 Referer（防热链基本够用），返回 {b64,size,ct} 或 None。
    v1.22.1：persona 人设支持 {ua, referer, range}——阶梯取流时换身份再试。"""
    import base64

    try:
        p = persona or {}
        headers = {
            "User-Agent": p.get("ua") or random.choice(USER_AGENTS),
            "Accept": p.get("accept") or "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if p.get("range"):
            headers["Range"] = p["range"]
        if p.get("referer"):
            headers["Referer"] = p["referer"]
        elif page_url:
            parsed = urllib.parse.urlparse(page_url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        req = urllib.request.Request(url, headers=headers)
        with _proxy_urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
            status = getattr(resp, "status", None) or resp.getcode()
        if not data or len(data) > 80 * 1024 * 1024:
            return None
        return {"b64": base64.b64encode(data).decode("ascii"), "size": len(data),
                "ct": ct, "status": status}
    except Exception:
        return None



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
        # v1.22.1 网易云压测排雷①：iframe 渲染页（网易云 g_iframe 等）主文档正文
        # 天生极短——正文在子 frame 里，不是壳页。带 iframe 的短正文页不穿透。
        try:
            n_iframes = page.evaluate(
                "() => document.querySelectorAll('iframe').length") or 0
        except Exception:
            n_iframes = 0
        if n_iframes > 0:
            break
        # v1.22.1 网易云压测排雷②：跳向站点首页/裸域 = 降级不是穿透（网易云歌页
        # canonical 指首页，整场收割被带去首页空转）。壳页只会跳向更具体的页面。
        def _specific(u: str) -> bool:
            try:
                p = urllib.parse.urlparse(u)
                return bool(p.path.strip("/") or p.query or p.fragment.strip("#/"))
            except Exception:
                return True
        if not _specific(target) and _specific(current):
            break
        sys.stderr.write(f"[pierce] 跟进落地页壳: {target[:120]}\n")
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            sys.stderr.write(f"[pierce] 跟进失败: {exc}\n")
            break
        visited.add(target)
        current = target
    return current



def _wait_images_complete(page, timeout_sec: float = 3.0) -> bool:
    """等页面 in-flight 图片加载完（img.complete 全 true 或超时）。
    治图集"忽多忽少"：收割太快时部分图还在加载中——没进 DOM 收割清单，
    或进了但 fetch 404 被记失败拉黑。滚一轮等一拍再收，稳定得多。"""
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline:
            pending = page.evaluate(
                "() => [...document.images].filter(i => !i.complete && i.src).length"
            ) or 0
            if pending <= 0:
                return True
            page.wait_for_timeout(400)
        return False
    except Exception:
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
    fail_counts: Dict = {}  # URL→失败次数：瞬时失败跨轮重试（最多2次）
    stall = 0
    for _ in range(max_rounds):
        if len(saved_all) >= max_total:
            break
        _trigger_lazy_media(page)
        _wait_images_complete(page)  # 等 in-flight 图挂载完再收，治忽多忽少
        batch = _harvest_dom_media(page, url, output_dir, allowed_kinds, seen,
                                   save_junk, limit=min(120, max_total - len(saved_all)),
                                   safe=safe, fail_counts=fail_counts)
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
        _wait_images_complete(page)
        tail = _harvest_dom_media(page, url, output_dir, allowed_kinds, seen,
                                  save_junk, limit=min(120, max(0, max_total - len(saved_all))),
                                  safe=safe, fail_counts=fail_counts)
        saved_all.extend(tail)
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    return saved_all



def _harvest_dom_media(
    page, url: str, output_dir: Path, allowed_kinds: set, seen: set, save_junk: bool,
    limit: int = 40, safe: bool = False, fail_counts: Optional[dict] = None,
    dedup_hashes: Optional[set] = None,
) -> List[Dict]:
    """收集页面里所有媒体 URL（DOM/元数据/内嵌JSON），用页面上下文逐个下载。
    与网络嗅探互补：嗅探抓"浏览器请求过的"，收割抓"页面上存在但可能没请求/请求被拦的"。
    fail_counts：URL→失败次数。瞬时失败（超时/被拦）不进 seen，跨轮还有机会重试
    （旧逻辑一次失败永久拉黑，迭代滚动收割后续轮次全跳过——漏图）；最多重试 2 次。
    dedup_hashes：已落盘内容 md5 集（v1.22.1 抖音压测排雷——URL 无扩展名的
    API 流（/play 之类）basename 无区分度，同视频 media.mp4 收割连下 2 份
    逐字节重复 816KB×2；内容 hash 是最后一道通用去重，与 URL 形态无关）。"""
    import base64
    import hashlib

    if fail_counts is None:
        fail_counts = {}

    candidates: List[Dict] = []
    # v1.22.1 网易云压测排雷③：iframe 渲染站（网易云 g_iframe 等）正文/媒体全在
    # 子 frame 里——只收主 frame = 全漏。全 frame 收割（主 frame 天然在首位）。
    try:
        frames = list(page.frames) or [page]
    except Exception:
        frames = [page]
    for frame in frames:
        try:
            dom_items = frame.evaluate(HARVEST_JS) or []
        except Exception:
            dom_items = []
        for it in dom_items:
            candidates.append((it.get("url", ""), it.get("tag", "dom"), it.get("kind", "")))

    # 内嵌 JSON：抖音/B站把媒体直链藏在 script 变量里（同样全 frame 收——
    # 网易云的歌单/歌曲数据在 iframe 文档的 script 里）
    script_texts = []
    for frame in frames:
        try:
            script_texts.append(frame.evaluate(
                "() => [...document.querySelectorAll('script')].map(s => s.textContent || '').join('\\n')"
            ) or "")
        except Exception:
            pass
    script_text = "\n".join(script_texts)
    if script_text:
        # v1.22.1 修快手滑图帖漏正文图集：内嵌 JSON（__INITIAL_STATE__ 等）里的 URL
        # 全是 JSON 转义形态 https:\/\/p2.xxx.com\/a.jpg（还有 \u002F/\u0026 变体），
        # 旧正则要求字面 //——一个都匹配不上，图集 URL 整体漏收。先还原转义再匹配。
        # 另补平台伪扩展 .image/.awebp（…~tplv-photomode-zl.image）。
        plain = (script_text
                 .replace("\\u002F", "/").replace("\\u002f", "/")
                 .replace("\\u0026", "&").replace("\\u0026", "&")
                 .replace("\\/", "/"))
        urls = re.findall(
            r"https?://[^\s\"'\\<>]+?\.(?:mp4|m4s|mp3|m4a|aac|webm|mov|jpg|jpeg|png|webp|image|awebp)(?:\?[^\s\"'\\<>]*)?",
            plain,
        )
        for u in urls[:120]:
            candidates.append((u, "script-json", _media_kind(u, "")))

    saved = []
    fetched = 0
    # 同资源判定键（v1.22.1 修重复拉流）：DOM 里 `//host/media.mp4?a=1`（协议相对）
    # 与 script JSON 里 `https://host/media.mp4?sig=B`（绝对）是同一文件——旧去重比
    # 完整字符串/去 query 字符串都漏判，同一视频被完整拉两份（1.7MB×2）。
    seen_ids = {_url_identity(s) for s in seen}
    # 镜像路径去重（v1.22.1 排雷）：B站 playinfo JSON 把 baseUrl + backupUrl 全列出来
    # （同路径不同 CDN 主机），旧逻辑逐条下载——同一段 m4s 被完整拉 3 份（20.8MB×3，
    # B站实测）。跨 CDN 镜像同路径 = 同一段流，只下首个。seen 里的网络层已抓 URL
    # 也按路径推导，收割与网络嗅探/整取三路互认。
    # v1.22.1 二次排雷：mcdn PCDN 镜像带 /v1/resource 路由前缀——必须用
    # _stream_path_norm 规范化，否则同一流按两种 path 各下一份（B站实测）。
    seen_paths = {
        _stream_path_norm(s)
        for s in seen if isinstance(s, str) and s.startswith(("http://", "https://", "//"))
    }
    # 流类 basename 去重（v1.22.1 抖音压测排雷）：抖音同一视频的多镜像 URL
    # 路径各不相同（tos hash 不同），路径去重失效——media.mp4 被连下 3 份
    # （整取 5.9MB + 收割 2.6MB×2）。带媒体扩展名的流文件同名即同资源。
    seen_stream_names = {_stream_basename(s) for s in seen if isinstance(s, str)}
    seen_stream_names.discard("")
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
        # 站点物料域一票否决（v1.22.1 抖音压测）：douyinstatic.com 引导图、
        # bytednsdoc.com 的 douyin_pc_client.mp4（11MB PC 客户端安装推广视频）
        # 全不是用户内容——域名级预拦，视频图片都拦，省流量防污染。
        if _is_static_asset_host(u):
            continue
        if _url_identity(u) in seen_ids:
            continue
        _upath = _stream_path_norm(u)
        if _upath and _upath in seen_paths:
            continue  # CDN 镜像：同路径不同主机 = 同一段，已由网络层/整取拿过
        # 流类 basename 去重：镜像 URL 路径各异（抖音 tos hash），同名流文件 =
        # 同资源（整取/前一条已拿），拦下不再拉第二份
        _bname = _stream_basename(u)
        if _bname and _bname in seen_stream_names:
            continue
        # 下载前预拦装饰件（v1.22.1）：uhead 头像/emotion 表情在 DOM 和 JSON 里
        # 都会出现——旧逻辑先整份下载再靠落盘前过滤扔掉，白耗流量还混进产物。
        if kind == "image" and _is_junk_resource(u, "", 0, size_strict=False):
            continue
        if fail_counts.get(u, 0) >= 2:
            continue  # 连败 2 次：真死链/真被拦，不再每轮空耗
        item = _page_fetch(page, u)
        if not item:
            # 页面 fetch 被拦（跨域 CDN 无 CORS 头，如小黑盒 cdn.max-c.com）→
            # 降级脚本侧直连：带浏览器 UA + 页面 Referer，公开 CDN 基本都放行
            item = _http_fetch_media(u, page_url=url)
        if not item:
            fail_counts[u] = fail_counts.get(u, 0) + 1
            continue  # 瞬时失败不进 seen：下一轮滚动收割还有机会重试
        seen.add(u)
        seen_ids.add(_url_identity(u))
        if _upath:
            seen_paths.add(_upath)
        if _bname:
            seen_stream_names.add(_bname)
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
        # 内容 hash 去重（v1.22.1 抖音压测排雷，最后一道通用防线）：URL 尺
        # （identity/path/basename）全失效时——抖音无扩展名 API 流 URL 路径
        # 各异——逐字节相同的第二份照样落盘（实测 media.mp4 816KB×2）。
        _h = hashlib.md5(data).hexdigest()
        if dedup_hashes is not None:
            if _h in dedup_hashes:
                sys.stderr.write(f"[harvest] 内容重复丢弃: {Path(u).name[:60]} "
                                 f"({len(data)}B，与已落盘产物逐字节相同)\n")
                continue
            dedup_hashes.add(_h)
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



def _file_direct_download(url: str, dest_dir: Path, safe: bool = False, referer: str = "") -> Optional[Dict]:
    """HTTP 流式直链下载（8MB 分块，不吃内存）。返回 saved 条目或 None（失败/是网页）。
    v1.22.1 实测排雷：Chrome UA 被 UA 黑名单 CDN 403 时（w3.org 实测——
    Chrome UA 3/3 拦、Firefox UA 3/3 过、yt-dlp 也被拦），换 Firefox UA 重试一次。
    这比开浏览器便宜两个数量级，先换装再上真 Chromium（_file_browser_fetch）。"""
    # UA 阶梯：Chrome（默认）→ Firefox（UA 黑名单站）
    _ua_chrome = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    _ua_firefox = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
                   "Gecko/20100101 Firefox/125.0")
    for _ua in (_ua_chrome, _ua_firefox):
        item = _file_direct_download_ua(url, dest_dir, safe, referer, _ua)
        if item is not None:
            return item
        # HTML 壳页返回 None 也别换 UA 重试（换装治不了壳页），但无法区分失败类型——
        # 换 UA 重试只在"异常失败"时才值得，壳页场景二次请求代价小，可接受
    return None


def _file_direct_download_ua(url: str, dest_dir: Path, safe: bool, referer: str, ua: str) -> Optional[Dict]:
    """_file_direct_download 的单 UA 实现（同一段流式下载逻辑跑不同 UA）。
    v1.23.0 断点续传：写 .part 临时文件，中断后下次从 Range: bytes=N- 续传，
    完整收到 EOF 才转正为最终文件名——修复两个实测缺陷：
    ①旧版直接写最终名，中断留下的半截文件"看起来是成品"（<64B 才删）；
    ②2GB 文件下到 90% 断掉只能从头再来。服务器不支持 Range（回 200）就
    清掉 .part 重来；同 URL 已有成品直接复用（幂等，省流量）。"""
    headers = {"User-Agent": ua, **({"Referer": referer} if referer else {})}
    try:
        req = urllib.request.Request(url, headers=headers)
        with _proxy_urlopen(req, timeout=60) as resp:
            ct = (resp.headers.get("Content-Type", "") or "").lower().split(";")[0].strip()
            # 网页不是文件本体（防壳页/错误页存成假文件）
            if ct in ("text/html", "application/xhtml+xml"):
                return None
            fname = _filename_from_disposition(resp, url)
            fname = re.sub(r'[\\/:*?"<>|]+', "_", fname).strip(" .") or "file"
            fname = _cap_filename(fname)
            # 安全模式：可执行文件白名单拦截（下载前就挡）
            if safe and _safe_save_reason(fname, 0):
                sys.stderr.write(f"[safe-block] 文件下载拒绝: {fname}\n")
                return None
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / fname
            # 成品已存在（此前下过同 URL）：幂等复用，不再重下
            if dest.exists() and dest.stat().st_size >= 64:
                return {"url": url, "path": str(dest), "size": dest.stat().st_size,
                        "kind": "file", "content_type": ct, "via": "already-cached"}
            part = dest_dir / (fname + ".part")
            offset = 0
            if part.exists():
                offset = part.stat().st_size
            if offset > 0:
                # 丢掉首次响应，带 Range 续传（.part 保留原则：只有服务器明确
                # 不支持 Range 时才清；网络错误保留，下次接着传）
                try:
                    resp.close()
                except Exception:
                    pass
                try:
                    rreq = urllib.request.Request(
                        url, headers={**headers, "Range": f"bytes={offset}-"})
                    resp = _proxy_urlopen(rreq, timeout=60)
                    if getattr(resp, "status", 0) != 206:
                        resp.close()
                        part.unlink(missing_ok=True)  # 服务器不支持 Range：作废重来
                        offset = 0
                        resp = _proxy_urlopen(urllib.request.Request(url, headers=headers),
                                              timeout=60)
                except urllib.error.HTTPError as he:
                    if he.code == 416 and offset >= 64:
                        # 续传起点==文件总长：.part 其实已完整，直接转正
                        sys.stderr.write(f"[file-dl] 断点续传完成: {fname}"
                                         f"（.part 已是完整文件）\n")
                        part.replace(dest)
                        return {"url": url, "path": str(dest), "size": offset,
                                "kind": "file", "content_type": ct, "via": "direct",
                                "resumed_from": offset}
                    sys.stderr.write(f"[file-dl] 续传请求失败({he.code})，.part 保留下次再续\n")
                    return None
                except Exception:
                    return None  # 网络错误：.part 保留，下次同 URL 自动续传
            size = offset
            over_limit = False
            try:
                with open(part, ("ab" if offset else "wb")) as f:
                    while True:
                        chunk = resp.read(8 * 1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        # 安全模式 2GB 上限必须在流式过程中执行（预检 content-length
                        # 可伪造/缺失；此前边下边写不查大小，恶意大文件能写满磁盘）
                        if safe and size > SAFE_MAX_FILE_BYTES:
                            over_limit = True
                            break
                        f.write(chunk)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            if over_limit:
                part.unlink(missing_ok=True)
                sys.stderr.write(f"[safe-block] 文件超过2GB上限，已中断删除: {url[:120]}\n")
                return None
            # 正常读到 EOF = 完整：.part 转正。异常中断走不到这里，
            # .part 保留（文件名带 .part 明示未完成），下次同 URL 自动续传
            if size < 64:
                part.unlink(missing_ok=True)
                return None
            if offset:
                sys.stderr.write(f"[file-dl] 断点续传完成: {fname}（续传自 {offset}B）\n")
            part.replace(dest)
            return {"url": url, "path": str(dest), "size": size, "kind": "file",
                    "content_type": ct, "via": "direct",
                    **({"resumed_from": offset} if offset else {})}
    except Exception as exc:
        sys.stderr.write(f"[file-dl] error: {exc} url={url[:120]}\n")
        return None



def _file_browser_fetch(url: str, output_dir: Path, safe: bool = False,
                        referer: str = "") -> Optional[Dict]:
    """文件阶梯第 2 招（v1.22.1 实测排雷）：真 Chromium 指纹取文件。
    治 TLS 指纹拦截站（JA3）：urllib 同样的请求头被 403、curl/浏览器 200
    （w3.org 实测复现）——服务器验的不是头是"谁在握手"。
    两条子路都流式：inline 响应走 resp.body()（content-length 预检防大文件
    涨内存）；触发下载事件走 Chromium 原生落盘 + 磁盘拷贝（零内存压力）。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    with sync_playwright() as p:
        browser = None
        try:
            browser = _launch_chromium(p, headless=True, args=_browser_launch_args(safe))
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                accept_downloads=True,
                ignore_https_errors=True,
            )
            _apply_stealth(context, "basic")
            page = context.new_page()
            download_holder: Dict = {}
            page.on("download", lambda d: download_holder.setdefault("d", d))
            resp = None
            _goto_err = ""
            try:
                _goto_kw = {"wait_until": "commit", "timeout": 30000}
                if referer:
                    _goto_kw["referer"] = referer  # 热链站：来源页当 referer
                resp = page.goto(url, **_goto_kw)
            except Exception as exc:
                resp = None
                _goto_err = str(exc)
            # 实测排雷：goto 抛 "Download is starting" 时下载事件还在路上（异步后到），
            # 异常后立刻查事件必查空——必须轮询等事件到达。
            if not download_holder.get("d"):
                _wait = 12 if "download" in _goto_err.lower() else 3
                _deadline = time.time() + _wait
                while not download_holder.get("d") and time.time() < _deadline:
                    try:
                        page.wait_for_timeout(200)
                    except Exception:
                        break
            # 子路1：下载事件（Chromium 已流式落盘到临时文件）
            if download_holder.get("d"):
                try:
                    d = download_holder["d"]
                    src = Path(d.path())
                    if src.exists() and src.stat().st_size >= 64:
                        fname = _cap_filename(d.suggested_filename or "file")
                        if safe:
                            reason = _safe_save_reason(fname, src.stat().st_size)
                            if reason:
                                sys.stderr.write(f"[safe-block] 浏览器取件拒绝 {reason}: {fname}\n")
                                return None
                        output_dir.mkdir(parents=True, exist_ok=True)
                        dst = output_dir / fname
                        import shutil
                        shutil.move(str(src), str(dst))
                        return {"url": url, "path": str(dst), "size": dst.stat().st_size,
                                "kind": "file", "via": "browser-download"}
                except Exception as exc:
                    sys.stderr.write(f"[file-dl:browser] download error: {exc}\n")
            # 子路2：inline 响应体（PDF 预览等）
            if resp is not None:
                try:
                    ct = (resp.headers.get("content-type", "") or "").lower().split(";")[0].strip()
                    if ct in ("text/html", "application/xhtml+xml"):
                        return None  # 网页壳：不算文件
                    cl = resp.headers.get("content-length", "")
                    if cl.isdigit() and int(cl) > 512 * 1024 * 1024:
                        sys.stderr.write(f"[file-dl:browser] 响应体过大({int(cl)//1048576}MB)不走内存路: {url[:120]}\n")
                        return None
                    body = resp.body()
                    if len(body) >= 64:
                        if safe:
                            reason = _safe_save_reason(_safe_filename(url, ct, 0), len(body))
                            if reason:
                                sys.stderr.write(f"[safe-block] 浏览器取件拒绝 {reason}: {url[:120]}\n")
                                return None
                        path = _save_bytes(body, output_dir, url, ct, 80000)
                        return {"url": url, "path": str(path), "size": len(body),
                                "kind": "file", "via": "browser-body"}
                except Exception as exc:
                    sys.stderr.write(f"[file-dl:browser] body error: {exc}\n")
            return None
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass


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
            # safe 落盘后大小复核（对齐浏览器 on_download 的防护，堵 2GB 漏洞）
            if safe and dest.exists() and dest.stat().st_size > SAFE_MAX_FILE_BYTES:
                dest.unlink()
                sys.stderr.write("[safe-block] 下载拒绝: 超过大小上限，已删除\n")
                continue
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
    fname = _cap_filename(fname) or "file"
    if safe and _safe_save_reason(fname, len(data)):
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / fname
    path.write_bytes(data)
    return {"url": url, "path": str(path), "size": len(data), "kind": "file",
            "content_type": ct, "via": "page-fetch"}



def _files_route(
    url: str, output_dir: Path, headed: bool = False, safe: bool = False,
    zip_bundle: bool = False, click_download: bool = False, stealth: str = "full",
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

    # 1) 文件直链（两招阶梯：urllib 流式 → Chromium 指纹，治 JA3 拦截）
    if urllib.parse.urlparse(url).path.lower().endswith(FILE_EXTS):
        item = _file_direct_download(url, output_dir, safe)
        if not item:
            item = _file_browser_fetch(url, output_dir, safe)
        if item:
            return {**base, "saved": [item], "count": 1}
        return {**base, "saved": [], "count": 0,
                "error": "file direct download failed (link dead / TLS-blocked / is a webpage)"}

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
                    # 启动样板归一（批 3）：自签证书容忍（下载站常自签 HTTPS）
                    browser, context, page, blocked = _open_page(
                        p, headed, safe, stealth, ignore_https_errors=True)
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
    max_chapters: int = 100, allow_chapters: bool = True, stealth: str = "full",
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
                    browser, context, page, blocked = _open_page(p, headed, safe, stealth)
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
                                human_scroll(page, 2000)
                                page.wait_for_timeout(600)
                            item = _save_page_text(page, final_url, output_dir)
                    else:
                        # 普通文章：滚动触发懒加载后单页保存
                        for _ in range(3):
                            human_scroll(page, 2000)
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


def _harvest_route(url: str, output_dir: Path, headed: bool, safe: bool,
                   save_junk: bool, allowed_kinds: set,
                   cookie_file: str = "", cookies_from_browser: str = "",
                   profile_dir: Optional[Path] = None, stealth: str = "full") -> Dict:
    """harvest 路线（自 auto_save_url 内联块原样提出，零逻辑改动）：
    DOM/元数据/JSON 收割 + 页面上下文下载，快（无长等待），适合照片/音频。"""
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
                context = None
                try:
                    browser, context, page, blocked = _open_page(
                        p, headed, safe, stealth,
                        profile_dir=profile_dir,
                        cookie_file=cookie_file, cookies_from_browser=cookies_from_browser,
                        cookie_route_name="harvest")
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
                        # v1.22.1 网易云压测排雷④：跳向站点首页/裸域 = 降级不是跟进
                        # （网易云歌页 canonical 指首页，0 收割时被带去首页再空转一轮）
                        try:
                            _p = urllib.parse.urlparse(real_target or "")
                            if not (_p.path.strip("/") or _p.query or _p.fragment.strip("#/")):
                                real_target = None
                        except Exception:
                            pass
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
                    elif context is not None:
                        context.close()  # 持久化上下文：close 才把 cookie/缓存刷进用户目录
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


def _browser_route(url: str, output_dir: Path, wait_seconds: int, method: str,
                   headed: bool, max_wait: int, auto_wait: bool,
                   save_junk: bool, keep_segments: bool, allowed_kinds: set,
                   safe: bool, cookie_file: str = "", cookies_from_browser: str = "",
                   profile_dir: Optional[Path] = None, stealth: str = "full",
                   yt_error: Optional[str] = None, ytdlp_fallback: bool = True) -> Dict:
    """browser/cache/auto 浏览器阶段（自 auto_save_url 内联块原样提出，零逻辑改动）：
    真实 Chromium 边播边缓存：网络嗅探 + 206 分段 + blob/MSE + DOM 收割 + 分段合并，
    wait 自适应，只抓到封面时自动降级 yt-dlp。
    ytdlp_fallback=False：chain 内调用专用——chain 已有独立 ytdlp 步与链尾 cookie 复试，
    内部再降级会让 yt-dlp 整链跑 3 次（压测实测），且 attempts 错误被 yt-dlp 文本顶替。"""
    saved: List[Dict] = []
    seen: set = set()
    body_hashes: set = set()  # 内容指纹：同文件重复响应（字节相同）去重（两种模式都开）
    media_streams: Dict[str, Dict] = {}  # 分段流账本（先要后抓）：URL → {total, max_seg}
    dup_segs = {"count": 0}  # cache 模式字节级重复分段计数（登录墙/服务器无视 Range 的诊断信号）
    counter = 0

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = None
        context = None
        try:
            # 启动样板归一（批 3）：下载信任 + 自签证书容忍 + 随机视口（拟真）全开
            browser, context, page, blocked = _open_page(
                p, headed, safe, stealth,
                profile_dir=profile_dir,
                accept_downloads=True,
                ignore_https_errors=True,
                random_viewport=True,
                cookie_file=cookie_file, cookies_from_browser=cookies_from_browser,
                cookie_route_name="浏览器路线")

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
                    # 超大响应预检：content-length 明示 >1GB 直接跳过（body() 会整包进内存）
                    try:
                        cl = response.headers.get("content-length", "")
                        if cl and int(cl) > 1024 * 1024 * 1024:
                            sys.stderr.write(f"[network-save] 跳过超大响应(>1GB): {response.url[:100]}\n")
                            return
                    except ValueError:
                        pass
                    # key 统一用完整 URL：同路径不同 query 是不同文件（旧逻辑砍掉 query
                    # 会误丢，YouTube watch?v= 同理）；真重复（同文件重发）靠字节指纹砍
                    key = response.url
                    if key in seen:
                        return
                    seen.add(key)
                    # 206 分段偏移捕获（v1.22.1 修合并失败根源①）：Content-Range 记下
                    # 文件内偏移，合并时按偏移排序——并行请求到达序 ≠ 文件序，旧逻辑
                    # 按到达序字节拼接 = 必然损坏 → 解码验证必挂。
                    range_start = None
                    range_total = None
                    try:
                        cr = response.headers.get("content-range", "")
                        m = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", cr)
                        if m:
                            range_start = int(m.group(1))
                            if m.group(3) != "*":
                                range_total = int(m.group(3))
                    except Exception:
                        range_start = None
                    try:
                        body = response.body()
                    except Exception as exc:
                        # v1.22.1 快手压测排雷：大体积流响应体在 inspector 缓存被
                        # 逐出（或页面已导航走）→ body() 拿不到，整条流静默丢失
                        # （快手实测：60s 正片丢、5.6s 推荐流反而成了"成品"）。
                        # URL 记入整取账本（先要后抓），后续 _refetch_full_media
                        # 用 HTTP 全量重取；CL 不可知时给 0（该 URL 不具候选资格）。
                        sys.stderr.write(f"[network-save] body 不可读（{str(exc)[:60]}），"
                                         f"记入整取账本: {response.url[:100]}\n")
                        if kind in ("video", "audio"):
                            try:
                                _cl = int(cl or 0)
                            except (TypeError, ValueError):
                                _cl = 0
                            msi = media_streams.setdefault(
                                response.url, {"total": 0, "max_seg": 0})
                            msi["total"] = max(msi.get("total") or 0, _cl or (range_total or 0))
                        return
                    # 小体量门槛：普通响应 1KB 起；缓存分段模式放宽到 64B——
                    # fMP4 init 段（moov 头）常只有几百字节，旧一刀切 1KB 把它砍了，
                    # 后面 m4s 分段拼出来永远没有 moov 头 = 必然解不开（v1.22.1 根源②）。
                    seg_ext = Path(urllib.parse.urlparse(response.url).path).suffix.lower()
                    min_body = 64 if (capture_cache and seg_ext in (".mp4", ".m4s", ".ts")) else 1024
                    if len(body) < min_body:
                        return
                    # 内容指纹去重（v1.22.1 扩到 cache 分段）：字节级相同的响应 = 重传，
                    # 只留一份。治两类实测病：①登录墙站无视 Range 请求，每次都回同一个
                    # 200KB 块（抖音实测 11×204801B 重复块，旧逻辑拼 11 份必坏再丢弃）；
                    # ②同一 init 段(moov头)经两条 URL 到达，拼两个 moov 也是坏文件。
                    body_hash = hashlib.md5(body).hexdigest()
                    if body_hash in body_hashes:
                        if capture_cache:
                            dup_segs["count"] += 1
                            if dup_segs["count"] in (3, 10):
                                sys.stderr.write(
                                    f"[network-save] 已连续丢弃 {dup_segs['count']} 个字节级重复分段："
                                    "服务器未按 Range 放流（疑似登录墙/截断），"
                                    "建议带 cookie 重试（--cookies-from-browser / --login-rescue）\n")
                        return
                    body_hashes.add(body_hash)
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
                        # 先要后抓线索（v1.22.1 范式升级）：视频/音频分段流记下
                        # "整文件重取"候选——Content-Range 总长远大于单块 = 单文件
                        # Range 流（抖音式），完整 GET 大概率能拿到全量。
                        if kind in ("video", "audio"):
                            msi = media_streams.setdefault(
                                response.url, {"total": 0, "max_seg": 0})
                            if range_total:
                                msi["total"] = max(msi["total"], range_total)
                            msi["max_seg"] = max(msi["max_seg"], len(body))
                        saved.append(
                            {
                                "url": response.url,
                                "path": str(path),
                                "content_type": content_type,
                                "size": len(body),
                                "status": response.status,
                                "seq": counter,
                                "range_start": range_start,
                                "range_total": range_total,
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
                    # 站点文件名硬限长（v1.22.1）：超长名 + 深目录会撞 Windows 260 上限，
                    # 三路写入全挂。stem 截 80 保扩展名。
                    filename = _cap_filename(filename)
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

            # 模拟真实用户滚动，触发懒加载的视频/图片（v1.22.0 升级拟人轨迹/滚动）。
            for _ in range(5):
                human_move(page, random.randint(200, 1500), random.randint(200, 900))
                human_scroll(page, 900)
                page.wait_for_timeout(1200)
            # 再滚回顶部，重新触发一遍懒加载。
            human_scroll(page, -5000)
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

            # 先要后抓（v1.22.1 范式升级）：分段流整文件重取优先——抖音类站
            # 播放器的 Range 请求被服务器糊弄（永远同一个 ~200KB 块），但完整
            # GET 照常给全量。要到了免拼装；要不到继续走下面的分段抓取合并。
            # 放 harvest 前：重取成功的 URL 进 seen，收割不再重复下载同一资源。
            try:
                refetched = _refetch_full_media(page, url, media_streams, output_dir, safe, seen)
                if refetched:
                    saved.extend(refetched)
            except Exception as exc:
                sys.stderr.write(f"[refetch] error: {exc}\n")

            # 缓存方式3：DOM/元数据/内嵌JSON 收割 + 页面上下文下载（照片/音频常靠这路拿到）。
            try:
                # 已落盘内容 hash 集（收割内容去重用）：嗅探/整取已拿到的流/图
                # 逐字节重复的第二份不再落盘（抖音实测 media.mp4 816KB×2）。
                _dh = set()
                for _i in saved:
                    try:
                        _fp = Path(_i.get("path", ""))
                        if _fp.exists() and _fp.stat().st_size:
                            _dh.add(hashlib.md5(_fp.read_bytes()).hexdigest())
                    except Exception:
                        pass
                saved.extend(_harvest_dom_media(page, url, output_dir, allowed_kinds,
                                                seen, save_junk, safe=safe,
                                                dedup_hashes=_dh))
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
            elif cleanup_info.get("removed_paths"):
                # 无合并产物但有分段被整文件重取取代：剔除已删盘的 phantom 条目
                _rp = cleanup_info["removed_paths"]
                saved = [i for i in saved if i.get("path") not in _rp]
        finally:
            if browser is not None:
                browser.close()
            elif context is not None:
                context.close()  # 持久化上下文：close 才把 cookie/缓存刷进用户目录

    if saved:
        has_media = _has_video_or_audio(saved)
        # browser/cache 模式如果只抓到图片/封面，没有视频本体，自动降级 yt-dlp。
        if method in ("browser", "cache") and not has_media and ytdlp_fallback:
            # 内部降级也要带登录态：不带 cookie 的 yt-dlp 过不了登录墙（同链尾复试逻辑）
            yt_fb, yt_error = _download_with_ytdlp(url, output_dir, safe,
                                                    cookie_file=cookie_file,
                                                    cookies_from_browser=cookies_from_browser)
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
            # 质量分级（v1.22.1）：junk = 只有分段残件/封面图等零交集产物。
            # 独立调用方据此降级；chain 据此不截断兜底链（垃圾不算成功）。
            "quality": _assess_saved_quality(saved, allowed_kinds),
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

    # browser/cache 模式什么都没抓到，再试 yt-dlp（chain 内调用时跳过：chain 已有独立 ytdlp 步）。
    if method in ("browser", "cache") and ytdlp_fallback:
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
        # ytdlp_fallback=False 时如实不标注 yt-dlp 错误（chain 的 attempts 不再被误导）
        **({} if not ytdlp_fallback else {"yt_dlp_error": yt_error or "yt-dlp returned no files"}),
    }
    if safe:
        out["safe_mode"] = True
        try:
            out["blocked"] = blocked
        except NameError:
            pass
    return out
