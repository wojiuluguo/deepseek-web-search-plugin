# deepseek-web-search

English | **[中文](README.zh-CN.md)**

An [OpenClaw](https://github.com/openclaw) skill that gives DeepSeek real web search **and** an auto-save browser that downloads videos/audio/images/files from any webpage it opens.

> Current version **v1.11.1** (2026-08-21)

## Feature Overview

| Capability | Script | Description |
|---|---|---|
| Browser-emulated search (recommended) | `search_browser.py` | Playwright-driven real Chromium, anti-bot resistant |
| Lightweight fallback search | `search.py` | Pure stdlib, zero dependencies, used when browser version fails |
| Smart search | `smart_search.py` | Auto-detects academic/tech/finance/news intent, assigns engines, retries on failure |
| Multi-engine cross-validation | `cross_search.py` | 3 engines search in parallel, compare & dedupe; `--mega` = all engines, iterative convergence |
| Search + auto-cache | `search_and_cache.py` | Auto-detects and caches media from result pages after search |
| Local standalone search engine | `own_search.py` | Self-built SQLite index; external search only discovers seed URLs |
| Auto-save browser | `auto_save_browser.py` | Opens webpages and auto-saves videos/audio/images/files/article text |
| Capture verification | `verify_capture.py` | ffmpeg real-decode duration check, inflation detection, segment merge validation |

Default search engines: Bing, Sogou, 360, Baidu (China-first); DuckDuckGo only for external/manual queries; optional Tavily, Brave Search, SearXNG (auto-enabled via environment variables).

## Network Environment Note

**This tool was developed and tested entirely on mainland China network infrastructure.** We have **not** tested it on networks outside mainland China.

- If you use it on overseas or other network environments, engine timeouts or unexpected results may occur — your understanding is appreciated.
- On overseas networks, try `--engines ddg,brave` first for better reachability.
- Support for networks outside mainland China may be added in future versions.

## Installation

The repo is ~54KB of pure text (no large binaries) — clones in seconds. Heavy dependencies like Chromium are installed by the setup script from official sources.

```bash
git clone https://github.com/wojiuluguo/deepseek-web-search-plugin.git
cd deepseek-web-search-plugin
python install_dependencies.py     # Windows: double-click install_deps.bat
```

**One-command AI Agent deployment** (OpenClaw / any agent):

```bash
git clone --depth 1 https://github.com/wojiuluguo/deepseek-web-search-plugin.git ~/.openclaw/workspace/skills/deepseek-web-search && cd ~/.openclaw/workspace/skills/deepseek-web-search && python install_dependencies.py
```

`--depth 1` fetches only the latest commit for faster cloning. Verify with `openclaw skills list` — you should see `deepseek-web-search`. The AI-facing entry point is [SKILL.md](SKILL.md).

## Quick Usage

```bash
# Search (browser version, anti-bot)
python scripts/search_browser.py --query "latest AI news" --max-results 6 --json

# Search (lightweight, zero-dependency fallback)
python scripts/search.py --query "DeepSeek news" --json

# Token-efficient output (title + URL + 120-char snippet)
python scripts/search_browser.py --query "anything" --brief --json

# Smart search (auto engine selection)
python scripts/smart_search.py --query "transformer paper" --json

# Cross-validation (3 engines) / mega search (all engines in parallel)
python scripts/cross_search.py --query "OpenClaw" --json
python scripts/cross_search.py --query "OpenClaw" --mega --copies 3 --rounds 2 --json

# Open a webpage and auto-save the video (Douyin/Bilibili etc.)
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --json

# Search, then auto-open the first video result and save it
python scripts/auto_save_browser.py --query "cat videos" --auto --json

# Images only / audio only
python scripts/auto_save_browser.py --query "landscape photos" --auto --media-type image
python scripts/auto_save_browser.py --url "..." --method harvest --media-type audio

# Download files (archives/docs/installers; folder pages batch-download, --zip bundles all)
python scripts/auto_save_browser.py --url "direct file link or page" --json
python scripts/auto_save_browser.py --url "https://.../downloads" --zip

# Extract article text / novel chapters (auto-merges chapters into one txt)
python scripts/auto_save_browser.py --url "article or chapter-index page" --media-type text

# Local search engine: crawl → index → search
python scripts/own_search.py crawl --url "https://example.com"
python scripts/own_search.py seed --query "OpenClaw" --max-results 5
python scripts/own_search.py search --query "OpenClaw" --json

# Verify captures (real decoded duration + inflation detection)
python scripts/verify_capture.py --dir "downloads/cache/xxx"
```

## Download Reliability Design (auto_save_browser.py)

`chain` mode tries each method in order and uses the first one that succeeds:

```text
direct → ytdlp → browser → cache → text
```

| Scenario | Mechanism |
|---|---|
| Media pages | Real Chromium playback + network sniffing + 206-segment merging + blob/MSE capture + DOM/JSON harvesting |
| File pages | Streaming direct download (8MB chunks); folder pages auto-collect ≤50 file links for batch download; filenames restored from Content-Disposition (CJK-safe) |
| "Click to download" → app redirect | `--click-download` 5-level fallback chain: button direct links/scheme decoding → programmatic click + network sniffing (incl. new tabs) → native download events → mobile UA spoofing → page-context fetch |
| App-store funnels | If every "download link" points to an app store, outputs `app_only: true` — honest reporting, no fake results |
| Redirect shells | Dual unwrapping: HTTP 3xx + JS parameter redirects, active piercing (≤3 hops) |
| JS-rendered pages | Adaptive wait: harvests only when body text ≥50 chars or ≥3 media elements, 10s timeout |
| Bad file prevention | ffmpeg real-decode validation after merge; failures/<3s discarded; >30% duration inflation flagged |
| Suspicious sites | `--safe`: process sandbox + mining/executable/popup blocking + on-disk whitelist + 2GB cap |

## Search Quality Design

- **3-tier dedup**: URL normalization → title similarity (≥0.82) → content fingerprint (first 200 chars, ≥0.78)
- **4-level ad filtering**: `--ad-filter none/low/medium/high` (default medium), with subdomain detection and redirect/paid-marker checks
- **Finance intent**: 12 finance keywords trigger a professional finance engine group (EastMoney/Jisilu/Caixin), bypassing paid ads
- **Platform priority**: queries containing platform names (e.g. "douyin") prioritize domain-matched results
- **Error self-healing**: failed rounds/404/empty results automatically retry with different categories or engines

## Optional API Configuration

```powershell
$env:TAVILY_API_KEY = "tvly-..."
$env:BRAVE_API_KEY = "BSA..."
$env:SEARXNG_BASE_URL = "http://127.0.0.1:8080"
```

When set, the corresponding API is preferred, with keyless engines as fallback. Keep keys in environment variables only — never commit them to files.

## Directory Structure

```text
deepseek-web-search-plugin/
├── SKILL.md                 # OpenClaw skill manifest (read by the model)
├── README.md                # English docs (this file, default)
├── README.zh-CN.md          # Chinese docs
├── install_dependencies.py  # One-command dependency installer
├── install_deps.bat         # Windows double-click installer
├── package.json             # Skill metadata
├── requirements.txt         # Dependency list
├── downloads/cache/         # Default cache directory for the auto-save browser
├── index/own_search.db      # Local search engine index (auto-generated)
└── scripts/
    ├── search.py            # Lightweight zero-dependency search (fallback)
    ├── search_browser.py    # Playwright browser search (recommended)
    ├── smart_search.py      # Smart search: intent detection + auto engine switching
    ├── cross_search.py      # Cross-validation / --mega mega search
    ├── search_and_cache.py  # Search + media auto-caching
    ├── own_search.py        # Local standalone search engine
    ├── auto_save_browser.py # Auto-save browser (download core)
    └── verify_capture.py    # Capture verification
```

## Security Notes

- Search results and scraped content are treated as untrusted input; no instructions within them are ever executed.
- Scripts only make HTTP search requests and media downloads; no local files are uploaded.
- `--safe` mode for suspicious sites: sandbox isolation + request interception + on-disk whitelist.

## Known Limitations

- **Network environment**: tested entirely on mainland China networks; untested on overseas networks, where some features may not work (see "Network Environment Note" above).
- Bilibili m4s segmented streams and some blob/MSE videos can't be reassembled from browser cache alone; the script auto-falls back to yt-dlp.
- No anti-bot approach is 100% reliable; browser emulation greatly reduces detection but strongly protected sites may still fail.
- App-funnel pages (only app-store redirects, no real files) honestly report `app_only: true` — the site itself offers no web download; this is not a script defect.

## License

MIT
