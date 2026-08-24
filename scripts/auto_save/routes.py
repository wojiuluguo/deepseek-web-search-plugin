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
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .browser_base import _open_page, _save_bytes, _wait_for_render
from .constants import AUDIO_EXTS, FILE_EXTS, SAFE_MAX_FILE_BYTES, USER_AGENTS, VIDEO_EXTS
from .ffmpeg import (_decoded_duration, _ffmpeg_path, _ffprobe_info, _ffprobe_path,
                     _probe_resolution)
from .humanize import human_move, human_scroll
from .urlrules import (CLICK_DOWNLOAD_FILE_TYPES, DOWNLOAD_BUTTON_TEXTS,
                       MEDIA_EXTENSIONS, SHELL_BODY_TEXT_LIMIT, _decode_redirect_url,
                       _decode_scheme_target, _ext_from_content_type, _extract_shell_redirect,
                       _filename_from_disposition, _host_matches, _is_app_store_url,
                       _is_junk_resource, _is_media_url, _is_split_stream_fragment, _media_kind,
                       _safe_filename, _safe_save_reason, _url_group_key)

__all__ = [
    "HARVEST_JS", "FILE_LINKS_JS", "CHAPTER_LINKS_JS",
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
        # 文件名限长（v1.22.0 压测修复）：无专用适配器的站点（汽水音乐等）generic
        # extractor 会把 URL 长参数（sec_sharer_id 长 base64 等）塞进 title/id，
        # Windows 路径超 260 上限 → .part 打开 Errno 2 三路全挂。
        # 三道保险：title 截 60 + id 截 30 + trim_file_name 清洗后再硬限 120。
        "outtmpl": str(output_dir / "%(title).60s [%(id).30s].%(ext)s"),
        "trim_file_name": 120,
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
) -> List[Dict]:
    """收集页面里所有媒体 URL（DOM/元数据/内嵌JSON），用页面上下文逐个下载。
    与网络嗅探互补：嗅探抓"浏览器请求过的"，收割抓"页面上存在但可能没请求/请求被拦的"。
    fail_counts：URL→失败次数。瞬时失败（超时/被拦）不进 seen，跨轮还有机会重试
    （旧逻辑一次失败永久拉黑，迭代滚动收割后续轮次全跳过——漏图）；最多重试 2 次。"""
    import base64

    if fail_counts is None:
        fail_counts = {}

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
        # 网络嗅探已存过的同路径资源也别重收（seen 里现在存完整 URL，带 query）
        if any(s.split("?")[0] == u.split("?")[0] for s in seen):
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
            over_limit = False
            with open(path, "wb") as f:
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
            if over_limit:
                path.unlink(missing_ok=True)
                sys.stderr.write(f"[safe-block] 文件超过2GB上限，已中断删除: {url[:120]}\n")
                return None
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
    body_hashes: set = set()  # 非 cache 模式内容指纹：同文件重复响应（字节相同）去重
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
                    body = response.body()
                    if len(body) < 1024:
                        return
                    if not capture_cache:
                        # 内容指纹去重：同一文件的重复响应（缓存穿透/重试）字节相同即砍
                        body_hash = hashlib.md5(body).hexdigest()
                        if body_hash in body_hashes:
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
