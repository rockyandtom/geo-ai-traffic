#!/usr/bin/env python3
"""GEO 执行状态机：告诉你现在在哪一步、下一步跑哪条命令、门禁过没过。

问题：技能里东西都在，但没人记得住下一步该干什么，于是永远停在上线当天那三问。
解法：每一步都要落一个状态记录，没记录就不算做完；下一步由脚本算，不靠人记。

跨项目发现（这是第二个问题，比下一步更常见）：
    .geo-state.json 只记当前工作目录那一个站，换个项目就看不见。
    geo_registry.py 维护 ~/.workbuddy/geo-sites.json，按站累加。
    本脚本每次 status 都会：
      1. 先列出台账里所有待处理的站（哪些站要做 GEO、哪些到期了）；
      2. 把当前项目自动登记进台账（老站漏登记也能补回来）；
      3. 把当前站的阶段、到期、上次审计同步回台账。
    所以「第二次想不起来哪个项目」不再靠记忆：跑一次 registry 或 status 就有全站清单。

用法：
    python geo_status.py                      # 看现在在哪一步、下一步是什么
    python geo_status.py registry             # 只看跨站台账：有哪些站待处理
    python geo_status.py --domain a.com --keyword "k" --scene "do x"   # 顺带把命令填好
    python geo_status.py mark 4 --note "三问问过，截图在 shots/"        # 标记阶段完成
    python geo_status.py gate 5                # 门禁检查，进得去退出 0，进不去退出 1
    python geo_status.py reset                 # 清空状态（换站时用；不动台账）

阶段与门禁：
    1 页面改造   → 无门禁
    2 基建       → 无门禁；顺带做「自建归因埋点 → 按 GPT 来源重配付费墙」
    3 审计       → 无门禁（跑 geo_audit.py 会自动记账）
    4 体检三问   → 需要 3 已完成且 FAIL=0；顺带做「反推问题清单 → 写回 FAQ」
    5 基线探测   → 需要 4 已完成
    6 改动与复测 → 需要 5 已完成
    7 复盘       → 需要 6 已完成

退出码：0 正常 / 1 门禁未过 / 2 参数或状态文件错误。
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo_registry  # noqa: E402

STATE_FILE = ".geo-state.json"
SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def abs_cmd(text):
    """把文档里的 `python scripts/xxx.py` 换成能直接复制的绝对路径。

    状态文件跟当前工作目录走（站点项目里），脚本却在技能目录里，
    给相对路径等于给用户一条跑不通的命令。
    """
    return text.replace("python scripts/", f"python3 {SKILL_SCRIPTS}/")

STAGES = {
    1: (
        "页面改造",
        "§2 六个硬指标",
        'python scripts/geo_audit.py {domain} --keyword "{keyword}"',
        "改完 Title / H1 / FAQ / SSR 之后跑一次审计",
    ),
    2: (
        "基建",
        "§3 robots / llms.txt / 边缘层 / IndexNow",
        'python scripts/geo_audit.py {domain} --keyword "{keyword}" --key <你的key>',
        "robots 放行、llms.txt 上线、边缘层不拦、IndexNow 二选一",
        'python scripts/geo_attribution.py snippet && python scripts/geo_attribution.py paywall',
        "本阶段顺带做（自建归因埋点 → 按 GPT 来源重配付费墙，§3.1）",
        "埋点必须在有流量之前上线，晚装补不回历史数据；片段进 public 后要在落地页加 script 引用。",
    ),
    3: (
        "审计",
        "§4 线上真实返回核对",
        'python scripts/geo_audit.py {domain} --keyword "{keyword}" --key <你的key>',
        "把 FAIL 清零，每个 FAIL 都有对应改动位置（§4.1）",
    ),
    4: (
        "体检三问",
        "§5 直接问 AI 三件事",
        'python scripts/prompt_pack.py --domain {domain} --keyword "{keyword}" --scene "{scene}" --stage check',
        "问抓取 / 问对手 / 问差距，回答与截图存档",
        'python scripts/geo_faq.py seed && python scripts/geo_faq.py ask --category "{keyword}"',
        "本阶段顺带做（反推问题清单 → 写回 FAQ）",
        "三份回答存成 faq-raw-*.txt，用 geo_faq.py collect 汇总，填完答案用 render 出 FAQ 区块。",
    ),
    5: (
        "基线探测",
        "§6 问题库五档",
        'python scripts/prompt_pack.py --domain {domain} --keyword "{keyword}" --scene "{scene}" --stage bank',
        "16 题 × 三遍 × 两环境，记进 probe-log.csv，出第一份提到率",
    ),
    6: (
        "改动与复测",
        "§7 把 AI 的话落成改动",
        'python scripts/summarize_probe.py --csv probe-log.csv',
        "按 AI 反馈改代码，改完重跑审计与探测，对比两次数字",
    ),
    7: (
        "复盘",
        "§8 验收清单",
        'python scripts/geo_status.py status',
        "结论写成一句：卡在收录、出词还是引荐",
    ),
}

GATES = {
    4: [3],
    5: [4],
    6: [5],
    7: [6],
}


def load(path):
    if not os.path.exists(path):
        return {"version": 1, "domain": "", "keyword": "", "scene": "", "marks": {}, "audit": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[FAIL] 状态文件读不了：{e}")
        sys.exit(2)
    data.setdefault("marks", {})
    data.setdefault("audit", {})
    return data


def save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAIL] 状态写不进去：{e}")
        sys.exit(2)


def gate_failures(data, stage):
    """返回挡住进入该阶段（或标记该阶段完成）的原因列表。"""
    fails = []
    audit = data.get("audit", {})
    audit_fail = audit.get("fail", 0)
    detail = f"：{'、'.join(audit.get('fails', [])[:5])}" if audit.get("fails") else ""

    # 阶段 3 的完成条件就是审计 FAIL 清零
    if stage == 3 and audit_fail > 0:
        fails.append(f"审计还有 {audit_fail} 项 FAIL{detail}")

    for need in GATES.get(stage, []):
        if str(need) not in data.get("marks", {}):
            fails.append(f"阶段 {need}（{STAGES[need][0]}）还没完成")

    if stage == 4 and audit_fail > 0:
        fails.append(f"审计还有 {audit_fail} 项 FAIL{detail}")
    return fails


def detect_probe_log(path="probe-log.csv"):
    """看探测记录是否真的落地了。返回 {rows, max_rounds}，文件不在返回 None。"""
    if not os.path.exists(path):
        return None
    rows = []
    try:
        import csv

        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error):
        return {"rows": 0, "max_rounds": 0}
    rounds = {}
    for r in rows:
        qid = (r.get("qid") or "").strip()
        rnd = (r.get("round") or "").strip()
        if qid:
            rounds.setdefault(qid, set()).add(rnd)
    return {"rows": len(rows), "max_rounds": max((len(v) for v in rounds.values()), default=0)}


def sync_registry(data, stage, next_text=""):
    """把当前项目写进跨站台账：没登记就自动补，已登记就同步阶段与审计日期。

    这一步是关键：老站、手工建的项目、漏跑第 11 步登记的站，
    只要有人在这个目录跑过一次 status，就会自动出现在全站清单里。
    """
    domain = (data.get("domain") or "").strip().lower().rstrip("/")
    domain = domain.replace("https://", "").replace("http://", "")
    if not domain:
        return
    try:
        reg = geo_registry.load()
        site = geo_registry.find(reg, domain)
        if not site:
            today = date.today()
            site = {
                "domain": domain,
                "project": os.getcwd(),
                "keyword": data.get("keyword", ""),
                "scene": data.get("scene", ""),
                "launched": today.isoformat(),
                "due": (today + timedelta(days=7)).isoformat(),
                "stage": stage,
                "next": next_text or geo_registry.STAGE_NEXT.get(stage, ""),
                "last_audit": "",
                "status": "active",
                "reminder": {"status": "pending", "automation_id": "", "fire_at": ""},
                "note": "geo_status.py 自动补登记（老站或漏登记）",
                "updated": today.isoformat(),
            }
            reg["sites"].append(site)
            print(f"台账：{domain} 原来没登记，已自动补进全站清单")
        else:
            site.setdefault("reminder", {"status": "pending", "automation_id": "", "fire_at": ""})
            # 上游第 11 步登记时可能已经写了 stage 4（三问刚做完），而项目里
            # 还没跑过状态机。这时不能用空状态机的 stage 1 把台账打回去。
            has_state = bool(data.get("marks")) or bool(data.get("audit", {}).get("at"))
            if has_state or stage > int(site.get("stage", 0)):
                site["stage"] = stage
                if next_text:
                    site["next"] = next_text
            if not site.get("project"):
                site["project"] = os.getcwd()
            site["updated"] = date.today().isoformat()
        audit_at = data.get("audit", {}).get("at", "")
        if audit_at:
            site["last_audit"] = audit_at[:10]
        geo_registry.save(reg)
    except SystemExit:
        pass


def print_registry_banner(data):
    """每次查状态，先把「还有哪些站要做 GEO」摆到第一屏。"""
    try:
        reg = geo_registry.load()
        sites = geo_registry.active(reg)
        if not sites:
            print("GEO 台账：没有待处理站点（新站上线时由 ai-subscription-site 第 11 步登记）")
            print()
            return
        due = [s for s in sites if geo_registry.is_due(s)]
        pending = [s for s in sites if (s.get("reminder") or {}).get("status") != "created"]
        print(
            f"GEO 台账：{len(sites)} 个站待处理，其中 {len(due)} 个已到期、"
            f"{len(pending)} 个还没建定时提醒"
            f" · 跑 {abs_cmd('python scripts/geo_status.py registry')} 看全部"
        )
        cur = (data.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
        for s in geo_registry.sorted_sites(sites):
            mark = " ← 当前项目" if s.get("domain", "").lower() == cur else ""
            print(f"  - {s['domain']} · 阶段 {s.get('stage', 0)}/7 · {geo_registry.due_label(s)}{mark}")
        if pending and any(s.get("domain", "").lower() == cur for s in pending):
            print(f"  首次执行必做：当前项目还没建第二次提问的定时提醒（跑 geo_reminder.py plan --domain {cur} 取参数）")
        print()
    except SystemExit:
        pass


def cmd_registry(args):
    return geo_registry.cmd_list(argparse.Namespace(all=False))


def current_stage(data, probe=None):
    marks = data.get("marks", {})
    # 审计有 FAIL 就一律卡在阶段 3，不管 marks 写了什么
    if data.get("audit", {}).get("fail", 0) > 0:
        return 3
    # 产物比记账可信：探测记录有任一题凑满三遍，就算阶段 5 做过了
    if probe and probe.get("max_rounds", 0) >= 3:
        marks.setdefault("5", {"at": "-", "note": "probe-log.csv 有三遍记录"})
        data["marks"] = marks
    for n in sorted(STAGES):
        if str(n) not in marks:
            return n
    return 7


def cmd_status(args):
    data = load(args.state)
    for key in ("domain", "keyword", "scene"):
        if getattr(args, key, ""):
            data[key] = getattr(args, key)
    save(args.state, data)

    probe = detect_probe_log()
    stage = current_stage(data, probe)
    save(args.state, data)

    # 先同步并展示全站台账，再讲当前项目这一步该干什么
    sync_registry(data, stage, STAGES[stage][3])
    print_registry_banner(data)

    done = sorted(int(k) for k in data.get("marks", {}))
    audit = data.get("audit", {})

    print(f"GEO 进度：{len(done)}/7 已完成" + (f"（{', '.join(map(str, done))}）" if done else ""))
    if audit.get("at"):
        print(
            f"最近一次审计：{audit['at']} · 通过 {audit.get('pass', 0)} / 警告 {audit.get('warn', 0)} / 失败 {audit.get('fail', 0)}"
        )
    if probe:
        print(f"探测记录：{probe['rows']} 条，单题最多 {probe['max_rounds']} 遍")
    else:
        print("探测记录：没有 probe-log.csv")
    if "5" in data.get("marks", {}) and "4" not in data.get("marks", {}):
        print("注意：探测数据已经存在，但阶段 4（三问）没有记录 —— 三问要么没做，要么做完忘了 mark 4。")
    if stage >= 5 and not os.path.exists("faq-questions.csv"):
        print("注意：反推问题清单还没做（没有 faq-questions.csv），三模型给的真实问法还没写回 FAQ。")
    print()

    info = STAGES[stage]
    name, ref, cmd, goal = info[:4]
    print(f"当前阶段 {stage}/7：{name}（{ref}）")
    print(f"目标：{goal}")

    fails = gate_failures(data, stage)
    if fails:
        print("门禁未过，先补：")
        for f in fails:
            print(f"  - {f}")
        if stage == 3:
            print("  清零后重跑审计即可，跑完会自动记账")
        else:
            print(f"  修完后跑：{abs_cmd(f'python scripts/geo_status.py mark {stage - 1}')}")
        return 1

    vals = {
        "domain": data.get("domain") or "<域名>",
        "keyword": data.get("keyword") or "<主词>",
        "scene": data.get("scene") or "<细分场景>",
    }
    shown = abs_cmd(cmd.format(**vals))
    print(f"下一步命令：{shown}")
    if len(info) > 4:
        label = info[5] if len(info) > 5 else "本阶段顺带做"
        print(f"{label}：{abs_cmd(info[4].format(**vals))}")
        if len(info) > 6:
            print(info[6])
    print(f"做完标记：{abs_cmd(f'python scripts/geo_status.py mark {stage}')}")
    if not data.get("domain"):
        print('\n提示：把 --domain / --keyword / --scene 一起传，命令会自动填好。')
    return 0


def cmd_mark(args):
    data = load(args.state)
    stage = args.stage
    if stage not in STAGES:
        print(f"[FAIL] 没有阶段 {stage}，可选 1-7")
        return 2
    fails = gate_failures(data, stage)
    if fails and not args.force:
        print(f"[FAIL] 阶段 {stage}（{STAGES[stage][0]}）门禁未过，不能标记完成：")
        for f in fails:
            print(f"  - {f}")
        print("确实要强行标记就加 --force。")
        return 1
    data["marks"][str(stage)] = {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": args.note,
    }
    save(args.state, data)
    print(f"[OK] 阶段 {stage}（{STAGES[stage][0]}）已标记完成")
    if stage == 4 and not os.path.exists("faq-questions.csv"):
        print(f"提醒：这个站还没做反推问题清单，跑一次 {abs_cmd('python scripts/geo_faq.py seed')} 再按 §5.1 把真实问法写回 FAQ。")
    nxt = current_stage(data)
    sync_registry(data, nxt, STAGES[nxt][3])
    print(f"下一阶段是 {nxt}（{STAGES[nxt][0]}），跑 {abs_cmd('python scripts/geo_status.py status')} 看命令")
    return 0


def cmd_gate(args):
    data = load(args.state)
    fails = gate_failures(data, args.stage)
    if fails:
        print(f"[BLOCKED] 进不了阶段 {args.stage}：")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"[OK] 可以进入阶段 {args.stage}（{STAGES[args.stage][0]}）")
    return 0


def cmd_reset(args):
    if os.path.exists(args.state):
        os.remove(args.state)
        print(f"[OK] 已清空 {args.state}")
    else:
        print("没有状态文件，本来就是空的")
    return 0


def main():
    ap = argparse.ArgumentParser(description="GEO 执行状态机：现在在哪一步、下一步跑什么")
    ap.add_argument("--state", default=STATE_FILE, help=f"状态文件，默认 {STATE_FILE}")
    sub = ap.add_subparsers(dest="cmd")

    p1 = sub.add_parser("status", help="看当前阶段与下一步命令（默认子命令）")
    p1.add_argument("--domain", default="")
    p1.add_argument("--keyword", default="")
    p1.add_argument("--scene", default="")
    p1.set_defaults(func=cmd_status)

    p2 = sub.add_parser("mark", help="标记某阶段完成")
    p2.add_argument("stage", type=int)
    p2.add_argument("--note", default="", help="证据备注，如截图路径、审计结论")
    p2.add_argument("--force", action="store_true", help="门禁未过也强行标记")
    p2.set_defaults(func=cmd_mark)

    p3 = sub.add_parser("gate", help="只做门禁检查，退出码 0/1")
    p3.add_argument("stage", type=int)
    p3.set_defaults(func=cmd_gate)

    p4 = sub.add_parser("reset", help="清空状态（不动跨站台账）")
    p4.set_defaults(func=cmd_reset)

    p5 = sub.add_parser("registry", help="只看跨站台账：有哪些站要做 GEO、各在第几步、哪些到期")
    p5.set_defaults(func=cmd_registry)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        args.domain = ""
        args.keyword = ""
        args.scene = ""
        return cmd_status(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
