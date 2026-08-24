"""广告过滤与相关性（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）：
四档过滤(none/low/medium/high) + 错误页硬挡 + 域名过滤 + 关键词精准排序。"""
import re
import urllib.parse
from typing import Dict, List

from .normalize import _is_error_result

__all__ = ["AD_HOST_KEYWORDS", "AD_TITLE_KEYWORDS", "AD_REDIRECT_MARKERS",
           "_has_cjk", "_low_relevance", "_is_ad_result", "_filter_results",
           "_filter_site", "_query_terms", "_score_results"]

AD_HOST_KEYWORDS = (
    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
    "amazon-adsystem.com", "adservice.google.com", "taboola.com",
    "outbrain.com", "adsterra.com", "propellerads.com", "popads.net",
    "adroll.com", "criteo.com", "pubmatic.com", "rubiconproject.com",
    "openx.net", "smartadserver.com", "mgid.com", "revcontent.com",
    "adservice.com", "adnxs.com", "adsrvr.org",
    # 追加：程序化广告/重定向/联盟广告常见域
    "adform.net", "adition.com", "smaato.net", "yieldmo.com", "sharethrough.com",
    "33across.com", "casalemedia.com", "bidswitch.net",
    "zedo.com", "adcolony.com", "applovin.com", "ironsrc.com", "vungle.com",
    "unityads.unity3d.com", "unity.com/ads", "mintegral.com",
    "adtrack", "adtracker", "clicktracker", "tracking21", "track.ad",
    "adsrv", "adsystem", "adserver", "admarket", "adtraffic",
)

AD_TITLE_KEYWORDS = (
    "广告", "推广", "赞助", "advertisement", "sponsored", "promoted", "ad:",
    "商编", "软广",
)

AD_REDIRECT_MARKERS = (
    "/link?", "url=", "click?", "rd?", "go.php", "jump?",
    "link?url", "jump.php", "rd2?", "redir?", "/aclk", "clicktrack",
    "utm_medium=cpc", "utm_source=ad", "paid=1", "sponsored_click",
)


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _low_relevance(results: List[Dict[str, str]], query: str) -> bool:
    """Heuristic: for Chinese queries, Bing sometimes returns dictionary junk."""
    if not _has_cjk(query):
        return False
    q_chars = set(re.findall(r"[\u4e00-\u9fff]", query))
    if len(q_chars) < 2:
        return False
    for r in results[:3]:
        title_chars = set(re.findall(r"[\u4e00-\u9fff]", r.get("title", "")))
        if len(q_chars & title_chars) >= max(1, len(q_chars) // 2):
            return False
    return True


def _is_ad_result(url: str, title: str, level: str) -> bool:
    """Adjustable ad filtering. High level may also remove some real content."""
    if level == "none":
        return False
    netloc = urllib.parse.urlparse(url).netloc.lower()
    title_l = title.lower()
    # 广告专用子域：ad.xxx / ads.xxx / adv.xxx / tracking.xxx（medium 起判广告）
    is_ad_subdomain = netloc.startswith(("ad.", "ads.", "adv.", "tracking.", "track."))

    if level == "low":
        return any(k in netloc for k in AD_HOST_KEYWORDS) or bool(
            re.search(r"\b(sponsored|advertisement)\b", title_l)
        )
    if level == "medium":
        return (
            any(k in netloc for k in AD_HOST_KEYWORDS)
            or is_ad_subdomain
            or any(k in title_l for k in AD_TITLE_KEYWORDS)
        )
    if level == "high":
        if any(k in netloc for k in AD_HOST_KEYWORDS):
            return True
        if is_ad_subdomain:
            return True
        if any(k in title_l for k in AD_TITLE_KEYWORDS):
            return True
        return any(m in url.lower() for m in AD_REDIRECT_MARKERS)
    return False


def _filter_results(results: List[Dict[str, str]], level: str = "medium") -> List[Dict[str, str]]:
    # 错误页/验证码墙是质量问题，任何广告过滤档位（含 none）都挡在结果外
    results = [r for r in results if not _is_error_result(r.get("url", ""), r.get("title", ""))]
    if level == "none":
        return results
    out = []
    for r in results:
        if not _is_ad_result(r.get("url", ""), r.get("title", ""), level):
            out.append(r)
    return out


def _filter_site(results: List[Dict[str, str]], site: str) -> List[Dict[str, str]]:
    if not site:
        return results
    site = site.lower().lstrip(".").rstrip("/")
    return [
        r for r in results
        if site in urllib.parse.urlparse(r.get("url", "")).netloc.lower()
    ]


def _query_terms(query: str) -> List[str]:
    r"""分词（v1.22.0 批 D 统一两版）：英文/数字按词切；中文整句会被 \w+ 黏成一个词
    （precision 排序对中文直接失效），拆成二元组做匹配粒度。"""
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", query) if len(t) > 1]
    cjk = re.findall(r"[\u4e00-\u9fff]", query)
    terms += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return terms


def _score_results(results: List[Dict[str, str]], query: str, precision: int = 50) -> List[Dict[str, str]]:
    """Sort by how many query terms appear in title/url/snippet."""
    if precision <= 0:
        return results
    terms = _query_terms(query)
    if not terms:
        return results

    def score(r):
        text = f"{r.get('title', '')} {r.get('url', '')} {r.get('snippet', '')}".lower()
        return sum(text.count(t) for t in terms)

    return sorted(results, key=score, reverse=True)
