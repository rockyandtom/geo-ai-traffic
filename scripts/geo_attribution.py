#!/usr/bin/env python3
"""GEO 自建归因埋点 + 按 GPT 来源重配付费墙（13 行动作表第 12 / 13 行）。

为什么这两件事必须放在一个脚本里：
    统计工具只会识别出 chatgpt.com 一个引荐来源，大量 GPT 流量被并进
    direct（出处：codex-resets.com 流量结构 + Frio 2026-10-11）。不自己
    埋点，就永远算不清 GPT 到底给了多少量；而「按 GPT 流量重配付费墙」
    的前提，恰恰是能先把这批来源认出来。先埋点，再分流，是一条链。

产物（默认写在当前项目目录，前端文件必须随构建上线）：
    geo-source.js             前端来源识别 + 上报片段，原生 JS 无依赖
    geo-source-server.md      服务端接收端点、字段说明、注意事项
    gpt-paywall.config.json   按来源分流的付费墙配置（不给免费额度 + 三档）
    geo-source-log.csv       埋点导出的表头（report 读它）

子命令：
    python geo_attribution.py snippet
    python geo_attribution.py paywall
    python geo_attribution.py report --csv geo-source-log.csv
    python geo_attribution.py check --domain example.com

纪律：
    1. 脚本只生成片段与配置，不替你接支付、不替你决定价格。
    2. referrer 为空时不能判定「不是 AI」，只能标 direct_suspect_ai；
       这条不能省，省了就又变成「只认 chatgpt.com」。
    3. check 是取证工具，不是验收判官：它只报告线上有没有加载到片段，
       不许拿它的退出码当「归因做完了」的结论。
"""

import argparse
import csv
import json
import os
import re
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date

SNIPPET_NAME = "geo-source.js"
SERVER_DOC = "geo-source-server.md"
PAYWALL_NAME = "gpt-paywall.config.json"
LOG_NAME = "geo-source-log.csv"
ENDPOINT = "/api/geo-source"
MARKER = "__geoSource"

# 顺序即优先级；命中第一个就停。chat.openai.com / bing.com/chat 是老入口，一并留着。
AI_HOSTS = [
    ("chatgpt", r"chatgpt\.com|chat\.openai\.com|openai\.com"),
    ("gemini", r"gemini\.google\.com|bard\.google\.com"),
    ("perplexity", r"perplexity\.ai"),
    ("claude", r"claude\.ai"),
    ("copilot", r"copilot\.microsoft\.com|bing\.com/chat"),
    ("poe", r"poe\.com"),
    ("you", r"you\.com"),
]

JS_TEMPLATE = r"""/* geo-source.js —— GEO 自建来源归因（无依赖，放在 public/ 并随构建上线）
 * 由 geo-ai-traffic / geo_attribution.py snippet 生成。改 AI_HOSTS 后重新生成会覆盖，别手改这里。
 *
 * 判定优先级：URL 显式参数 > document.referrer 匹配 AI 域名 > direct。
 * 关键：referrer 为空不等于「不是 AI」，AI App 内打开经常不带 referrer，
 *      这类流量标成 direct_suspect_ai，单独统计，绝不并入确定的 AI 量。
 */
(function () {
  'use strict';
  var ENDPOINT = '/api/geo-source';
  var COOKIE_DAYS = 90;
  var AI_HOSTS = __AI_HOSTS__;
  var PARAM_KEYS = ['utm_source', 'ref', 'ai_source', 'source'];
  var KNOWN = __KNOWN__;
  var ALIAS = { gpt: 'chatgpt', chatgpt: 'chatgpt', openai: 'chatgpt', gemini: 'gemini',
                bard: 'gemini', perplexity: 'perplexity', claude: 'claude',
                copilot: 'copilot', bing: 'copilot', poe: 'poe', you: 'you' };

  function norm(v) {
    v = String(v || '').toLowerCase().trim();
    return ALIAS[v] || (KNOWN.indexOf(v) >= 0 ? v : '');
  }

  function classify() {
    var q = new URLSearchParams(location.search);
    for (var i = 0; i < PARAM_KEYS.length; i++) {
      var hit = norm(q.get(PARAM_KEYS[i]));
      if (hit) return { source: hit, confidence: 'explicit', landing: location.pathname };
    }
    var ref = document.referrer || '';
    for (var j = 0; j < AI_HOSTS.length; j++) {
      if (AI_HOSTS[j][1].test(ref)) {
        return { source: AI_HOSTS[j][0], confidence: 'referrer', landing: location.pathname };
      }
    }
    // 自家站内跳转变不出来 AI 来源；外站但非 AI 的 referrer 也要与「无 referrer」分开。
    return {
      source: 'direct',
      confidence: ref ? 'direct_other' : 'direct_suspect_ai',
      landing: location.pathname
    };
  }

  function setCookie(name, value, days) {
    var d = new Date();
    d.setTime(d.getTime() + days * 86400000);
    document.cookie = name + '=' + encodeURIComponent(value) +
      ';expires=' + d.toUTCString() + ';path=/;SameSite=Lax';
  }

  function send(payload) {
    try {
      var blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      if (navigator.sendBeacon) { navigator.sendBeacon(ENDPOINT, blob); return; }
    } catch (e) { /* 走下面的 fetch 兜底 */ }
    try {
      fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), keepalive: true });
    } catch (e) { /* 上报失败不能影响页面 */ }
  }

  var hit = classify();
  // 首次来源为准：用户在站内跳转后别把来源覆盖成 direct。
  if (!sessionStorage.getItem('geo_source')) {
    sessionStorage.setItem('geo_source', hit.source);
    sessionStorage.setItem('geo_confidence', hit.confidence);
    setCookie('geo_source', hit.source, COOKIE_DAYS);
    setCookie('geo_confidence', hit.confidence, COOKIE_DAYS);
  }
  var state = {
    source: sessionStorage.getItem('geo_source') || hit.source,
    confidence: sessionStorage.getItem('geo_confidence') || hit.confidence,
    landing: hit.landing,
    path: location.pathname,
    ts: new Date().toISOString()
  };
  window.__MARKER__ = state;
  send(Object.assign({ event: 'visit' }, state));

  // 注册 / 付费节点调用：window.__geoTrack('signup') / window.__geoTrack('purchase', {plan:'pack3', amount:19.9})
  window.__geoTrack = function (event, extra) {
    var payload = Object.assign({ event: event }, window.__MARKER__ || {}, extra || {});
    payload.ts = new Date().toISOString();
    send(payload);
    return payload;
  };
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest && e.target.closest('[data-geo-event]');
    if (el) window.__geoTrack(el.getAttribute('data-geo-event'), {
      plan: el.getAttribute('data-geo-plan') || '',
      amount: el.getAttribute('data-geo-amount') || ''
    });
  }, true);
})();
"""

SERVER_DOC_TEMPLATE = """# geo-source 服务端接收说明

前端 `geo-source.js` 会把来源与事件 POST 到 `{endpoint}`。这一层必须自己写，
统计工具（GA4 / Plausible / SimilarWeb）只会认出 `chatgpt.com` 一条引荐，
大量 GPT 流量被并进 direct，靠它们算不清 GPT 给了多少量。

## 字段

1. `source` —— `chatgpt` / `gemini` / `perplexity` / `claude` / `copilot` / `poe` / `you` / `direct`。
2. `confidence` —— `explicit`（URL 带 utm_source 等参数）/ `referrer`（referrer 命中 AI 域名）/
   `direct_other`（有 referrer 但不是 AI）/ `direct_suspect_ai`（referrer 为空，疑似 AI App 内打开）。
3. `landing` —— 首次落地路径；`path` —— 当前路径；`ts` —— ISO 时间。
4. `event` —— `visit` / `signup` / `purchase`；付费事件另带 `plan` 与 `amount`。
5. `session_id` 由服务端按 cookie 或会话生成，前端不要自己造可识别个人身份的 ID。

## 三条必须守的

1. **`direct_suspect_ai` 不能当成确定的 AI 流量**，也不能直接丢掉。它是「统计工具看不见的那部分」的
   上界线索：报数时和确定的 AI 来源分两栏写，不要合成一个「GPT 流量」总数。
2. **首次来源为准**，站内跳转不覆盖。前端已用 sessionStorage + 90 天 first-party cookie 处理，
   服务端落库时同样别用最后一次 visit 的来源去覆盖注册/付费事件的来源。
3. **上报失败不影响页面**（前端已用 sendBeacon + fetch keepalive 兜底）；端点要接受
   `Content-Type: application/json` 的 beacon 请求，并返回 204。

## 导出给 report 用

把埋点表导出成 `geo-source-log.csv`，表头固定：

    ts,session_id,source,confidence,landing,event,plan,amount

跑 `python geo_attribution.py report --csv geo-source-log.csv` 出：各来源会话/注册/付费数、
注册到付费转化率、`chatgpt.com` 单条 referrer 能认出的量 vs 自埋点认出的 AI 总量、
`direct_suspect_ai` 的数量与占比。

## 上线前核对

`python geo_attribution.py check --domain <域名>` 会看 `/geo-source.js` 是否 200、
首页 HTML 有没有引用它。它是取证工具，只报告「线上有没有加载到」，不代替人工确认
端点是否真的在收数。
"""

PAYWALL_NOTE = (
    "社群口径（哥飞 2026-10-11）：GPT 来的流量带着明确购买意图，不要给免费额度，直接告知需付费；"
    "短期热点主推 9.9 单次 / 19.9 三次 / 29.9 五次；注册到付费综合约 8%。"
    "这些数字是实践观测的起点，不是本机实测，也不是必须照抄的定价。"
)

# 我们的基线模板 v1.3.0 起把这两块代码开箱内置。检测到就不生成第二份，
# 否则同一个站点会同时存在「模板预置」和「技能生成」两套实现，改一处漏一处。
BASELINE_FILES = {
    "snippet": [
        "src/lib/geo-source.ts",
        "src/components/analytics/geo-source.tsx",
        "src/routes/api/geo-source.ts",
    ],
    "paywall": ["src/config/geo-paywall.ts"],
}


def detect_baseline(out="."):
    """返回 {类别: 已存在的基线文件列表}；空列表表示这是需要技能生成片段的老站。"""
    return {
        kind: [f for f in files if os.path.isfile(os.path.join(out, f))]
        for kind, files in BASELINE_FILES.items()
    }


def probe_endpoint(url, timeout=10):
    """用非法 Content-Type 探测端点是否存在，不写任何数据、不产生埋点行。

    基线端点对 text/plain 返回 415；老站未部署端点时是 404 / 405。
    """
    handlers = [
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    ]
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "Content-Type": "text/plain",
            "User-Agent": "geo-attribution-probe/1.0",
        },
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def ai_hosts_js():
    rows = []
    for name, pattern in AI_HOSTS:
        # JS 正则字面量里 "/" 必须转义，否则 /bing\.com/chat/i 会被解析成
        # 正则提前结束 + 非法标志，整段脚本加载即报错（实测踩过）。
        safe = pattern.replace("/", r"\/")
        rows.append(f"    ['{name}', /{safe}/i]")
    return "[\n" + ",\n".join(rows) + "\n  ]"


def cmd_snippet(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    baseline = detect_baseline(out)["snippet"]
    if baseline:
        csv_path = os.path.join(out, LOG_NAME)
        if not os.path.exists(csv_path):
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                f.write("ts,session_id,source,confidence,landing,event,plan,amount\n")
        print("检测到基线内置归因（模板 v1.3.0+），不生成 geo-source.js，避免同一功能两份代码：")
        for rel in baseline:
            print(f"  {os.path.join(out, rel)}")
        print()
        print("上线当天三件事：")
        print("1. 确认 drizzle/0001_geo_attribution.sql 已随 pnpm db:migrate 执行（geo_source_event 表 + user 两列）。")
        print("2. 后台打开 /api/admin/geo-source-export 下载 geo-source-log.csv，确认有 visit 行。")
        print("3. 验完来源后把 src/config/geo-paywall.ts 的 GEO_PAYWALL.enabled 改成 true（默认 false）。")
        print()
        print(f"{csv_path} 表头已保留；也可直接用后台导出的 CSV 跑 report，八列完全对齐。")
        print("口径不变：referrer 为空标 direct_suspect_ai，疑似量不并入确定的 AI 来源。")
        return 0

    js = (JS_TEMPLATE
          .replace("__AI_HOSTS__", ai_hosts_js())
          .replace("__KNOWN__", json.dumps([n for n, _ in AI_HOSTS]))
          .replace("__MARKER__", MARKER))
    js_path = os.path.join(out, SNIPPET_NAME)
    doc_path = os.path.join(out, SERVER_DOC)
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(js)
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(SERVER_DOC_TEMPLATE.format(endpoint=ENDPOINT))

    csv_path = os.path.join(out, LOG_NAME)
    if not os.path.exists(csv_path):
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            f.write("ts,session_id,source,confidence,landing,event,plan,amount\n")

    print("自建归因埋点片段已生成（13 行动作表第 13 行）：")
    print(f"  {js_path}")
    print(f"  {doc_path}")
    print(f"  {csv_path}（导出表头，report 读它）")
    public_dir = os.path.join(out, "public")
    if os.path.isdir(public_dir):
        target = os.path.join(public_dir, SNIPPET_NAME)
        shutil.copyfile(js_path, target)
        print(f"  检测到 public/ 目录，已同步一份到 {target}（说明文档与 CSV 表头留在项目根，不放 public）")
    else:
        print(f"  当前目录没有 public/，请把 {SNIPPET_NAME} 手动放进静态资源目录后重新部署。")
    print()
    print("接下来三件事必须做，脚本替不了：")
    print(f"1. 确认 public/{SNIPPET_NAME} 已随构建上线，并在所有落地页用 <script src=\"/{SNIPPET_NAME}\" defer></script> 引用。")
    print(f"2. 按 {SERVER_DOC} 写 {ENDPOINT} 接收端点，注册与付费节点调用 __geoTrack('signup') / __geoTrack('purchase', {{plan, amount}})，或给按钮加 data-geo-event 属性。")
    print("3. 上线后用 check --domain <域名> 核对片段真的加载了，再把埋点表导出成 geo-source-log.csv 跑 report。")
    print()
    print("口径提醒：referrer 为空会被标成 direct_suspect_ai，它是疑似量，不能并进确定的 AI 来源。")
    return 0


def cmd_paywall(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, PAYWALL_NAME)

    baseline = detect_baseline(out)["paywall"]
    if baseline:
        print("检测到基线内置付费墙分流（模板 v1.3.0+），不生成 gpt-paywall.config.json：")
        for rel in baseline:
            print(f"  {os.path.join(out, rel)}")
        print()
        print("要改的三处，别再生成第二份配置：")
        print("1. 开关：src/config/geo-paywall.ts → GEO_PAYWALL.enabled（默认 false，验完线上归因再打开）。")
        print("2. 价格与档位：src/config/pricing.ts，模板不写死价格，也不替你定价格。")
        print("3. 注册钩子 src/core/auth/index.ts 已把首次来源传给 grantForNewUser()，不要再改一遍。")
        print()
        print("规则不变：只有确认的 AI 来源走 0 免费额度；direct_suspect_ai 走正常额度。")
        return 0

    cfg = {
        "_note": PAYWALL_NOTE,
        "_prerequisite": (
            "必须先跑 geo_attribution.py snippet 并把埋点上线；认不出来源就没有「按 GPT 流量重配」可言。"
            "来源取自 window.__geoSource.source / 服务端 session 里的首次来源。"
        ),
        "match_sources": ["chatgpt", "gemini", "perplexity", "claude", "copilot", "poe", "you"],
        "free_credits": 0,
        "plans": [
            {"id": "single", "price": 9.9, "credits": 1, "currency": "USD", "label": "单次"},
            {"id": "pack3", "price": 19.9, "credits": 3, "currency": "USD", "label": "3 次"},
            {"id": "pack5", "price": 29.9, "credits": 5, "currency": "USD", "label": "5 次"},
        ],
        "fallback": {
            "rule": "识别不到 AI 来源时走站点默认配置，不要对 direct_suspect_ai 直接关掉免费额度",
            "reason": "direct_suspect_ai 只是疑似，误伤普通 direct 流量会把转化打没，而归因精度不足以支撑这个判断",
        },
        "events": ["signup", "purchase"],
        "benchmark": {
            "signup_to_paid": 0.08,
            "source": "哥飞 2026-10-11 社群观测，非本机实测；普通 AI 视频站 2% 已算不错",
        },
        "status": "template",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print("按 GPT 来源重配的付费墙配置已生成（13 行动作表第 12 行）：")
    print(f"  {path}")
    print()
    print(PAYWALL_NOTE)
    print()
    print("配置里的三条落地规则：")
    print("1. 只有 match_sources 命中的会话才走 free_credits=0 与三档定价；来源取自埋点的首次来源，不取最后一次 visit。")
    print("2. direct_suspect_ai 走 fallback，不关免费额度 —— 它是疑似量，不能拿它做确定性分流。")
    print("3. 注册和付费都要带 plan / amount 上报，才能用 report 算注册到付费转化率，和 8% 这个参考值对比。")
    print()
    print("这是配置模板，不是支付接入。价格、档位、币种按自己站改，改完把 status 从 template 改成 active。")
    return 0


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    need = {"source", "confidence", "event", "session_id"}
    if not rows:
        return []
    missing = need - set(rows[0].keys())
    if missing:
        raise ValueError(f"CSV 缺列：{'、'.join(sorted(missing))}")
    return rows


def cmd_report(args):
    if not os.path.exists(args.csv):
        print(f"[FAIL] 找不到 {args.csv}。先用 snippet 生成表头，把埋点数据导进来。")
        return 2
    try:
        rows = read_rows(args.csv)
    except (OSError, ValueError) as e:
        print(f"[FAIL] 读不了：{e}")
        return 2
    if not rows:
        print("表里没有数据行。没有真实埋点数据就不出结论，这里不会替你编数。")
        return 0

    by_source = defaultdict(lambda: {"visit": set(), "signup": set(), "purchase": set(), "amount": 0.0})
    suspects = set()
    for r in rows:
        src = (r.get("source") or "unknown").strip() or "unknown"
        ev = (r.get("event") or "").strip()
        sid = (r.get("session_id") or "").strip()
        rec = by_source[src]
        if ev in rec:
            rec[ev].add(sid or r.get("ts", "") + src + ev)
        if ev == "purchase":
            try:
                rec["amount"] += float(r.get("amount") or 0)
            except ValueError:
                pass
        if (r.get("confidence") or "").strip() == "direct_suspect_ai":
            suspects.add(sid or r.get("ts", "") + src)

    ai_names = [n for n, _ in AI_HOSTS]
    ai_visits = sum(len(by_source[n]["visit"]) for n in ai_names)
    chatgpt_visits = len(by_source["chatgpt"]["visit"])
    other_ai = ai_visits - chatgpt_visits
    total_visits = sum(len(v["visit"]) for v in by_source.values())
    total_signup = sum(len(v["signup"]) for v in by_source.values())
    total_purchase = sum(len(v["purchase"]) for v in by_source.values())
    rate = (total_purchase / total_signup) if total_signup else 0.0

    print(f"归因报表：{args.csv} · {len(rows)} 条事件 · {total_visits} 次访问 · {date.today().isoformat()}")
    print()
    print("按来源（访问 / 注册 / 付费 / 金额）：")
    for src in sorted(by_source, key=lambda s: -len(by_source[s]["visit"])):
        v = by_source[src]
        if not (v["visit"] or v["signup"] or v["purchase"]):
            continue
        print(f"  {src}：{len(v['visit'])} / {len(v['signup'])} / {len(v['purchase'])} / {v['amount']:.2f}")
    print()
    print("这是第 13 行那条动作要算的差额：")
    print(f"  统计工具只能认出 chatgpt.com 的量：{chatgpt_visits} 次访问")
    print(f"  自埋点另外认出的 AI 来源：{other_ai} 次访问（gemini / perplexity / claude / copilot 等）")
    print(f"  referrer 为空的疑似 AI（direct_suspect_ai）：{len(suspects)} 个会话，占全部访问 {len(suspects) / total_visits * 100:.1f}%" if total_visits else "  疑似会话：0")
    print("  疑似量单独列，不并入确定量；它和爬虫、直接输入、书签混在一起，只能当上界线索。")
    print()
    print(f"注册到付费：{total_signup} 注册 / {total_purchase} 付费 = {rate * 100:.1f}%")
    print(f"对照参考值 8%（哥飞 2026-10-11 社群观测，非本机实测）：{'高于' if rate > 0.08 else '低于'}参考值，差 {(rate - 0.08) * 100:+.1f} 个百分点。")
    if rate < 0.08:
        print("转化低于参考值：先按 SKILL.md §3.1 查埋点是不是漏了注册 / 付费事件，再查免费额度是不是给多了，别一上来改文案。")
    else:
        print("转化达到或超过参考值时，先抽查 purchase 有没有重复上报，再谈放大流量。")
    return 0


def fetch(url, timeout=15):
    handlers = [urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context())]
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; geo-attribution-check/1.0)"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(300_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def cmd_check(args):
    domain = (args.domain or "").strip().replace("https://", "").replace("http://", "").rstrip("/")
    if not domain:
        print("[FAIL] 要传 --domain")
        return 2
    base = "https://" + domain

    if detect_baseline(".")["snippet"]:
        ep = probe_endpoint(base + ENDPOINT)
        ok = ep in (400, 403, 415)
        print(f"归因埋点线上核对（基线内置形态）：{base}（{date.today().isoformat()}）")
        print(f"  POST {ENDPOINT} 用非法 Content-Type 探测 → HTTP {ep}（不会写入任何埋点数据）")
        print(f"  端点{'已上线' if ok else '没上线或没被这一版部署带上'}")
        if ok:
            print("  下一步：后台打开 /api/admin/geo-source-export 下载 CSV，确认真的有 visit 行；这一步脚本查不了。")
        else:
            print("  检查 drizzle/0001_geo_attribution.sql 是否已随 db:migrate 执行，以及本次部署是否是含该端点的版本。")
        return 0 if ok else 1

    js_status, js_body = fetch(base + "/" + SNIPPET_NAME)
    home_status, home_body = fetch(base + args.path)
    has_marker = MARKER in js_body and "sendBeacon" in js_body
    has_ref = SNIPPET_NAME in home_body

    print(f"归因埋点线上核对：{base}（{date.today().isoformat()}）")
    print(f"  /{SNIPPET_NAME} 返回 {js_status}，正文 {len(js_body)} 字符，含 {MARKER} 标记：{'是' if has_marker else '否'}")
    print(f"  落地页 {args.path} 返回 {home_status}，HTML 里引用了 {SNIPPET_NAME}：{'是' if has_ref else '否'}")
    if js_status == 200 and has_marker and has_ref:
        print("  证据齐了：片段在线、首页有引用。下一步是确认端点真的在收数，这一步脚本查不了。")
    else:
        print("  片段没上线或没被引用：把 geo-source.js 放进 public 并随构建发布，在落地页模板加 script 引用后重跑。")
    return 0 if (js_status == 200 and has_marker and has_ref) else 1


def main():
    ap = argparse.ArgumentParser(description="GEO 自建归因埋点 + 按 GPT 来源重配付费墙")
    sub = ap.add_subparsers(dest="cmd")

    p1 = sub.add_parser("snippet", help="生成前端埋点片段、服务端说明与导出表头")
    p1.add_argument("--out", default=".", help="输出目录，默认当前目录（一般是站点项目根）")
    p1.set_defaults(func=cmd_snippet)

    p2 = sub.add_parser("paywall", help="生成按来源分流的付费墙配置")
    p2.add_argument("--out", default=".", help="输出目录")
    p2.set_defaults(func=cmd_paywall)

    p3 = sub.add_parser("report", help="汇总埋点数据：来源、转化、direct 疑似量")
    p3.add_argument("--csv", default=LOG_NAME, help=f"埋点导出表，默认 {LOG_NAME}")
    p3.set_defaults(func=cmd_report)

    p4 = sub.add_parser("check", help="线上核对埋点片段是否真的加载了（取证，不是验收）")
    p4.add_argument("--domain", required=True)
    p4.add_argument("--path", default="/", help="落地页路径")
    p4.set_defaults(func=cmd_check)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
