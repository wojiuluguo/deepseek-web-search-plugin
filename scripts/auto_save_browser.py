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
import hashlib
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

# ---- 拆分（v1.21.1 第 1 批，绝对安全级）：常量/ffmpeg/cookies 移入 auto_save 包 ----
# 本文件仍是唯一命令行入口与唯一被外部 import 的模块；此处 re-import 保持全部旧名可用。
from auto_save.constants import (
    STEALTH_JS, USER_AGENTS, VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS, MEDIA_EXTENSIONS,
    CONTENT_TYPE_EXT, VIDEO_LIKE_HOSTS, IMAGE_LIKE_HOSTS, AUDIO_LIKE_HOSTS, FILE_EXTS,
    PROFILE_DIR, SEARCH_REDIRECT_HOSTS, JUNK_EXTENSIONS, JUNK_URL_HINTS,
    DANGEROUS_EXTS, MINING_DOMAINS, STRATUM_PORTS, SAFE_ALLOWED_EXTS, SAFE_MAX_FILE_BYTES,
    SHARE_SHORTLINK_HOSTS, LOGIN_WALL_HOSTS,
)
from auto_save.ffmpeg import (
    _find_tool, _ffmpeg_path, _ffprobe_path, _decoded_duration, _ffprobe_info, _probe_resolution,
)
from auto_save.cookies import (
    _parse_netscape_cookies, _add_cookies_to_context, _browser_cookies_to_playwright,
    _inject_login_cookies, _base_domain, _login_rescue,
)
# ---- 拆分（v1.21.1 第 2 批，绝对安全级）：URL/媒体/安全判定纯函数移入 auto_save.urlrules ----
from auto_save.urlrules import (
    APP_STORE_HOSTS, SHELL_BODY_TEXT_LIMIT, CLICK_DOWNLOAD_FILE_TYPES, DOWNLOAD_BUTTON_TEXTS,
    _decode_redirect_url, _is_media_url, _media_kind, _ext_from_content_type, _host_matches,
    _safe_request_reason, _safe_save_reason, _is_junk_resource, _safe_filename,
    _url_group_key, _url_identity, _cap_filename, _resolve_share_redirect,
    _assess_saved_quality,
    _extract_shell_redirect, _is_split_stream_fragment,
    _filename_from_disposition, _is_app_store_url, _decode_scheme_target,
)
# ---- 拆分（v1.22.0 第 3 批，比较安全级）：浏览器基建移入 auto_save.browser_base ----
# _setup_safe_mode/_browser_launch_args/_apply_stealth/_save_bytes 搬迁零逻辑改动；
# _browser_launch_args/_apply_stealth 内部挂钩 --real-headless 拟真（与 --stealth 正交）。
from auto_save.browser_base import (
    _setup_safe_mode, _browser_launch_args, _apply_stealth, _save_bytes,
)
# ---- 新增（v1.22.0）：拟人输入 + 无头拟真 ----
# humanize：行为层拟真（贝塞尔轨迹/微偏移按压/正态键间隔/分步滚动），--humanize on|off
from auto_save.humanize import (
    human_click, human_move, human_type, human_scroll, human_pause, set_humanize,
)
# realheadless：无头静态指纹补丁 + 真 Chrome 探测，--real-headless on|off
from auto_save import realheadless
# ---- 拆分（v1.22.0 批 B）：下载路线层移入 auto_save.routes ----
# 21 个路线助手搬迁 + auto_save_url 内联两大块提成 _harvest_route/_browser_route；
# 调度器 auto_save_url 本体留在本文件（chain 递归+分派薄壳），全部零逻辑改动。
from auto_save.routes import (
    HARVEST_JS, FILE_LINKS_JS, CHAPTER_LINKS_JS,
    _download_direct, _download_with_ytdlp, _http_fetch_media, _page_fetch,
    _file_direct_download, _goto_pierce_shell, _trigger_lazy_media,
    _auto_play_videos, _wait_images_complete, _extract_body_text,
    _save_page_text, _zip_bundle, _try_click_download, _page_fetch_download,
    _files_route, _text_route, _capture_blob_media, _harvest_dom_media,
    _harvest_lazy_all, _merge_segments, _has_video_or_audio,
    _harvest_route, _browser_route,
)


# （ffmpeg/ffprobe 探测与解码验证已移入 auto_save/ffmpeg.py）

# （垃圾过滤/安全模式常量已移入 auto_save/constants.py）

# （URL/媒体/安全判定纯函数已移入 auto_save/urlrules.py）

# （浏览器基建 _setup_safe_mode/_browser_launch_args/_apply_stealth/_save_bytes
#   已移入 auto_save/browser_base.py，v1.22.0 第 3 批）
# ---- 拆分（v1.22.0 批 A）：视觉协议层/截图工具移入 auto_save 包 ----
# vision.py：_vision_route 会话协议 + DOM 精准操作 + 元素标注/验证码 JS + 看门狗；
# shots.py：_screen_info/_capture_full_page/_shot_viewport/_screenshot_standalone（--screenshot 共用）；
# _wait_for_render 移入 browser_base.py。全部零逻辑搬迁，此处 re-import 保持旧名可用。
from auto_save.browser_base import _wait_for_render
from auto_save.shots import (
    VISION_MAX_IMAGE_EDGE, VISION_SEGMENT_MAX_PX,
    _screen_info, _scroll_page_to_bottom, _capture_full_page, _shot_viewport, _screenshot_standalone,
)
from auto_save.vision import (
    VISION_MODEL_NAME, VISION_DEFAULT_MAX_SCREENS, VISION_ACTIONS,
    MOUSE_TRACK_JS, CURSOR_OVERLAY_JS, ELEMENTS_JS, CAPTCHA_JS,
    _is_vision_model, _vision_api_hint, _free_port, _eval_watchdog_thread,
    _vision_find_el, _vision_el_center, _click_flash, _vision_dom_action,
    _vision_dom_type, _vision_exec_action, _skill_version, _vision_route,
)


# （Netscape 解析/浏览器提取/登录接种/登录兜底已移入 auto_save/cookies.py）




# ---- 拆分（v1.22.0 结构优化批 1）：意图检测/选路/结果挑选移入 auto_save.routing ----
# 本文件仍是唯一命令行入口与唯一被外部 import 的门面；此处 re-import 保持全部旧名可用。
from auto_save.routing import (
    _is_bare_homepage, _platform_search_url, _pick_video_url,
    _detect_media_intent, _detect_url_media_type, _route_method,
    _pick_media_url, _baidu_image_search_url, _search_first_media_url,
)


# （意图路由 9 函数已移入 auto_save/routing.py，v1.22.0 结构优化批 1）
# （DOM 收割/文件电路/文本电路实现已移入 auto_save/routes.py，v1.22.0 批 B——
#   auto_save_url 调度本体留在本文件）


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
    vision_viewport: tuple = (1440, 900),
    cookie_file: str = "",
    cookies_from_browser: str = "",
    profile_dir: Optional[Path] = None,
    captcha_mode: str = "off",
    idle_timeout: Optional[int] = None,
    linger: bool = False,
    stealth: str = "full",
    login_rescue: bool = False,
    ytdlp_fallback: bool = True,
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

    # 分享短链预解析（v1.22.1 修 note 转路盲区）：v.douyin.com/xhslink.com 短链不含
    # /note/，下方预判（子串检查）永远不触发，ytdlp 白撞 Unsupported URL。先跟一次
    # 重定向拿真实 URL 再判。解析失败按原 URL 走（浏览器路线自己会跟跳，不会更糟）。
    effective_url = url
    try:
        _sl_host = urllib.parse.urlparse(url).netloc.lower()
        if any(_host_matches(_sl_host, d) for d in SHARE_SHORTLINK_HOSTS):
            resolved = _resolve_share_redirect(url)
            if resolved:
                effective_url = _decode_redirect_url(resolved) or resolved
                sys.stderr.write(f"[note] 短链解析: {url[:60]} → {effective_url[:100]}\n")
    except Exception:
        effective_url = url

    # 媒体类型过滤：--media-type video,audio,image 任意组合，空则全部
    allowed_kinds = {t.strip() for t in re.split(r"[,，]", (media_types or "").strip()) if t.strip()}
    if not allowed_kinds:
        allowed_kinds = {"video", "audio", "image"}

    # 抖音图文帖（/note/…）预判：yt-dlp 不支持 note URL（直接 Unsupported URL 报错），
    # 自动转 harvest 图集收割——原图走页面上下文下载，不再白撞一墙。
    # v1.22.0 压测修正：①harvest 空转/只收到图时必须留痕（stderr + attempts），
    # 否则链路无法诊断（用户误判"转路没触发"）；②音频类 note（音乐分享帖）harvest
    # 收不到流媒体，若用户要 audio/video 不能因收到几张图就提前 return，落 chain 抓流，
    # chain 失败时 harvest 收获兜底返回、成功时合并（文件已落盘，不能丢）。
    # v1.22.1：用短链解析后的 effective_url 判定（短链本身看不出 note）。
    note_harvest = None
    if "/note/" in effective_url and method in ("chain", "auto", "ytdlp"):
        try:
            r = auto_save_url(url, output_dir, wait_seconds, "harvest", headed, max_wait,
                              auto_wait, save_junk, keep_segments, media_types, safe,
                              cookie_file=cookie_file,
                              cookies_from_browser=cookies_from_browser,
                              profile_dir=profile_dir,
                              stealth=stealth)
            if r.get("saved"):
                wants_av = bool({"audio", "video"} & allowed_kinds)
                has_av = any(
                    Path(s.get("path", "")).suffix.lower() in set(AUDIO_EXTS) | set(VIDEO_EXTS)
                    for s in r["saved"]
                )
                if not wants_av or has_av:
                    r["method"] = f"{method}->harvest(note)"
                    r["note_auto_rerouted"] = True
                    return r
                # 收到的只有图/元数据，用户要的音频视频流 harvest 拿不到 → chain 继续
                note_harvest = r
                sys.stderr.write("[note] /note/ 预判 harvest 只收到图片类内容，"
                                 "音频/视频流继续走 chain 抓取\n")
            else:
                sys.stderr.write("[note] /note/ 预判 harvest 未收到内容"
                                 "（图集可能需登录），chain 兜底\n")
                if method in ("auto", "ytdlp"):
                    return r
        except Exception as exc:
            sys.stderr.write(f"[note] /note/ 预判 harvest 异常: {exc}，chain 兜底\n")

    # chain：按顺序尝试多个下载/缓存方式，哪个成功用哪个；text 兜底保证纯文本页也能存。
    if method == "chain":
        attempts = []
        # note 预判跑过就先记一笔（哪怕空转），JSON attempts 可诊断转路是否触发
        if "/note/" in url:
            attempts.append({
                "method": "harvest(note)",
                "count": len(note_harvest["saved"]) if note_harvest else 0,
                "error": None if note_harvest else "harvest 未收到内容(可能需登录)",
            })
        last_result = None
        # 质量门（v1.22.1 修"假成功截断兜底链"）：垃圾成果不算成功，链继续往下兜。
        # 判据平台无关：产物媒体类型与用户意图的交集 + 残件不算成果。
        # 抖音封面图、快手头像、任何站的"抓了个寂寞"都按同一把尺子量。
        _q_rank = {"full": 3, "partial": 2, "junk": 1, "empty": 0}
        best_result = None  # 全链无正果时返回质量最高的那环（聊胜于无 + 如实标注）
        # 文件直链意图（v1.22.1 排雷修复B）：URL 以文件扩展名结尾时，拿到文件本体
        # 就是正片——zip/pdf 不在 video/audio/image 里，旧质量门会判 junk 导致
        # 全链白跑 6 环（含起浏览器）。文件意图下 file/direct 条目直接记 full。
        _explicit_file = urllib.parse.urlparse(url).path.lower().endswith(FILE_EXTS)

        def _q(result):
            # 文件直链意图：拿到文件本体就是正片（kind 不限——direct/files/yt-dlp/browser
            # 路线都能交付文件；排除 text 挑战页残文和 cache-segment 残件）
            # v1.22.1 排雷：必须直接赋值——_browser_route 返回时已自带 quality
            # （常是 junk：file 不在媒体 kind 里），setdefault 升不了级，
            # 文件已到手链却继续空跑、最终按 junk 上报。
            if _explicit_file and any(
                    i.get("kind") not in ("text", "cache-segment", None)
                    for i in result.get("saved", [])):
                result["quality"] = "full"
                return result["quality"]
            result.setdefault("quality", _assess_saved_quality(result.get("saved", []), allowed_kinds))
            return result["quality"]

        # 兜底链扩容：direct → ytdlp → browser → cache → harvest(媒体页兜底) → text
        # 有 cookie 时追加 ytdlp+cookie 复试（第一遍未带 cookie 的 ytdlp 失败多半是登录墙）
        chain_methods = ["direct", "ytdlp", "browser", "cache", "harvest", "text"]
        # 登录墙直通（v1.22.1）：已知登录墙站（抖音等）且未带任何登录态时，
        # direct（只会拿到 HTML 壳页）/ytdlp（Fresh cookies needed）必败——
        # 不再白跑这两步，直上 browser 硬抓。带 cookie 时 ytdlp 仍有戏，照常走全链。
        try:
            _lw_host = urllib.parse.urlparse(url).netloc.lower()
            if (any(_host_matches(_lw_host, d) for d in LOGIN_WALL_HOSTS)
                    and not (cookie_file or cookies_from_browser)):
                chain_methods = ["browser", "cache", "harvest", "text"]
                sys.stderr.write("[chain] 登录墙站点且未带 cookie：跳过 direct/ytdlp 直上 browser\n")
        except Exception:
            pass
        for m in chain_methods:
            try:
                if m == "text":
                    # chain 兜底的 text 只做单页快速正文（目录逐章是 text 专用线的活，别拖死 chain）
                    result = auto_save_url(url, output_dir, wait_seconds, m, headed, max_wait,
                                           auto_wait, save_junk, keep_segments, media_types, safe,
                                           max_chapters=1, allow_chapters=False)
                elif m == "harvest":
                    # harvest 在 chain 里只收图片/音频（视频已由 browser/cache 干过一遍）。
                    # cookie/profile 也要带上：登录墙图集（抖音 note 等）不带 cookie 收不到原图
                    result = auto_save_url(url, output_dir, wait_seconds, m, headed, max_wait,
                                           auto_wait, save_junk, keep_segments, "image,audio", safe,
                                           cookie_file=cookie_file,
                                           cookies_from_browser=cookies_from_browser,
                                           profile_dir=profile_dir,
                                           stealth=stealth)
                else:
                    # chain 的 browser/cache 步关掉内部 yt-dlp 降级：chain 前面已有
                    # 独立 ytdlp 步、链尾还有 cookie 复试，内部再跑会让 yt-dlp 整链 3 次
                    result = auto_save_url(url, output_dir, wait_seconds, m, headed, max_wait,
                                           auto_wait, save_junk, keep_segments, media_types, safe,
                                           cookie_file=cookie_file,
                                           cookies_from_browser=cookies_from_browser,
                                           profile_dir=profile_dir,
                                           stealth=stealth,
                                           ytdlp_fallback=(m not in ("browser", "cache")))
            except Exception as exc:
                # 某一环崩了（页面打不开/playwright 缺失等）不让 chain 整体死掉，继续试下一种
                result = {"saved": [], "count": 0, "method": m, "yt_dlp_error": f"crash: {exc}"}
            attempts.append(
                {
                    "method": m,
                    "count": result.get("count", 0),
                    "error": result.get("yt_dlp_error") or result.get("error"),
                    "quality": _q(result),
                }
            )
            if result.get("saved"):
                # junk 不截断链（v1.22.1）：只有残件/封面的"成功"是假成功——
                # 记为当前最佳候选后继续兜底，给后面的环留机会。
                if _q(result) == "junk":
                    if best_result is None or _q_rank[_q(result)] > _q_rank.get(best_result.get("quality", ""), 0):
                        best_result = result
                    last_result = result
                    continue
                # note 预判已落盘的收获（图/元数据）合并进 chain 成功结果，不能丢
                if note_harvest:
                    result["saved"] = note_harvest["saved"] + result["saved"]
                    result["count"] = len(result["saved"])
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
                    if note_harvest:
                        saved = note_harvest["saved"] + saved
                    return {"mode": "url", "source_url": url, "output_dir": str(output_dir),
                            "saved": saved, "count": len(saved), "method": "chain->ytdlp+cookies",
                            "attempts": attempts}
            except Exception as exc:
                attempts.append({"method": "ytdlp+cookies", "count": 0, "error": f"crash: {exc}"})
        if last_result is None:
            last_result = {"saved": [], "count": 0, "method": "chain"}
        # chain 全败但 note 预判收到过图 → 用 harvest 收获兜底返回（比空手强）
        if note_harvest:
            note_harvest["attempts"] = attempts
            note_harvest["method"] = "chain->harvest(note)"
            note_harvest["note_auto_rerouted"] = True
            return note_harvest
        # 全链无正果：返回质量最高的一环（junk 成果文件已落盘不丢，但如实标注），
        # 而不是恰好最后一环的结果——最后一环常是 text 正文，用户要的视频残件反被丢掉。
        fallback = best_result or last_result
        fallback["attempts"] = attempts
        fallback.setdefault("quality", _assess_saved_quality(fallback.get("saved", []), allowed_kinds))
        return fallback

    # files：文件专用路线（压缩包/文档/表格/文本等，直链直下、页面批量下、可打包zip）
    if method == "files":
        return _files_route(url, output_dir, headed=headed, safe=safe,
                            zip_bundle=zip_bundle, click_download=click_download,
                            stealth=stealth)

    # vision：视觉会话模式（多模态模型的"眼睛+手"，stdin/stdout JSON 协议驱动）
    if method == "vision":
        return _vision_route(url, output_dir, headed=headed, safe=safe,
                             max_screens=vision_max_screens, detail=vision_detail,
                             model=model_name, session_timeout_sec=vision_timeout,
                             viewport_w=vision_viewport[0], viewport_h=vision_viewport[1],
                             cookie_file=cookie_file,
                             cookies_from_browser=cookies_from_browser,
                             profile_dir=profile_dir,
                             captcha_mode=captcha_mode,
                             idle_timeout=idle_timeout,
                             linger=linger,
                             stealth=stealth,
                             login_rescue=login_rescue)

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
                           max_chapters=max_chapters, allow_chapters=allow_chapters,
                           stealth=stealth)

    # harvest：只走 DOM/元数据/JSON 收割 + 页面上下文下载，快（无长等待），适合照片/音频。
    if method == "harvest":
        return _harvest_route(url, output_dir, headed=headed, safe=safe,
                              save_junk=save_junk, allowed_kinds=allowed_kinds,
                              cookie_file=cookie_file,
                              cookies_from_browser=cookies_from_browser,
                              profile_dir=profile_dir, stealth=stealth)
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

    # browser / cache / auto 的浏览器阶段（路线实现在 auto_save/routes.py）。
    return _browser_route(url, output_dir, wait_seconds=wait_seconds, method=method,
                          headed=headed, max_wait=max_wait, auto_wait=auto_wait,
                          save_junk=save_junk, keep_segments=keep_segments,
                          allowed_kinds=allowed_kinds, safe=safe,
                          cookie_file=cookie_file, cookies_from_browser=cookies_from_browser,
                          profile_dir=profile_dir, stealth=stealth, yt_error=yt_error,
                          ytdlp_fallback=ytdlp_fallback)


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
    q = data.get("quality")
    if q:
        q_desc = {"full": "完整成果（含验证过/完整的视频音频）",
                  "partial": "部分成果（有匹配的内容，未过解码验证）",
                  "junk": "低质量（与目标类型零交集：残件/封面等，全链未取得正片）"}.get(q, q)
        lines.append(f"质量: {q}（{q_desc}）")
    lines.append(f"已保存 {len(saved)} 个文件")
    for i, item in enumerate(saved, 1):
        dur = item.get("verified_duration_sec")
        dur_str = f", 实测时长 {dur}s" if dur else (", 时长未验证" if item.get("kind") in ("merged-segment", "merged-segment-candidate") else "")
        lines.append(f"{i}. {item.get('path')} ({item.get('size', 0)} bytes) [{item.get('kind', '')}]{dur_str}")
    if data.get("metadata_note"):
        lines.append(f"说明: {data['metadata_note']}")
    return "\n".join(lines)


def main(argv=None):
    # 输出编码说明（v1.22.0 压测后修正）：Windows 中文环境下 Python 管道输出默认用
    # locale 编码（GBK），与常见终端/重定向查看端一致——保持默认即可正确显示。
    # 不要强设 UTF-8：GBK 终端读 UTF-8 字节会出"鏈畨瑁咃"式乱码（实测教训）。
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
        default="1440x900",
        metavar="WxH",
        help="视觉会话视口尺寸（默认 1440x900：800x800 实测会裁掉页面底部按钮——完整性优先，清晰度由官方 384token 封顶兜底；DeepSeek 视觉原生 800x800 需要极致清晰时手动指定）。AI 也可在会话中发 {\"action\":\"viewport\",\"width\":W,\"height\":H} 动态改",
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
    parser.add_argument(
        "--profile",
        nargs="?",
        const=str(PROFILE_DIR),
        default=None,
        metavar="目录",
        help="持久化浏览器用户目录：登录一次以后免登录（等同真实浏览器的用户配置，cookie/缓存跨会话保留）。不带值=默认 downloads/browser_profile/，也可给自定义路径。首次登录：--method vision --profile --headed 弹出窗口人肉扫码；之后 --profile 无头跑即可。目录含登录 cookie（已 gitignore，别拷给别人），同一目录同时只能开一个会话",
    )
    parser.add_argument(
        "--captcha-mode",
        choices=["off", "detect"],
        default="off",
        help="视觉会话验证码检测：off=不检测不输出（默认——此前误报会让 AI 见到 captcha_detected 就停手卡死）；detect=每步检测并上报（只检测不绕过，真验证码需 --headed 人工过）",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=None,
        metavar="秒",
        help="视觉会话空闲看门狗：N 秒收不到下一条指令判定 AI 断线自动收尾（默认 120；--headed 有人在场自动放宽到 600；0=关闭，只受 --vision-timeout 总时长约束）",
    )
    parser.add_argument(
        "--linger",
        action="store_true",
        help="视觉会话结束后不立即关浏览器：--headed 窗口保留给人看完手动关（上限1h）；无头保留 30s 自动退。AI 脚本崩了浏览器现场不再消失",
    )
    parser.add_argument(
        "--stealth",
        choices=["full", "basic", "off"],
        default="full",
        help="浏览器伪装档位：full=全套（默认，playwright-stealth 深层指纹补丁，挡搜狗 antispider 级风控；库未装自动降级 basic 并告知）；basic=半套（项目自带 webdriver 抹除+UA/视口伪装）；off=关闭（对照调试用）",
    )
    parser.add_argument(
        "--login-rescue",
        action="store_true",
        help="登录兜底（配 --method vision/--profile 用）：打开页面后自动检查本机 chrome/edge/firefox，谁有所需站点的登录 cookie 就接种进来并刷新（治'扫码确认了但站点拒发 session'——人肉在自己平时浏览器登录目标站，工具把登录态搬进来）",
    )
    parser.add_argument(
        "--humanize",
        choices=["on", "off"],
        default="on",
        help="拟人输入（v1.22.0 默认 on）：鼠标贝塞尔轨迹+缓入缓出+手抖、点击微偏移+按压时长、打字正态键间隔+标点后思考停顿、滚动分步微停。事件层走 CDP isTrusted=true（与 USB 硬件输入同级），行为层补机器模式破绽，防行为风控。off=逐字节退回原生 API（旧行为，对照调试用）；拟真步骤异常也自动退原生，最坏=没拟真不会挂任务",
    )
    parser.add_argument(
        "--real-headless",
        choices=["on", "off"],
        default="on",
        dest="real_headless",
        help="无头拟真（v1.22.0 默认 on）：补无头 Chromium 静态指纹缺口（硬件核数/内存、permissions 一致性、WebGL 渲染器、chrome.app、色彩深度）+ 拟真 launch 参数（lang=zh-CN 等）。与 --stealth 正交，两个开关任意组合；off=回到 v1.21.x 行为",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    # ---- v1.22.0 行为开关落到模块级（避免参数层层穿透各路线）----
    set_humanize(args.humanize == "on")
    realheadless.set_enabled(args.real_headless == "on")

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

    # 持久化用户目录（--profile）：登录一次以后免登录
    profile_dir = Path(args.profile).expanduser().resolve() if args.profile else None
    if profile_dir:
        print(f"[profile] 持久化用户目录: {profile_dir}（登录态跨会话保留）", file=sys.stderr)

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
            # --viewport "WxH" 解析（vision 会话视口；坏格式回退默认 1440x900）
            try:
                _vw, _vh = str(args.viewport).lower().split("x", 1)
                vision_vp = (max(200, min(3840, int(_vw))), max(200, min(3840, int(_vh))))
            except (ValueError, AttributeError):
                vision_vp = (1440, 900)
                print(f"[提示] --viewport 格式应为 WxH（如 1280x800），已回退默认 1440x900",
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
                profile_dir=profile_dir,
                captcha_mode=args.captcha_mode,
                idle_timeout=args.idle_timeout,
                linger=args.linger,
                stealth=args.stealth,
                login_rescue=args.login_rescue,
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
                        profile_dir=profile_dir,
                        stealth=args.stealth,
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
                    profile_dir=profile_dir,
                    stealth=args.stealth,
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
                        profile_dir=profile_dir,
                        stealth=args.stealth,
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
            shot = _screenshot_standalone(shot_url, output_dir, headed=args.headed,
                                          safe=args.safe, stealth=args.stealth,
                                          profile_dir=profile_dir)
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

    # 质量门补齐（v1.22.1 压测排雷）：files/direct/text/harvest 等专用线不自带
    # quality 字段（只有 chain 线全程评估）——退出码判"非 junk"虽已正确，但
    # JSON 消费端拿不到统一质量信号（实测 files 线 60MB 完整下载报 quality: null）。
    # 与 chain 线 _q 同尺：文件直链意图拿到非残件产物即 full；其余按通用评估
    # （wants 按方法补 file/text 意图，防成功下载被误判 junk）。
    if not data.get("quality") and args.method != "vision":
        if data.get("saved"):
            _src = data.get("source_url") or args.url or ""
            _explicit_file = urllib.parse.urlparse(_src).path.lower().endswith(FILE_EXTS)
            if _explicit_file and any(i.get("kind") not in ("text", "cache-segment", None)
                                      for i in data["saved"]):
                data["quality"] = "full"
            else:
                _kinds = {t.strip() for t in re.split(r"[,，]", (args.media_type or "").strip()) if t.strip()}
                if not _kinds:
                    _kinds = {"video", "audio", "image"}
                if args.method == "files":
                    _kinds.add("file")
                elif args.method == "text":
                    _kinds.add("text")
                data["quality"] = _assess_saved_quality(data["saved"], _kinds)
        else:
            data["quality"] = "empty"

    if args.json:
        # default=str 兜底（v1.22.1 排雷）：产物 dict 里混进任何非 JSON 类型
        # （实测 cleanup.removed_paths 曾是 set）不该让整场下载在输出层崩掉。
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(_format_plain(data))
    # 退出码语义（v1.22.1 修"失败无信号"）：有正果 = 0，无正果 = 1。
    # 此前恒 return 0——下载失败/全链空手也报成功，宿主无法据此降级重试。
    # 判据与质量门同尺：saved 非空且 quality != junk（junk = 残件/封面等零交集
    # 产物，文件虽落盘但不算正果，如实报失败）；vision 是 stdin/stdout 会话
    # 协议，自有状态上报，不按下载退出码量。
    if args.method == "vision":
        return 0
    return 0 if (data.get("saved") and data.get("quality") != "junk") else 1


if __name__ == "__main__":
    sys.exit(main())
