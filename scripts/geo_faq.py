#!/usr/bin/env python3
"""反推问题清单 → 汇总 → 写回 FAQ（三步法第一步的完整可执行版）。

出处：13 行动作表第 7 条 / 三步法 ①（2026-09-09）：
「问 ChatGPT：假如你是用户想找 XX 工具，会怎么提问？Claude、Gemini 同理，汇总成问题清单。」
原来技能里只有 prompt_pack.py --stage reverse 的一条单模型问句，
没有「三个模型」「汇总成清单」「写回 FAQ」这三件事，状态机里也没有挂点。

本脚本把这条链路做成四个产物文件，全部写在当前工作目录（站点项目里）：

    faq-questions.csv    唯一的问题清单（可人工填答案）
    faq-raw-*.txt        三个模型回答全文（你贴回来，不要伪造）
    faq-block.html       可见 FAQ 区块 + FAQPage JSON-LD，直接贴进落地页
    faq-block.md         同一份内容的 Markdown 版

命令：
    python geo_faq.py seed                        # 不依赖 AI，先给一份种子清单
    python geo_faq.py ask --category "XX 工具"    # 三模型反推提问包，纯段落可复制
    python geo_faq.py collect --dir .             # 汇总三份回答，去重、归类、追加进清单
    python geo_faq.py list                        # 随时把问题清单打印出来
    python geo_faq.py render                      # 填完答案后生成页面 FAQ 区块

纪律：清单内容必须来自三个模型的真实回答，或 seed 的固定六问。
不许凭空编造「AI 给出的问句」，也不许给没答案的条目编答案。
输出一律普通段落，不用代码块、不用表格。
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date

CSV_FILE = "faq-questions.csv"
HTML_FILE = "faq-block.html"
MD_FILE = "faq-block.md"
FIELDS = ["qid", "question", "source", "bucket", "status", "answer"]
SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))

BUCKETS = [
    ("price", "价格 / 收费"),
    ("free", "免费额度"),
    ("watermark", "水印"),
    ("format", "格式与导出"),
    ("bulk", "批量与上限"),
    ("signup", "注册与账号"),
    ("other", "其他真实问法"),
]

BUCKET_LABEL = dict(BUCKETS)

# 顺序有意：先判专属词，再判宽泛词
BUCKET_RULES = [
    ("watermark", r"水印|watermark"),
    ("signup", r"注册|登录|绑卡|账号|sign\s?up|signup|login|account"),
    ("free", r"免费|不花钱|白嫖|额度|free|quota|without paying|no cost|no charge"),
    ("price", r"价格|多少钱|收费|付费|买断|订阅|套餐|加钱|另收|price|pricing|cost|paywall|paid|pay for|subscription"),
    ("bulk", r"批量|一次.*(多|几个)|上限|bulk|batch"),
    ("format", r"格式|导出|分辨率|尺寸|format|export|png|jpg|pdf|mp4|svg"),
]

SEED_QUESTIONS = [
    ("price", "这个工具多少钱？有没有一次性买断的选项？"),
    ("free", "免费额度有多少？不花钱能做到什么程度？"),
    ("watermark", "导出会有水印吗？要怎么去掉？"),
    ("format", "支持导出哪些格式？能导出高清大图吗？"),
    ("bulk", "能一次批量处理多个吗？一次最多几个？"),
    ("signup", "必须注册才能用吗？要不要绑卡？"),
    ("other", "有没有不用下载软件、直接在网页里就能用的？"),
    ("other", "手机上能用吗？"),
    ("other", "做出来的东西能商用吗？版权归谁？"),
    ("other", "上传的文件会被保存吗？隐私怎么说的？"),
]


# ---------- 提问包（唯一来源，prompt_pack.py 也 import 这里） ----------

def main_question(v, lang="zh"):
    """三步法第一步的那句反提问。三个模型问同一句，差异正是要收集的。"""
    c = (v.get("category") or v.get("keyword") or "这类工具").strip()
    n = v.get("n", 15)
    if lang == "en":
        if re.search(r"(tools?|websites?|apps?|services?|generators?|software|platforms?)$", c, re.I):
            art = "" if re.search(r"s$", c) else ("an " if c[0] in "AEIOU" else "a ")
            need = f"looking for {art}{c}"
        else:
            need = f"looking for a tool that can {c}"
        return (
            f"If you were a real user {need}, how would you ask an AI? "
            f"Give me {n} questions real users would actually type, covering different scenarios and phrasings. "
            "Avoid industry jargon. Put a short scene label in front of each question (free / watermark / "
            "bulk / mobile / signup / price / export format / comparison). Output the question list only, "
            "no explanations and no answers."
        )
    sep = " " if re.match(r"^[A-Za-z0-9]", c) else ""
    need = (f"想找{sep}{c}" if re.search(r"(工具|网站|软件|平台|服务|应用|生成器)$", c)
            else f"想找能做 {c} 的工具")
    return (
        f"假如你是一个真实用户，{need}，你会怎么向 AI 提问？"
        f"请给我 {n} 个真实用户会打出来的问句，覆盖不同场景和说法，不要用行业术语。"
        "每一条前面标一个场景标签（免费 / 无水印 / 批量 / 手机端 / 要不要注册 / 价格 / 导出格式 / 和同类比），"
        "只输出问句清单，不要解释，也不要给答案。"
    )


def followup_question(lang="zh"):
    """问完主句后的追问：让它自己按 FAQ 板块归类，方便和脚本 collect 的结果对账。"""
    if lang == "en":
        return (
            "Now group the questions you just gave into at most six buckets by the problem the user is "
            "actually trying to solve. Keep the three most representative questions in each bucket, and "
            "mark which ones are about price, free quota, watermark, export format, bulk limits, and signup."
        )
    return (
        "把你刚才给的这些问句，按「用户真正想解决的问题」归成六类以内，每类保留最有代表性的三条，"
        "并标出哪些是问价格、免费额度、水印、导出格式、批量上限、要不要注册的。"
    )


MODELS = [
    ("chatgpt", "ChatGPT"),
    ("claude", "Claude"),
    ("gemini", "Gemini"),
]


def ask_output(v, lang="zh"):
    lines = []
    q = main_question(v, lang)
    f = followup_question(lang)
    lines.append(f"反推问题清单提问包  |  品类：{(v.get('category') or v.get('keyword') or '这类工具').strip()}  |  每家要 {v.get('n', 15)} 条")
    lines.append("同一句问三个模型，各开一个新会话；三家的差异正是要收集的东西。回答全文别改，存成 faq-raw-<模型名>.txt。")
    for i, (key, label) in enumerate(MODELS, 1):
        lines.append("")
        lines.append(f"第 {i} 份：在 {label} 里问下面这句")
        lines.append("")
        lines.append(q)
        lines.append("")
        lines.append(f"问完在同一会话补这句（{label}）")
        lines.append("")
        lines.append(f)
    lines.append("")
    lines.append(
        "三份回答全文分别存成 faq-raw-chatgpt.txt、faq-raw-claude.txt、faq-raw-gemini.txt，放在项目根目录。"
    )
    lines.append(
        f"然后跑 python3 {SKILL_SCRIPTS}/geo_faq.py collect --dir . 自动去重、归类、追加进 {CSV_FILE}；"
        "汇总不靠人，也不用再问一次 AI。"
    )
    lines.append("存证：回答全文 + 整屏截图；同一句在三个模型里都用未登录的临时会话，别用带产品记忆的账号。")
    return "\n".join(lines)


# ---------- CSV ----------

def read_csv(path=CSV_FILE):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(rows, path=CSV_FILE):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def norm(q):
    return re.sub(r"[\s\W_]+", "", q.lower())


def classify(q):
    for bucket, pattern in BUCKET_RULES:
        if re.search(pattern, q, flags=re.I):
            return bucket
    return "other"


def next_qid(rows):
    mx = 0
    for r in rows:
        m = re.match(r"F(\d+)", r.get("qid", ""))
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


# ---------- 解析三个模型的回答 ----------

NUM_PREFIX = re.compile(r"^\s*(?:\(?\d{1,3}\)?[\.、\)）:：]\s*|[-*•·>]\s*|\d{1,3}\s+)")
NOISE = re.compile(r"以下是|下面是|共\s*\d+\s*(个|条)|当然可以|好的，|希望|需要我|我可以帮你|作为(一个|一名)|请注意|总结一|说明[:：]|no problem|here are|sure[,!]", re.I)
ASK_START = re.compile(r"^(有没有|能不能|可不可以|会不会|要不要|是不是|怎么|怎样|如何|什么|哪个|哪款|哪些|多少|几|支持|能用|可以|求|想找|找|is there|can i|how|what|which|does|do i|are there|any |where|why)", re.I)


def extract_questions(text):
    """从一份回答里抽出问句。宁可少抽，不把说明文字当问题。"""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = NUM_PREFIX.sub("", line)
        line = re.sub(r"^\*\*|\*\*$", "", line).strip()
        line = re.sub(r"^[\"'`]|[\"'`]$", "", line).strip()
        # 场景标签：允许「免费 / 免费吗？」这种前缀，去掉方括号与短标签
        line = re.sub(r"^\[[^\]]{1,12}\]\s*", "", line)
        line = re.sub(r"^\*\*[^*]{1,12}\*\*\s*[:：]?\s*", "", line)
        # 模型常给「免费 / 有没有…」这种短场景标签，剥掉只留问句
        line = re.sub(r"^[\u4e00-\u9fa5A-Za-z ]{1,12}\s*[/／]\s*", "", line)
        if len(line) < 6 or len(line) > 140:
            continue
        if NOISE.search(line):
            continue
        is_q = ("?" in line or "？" in line or ASK_START.match(line)
                or line.endswith(("吗", "呢", "吧")))
        if not is_q:
            continue
        out.append(line)
    return out


def collect_from_files(pairs):
    """pairs: [(model, path), ...] → 新增条目列表 + 统计"""
    rows = read_csv()
    seen = {norm(r["question"]) for r in rows}
    added, dup, skipped = [], 0, 0
    n = next_qid(rows)
    for model, path in pairs:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"[FAIL] 读不了 {path}：{e}")
            sys.exit(2)
        qs = extract_questions(text)
        if not qs:
            skipped += 1
            print(f"[WARN] {os.path.basename(path)} 里没抽到问句，检查是不是只存了摘要没存全文")
        for q in qs:
            key = norm(q)
            if key in seen:
                dup += 1
                continue
            seen.add(key)
            n += 1
            added.append({
                "qid": f"F{n:03d}", "question": q, "source": model,
                "bucket": classify(q), "status": "todo", "answer": "",
            })
    return rows, added, dup, skipped


def print_coverage(rows):
    have = {r["bucket"] for r in rows}
    filled = {r["bucket"] for r in rows if (r.get("answer") or "").strip()}
    todo = [r for r in rows if not (r.get("answer") or "").strip()]
    missing_q = [label for key, label in BUCKETS if key != "other" and key not in have]
    missing_a = [label for key, label in BUCKETS if key != "other" and key not in filled]
    print(f"清单共 {len(rows)} 条，已填答案 {len(rows) - len(todo)} 条，待填 {len(todo)} 条。")
    print("问题覆盖（六类问句收齐没）：" + ("齐" if not missing_q else "还缺 " + "、".join(missing_q)))
    print("答案覆盖（六类答了没）：" + ("齐" if not missing_a else "还缺 " + "、".join(missing_a)))
    return todo


# ---------- 子命令 ----------

def cmd_seed(args):
    rows = read_csv()
    if rows and not args.force:
        print(f"{CSV_FILE} 已经有 {len(rows)} 条，不覆盖。要重建加 --force（会丢掉已填的答案）。")
        return 1
    rows = []
    for i, (bucket, q) in enumerate(SEED_QUESTIONS, 1):
        rows.append({
            "qid": f"F{i:03d}", "question": q, "source": "seed",
            "bucket": bucket, "status": "todo", "answer": "",
        })
    write_csv(rows)
    print(f"[OK] 已写 {CSV_FILE}：{len(rows)} 条种子问题（FAQ 六问 + 四条真实口语问法）")
    print("种子清单不依赖 AI，可以先拿去写回 FAQ；三模型反推的问句用 collect 追加进来。")
    print("")
    print_questions(rows)
    print("")
    print(f"下一步：跑 python3 {SKILL_SCRIPTS}/geo_faq.py ask --category \"<品类>\" 拿三模型提问包。")
    return 0


def cmd_ask(args):
    v = {"category": args.category, "keyword": args.keyword, "n": args.n}
    print(ask_output(v, args.lang))
    return 0


def cmd_collect(args):
    pairs = []
    for item in args.input or []:
        if ":" in item:
            model, path = item.split(":", 1)
        else:
            model, path = guess_model(item), item
        pairs.append((model, path))
    if args.dir:
        for fn in sorted(os.listdir(args.dir)):
            if fn.startswith("faq-raw-") and fn.endswith(".txt"):
                pairs.append((guess_model(fn), os.path.join(args.dir, fn)))
    # 去重同一路径
    uniq, seen_paths = [], set()
    for m, p in pairs:
        ap = os.path.abspath(p)
        if ap not in seen_paths:
            seen_paths.add(ap)
            uniq.append((m, p))
    if not uniq:
        print("[FAIL] 没找到三份回答。用 --input chatgpt:faq-raw-chatgpt.txt 逐个传，或 --dir . 自动找 faq-raw-*.txt。")
        return 2
    for m, p in uniq:
        if not os.path.exists(p):
            print(f"[FAIL] 文件不存在：{p}")
            return 2
    rows, added, dup, skipped = collect_from_files(uniq)
    rows.extend(added)
    write_csv(rows)
    print(f"[OK] 读了 {len(uniq)} 份回答（{', '.join(m for m, _ in uniq)}），新增 {len(added)} 条，重复 {dup} 条已丢弃")
    if skipped:
        print(f"有 {skipped} 份没抽到问句。")
    print("")
    print_coverage(rows)
    print("")
    dist = [f"{m} {sum(1 for r in rows if r['source'] == m)} 条" for m, _ in MODELS if any(r["source"] == m for r in rows)]
    print("按来源分布：" + ("、".join(dist) if dist else "目前只有 seed 的固定六问"))
    print("")
    print(f"下一步：打开 {CSV_FILE} 给每条填真实答案（answer 列），status 改成 done；")
    print(f"填完跑 python3 {SKILL_SCRIPTS}/geo_faq.py render 生成可贴进页面的 FAQ 区块。")
    return 0


def print_questions(rows):
    by_bucket = {}
    for r in rows:
        by_bucket.setdefault(r["bucket"], []).append(r)
    for key, label in BUCKETS:
        group = by_bucket.get(key, [])
        if not group:
            continue
        print(f"{label}（{len(group)} 条）")
        for r in group:
            flag = "已答" if (r.get("answer") or "").strip() else "待答"
            print(f"{r['qid']}  [{flag}]  {r['question']}")
        print("")


def cmd_list(args):
    rows = read_csv()
    if not rows:
        print(f"还没有 {CSV_FILE}。先跑 python3 {SKILL_SCRIPTS}/geo_faq.py seed。")
        return 1
    print(f"FAQ 问题清单  |  {CSV_FILE}  |  共 {len(rows)} 条")
    print("")
    print_questions(rows)
    print_coverage(rows)
    return 0


def cmd_render(args):
    rows = read_csv()
    if not rows:
        print(f"[FAIL] 没有 {CSV_FILE}，先 seed 或 collect。")
        return 1
    done = [r for r in rows if (r.get("answer") or "").strip()]
    if not done:
        print(f"[FAIL] {CSV_FILE} 里一条答案都没填。FAQ 的答案必须真实，不能编；填完 answer 列再 render。")
        return 1
    order = {k: i for i, (k, _) in enumerate(BUCKETS)}
    done.sort(key=lambda r: (order.get(r["bucket"], 99), r["qid"]))

    html = ['<section id="faq">', '  <h2>常见问题</h2>']
    for r in done:
        q = esc(r["question"])
        a = esc(r["answer"])
        html.append(f'  <h3>{q}</h3>')
        html.append(f'  <p>{a}</p>')
    html.append('</section>')
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": r["question"],
             "acceptedAnswer": {"@type": "Answer", "text": r["answer"]}}
            for r in done
        ],
    }
    html.append('')
    html.append('<script type="application/ld+json">')
    html.append(json.dumps(schema, ensure_ascii=False, indent=2))
    html.append('</script>')
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(html) + "\n")

    md = ["## 常见问题", ""]
    for r in done:
        md.append(f"### {r['question']}")
        md.append("")
        md.append(r["answer"])
        md.append("")
    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"[OK] 已生成 {HTML_FILE}（可见 FAQ 区块 + FAQPage JSON-LD）与 {MD_FILE}")
    print(f"用了 {len(done)} 条已答问题；把它贴进落地页（Next.js 改页面组件，静态站改模板），人眼可见的区块和 JSON-LD 内容要一致。")
    print("")
    todo = print_coverage(rows)
    if todo:
        print(f"还有 {len(todo)} 条只有问题没答案，没有进区块；别把没答案的问题贴上线。")
    print("")
    print(f"贴完上线后跑一次 python3 {SKILL_SCRIPTS}/geo_audit.py <域名> --keyword \"<主词>\"，看 FAQ 结构这项是不是 PASS。")
    return 0


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def guess_model(name):
    low = os.path.basename(name).lower()
    if "claude" in low:
        return "claude"
    if "gemini" in low:
        return "gemini"
    if "gpt" in low or "chatgpt" in low or "openai" in low:
        return "chatgpt"
    return "unknown"


def main():
    ap = argparse.ArgumentParser(description="反推问题清单 → 汇总 → 写回 FAQ")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("seed", help="先给一份不依赖 AI 的种子问题清单")
    p.add_argument("--force", action="store_true", help="覆盖已有清单（会丢已填答案）")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("ask", help="生成 ChatGPT / Claude / Gemini 三模型反推提问包")
    p.add_argument("--category", default="", help="品类词，如 AI 海报生成工具")
    p.add_argument("--keyword", default="", help="主词，没给 category 时用它")
    p.add_argument("--n", type=int, default=15, help="每个模型要几条问句，默认 15")
    p.add_argument("--lang", choices=["zh", "en"], default="zh")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("collect", help="汇总三份回答，去重归类追加进清单")
    p.add_argument("--input", action="append", help="模型:文件路径，可多次传，如 chatgpt:faq-raw-chatgpt.txt")
    p.add_argument("--dir", default="", help="自动找该目录下的 faq-raw-*.txt")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("list", help="打印当前问题清单与六问覆盖")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("render", help="把已答问题生成页面 FAQ 区块 + JSON-LD")
    p.set_defaults(func=cmd_render)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
