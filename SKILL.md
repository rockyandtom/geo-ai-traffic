---
name: geo-ai-traffic
description: 站点的 GEO（Generative Engine Optimization，拿 ChatGPT / AI 推荐流量）只覆盖两条线：**改代码让 AI 抓得到读得懂** + **问 GPT 拿到诊断与探测数据**。代码线含 Title/H1 对齐主词、一需求一页、FAQ 六问、必须 SSR、robots 放行 9 个 AI 爬虫、llms.txt、Cloudflare 边缘层拦截排查、用 geo_audit.py 核对线上真实返回；提问线含上线当天体检三问（能不能抓到你 / 现在推谁 / 愿不愿意推荐你）、五档问题库、提问规程、九项记录、两种环境分开统计、summarize_probe.py 汇总提到率与竞品榜。凡遇到"AI 从来不提我的站""robots / llms.txt 怎么配""页面要不要 SSR / 要不要写 FAQ""怎么直接问 GPT 肯不肯推荐我""怎么验证 AI 到底有没有推荐我""AI 的回答该怎么落到页面改动"，都先读本 skill。凡遇到「反推问题清单」「三步法第一步」「把 GPT 给的问题写回 FAQ」「Claude / Gemini 也要问吗」，走 §5.1 与 `geo_faq.py`，别只给一条单模型问句。**凡遇到「GPT 流量算不清」「direct 里是不是有 ChatGPT」「要不要自己埋点」「有流量没出单」「免费额度是不是给多了」「按 GPT 流量怎么配付费墙」「9.9 / 19.9 / 29.9」「注册到付费 8%」，走 §3.1 与 `geo_attribution.py`。**跨项目发现：维护 ~/.workbuddy/geo-sites.json 全站台账，开工先跑 geo_status.py registry 列出所有待处理站点、各自第几步、到期日；新站由 ai-subscription-site 第 11 步登记，老站跑一次 status 自动补登记。**首次给某个站执行本技能时，必须用 geo_reminder.py plan 生成参数并创建一次性定时提醒，主动触发 7 天后第二次问 GPT（复测三问 + 推进基线探测），创建后用 mark-created 回写 id。** 凡遇到「我有哪些站要做 GEO」「第二次回来该做哪个项目」「上线后 7 天要对比什么」「继续做某个站的 GEO」「改版后还要不要再问 AI」「某个站 GEO 做到哪了」，都先读本 skill 并查台账，不要凭记忆挑项目。不含站外软文铺量、选词赛马、社群案例复盘，也不含建站部署。
agent_created: true
---

# GEO：只做两件事 —— 把代码改对，把该问 AI 的话问对

## 先跑这一条（每次开工都从这里开始）

**第一步：看全站，不要凭记忆挑项目。**

`python scripts/geo_status.py registry`

它列出全站台账里所有待处理站点：域名、项目绝对路径、当前第几步、下一步、到期日，按到期排序并标出已逾期的站。这一步回答的是「**哪些项目现在需要做 GEO**」，不是「某个项目做到第几步」。GEO 是持续动作（上线当天三问 → 7 天对比 → 每次改版复测），不是只在首次上线做一次的清单。

**第二步：进到选中的项目，再看它这一步该干什么。**

`cd <第一步给的项目路径>`

`python scripts/geo_status.py status`

首次给某个站跑，带上站点信息，之后命令会自动填好：

`python scripts/geo_status.py status --domain <域名> --keyword "<主词>" --scene "<细分场景>"`

`status` 现在做三件事：先把全站台账摆到第一屏（哪些站待处理、哪些到期）、把当前项目自动登记进台账（老站漏登记也能补回来）、把当前站的阶段与上次审计同步回台账，最后才给这一步的命令。**不要从头读这个文件再自己判断该做什么**，跑完它照着做就行。

下文 §1–§10 里的 `python scripts/xxx.py` 是简写，一律指本技能目录下的脚本；状态文件写在站点项目目录里，所以**在项目中跑命令要用状态机打印的绝对路径版本**，不要照抄简写。

**第零步：第一次给某个站执行本技能，必须在这一轮创建定时提醒。**

`status` 的第一屏会打印「N 个站还没建定时提醒」并列出域名。这一步不做，第二次提问就又要靠人记。

1. 跑 `python3 scripts/geo_reminder.py plan --domain <域名>`，拿到一份自包含的创建参数：`name` / `prompt` / `scheduleType=once` / `scheduledAt` / `status=ACTIVE` / `cwds`。默认触发时刻是台账到期日 10:00，到期日已过就顺延到明天 10:00。
2. **由 Agent 调用平台的自动化创建工具**按这份参数建一个一次性自动化。Python 脚本不能也不该自己写自动化配置，它只负责生成参数。
3. 把工具返回的 id 回写台账：`python3 scripts/geo_reminder.py mark-created --domain <域名> --id <id> --at <触发时刻>`。**不回写会重复建**，`plan` 遇到已建的站会直接 SKIP。
4. 到点那次执行要做的事写在 `plan` 生成的 prompt 里：把上线第 0 天的三问原样再问一遍做对比、按状态机阶段出题（check 或 bank）、回答记进 `probe-log.csv` 并汇总、续下一轮到期。提示词自包含，不用再读技能全文。
5. 提醒触发过或被删后跑 `clear` 把标记清回 pending，下一轮重新 `plan`；七步走完用 `geo_registry.py done` 归档，并删掉或暂停对应自动化。

漏建检查：`geo_reminder.py pending` 列出所有还没建的站，`status` 第一屏也会报这个数。

### 七步与门禁

1. **页面改造**（§2）→ 跑一次审计，脚本会自动把这一步记为已做过。
2. **基建**（§3）→ 同上，审计覆盖；IndexNow 的 key 文件也在审计里查。**同一轮顺带做 §3.1 的自建归因埋点与按来源分流的付费墙** —— 基线 v1.3.0+ 站是「确认已内置 + 验收 + 打开关」，老站才是生成片段 + 自己写端点。埋点必须在流量来之前上线，晚装补不回历史数据。
3. **审计**（§4）→ **FAIL 清零才算完成**，`geo_audit.py` 会自动记账；有 FAIL 时状态会撤回这一步。
4. **体检三问**（§5）→ 人工做，做完 `python scripts/geo_status.py mark 4`。门禁：第 3 步完成且 FAIL=0。**同一轮顺带做 §5.1 的反推问题清单 → 写回 FAQ**，状态机会把这条命令一起打出来；漏了清单，阶段 5 之后的状态会一直提醒。
5. **基线探测**（§6）→ 人工做，做完 `mark 5`。门禁：第 4 步完成（三问真的问过了）。
6. **改动与复测**（§7）→ 门禁：第 5 步完成（至少跑过一轮探测，有 `probe-log.csv`）。
7. **复盘**（§8）→ 门禁：第 6 步完成。

门禁不是形式。**没有第 5 步的数据，第 6 步改对改错都无从判断**，所以脚本会挡住你跳过它。要强行跳过加 `--force`，但那就等于放弃验证。

### 状态以产物为准，不只信 marks

`marks` 是记账，产物才是事实。三种情况会让两者不一致：在别的目录跑过（状态文件跟着当前工作目录走，不在脚本目录）、忘了 mark、文件被删。

判断顺序固定为：

1. `audit.fail > 0` → 卡在第 3 步，不管 marks 写了什么。
2. 没有 `probe-log.csv`，或里面每题凑不满三遍、缺环境 → 第 5 步没做完。
3. 没有三问的截图 / 回答存档 → 第 4 步没做完，marks 写了 4 也不算。
4. 有基线数据且能拿出两次数字对比 → 第 6–7 步。

要看人话版结论就跑 `python scripts/geo_status.py status`：现在第几步、门禁卡在哪、下一条命令，一次给全。

### 跨项目台账：第二次怎么想起来

**病根**：GEO 原来唯一的触发点是「首次上线」这一个一次性事件，之后的 7 天对比、改版复测、第二个站都没有入口。项目里的 `.geo-state.json` 和 `TODO.md` 都跟着那个项目目录走，换个项目、换次会话就看不见。所以「哪个项目现在需要做 GEO」这个问题，在单个技能内部再加多少提示都答不了。

**解法**：一份路径固定、按站累加的台账 `~/.workbuddy/geo-sites.json`，不放在任何项目里。

1. 谁写入：① `ai-subscription-site` 第 11 步上线当天，用 `geo_registry.py add` 显式登记，带项目绝对路径、主词、上线日、默认 7 天到期；② 任何项目里跑一次 `geo_status.py status`，若该站不在台账里会自动补登记；③ `mark` 与 `status` 会把当前站的阶段、下一步、上次审计日期同步回台账。
2. 谁读：① 本技能开工第一步 `geo_status.py registry`；② 每次 `status` 的第一屏；③ `ai-subscription-site` 第 11 步与它的技能边界指向这里；④ 只想看到期的站用 `geo_registry.py due`。
3. 到期驱动：每站有 `due`（默认上线日 +7）。`due` 只列已到期和今天到期的站；跑完一轮用 `geo_registry.py update --domain <域名> --due-in 7` 续下一轮，用 `--stage N` 校正阶段；七步走完用 `done` 归档，`list --all` 仍查得到。
4. 常用命令（下文 `scripts/` 指本技能目录，在项目目录里跑要写全路径）：`geo_registry.py list`、`due`、`add`、`update`、`done`、`path --domain <域名>`（输出项目绝对路径，可直接 cd）、`scan --root <项目根目录>`。
5. **存量站冷启动**：台账刚建时是空的。跑一次 `geo_registry.py scan --root <你的项目根目录>`，它只读地列出所有带 `.geo-state.json` 或 7 天对比待办痕迹的项目，给出路径、域名和建议的 `add` 命令；**scan 不写台账**，确认哪些站还要做 GEO 之后再逐条登记。也可以直接 cd 进每个已上线项目跑一次 `geo_status.py status`，它会自动补登记。
6. 边界说清楚：台账负责「只要技能被调用、或问起任何一个站，就不会漏掉别的站」；每站的**第二次提问**不靠人记，由首次执行时创建的一次性定时提醒主动拉回来。若连「打开技能」都不想靠人，可以再加一个每周跑 `registry due` 的总览提醒，那需要另外单独建。

`ai-subscription-site` 第 11 步写的 `TODO.md` 仍然保留，它是项目内留痕；**中央台账才是跨项目提醒源**，两者不是二选一。

下面的 §1–§10 是每一步的参考资料：执行面板指到哪一节，才去看哪一节。

---

本 skill 只管两条线：

1. **CODE 线**：站点代码与配置，目标是"AI 抓得到、读得懂、愿意整段引用"。
2. **ASK 线**：向 GPT / Claude / Gemini 提问，目标是拿到诊断报告和可对比的探测数据。

不属于这两条线的内容（选词与赛马、站外软文铺量、社群案例复盘）不在本 skill 范围内。**付费墙本身是商业决策，但「先埋点认出 GPT 来源、再按来源分流」是可执行的代码改动**，已作为 §3.1 纳入 CODE 线；价格数字只作参考口径，不替你定价格。外链渠道见 `游戏站外链建设`，建站与部署见 `站点上线总纲`。

配套文件：

1. `references/probe-protocol.md` —— ASK 线执行细则：五档问题库怎么出、提问规程、九项记录字段、两种环境分开统计、判读口径、常见误判。
2. `assets/templates/ask-gpt-prompts.md` —— 可直接粘贴的提问模板（体检三问、反推、竞品与反向询问、五档题库、复盘追问）。
3. `assets/templates/robots-ai.txt` —— 放行 9 个 AI 爬虫 + llms.txt 的 robots 片段，改域名即用。
4. `assets/templates/llms.txt` / `llms-full.txt` —— 两个文件的结构模板。
5. `assets/templates/question-bank.csv` —— 问题库空表（五档 × 多语言）。
6. `assets/templates/probe-log.csv` —— 探测记录表（九项字段 + 竞品列）。
7. `assets/templates/site-profile.md` —— 单站作业单：主词、页面清单、基建状态、探测结论。
8. `scripts/geo_audit.py` —— 线上真实返回核对（robots / llms.txt / title / H1 / SSR / FAQ / GPTBot UA）。
9. `scripts/summarize_probe.py` —— 把 `probe-log.csv` 汇总成提到率 / 联网率 / 平均位次 / 竞品榜 / 抢用户比例。
10. `scripts/prompt_pack.py` —— 一键生成可复制的提问包，`--stage check|reverse|extra|bank|probe|all`、`--lang zh|en`。
11. `scripts/indexnow_submit.py` —— IndexNow 三件事合一：`keygen` 生成 key 文件写进 public、`check` 核对线上 key 是否 200 且内容一致、`submit` 从 sitemap 或 URL 文件批量推送（带 `--dry-run`）。
12. `scripts/geo_status.py` —— 七步状态机：`status` 给下一步命令并显示全站台账、`registry` 只列全站、`mark <阶段>` 记账、`gate <阶段>` 门禁、`reset` 清空项目状态（不动台账）。开工先跑它，别靠记性。
13. `scripts/geo_registry.py` —— 跨站台账 `~/.workbuddy/geo-sites.json`：`list` / `due` / `add` / `update` / `done` / `path` / `scan`（只读扫存量项目）。回答「哪些站要做 GEO、各在第几步、哪些到期了」。
14. `scripts/geo_reminder.py` —— 首次执行技能时生成「第二次问 GPT」的一次性定时提醒参数：`plan` 出自包含 JSON、`pending` 列漏建的站、`mark-created` 回写自动化 id、`clear` 清回待建。
15. `scripts/geo_faq.py` —— 反推问题清单 → 汇总 → 写回 FAQ：`seed` 出种子清单、`ask` 出 ChatGPT/Claude/Gemini 三模型提问包、`collect` 汇总三份回答、`list` 打印清单与六问覆盖、`render` 出 FAQ 区块与 JSON-LD。产物 `faq-questions.csv` / `faq-block.html` / `faq-block.md`。
16. `scripts/geo_attribution.py` —— 自建归因埋点 + 按 GPT 来源重配付费墙：`snippet` 出前端片段与服务端说明、`paywall` 出分流配置、`report` 汇总来源与转化、`check` 线上核对（取证，不当验收）。产物 `geo-source.js` / `geo-source-server.md` / `gpt-paywall.config.json` / `geo-source-log.csv`。**检测到基线模板 v1.3.0+ 的内置文件时会跳过生成**，只给接线与开关步骤，避免同一功能两份代码。

---

## 0. 何时用

1. 站上线了，要主动让 AI 能引用你，而不是等它自己发现。
2. 页面写好了但 AI 从不提你 —— 先跑审计，再用体检三问定位。
3. 要给站配 AI 爬虫放行、写 llms.txt、核对是否真的生效。
4. 要建问题库、把"AI 推没推我"变成可量化数据。
5. 拿到 AI 的回答后，不知道要改哪一段代码。
6. 新页面上线，要让它更快被 Bing 发现（sitemap 与 IndexNow，见 §3 第 7 条）。
7. **不知道该干什么** —— 直接跑 `scripts/geo_status.py`，它告诉你现在第几步、下一条命令是什么。
8. **第一次给某个站执行本技能** —— 除了看状态，必须在这一轮用 `geo_reminder.py plan` 生成参数并创建第二次提问的一次性定时提醒，创建后 `mark-created` 回写 id。
9. **要反推问题清单、把 GPT 给的真实问法写回 FAQ** —— 走 §5.1 与 `geo_faq.py`，三个模型各问一遍，汇总成 `faq-questions.csv` 再生成页面区块。
10. **算不清 GPT 给了多少流量、direct 里是不是有 ChatGPT、有流量没出单** —— 走 §3.1 与 `geo_attribution.py`：先自建埋点认出来源，再按 GPT 来源重配付费墙，最后用 `report` 出转化与差额。

不适用：还没上线、页面还没内容 —— 先做建站与索引。

输入三件套（缺哪个先问用户，别猜）：

1. `domain` —— 站点域名。
2. `keyword` —— 主词，即 AI 联网时真正会打的那个词（常带年份，如 `ai poster generator 2026`）。
3. `path`（可选）—— 承载该需求的落地页路径，默认首页。
4. `indexnow_key`（可选）—— 只有自建 IndexNow 时才要；走 Cloudflare Crawler Hints 的站没有这个东西。

---

## 1. 三条前提（决定代码为什么这么写）

1. **AI 只在"找工具 / 网站 / 服务"时才联网搜索并列出来源。** 解释类问题它靠记忆回答，不引用任何站点。→ 页面要写成"工具答案页"，不是科普文；FAQ 要答工具问题，不是讲原理。
2. **AI 不做鉴别，直接相信抓到的页面内容。** → 正向表述、摆数据、写明比竞品强在哪，这些都能被它照抄。
3. **顺序是收录 → 出词 → 引荐。** 引荐为 0 不等于失败。→ 先跑审计确认抓取链路通不通，别一上来改文案。

---

## 2. CODE｜页面：六个硬指标

按这个顺序改，每条都对应 AI 抓取与引用的一环。

1. **域名 / Title / H1 三者对齐 `keyword`**，Title 带年份，50–60 字符。对不上，大词流量不会来，这是"主词没量"第一个要查的地方。
2. **一个需求一个页面**，别指望首页通吃所有细分场景。
3. **主词出现在 H1、首屏 CTA、至少一个小标题，以及正文首段。** 只在 meta 里堆词没用，AI 读正文；正文通篇要讲这个需求的工具，不是通用产品介绍。
4. **FAQ 全覆盖**：价格 / 免费额度 / 水印 / 格式支持 / 批量 / 是否要注册，六问一个不漏，标准是"用户不用再问第二个问题"。同时加 FAQPage 结构化数据 —— FAQ 是 AI 最常整段引用的结构。
5. **必须后端渲染（SSR 或 SSG）**，纯 CSR 的 SPA 不合格。判断法：用 curl 取原始 HTML（不带 JS），正文在 HTML 里就是合格；只剩一个挂载 div 就是空壳。这是"页面写得好但 AI 死活不提"的第一大原因。
6. **正向表述 + 具体数据 + 竞品对比**：Best / Top 开头、绝对化表述、写清比谁强在哪。AI 不信也得信，因为它不鉴别。

另外：Bing Webmaster 提交 sitemap。AI 联网搜索对 Bing 依赖更重，索引不在 Bing，引用机会就少一大截。提交之后再做 §3 第 7 条的 IndexNow，新页能更快被 Bing 发现。

---

## 3. CODE｜基建：robots、llms.txt、边缘层

1. **robots.txt 放行这 9 个 UA**：`GPTBot`、`ChatGPT-User`、`OAI-SearchBot`、`ClaudeBot`、`PerplexityBot`、`GoogleOther`、`Amazonbot`、`Applebot`、`Bytespider`；并显式 `Allow` 掉 `/llms.txt`、`/llms-full.txt`。片段直接抄 `assets/templates/robots-ai.txt`，只改域名。
   - 自查一个坑：`User-agent: *` 下面的 `Disallow: /` 会把 `OAI-SearchBot` 一起挡住 —— 通配规则对没被单独列出的爬虫生效。
2. **`/llms.txt`**：一行站点简介 + 分节列核心内容（产品 / 服务 / 博客，每条一句话 + 链接）+ 常用资源（定价、FAQ、sitemap）。结构见模板。
3. **`/llms-full.txt`**：同结构，每条展开成完整文本。
4. **分量校准**：谷歌已明确说不看 llms.txt，其他引擎没说。→ 做，但别当决定项，更别把"没写 llms.txt"当成引荐为 0 的原因。
5. **边缘层拦截（最常见的隐形杀手）**：Cloudflare 的 Block AI bots、Bot Fight Mode、WAF 规则会在边缘直接返 403 / 429 / 503，这一层在 robots.txt 之上 —— robots 写得再对也没用。`geo_audit.py` 会用 GPTBot 的 UA 复测首页，返回这几个码就去 Dashboard 关掉对应开关。
6. **核对只看线上真实返回**，不看本地文件。本地 `public/llms.txt` 存在不代表线上 200，构建产物漏拷、路由拦截、大小写都能让它 404。
7. **IndexNow 提交（让 Bing 侧更快发现新页；代码为主，两处手动）**：
   - 只推 Bing / Yandex / Naver / Seznam，**Google 不参与** —— 它不改变 Google 侧任何数据，不能替代 GSC 与 sitemap。
   - **代码**：`python scripts/indexnow_submit.py keygen --domain <域名> --out ./public` 生成 `<key>.txt`，内容只有 key 本身；文件必须进仓库、随构建上线，不进 public 就是 404。
   - **手动**：部署后跑 `check --domain <域名> --key <key>` 核对线上，必须 200 直出且内容一致；返回 301/302 说明 www 与非 www 不一致，或路由把 `.txt` 吃掉了。这一步和 §4 的 `geo_audit.py --key <key>` 是同一个检查，随手跑哪个都行。
   - **代码**：`submit --sitemap https://<域名>/sitemap.xml` 首次全量，之后每次上线只推增量 `--urls new-urls.txt`；推之前先 `--dry-run` 看一眼清单。
   - **手动**：站挂在 Cloudflare 就开 Crawler Hints，它代发 IndexNow，key 都不用自己管 —— 跟上面的自建方式选一种即可，两边都开会重复提交同一批 URL。
   - 判读：200 成功 / 202 待验证 / 403 key 无效 / 422 host 或 key 不匹配 / 429 当天别重推。**提交 ≠ 收录**，收没收去 Bing Webmaster 看。
   - host 必须完全一致：带 www 和不带 www 是两个 host，key 文件要与提交的 URL 同 host，否则 422。

### 3.1 CODE｜自建归因埋点 → 按 GPT 来源重配付费墙（动作表第 12 / 13 行）

出处是 13 行动作表的最后两行。第 13 行「自建归因埋点」来自 codex-resets.com 的流量结构（月访问 173.9 万，direct 占 83%，AI 引荐**只识别出 chatgpt.com 一个**）与 Frio 2026-10-11 的反馈（出单大多显示 direct）；第 12 行「付费墙按 GPT 流量重配」是哥飞 2026-10-11 的口径：**不给免费额度，主推 9.9 刀单次 / 19.9 刀 3 次 / 29.9 刀 5 次，注册到付费综合约 8%**，并判断「有流量没出单」多数是免费额度给多了。这些是社群实践观测的参考起点，不是本机实测，也不替你定价格。

**这两行是一条链，不是两件事。** 统计工具只会认出 `chatgpt.com` 一条引荐，大量 GPT 流量被并进 `direct`，不自己埋点就永远算不清 GPT 给了多少量；而「按 GPT 流量重配付费墙」的前提，恰恰是能先把这批来源认出来。顺序固定：**先埋点 → 再按来源分流 → 再用自有数据算转化**。埋点必须在流量来之前上线，晚装补不回历史数据，所以它挂在**阶段 2 基建**，由 `geo_status.py status` 跟审计命令一起打出来。

**基线站（我们自己的 ShipAny 模板 v1.3.0+）不用再跑生成命令，也不要再写一遍代码。** 两功能已开箱内置：`src/lib/geo-source.ts`（来源判定）、`src/components/analytics/geo-source.tsx`（上报）、`src/routes/api/geo-source.ts`（匿名端点）、`src/modules/geo-source/service.ts`（落库 + 八列 CSV）、`src/config/geo-paywall.ts`（分流开关）；`drizzle/0001_geo_attribution.sql` 建 `geo_source_event` 表并给 `user` 加两列，`src/core/auth/index.ts` 把首次来源钉在用户行上并传给 `grantForNewUser()`。`geo_attribution.py` 检测到这些文件会**跳过生成**，避免同一功能存在两份实现。基线站上线当天只做三件事：① 确认迁移已随 `pnpm db:migrate` 执行；② 后台打开 `/api/admin/geo-source-export` 下载 `geo-source-log.csv`，确认有 visit 行；③ 验完来源后把 `GEO_PAYWALL.enabled` 从 `false` 改成 `true`。**开关默认关，没验过线上归因不要开**；价格与档位仍只改本站 `src/config/pricing.ts`。`check --domain` 对基线站改为探测 `/api/geo-source`（非法 Content-Type 的空 POST，不写数据），`geo_audit.py` 的归因项同样认这种形态。

下面四步只适用于**没有这套基线的老站**，产物全在项目目录：

1. `python scripts/geo_attribution.py snippet` —— 生成 `geo-source.js`（原生 JS，无依赖）、`geo-source-server.md`（端点与字段说明）、`geo-source-log.csv`（导出表头）。检测到 `public/` 会自动同步一份 js 进去。片段按「URL 显式参数 → referrer 命中 AI 域名 → direct」判来源，注册与付费节点调 `__geoTrack('signup')` / `__geoTrack('purchase', {plan, amount})`，或用 `data-geo-event` 属性。
2. **把片段接上线**：所有落地页加 `<script src="/geo-source.js" defer></script>`，按 `geo-source-server.md` 写 `/api/geo-source` 接收端点，注册与付费事件都要带上来源。这一步脚本替不了，也别只生成不接。
3. `python scripts/geo_attribution.py paywall` —— 生成 `gpt-paywall.config.json`：只有识别到 AI 来源的会话走 `free_credits=0` 与三档定价；`direct_suspect_ai` 走 fallback，不关免费额度；注册与付费都上报，才能算转化。价格、档位、币种按自己站改，改完把 `status` 从 `template` 改成 `active`。
4. `python scripts/geo_attribution.py check --domain <域名>` 核对片段线上是否加载；把埋点表导出成 `geo-source-log.csv` 后跑 `python scripts/geo_attribution.py report --csv geo-source-log.csv`，出各来源的会话 / 注册 / 付费 / 金额、注册到付费转化率、`chatgpt.com` 单条能认出的量 vs 自埋点认出的 AI 总量、疑似量占比。转化低不要先改定价：先查埋点是不是漏了注册 / 付费事件，再查免费额度是不是给多了。

三条纪律：

1. **referrer 为空 ≠ 不是 AI。** AI App 内打开经常不带 referrer，这类流量标 `direct_suspect_ai` 单独统计，**不能并进确定的 AI 来源**，也不能直接丢掉；它混着爬虫、直接输入和书签，只能当上界线索。省掉这条，就又变回「只认 chatgpt.com」。
2. **首次来源为准**，站内跳转不覆盖；服务端落库也别拿最后一次 visit 的来源去覆盖注册 / 付费事件的来源。
3. **没有真实埋点数据就不出转化结论**。`report` 对空表只说「没有数据行」，不许编造 AI 流量或转化率；`check` 是取证工具，只报「线上有没有加载到」，不当验收判官。

挂点有三个，都不靠人记：阶段 2 的顺带命令、`geo_audit.py` 的第九项检查（**WARN，不阻塞 FAIL 清零**，因为有些站用第三方方案）、§8 验收清单第 10、11 项。`references/probe-protocol.md` §6.2 的「direct 里可能藏着 ChatGPT 流量」就是这一步的依据。

---

## 4. CODE｜跑审计（geo_audit.py）

改完页面或基建必须跑一次，它读的是 `https://` 线上响应：

`python scripts/geo_audit.py example.com --keyword "ai poster generator" --path /best-ai-poster-generator`

参数：`--keyword` 主词（用于 title / H1 对齐判定）、`--path` 落地页、`--key` IndexNow 的 key（传了才核对 key 文件）、`--sitemap` sitemap 地址（默认 `/sitemap.xml`）、`--json` 机器可读、`--proxy` 走代理。退出码 0 全通过 / 1 有 FAIL / 2 参数或网络致命错误。

它检查十项：robots 是否放行 9 个爬虫、llms.txt 与 llms-full.txt 是否 200 且非空、title 是否含主词与年份、H1 是否含主词、**是否后端渲染**、**有没有 FAQ 结构**、**GPTBot UA 抓首页返回什么码**、**sitemap 是否可达且落地页在里面**（返回 HTML 说明被 SPA 兜底规则吃了）、**IndexNow key 文件是否 200 直出且内容一致**（不传 `--key` 时这项只给 INFO，走 Cloudflare Crawler Hints 的站可以跳过）、**归因埋点片段有没有被落地页引用**（§3.1，WARN 级，只取证、不阻塞 FAIL 清零）。

**汇报纪律（这条比脚本本身重要）**：`geo_audit.py` 是取证工具，不是验收判官。不许用"退出码 0 / 全部通过"当结论，必须给出具体证据 —— 哪一页、title 实际长什么样、H1 原文、FAQ 命中几条、GPTBot UA 拿到的是 200 还是 403、原始 HTML 里有多少字正文。用户要能拿这些去对照页面自己判断。

### 4.1 每个 FAIL 对应改哪里（脚本末尾会直接打出来）

1. robots 放行被拦 / 缺 Sitemap 行 → 站点根 `robots.txt`（静态站 `public/robots.txt`，Next.js 用 `app/robots.ts` 或 `public/robots.txt`）；片段抄 `assets/templates/robots-ai.txt`。
2. `/llms.txt` 404 或结构不对 → `public/llms.txt`（Next.js / Nuxt / Astro 都是 `public/`）。
3. `/llms-full.txt` 404 → `public/llms-full.txt`。
4. Title 未对齐主词 / 无年份 / 过长 → 落地页的 `<title>`：Next.js 改 `metadata.title` 或 `generateMetadata`，Astro 改 frontmatter 的 `title`，其余改模板里的 `<title>`。
5. H1 缺失或多个 → 落地页组件里的 `<h1>`，一页只留一个，页尾 CTA 不要再用 h1。
6. SSR 不通过 → 渲染模式：去掉纯客户端挂载点，改 SSR / SSG；Next.js 用 server component 或静态生成，Vite SPA 要加预渲染。
7. FAQ 缺失或不完整 → 落地页加一块人眼可见的 FAQ + FAQPage JSON-LD，六问：价格 / 免费额度 / 水印 / 格式 / 批量 / 注册。
8. GPTBot UA 拿到 403 / 429 / 503 → **不在代码里**：Cloudflare Dashboard 关 Block AI bots 与 Bot Fight Mode，或给 GPTBot 放行 WAF 规则。改 robots 没用。
9. sitemap 404、或 200 但返回 HTML（被 catch-all 兜底）→ 构建期生成（Next.js 用 `app/sitemap.ts`，Astro 用 sitemap 集成，其余用脚本从数据源生成），并把 `/sitemap.xml` 排除出 catch-all 路由。
10. IndexNow key 404 / 内容不符 / 302 → `public/<key>.txt`，内容只放 key 本身；生成用 `scripts/indexnow_submit.py keygen`。
11. 归因埋点片段没加载（WARN）→ 基线站确认 `/api/geo-source` 在线且跑过 0001 迁移（审计会自动探测端点）；老站跑 `scripts/geo_attribution.py snippet`，确认 `public/geo-source.js` 上线、落地页有 script 引用，并按 `geo-source-server.md` 接好端点；细节见 §3.1。

改完重跑同一条命令即可。但 **FAIL 清零只说明这几项机检过了** —— 正文够不够、FAQ 有没有真答全、文案对不对主词，仍然要人看，这条不回退到"退出码当验收"。

`§7` 是反方向：AI 说了什么 → 该改哪段代码；本节是代码自己哪里不对 → 改哪个文件。两边都用同一套位置口径。

---

## 5. ASK｜上线当天三问（成本最低的诊断）

新开会话，按顺序问，把回答当诊断报告用。现成句子跑 `python scripts/prompt_pack.py --domain <域名> --keyword "<主词>" --scene "<细分场景>" --stage check`，或看 `ask-gpt-prompts.md` 的 A 节。

1. **问抓取**：「你能不能访问 `https://<域名>`，把你读到的页面内容复述一遍？读不到就告诉我卡在哪一步。」
   - 复述出 H1、主词、FAQ 条目 = 链路通。
   - 说读不到、或只复述出导航栏和 Loading = SSR 或爬虫放行有问题，回 §2 第 5 条与 §3。
2. **问对手**：「你的数据库里，关于 `<主词>` 这个需求，目前有哪些工具或网站可以推荐？按推荐优先级列出来，并说明为什么推荐它们。」
   - 拿到的名单就是你的真实对手榜（进 `probe-log.csv` 的 `competitors` 列），它给的推荐理由直接当你的页面大纲。
3. **问差距**：「如果用户问『有没有能做 `<细分场景>` 的网站』，你会推荐 `https://<域名>` 吗？为什么？要多推荐它，页面需要改进什么？请具体到板块。」
   - 它说缺 FAQ 就补 FAQ，说缺价格就摆价格表。**改完用同一条再问一遍**，看理由是否转向 —— 这是闭环，不做闭环等于白问。

三问的截图与回答全文要存档，和后面的探测数据放一起：这是同一账号在"主动问"与"被动等"两种姿态下的对照。

模板库里另外三种问法按需取用（`ask-gpt-prompts.md` 的 B、C 节）：**反推三步**让它自曝真实用户会怎么问；**抄竞品问原因**把它的推荐理由直接当页面大纲；**角色互换**在闲聊里补一句「我听说 `https://<域名>` 也在做这个，你去对比一下」—— 这句会把 URL 递到它面前触发实时抓取，不用等定期爬虫。

### 5.1 反推问题清单 → 写回 FAQ（三步法第一步，本阶段必做）

出处是 13 行动作表第 7 条 / 三步法 ①（2026-09-09）：**问 ChatGPT「假如你是用户想找 XX 工具，会怎么提问？」Claude、Gemini 同理，汇总成问题清单。**

为什么单独列一节：这条原来只有 `prompt_pack.py --stage reverse` 里的一条单模型问句，`gefei-playbook.md` 删掉之后，「三个模型」「汇总成清单」「写回 FAQ」三件事都没了，状态机也没有挂点 —— 正是「信息躺在技能里没人记得用」的那种情况。现在它挂在阶段 4，跟三问同一轮做，命令由 `geo_status.py status` 一起打出来。

四步走，产物全在项目根目录：

1. **先出种子清单**：`python scripts/geo_faq.py seed`，写 `faq-questions.csv`，含 §2 第 4 条的六问（价格 / 免费额度 / 水印 / 格式 / 批量 / 注册）加四条真实口语问法。这一步不依赖任何 AI，现在就能拿去写回 FAQ。
2. **拿三模型的问句**：`python scripts/geo_faq.py ask --category "<品类>"` 输出可直接复制的提问包。同一句在 **ChatGPT、Claude、Gemini 各开一个新会话问一遍**，问完再各补一句归类追问；三份回答全文分别存成 `faq-raw-chatgpt.txt`、`faq-raw-claude.txt`、`faq-raw-gemini.txt`。用未登录的临时会话，别用带自己产品记忆的账号。
3. **汇总成清单**：`python scripts/geo_faq.py collect --dir .` 自动抽问句、跨模型去重、按六类归档、追加进 `faq-questions.csv`（已填的答案不会被覆盖）。`python scripts/geo_faq.py list` 随时把清单和六问覆盖情况打印出来。**汇总由脚本做，不用再问一次 AI**，也不要手工复制粘贴三份名单。
4. **写回 FAQ**：打开 `faq-questions.csv`，逐条填真实答案、把 `status` 改成 `done`，再跑 `python scripts/geo_faq.py render`，生成 `faq-block.html`（人眼可见的 FAQ 区块 + FAQPage JSON-LD）与 `faq-block.md`。把区块贴进落地页，人眼可见内容与 JSON-LD 必须一致，上线后重跑一次 `geo_audit.py` 看 FAQ 结构这项是不是 PASS。

三条纪律：① 清单内容只能来自三个模型的真实回答或 `seed` 的固定六问，**不许编造「AI 给出的问句」**，也不许给没答案的条目编答案；② `render` 只用已答条目，没答案的问题不贴上线；③ 六问是底线，反推得到的是「六问之外用户真会问的」，写回去之后依然要满足 §2 第 4 条与 §4.1 第 7 条。

三步法的后两步（**另开窗口逐问观察抓取**、**把标题丢回去问该写什么**）仍在 `prompt_pack.py --stage reverse` 的 B2 / B3，别只做第一步就停。第 4 步写回 FAQ 属于 §7 的第 2 条映射：`geo_faq.py` 就是把那句话变成可执行改动的那一环。

---

## 6. ASK｜问题库与探测

细则见 `references/probe-protocol.md`，这里只给骨架。

这一步是**阶段 5**，要等 `geo_status.py` 的门禁过了才启动（第 4 步三问做完）。跳过它直接改页面，等于改对改错都不知道。

1. **五档问题库**（每种语言各一套，主体是第二档）。生成用 `python scripts/prompt_pack.py --stage bank --lang zh` / `--lang en`：
   1. 品牌题「某某是什么」—— 看它认不认识你、价格与免费额度有没有过时。
   2. **找工具题「有没有能做某事的网站」—— 每个细分品类一题，这是主体。** 只有这类题稳定触发联网 + 列来源。
   3. 比较 / 合集题「最好的几个」「能一次做几件事的」—— 看榜单型回答里给不给你位次。
   4. 口语版 —— 同一需求用日常说法再问一遍，术语版被提、口语版不提说明页面措辞离用户太远。
   5. 解释类题 —— 少量，只用来验证"解释类不联网"这条规律还成不成立。
2. **提问规程（机械细节决定数据可信度）**：每题新开会话；页面打开等三四秒再输入；确认消息真发出；回答十几秒不再变化才算写完（最长等两分钟）；两题间隔二三十秒；遇人机验证或限流**立刻停下记录，不硬闯**。
3. **每题问三遍** —— 名单和顺序每次都会变，单次结果不能当结论。三遍全提 = 稳定；全不提 = 稳定不提；摇摆的单独列出。
4. **两种环境分开统计，绝不混算**：未登录（脚本开全新浏览器，干净、可无人值守、偏保守）与登录后**临时聊天**（贴近真实用户，但必须用无记忆会话，否则账号里关于自己产品的记忆会污染结果）。同一批 17 题实测：未登录提到 2 次、登录后 5 次，差 2.5 倍。
5. **每条回答记九项**：问题 / 语言 / 环境 / 第几遍 / 是否联网 / 提没提你 / 位次 / 原话 / 引用的是首页还是内页 / 描述是否过时 / 它有没有说「我直接在对话里帮你做」。字段定义见 `probe-log.csv`。
6. **汇总**：`python scripts/summarize_probe.py --csv probe-log.csv` 出提到率、联网率、平均位次、竞品榜、抢用户比例。报告中两种环境分两段给提到率，不要给一个"总提到率"。

---

## 7. 把 AI 的回答翻译成代码改动

这是两条线的接缝：ASK 线拿到的每句话，都要能落成 CODE 线的具体改动，否则问题就白问了。

1. 「我读不到这个页面」→ 查三处：是否 SSR（curl 原始 HTML 有没有正文）、robots 是否放行 `ChatGPT-User` / `OAI-SearchBot`、边缘层是否 403。
2. 「缺 FAQ / 没写价格 / 内容太薄」→ 按 §2 第 4 条补 FAQ 六问，把价格表提到首屏；六问之外该补什么，用 §5.1 的三模型反推清单决定，别自己拍脑袋想问题，答案填好后由 `geo_faq.py render` 直接出区块。
3. 「引的是你首页，不是你那个落地页」→ 说明"一需求一页"没做到，或者内页 Title/H1 没对齐该细分主词。
4. 「因为它价格透明 / 因为它有对比表」→ 这就是它给的大纲，照着上板块。
5. 「我直接在对话里帮你做」出现得多 → 这个需求天生不需要点进网站，换需求比继续优化页面划算。
6. 「三遍都没提，但页面能读到」→ 不是代码问题，是还没被索引或引用位置被竞品占满，回去查收录，别再改文案。

本节只处理"AI 说了什么"。如果是审计脚本自己报的 FAIL（抓取、渲染、FAQ 结构这类），去 §4.1 找改动位置，别在这里绕。

---

## 8. 跑完怎么算做完

CODE 线：

1. [ ] Title 含主词与年份、H1 含主词、域名与主词方向一致
2. [ ] 一个需求一个落地页，主词进了 H1 / 首屏 CTA / 小标题
3. [ ] FAQ 覆盖价格、免费额度、水印、格式、批量、注册六问，且有 FAQPage 结构
4. [ ] curl 原始 HTML 能读到正文（SSR / SSG 达成）
5. [ ] robots 放行 9 个 AI 爬虫，且没有通配 `Disallow: /` 把它们顺带挡住
6. [ ] `/llms.txt` 与 `/llms-full.txt` 线上 200 且非空；`/sitemap.xml` 200、不是 HTML 兜底、落地页在里面
7. [ ] GPTBot UA 抓首页返回 200（不是 403 / 429 / 503）
8. [ ] `geo_audit.py` 已跑，且报告里给的是具体证据（title 原文、H1 原文、FAQ 命中条数、UA 返回码、sitemap 条数、key 文件状态），不是"退出码 0"
9. [ ] IndexNow 二选一做完了：要么 Cloudflare Crawler Hints 已开，要么 key 文件线上 200 且内容一致、提交返回 200/202（不是 403/422）
10. [ ] 自建归因埋点已上线：基线站 = `/api/geo-source` 在线、后台能下到带 visit 行的 CSV、`GEO_PAYWALL.enabled` 在验完来源后才打开；老站 = `public/geo-source.js` 随构建发布、落地页有 script 引用、`/api/geo-source` 真的在收数。`direct_suspect_ai` 单独统计，没并进确定量
11. [ ] `gpt-paywall.config.json` 已按本站改好、status 改成 active；注册与付费事件都带来源，`report` 能算出注册到付费转化率与 direct 疑似量占比

ASK 线：

12. [ ] 体检三问问过、截图存档，且"问差距"做过一轮改完再问的闭环
13. [ ] 问题库五档已出，主体是找工具题
14. [ ] 每题三遍、两环境分开、九项字段有记录
15. [ ] `summarize_probe.py` 有输出：提到率 / 联网率 / 竞品榜
16. [ ] 每条 AI 反馈已落到 §7 的某一条改动上，或明确判定"不是代码问题"
17. [ ] 结论写成一句：现在卡在收录、出词、还是引荐
18. [ ] `faq-questions.csv` 已建、三模型反推的真实问句已汇总进去、六问覆盖齐全；`geo_faq.py render` 出的区块已贴进落地页，且 `geo_audit.py` 的 FAQ 结构这项是 PASS

首次执行必做（每个站只做一次，漏了就没有第二次）：

- [ ] 本站已登记进 `~/.workbuddy/geo-sites.json`，带项目绝对路径与 7 天到期日
- [ ] `geo_reminder.py plan` 生成的参数已用自动化创建工具建成一次性提醒，触发时刻为到期日 10:00
- [ ] 工具返回的 id 已用 `mark-created` 回写台账；`geo_reminder.py pending` 里不再出现本站

---

## 9. 附录 A｜产出"可复制的提问"时的硬规则

**报告里不许只说"去问 AI 愿不愿意推荐你"，必须把整句写出来让用户能直接复制。**

1. **生成方式**：跑 `python scripts/prompt_pack.py --domain <域名> --keyword "<主词>" --scene "<动词短语场景>" --competitor <竞品域名> --lang zh|en --stage check|reverse|extra|bank|probe|all`，用它的输出，别手拟问句。
2. **格式（违反等于返工）**：提问正文用普通段落直出，不要代码块、不要表格、不要用引号把整段包起来；每条前只加一行用途说明，空一行再放提问原文；变量全部替换成真实值，不许留 `{domain}` 这类占位符。
3. **数量**：一次最多 10~15 条，多了让用户分批；题库超 15 条按档分组，先给主体档（找工具题）。
4. **结尾必须交代三件事**：在哪个环境问（未登录 / 登录后临时聊天）、同一题问几遍（三遍）、存证三样（回答全文 + 整屏截图 + 来源面板）。
5. **按阶段给不同的包**：先跑 `geo_status.py` 看当前在第几步，按它给的命令出题 —— 第 4 步给 `check`（三问）**并顺带给 §5.1 的 `geo_faq.py ask` 三模型包**，**第 5 步才给 `bank`**（题库），第 6 步给 `probe`。用户没指定也不要一次把六种包全倒出来。
6. **反推问题清单不给半成品**：只给一条「去问 ChatGPT 会怎么提问」等于没给。要按 §5.1 把三份可复制的问句都写出来，交代回答存成 `faq-raw-*.txt`，并说明汇总与写回 FAQ 的命令。**不要把 15 这个数字当成清单本身** —— 用户要的是三份真实回答汇总后的问题清单，不是「它会给你 15 条」这句许诺。

---

## 10. 三条红线

1. **别把 llms.txt 没写当成引荐为 0 的原因** —— 谷歌明确说不看，真正的堵点是前端渲染与边缘层拦截。
2. **别用 DR 判断能不能被 AI 推荐** —— 1 DR 的站也被推荐过，谷歌和 ChatGPT 都不看 DR。
3. **被限流、遇人机验证就停** —— 硬闯会把账号打进风控，整批探测数据作废。
