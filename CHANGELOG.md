# Changelog

Full version history. The READMEs keep only the latest 3 releases; all detailed entries live here.
Chinese version: [CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md). Feature docs: [README.md](README.md) (English) / [README.zh-CN.md](README.zh-CN.md) (Chinese).

## Version Timeline

```text
                     ┌─ Oct ─● v1.25.4  current (2026-10-25)
                     │        ○ v1.25.3  legacy full regression
                     │        ○ v1.25.2  sync verdict + sanitization
                     │        ○ v1.25.1  external-audit verdicts
   2026 ─────────────┼─ Sep ─● v1.25.0  search stress & optimization
   (newest first)    │        ○ v1.24.1  download-pipeline fixes
                     │        ○ v1.24.0  global watchdog
                     │        ○ v1.23.0~3 capabilities + stress tests
                     └─ Aug ─● v1.22.x  modularization
                              ○ v1.21.x  download-core split
                              ○ v1.20.0  three-state virtual cursor
                              ○ v1.19.x  mouse pointer + project article
                              ○ v1.18.0  login rescue
                              ○ v1.17.0  3-tier stealth
                              ○ v1.16.0  field-test fixes
                              ○ v1.15.0  DOM-precise mode
                              ○ v1.14.x  persistent login + security batch
                              ○ v1.13.x  login-wall downloads + fallback chain
                              ○ v1.12.4  vision session overhaul
```

```text
 v1.25.4 ●━ Oct   BUGS.md S6 synced: child-process UTF-8 env (GBK pipe crash fixed)
 v1.25.3 ●━ Oct   full live regression: --assemble crash fixed (never worked) · safe error fixed
 v1.25.2 ●━ Oct   sync verdict: ok bound to returncode · invisible-char sanitization
 v1.25.1 ●━ Oct   external audit 8 suspects: 4 fixed · 4 shelved with evidence
 v1.25.0 ●━ Sep   search stress: shell resolution · 2.2x concurrency · LAN search
 v1.24.1 ●━ Sep   downloads: hang root-cured · font-obfuscation deobfuscation
 v1.24.0 ●━ Sep   global watchdog --timeout
 v1.23.x ●━ Sep   yt-dlp switches · vision trio · first test suite
 v1.22.x ●━ Aug   5-batch modularization · 17 stress fixes · exit-code semantics
 v1.21.x ●━ Aug   download-core split · quick click + ripple
 v1.20.0 ●━ Aug   three-state virtual cursor
 v1.19.x ●━ Aug   mouse pointer · full audit · ARTICLE.md
 v1.18.0 ●━ Aug   login rescue --login-rescue
 v1.17.0 ●━ Aug   3-tier stealth --stealth
 v1.16.0 ●━ Aug   viewport / new-tab / gallery fixes
 v1.15.0 ●━ Aug   DOM-precise mode + read-back verification
 v1.14.x ●━ Aug   persistent login --profile · security batch
 v1.13.x ●━ Aug   login-wall downloads --cookies · 6-route chain · lazy galleries
 v1.12.4 ●━ Aug   vision session overhaul + 12 critical bug fixes
```

## Monthly Index

### October 2026

| Version | Date | Type | Summary |
|---|---|---|---|
| v1.25.4 | 10-25 | Fix | BUGS.md S6 synced: Python child processes get `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1` (GBK pipe `UnicodeEncodeError` on `\xa0` fixed); shared `child_env()` wired into runner + own_search download + search_and_cache (2 calls); 9 regression checks, suite 11 files |
| v1.25.3 | 10-24 | Fix | Full live regression across search/download/verify: `verify_capture --assemble` set\|tuple TypeError fixed (feature never worked since the first commit); safe-mode rejection now reports the real reason; live matrix covered file/video/audio/image/novel/folder/zip/yt-dlp/verify/own_search/vision |
| v1.25.2 | 10-15 | Security·Fix | Sub-service sync-list verdict: S1 envelope `ok` bound to returncode; S2 invisible-character sanitization ported & wired at the aggregation source; S3 acceptance landed; 21 new tests, suite 10 files all green |
| v1.25.1 | 10-04 | Security·Fix | External audit, 8 suspects: 4 confirmed & fixed (deletion guard / URL whitelist double-guard / browser watchdog / dead code), 4 shelved with evidence |

### September 2026

| Version | Date | Type | Summary |
|---|---|---|---|
| v1.25.0 | 09-28 | Perf·Features | Full search stress round: redirect-shell resolution, 4-way engine concurrency 2.2x, browser-death protection, 31-engine census, LAN search, --site suffix-match fix, engine HTML fixture tests |
| v1.24.1 | 09-24 | Fix·Features | Download focus: hang root-cured (single JS eval + bounded close), Fanqie novel font-obfuscation deobfuscation, text-route login state & TOC completeness |
| v1.24.0 | 09-14 | Features | `--timeout N` global watchdog; Fanqie/Qidian/Ximalaya stress round; Qidian VIP reported honestly (no paywall bypass) |
| v1.23.3 | 09-14 | Fix | Audio-circuit login-page hijack fixed; NetEase song-page hang confirmed & recorded; all-platform matrix stress finale |
| v1.23.2 | 09-14 | Fix | Link-picking hijack by section pages root-cured (bare-homepage/item-page gates); `--query --auto` full-pipeline stress |
| v1.23.1 | 09-14 | Fix | Day-one self-review: frame order, --proxy covering the search step, swallowed error text, silent --playlist-max; 2 ruled not-bugs on record |
| v1.23.0 | 09-14 | Features | yt-dlp trio (playlists / audio extract / quality cap), vision trio (dialogs / upload / iframes), full-chain proxy, resumable downloads, download ledger, first real test suite |

### August 2026

| Version | Date | Type | Summary |
|---|---|---|---|
| v1.22.1 | 08-25 | Fix | "Request first, capture later" 6-move ladder; 17 fixes from 5-platform stress tests; exit-code semantics (real yield = 0) |
| v1.22.0 | 08-24 | Refactor | Full 5-batch modularization (auto_save/ + searchkit/ + unified runner); 7 bugs + 7 stress fixes + 5 audit fixes along the way |
| v1.21.1 | 08-23 | Refactor | Download-core split into auto_save/ (batches 1–2); AST diff + 162-case differential test, zero logic change |
| v1.21.0 | 08-23 | Features | Quick click (current mouse position) + click ripple feedback |
| v1.20.0 | 08-22 | Features | Three-state virtual cursor (hand / I-beam / arrow, morphs on hover) |
| v1.19.1 | 08-22 | Maintenance | Full code audit; author info; new ARTICLE.md project article |
| v1.19.0 | 08-22 | Features | Vision-session virtual mouse pointer (enlarged white arrow, real-time follow) |
| v1.18.0 | 08-22 | Features | `--login-rescue` login rescue (grafts local browser cookies); self-identifying session banner |
| v1.17.0 | 08-22 | Features | `--stealth` 3-tier disguise (default full, deep-fingerprint patches) |
| v1.16.0 | 08-22 | Fix | Viewport 1440×900, new-tab auto-tracking, gallery waits for images, CJK typing note |
| v1.15.0 | 08-22 | Features | Vision-session DOM-precise mode (text/selector locating + read-back verification) |
| v1.14.2 | 08-22 | Fix | Captcha detection off by default (false positives froze operations) |
| v1.14.1 | 08-22 | Fix | Captcha false-positive tightening + `--captcha-mode allow` + `--linger` + `--idle-timeout` |
| v1.14.0 | 08-22 | Features·Security | `--profile` persistent login; cookies-from-browser effective everywhere; safe-mode 2GB hole + 5 more fixes |
| v1.13.1 | 08-22 | Fix | SPA lazy-loaded gallery iterative scroll-harvest; cross-origin CDN fallback |
| v1.13.0 | 08-22 | Features | `--cookies` login-wall downloads; fallback chain 5→6 routes; Douyin note auto-reroute |
| v1.12.6 | 08-22 | Maintenance | Default-branch fix (single main branch); mascot moved to assets/ |
| v1.12.5 | 08-22 | Fix·Maintenance | eval deadlock watchdog; own_search subprocess timeouts; mascot added |
| v1.12.4 | 08-22 | Fix | Vision session overhaul + 12 critical bug fixes (incl. previously unreleased v1.12.2~3 internal iterations) |

## Detailed Entries

### v1.25.4 (2026-10-25)

BUGS.md sync-list compliance round: re-audited the sub-service's "main-project sync list" after v1.25.3 and found **S6** (added 2026-10-16) had been missed. Synced with constructive proof.

- **S1/S2/S3**: already synced in v1.25.2 (S2 sanitization was deliberately placed at the engine aggregation source rather than per-exit, documented in that release).
- **S4/S5**: memos only, no code change (unchanged verdicts).
- **Fixed S6 (stability): Python child-process GBK pipe crash** — `runner.py` called `subprocess.run(..., encoding="utf-8")` on the parent side, but the **child** still wrote JSON to a GBK pipe on Chinese Windows; `search.py`/`search_browser.py` use `ensure_ascii=False`, so a snippet containing `\xa0` raised `UnicodeEncodeError` inside the child → intermittent `exit 1` ("works sometimes, fails sometimes"; a terminal already set to UTF-8 masks it locally).
  - **Proof**: grep showed no `PYTHONIOENCODING`/`PYTHONUTF8` anywhere in `scripts/`; forcing `PYTHONIOENCODING=gbk, PYTHONUTF8=0` and printing `\xa0` reproduced `UnicodeEncodeError` (exit 1); with the new env the same code exits 0 and round-trips `\xa0`.
  - **Fix**: new shared `child_env()` in `searchkit/runner.py` (copies `os.environ`, then forces `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`, overriding inherited values). Wired into the three places that parse a Python child's JSON stdout: `runner.run_search_cli` (covers smart/cross/own_search seed), `own_search.cmd_download`, and both `search_and_cache` calls (`run_search` and `cache_url`).
  - **Regression**: new `tests/test_sync_s6.py` — 9 checks (env semantics / GBK constructive crash / child_env recovery / all three call sites actually pass `env`). Suite now **11 files, all green**.

### v1.25.3 (2026-10-24)

Full live regression across legacy search/download/verify features (prompted by "old features may still break"). Two confirmed bugs, fixed with reproducible evidence; everything else passed or failed only for environmental reasons.

- **Fixed (high, crash): `verify_capture.py --assemble` was never functional** — `files = [... if p.suffix.lower() in VIDEO_EXTS | AUDIO_EXTS]`: `VIDEO_EXTS` is a `set`, `AUDIO_EXTS` is a `tuple`, so the expression raises `TypeError: unsupported operand type(s) for |: 'set' and 'tuple'` **before reading any file**. Proof: (1) running `--assemble downloads/_assemble_probe` produced the traceback at verify_capture.py:212; (2) git history shows the same expression in the very first commit `b8e7b4d` (v1.11.1) while the constant types never changed — the feature has never worked in any release; (3) after `VIDEO_EXTS | set(AUDIO_EXTS)`, the same directory assembled 4 segments into a 110.01s file (ffmpeg real-decode verified). Regression check added to tests/test_audit_fixes.py.
- **Fixed (low, diagnostics): safe-mode rejection lied about the cause** — with `--safe`, archives (`.gz/.zip/...`) are refused by the on-disk whitelist (`SAFE_ALLOWED_EXTS` = media + txt/json), but `_files_route` fell through to the generic `"file direct download failed (link dead / TLS-blocked / is a webpage)"`, so a whitelist refusal looked like a dead link. Now `_files_route` pre-checks the whitelist and reports `safe mode 拒绝: 非白名单扩展名 .gz`; normal (non-safe) downloads unchanged. Two regression checks added.
- **Live test matrix (what was tested)**:
  - Search: lightweight `--json/--brief/--site/--category all/--engines/--ad-filter none/--precision 100/--no-resolve`, browser search (`--json/--brief/--site/--stealth off/--timeout`), smart_search (plain + `--browser`), cross_search (`--json`, `--mega --copies 1 --rounds 1`), API engines without keys (tavily/brave/searxng correctly report `set XXX_API_KEY`).
  - Downloads: direct file (8.7MB tar.gz, 2s, quality=full), Bilibili video via chain (`quality=full`, 15.6s), yt-dlp `--quality 480p` (13.4MB) and `--extract-audio mp3` (2.2MB), direct audio, image gallery harvest (local fixture 6/6; 250-image fixture capped at exactly 200), lazy `data-src` gallery 4/4, novel TOC chapter merge 6/6 (4717-byte txt), folder page batch (2/2 files), `--zip` bundle (zip entries verified intact), `--safe` block behavior, `--query --auto` search-then-download, screenshot, text extraction.
  - Verify: `--dir` scan, `--clean`, `--clean --keep-broken` (junk deleted, broken kept), `--recheck` (MD5 stable), `--assemble` (fixed).
  - own_search: `crawl` → `search`, `seed`, `lan` (private-IP guard), `stats`, `download` passthrough; `file://` rejected; `--hosts 8.8.8.8` rejected.
  - Vision: `test_vision_e2e.py` 12/12 (elements/iframe click/dialog accept-dismiss/upload) + offline checks.
  - Negative: nonexistent cookies file (honest warning + exit 1), dead proxy (bounded by watchdog), nonexistent dir (exit 2), page requested as video (honest empty).
- **Environment-caused failures, not product bugs (evidence recorded)**: w3.org SSL handshake timeout (130s) and zh.wikipedia connection timeout — network walls; SoundHelix mp3 only ~11KB/s (curl measured 655KB/60s), so an 8.9MB file cannot finish quickly — server throttling; running tests with the Hermes venv Python (no playwright) made vision/timeout tests fail — the project `.venv` passes all 10 files.
- **Suite**: tests/run_all.py **10 files all green** (audit file now 25 checks).

### v1.25.2 (2026-10-15)

Sync-list verdict round for the sub-service's `docs/BUGS.md` (5 items proposed for this repo; each judged under the "fix only at 100% confirmation" rule — **2 confirmed & fixed, 3 carried as memos with no fix instruction**; verdicts recorded here in this repo's own docs — BUGS.md belongs to the sub-service and is untouched):

- **Instruction triage**: of the 5 sync items, only S1/S2 are explicitly marked "pending sync to main repo"; S3 is S2's acceptance appendix (not an independent bug — this regex never existed here); S4 is explicitly N/A; S5 is a server-deployment memo. All second-round entries (I1-I4/P0/P2) are sub-service-internal — none claims the main repo affected.
- **Fixed S1 (stability, sub-service P1 counterpart)**: both code claims verified 100% — `dispatch.py` `_format_plain` subscripts `data["results"]` directly (L125) and `runner.py` sets `envelope["ok"] = True` unconditionally (L154: empty stdout coerced via `or "{}"`). Constructive reproduction: subprocess rc=1 with valid JSON / rc=0 with empty stdout → `data={}` delivered as success → consumer KeyError. Fixed: runner `ok` bound to `returncode == 0` (rc≠0 gets `subprocess exit N`); dispatch uses `.get("results") or []`. Compatibility audited: of 4 consumers only smart_search changes behavior (now takes the designed error-placeholder branch); routing/cross_search/own_search were already `.get`-guarded.
- **Fixed S2 (security, sub-service I2 counterpart)**: invisible-character stripping in main repo scripts/ — **zero hits across 17 grep patterns (no protection at all)**; zero-width/bidi/Unicode-Tag chars (ASCII Smuggling carriers) could flow from web pages into AI prompts. Ported the sub-service sanitize.py (≥2026-10-04 build) as `searchkit/sanitize.py`; architecture differs: the sub-service sanitizes at its server output (engine layer stays dependency-free), while this repo has no server — sanitization sits at the **engine aggregation source** (before dispatch/browser returns + own_search ingestion), so all 5 `_format_plain` copies and JSON stay clean automatically without per-exit wiring (the drift breeding ground).
- **S3 acceptance landed**: the mandated case `sanitize_output('abc123 XYZ 中文 456 https://a.com/x?y=1 2026年')` round-trips byte-identical (P0 lesson: a bad escape once ate all ASCII); codepoints ≥5 hex digits always use `\UXXXXXXXX`.
- **S4 review note (recorded, not fixed)**: BUGS.md's wording "main repo has no open-arbitrary-URL feature" is imprecise — own_search's add/crawl/download subcommands all accept a user `--url`; however the input source is the local operator, not untrusted external input, so the SSRF threat model does not apply and the N/A verdict stands. If this repo ever becomes a server, adopt the sub-service's pinned-connection implementation directly (S4's reminder is valid).
- New tests/test_sync_s1s2.py (21 checks: constructive KeyError elimination / ok binding / ASCII acceptance / Tag-block stripping / VS16 preservation / field sanitization / integration smoke); tests/run_all.py **10 files all green**.
- Standing decision: **not pushed to GitHub** — batched release pending.

### v1.25.1 (2026-10-04)

External-audit verdict round (DeepSeek 4.1 flagged 8 suspects; each verified with evidence — 4 confirmed & fixed, 4 shelved as non-bugs with reasons; suite now 9 files):

- **Fixed ① (high, destructive): `verify_capture.py --clean/--assemble` directory boundary** — any `--dir` used to be accepted, and the junk verdict includes "image <150KB", so pointing it at e.g. a photo album would irreversibly delete real small images. Now destructive ops require the target inside this project's `downloads/` tree (`_within_downloads`), otherwise exit 2 with a clear refusal.
- **Fixed ② (high, security): `own_search` URL scheme whitelist** — `crawl --url file:///C:/windows/win.ini` could read local files into the index (stdlib urlopen natively supports file://). New `_require_http_url` guards **both** the urllib layer and the Playwright fallback layer (the crawl command's `except` used to swallow the first rejection and retry via browser, where `goto file://` reads local files just the same — double guard is required, verified by test). `lan --hosts` likewise used to bypass the RFC1918 net-range guard (`--hosts 8.8.8.8` scanned the public net); every explicit host must now be a private IP, verified live.
- **Fixed ③ (interface gap): `search_browser.py` gains `--timeout N`** — the global watchdog existed only in auto_save_browser (v1.24.0), so the "AI agents always pass `--timeout 600`" advice was unusable on the browser-search CLI. Same semantics (default 0 = off, `[timeout]` marker, exit 1); implementation hoisted to `searchkit.runner.start_global_timeout` shared by both facades (removes a duplicate copy flagged by the audit).
- **Fixed ⑧ (dead code): `verify_capture._md5_file` removed** (zero callers); note the audit's `check_local_index` claim is refuted for this repo — it has live callers in cross_search.
- **Shelved with evidence (non-bugs)**: ④ GBK stderr second-crash claim — disproven by experiment (Python 3.14 stderr emits UTF-8 with backslashreplace semantics; Chinese written without error); ⑤ cross_search low-confidence labels are honest reporting, not a defect; ⑥ relevance/keyword-table coverage limits (documented, not logic bugs); ⑦ `_format_plain` ×5 / STEALTH_JS ×3 / USER_AGENTS ×2 duplicates are maintenance debt, deliberately deferred (watch item: QA-1-style drift already happened once between copies).
- New tests/test_audit_fixes.py (22 checks: boundary/scheme/private-net/watchdog/dead-code); tests/run_all.py **9 files all green**; live-fire normal paths verified (in-downloads --clean works, https fetch works).
- Not pushed to GitHub yet — batched release pending per maintainer decision.

### v1.25.0 (2026-09-28)

Full search stress test + optimization (assets & data: downloads/_search_stress/):

- **Redirect-shell resolution (new, fixes major correctness bug)**: Baidu/360 results are all encrypted redirect shells, and the old dedupe dropped their query params — keys collapsed to one, **8 Baidu results deduped to 1 (7 wrongly killed)**. Fixed: shells keep their query in the dedupe key; new `searchkit/resolve.py` concurrently resolves shells to real URLs (302 follow / shell-page JS extraction, 11/11 restored to real addresses like docs.python.org in testing; same-site landing guard against captcha pollution; failures keep the shell). `--no-resolve` to disable.
- **Concurrent lightweight engines (2.2x)**: 17 engines serial 45-54s → concurrent (4 workers) **~21s**; smart_search/cross_search/own_search benefit via the shared runner.
- **Browser-death protection (issue #2 handled)**: stress test F2 proved it worse than documented — after a playwright driver dies, `page.goto` **hangs forever** while python spins (565s CPU observed), with no in-process timeout. Handled: download-circuit search steps moved to subprocess isolation (bounded timeout); browser run_search checks `is_connected()` per engine and marks dead-browser engines as skipped instead of white-waiting.
- **JS-failure verdict** (matrix C): nothing hangs (all bounded); bing/baidu are SSR (results survive JS-off), so360 needs JS; architectural fallback = the lightweight route needs no JS.
- **Engine health**: Sogou/360 serve captcha pages to anonymous requests — HTML engines now report `captcha suspected` instead of a blanket "no results".
- **Full engine census (31 engines tested one-by-one)**: lightweight ok=8/flaky=2; browser ok=2/flaky=1; the rest are network walls and anti-bot (details in downloads/_search_stress/census_*.json). **Fixed two browser engines dead since launch** — arxiv (result titles `<p class="title">` are plain text without `<a>`, the old selector could never get an href) and Eastmoney (real container `div.news_item` with underscore vs the old `.news-item` with hyphen); `_extract_from_items` gains optional `url_sel` for title/link-split structures. API engines (tavily/brave/searxng) now report `set XXX_API_KEY` honestly when unconfigured instead of pretending "no results".
- **Engine HTML fixture tests (new, first step for issue #4)**: tests/test_engine_fixtures.py + tests/fixtures/engine_html/ (real recorded bing/baidu responses + minimal-structure sogou/360/DDG fixtures) assert parse counts and field completeness — after a site redesign, one run tells you which selector to fix; suite now 7 files.
- **LAN search (new, own_search.py lan)**: discovers LAN devices/HTTP services/NAS/SMB shares into the local index — read-only probing (TCP port probe + HTTP title/Server identification + `net view` share enumeration), hard-restricted to private ranges (RFC1918), stdlib-only. Verified live: 254 hosts ×12 ports in 15s, correctly identified the Xiaomi router; `search --query 路由器` hits immediately after indexing.
- **Search unit audit round (strict evidence process)**: 4 suspects tested one-by-one — (1) the 16s tail on walled engines despite timeout=8 is stdlib's *per-operation* timeout semantics (DNS 0.1s / connect 8.0s / data-layer wall proven separately; not a code bug); (2) **`--site` substring-match bug fixed** (`--site python.org` used to admit `notpython.org.evil.com`; now host-suffix match, end-to-end re-verified with zero violating hosts); (3) **news keyword-table fix** ("今天/最新" over-broad words removed — "今天天气怎么样" was classified news, now falls back to general while strong news queries unaffected); (4) dedupe's rebranded-title culling is the intended anti-spam design (locked in as regression). New tests/test_search_units.py (5 tests); suite now 8 files, all green.
- **Data**: Slow3G / 6x CPU throttle cause no material change (SSR engines hold); offline fails fast in 4.1s; tests/run_all.py 8 files green.

### v1.24.1 (2026-09-24)

Download-pipeline fixes (hang root-caused + novel completeness):

- **Hang root-caused (issue #1 closed)**: two stacked causes — (1) `_extract_body_text` probed 11 selectors via `page.inner_text`, each missing selector waits up to 30s on Fanqie reader pages (custom divs match none) → ~330s wasted per chapter, a 351-chapter book never finishes; (2) `browser.close()` blocks forever on pages with live WebSocket/SSE. Fixed: body extraction now one bounded JS evaluation; `_eval_bounded` caps every unbounded evaluate (driver-enforced timeout); `_close_bounded` closes page→context→browser in order on the main thread (0.7s on the same page); new `[stage]` timing logs make any future hang visible in one line.
- **Novel font-obfuscation deobfuscation (new)**: about half of Fanqie chapter text uses Private-Use-Area codepoints (renders fine via a CDN woff2, but extracted text loses characters). New `auto_save/novel_font.py` builds a glyph-bitmap mapping from the font (cached in `index/`); 338/362 codes restored in testing, prose reads correctly. Deps fonttools/brotli/pillow/numpy added to requirements.txt; degrades gracefully to raw text if missing.
- **text route login state + TOC completeness**: `--cookies-from-browser/--profile/cookie_file` now supported on the text route (use your own account entitlement); TOC scroll-expands to collect all chapters; `--max-chapters 0` = unlimited; skipped chapters are classified (vip/lock signals) and reported honestly in JSON. **No paid/VIP bypass** — stance unchanged.
- **Verified**: Fanqie full book 351/351 chapters, 0 skipped, 497KB (old code couldn't finish 10 chapters in 300s); Douyin video quality=full (16.3s ffmpeg-verified); tests/run_all.py 6 files green.

### v1.24.0 (2026-09-14)

New source-type stress round (Fanqie novels / Qidian / Ximalaya) + an AI-Agent fuse:

- **`--timeout N` global watchdog (new)**: each chain stage has its own timeout but **their sum is unbounded** — extreme pages (NetEase song pages, confirmed in v1.23.3: 15 minutes of silence) can hang forever. Any command with `--timeout 600` now hard-exits after N seconds (stderr `[timeout]` marker + exit 1), giving AI agents a "guaranteed to finish" promise. Subprocess kill-test added to the suite (tests/test_timeout_watchdog.py; suite now 6 files, all green).
- **Fanqie novels (web free tier): second hang confirmed** — the static HTML exposes 352 "第X章" links (TOC parsing fine), but the text route hangs with the same signature as NetEase (near-zero CPU, zero output); **`--timeout 90` proven live: forced exit at 90s with exit 1 + the [timeout] marker** — the new watchdog covers exactly these cases.
- **Qidian VIP behavior, honestly**: for a 1401-chapter book the text route captured exactly **3 chapters** (the free previews), merged into a 29KB txt and labeled 3/1401. The tool takes what the web actually shows and **does not bypass VIP/paywalls** (access-control circumvention is out of scope); content that's free in the mobile app should be consumed in the app.
- **Ximalaya audio**: audio circuit exercised (see stress records).

### v1.23.3 (2026-09-14)

All-platform matrix stress round (Bilibili/Kuaishou/Douyin/Weibo/NetEase/Xiaohongshu/WeChat-article/novel-site/GitHub/w3.org across video, image-text, text, music, files): 1 fixed, 1 confirmed-unfixed honestly, limitations recorded as-is.

- **Fix: audio-circuit login-page hijack** — searching "网易云音乐 周杰伦 晴天", the audio round host-matched `music.163.com/login` as the "audio target" (same family as the v1.23.2 video-circuit bug). `_looks_like_item_page` gains audio tokens (song/songDetail/play_detail/sound/album/playlist/program), a query `id=\d` signal (music.163.com/song?id= style item pages), and a login/register veto; the text circuit skips login pages too; `test_routing_offline.py` +8 assertions (suite all green). After the fix the same query honestly returns empty (no song URL existed in results) instead of downloading a login page.
- **Confirmed, unfixed: NetEase song-page direct link (music.163.com/song?id=) hangs** — harvest/chain exceeded 15 minutes with zero stderr output, process idling at near-zero CPU (iframe-rendered page, suspected unbounded wait somewhere). Recorded in the SKILL.md self-heal table (Ctrl+C + switch to `--method ytdlp`); the proper cure is a global `--timeout` watchdog (each chain stage is bounded, their sum is not).
- **Stress matrix (evidence kept in downloads/_stress_v123/)**: Kuaishou video full (27MB mp4 via sogou redirect → yt-dlp); Douyin video full (1.15MB); Weibo full (43 files, request-first refetched mp4s); Bilibili baseline full (28MB); image circuit fell back to Baidu Image and harvested 200 images / 21.5MB (partial; XHS originals need login — documented limitation); w3.org PDF full (UA ladder beats JA3-style Chrome-UA blocking — the v1.22.1 fix works in the field); Journey-to-the-West chapter merge 5/5 chapters into one 106KB txt (chapters-merged); WeChat-article text extraction 16KB (partial).
- **Recorded honestly (not tool bugs)**: arxiv.org unreachable from this network at every layer (connections reset for urllib and yt-dlp alike); yt-dlp.zip asset does not exist (wrong test URL — the tool 404'd honestly and junk→exit-1 semantics held); overseas platforms (YouTube/X) untested (network environment).

### v1.23.2 (2026-09-14)

Stress-test finale: the `--query --auto` full-pipeline stress test caught a **link-picking flaw dating back to v1.22.0** and root-cures it; the skill's quick-pick table gains the new switches.

- **Fix: section pages hijacking link picking** — searching "B站 猫 视频", the platform round selected `t.bilibili.com/index.html` / `bilibili.com/read/home` (section/pseudo homepages) on host match alone, and the whole chain harvested avatar thumbnails on the wrong page (junk). Two platform-agnostic layers: `_is_bare_homepage` now recognizes homepage filenames (index.html/htm, default, home); a new `_looks_like_item_page` gate requires an item-page shape (path with /video/, BV-id, watch keywords, or an ID-like last segment — covers both youtu.be short IDs and numeric IDs), applied to both picking rounds. **Verified live**: the same query now lands on a sogou redirect → yt-dlp resolves the real video BV1GVMszFETr → 2.7MB mp4, quality=full, exit 0.
- **tests**: new `test_routing_offline.py` (18 assertions for bare-homepage/item-page verdicts); suite grows to 5 files.
- Stress matrix (v1.23.1 code + this fix): full suite (5 files), Bilibili `--quality 480p` (full), `--extract-audio mp3` (full), dead-port proxy fast-fail (`WinError 10061` proves proxy reaches yt-dlp), `.manifest.jsonl` ledger on disk, `--query --auto` full pipeline (junk before the fix → full after).

### v1.23.1 (2026-09-14)

Self-review of v1.23.0 on day one (every suspect walked the full verdict → reasons → counter-question → confirm loop): 4 fixed, 2 ruled not-bugs with rationale kept on record.

- **Fix: frame-order assumption** — `page.frames[1:]` implicitly assumed index 0 is the main frame; Playwright only contracts the `main_frame` property, not list order. Now filtered by identity (`fr is not page.main_frame`, 3 sites).
- **Fix: `--proxy` didn't cover the `--query` auto-search step** (while help claimed "every exit path") — counter-question revealed `run_search` already had a `proxy` parameter; all 6 `_search_first_media_url` call sites now pass `proxy=get_proxy()`, so the help text stands.
- **Fix: `_vision_find_el` swallowed Playwright's selector-parse error text** (diagnostics regression) — exception text is preserved into the note again.
- **Fix: `--playlist-max` without `--playlist` was silently ignored** — same class as issue #3 of the project's own v1.12.1 review ("`--safe` accepted but never effective", rated high); a one-shot stderr warning now fires.
- **Ruled not-bugs (on record)**: ① resume lacks ETag/If-Range content validation — strictly better than the old behavior, a full fix needs persisted validators, and media has ffmpeg decode verification as a backstop (documented as a known limitation in the docstring); ② finished file coexisting with `.part` — atomic `replace` plus the already-cached short-circuit make it unreachable in normal flow.
- **Regression**: `tests/run_all.py` all 4 files green; `--playlist-max` warning and download behavior live-tested (count=1); `routing.get_proxy` wiring unit-checked.

### v1.23.0 (2026-09-14)

Capability release: yt-dlp switches + vision-session trio + download-chain proxy/resume/ledger + the project's first real test suite. Zero default-behavior changes (everything is opt-in).

- **yt-dlp switches**: `--playlist` / `--playlist-max N` (download full collections — noplaylist was hardcoded; single-video semantics stay the default); `--extract-audio --audio-format mp3|m4a|...` (audio-only stream saves half the traffic, ffmpeg transcodes); `--quality best|1080p|720p|480p|360p` (resolution cap). Two live-test lessons: the format fallback chain must end in `bestvideo+bestaudio` (DASH-only sites like Bilibili have no progressive single file, so bare `best` never matches); portrait videos' "height" is the long edge (their 480P tier is 480x852), so a `width<=N` alternative is required to hit the same-named tier.
- **Vision-session trio**: ① **Dialogs** — Playwright silently auto-dismisses alert/confirm/prompt by default; the AI never knew a dialog appeared and confirm-based flows were unreachable. Now every dialog is reported via `dialog_events` (still dismissed by default — zero breakage), and `{"action":"dialog","accept":true}` sets a one-shot accept policy (prompt can carry reply text). ② **File upload** — the `upload` command with a 3-step ladder: explicit input selector direct-set > `click_selector` file-chooser interception (expect_file_chooser, the mainstream upload pattern) > auto-find input[type=file] across all frames. ③ **iframes** — elements now annotate cross-frame (child-frame coordinates offset by the iframe's bounding box into main-viewport space, `frame` field marks the source); selector/text locators fall back frame-by-frame when the main frame misses (child-frame bounding_box is officially main-viewport-relative, so coordinate clicks need no conversion).
- **Download-chain additions**: ① `--proxy` plumbed through every exit path (Chromium launch both persistent and one-shot, three raw-urllib sites, yt-dlp, share-link resolution — the download core previously had no proxy support at all); ② **resumable downloads** — files now write to `.part` + `Range: bytes=N-`, resuming after interruption (a 2GB file cut at 90% no longer restarts), renaming only on complete EOF (fixes half-files wearing finished names), with honest handling for no-Range servers and already-cached files; ③ **download ledger** — `.manifest.jsonl` records url→file/size/md5 (<8MB) line by line, traceable across runs.
- **tests/ (the project's first real test directory)**: `python tests/run_all.py` runs everything, pure stdlib with zero new dependencies, 3 files / 28 checks — ytdlp option dict shapes, resume + proxy effectiveness (a local HTTP server with hand-built Range support + a dead-port proxy-must-fail probe), ledger fields, vision command registration.
- **Verified live**: Bilibili `--quality 480p` (13.4MB product) and `--extract-audio mp3` (2.2MB) end to end; `--playlist` on a single video still downloads exactly 1; vision trio 12/12 on a local HTML test page (iframe element annotation, in-iframe click, confirm report + accept, dismiss semantics assertion, both upload moves, filename readback).

### v1.22.1 (2026-08-25)

Fallback-chain activation ("request first, capture later") + 17 fixes from 5-platform stress tests. No usage changes — pure bug fixes plus one paradigm upgrade.

- **New media-fetch paradigm — "request first, capture later" (6-move ladder, feedback-driven, stop on first success, ≤6 total attempts)**: ① tab (in-page fetch with full cookies/referer) → ② desktop (HTTP, desktop UA + referer) → ③ mobile (mobile UA) → ④ bare (no referer) → ⑤ refresh (reload page for a fresh signed URL) → ⑥ fallback round. Feedback-driven: 403 → switch persona; truncated 200 → jump to refresh for a new ticket; 416 → pure GET.
- **Douyin (5)**: segment merger now sorts by Content-Range file offset (out-of-order arrival was corrupting every merge); fMP4 init segment (moov header) merged into its group; byte-identical duplicate segments dropped (login-wall 11×204801B re-sends no longer corrupt files); promo-material domains (douyinstatic/bytednsdoc — an 11MB PC-client installer video!) vetoed at domain level; JSON-escaped URLs (`\/`, `\u002F`) decoded and pseudo-extensions (.image/.awebp) recognized so gallery images stop being missed.
- **Kuaishou (4)**: a complete stream arriving as a single response is now promoted directly (the old "merge needs ≥2 segments" rule was killing whole videos); 206 partial blocks must cover through EOF before promotion; unreadable response bodies (inspector cache evicted) are recorded to the full-refetch ledger instead of silently losing the stream; escaped gallery URLs pre-decoded.
- **Bilibili (4)**: CDN mirror dedupe (path + basename dual gauge, mcdn route prefix normalized — same file was being downloaded 2–3×); content-hash dedupe (byte-identical second copy dropped); yt-dlp product quality-gate fix (a short-circuit `url or path` misjudged 21.5MB files as junk, sending the whole chain re-fetching 188MB); site-asset domain blocked (13MB wallpaper pack).
- **NetEase Music / Xiaohongshu (4)**: yt-dlp progress lines no longer pollute `--json` stdout (`noprogress`); iframe-rendered pages (NetEase g_iframe) now harvested; homepage redirects recognized as downgrades (not follow-through); Xiaohongshu login-wall decoration images blocked (fe-platform.xhscdn).
- **General**: **exit-code semantics — success (real yield) = 0, failure/junk-only = 1** (previously always 0, hosts couldn't retry on failure); quality gate backfilled for files/direct/text routes (a 60MB intact download used to report `quality: null`); Chromium channel preference + hardware video decode disabled + SwiftShader software rendering (root-causes the sandbox false-kill on AI hosts); JSON serialization `default=str` guard (a `set` once crashed output); install_dependencies.py pip detection fix.
- **Stress-test matrix (all passing)**: NetEase Music via ytdlp (full), Bilibili via browser (full — streams + covers, dedupe active), Douyin via chain (full — promo material blocked, exit 0), 60MB file via files (byte-exact match), small exe via files (full).

### v1.22.0 (2026-08-24)

Full modularization refactor (5 batches) + 5-platform stress-test fixes:

- **Batches A/B (download side)**: vision-session protocol split into `auto_save/vision.py` + `shots.py`; download routes split into `auto_save/routes.py` (browser/cache/harvest/files/text); `auto_save_browser.py` slimmed from 4700+ to 1132 lines.
- **Batches C/D (search side)**: `search.py` (961 lines) split into the `searchkit/` package — http/normalize/adfilter/dispatch + engines/ (20 engines in 5 categories); `search_browser.py` (820 lines) merged into searchkit sharing normalization/dedupe/ad-filter/ranking, and the **duplicate engine tables are gone** (light and browser versions now use one unified CATEGORY_ENGINES table, filtered by mode availability at dispatch time).
- **Batch E (dispatcher side)**: the duplicated "pick script → build args → subprocess → parse" logic in smart/cross/own converged into a single `searchkit/runner.py` executor with engine-count-adaptive timeouts (the all-category's 17 engines no longer get killed by a timeout sized for 9).
- **7 real bugs fixed along the way**: arxiv engine's wrong `ns=` parameter name (the academic engine had been broken all along), 3 missing imports in engines/, `--brief` plain-text crash, Chinese precision ranking never working (`\w+` tokenization glued whole Chinese sentences into one token — switched to bigram tokenization).
- **7 stress-test fixes** (live-tested on Douyin/Xiaohongshu/Kuaishou/Xiaoheihe/Qishui Music + two rounds of user reports): ① search picking a platform's bare homepage as a "video link" — now skipped, plus a `_platform_search_url` fallback for 8 platforms; ② engine-indexed platform search pages carrying only partial keywords — now auto-upgraded to full-keyword search pages; ③ yt-dlp running 3 times in chain mode — a `ytdlp_fallback` switch dedupes it inside the chain; ④ harvest saving SVG sprites/login banners/ad images/guide images as "content" — junk-filter rules extended; ⑤ Xiaohongshu search pages asking for images but getting force-routed to the video pipeline by the "video-site veto" — explicit `--media-type` now wins on search/list pages; ⑥ malformed `duration Nones` log line; ⑦ **yt-dlp filename exceeding Windows' 260-char path limit** (Qishui Music's URL params crammed into title/id, all three routes dying with Errno 2 on the `.part` file) — outtmpl truncation + `trim_file_name` hard cap; verified 598 → 97 chars, file writes fine. Round 2 (/note/ posts): ⑧ note reroute was undiagnosable and music-post harvests got dropped — empty/image-only harvests now logged and recorded in attempts as `harvest(note)`, and when the user wants audio/video that harvest can't provide, the chain proceeds to grab the stream and merges the harvest back; ⑨ mojibake fix rolled back (forcing UTF-8 caused mojibake on GBK terminals — Python's locale default is correct); ⑩ exit code 1 identified as an environment-layer false alarm (Chromium hardcodes a debug.log next to its exe; sandbox/AV interception flags the whole command, while main() provably returns 0).
- **Full mode audit fixes (5)** (switch inventory + plumbing check across all 6 entry points): ①searchkit/browser layering inversion (search package imported infra via the download facade → now imports `auto_save.browser_base` directly); ②accompanying infra-copy drift (the fallback `_browser_launch_args` copy missed that same day's `--log-file` fix → unified import source); ③smart_search gained `--ad-filter/--precision/--category` end-to-end passthrough, own_search seed gained `--ad-filter`, runner gained precision/site passthrough; ④`--screenshot --profile` captured login-walled pages as empty shells → profile_dir passthrough
- **Structural cleanup (3 batches, easy → hard, zero logic change)**: batch 1 sunk 9 intent-routing functions into `auto_save/routing.py` (facade 1132 → 824 lines); batch 2 slimmed `searchkit/browser.py` 510 → 257 lines by splitting its 14 browser engines into an `engines_browser/` package (dom/web/dev/academic/alt); batch 3 converged the four duplicated browser-launch templates in routes.py (files/text/harvest/browser) into a single `browser_base._open_page()` — all differences became parameters (profile dir / download trust / self-signed-cert tolerance / random viewport / cookie injection), persistent-context fallback and failure self-cleanup semantics preserved, verified key-by-key equivalent with a fake playwright object (46 checks, all passing).
- **Compatibility contract**: the three facades (auto_save_browser/search/search_browser) remain the sole CLI entry points; every old name stays available via re-imports, so external import paths are unchanged; each batch verified by AST node-by-node diff + runtime acceptance.

### v1.21.1 (2026-08-23)

Download-core modularization refactor (pure structural cleanup, zero functional change):

- **`auto_save_browser.py` split by safety level into the `scripts/auto_save/` package**: batch 1 = constants / ffmpeg / cookies, batch 2 = urlrules (pure URL/media/security classification functions) — the main file slimmed from 4393 to ~4140 lines, all nine routes intact.
- **Compatibility contract**: `auto_save_browser.py` remains the sole CLI entry point and the only module imported externally; every old name stays available via re-imports, so external call paths are unchanged.
- **Pure-move verification**: AST node-by-node diff against the git HEAD original confirms all 29 extracted definitions are logic-identical; 162-case differential test shows old/new outputs identical for the same inputs; `__all__` re-exports added for 51 package-level names; text/direct/files routes verified end-to-end in a real browser, byte-identical to the original.
- Side fix: restored a `List[Path]` type annotation drift from batch 1 (now literally identical to the original).

### v1.21.0 (2026-08-23)

Quick click + click ripple (pre-school-term wrap-up):

- **Quick click**: `{"action":"click"}` with no arguments clicks the **current mouse position** — aim with `move` first, then just send `click`; `{"action":"click","button":"right"}` right-clicks there. The coordinate mode (x/y) and DOM-precise mode (selector/text) are fully preserved — three coexisting modes, chosen per situation.
- **Click ripple feedback**: every click in all three modes draws an **expanding ripple** (white ring, black edge, ~0.5s fade) at the click point — the next screenshot shows exactly where the click landed (a 150ms pause ensures it's captured).
- Full check: all 9 scripts compile, AST parameter-chain check passes; quick/coordinate/DOM modes and the ripple verified live.
- Sporadic updates **possible** within the next week or two (maintainer heading back to school; unscheduled).

### v1.20.0 (2026-08-22)

Three-state virtual cursor (user feedback: a fixed arrow isn't like a real mouse):

- **The cursor now morphs like a real one**: hovering links/buttons → **pointing hand**; hovering input fields → **I-beam text cursor**; elsewhere → **arrow**. Switches automatically by inspecting the element under the pointer via CSS cursor (pointer/grab→hand, text or input/textarea/contenteditable→I-beam, else arrow).
- From a screenshot the AI now knows not just "where the mouse is" but "is the hovered thing **clickable (hand) / typeable (I-beam)**".
- All three shapes white-filled with black outline, hotspot-aligned (arrow/hand tips and I-beam crossbar center = the real mouse coordinate).
- Verified live: link on example.com = HAND, blank area = ARROW, Baidu input = TEXT — all pass.

### v1.19.1 (2026-08-22)

Maintenance release (full audit + author info + project article):

- **Full code audit**: all 9 scripts compile; AST parameter-chain check passes (no unknown args, no edit leftovers); all 8 stealth hookup points verified; 5 routes smoke-tested green. Historical low-severity leftovers (`\\n` log typo / English vision-session notes / concat-failure cleanup) confirmed all fixed — no new bugs found.
- **Author info**: Douyin ID 94636651553 added to SKILL.md / package.json / both READMEs.
- **New [ARTICLE.md](ARTICLE.md)**: the project's story — three iron rules (degradation chains / never trust declared metadata / never fabricate), vision-mode lessons, and the wisdom of not fighting login walls head-on.
- The project pauses updates for a week or two after this release (maintainer rest).

### v1.19.0 (2026-08-22)

Virtual mouse cursor for vision sessions:

- **Virtual mouse cursor (built into vision sessions, no flag needed)**: headless screenshots don't render the OS cursor — the AI previously had to guess "where is the mouse" from `screen.mouse` numbers. Sessions now auto-inject an **enlarged white arrow cursor (34px, black outline, visible on any background)** that follows the mouse in real time (CDP-driven move/click/drag all trigger it). The big white arrow in screenshots IS the current mouse position, consistent with screen.mouse.
- Implementation: injected overlay (pointer-events:none so it never blocks clicks, attached to documentElement so body-clearing pages can't drop it, waits for DOMContentLoaded); enabled only in vision sessions (fixed-position would misplace in full-page screenshots, so the standalone screenshot route skips it).
- Verified live: move(400,300) → cursor translate(398,298) in sync with screen.mouse(400,300), screenshots normal.

### v1.18.0 (2026-08-22)

Login rescue + self-identifying session logs (real-world: Douyin QR confirmed on phone but the web page still refused to log in):

- **New `--login-rescue`**: hard risk-control sites (Douyin etc.) confirm the QR on your phone but refuse to issue a session to an automated browser (CDP detection; fingerprint stealth can't help). The fix: log in to the target site in your everyday browser, then start the session with `--login-rescue` — it walks local chrome→edge→firefox, grafts whichever has target-domain login cookies into the session, and reloads. Result is honestly reported via stderr and the first-state `login_rescue` field; with `--profile` the refreshed session persists.
- **Local debug port auto-disabled for `--profile --headed` manual-login sessions**: the eval-watchdog DevTools port is one of the detection surfaces ByteDance-grade risk control looks at; it's now closed during login windows (the watchdog degrades to disabled — acceptable).
- **Vision session startup banner**: first stderr line shows `version | stealth | profile | headed | idle-watchdog | captcha | debug-port | login_rescue` — logs now prove which build produced them, ending the "an old copy behaves weirdly (e.g. 120s disconnect even with --headed)" mystery.
- Clarified the "120s no login detected" log: that's the idle watchdog counting AI-command gaps, unrelated to page login; new builds relax to 600s under --headed, so a 120s hit means an old copy was running.
- Verified live: banner / honest rescue reporting / JSON field all pass.

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
