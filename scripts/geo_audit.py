#!/usr/bin/env python3
"""GEO 线上体检：核对 AI 友好度基建与页面关键词对齐是否真的生效。

只读线上真实返回（不是本地文件），检查九件事：
1. robots.txt 是否放行 9 个 AI 爬虫
2. /llms.txt 与 /llms-full.txt 是否 200 且结构像样
3. 落地页 title / H1 是否对齐主词、title 是否带年份
4. 落地页是否**后端渲染**（原始 HTML 里就有可读正文，不是 JS 空壳）
5. 落地页有没有 **FAQ 结构**（FAQPage 结构化数据或 FAQ 小标题）
6. 用 GPTBot 的 UA 再请求一次首页，判断是否被边缘层（如 Cloudflare）拦住
7. sitemap.xml 是否可达、有多少条、落地页在不在里面（IndexNow 与 Bing 提交都靠它）
8. 传了 --key 时核对 IndexNow 的 key 文件：是否 200 直出、内容是否与 key 一致
9. 落地页有没有加载**自建归因埋点**（统计工具只认 chatgpt.com，其余并进 direct）

用法：
    python geo_audit.py example.com --keyword "ai poster generator"
    python geo_audit.py example.com --keyword "ai poster generator" --path /best-ai-poster-generator
    python geo_audit.py example.com --key 3f9a2c7b41d8e05a6b1c9f2e7d4a8b03
    python geo_audit.py https://example.com --keyword "ai poster generator" --json
    python geo_audit.py example.com --proxy http://127.0.0.1:7892

退出码：0 全部通过 / 1 有 FAIL 项 / 2 参数或网络致命错误。
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

AI_BOTS = [
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "PerplexityBot",
    "GoogleOther",
    "Amazonbot",
    "Applebot",
    "Bytespider",
]

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"

# 每个检查项失败时该去改哪里。按 item 名做包含匹配，兜底给空串。
# 目的：报告不只说"哪里不对"，还要说"改哪个文件"，改完能直接重跑同一命令。
FIX_HINTS = [
    (
        "robots.txt 放行",
        "站点根 robots.txt（静态站 public/robots.txt；Next.js 用 app/robots.ts 或 public/robots.txt）；片段抄 assets/templates/robots-ai.txt",
    ),
    ("robots.txt 有 Sitemap", "同一个 robots.txt 末尾加一行 Sitemap: https://<域名>/sitemap.xml"),
    (
        "robots.txt 可访问",
        "先查域名解析与证书；返回 401/403/503 是边缘层拦截，去 Cloudflare 关 AI 爬虫拦截（不是改 robots）",
    ),
    ("/llms.txt", "public/llms.txt（Next.js / Nuxt / Astro 都是 public/）；结构抄 assets/templates/llms.txt"),
    ("/llms-full.txt", "public/llms-full.txt；结构抄 assets/templates/llms-full.txt"),
    (
        "Title",
        "落地页的 <title>：Next.js 改 metadata.title / generateMetadata，Astro 改 frontmatter 的 title，其余改模板里的 <title>",
    ),
    ("H1", "落地页组件的 <h1>，一页只留一个；页尾 CTA 不要再放 h1"),
    (
        "后端渲染",
        "渲染模式：去掉纯客户端挂载点，改 SSR / SSG；Next.js 用 server component 或静态生成，Vite SPA 要加预渲染",
    ),
    ("FAQ", "落地页加一块人眼可见的 FAQ + FAQPage JSON-LD；六问：价格 / 免费额度 / 水印 / 格式 / 批量 / 注册"),
    (
        "GPTBot",
        "不在代码里：Cloudflare Dashboard 关 Block AI bots 与 Bot Fight Mode，或给 GPTBot 放行 WAF 规则",
    ),
    (
        "sitemap.xml",
        "构建期生成（Next.js 用 app/sitemap.ts，Astro 用 sitemap 集成，其余用脚本从数据源生成），并把 /sitemap.xml 排除出 catch-all 路由",
    ),
    (
        "IndexNow key",
        "public/<key>.txt，内容只放 key 本身；生成用 scripts/indexnow_submit.py keygen --domain <域名> --out ./public",
    ),
    (
        "归因埋点",
        "基线 v1.3.0+ 已内置：确认 /api/geo-source 在线且跑过 0001 迁移；老站才需要跑 scripts/geo_attribution.py snippet 生成 public/geo-source.js 并接端点；见 SKILL.md §3.1",
    ),
]


def lookup_fix(item):
    for needle, fix in FIX_HINTS:
        if needle in item:
            return fix
    return ""



def fetch(url, ua=BROWSER_UA, proxy=None, timeout=20):
    """返回 (status, headers_dict, body_text, error)。不抛异常，错误放进第 4 项。"""
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    ctx = ssl.create_default_context()
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(400_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, dict(resp.headers), raw.decode(charset, "replace"), None
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read(20_000)
        except Exception:
            pass
        return e.code, dict(e.headers or {}), raw.decode("utf-8", "replace"), None
    except Exception as e:  # noqa: BLE001
        return None, {}, "", f"{type(e).__name__}: {e}"


def probe_geo_endpoint(page_url, proxy=None, timeout=10):
    """基线模板 v1.3.0+ 把归因做成 React 组件，SSR HTML 里没有脚本标记。

    这时改为探测匿名端点 /api/geo-source 是否在线：用非法 Content-Type 发
    一个空 POST，端点返回 415 / 400 / 403，未部署则是 404 / 405。不会写入
    任何埋点数据，也不会产生假的 visit 行。
    """
    parts = page_url.split("/")
    base = parts[0] + "//" + parts[2]
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        base + "/api/geo-source",
        data=b"",
        method="POST",
        headers={
            "Content-Type": "text/plain",
            "User-Agent": "geo-audit-probe/1.0",
        },
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001
        return 0


# ---------- robots.txt ----------


def parse_robots(text):
    groups = []
    cur = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            if cur is None or cur["closed"]:
                cur = {"agents": [val.lower()], "rules": [], "closed": False}
                groups.append(cur)
            else:
                cur["agents"].append(val.lower())
        elif key in ("allow", "disallow"):
            if cur is None:
                continue
            cur["rules"].append((key, val))
            cur["closed"] = True
        else:
            if cur is not None:
                cur["closed"] = True
    return groups


def path_matches(pattern, path):
    if pattern in ("", "/"):
        return True
    rx = re.escape(pattern).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    else:
        rx += ".*"
    return re.match("^" + rx, path) is not None


def pick_rules(groups, bot):
    bot = bot.lower()
    best = None
    for g in groups:
        for a in g["agents"]:
            if a == "*":
                continue
            if a in bot or bot in a:
                score = len(a)
                if best is None or score > best[0]:
                    best = (score, g["rules"])
    if best:
        return best[1], "explicit"
    for g in groups:
        if "*" in g["agents"]:
            return g["rules"], "wildcard"
    return [], "no-rule"


def is_allowed(rules, path="/"):
    decision = True
    best_len = -1
    for key, pat in rules:
        if pat.strip() == "":
            continue
        if not path_matches(pat, path):
            continue
        if len(pat) > best_len or (len(pat) == best_len and key == "allow"):
            best_len = len(pat)
            decision = key == "allow"
    return decision


# ---------- HTML ----------


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"\s+", " ", text).strip()


def get_title(html):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return re.sub(r"\s+", " ", strip_tags(m.group(1))).strip() if m else ""


def get_h1s(html):
    return [
        re.sub(r"\s+", " ", strip_tags(h)).strip()
        for h in re.findall(r"(?is)<h1[^>]*>(.*?)</h1>", html)
    ]


def keyword_hit(text, keyword):
    """整串命中或全部词命中都算命中，返回 (bool, mode)。"""
    if not keyword:
        return None, "no-keyword"
    t = text.lower()
    if keyword.lower() in t:
        return True, "exact"
    words = [w for w in re.split(r"\s+", keyword.lower()) if w]
    if words and all(w in t for w in words):
        return True, "all-words"
    return False, "miss"


def check_llms(text):
    issues = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        issues.append("内容为空")
        return issues
    if not lines[0].lstrip().startswith("# "):
        issues.append("首行不是一级标题（应为 `# 站点名`）")
    has_quote = any(ln.lstrip().startswith("> ") for ln in lines[:5])
    if not has_quote:
        issues.append("缺少 `> 一行简介`（AI 权重最高的一行）")
    items = [ln for ln in lines if ln.lstrip().startswith("- [")]
    if len(items) < 3:
        issues.append(f"条目只有 {len(items)} 条，建议 ≥3 条（名称 + 链接 + 一句话）")
    return issues


# ---------- 页面结构：SSR / FAQ ----------

CSR_SHELL = re.compile(
    r"""(?is)<(?:div|main)[^>]+id=["'](?:root|app|__next)["'][^>]*>\s*</(?:div|main)>"""
)
NOSCRIPT_HINT = re.compile(r"(?is)<noscript[^>]*>.*?(enable|requires?)\s+javascript.*?</noscript>")

FAQ_HEADING = re.compile(
    r"""(?is)<h[2-4][^>]*>(?:(?!</h[2-4]>).)*?(faq|frequently\s+asked|common\s+questions|常见问题|问答)(?:(?!</h[2-4]>).)*?</h[2-4]>"""
)
FAQ_SCHEMA = re.compile(r'"@type"\s*:\s*"FAQPage"')


def check_ssr(html, words):
    """返回 (status, detail, hint)。原始 HTML 里没有正文就是前端渲染空壳。"""
    shell = bool(CSR_SHELL.search(html))
    noscript = bool(NOSCRIPT_HINT.search(html))
    if words >= 150:
        return PASS, f"原始 HTML 可读正文 {words} 词", ""
    if words >= 80:
        return (
            WARN,
            f"原始 HTML 只有 {words} 词" + ("，且有空 CSR 容器" if shell else ""),
            "疑似半前端渲染：把正文改成 SSR/SSG，否则 AI 抓到的内容不完整",
        )
    extra = "，并检测到空 CSR 容器" if shell else ""
    extra += "，noscript 里写着需要启用 JS" if noscript else ""
    return (
        FAIL,
        f"原始 HTML 仅 {words} 词{extra}",
        "前端渲染的站 AI 抓到的是空壳（SKILL.md §2 第 5 条）；改 SSR / SSG 后再复测",
    )


def check_faq(html):
    """返回 (status, detail, hint)。FAQPage 结构化数据 > FAQ 小标题 > 都没有。"""
    has_schema = bool(FAQ_SCHEMA.search(html))
    has_heading = bool(FAQ_HEADING.search(html))
    if has_schema and has_heading:
        return PASS, "FAQPage 结构化数据 + FAQ 小标题都在", ""
    if has_schema:
        return WARN, "有 FAQPage 结构化数据，但没抓到 FAQ 小标题", "补一个人眼可见的 FAQ 区块，结构化数据要与可见内容一致"
    if has_heading:
        return WARN, "有 FAQ 区块，但缺 FAQPage 结构化数据", "给 FAQ 加 JSON-LD（FAQPage），AI 更容易整段引用"
    return (
        FAIL,
        "没有 FAQ 区块（也没 FAQPage 数据）",
        "SKILL.md §2 第 4 条：价格 / 免费额度 / 水印 / 格式 / 批量 / 注册，六个高频问题全答一遍",
    )


# ---------- main ----------


def record_state(path, host, keyword, result):
    """把本次审计写进状态文件；FAIL 清零时自动标记阶段 3 完成，供 geo_status.py 读。"""
    data = {"version": 1, "marks": {}, "audit": {}}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            pass
    data.setdefault("version", 1)
    data.setdefault("marks", {})
    data["domain"] = data.get("domain") or host
    if keyword:
        data["keyword"] = keyword
    fails = [c["item"] for c in result["checks"] if c["status"] == FAIL]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["audit"] = {
        "at": stamp,
        "pass": result["summary"]["pass"],
        "warn": result["summary"]["warn"],
        "fail": result["summary"]["fail"],
        "fails": fails,
    }
    if not fails:
        data["marks"].setdefault("3", {"at": stamp, "note": "geo_audit 全过"})
    else:
        # 之前全过、现在改坏了：把阶段 3 的完成记录撤掉，否则状态会误判成已晋级
        data["marks"].pop("3", None)
    # 页面与基建这两步没法靠人记得标记，跑过审计就等于做过一轮
    for covered in ("1", "2"):
        data["marks"].setdefault(covered, {"at": stamp, "note": "被审计覆盖"})
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[WARN] 状态文件写不进去：{e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="域名或 URL，如 example.com 或 https://example.com")
    ap.add_argument("--keyword", default="", help="主词：AI 联网时真会打的词（常带年份）")
    ap.add_argument("--year", type=int, default=date.today().year, help="Title 应包含的年份，默认今年")
    ap.add_argument("--path", default="/", help="要体检的落地页路径，默认 /（一个需求一个页面时传那个页）")
    ap.add_argument("--sitemap", default="", help="sitemap 地址，默认取 /sitemap.xml")
    ap.add_argument("--key", default="", help="IndexNow 的 key；传了才核对 <key>.txt 是否上线且内容一致")
    ap.add_argument("--proxy", default="", help="可选代理，如 http://127.0.0.1:7892（默认直连）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--state", default=".geo-state.json", help="把结果记进这个状态文件，供 geo_status.py 读")
    ap.add_argument("--no-state", action="store_true", help="不写状态文件")
    args = ap.parse_args()

    t = args.target.strip()
    if not t.startswith("http"):
        t = "https://" + t
    base = t.rstrip("/")
    host = re.sub(r"^https?://", "", base).split("/")[0]
    path = args.path if args.path.startswith("/") else "/" + args.path
    page_url = base + ("/" if path == "/" else path)
    label = "首页" if path == "/" else f"落地页 {path}"

    checks = []

    def add(item, status, detail, hint=""):
        checks.append({"item": item, "status": status, "detail": detail, "hint": hint, "fix": lookup_fix(item)})

    # 1. robots.txt
    r_status, r_headers, r_body, r_err = fetch(base + "/robots.txt", proxy=args.proxy)
    robots = {"status": r_status, "bots": {}, "sitemap": [], "error": r_err}
    if r_status == 200:
        groups = parse_robots(r_body)
        for bot in AI_BOTS:
            rules, mode = pick_rules(groups, bot)
            ok = is_allowed(rules, "/") and is_allowed(rules, "/llms.txt")
            robots["bots"][bot] = {"allowed": ok, "matched_by": mode}
        robots["sitemap"] = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r_body)
        blocked = [b for b, v in robots["bots"].items() if not v["allowed"]]
        if blocked:
            add(
                "robots.txt 放行 AI 爬虫",
                FAIL,
                "被拦：" + ", ".join(blocked),
                "把 assets/templates/robots-ai.txt 片段放到 robots.txt 最前面",
            )
        else:
            add("robots.txt 放行 AI 爬虫", PASS, "9/9 放行")
        if robots["sitemap"]:
            add("robots.txt 有 Sitemap 行", PASS, robots["sitemap"][0])
        else:
            add("robots.txt 有 Sitemap 行", WARN, "没有 Sitemap: 行", "补一行 Sitemap: https://域名/sitemap.xml")
    elif r_status is None:
        add("robots.txt 可访问", FAIL, f"请求失败：{r_err}", "先确认域名解析与证书；本机有代理时加 --proxy")
    elif r_status in (401, 403, 503):
        add(
            "robots.txt 可访问",
            FAIL,
            f"HTTP {r_status}（疑似边缘层拦截，不是 robots 规则问题）",
            "查 Cloudflare 的 Block AI bots / Bot Fight Mode / WAF；这类拦截在 robots.txt 之上，放行也没用",
        )
    else:
        add("robots.txt 可访问", WARN, f"HTTP {r_status}", "没有 robots.txt 时会全站可抓，但建议放一份显式放行")

    # 2. llms.txt / llms-full.txt
    llms = {}
    for name in ("llms.txt", "llms-full.txt"):
        s, h, body, err = fetch(f"{base}/{name}", proxy=args.proxy)
        issues = check_llms(body) if s == 200 else []
        llms[name] = {"status": s, "bytes": len(body.encode("utf-8")), "issues": issues, "error": err}
        if s == 200 and len(body.strip()) > 0:
            if issues:
                add(f"/{name}", WARN, "；".join(issues), "按 assets/templates 的结构改写")
            else:
                add(f"/{name}", PASS, f"{len(body.encode('utf-8'))} bytes，结构正常")
        elif s == 200:
            add(f"/{name}", FAIL, "200 但内容为空")
        else:
            add(
                f"/{name}",
                FAIL if s in (404, None) else WARN,
                f"HTTP {s}" + (f"（{err}）" if err else ""),
                "静态站放到 public/ 或 dist 根目录后重新部署；确认线上真实可访问",
            )

    # 3. 落地页 title / H1 / SSR / FAQ / 归因埋点
    attribution = {"loaded": False}
    h_status, h_headers, html, h_err = fetch(page_url, proxy=args.proxy)
    page = {"url": page_url, "status": h_status, "title": "", "h1": [], "words": 0, "faq": "", "error": h_err}
    if h_status == 200:
        page["title"] = get_title(html)
        page["h1"] = get_h1s(html)
        page["words"] = len(strip_tags(html).split())

        title = page["title"]
        if not title:
            add(f"{label} Title", FAIL, "没抓到 <title>")
        else:
            if len(title) > 65:
                add("Title 长度", WARN, f"{len(title)} 字符（建议 50–60）", "过长会被截断")
            else:
                add("Title 长度", PASS, f"{len(title)} 字符")
            if args.keyword:
                hit, mode = keyword_hit(title, args.keyword)
                add(
                    "Title 对齐主词",
                    PASS if hit else FAIL,
                    ("命中（%s）" % mode) if hit else f"未命中主词「{args.keyword}」",
                    "" if hit else "AI 推荐拿大词流量靠的是 Title/H1 与主词对齐，必须改",
                )
            years = {str(args.year), str(args.year + 1)}
            if any(y in title for y in years):
                add("Title 带年份", PASS, "含 " + "/".join(sorted(years)))
            else:
                add("Title 带年份", WARN, "未含当前或明年年份", "落地页 Title 带年份，对齐输入的主词")

        if len(page["h1"]) == 1:
            add("H1 数量", PASS, "1 个")
        elif not page["h1"]:
            add("H1 数量", FAIL, "没有 H1", "纯 JS 渲染的页面常见；加一个静态 H1")
        else:
            add("H1 数量", WARN, f"{len(page['h1'])} 个", "只保留一个主 H1")

        if page["h1"] and args.keyword:
            joined = " ".join(page["h1"])
            hit, mode = keyword_hit(joined, args.keyword)
            add(
                "H1 对齐主词",
                PASS if hit else FAIL,
                ("命中（%s）" % mode) if hit else f"未命中主词「{args.keyword}」",
                "" if hit else "H1 要与主词一致，这是 AI 判断「这页是干什么的」的主要依据",
            )

        # SSR（§2 第 5 条）
        ssr_status, ssr_detail, ssr_hint = check_ssr(html, page["words"])
        add("后端渲染（SSR）", ssr_status, ssr_detail, ssr_hint)

        # FAQ（§2 第 4 条）
        faq_status, faq_detail, faq_hint = check_faq(html)
        page["faq"] = faq_status
        add("FAQ 结构", faq_status, faq_detail, faq_hint)

        # 自建归因埋点（§3.1 / 13 行动作表第 13 行）
        # 统计工具只会认出 chatgpt.com 一条引荐，其余 GPT 流量并进 direct，
        # 所以必须自己埋点。这里只取证「片段有没有被页面引用」，不判定收数是否正常。
        has_attr = ("geo-source.js" in html) or ("__geoSource" in html)
        if has_attr:
            detail, hint = "落地页引用了 geo-source.js", ""
        else:
            ep = probe_geo_endpoint(page_url, proxy=args.proxy)
            if ep in (400, 403, 415):
                has_attr = True
                detail = f"基线内置 /api/geo-source 端点在线（探测 HTTP {ep}）"
                hint = ""
            else:
                detail = f"落地页没找到 geo-source.js / __geoSource，端点探测 HTTP {ep}"
                hint = "老站跑 geo_attribution.py snippet；基线站确认本次部署含 /api/geo-source 且已跑 0001 迁移"
        attribution["loaded"] = has_attr
        add(
            "归因埋点片段",
            PASS if has_attr else WARN,
            detail,
            hint,
        )
    elif h_status in (401, 403, 503):
        add(f"{label}可访问", FAIL, f"HTTP {h_status}", "疑似边缘拦截")
    else:
        add(f"{label}可访问", FAIL, f"HTTP {h_status}" + (f"（{h_err}）" if h_err else ""))

    # 4. 用 GPTBot 的 UA 复测（判断边缘层是否直接拦 AI 爬虫）
    b_status, b_headers, b_body, b_err = fetch(
        page_url, ua="Mozilla/5.0 AppleWebKit/537.36; compatible; GPTBot/1.1; +https://openai.com/gptbot",
        proxy=args.proxy,
    )
    edge = {"status": b_status, "cf_mitigated": b_headers.get("cf-mitigated", ""), "error": b_err}
    if b_status == 200:
        add("GPTBot UA 抓页面", PASS, "200，边缘层未拦")
    elif b_status in (401, 403, 429, 503):
        add(
            "GPTBot UA 抓页面",
            FAIL,
            f"HTTP {b_status}" + (f"，cf-mitigated={edge['cf_mitigated']}" if edge["cf_mitigated"] else ""),
            "边缘层（Cloudflare Bot Fight Mode / Block AI bots / WAF）在拦，robots 放行无效；去 Dashboard 关掉 AI 爬虫拦截",
        )
    elif b_status is None:
        add("GPTBot UA 抓页面", WARN, f"请求失败：{b_err}", "网络问题，重试或加 --proxy")
    else:
        add("GPTBot UA 抓页面", WARN, f"HTTP {b_status}")

    # 5. sitemap：Bing 收录与 IndexNow 提交都靠它，落地页必须在里面
    sitemap_url = args.sitemap or f"{base}/sitemap.xml"
    s_status, s_headers, s_body, s_err = fetch(sitemap_url, proxy=args.proxy)
    sitemap = {"url": sitemap_url, "status": s_status, "count": 0, "has_page": False, "is_index": False, "error": s_err}
    if s_status == 200:
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", s_body, flags=re.I)
        sitemap["count"] = len(locs)
        sitemap["is_index"] = "<sitemapindex" in s_body.lower()
        norm = page_url.rstrip("/")
        sitemap["has_page"] = any(u.rstrip("/") == norm for u in locs)
        head = s_body.lstrip()[:200].lower()
        if head.startswith(("<!doctype", "<html")):
            add(
                "sitemap.xml",
                FAIL,
                "200 但返回的是 HTML 页面，不是 sitemap（路由兜底了）",
                "把 /sitemap.xml 排除出 SPA 的 catch-all 规则，构建期生成真正的 XML",
            )
        elif sitemap["is_index"]:
            add("sitemap.xml", PASS, f"sitemapindex，{len(locs)} 个子 sitemap（落地页归属在这一层不判定）")
        elif not locs:
            add(
                "sitemap.xml",
                WARN,
                "200 但里面没有 <loc>",
                "sitemap 从数据源生成，别手写；至少包含首页与全部落地页",
            )
        elif sitemap["has_page"]:
            add("sitemap.xml", PASS, f"{len(locs)} 条，落地页在里面")
        else:
            add(
                "sitemap.xml",
                WARN,
                f"{len(locs)} 条，但里面没有 {path}",
                "把落地页加进 sitemap，否则 Bing 抓不到、IndexNow 也推不到它",
            )
    elif s_status is None:
        add("sitemap.xml", WARN, f"请求失败：{s_err}", "网络问题，重试或加 --proxy")
    else:
        add(
            "sitemap.xml",
            FAIL if s_status == 404 else WARN,
            f"HTTP {s_status}",
            "构建期生成 /sitemap.xml，并在 robots.txt 加一行 Sitemap:",
        )

    # 6. IndexNow key 文件（传了 --key 才查）
    indexnow = {"key": args.key, "url": "", "status": None, "match": False, "error": ""}
    if args.key:
        scheme = base.split("://")[0]
        key_url = f"{scheme}://{host}/{args.key.strip()}.txt"
        indexnow["url"] = key_url
        k_status, k_headers, k_body, k_err = fetch(key_url, proxy=args.proxy)
        indexnow.update({"status": k_status, "match": k_body.strip() == args.key.strip(), "error": k_err})
        if k_status == 200 and indexnow["match"]:
            add("IndexNow key 文件", PASS, "200 直出，内容与 key 一致")
        elif k_status == 200:
            add(
                "IndexNow key 文件",
                FAIL,
                "200 但内容与 key 不一致",
                "文件里只放 key 本身：不要引号、空格、注释或 BOM",
            )
        elif k_status in (301, 302, 307, 308):
            add(
                "IndexNow key 文件",
                FAIL,
                f"HTTP {k_status} 重定向",
                "www 与非 www 不一致，或路由把 .txt 吃掉了；IndexNow 要求 200 直出",
            )
        elif k_status is None:
            add("IndexNow key 文件", WARN, f"请求失败：{k_err}", "网络问题，重试或加 --proxy")
        else:
            add(
                "IndexNow key 文件",
                FAIL,
                f"HTTP {k_status}",
                "key 文件没上线：放 public/ 根目录重新部署，或改用 Cloudflare Crawler Hints",
            )
    else:
        add(
            "IndexNow key 文件",
            INFO,
            "未检查（没传 --key）",
            "要核对就加 --key <你的key>；走 Cloudflare Crawler Hints 的站可以跳过",
        )

    failed = [c for c in checks if c["status"] == FAIL]
    result = {
        "host": host,
        "page_url": page_url,
        "keyword": args.keyword,
        "year": args.year,
        "checks": checks,
        "robots": robots,
        "llms": llms,
        "page": page,
        "edge": edge,
        "sitemap": sitemap,
        "indexnow": indexnow,
        "attribution": attribution,
        "summary": {"pass": sum(c["status"] == PASS for c in checks), "warn": sum(c["status"] == WARN for c in checks), "fail": len(failed)},
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\nGEO 体检  {page_url}")
        print("=" * 60)
        for c in checks:
            mark = {PASS: "[PASS]", WARN: "[WARN]", FAIL: "[FAIL]", INFO: "[INFO]"}[c["status"]]
            print(f"{mark} {c['item']}: {c['detail']}")
            if c["hint"]:
                print(f"       → {c['hint']}")
        s = result["summary"]
        print("=" * 60)
        print(f"通过 {s['pass']} / 警告 {s['warn']} / 失败 {s['fail']}")
        if failed:
            print("\n先修这几项（改完重跑同一条命令）：")
            for c in failed:
                print(f"- {c['item']}：{c['detail']}")
                if c["fix"]:
                    print(f"  改这里：{c['fix']}")
        else:
            print("\n基建层面没有硬伤。下一步：Bing 交 sitemap、GSC 加域名属性、IndexNow 首次全量推一遍（见 SKILL.md §3 第 7 条）、按 SKILL.md §6 跑问题库。")

    if not args.no_state:
        record_state(args.state, host, args.keyword, result)
        if not args.json:
            print(f"\n状态已记到 {args.state}。跑 python scripts/geo_status.py 看下一步。")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
