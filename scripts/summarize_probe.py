#!/usr/bin/env python3
"""把 GEO 探测记录（probe-log.csv）汇总成可对比的数字。

输入：assets/templates/probe-log.csv 格式（九项字段 + 竞争对手列）。
输出：按环境的提到率 / 联网率 / 平均位次 / 三遍一致性 / 竞品榜 / 抢用户比例 / 引用页面分布。

用法：
    python summarize_probe.py --csv probe-log.csv
    python summarize_probe.py --csv probe-log.csv --json > summary.json
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict

YES = {"yes", "y", "true", "1", "是"}
NO = {"no", "n", "false", "0", "否"}


def flag(val):
    v = (val or "").strip().lower()
    if v in YES:
        return True
    if v in NO:
        return False
    return None


def rank_of(val):
    v = (val or "").strip()
    if not v:
        return None
    try:
        n = int(float(v))
        return n if n > 0 else None
    except ValueError:
        return None


def pct(a, b):
    return f"{a / b * 100:.0f}%" if b else "-"


def grade(rate):
    if rate is None:
        return "-"
    if rate >= 0.5:
        return "稳定被推荐"
    if rate >= 0.2:
        return "偶发出现，边缘"
    if rate > 0:
        return "几乎不提"
    return "完全没进名单"


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]
    for r in rows:
        r["_mentioned"] = flag(r.get("mentioned"))
        r["_searched"] = flag(r.get("searched"))
        r["_rank"] = rank_of(r.get("rank"))
        r["_steal"] = flag(r.get("does_it_for_you"))
        r["_env"] = (r.get("env") or "unknown").strip() or "unknown"
        r["_tier"] = (r.get("tier") or "unknown").strip() or "unknown"
        r["_qid"] = (r.get("qid") or "").strip()
        r["_cited"] = (r.get("cited_url") or "").strip() or "none"
        r["_outdated"] = (r.get("outdated") or "").strip() or "no"
    return rows


def summarize(rows):
    out = {"total_rows": len(rows), "env": {}, "tier": {}, "round_consistency": {}, "competitors": {}, "steal": {}, "cited": {}, "outdated": {}}

    # 按环境
    by_env = defaultdict(list)
    for r in rows:
        by_env[r["_env"]].append(r)
    for env, rs in sorted(by_env.items()):
        qids = {r["_qid"] for r in rs if r["_qid"]}
        mentions = [r for r in rs if r["_mentioned"]]
        searched = [r for r in rs if r["_searched"]]
        ranks = [r["_rank"] for r in rs if r["_rank"]]
        out["env"][env] = {
            "rows": len(rs),
            "questions": len(qids),
            "mention_rows": len(mentions),
            "mention_rate": round(len(mentions) / len(rs), 3) if rs else None,
            "searched_rows": len(searched),
            "search_rate": round(len(searched) / len(rs), 3) if rs else None,
            "avg_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
            "verdict": grade(len(mentions) / len(rs)) if rs else "-",
        }

    # 按题型（合并两种环境，仅作结构参考；报告主结论仍看 env）
    by_tier = defaultdict(list)
    for r in rows:
        by_tier[r["_tier"]].append(r)
    for tier, rs in sorted(by_tier.items()):
        m = sum(1 for r in rs if r["_mentioned"])
        s = sum(1 for r in rs if r["_searched"])
        out["tier"][tier] = {
            "rows": len(rs),
            "mention_rows": m,
            "search_rows": s,
            "mention_rate": round(m / len(rs), 3) if rs else None,
            "search_rate": round(s / len(rs), 3) if rs else None,
        }

    # 三遍一致性（同一 qid + env 视为一组）
    grp = defaultdict(list)
    for r in rows:
        if r["_qid"]:
            grp[(r["_qid"], r["_env"])].append(r)
    cons = {"all_yes": [], "all_no": [], "mixed": [], "single_run": []}
    for (qid, env), rs in sorted(grp.items()):
        vals = [r["_mentioned"] for r in rs if r["_mentioned"] is not None]
        if not vals:
            continue
        key = f"{qid}@{env}"
        if len(vals) < 3:
            cons["single_run"].append(key)
        elif all(vals):
            cons["all_yes"].append(key)
        elif not any(vals):
            cons["all_no"].append(key)
        else:
            cons["mixed"].append(key)
    out["round_consistency"] = cons

    # 竞品榜
    comp = Counter()
    for r in rows:
        for d in (r.get("competitors") or "").replace(",", ";").replace(" ", ";").split(";"):
            d = d.strip().lower().strip("/")
            if d:
                comp[d] += 1
    out["competitors"] = dict(comp.most_common(15))

    # 抢用户 / 引用页 / 过时
    steal_yes = sum(1 for r in rows if r["_steal"])
    out["steal"] = {
        "yes": steal_yes,
        "total": len(rows),
        "rate": round(steal_yes / len(rows), 3) if rows else None,
    }
    cited = Counter(r["_cited"] for r in rows if r["_mentioned"])
    out["cited"] = dict(cited.most_common())
    outd = Counter(r["_outdated"] for r in rows if r["_mentioned"])
    out["outdated"] = dict(outd.most_common())
    return out


def fmt_counter(d):
    if not d:
        return "无"
    return "，".join(f"{k} {v} 次" for k, v in d.items())


def render(s):
    lines = []
    lines.append(f"探测记录汇总（{s['total_rows']} 条）")
    lines.append("")
    lines.append("## 按环境（结论只看这里，两种环境不要混算）")
    if not s["env"]:
        lines.append("1. 没有数据")
    for i, (env, v) in enumerate(s["env"].items(), 1):
        lines.append(
            f"{i}. {env}：{v['questions']} 题 / {v['rows']} 条记录；提到 {v['mention_rows']} 次（{pct(v['mention_rows'], v['rows'])}）；"
            f"联网 {v['searched_rows']} 次（{pct(v['searched_rows'], v['rows'])}）；平均位次 {v['avg_rank'] or '-'}；判定：{v['verdict']}"
        )
    lines.append("")
    lines.append("## 按题型")
    for i, (tier, v) in enumerate(s["tier"].items(), 1):
        lines.append(
            f"{i}. {tier}：{v['rows']} 条；提到 {v['mention_rows']} 次（{pct(v['mention_rows'], v['rows'])}）；"
            f"联网 {v['search_rows']} 次（{pct(v['search_rows'], v['rows'])}）"
        )
    lines.append("")
    lines.append("## 三遍一致性")
    c = s["round_consistency"]
    lines.append(f"1. 三遍全提（{len(c['all_yes'])}）：{', '.join(c['all_yes']) or '无'}")
    lines.append(f"2. 三遍全不提（{len(c['all_no'])}）：{', '.join(c['all_no']) or '无'}")
    lines.append(f"3. 摇摆（{len(c['mixed'])}）：{', '.join(c['mixed']) or '无'} —— 这些不能平均掉，要单独看")
    if c["single_run"]:
        lines.append(f"4. 不足三遍（{len(c['single_run'])}）：{', '.join(c['single_run'])} —— 数据还不能下结论，补问")
    lines.append("")
    lines.append("## 竞品榜（它点名的其他网站）")
    if s["competitors"]:
        for i, (d, n) in enumerate(s["competitors"].items(), 1):
            lines.append(f"{i}. {d} —— {n} 次")
    else:
        lines.append("1. 无")
    lines.append("")
    lines.append("## 它在替你做事 / 引用页 / 描述过时")
    st = s["steal"]
    lines.append(f"1. 回答里说自己「直接帮你做」：{st['yes']}/{st['total']}（{pct(st['yes'], st['total'])}）—— 比例高说明这个需求天生不适合做站")
    lines.append(f"2. 引用页面分布：{fmt_counter(s['cited'])}")
    lines.append(f"3. 描述过时分布：{fmt_counter(s['outdated'])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="probe-log.csv 路径")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        rows = load(args.csv)
    except FileNotFoundError:
        print(f"找不到文件：{args.csv}", file=sys.stderr)
        return 2
    s = summarize(rows)
    print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
