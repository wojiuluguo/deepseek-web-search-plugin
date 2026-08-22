# deepseek-web-search

English | **[中文](README.zh-CN.md)**

An [OpenClaw](https://github.com/openclaw) skill that gives DeepSeek real web search **and** an auto-save browser that downloads videos/audio/images/files from any webpage it opens — plus a vision mode for multimodal models (see a page, operate a page).

> Current version **v1.17.0** (2026-08-22) · Author: user · [Changelog](#changelog)

<p align="center"><img src="assets/mascot.png" alt="deepseek-web-search mascot" width="220"></p>

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
| Vision mode (multimodal) | `auto_save_browser.py` | Screenshots + screen info fed to vision models; mouse/keyboard control session (for deepseek-v4-flash-vision-exp) |
| Capture verification | `verify_capture.py` | ffmpeg real-decode duration check, inflation detection, segment merge validation |

Default search engines: Bing, Sogou, 360, Baidu (China-first); DuckDuckGo only for external/manual queries; optional Tavily, Brave Search, SearXNG (auto-enabled via environment variables).

## Network Environment Note

**This tool was developed and tested entirely on mainland China network infrastructure.** We have **not** tested it on networks outside mainland China.

- If you use it on overseas or other network environments, engine timeouts or unexpected results may occur — your understanding is appreciated.
- On overseas networks, try `--engines ddg,brave` first for better reachability.
- Support for networks outside mainland China may be added in future versions.

## Installation

The repo is plain-text code plus one mascot image (~2MB); heavy dependencies like Chromium are installed from official sources by the setup script.

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

# Login-wall sites (Douyin/Bilibili): attach login cookies for video streams
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --cookies "D:/cookies.txt" --json
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --cookies-from-browser chrome --json

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

# Vision mode (multimodal models): one-shot page screenshot
python scripts/auto_save_browser.py --url "..." --method text --screenshot --model deepseek-v4-flash-vision-exp --json

# Vision mode: operate a page like a human (JSON commands via stdin, screenshots + state via stdout)
python scripts/auto_save_browser.py --url "..." --method vision --model deepseek-v4-flash-vision-exp --json
```

## Vision Mode (for multimodal models, v1.12.0)

Adapts the official `deepseek-v4-flash-vision-exp` multimodal model (released 2026-08-21): gives the model "eyes" and "hands".

| Capability | Usage | Description |
|---|---|---|
| Page screenshots | Add `--screenshot` to any command | Opens page → lazy-load scroll → full-page PNG + screen info; ultra-tall pages auto-segmented (official max edge 8192px) |
| Vision session | `--method vision` | Send JSON commands line-by-line via stdin (click/right_click/dblclick/move/scroll/type/press/goto/back/forward/reload/wait/screenshot/eval/quit); each step returns a screenshot + screen state on stdout |
| Screen info | Auto-output each step | Viewport size, full-page size, DPR, mouse coordinates, scroll position — the model computes click coordinates from these |
| Model detection | `--model <name>` | Name contains "vision" = multimodal; outputs `vision_capable` + `api_hint` (official API params, copy-paste into requests) |
| Cost guard | `--max-screenshots` (default 30) / `--shot-detail low` | Each screenshot ≤384 tokens (official cap); auto-stops when limit hit; low = 512×512 budget mode |

**Official parameter basis** (api-docs.deepseek.com/guides/vision): images are tokenized by size, capped at 384 tokens each; formats JPEG/PNG/GIF/WebP (detected from actual content); three input methods — base64 inline (48 MiB body limit), external URL, or Files API; images may only appear in user messages.

## Download Reliability Design (auto_save_browser.py)

`chain` mode tries each method in order and uses the first one that succeeds (v1.13.0: expanded from 5 to 6 routes + cookie retry):

```text
direct → ytdlp → browser → cache → harvest → text   (+ ytdlp-with-cookies retry if cookies were provided)
```

| Scenario | Mechanism |
|---|---|
| Media pages | Real Chromium playback + network sniffing + 206-segment merging + blob/MSE capture + DOM/JSON harvesting |
| Lazy-loaded SPA galleries (Xiaoheihe etc.) | Iterative scroll-harvest: scroll a step → wait for new images to mount → harvest the batch → repeat until no new items (≤30 rounds, 200-file cap); cross-origin CDN images fall back to direct HTTP download when in-page fetch is CORS-blocked |
| Login walls (Douyin/Bilibili) | `--cookies <file>` (Netscape cookies.txt, exported via "Get cookies.txt" extension) or `--cookies-from-browser chrome/edge/firefox` — injected into yt-dlp, browser contexts, cache & harvest routes alike |
| Douyin photo posts (`/note/`) | Auto-rerouted to `harvest` (yt-dlp doesn't support note URLs); output `note_auto_rerouted: true` |
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

## Changelog

### v1.17.0 (2026-08-22)

Three-tier browser stealth, full by default:

- **New `--stealth full|basic|off` (default full)**: playwright-stealth deep-fingerprint patches (plugins/WebGL/UA-Data/sec-ch-ua/hairline, 20+ items) on top of the existing webdriver-erase + UA/viewport/locale disguise — headless fingerprint now closely resembles a real user's browser; `basic` keeps the old half-set; `off` for control testing.
- **Applied everywhere**: search browser + all download/vision routes share `_apply_stealth`; auto-degrades to basic with an stderr notice when the library is missing.
- New dependency `playwright-stealth` added to requirements.txt and the installer.
- **Verified live**: off → plugins=0 (bare), basic → plugins=5 (fake), full → plugins=3 + brands without HeadlessChrome (real-looking); Bing search regression passes.
- **Known limitation (stated honestly)**: Sogou antispider is IP/behavior-level risk control that fingerprint stealth cannot pass — switch engines or warm a `--profile` login (documented in SKILL.md).

### v1.16.0 (2026-08-22)

Four fixes from real-world testing (viewport clipping / new tabs / gallery inconsistency / CJK typing note):

- **Default viewport 800×800 → 1440×900**: 800px height actually clipped page bottoms (Baidu's search button cut in half) — completeness first, sharpness backstopped by the official 384-token cap; use `--viewport 800x800` for max fidelity.
- **New-tab auto-tracking**: clicking target=_blank links (related-searches/hot-topics) now auto-switches the vision session to the new tab (with a note); new `tabs` (list tabs) and `switch_tab` commands. Verified live on Bing: click result → auto-switch → subsequent commands run on the new tab.
- **Gallery harvest waits for images**: each scroll round now polls `img.complete` (up to 3s) before harvesting — fixes inconsistent gallery captures (7 vs 2 images): in-flight images were being skipped or marked failed.
- **CJK typing note**: legacy coordinate `type` may output `???` for CJK — use the v1.15.0 precise typing `{"action":"type","selector":"...","text":"中文"}` (JS-value fallback when the keyboard channel fails); for pure HTTP CJK search use `search.py`.
- Login walls (Doubao/Douyin/DeepSeek web) are site-enforced identity checks the tool does not bypass: `--profile` persistent login (v1.14.0) is the intended path.

### v1.15.0 (2026-08-22)

DOM-precise vision session — click/move/scroll/type no longer rely on guessed pixels:

- **New DOM-precise mode (default recommended)**: `click`/`move`/`scroll` accept `"text"` (locate by on-page text) or `"selector"` (CSS); `type` accepts `"selector"` for the input box. Pipeline: locate → wait visible (3s) → act on bounding-box center (scroll = scroll into view) → verify → auto-retry up to 3 times.
- **Precise typing has read-back verification**: after typing, the input's value/innerText must contain the typed text, otherwise a JS fallback sets the value and dispatches input/change events (contenteditable uses execCommand insertText for a real input event) — React controlled components and ProseMirror honor events, not keystrokes; this fixes "typed text disappears".
- **`"expect_gone": true`** optional click verification (element must disappear — closing popups/dropdowns).
- **Coordinate mode fully preserved** (x/y-only commands behave exactly as before, backward compatible). Regression-tested live: click-by-text, precise typing with verification, element scroll, and coordinate mode all pass.
- Hidden elements fail honestly (wait-visible timeout → 3 retries → clear error) instead of blind-clicking.

### v1.14.2 (2026-08-22)

Captcha detection off by default (real-world feedback: false positives froze all operations):

- **`--captcha-mode` default flipped from `detect` to `off`**: no more per-step detection or `captcha_detected` output — normal pages (carousels/icon classes) used to be falsely flagged, and downstream AI would halt on sight, freezing typing/clicking/dragging. Detection stays available via explicit `--captcha-mode detect`.
- Note: terminal "echo" is standard TTY input display, not tool output (the tool's stdout is a clean JSON state stream); for manual operation use the `--headed` real window.

### v1.14.1 (2026-08-22)

Vision-session robustness (5 tool-level issues from real-world feedback):

- **Fix captcha false positives**: tightened detection selectors — bare `.slider` (image carousels) and `[class*="rotate"]` (Tailwind rotate-\* icons) no longer misreported as slider/rotate captchas; dropped the "向右滑动" keyword (standard carousel hint text). Normal pages used to trigger `captcha_detected`, making downstream AI halt.
- **New `--captcha-mode allow`**: disables captcha detection entirely (for pages that actually work fine while detection keeps misfiring).
- **New `--linger`**: session end (AI disconnect/quit/EOF) no longer closes the browser instantly — `--headed` window is kept for the human to close manually (1h cap); headless gets a 30s grace. A crashed AI script no longer kills the browser session.
- **New `--idle-timeout N`**: configurable idle watchdog (default 120s; auto-relaxed to 600s in `--headed` mode so QR-scan/manual interaction isn't killed; 0=off, only total timeout applies).
- Tolerant cleanup when the persistent-context window is manually closed; captcha handoff guidance updated to `--headed --profile` (login state preserved).
- Note: the stdin/stdout protocol is designed for programmatic pipes; typing manually in a TTY mixes terminal echo (not a bug — documented; manual scenarios should use `--headed`).

### v1.14.0 (2026-08-22)

Persistent login + a batch of security/functional fixes:

- **New `--profile [dir]` persistent browser user-data dir**: log in once, stay logged in across sessions (Doubao/Douyin/Bilibili web and other login-walled sites) — cookies/cache/login state persist like a real browser. First login: `--method vision --profile --headed` (human scans QR), then headless with `--profile`. The dir holds login cookies (gitignored).
- **Fix: `--cookies-from-browser` only worked in the yt-dlp route** — browser/cache/harvest/vision routes silently ignored it (Playwright has no API to read host-browser cookies). Now extracted via yt-dlp's cookie extractor and injected; honest error when unreadable.
- **Fix: browser-route's internal yt-dlp fallback dropped cookies** (explicit `--method browser --cookies` degraded without login state); chain's harvest step also missed passing cookies.
- **Fix: safe-mode 2GB cap holes** — files-route streaming download and click-download never checked size (disk-fill risk); now abort+delete mid-stream over the cap, native downloads re-checked after save.
- **Fix: substring domain matching** (`notdouyin.com` matched `douyin.com`) → exact domain/subdomain matching everywhere.
- **Fix: harvest permanently blacklisted transiently-failed URLs** (one timeout = never retried, lazy galleries lost images) → retry up to 2 times across scroll rounds.
- **Fix: vision session lost safe-mode popup blocking after page rebuild**; startup URL failure no longer wastes screenshot budget on a blank page.
- Search: CJK precision ranking fixed (whole-sentence glue → bigram terms); search_browser now ignores self-signed certs (aligned with other routes); network sniffing skips >1GB responses and same-path-different-query files are no longer wrongly deduped (true duplicates cut by content hash).

### v1.13.1 (2026-08-22)

Lazy-loaded SPA gallery fix (reported: Xiaoheihe gallery pages only yielded ~3 visible thumbnails):

- **Iterative scroll-harvest** replaces the old "jump-to-bottom + fixed 3 scrolls + single harvest": harvest now scrolls step-by-step, waits for newly mounted images, harvests each batch, and repeats until the page bottom yields no new items (or 4 consecutive empty rounds / 30-round cap / 200-file cap). IntersectionObserver-style lazy loading requires images to pass through the viewport — the old logic never triggered them.
- **Cross-origin CDN fallback**: images on CDNs without CORS headers (e.g. `cdn.max-c.com`) used to fail silently in the in-page fetch; now they fall back to a direct script-side HTTP download with browser UA + page Referer.
- **Small-image false-positive fix**: harvest mode no longer discards images <150KB as junk (gallery regulars are often 6–81KB); only icon/logo keyword URLs are filtered.
- Regression: chain direct/ytdlp/browser/cache/harvest/text fallback all pass; Bing image-wall test harvests the full lazy grid (200 files).

### v1.13.0 (2026-08-22)

Login-wall downloads + bigger fallback chain:

- **New: `--cookies <file>` / `--cookies-from-browser chrome|edge|firefox`** — attach login state for Douyin/Bilibili-style paywall/login sites. Netscape cookies.txt (exported via the "Get cookies.txt" browser extension) or read directly from a locally logged-in browser. Injected into every route: yt-dlp (`cookiefile`/`cookiesfrombrowser`), browser & cache contexts (`add_cookies`), harvest, and the note-reroute.
- **chain fallback expanded 5 → 6 routes**: `direct → ytdlp → browser → cache → harvest → text`; each failed step automatically moves to the next, first success returns immediately; per-step outcome recorded in the `attempts` array; a single crashed route (page won't open, Playwright missing) no longer kills the chain. With cookies provided and everything failed, an extra `ytdlp+cookies` retry fires as the last resort.
- **Douyin photo posts (`/note/`) auto-reroute**: yt-dlp reports Unsupported URL on note links — now auto-detected and rerouted to `harvest` for the full-resolution image set (`note_auto_rerouted: true`); if harvest comes back empty, chain continues instead of failing.
- `own_search.py download` now passes through `--method` / `--cookies` / `--cookies-from-browser`.

### v1.12.6 (2026-08-22)

Repo sync fix:

- **Fixed: default branch was stale.** Releases were pushed to `master` while GitHub's default branch `main` still showed v1.12.3 — `main` is now fast-forwarded to the latest and `master` removed, single-branch from now on.
- Mascot moved from `.github/` to `assets/` for reliable README image rendering on GitHub (hidden dot-folders render inconsistently).

### v1.12.5 (2026-08-22)

Vision session robustness + repository polish:

- Vision session: `--method vision` startup now includes `vision_capable` and `model` fields in the first state line (AI can immediately detect whether it supports vision).
- Vision session: `eval` instruction gets a 10s deadlock watchdog — if user-supplied JS contains `while(true){}` or similar hang, the DevTools HTTP `/json/close` endpoint kills the page and the session is rebuilt automatically (no more permanent session freeze).
- Bug fix: `own_search.py download` and `own_search.py seed` now have subprocess timeouts (1800s / 300s) so a stuck downstream no longer freezes the parent.
- Repo: added project mascot (now at `assets/mascot.png`), embedded in both README pages.

### v1.12.4 (2026-08-22)

Vision session overhaul + 12 critical bug fixes. Also ships the previously unreleased v1.12.2~v1.12.3 internal iterations (`focus` action with CSS selectors, `elements` element annotation, captcha detection reporting).
- Data-loss guard: `verify_capture.py --clean` refuses to delete "broken" media when ffmpeg is missing (unverifiable ≠ broken).
- Crash fix: `search_and_cache.py` subprocess timeouts no longer crash the whole script (returns JSON error instead); cache timeout raised to 300s.
- Security fix: `own_search.py download --safe` now actually passes `--safe` to the underlying browser.
- Search robustness: smart_search browser timeout 90s→240s; cross_search mega timeout scales with engine count and reports `timed_out_copies` instead of silently returning empty; URL dedup now keeps business-meaningful query params (`v/id/tid`…, e.g. different YouTube videos no longer collapse into one).
- UX: vision session messages unified to Chinese; `--query --auto` now falls back to the chain route like `--url` mode; log newline typo fixed.

## License

MIT
