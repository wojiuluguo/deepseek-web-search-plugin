"""HTTP 公共件（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）：
UA/CA 配置、GET(_fetch)/POST-JSON(_post_json)/结果构造(_result)/HTML 清洗。
CA_CERT 通过 set_ca_cert() 设置（--cacert 路径，main() 调用）。"""
import html
import json
import re
import ssl
import urllib.request
from typing import Dict

__all__ = ["DEFAULT_ENGINES", "DEFAULT_USER_AGENT", "CA_CERT", "set_ca_cert",
           "_clean_html", "_fetch", "_post_json", "_result"]

DEFAULT_ENGINES = ["bing", "sogou", "so360", "baidu"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 可通过 --cacert 指定自定义 CA 证书包，用于某些需要安装证书的站点。
CA_CERT = None


def set_ca_cert(path):
    """设置自定义 CA 证书包（--cacert）。原 main() 里 global CA_CERT 赋值的模块化替代。"""
    global CA_CERT
    CA_CERT = path


def _clean_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _fetch(url: str, timeout: int = 8, headers: Dict[str, str] = None) -> str:
    """GET a URL and return decoded text."""
    req_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context(cafile=CA_CERT) if CA_CERT else ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
    # Try common encodings; most modern engines are UTF-8.
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def _post_json(url: str, payload: dict, timeout: int = 8, headers: Dict[str, str] = None) -> dict:
    """POST a JSON payload and return parsed JSON."""
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    ctx = ssl.create_default_context(cafile=CA_CERT) if CA_CERT else ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _result(title: str, url: str, snippet: str, source: str) -> Dict[str, str]:
    return {
        "title": _clean_html(title)[:300],
        "url": url[:500],
        "snippet": _clean_html(snippet)[:500],
        "source": source,
    }
