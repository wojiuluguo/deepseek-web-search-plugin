"""URL/媒体/安全判定纯函数：输入字符串或响应头 → 返回判定结果。
不碰浏览器、不碰全局可变状态、不写文件——拆分绝对安全级（v1.21.1 第 2 批）。"""

import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from .constants import (
    SEARCH_REDIRECT_HOSTS, VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS, MEDIA_EXTENSIONS,
    CONTENT_TYPE_EXT, JUNK_EXTENSIONS, JUNK_URL_HINTS,
    MINING_DOMAINS, STRATUM_PORTS, DANGEROUS_EXTS, SAFE_ALLOWED_EXTS, SAFE_MAX_FILE_BYTES,
)

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

SHELL_BODY_TEXT_LIMIT = 600  # 正文短于这个数且带跳转标记 → 判为落地页壳页

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


def _decode_redirect_url(url: str) -> str:
    """Try to extract the real target URL from search-engine redirect links."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if not any(_host_matches(host, rh) for rh in SEARCH_REDIRECT_HOSTS) and "link" not in parsed.path.lower():
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


def _host_matches(host: str, domain: str) -> bool:
    """域名精确匹配：host 等于 domain 或是其子域名。
    修复子串匹配漏洞——"douyin.com" in "notdouyin.com" 为 True，
    伪造前缀域名能骗过视频站一票否决/APP商店识别等全部域名判断。"""
    h = (host or "").lower().strip()
    d = (domain or "").lower().strip()
    return h == d or h.endswith("." + d)


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


def _is_app_store_url(url: str) -> bool:
    """判定 URL 是否 APP 商店/引流装APP页面。"""
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(_host_matches(host, h) for h in APP_STORE_HOSTS)


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


__all__ = [
    'APP_STORE_HOSTS',
    'SHELL_BODY_TEXT_LIMIT',
    'CLICK_DOWNLOAD_FILE_TYPES',
    'DOWNLOAD_BUTTON_TEXTS',
    '_decode_redirect_url',
    '_is_media_url',
    '_media_kind',
    '_ext_from_content_type',
    '_host_matches',
    '_safe_request_reason',
    '_safe_save_reason',
    '_is_junk_resource',
    '_safe_filename',
    '_url_group_key',
    '_extract_shell_redirect',
    '_is_split_stream_fragment',
    '_filename_from_disposition',
    '_is_app_store_url',
    '_decode_scheme_target',
]
