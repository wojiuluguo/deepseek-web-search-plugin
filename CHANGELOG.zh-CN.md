# 更新记录（中文版）

完整版本历史。README 只保留最近 3 版摘要，详细记录全部沉淀在本文件。
英文版：[CHANGELOG.md](CHANGELOG.md)。功能说明见 [README.md](README.md)（英文）/ [README.zh-CN.md](README.zh-CN.md)（中文）。

## 版本时间轴

```text
                     ┌─ 10月 ─● v1.25.4  当前版本（2026-10-25）
                     │        ○ v1.25.3  旧功能全量回归
                     │        ○ v1.25.2  同步裁决 + 隐形字符净化
                     │        ○ v1.25.1  外部审计裁决
   2026 ─────────────┼─ 09月 ─● v1.25.0  搜索压测优化
   （由新到旧）       │        ○ v1.24.1  下载专项修复
                     │        ○ v1.24.0  全局看门狗
                     │        ○ v1.23.0~3 能力补强 + 压测
                     └─ 08月 ─● v1.22.x  模块化重构
                              ○ v1.21.x  下载核心拆包
                              ○ v1.20.0  虚拟鼠标三形态
                              ○ v1.19.x  鼠标指针 + 项目文章
                              ○ v1.18.0  登录兜底
                              ○ v1.17.0  伪装三档
                              ○ v1.16.0  实测四连修
                              ○ v1.15.0  DOM 精准模式
                              ○ v1.14.x  登录持久化 + 安全批修
                              ○ v1.13.x  登录墙下载 + 兜底链
                              ○ v1.12.4  视觉会话全面修复
```

```text
 v1.25.4 ●━ 10月   BUGS.md S6 同步：子进程 UTF-8 环境（GBK 管道崩溃修复）
 v1.25.3 ●━ 10月   全量实测回归：--assemble 崩溃修复（从未可用） · safe 报错修复
 v1.25.2 ●━ 10月   同步裁决：ok 绑定 returncode · 隐形字符净化
 v1.25.1 ●━ 10月   外部审计 8 条：4 修 · 4 搁置留证
 v1.25.0 ●━ 09月   搜索压测：壳解码 · 并发 2.2x · 局域网搜索
 v1.24.1 ●━ 09月   下载专项：挂死根治 · 字体反爬还原
 v1.24.0 ●━ 09月   全局看门狗 --timeout
 v1.23.x ●━ 09月   yt-dlp 三开关 · 视觉三件套 · 首个测试目录
 v1.22.x ●━ 08月   模块化重构五批 · 17 项压测修复 · 退出码语义
 v1.21.x ●━ 08月   下载核心拆包 · 快捷点击 + 涟漪
 v1.20.0 ●━ 08月   虚拟鼠标三形态
 v1.19.x ●━ 08月   鼠标指针 · 全面审查 · ARTICLE.md
 v1.18.0 ●━ 08月   登录兜底 --login-rescue
 v1.17.0 ●━ 08月   伪装三档 --stealth
 v1.16.0 ●━ 08月   视口/新标签/图集四连修
 v1.15.0 ●━ 08月   DOM 精准模式 + 回读验证
 v1.14.x ●━ 08月   登录持久化 --profile · 安全修复批
 v1.13.x ●━ 08月   登录墙下载 --cookies · 兜底链 6 路 · 懒加载图集
 v1.12.4 ●━ 08月   视觉会话全面修复 + 12 项关键 bug
```

## 分月索引

### 2026 年 10 月

| 版本 | 日期 | 类型 | 一句话摘要 |
|---|---|---|---|
| v1.25.4 | 10-25 | 修复 | BUGS.md S6 同步：Python 子进程强制 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`（GBK 管道遇 `\xa0` 的 UnicodeEncodeError 修复）；`child_env()` 收口接入 runner / own_search download / search_and_cache 两处；9 项回归，套件 11 文件 |
| v1.25.3 | 10-24 | 修复 | 全量实测回归（搜索/下载/校验）：`verify_capture --assemble` set\|tuple TypeError 修复（该功能自首个提交起从未可用）；safe 模式拒绝归档改报真实原因；实跑覆盖文件/视频/音频/图集/小说/文件夹/zip/yt-dlp/校验/本地索引/视觉 |
| v1.25.2 | 10-15 | 安全·修复 | 子服务同步清单裁决：S1 envelope ok 绑定 returncode；S2 隐形字符净化移植并接线聚合源头；S3 验收落地；21 项新测试 |
| v1.25.1 | 10-04 | 安全·修复 | 外部审计 8 条裁决：4 确证修复（删除护栏 / URL 白名单双层设防 / 浏览器看门狗 / 死代码）、4 搁置留证 |

### 2026 年 9 月

| 版本 | 日期 | 类型 | 一句话摘要 |
|---|---|---|---|
| v1.25.0 | 09-28 | 性能·新能力 | 搜索全面压测：跳转壳解码、引擎 4 路并发 2.2x、浏览器死亡防护、31 引擎普查、局域网搜索 lan、--site 后缀匹配修复、引擎 HTML 夹具测试 |
| v1.24.1 | 09-24 | 修复·新能力 | 下载专项：挂死根治（单次 JS 求值 + 有界关闭）、番茄小说字体反爬还原、text 线登录态与目录完整性 |
| v1.24.0 | 09-14 | 新能力 | `--timeout N` 全局看门狗；番茄/起点/喜马拉雅压测；起点 VIP 如实报告（不绕过付费） |
| v1.23.3 | 09-14 | 修复 | 音频电路登录页抢位修复；网易云歌曲页挂死实锤记录；全平台矩阵压测收官 |
| v1.23.2 | 09-14 | 修复 | 挑链被栏目页抢位根治（裸首页/条目页判定）；`--query --auto` 全链路压测 |
| v1.23.1 | 09-14 | 修复 | 上线即自审：frames 顺序、--proxy 覆盖搜索步、吞错误文本、--playlist-max 静默无效；2 项判非 bug 留痕 |
| v1.23.0 | 09-14 | 新能力 | yt-dlp 三开关（合集/转音频/清晰度）、视觉三件套（对话框/上传/iframe）、代理全链穿透、断点续传、下载台账、首个正式测试目录 |

### 2026 年 8 月

| 版本 | 日期 | 类型 | 一句话摘要 |
|---|---|---|---|
| v1.22.1 | 08-25 | 修复 | 兜底链活化"先要后抓"六招阶梯；五平台压测 17 项修复；退出码语义（有正果=0） |
| v1.22.0 | 08-24 | 重构 | 全量模块化五批（auto_save/ + searchkit/ + runner 统一）；顺手修 7 bug + 压测 7 项 + 全模式审计 5 项 |
| v1.21.1 | 08-23 | 重构 | 下载核心拆包 auto_save/ 第一二批；AST 比对 + 162 项差分测试零逻辑变化 |
| v1.21.0 | 08-23 | 新能力 | 快捷点击（当前鼠标位置）+ 点击涟漪视觉反馈 |
| v1.20.0 | 08-22 | 新能力 | 虚拟鼠标三形态（手 / I 光标 / 箭头随悬停变形） |
| v1.19.1 | 08-22 | 维护 | 全面代码审查；作者信息写入；新增 ARTICLE.md 项目文章 |
| v1.19.0 | 08-22 | 新能力 | 视觉会话虚拟鼠标指针（白色大箭头实时跟随） |
| v1.18.0 | 08-22 | 新能力 | `--login-rescue` 登录兜底（接种本机浏览器登录态）；会话启动横幅自证 |
| v1.17.0 | 08-22 | 新能力 | `--stealth` 三档伪装（默认 full 深层指纹补丁） |
| v1.16.0 | 08-22 | 修复 | 视口 1440×900、新标签页自动跟踪、图集等图加载完、中文输入备忘 |
| v1.15.0 | 08-22 | 新能力 | 视觉会话 DOM 精准模式（text/selector 定位 + 回读验证） |
| v1.14.2 | 08-22 | 修复 | 验证码检测默认关闭（误报导致操作卡死） |
| v1.14.1 | 08-22 | 修复 | 验证码误报收紧 + `--captcha-mode allow` + `--linger` + `--idle-timeout` |
| v1.14.0 | 08-22 | 新能力·安全 | `--profile` 登录持久化；cookies-from-browser 全线生效；安全模式 2GB 漏洞等 6 项修复 |
| v1.13.1 | 08-22 | 修复 | SPA 懒加载图集迭代滚动收割；跨域 CDN 降级 |
| v1.13.0 | 08-22 | 新能力 | `--cookies` 登录墙下载；兜底链 5→6 路；抖音 note 自动转路 |
| v1.12.6 | 08-22 | 维护 | 默认分支修复（main 单分支）；吉祥物移 assets/ |
| v1.12.5 | 08-22 | 修复·维护 | eval 死循环看门狗；own_search 子进程超时；吉祥物入仓库 |
| v1.12.4 | 08-22 | 修复 | 视觉会话全面修复 + 12 项关键 bug（含未单独发版的 v1.12.2~3 内部迭代） |

## 详细记录

### v1.25.4（2026-10-25）

同步文档核对轮：v1.25.3 之后重读子服务 BUGS.md 的"主项目同步清单"，发现 **S6**（2026-10-16 新增）被漏掉，本轮补齐并留构造性证据。

- **S1/S2/S3**：v1.25.2 已同步（S2 净化位置有意放在引擎聚合源头而非逐出口，已在当版说明）。
- **S4/S5**：仅备忘，不改代码（结论维持）。
- **修复 S6（稳定性）：Python 子进程 GBK 管道崩溃**——`runner.py` 父进程侧写了 `encoding="utf-8"`，但**子进程**在中文 Windows 下仍按 GBK 写 stdout；`search.py`/`search_browser.py` 用 `ensure_ascii=False`，摘要含 `\xa0` 时子进程内抛 `UnicodeEncodeError` → 偶发 `exit 1`（"时好时坏"；本机终端已设 UTF-8 会掩盖）。
  - **证据**：grep 确认 `scripts/` 下无 `PYTHONIOENCODING`/`PYTHONUTF8`；强制 `PYTHONIOENCODING=gbk, PYTHONUTF8=0` 打印 `\xa0` 复现 `UnicodeEncodeError`（exit 1）；注入新环境后同一代码 exit 0 且 `\xa0` 原样输出。
  - **修法**：`searchkit/runner.py` 新增公共件 `child_env()`（复制 `os.environ` 后强制 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，覆盖继承值）。接入全部"解析 Python 子进程 JSON stdout"的位置：`runner.run_search_cli`（覆盖 smart/cross/own_search seed）、`own_search.cmd_download`、`search_and_cache` 两处（`run_search` 与 `cache_url`）。
  - **回归**：新增 `tests/test_sync_s6.py`——9 项断言（环境语义 / GBK 构造性复现 / child_env 修复 / 三个调用点确实传 env）。套件 **11 文件全绿**。

### v1.25.3（2026-10-24）

旧功能全量实测回归（起因："以前那些功能没有用，还会出问题"）。确认 2 个 bug 并修复（含可复现证据），其余全部通过，或失败原因经实测定性为环境问题。

- **修复（高·崩溃）：`verify_capture.py --assemble` 从未可用过**——`files = [... if p.suffix.lower() in VIDEO_EXTS | AUDIO_EXTS]`：`VIDEO_EXTS` 是 `set`、`AUDIO_EXTS` 是 `tuple`，`set | tuple` 在读任何文件之前就抛 `TypeError: unsupported operand type(s) for |: 'set' and 'tuple'`。证据链：①实跑 `--assemble downloads/_assemble_probe` 在 verify_capture.py:212 直接 traceback；②git 历史：该表达式从首个提交 `b8e7b4d`（v1.11.1）就在，常量类型从未变过——该功能在所有已发布版本中从未工作；③改为 `VIDEO_EXTS | set(AUDIO_EXTS)` 后，同一目录 4 段成功组装为 110.01s 成品（ffmpeg 真解码验证）。回归用例已加入 tests/test_audit_fixes.py。
- **修复（低·诊断）：safe 模式拒绝归档时谎报原因**——`--safe` 下归档（`.gz/.zip` 等）被落盘白名单（`SAFE_ALLOWED_EXTS` = 媒体 + txt/json）拒绝，但 `_files_route` 最终笼统报 `"file direct download failed (link dead / TLS-blocked / is a webpage)"`，把"白名单拒绝"误导成"死链"。现在 `_files_route` 先做白名单预检，直接返回 `safe mode 拒绝: 非白名单扩展名 .gz`；非 safe 下载行为不变。新增 2 项回归断言。
- **实测矩阵（到底测了什么）**：
  - 搜索：轻量版 `--json/--brief/--site/--category all/--engines/--ad-filter none/--precision 100/--no-resolve`；浏览器版 `--json/--brief/--site/--stealth off/--timeout`；smart_search（普通 + `--browser`）；cross_search（`--json`、`--mega --copies 1 --rounds 1`）；API 引擎无 Key（tavily/brave/searxng 均如实报 `set XXX_API_KEY`）。
  - 下载：文件直链（8.7MB tar.gz，2s，quality=full）、B站视频 chain（`quality=full`，15.6s）、yt-dlp `--quality 480p`（13.4MB）与 `--extract-audio mp3`（2.2MB）、音频直链、图集 harvest（本地夹具 6/6；250 张夹具精确封顶 200）、懒加载 `data-src` 图集 4/4、小说目录逐章合并 6/6（4717 字节 txt）、文件夹页批量（2/2）、`--zip` 打包（解压校验条目完整）、`--safe` 拦截行为、`--query --auto` 搜索后下载、截图、正文提取。
  - 校验：`--dir` 扫描、`--clean`、`--clean --keep-broken`（垃圾删、坏文件留）、`--recheck`（MD5 两次一致）、`--assemble`（修复后通过）。
  - own_search：`crawl` → `search`、`seed`、`lan`（私网护栏）、`stats`、`download` 透传；`file://` 被拒；`--hosts 8.8.8.8` 被拒。
  - 视觉：`test_vision_e2e.py` 12/12（elements/iframe 点击/对话框接受与取消/上传）+ 离线检查。
  - 负向：不存在的 cookies 文件（如实警告 + exit 1）、死代理（由看门狗兜底）、不存在的目录（exit 2）、把图片页当视频要（如实空手）。
- **环境问题、非产品 bug（已留证）**：w3.org SSL 握手超时（130s）与 zh.wikipedia 连接超时——网络墙；SoundHelix mp3 实测仅 ~11KB/s（curl 60s 只下 655KB），8.9MB 文件本来就下不完——服务器限速；用 Hermes venv 的 Python（无 playwright）跑测试会导致 vision/看门狗用例失败——项目 `.venv` 下 10 文件全绿。
- **套件**：tests/run_all.py **10 文件全绿**（审计文件现 25 项断言）。

### v1.25.2（2026-10-15）

子服务 BUGS.md 同步清单裁决轮（search-api-service/docs/BUGS.md 提出主项目同步项 5 条；逐项按"100% 确认才修"裁决——**2 条确认修复、3 条无修复指示仅备忘**；裁决记录写本仓库文档，BUGS.md 属子服务文档不动）：

- **指示判定**：同步清单 5 项中，仅 S1/S2 明确标注"主项目待同步"；S3 是 S2 的验收附属（非独立 bug，主项目不存在该正则）；S4 明确"不适用"；S5 是服务端部署备忘。第二轮台账的 I1-I4/P0/P2 全部为子服务自身事项，无一项断言主项目存在。
- **修复 S1（稳定性，子服务 P1 同源）**：主项目两处代码证据 100% 核实——`dispatch.py` `_format_plain` 直接下标 `data["results"]`（125 行）+ `runner.py` `envelope["ok"] = True` 无条件置真（154 行空 stdout 被 `or "{}"` 兜成 `{}`）。构造性复现：子进程 rc=1 但输出合法 JSON / rc=0 空 stdout → `data={}` 被当成功下发 → 消费方 KeyError。修复：runner `ok` 绑定 `returncode == 0`（rc≠0 补 `subprocess exit N`）；dispatch 改 `.get("results") or []`。兼容面核清：4 个消费方中仅 smart_search 行为变化（改为走设计好的错误占位分支），routing/cross_search/own_search 均已 `.get` 防护零影响。
- **修复 S2（安全，子服务 I2 同类）**：主项目 scripts/ 隐形字符剥离 grep 17 种模式 **0 命中（防护为零）**——零宽/双向控制符/Unicode Tag 块（ASCII Smuggling 载体）可从网页进结果再进 AI prompt。移植子服务 sanitize.py（≥2026-10-04 版）为 `searchkit/sanitize.py`，架构差异：子服务在 server 出口净化（引擎层零依赖），主项目无 server、改在**引擎聚合源头**净化（dispatch/browser 返回前 + own_search 入库前）——下游 5 份 `_format_plain` 与 JSON 全部自动干净，不再逐出口接线（副本漂移温床）。
- **S3 验收落地**：BUGS.md 指定用例 `sanitize_output('abc123 XYZ 中文 456 https://a.com/x?y=1 2026年')` 原样保留（P0 教训：转义错误曾吞全部 ASCII）已入回归；5 位以上码位一律 `\UXXXXXXXX`。
- **S4 复核意见（记录，不修）**：BUGS.md"主项目无打开任意 URL 功能"表述不准——own_search 的 add/crawl/download 三子命令均收用户 `--url`；但输入方=本机操作者本人而非不可信外部输入，SSRF 威胁模型不成立，"不适用"结论维持。若未来主项目做服务端化，须直接采用子服务钉定实现（BUGS.md S4 提醒有效）。
- 新增 tests/test_sync_s1s2.py（21 项：构造性 KeyError 消除/ok 绑定/ASCII 验收/Tag 块剥离/VS16 保留/字段净化/集成冒烟）；tests/run_all.py **10 文件全绿**。
- 延续决策：**不推送 GitHub**，累积统一发版。

### v1.25.1（2026-10-04）

外部审计质疑裁决轮（DeepSeek 4.1 标记 8 条"查看质疑"，逐条取证——4 条确证修复、4 条非 bug 搁置并留证据；套件扩至 9 文件）：

- **修复①（高·破坏性）：`verify_capture.py --clean/--assemble` 目录边界**——此前 `--dir` 接受任意目录，而 junk 判定含"图片<150KB"，指到相册等目录会不可逆删除真实小图。现在破坏性操作要求目标必须在本项目 `downloads/` 树内（`_within_downloads`），越界 exit 2 明确拒绝。
- **修复②（高·安全）：`own_search` URL scheme 白名单**——`crawl --url file:///C:/windows/win.ini` 可把本地文件读进索引（stdlib urlopen 原生支持 file://）。新增 `_require_http_url` **双层设防**：urllib 层 + Playwright 兜底层（crawl 的 `except` 会吞掉第一层拒绝转浏览器重试，`goto file://` 照样读本地文件——双层缺一不可，测试已证）；`lan --hosts` 同样此前绕过 RFC1918 私网护栏（`--hosts 8.8.8.8` 可扫公网），现在显式主机必须逐一为私网 IP，实测拒绝 8.8.8.8、放行 192.168.31.1。
- **修复③（接口缺口）：`search_browser.py` 补 `--timeout N`**——全局看门狗此前只在 auto_save_browser（v1.24.0），"AI 调用统一带 --timeout 600"的建议在浏览器搜索 CLI 上根本不可用。同语义（默认 0=关、`[timeout]` 标记、exit 1）；实现上收为 `searchkit.runner.start_global_timeout` 双门面共享（顺带消灭审计⑦点名的一份重复副本）。
- **修复⑧（死代码）：删除 `verify_capture._md5_file`**（零调用方）；审计对 `check_local_index` 的死代码指控在本仓库被驳回——cross_search 有活调用。
- **非 bug 搁置（留证据）**：④ GBK stderr 二次崩溃——实验驳回（Python 3.14 stderr 实测 UTF-8 输出 + backslashreplace 语义，中文正常写出不抛异常）；⑤ cross_search 低可信标注是如实报告非缺陷；⑥ 相关度/词表覆盖局限（已文档化，非逻辑错误）；⑦ `_format_plain`×5 / STEALTH_JS×3 / USER_AGENTS×2 重复属维护债，本轮有意延后（观察项：QA-1 式副本漂移已发生过一次）。
- 新增 tests/test_audit_fixes.py（22 项：边界/scheme/私网/看门狗/死代码）；tests/run_all.py **9 文件全绿**；正常路径实弹验证（downloads 内 --clean 正常、https 抓取正常）。
- 按维护者决策**暂不推送 GitHub**，累积多个修复后统一发版。

### v1.25.0（2026-09-28）

搜索功能全面压测与优化（压测资产与数据：downloads/_search_stress/）：

- **跳转壳解码（新能力，修复重大正确性 bug）**：压测实锤百度/360 结果全是加密跳转壳，且旧去重把壳 URL 的 query 参数全丢——key 坍缩成同一个，**百度 8 条结果去重后只剩 1 条（7 条被误杀）**。修复：①壳 URL 保留 query 参与去重 key；②新增 `searchkit/resolve.py` 并发解码壳链接（302 跟随 / 壳页 JS 提取，实测 11/11 还原为 docs.python.org 等真实地址，同源落点防验证页污染，失败保留原壳），`--no-resolve` 可关。
- **轻量引擎并发（2.2x 提速）**：旧版 17 引擎串行 45-54s → 并发（4 路）后 **~21s**；`smart_search`/`cross_search`/`own_search` 经 runner 统一受益。
- **浏览器死亡防护（问题 #2 处置）**：压测 F2 实锤比记载更严重——playwright driver 突死后 `page.goto` **永久挂起**且 python 空转烧 CPU（565s 实测），进程内调用无任何超时兜底。处置：①下载电路搜索步从进程内直调改子进程隔离（超时有界）；②浏览器版 run_search 每引擎前查 `is_connected()`，断开如实标记快速失败，不再逐引擎白等。
- **JS 失败场景定论**（压测 C 矩阵）：系统不会挂死（全部有界）；bing/baidu 是 SSR（JS 禁用仍有结果），so360 依赖 JS；架构兜底 = 轻量版不依赖 JS。
- **引擎健康度**：搜狗/360 匿名请求返回验证码页实锤，HTML 引擎命中特征如实报 `captcha suspected` 而非笼统 "no results"。
- **全引擎健康度普查（31 引擎逐个实测）**：轻量 ok=8/flaky=2、浏览器 ok=2/flaky=1，其余为网络墙与反爬（明细见 downloads/_search_stress/census_*.json）。**修复两个从上线起就抓空的浏览器引擎**——arxiv（结果标题 `<p class="title">` 是纯文本无 `<a>`，旧选择器永远取不到链接）、东方财富（真实容器 `div.news_item` 下划线，旧选择器写成连字符 `.news-item`）；`_extract_from_items` 新增可选 `url_sel` 支持标题/链接分离结构。API 引擎（tavily/brave/searxng）无 Key 时如实报 `set XXX_API_KEY` 而非假装 "no results"。
- **引擎 HTML 夹具测试（新，问题清单 #4 落地第一块砖）**：tests/test_engine_fixtures.py + tests/fixtures/engine_html/（bing/baidu 真实录制响应 + 搜狗/360/DDG 最小结构夹具），断言解析数量与字段齐全——站点改版后跑一次即知哪个选择器该修；套件增至 7 文件。
- **局域网搜索（新能力，own_search.py lan）**：发现局域网设备/HTTP 服务/NAS/SMB 共享并入本地索引——只读探测（TCP 端口探测 + HTTP 标题/Server 识别 + `net view` 共享枚举），硬性限私网段（RFC1918）防误扫公网，纯 stdlib 零依赖。实测 254 主机 ×12 端口 15s，正确识别小米路由器；入索引后 `search --query 路由器` 即命中。
- **搜索单元审查轮（严格证据流程）**：4 个疑点逐一实验定性——①墙外引擎 8s 超时实测拖尾 16s 为 stdlib"每操作超时"语义（DNS 0.1s/connect 8s/数据层墙各证，非代码 bug）；②**`--site` 子串匹配 bug 实锤修复**（`--site python.org` 曾放行 `notpython.org.evil.com`，改域后缀匹配，端到端复验零违规 host）；③**news 词表"最新/今天"误分类修复**（"今天天气怎么样"曾被判 news，移除超宽泛词后回落 general 且强新闻词不受影响）；④dedupe 换皮标题互杀为既定防垃圾设计（已固化回归防漂移）。新增 tests/test_search_units.py（5 项），套件增至 8 文件全绿。
- **实测数据**：Slow3G/CPU 6x 节流对结果无实质影响（SSR 引擎扛住）；离线 4.1s 快速失败；tests/run_all.py 8 文件全绿。

### v1.24.1（2026-09-24）

下载功能专项修复（压测挂死根治 + 小说完整性）：

- **挂死根治（问题清单 #1 销账）**：真凶两层——①`_extract_body_text` 逐个试 11 个选择器，元素不存在时 Playwright 隐式等 30s/个，番茄阅读页全 miss 单章空耗 ~330s（351 章永远跑不完）；②`browser.close()` 对长连页面（WebSocket/SSE）无限阻塞。修复：正文提取改单次 JS 求值 + `_eval_bounded`（driver 强制超时）封顶全部无界 evaluate；`_close_bounded` 主线程 page→context→browser 三级顺序关闭（实测 0.7s 全清）；新增 `[stage]` 分段计时日志——挂点从此一条日志可见。
- **小说字体反爬还原（新能力）**：番茄正文约一半字符是私有区码位（视觉正常、提取缺字）。新增 `auto_save/novel_font.py`：woff2 字体解析 + 字形位图比对建映射（缓存 `index/novel_font_map_*.json`），实测 338/362 码位还原、正文通顺；依赖 fonttools/brotli/pillow/numpy 入 requirements.txt，缺失时优雅降级原样保存。
- **text 线登录态 + 目录完整性**：补 `--cookies-from-browser/--profile/cookie_file`（本人账号权限下有权限内容）；目录滚动展开拿全章节、`--max-chapters 0` 不限章数；跳过章节带原因分类（vip/lock 信号检测），`skipped_detail/skip_reasons` 如实进 JSON。**不做付费/VIP 绕过**的立场不变。
- **实测**：番茄全书 351/351 章 0 跳 497KB（旧代码 300s 走不完 10 章）；抖音视频 quality=full（16.3s ffmpeg 实测）；tests/run_all.py 6 文件全绿。

### v1.24.0（2026-09-14）

新增源类型压测（番茄小说/起点/喜马拉雅）+ AI Agent 保险丝：

- **`--timeout N` 全局看门狗（新能力）**：chain 各步单独有超时但**总和无界**——网易云歌曲页等极端页面会无限挂死（v1.23.3 实锤 15 分钟零输出）。现在任意命令加 `--timeout 600`，整条命令超过 N 秒强制退出（stderr 打 `[timeout]` 标记 + exit 1），AI Agent 调用从此有"必然结束"保证。子进程截杀测试入套件（tests/test_timeout_watchdog.py，套件增至 6 文件全绿）。
- **番茄小说（网页版免费书）：第二例挂死实锤**——书页静态 HTML 352 个"第X章"链接全命中（目录解析没问题），但 text 路线打开后与网易云同签名挂死（低 CPU+零输出）；**`--timeout 90` 实弹验证：90 秒强制收口 exit 1 + [timeout] 标记**——新看门狗恰好治住这两例。
- **起点 VIP 行为验证（如实）**：诡秘之主 1401 章，text 路线只抓到 **3 章**（免费试读），合并 29KB txt 并如实标注 3/1401——工具只拿网页真实可见的内容，**不做 VIP/付费绕过**（规避访问控制不做）；手机 App 免费的内容请在 App 内看，工具侧无解也不该有解。
- **喜马拉雅音频**：音频电路实测（结果见压测留证）。

### v1.23.3（2026-09-14）

全平台矩阵压测收官（B站/快手/抖音/微博/网易云/小红书/公众号/小说站/GitHub/w3.org，覆盖视频/图文/文字/音乐/文件五类），修 1 项、实锤 1 项未根治、如实记录若干局限：

- **修：音频电路登录页抢位**——搜"网易云音乐 周杰伦 晴天"，音频轮 host 匹配就把 `music.163.com/login` 当"音频目标"（v1.23.2 只修了视频轮的同类病）。`_looks_like_item_page` 补音频 token（song/songDetail/play_detail/sound/album/playlist/program）+ query `id=\d` 信号（music.163.com/song?id= 式条目页）+ 登录/注册页一票否决；text 轮同跳登录页；`test_routing_offline.py` 补 8 项断言（套件 5 文件全绿）。修复后同查询如实空手（搜索结果里本就没有歌曲页 URL）而非下载登录页。
- **实锤未根治：网易云歌曲页直链（music.163.com/song?id=）采集卡死**——harvest/chain 超过 15 分钟 stderr 零输出、进程低 CPU 纯等待（iframe 渲染页疑似某步无界等待）。已写入 SKILL.md 错误自愈表（Ctrl+C 终止 + 换 `--method ytdlp`）；根治方向：全局 `--timeout` 看门狗（chain 各步单独有界但总和无界）。
- **压测矩阵（全部留证 downloads/_stress_v123/）**：快手视频 full（27MB mp4，搜狗跳转→yt-dlp）；抖音视频 full（1.15MB）；微博 full（43 个文件，先要后抓整取 mp4）；B站基线 full（28MB）；图文电路兜百度图片页收 200 张 21.5MB（partial，小红书原图需登录=文档载明局限）；w3.org PDF full（UA 阶梯治 JA3 拦截，v1.22.1 修复实战有效）；西游记章节合并 5/5 章 106KB 单文件（chapters-merged）；公众号文章正文提取 16KB（partial）。
- **如实记录（非工具 bug）**：arxiv.org 本网络全层不可达（urllib/yt-dlp 连接被重置）；yt-dlp.zip 资产不存在（测试 URL 选错，工具全程如实 404 且 junk→exit 1 语义正确）；海外平台（YouTube/X）未测（网络环境）。

### v1.23.2（2026-09-14）

压测收官版：`--query --auto` 全链路压测揪出一个 v1.22.0 时代的**挑链缺陷**并根治，选脚本表补齐新开关。

- **修：挑链被站点栏目页抢位**——搜"B站 猫 视频"，平台轮只看 host 匹配就选中 `t.bilibili.com/index.html`、`bilibili.com/read/home` 这类栏目/伪首页，chain 全链在错误页面上收割头像缩略图（junk）。两级修复（平台无关）：`_is_bare_homepage` 补首页文件名判定（index.html/htm、default、home）；新增 `_looks_like_item_page` 条目页判定（路径含 /video/、BV号、watch 等关键词，或末段为 ID 形态——youtu.be 短 ID 与纯数字 ID 都覆盖），两轮挑选全部加门。**实测修通**：同查询现在落到搜狗跳转链 → yt-dlp 跟出真视频 BV1GVMszFETr → 2.7MB mp4，quality=full，exit 0。
- **tests**：新增 `test_routing_offline.py`（裸首页/条目页判定 18 项断言），套件增至 5 文件。
- 压测矩阵（v1.23.1 代码 + 本修复）：全套件 5 文件、B站 `--quality 480p`（full）、`--extract-audio mp3`（full）、死端口代理快速失败（`WinError 10061` 证明 proxy 贯通 yt-dlp）、`.manifest.jsonl` 台账落盘、`--query --auto` 全链路（修复前 junk → 修复后 full）。

### v1.23.1（2026-09-14）

v1.23.0 上线即自审（每条疑点走"判定→理由→反问→确认"四步），修 4 项、判非 bug 2 项留痕：

- **修：frames 顺序假设**——`page.frames[1:]` 隐含"索引 0=主 frame"，Playwright 只契约 `main_frame` 属性不保证列表顺序；改为按身份过滤（`fr is not page.main_frame`，3 处）。
- **修：`--proxy` 未覆盖 `--query` 自动搜索步骤**（help 却写"覆盖全部出口"）——反问后发现 `run_search` 本来就有 `proxy` 参数，线是现成的：`_search_first_media_url` 6 处调用全部接上 `proxy=get_proxy()`，help 无需降级。
- **修：`_vision_find_el` 吞掉 Playwright 选择器解析错误文本**（诊断信息退化）——异常文本保留进 note。
- **修：`--playlist-max` 不带 `--playlist` 时静默无效**——按项目 v1.12.1 问题清单第 3 条（"--safe 被接受但从未生效"定级"高"）同类判例，加一次性 stderr 告警。
- **判非 bug（留痕）**：①断点续传无 ETag/If-Range 内容校验——旧行为严格更差、完整修复需持久化校验头，媒体另有 ffmpeg 解码兜底，记入 docstring 已知局限；②成品与 `.part` 并存——原子 `replace` + already-cached 短路使正常流程不可达。
- **回归**：`tests/run_all.py` 4 文件全绿；`--playlist-max` 告警与下载行为实测（count=1）；`routing.get_proxy` 接线单查通过。

### v1.23.0（2026-09-14）

能力补强版：yt-dlp 三开关 + 视觉会话三件套 + 下载链代理/续传/台账 + 项目史上第一个正式测试目录。全部默认行为零变化（新能力全部 opt-in）。

- **yt-dlp 三开关**：`--playlist` / `--playlist-max N`（合集/播放列表整单，此前写死 noplaylist 只能下单条——单视频语义保留为默认）；`--extract-audio --audio-format mp3|m4a|...`（只拉音轨省一半流量，ffmpeg 转码）；`--quality best|1080p|720p|480p|360p`（清晰度封顶）。实测踩坑两连：format 回退链末端必须兜 `bestvideo+bestaudio`（B站等纯 DASH 站没有渐进单文件，`best` 永远落空）；竖屏视频"高度"是长边（480P 档=480x852），补 `width<=N` 招才命中同名清晰度档。
- **视觉会话三件套**：① **对话框**——此前 Playwright 默认静默取消 alert/confirm/prompt，AI 不知道弹过框、confirm 流程永远走不通；现在每次上报 `dialog_events`（默认仍取消，零破坏），`{"action":"dialog","accept":true}` 设一次性接受策略（prompt 可带回复文本）。② **文件上传**——`upload` 指令三招：显式 selector 直设 > `click_selector` 拦截系统选框（expect_file_chooser，主流上传模式）> 全 frame 自动找 input[type=file]。③ **iframe**——elements 跨 frame 标注（子 frame 坐标加 iframe 包围盒偏移换算到主视口，`frame` 字段标来源）；selector/text 主 frame 找不到自动逐 frame 定位（child frame 的 bounding_box 官方语义就是主视口基准，坐标点击无需换算）。
- **下载链三补**：① `--proxy` 全链穿透（Chromium launch 持久化/一次性两路、urllib 直连三处、yt-dlp、分享短链解析——此前下载核心完全没有代理能力）；② **断点续传**——文件下载改写 `.part` + `Range: bytes=N-`，中断后续传（2GB 下到 90% 断掉不再从头来），完整 EOF 才转正（修复"半截文件顶着成品名留盘"），服务器不支持 Range 或成品已存在各有如实处置；③ **下载台账**——`.manifest.jsonl` 逐行记录 url→文件/大小/md5（<8MB 才算），跨运行可追溯。
- **tests/（项目首个正式测试目录）**：`python tests/run_all.py` 一键跑，纯 stdlib 零新依赖，3 文件 28 项——yt-dlp 开关字典形态、断点续传/代理生效（本地 HTTP 服务器自建 Range 支持 + 死端口代理必炸法）、台账字段、vision 指令注册。
- **实测验证**：B站 `--quality 480p`（13.4MB 成品）/ `--extract-audio mp3`（2.2MB）端到端；`--playlist` 单视频回归仍只下 1 条；vision 三件套本地 HTML 测试页 e2e 12/12（iframe 元素标注/iframe 内点击/confirm 上报与接受/dismiss 语义断言/upload 双招/文件名回读）。

### v1.22.1（2026-08-25）

兜底链活化（"先要后抓"）+ 五平台压测修复 17 项。用法零变化——纯修 bug + 一次范式升级。

- **媒体获取新范式——"先要后抓"六招阶梯（反馈驱动，成功即停，总尝试 ≤6）**：① tab（页签原生 fetch，cookie/referer 齐全）→ ② desktop（HTTP 桌面 UA + referer）→ ③ mobile（移动 UA）→ ④ bare（不带 referer）→ ⑤ refresh（刷新页面换新鲜签名 URL）→ ⑥ 兜底轮。反馈驱动：403 → 换人设；200 截断 → 跳 refresh 换票；416 → 换纯 GET。
- **抖音（5 项）**：合并引擎按 Content-Range 文件偏移排序（乱序到达必拼坏文件的根源）；fMP4 init 段（moov 头）并入同组；字节级重复分段去重（登录墙 11×204801B 重传块不再拼坏文件）；推广物料域一票否决（douyinstatic/bytednsdoc——11MB 的 PC 客户端安装推广视频！）；JSON 转义 URL（`\/`、`\u002F`）还原 + 伪扩展名（.image/.awebp）识别，图集不再漏图。
- **快手（4 项）**：单响应完整流直接转正（旧"至少 2 段才拼"规则在杀整条视频）；206 部分块须覆盖到文件尾才转正；body 不可读（缓存逐出）记入整取账本不再静默丢流；滑图帖转义 URL 预还原。
- **B站（4 项）**：CDN 镜像去重（路径 + basename 双尺，mcdn 路由前缀归一——同一文件曾下 2-3 份）；内容 hash 去重（逐字节相同的第二份丢弃）；yt-dlp 产物质量门修正（`url or path` 短路写法把 21.5MB 成品误判 junk → 全链重抓 188MB）；站点物料域拦截（13MB 壁纸包）。
- **网易云/小红书（4 项）**：yt-dlp 进度条不再污染 `--json` stdout（noprogress）；iframe 渲染页（网易云 g_iframe）正文/媒体收割；跳首页识别为降级（不跟进）；小红书登录墙装饰图域拦截（fe-platform.xhscdn）。
- **通用**：**退出码语义——有正果 = 0，失败/全 junk = 1**（原恒 return 0，宿主无法降级重试）；files/direct/text 专用线质量门补齐（60MB 完整下载曾报 quality: null）；Chromium 通道择优 + 禁视频硬解 + SwiftShader 软渲染（根治 AI 宿主沙箱误杀）；JSON 序列化 default=str 兜底（set 类型曾崩溃）；install_dependencies.py pip 检测修复。
- **压测矩阵（全通过）**：网易云 ytdlp（full）、B站 browser（full，流+封面，去重生效）、抖音 chain（full，推广物料全拦，exit 0）、60MB 文件 files（字节精确匹配）、小文件 exe files（full）。

### v1.22.0（2026-08-24）

全量模块化重构（五批）+ 五平台压力测试修复：

- **批 A/B（下载侧）**：视觉会话协议层拆出 `auto_save/vision.py` + `shots.py`；下载路线拆出 `auto_save/routes.py`（browser/cache/harvest/files/text）；`auto_save_browser.py` 从 4700+ 行瘦身至 1132 行
- **批 C/D（搜索侧）**：`search.py`（961 行）拆出 `searchkit/` 包——http/normalize/adfilter/dispatch + engines/ 五类 20 引擎；`search_browser.py`（820 行）并入 searchkit 共用归一/去重/广告过滤/排序/**双引擎表消灭**（轻量版与浏览器版统一用一套 CATEGORY_ENGINES 分类表，调度时按模式可用性过滤）
- **批 E（调度侧）**：smart/cross/own 三调度器重复的"选脚本→拼参数→subprocess→解析"收敛为 `searchkit/runner.py` 统一执行件，超时按引擎数自适应（all 分类 17 引擎不再被按 9 引擎估的超时误杀）
- **顺手修复 7 个真实 bug**：arxiv 引擎 `ns=` 参数名错（学术引擎一直坏）、engines 缺 import×3、`--brief` 纯文本输出崩溃、中文 precision 排序失效（`\w+` 分词把中文整句黏成一个词，改二元组分词）
- **压力测试修复 7 项**（抖音/小红书/快手/小黑盒/汽水音乐实测 + 用户反馈两轮）：①搜索捡到平台裸首页当视频链接——跳过+新增 8 平台搜索页兜底 `_platform_search_url`；②引擎索引的平台搜索页只带残缺关键词——自动升级为全关键词搜索页；③chain 模式 yt-dlp 跑 3 次——加 `ytdlp_fallback` 开关链内去重；④harvest 把 svg 精灵/登录横幅/广告图/引导图当内容存盘——补垃圾过滤规则；⑤小红书搜索页要图被"视频站一票否决"导去视频链——搜索页显式 `--media-type` 优先；⑥日志 `时长 Nones` 格式错；⑦**ytdlp 文件名超长 Windows 写入失败**（汽水音乐 URL 长参数塞进 title/id，路径超 260 上限三路全挂）——outtmpl 截断 + `trim_file_name` 硬限，实测 598→97 字符写盘成功。第二轮（/note/ 链路）：⑧note 转路不可诊断+音乐帖收获丢失——harvest 空转/只收图留痕、attempts 记 `harvest(note)`、要音视频而收获没有则落 chain 抓流并合并收获；⑨乱码修复回滚（UTF-8 强设在 GBK 终端反致乱码，保持 Python 默认）；⑩exit 1 定性为环境层误伤（Chromium 写 exe 目录 debug.log 被沙箱/杀软拦，代码层 main 实测 return 0）
- **全模式审计修复 5 项**（6 入口全部开关盘点 + 管线核查）：①searchkit/browser 分层倒挂（搜索包经下载门面 import 基建→直接用 `auto_save.browser_base`）；②伴随的基建副本漂移（兜底 `_browser_launch_args` 复制品漏了当天的 `--log-file` 修复→import 源归一消灭）；③smart_search 补 `--ad-filter/--precision/--category` 全链透传、own_search seed 补 `--ad-filter`（防垃圾 URL 入索引）、runner 补 precision/site 透传；④`--screenshot --profile` 截图不带登录态（登录墙页截出空壳）→ profile_dir 透传
- **结构优化三批**（由易到难，零逻辑改动）：批 1 意图路由 9 函数下沉 `auto_save/routing.py`（门面 1132→824 行）；批 2 `searchkit/browser.py` 510→257 行，14 个浏览器引擎拆 `engines_browser/` 包（dom/web/dev/academic/alt 五类）；批 3 routes.py 四份浏览器启动样板（files/text/harvest/browser 各一份近 40 行副本）归一为 `browser_base._open_page()` 单实现，差异全部入参（持久化目录/下载信任/自签容忍/随机视口/登录态注入），持久化回退与失败自清理语义保持，伪造 playwright 对象 46 项逐键等价验证全过
- **兼容性契约**：三大门面（auto_save_browser/search/search_browser）仍是唯一命令行入口，全部旧名 re-import 保持可用，外部 import 路径零变化；每批经 AST 逐节点比对 + 运行时验收

### v1.21.1（2026-08-23）

下载核心模块化重构（纯结构优化，零功能变化）：

- **`auto_save_browser.py` 按安全等级分批拆出 `scripts/auto_save/` 包**：第 1 批 constants（常量）/ ffmpeg（探测验证）/ cookies（登录态），第 2 批 urlrules（URL/媒体/安全判定纯函数）——主文件从 4393 行瘦身到约 4140 行，仍保留全部九大路线
- **兼容性契约**：`auto_save_browser.py` 仍是唯一命令行入口与唯一被外部 import 的模块，全部旧名经 re-import 保持可用，外部调用路径零变化
- **纯搬迁验证**：AST 逐节点比对 git HEAD 原版确认 29 个拆出定义零逻辑改动；差分测试 162 项同输入新旧行为全等；`__all__` 补齐 51 个名字的包级导出；text/direct/files 三路线真浏览器端到端与原版逐字节一致
- 顺手修复：第 1 批遗留的 `List[Path]` 类型注解偏差（恢复与原版逐字一致）

### v1.21.0（2026-08-23）

快捷点击 + 点击涟漪（开学前收尾版）：

- **新增快捷点击**：`{"action":"click"}` 不带任何参数 = 直接点**当前鼠标位置**——先 `move` 瞄准再发 `click`，不用重复报坐标；`{"action":"click","button":"right"}` = 在当前位置右键。原坐标模式（x/y）与 DOM 精准模式（selector/text）完全保留，三套并存 AI 按场景自选
- **新增点击涟漪视觉反馈**：三种模式的每次点击都会在点击位置画一圈**扩散涟漪**（白圈黑边，约 0.5s 淡出）——下一张截图直接看到"刚才点在哪"，确认点击生效（截图带 150ms 停留确保拍到）
- 全面检查：9 脚本编译全过、AST 参数链检查通过、快捷/坐标/DOM 三模式及涟漪实测通过
- 后续一两周内**可能**有零星更新（维护者临近开学，不定期）

### v1.20.0（2026-08-22）

虚拟鼠标三形态（用户反馈：固定箭头不像真鼠标）：

- **指针会变形了，跟真鼠标一样**：悬停链接/按钮 → **手指**；悬停输入框 → **I 型文本光标**；其他位置 → **箭头**。每步检测鼠标下元素的 CSS cursor 自动切换（pointer/grab→手、text 或 input/textarea/contenteditable→I 光标、其余→箭头）
- AI 看截图不只知"鼠标在哪"，还知"悬停的东西**能不能点（手指）/能不能输入（I 光标）**"
- 三种形态均白底黑描边 + 热点对齐（箭头/手指尖端、I 光标横杆中心 = 真实鼠标坐标）
- 实测：example.com 链接上=HAND、空白=ARROW、百度输入框=TEXT，三态全过

### v1.19.1（2026-08-22）

维护版（全面审查 + 作者信息 + 项目文章）：

- **全面代码审查**：9 脚本编译全过、AST 参数链检查全过（无未知参数/无编辑残留）、8 处伪装接入点核对、5 条路线运行时冒烟全绿；历史遗留低危项（`\\n` 日志笔误/视觉会话英文提示/concat 失败清理）确认已全部修复，无新 bug
- **作者信息**：抖音号 94636651553 写入 SKILL.md / package.json / 双语 README
- **新增 [ARTICLE.md](ARTICLE.md)**：项目文章——三条铁律（降级链/不信任标称数据/绝不造假）、视觉模式踩坑记、登录墙的不打智慧
- 本版后项目暂停更新一两周（维护者休整）

### v1.19.0（2026-08-22）

视觉会话虚拟鼠标指针：

- **新增虚拟鼠标指针（视觉会话自带，无需参数）**：无头截图不渲染系统光标，AI 此前只能靠 `screen.mouse` 数字坐标猜"鼠标在哪"。现在会话自动注入一个**放大的白色箭头指针（34px，黑描边，任何底色都看得清）**，实时跟随鼠标（CDP 驱动的 move/click/drag 都会触发），截图里直接可见——白色大箭头 = 鼠标当前位置，与 screen.mouse 坐标一致
- 实现：注入式覆盖层（pointer-events:none 不挡点击、挂 documentElement 页面清 body 不丢、DOMContentLoaded 前自动等待）；仅视觉会话启用（整页截图的 fixed 定位会错位，独立截图线不注）
- 实测：move(400,300) → 指针 translate(398,298) 与 screen.mouse(400,300) 同步，截图正常

### v1.18.0（2026-08-22）

登录兜底 + 会话日志自证（实测：抖音扫码手机确认成功但网页仍拒登录）：

- **新增 `--login-rescue` 登录兜底**：强风控站（抖音等）对自动化环境扫码会"手机确认了但服务端拒发 session"（检测 CDP 痕迹，指纹伪装救不了）。正解：人肉在自己平时的浏览器登录目标站，工具加 `--login-rescue` 开会——自动遍历本机 chrome→edge→firefox，谁有目标域登录 cookie 就接种进当前会话并刷新；结果在 stderr 与首屏 `login_rescue` 字段如实报告；配 `--profile` 接种后的新 session 会持久化
- **`--profile --headed` 人肉登录场景自动关本地调试口**：eval 看门狗的 DevTools 调试口是字节级风控的检测面之一，登录窗口期自动收敛（看门狗随之退化为不启用，可接受）
- **视觉会话启动横幅**：stderr 首行输出 `版本 | stealth | profile | headed | idle看门狗 | captcha | 调试口 | login_rescue`——日志自证身份，杜绝"老副本跑出诡异行为（如 --headed 仍 120s 断线）查半天"
- 澄清"120s 未检测登录"日志：那是空闲看门狗（数的是 AI 发指令的间隔，与页面登录无关）；--headed 下新副本自动放宽到 600s，仍打 120s 的一定是老副本
- 实测：横幅/兜底如实报告/JSON 字段透出全通过

### v1.17.0（2026-08-22）

浏览器伪装三档可选，默认全套：

- **新增 `--stealth full|basic|off`（默认 full 全套）**：接入 playwright-stealth 深层指纹补丁（plugins/WebGL/UA-Data/sec-ch-ua/hairline 等 20+ 项），配合原有 webdriver 抹除 + UA/视口/locale 伪装——无头浏览器指纹显著接近真人浏览器；`basic` 保留原半套；`off` 裸奔对照
- **全线接入**：搜索浏览器（search_browser）+ 全部下载/视觉路线（browser/cache/harvest/files/text/vision/screenshot）统一走 `_apply_stealth`；库未安装自动降级 basic 并 stderr 告知，不硬崩
- 新依赖 `playwright-stealth` 已进 requirements.txt 与一键安装脚本
- **实测验证**：off 档 plugins=0（裸奔）/ basic 档 plugins=5（假插件）/ full 档 plugins=3 + brands 无 HeadlessChrome（真实指纹）；必应搜索回归正常
- **已知限制（如实声明）**：搜狗 antispider 属 IP/行为层风控，指纹伪装无法通过——换引擎或 `--profile` 养登录态（已写进 SKILL.md 错误自愈表）

### v1.16.0（2026-08-22）

实测反馈四连修（视口裁切/新标签页/图集忽多忽少/中文输入备忘）：

- **默认视口 800×800 → 1440×900**：实测 800 高度裁掉页面底部（百度"百度一下"按钮被裁半）——完整性优先，清晰度由官方 384 token 封顶兜底；极致清晰可 `--viewport 800x800` 指定
- **新标签页自动跟踪**：点"相关搜索/热搜"等 target=_blank 链接开了新标签时，视觉会话**自动切到新标签**（note 告知），截图/操作都落在新标签；新增 `tabs`（标签清单）/ `switch_tab`（手动切换）指令。必真实测：点必应结果→自动切换→后续指令在新标签执行
- **图集收割加"等图加载完"**：每轮收割前轮询 `img.complete`（最多 3s）——治小黑盒图集"忽多忽少"（7 张/2 张）：此前部分图还在 in-flight 就收割，漏收或误记失败
- **中文输入备忘**：原坐标 type 对中文可能输出 `???`——用 v1.15.0 精准输入 `{"action":"type","selector":"...","text":"中文"}`（键盘通道失败自动 JS 设值兜底，中文可靠）；纯 HTTP 搜中文走 `search.py`
- 登录墙（豆包/抖音/DeepSeek 网页）为站点强制身份验证，工具不绕：`--profile` 持久登录（v1.14.0）是正解

### v1.15.0（2026-08-22）

视觉会话 DOM 精准化——点击/移动/滚动/输入不再靠猜像素：

- **新增 DOM 精准模式（默认推荐）**：`click`/`move`/`scroll` 支持 `"text"`（按页面文字找元素）或 `"selector"`（CSS 选择器）定位，`type` 支持 `"selector"` 定位输入框。执行链：定位元素 → 等可见(3s) → 取包围盒中心执行（scroll=滚进视口）→ 验证 → 失败自动重试（最多 3 次）
- **精准输入自带回读验证**：输完回读输入框内容，不含所输文字就 JS 设值兜底（input/textarea 设 value+补发 input/change 事件；富文本编辑器 execCommand insertText 触发真实 input）——React 受控组件/ProseMirror 认事件不认按键，专治"输入后文字消失"
- **`"expect_gone": true` 可选点击验证**：要求点击后元素消失（关弹窗/关下拉类场景）
- **原坐标模式完全保留**（只给 x/y 走老路径，向后兼容，AI 按场景自选）；实测回归：按文字点击"百度一下"、精准输入+回读验证、元素滚动、坐标模式全过
- 隐藏元素如实报错不硬点（等可见超时 → 重试 3 次 → 明确失败原因）

### v1.14.2（2026-08-22）

验证码检测默认关闭（用户实测：误报导致操作卡死）：

- **`--captcha-mode` 默认从 detect 改为 off**：不再每步检测、不再输出 `captcha_detected`——历史行为里普通页面（轮播图/图标类）被误报验证码，下游 AI 一见就停手，输入/点击/拖拽全卡死。现在默认一路畅通；确需检测时显式 `--captcha-mode detect`
- 说明：终端"回声"是 TTY 对输入的标准回显，不是工具输出（工具 stdout 为纯 JSON 状态流）；手动操作请用 `--headed` 真窗口

### v1.14.1（2026-08-22）

视觉会话健壮性（用户实测反馈的 5 个纯工具问题）：

- **修复验证码误报**：收紧检测选择器——裸 `.slider`（轮播图）与 `[class*="rotate"]`（Tailwind rotate-\* 图标）不再被误判为滑块/旋转验证码；文案关键词去掉"向右滑动"（轮播图标准指示文案）。此前普通页被误报 `captcha_detected`，下游 AI 一见就停手
- **新增 `--captcha-mode allow`**：整体关掉验证码检测（页面实际能操作而检测误报干扰时用）
- **新增 `--linger`**：会话结束（AI 断线/quit/EOF）不立即关浏览器——`--headed` 窗口保留给人看完手动关（上限 1h），无头保留 30s 自退。AI 脚本崩了浏览器现场不再跟着消失
- **新增 `--idle-timeout N`**：空闲看门狗可配置（默认 120s；`--headed` 有人在场自动放宽到 600s 防扫码/人肉操作被误杀；0=关闭只受 `--vision-timeout` 约束）
- 持久化上下文的窗口被手动关闭后清理加了容错；验证码人工接管指引更新为 `--headed --profile`（登录态保留）
- 说明：stdin/stdout 协议为程序管道设计，TTY 手敲会混终端回声（非 bug，文档已注明手动场景用 `--headed`）

### v1.14.0（2026-08-22）

登录持久化 + 一批安全/功能修复：

- **新增 `--profile [目录]` 持久化浏览器用户目录**：登录一次以后免登录（豆包/抖音/B站网页版等登录墙站点），cookie/缓存/登录态跨会话保留，等同真实浏览器。首次 `--method vision --profile --headed` 人肉登录，之后无头免登录。目录含登录 cookie，已 gitignore。
- **修复：`--cookies-from-browser` 此前只在 yt-dlp 路线生效**——浏览器/cache/harvest/vision 路线静默无视该参数（Playwright 没有读本机浏览器的 API）。现在借道 yt-dlp 提取器读取并注入；读不到（浏览器未登录/Chrome 新版加密）如实报错。
- **修复：浏览器路线内部 yt-dlp 降级丢 cookie**（显式 `--method browser --cookies` 时降级不带登录态必败）；chain 的 harvest 环节同样漏传 cookie。
- **修复：安全模式 2GB 上限漏洞**——files 直链流式下载与点击下载路线此前不查大小，可被写满磁盘；现在流式过程超限即中断删除、原生下载落盘后复核。
- **修复：域名匹配子串误判**（`notdouyin.com` 能命中 `douyin.com` 类前缀伪造）→ 全部改精确域名/子域匹配。
- **修复：harvest 瞬时失败永久拉黑**（URL 一次超时后永久跳过，迭代滚动收割漏图）→ 允许跨轮重试最多 2 次。
- **修复：视觉会话重建页面后安全模式弹窗拦截丢失**；启动 URL 失败不再浪费截图预算拍空白页。
- 搜索增强：中文 query 精准度排序此前因整句黏词失效 → 中文二元组分词；search_browser 忽略自签证书（与其他路线对齐）；网络嗅探跳过 >1GB 超大响应防内存打爆、同路径不同 query 的不同文件不再被误去重（真重复靠字节指纹砍）。

### v1.13.1（2026-08-22）

SPA 懒加载图集修复（用户反馈：小黑盒图集只抓到 3 张可见缩略图）：

- **迭代滚动收割**替换旧"跳到底+固定滚 3 次+一次性收割"：harvest 路线现在逐段滚动→等新图挂载→收割本轮新图→循环，直到滚到底无新增（或连续 4 轮空 / 30 轮上限 / 200 张封顶）。IntersectionObserver 型懒加载必须让图片逐段经过视口，旧逻辑根本触发不了。
- **跨域 CDN 降级**：无 CORS 头的 CDN 图（如 `cdn.max-c.com`）此前在页面 fetch 里静默失败；现在自动降级脚本侧直连（带浏览器 UA + 页面 Referer）。
- **小图误判修复**：图集收割不再把 <150KB 的图当垃圾（图集正片常在 6–81KB）；只按 icon/logo 关键词滤真图标。
- 回归：chain 六路兜底全过；Bing 图墙实测收满整个懒加载网格（200 张）。

### v1.13.0（2026-08-22）

登录墙下载 + 兜底链扩容：

- **新增 `--cookies <文件>` / `--cookies-from-browser chrome|edge|firefox`**：抖音/B站类登录墙站点带登录态下载。支持 Netscape cookies.txt（"Get cookies.txt" 浏览器扩展导出）或直接读本机已登录的浏览器。全线生效：yt-dlp（`cookiefile`/`cookiesfrombrowser`）、浏览器与 cache 上下文（`add_cookies` 注入）、harvest、note 转路。
- **chain 兜底链扩容 5 → 6 路**：`direct → ytdlp → browser → cache → harvest → text`，一步失败自动换下一个，首个成功立即返回；每步成败记录在 `attempts` 数组；单路崩溃（页面打不开/缺 Playwright）不再拖死整链。带了 cookie 且全链失败时，最后追加 `ytdlp+cookies` 复试一搏。
- **抖音图文帖（`/note/`）自动转路**：yt-dlp 对 note URL 直接报 Unsupported URL——现在自动识别并转 harvest 收割图集原图（输出 `note_auto_rerouted: true`）；harvest 也空时 chain 继续走兜底链不中断。
- `own_search.py download` 透传 `--method` / `--cookies` / `--cookies-from-browser`。

### v1.12.6（2026-08-22）

仓库同步修复：

- **修复：默认分支落后**。此前发版推到 `master`，而 GitHub 默认分支 `main` 还停在 v1.12.3——现在 `main` 已快进到最新，`master` 已删除，今后只维护单一分支
- 吉祥物从 `.github/` 移到 `assets/`，修复 GitHub README 图片渲染（点开头隐藏目录的图片显示不稳定）

### v1.12.5（2026-08-22）

视觉会话健壮性 + 仓库打磨：

- 视觉会话：`--method vision` 启动后首屏状态现在带 `vision_capable` 和 `model` 字段（AI 进会话第一眼就能判定自己是否支持视觉）
- 视觉会话：`eval` 指令新增 10s 死循环看门狗——用户/恶意 prompt 发的 `while(true){}` 等会卡死 JS 时，DevTools HTTP `/json/close` 端点强杀页面，会话自动重建（再也不会永久卡死）
- Bug 修复：`own_search.py download` 和 `own_search.py seed` 补上 subprocess 超时（1800s / 300s），下游卡死不再拖死父进程
- 仓库：新增项目吉祥物（现位于 `assets/mascot.png`），已嵌入两个 README 页面

### v1.12.4（2026-08-22）

视觉会话全面修复 + 12 项关键 bug 修复。同时包含此前未单独发版的 v1.12.2~v1.12.3 内部迭代（`focus` CSS 选择器聚焦、`elements` 元素标注、验证码检测上报）。
- 数据安全：`verify_capture.py --clean` 在无 ffmpeg 时拒删 broken 文件（无法验证 ≠ 损坏），防止清光用户正片。
- 崩溃修复：`search_and_cache.py` 子进程超时不再整体崩溃（改为返回 JSON 错误）；缓存超时放宽到 300s。
- 安全修复：`own_search.py download --safe` 现在真正传递 `--safe` 给底层浏览器。
- 搜索健壮性：smart_search 浏览器版超时 90s→240s；cross_search mega 超时按引擎数放大并在 `rounds_info` 标记 `timed_out_copies`（不再静默返回空）；URL 去重保留业务参数（`v/id/tid` 等，YouTube 不同视频不再被误判为同一条）。
- 体验：视觉会话提示统一中文；`--query --auto` 与 `--url` 模式对齐增加 chain 兜底；日志换行笔误修复。
