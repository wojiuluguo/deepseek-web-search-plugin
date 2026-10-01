"""URL 归一化与去重 + 错误页识别（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）。"""
import re
import urllib.parse
from typing import Dict, List

__all__ = ["_URL_KEEP_PARAMS", "_normalize_url", "_dedupe",
           "ERROR_PAGE_STRONG", "ERROR_PAGE_WEAK", "_is_error_result"]

# 有业务含义的 query 参数（保留参与去重 key；其余跟踪参数如 utm_*/spm 等仍丢弃）
_URL_KEEP_PARAMS = ("v", "id", "p", "tid", "pid", "aid", "vid", "q", "w", "keyword",
                    "doc", "item", "thread", "post", "video", "album", "song", "play")


def _normalize_url(url: str) -> str:
    """URL 规范化：去 www.、去跟踪类 query/fragment、去尾斜杠。
    同一页面从 5 个引擎来（带各自跟踪参数）只留一份；
    但保留有业务含义的参数（v/id/tid 等）——YouTube watch?v=aaa 和 watch?v=bbb
    是不同视频，丢了参数会被误判成同一条。
    v1.25.0 压测修复（跳转壳去重坍缩）：搜狗 /link?url=、百度 /link?url=、
    360 /link?m= 这类跳转壳的 query 全是 url=/m= 加密 token，旧版把参数全丢后
    key 坍缩成 "baidu.com/link"——实测百度 8 条结果去重后只剩 1 条（7 条被误杀）。
    壳 URL 保留 query 原文参与 key（壳与壳之间 token 各不相同，天然不冲突）；
    壳解码（resolve.py）后真实 URL 再正常参与去重。"""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/").lower()
        # 跳转壳：query 加密 token 是 URL 身份的一部分，必须整体保留
        if "/link" in path:
            q = parsed.query
            return f"{host}{path}?{q}" if q else f"{host}{path}"
        keep = []
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if k.lower() in _URL_KEEP_PARAMS and v:
                keep.append(f"{k}={v}")
        keep.sort()  # 参数顺序无关
        return f"{host}{path}?{'&'.join(keep)}" if keep else f"{host}{path}"
    except Exception:
        return (url or "").lower()


def _dedupe(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """三层去重（与 search_browser 同口径）：
    1. URL 规范化：域名+路径做 key，跟踪参数不影响；
    2. 标题相似度 ≥0.82 判重复：标题换皮的结果全砍；
    3. 摘要指纹：前 200 字符相似度 ≥0.78 判重复：内容一样的缝合怪全砍。

    v1.25.0 新闻过滤压测修正（过度过滤实锤）：短模板化标题（新闻栏目页
    "时政_新华网"/"时政_央广网"/"时政要闻"）相似度天然 ≥0.8——5 字标题换
    2 字即 0.8，0.82 阈值对短标题无区分度，实测 84 条真实新闻 17 条不同权威源
    互遭连坐。修正：标题 <12 字时阈值提至 0.95（真转载短标题通常完全相同
    仍被杀，不同站点栏目页获救）；长标题维持 0.82 不变。

    二轮修正（差分归因后）：title 阈值修复后误过滤仍在——真凶在 snippet 层，
    栏目页的模板化摘要（"提供最新最全的XX资讯…"）雷同度同样 ≥0.78。与标题
    同构分档：snippet <120 字时阈值提至 0.95（同文转载摘要通常逐字相同仍被
    杀，模板化摘要的不同站点获救）；长摘要维持 0.78。"""
    from difflib import SequenceMatcher

    seen_urls = set()
    kept: List[Dict[str, str]] = []
    kept_titles: List[str] = []
    kept_snips: List[str] = []
    for r in results:
        key = _normalize_url(r.get("url", ""))
        if key and key in seen_urls:
            continue
        title = (r.get("title") or "").strip()
        snip = (r.get("snippet") or "").strip()[:200]
        title_threshold = 0.95 if len(title) < 12 else 0.82
        snip_threshold = 0.95 if len(snip) < 120 else 0.78
        # 第二层：标题相似度（换皮标题）
        if title and any(
            SequenceMatcher(None, title, t).ratio() >= title_threshold for t in kept_titles
        ):
            continue
        # 第三层：摘要指纹（同内容不同来源的缝合稿）
        if snip and len(snip) >= 30 and any(
            SequenceMatcher(None, snip, s).ratio() >= snip_threshold for s in kept_snips
        ):
            continue
        if key:
            seen_urls.add(key)
        kept.append(r)
        kept_titles.append(title)
        kept_snips.append(snip)
    return kept


ERROR_PAGE_STRONG = (
    # 强模式：正常结果标题不会出现这些词，命中即挡（不分标题长短）
    "页面不存在", "网页不存在", "链接已失效", "链接失效", "页面已删除",
    "内容不存在", "无法找到该页", "请输入验证码", "人机验证", "安全验证",
    "访问异常", "滑动验证", "just a moment",
)

ERROR_PAGE_WEAK = (
    # 弱模式：可能出现在正常文章标题（如"如何解决404错误"），
    # 只在标题极短时才判错（真实错误页标题如 "404 Not Found"≈13字符）
    "404", "403", "500", "not found", "page not found", "forbidden",
    "access denied",
)


def _is_error_result(url: str, title: str) -> bool:
    """错误页/验证码墙判定：标题命中错误模式，或 URL 是错误页路径。
    强模式全挡；弱模式仅极短标题挡（防误杀"如何解决404"这类教程）。"""
    title_l = (title or "").strip().lower()
    if not title_l:
        return True  # 连标题都没有的基本是坏结果
    for pat in ERROR_PAGE_STRONG:
        if pat in title_l:
            return True
    if len(title_l) <= 15:
        for pat in ERROR_PAGE_WEAK:
            if pat in title_l:
                return True
    # 错误页 URL 模式：/error /404 /403 结尾
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(("/404", "/403", "/500", "/error", "/notfound", "/not-found")):
        return True
    return False
