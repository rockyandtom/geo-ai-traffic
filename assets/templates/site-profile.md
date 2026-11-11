# 站点 GEO 作业单

复制到项目里，边做边填。只记两条线：代码（页面 + 基建 + 审计）与提问（体检 + 探测）。

## 1. 基本信息

- domain：
- brand：
- keyword（AI 联网时真会打的词，常带年份）：
- 落地页 path（承载该需求的页面，默认首页）：
- 上线日期：

## 2. CODE｜页面（SKILL.md §2）

- Title 原文（含主词 + 年份，50–60 字符）：
- H1 原文：
- 主词是否进了首屏 CTA、至少一个小标题：是 / 否
- 落地页清单（一个需求一页）：
  1.
  2.
- FAQ 覆盖情况（价格 / 免费额度 / 水印 / 格式 / 批量 / 注册，六项各打勾）：
- 是否有 FAQPage 结构化数据：是 / 否
- curl 原始 HTML 能读到正文（SSR / SSG）：是 / 否
- 内容是否正向表述 + 数据 + 竞品对比：
- Bing Webmaster 已交 sitemap：是 / 否

## 3. CODE｜基建（SKILL.md §3）

- robots 放行 9 个 AI 爬虫：是 / 否
- 有没有通配 `User-agent: * / Disallow: /` 把搜索类爬虫顺带挡住：有 / 无
- Cloudflare 是否开了 Block AI bots / Bot Fight Mode（开了会 403，必须关）：
- `/llms.txt` 线上 200 且非空：是 / 否
- `/llms-full.txt` 线上 200 且非空：是 / 否
- `/sitemap.xml` 线上 200、不是 HTML 兜底、落地页在里面：是 / 否（条数：）
- GPTBot UA 抓首页返回码：
- IndexNow 走的哪条：Cloudflare Crawler Hints 已开 / 自建 key 文件线上 200 / 未做

### 自建归因埋点 → 按 GPT 来源重配付费墙（SKILL.md §3.1，阶段 2 同一轮做）

- `public/geo-source.js` 已随构建上线：是 / 否
- 落地页有 script 引用 / `/api/geo-source` 真的在收数：是 / 否
- `geo_attribution.py check` 两项结果（片段 200 且含标记 / 首页有引用）：
- 注册与付费事件都带来源、首次来源不被站内跳转覆盖：是 / 否
- `gpt-paywall.config.json`：template / active（价格与档位改成本站的）：
- `report` 出的注册到付费转化率：% （参考 8%，哥飞 2026-10-11 社群观测，非本机实测）
- chatgpt.com 单条能认出的访问数 / 自埋点另外认出的 AI 来源数：
- `direct_suspect_ai` 会话数与占比（单独列，不并入确定量）：

## 4. CODE｜审计取证的原始结果（SKILL.md §4）

贴 `geo_audit.py` 的具体输出，不要只写"通过"：

- title 实际内容：
- H1 实际内容：
- SSR 判定依据（原始 HTML 正文字数 / 是否只有挂载点）：
- FAQ 命中条数：
- sitemap 条数 / 落地页是否在里面 / 是否被 HTML 兜底：
- IndexNow key 文件状态（没查就写"未查"）：
- GPTBot UA 返回码：
- 归因埋点片段这项：PASS / WARN（只取证，不阻塞 FAIL 清零）：
- robots 中 9 个爬虫各自结果：

## 5. ASK｜体检三问（SKILL.md §5）

- 问抓取：它复述出了什么（有没有复述到 H1 / 主词 / FAQ 条目）：
- 问对手：它列了哪些站 + 推荐理由：
- 问差距：它说页面缺什么（逐条抄）：
- 改完再问一次，理由有没有转向：
- 截图存档路径：

### 反推问题清单 → 写回 FAQ（SKILL.md §5.1，阶段 4 同一轮做）

- `faq-questions.csv` 已建 / 总条数：
- 三份回答全文是否齐：ChatGPT / Claude / Gemini
- `collect` 新增问句数 / 跨模型去重丢弃数：
- 六问覆盖：齐 / 还缺哪几类
- 已填答案条数 / 待答条数（待答的不许贴上线）：
- `faq-block.html` 已贴进落地页：是 / 否
- 贴完重跑 `geo_audit.py`，FAQ 结构这项：PASS / WARN / FAIL

## 6. ASK｜探测（SKILL.md §6）

- 问题库文件：
- 未登录批：题目数 / 提到次数 / 联网率
- 登录后批（临时聊天）：题目数 / 提到次数 / 联网率
- 平均位次：
- 竞品榜 top5：
- 抢用户话术（"我直接帮你做"）比例：
- 探测时段（与服务器日志对账用）：开始 —— 结束

## 7. 结论

- 每条 AI 反馈落到了哪条代码改动（对 SKILL.md §7）：
- 现在卡在：收录 / 出词 / 引荐（三选一）
- 下一件事：
