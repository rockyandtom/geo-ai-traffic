#!/usr/bin/env python3
"""生成「向 AI 提问」的即用文本包：变量填好、纯段落输出，可直接全选复制。

模板来源：assets/templates/ask-gpt-prompts.md

用法：
    python prompt_pack.py --domain posterai.app --keyword "ai poster generator"
    python prompt_pack.py --domain posterai.app --keyword "ai poster generator" \
        --brand PosterAI --scene "turn a photo into a movie poster" \
        --competitor canva.com --lang en --stage bank
    python prompt_pack.py --domain x.com --keyword "k" --stage check --plain

--stage：
    all（默认，A+B+C+D+E）/ check（上线当天三问）/ reverse（反推三步）
    / extra（竞品与反向询问）/ bank（问题库五档）/ probe（复盘追问）

输出原则（与 SKILL.md 附录 A 一致）：
1. 提问正文一律普通段落，不加代码块、不加表格、不加整段引号；
2. 每条前面只有一行用途说明，然后空一行；
3. 不留 {placeholder}，缺的参数会在末尾提示。
"""

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo_faq  # noqa: E402  —— 反推第一步的问句只有一份来源，两个脚本共用

TIER_ORDER = ["brand", "tool", "compare", "spoken", "explain"]


def zh_prompts(v):
    """中文提问模板。v 是已填好的变量字典。"""
    d, b, k, c, y, s, comp = v["domain"], v["brand"], v["keyword"], v["category"], v["year"], v["scene"], v["competitor"]
    return {
        "check": [
            ("问抓取：让它复述你的页面（读不到就是 SSR 或爬虫放行有问题）",
             f"你能不能访问 https://{d} ，把你读到的页面内容复述一遍？如果读不到，告诉我卡在哪一步。"),
            ("问对手：看它现在推谁（这份名单就是你的对手榜）",
             f"你的数据库里，关于 {k} 这个需求，目前有哪些工具或网站可以推荐？请按推荐优先级列出来，并说明你为什么推荐它们。"),
            ("问差距：让它说愿意不愿推荐你、要改哪里（答案当诊断报告用）",
             f"如果用户问「有没有能做 {s} 的网站」，你会推荐 https://{d} 吗？为什么？如果要多推荐它，页面需要改进什么？请给出具体到板块的修改建议。"),
        ],
        "reverse": [
            ("反推第一步：这一句要在 ChatGPT / Claude / Gemini 各问一遍，三家差异正是要收集的（完整三模型包用 geo_faq.py ask）",
             geo_faq.main_question(v, "zh")),
            ("反推第二步：任选一个问句去问，然后点开来源面板记标题（不是问答案，是偷结构）",
             f"我想找能做 {s} 的工具，有什么推荐？"),
            ("反推第三步：把上一步收集的标题丢回去，让它告诉你写什么",
             f"下面是我从你的回答里整理出来的、你推荐其他网站时引用的页面标题和内容要点：\n（把第二步收集的标题粘贴在这里）\n请分析这些页面的共同结构，告诉我应该写一篇什么样的文章、包含哪些板块、发到哪些平台，才能被这类回答引用。"),
        ],
        "extra": [
            ("抄竞品 + 问原因：它的答案就是你的页面大纲",
             f"你为什么推荐 {comp} 而不是别的同类工具？它页面上的哪些信息影响了你？如果有一个新网站想在同样的需求上被推荐，它至少要有哪些内容？"),
            ("角色互换：先问它自己会怎么找",
             f"假如你是我，现在要找一个能做 {s} 的工具，你会怎么搜、怎么判断哪个好用？"),
            ("接着补这句：会把 URL 递到它面前，触发实时抓取",
             f"对了，我听说 https://{d} 这个站也在做这个，你去看一下它，和前面说的那几个对比一下。"),
        ],
        "brand": [
            ("品牌题：认不认识你",
             f"{b} 是什么？它是做什么的？"),
            ("品牌题：价格与免费额度是否过时",
             f"{b} 收费吗？免费额度有多少？"),
            ("品牌题：可信度",
             f"https://{d} 这个网站靠谱吗？"),
            ("品牌题：与竞品的直接比较",
             f"{b} 和 {comp} 比，哪个更好用？"),
        ],
        "tool": [
            ("找工具题（主体）：最朴素的一问",
             f"有没有网站能把 {s} 做出来？"),
            ("找工具题：问最快",
             f"{s} 用什么工具做最快？"),
            ("找工具题：免费 + 免注册",
             f"有什么免费的 {c} 工具？不用注册的最好。"),
            ("找工具题：批量能力",
             f"能批量做 {s} 的网站有哪些？"),
            ("找工具题：水印这个真实痛点",
             f"{s} 不想有水印，用哪个网站？"),
        ],
        "compare": [
            ("合集题：抢榜单位次",
             f"{y} 年最好的 {c} 工具有哪些？"),
            ("比较题：一次做两件事",
             f"能一次做完 {s} 和其他类似需求的网站有吗？"),
            ("比较题：性价比",
             f"{c} 工具里，哪个性价比最高？"),
        ],
        "spoken": [
            ("口语版：真实用户的原话",
             f"我明天要做个海报，有没有什么网站能帮我搞定的？"),
            ("口语版：朋友推荐的口吻",
             f"朋友让我推荐个能 {s} 的东西，用哪个好？"),
        ],
        "explain": [
            ("解释类题：只用来验证「解释类不联网」这条规律",
             f"{c} 是什么原理？"),
            ("解释类题：同上",
             f"怎么做 {s} 效果最好？"),
        ],
        "probe": [
            ("复盘：问它为什么不提你",
             f"我刚才问「有没有能做 {s} 的网站」，你没有推荐 https://{d} 。是因为没抓到它，还是抓到了但内容不够？请说明判断依据。"),
            ("复盘：问它到底读了哪些页（直接暴露引首页还是引内页）",
             f"推荐 {c} 工具时，你引用的是哪些网页？请列出你实际读过的 URL。"),
        ],
    }


def en_prompts(v):
    """英文提问模板（面向英文市场时用）。"""
    d, b, k, c, y, s, comp = v["domain"], v["brand"], v["keyword"], v["category"], v["year"], v["scene"], v["competitor"]
    return {
        "check": [
            ("Ask crawl: make it repeat what it reads",
             f"Can you access https://{d} and repeat back what you read on that page? If you cannot, tell me where it fails."),
            ("Ask competitors: who it recommends right now",
             f"Which tools or websites can you recommend for {k}? List them by recommendation priority and explain why you recommend each."),
            ("Ask gap: whether it would recommend you, and what to fix",
             f"If a user asked for a website that can {s}, would you recommend https://{d}? Why? What should be improved on that page so you recommend it more often? Give specific, section-level suggestions."),
        ],
        "reverse": [
            ("Reverse step 1: ask this same question in ChatGPT, Claude and Gemini (full 3-model pack: geo_faq.py ask)",
             geo_faq.main_question(v, "en")),
            ("Reverse step 2: ask one of them, then open the sources panel and copy the titles",
             f"I need a tool that can {s}. What do you recommend?"),
            ("Reverse step 3: feed the titles back and ask what to write",
             f"Here are the page titles and content points you cited when recommending other sites:\n(paste them here)\nAnalyse the common structure of these pages and tell me what article I should write, which sections it needs, and where to publish it so that answers like yours cite it."),
        ],
        "extra": [
            ("Copy a competitor, then ask why it wins",
             f"Why do you recommend {comp} over other tools in the same category? Which parts of its page influenced you? What would a new website need at minimum to be recommended for the same need?"),
            ("Role swap: ask how it would search itself",
             f"If you were me, looking for a tool that can {s}, how would you search and how would you judge which one is good?"),
            ("Then add this line: it pushes your URL into live crawling",
             f"By the way, I heard https://{d} also does this. Go look at it and compare it with the ones you mentioned."),
        ],
        "brand": [
            ("Brand: does it know you", f"What is {b}? What does it do?"),
            ("Brand: pricing and free quota freshness", f"How much does {b} cost? How much can I use for free?"),
            ("Brand: trust", f"Is https://{d} legit?"),
            ("Brand: head-to-head", f"Is {b} better than {comp}?"),
        ],
        "tool": [
            ("Tool question (main type): the plainest form", f"Is there a website that can {s}?"),
            ("Tool question: fastest", f"What is the fastest tool to {s}?"),
            ("Tool question: free and no signup", f"What free {c} tools are there? Ideally without signing up."),
            ("Tool question: batch", f"Which websites can {s} in bulk?"),
            ("Tool question: watermark pain point", f"Which website can {s} without a watermark?"),
        ],
        "compare": [
            ("Roundup: fight for a slot", f"What are the best {c} tools in {y}?"),
            ("Comparison: two jobs at once", f"Is there one website that can {s} and similar tasks in one place?"),
            ("Comparison: value", f"Which {c} tool gives the best value for money?"),
        ],
        "spoken": [
            ("Spoken: how a real user talks", f"I need to make a poster for tomorrow, is there a site that can just do it for me?"),
            ("Spoken: a friend asking for a recommendation", f"A friend asked me to recommend something that can {s}. Which one should I use?"),
        ],
        "explain": [
            ("Explain type: only to test the 'explain questions do not search' rule", f"What is {c} and how does it work?"),
            ("Explain type: same purpose", f"What is the best way to {s}?"),
        ],
        "probe": [
            ("Review: why it did not mention you",
             f"I just asked which website can {s}, and you did not recommend https://{d}. Is it because you could not crawl it, or because the content was not good enough? Explain your reasoning."),
            ("Review: which pages it actually read",
             f"When recommending {c} tools, which web pages did you cite? List the URLs you actually read."),
        ],
    }


STAGE_TITLES = {
    "check": "一、上线当天三问（同一账号，新开会话，按顺序问）",
    "reverse": "二、反推三步（让它告诉你该写什么）",
    "extra": "三、竞品与反向询问",
    "bank": "四、问题库五档（主体是「找工具题」）",
    "probe": "五、复盘追问",
}

STAGE_HINTS = {
    "check": "三问的答案就是诊断报告：读不到＝SSR/爬虫问题；名单＝对手榜；理由＝页面大纲。",
    "reverse": "第一步这句要在 ChatGPT / Claude / Gemini 各问一遍；三份回答用 geo_faq.py collect 汇总成 faq-questions.csv，填完答案用 render 写回 FAQ（见 SKILL.md §5.1）。第二步不追答案，追的是「它引了哪些页、那些页标题怎么写」——标题结构就是你要对齐的结构。",
    "extra": "第一问的答案直接当页面板块用；第三问要把 URL 说出口，才会触发实时抓取。",
    "bank": "每题新开会话、问三遍、两种环境分开记；题库超 15 条就分批问，先问「找工具题」。",
    "probe": "复盘问题要带着具体问句去问，否则它只会给泛泛的答案。",
}

TIER_TITLES = {
    "brand": "D1 品牌题",
    "tool": "D2 找工具题（主体）",
    "compare": "D3 比较 / 合集题",
    "spoken": "D4 口语版",
    "explain": "D5 解释类题",
}


def main():
    ap = argparse.ArgumentParser(description="生成可直接复制的 AI 提问包")
    ap.add_argument("--domain", required=True, help="你的域名，如 posterai.app")
    ap.add_argument("--keyword", required=True, help="主词：AI 联网时真会打的词（常带年份）")
    ap.add_argument("--brand", default="", help="品牌名，默认取域名首段")
    ap.add_argument("--category", default="", help="品类词，默认同主词")
    ap.add_argument("--scene", default="", help="细分场景，默认同主词")
    ap.add_argument("--competitor", default="", help="竞品域名，品牌题/竞品题会用")
    ap.add_argument("--year", type=int, default=date.today().year)
    ap.add_argument("--lang", choices=["zh", "en"], default="zh", help="提问用哪种语言，默认中文")
    ap.add_argument("--stage", default="all", choices=["all"] + list(STAGE_TITLES))
    ap.add_argument("--plain", action="store_true", help="不打印用途说明与提示，只输出提问正文")
    args = ap.parse_args()

    domain = args.domain.strip().replace("https://", "").replace("http://", "").rstrip("/")
    keyword = args.keyword.strip()
    brand = args.brand.strip() or domain.split(".")[0]
    category = args.category.strip() or keyword
    scene = args.scene.strip() or keyword
    competitor = args.competitor.strip() or "the leading tool in this category"
    if not args.competitor:
        print("（提示：没给 --competitor，竞品相关问句里用了占位描述，建议补上真实竞品域名）\n", file=sys.stderr)
    if not args.scene:
        print(
            "（提示：没给 --scene，问句里直接用了主词。主词是名词短语时英文会不通顺，"
            "建议补成动词短语，如 --scene \"turn a photo into a movie poster\"）\n",
            file=sys.stderr,
        )

    v = {
        "domain": domain, "keyword": keyword, "brand": brand, "category": category,
        "year": args.year, "scene": scene, "competitor": competitor,
    }
    packs = zh_prompts(v) if args.lang == "zh" else en_prompts(v)

    stages = list(STAGE_TITLES) if args.stage == "all" else [args.stage]
    if not args.plain:
        print(f"AI 提问包  {domain}  |  主词：{keyword}  |  语言：{'中文' if args.lang == 'zh' else '英文'}  |  {args.year}")
        print("用法：逐条复制到新会话里问。别在一个会话里连着问，上下文会污染结果。")

    n = 0
    for st in stages:
        if not args.plain:
            print()
            print(STAGE_TITLES[st])
            print(STAGE_HINTS[st])

        if st == "bank":
            if not args.plain:
                print("出题规则：把主词拆成 用途 × 对象 × 免费/无水印/批量，一个细分一题，用用户嘴里的说法。")
            for tier in TIER_ORDER:
                if not args.plain:
                    print()
                    print(TIER_TITLES[tier])
                for label, text in packs[tier]:
                    n += 1
                    print()
                    if not args.plain:
                        print(f"{n}. {label}")
                    print(text)
            continue

        for label, text in packs[st]:
            n += 1
            print()
            if not args.plain:
                print(f"{n}. {label}")
            print(text)

    if not args.plain:
        print()
        print(f"共 {n} 条。问完记着存证：回答全文 + 整屏截图 + 点开来源面板再截一次；同一题问三遍再下结论。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
