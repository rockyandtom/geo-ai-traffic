#!/usr/bin/env python3
"""GEO 首次执行时，生成「第二次问 GPT」的一次性定时提醒参数。

为什么要单独一个脚本：
    定时自动化必须由 Agent 调用平台的自动化工具创建，Python 脚本不能也不该
    自己去写自动化配置。所以本脚本只做三件事：
      1. plan   —— 从台账读站点信息，产出一份自包含的创建参数（JSON）；
      2. pending—— 列出还没建提醒的站，防止首次执行漏建；
      3. mark-created / clear —— Agent 创建成功后把 id 与触发时间回写台账。

触发时机：项目第一次执行 geo-ai-traffic（首次 status 或首次 add）时，
必须为本站创建一次；默认触发时刻是台账到期日 10:00（上台架时若已过期，
顺延到明天 10:00）。到点后由那次执行决定要不要为下一轮再建一个。

用法：
    python geo_reminder.py plan --domain a.com
    python geo_reminder.py plan --domain a.com --at 2026-11-13T10:00
    python geo_reminder.py plan --domain a.com --json
    python geo_reminder.py pending
    python geo_reminder.py mark-created --domain a.com --id <自动化id> --at 2026-11-13T10:00
    python geo_reminder.py clear --domain a.com
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo_registry  # noqa: E402

SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TIME = "10:00"
STATUS = "python3 " + os.path.join(SKILL_SCRIPTS, "geo_status.py")
REGISTRY = "python3 " + os.path.join(SKILL_SCRIPTS, "geo_registry.py")
PROMPT_PACK = "python3 " + os.path.join(SKILL_SCRIPTS, "prompt_pack.py")
SUMMARIZE = "python3 " + os.path.join(SKILL_SCRIPTS, "summarize_probe.py")


def fire_at_for(site, override="", time_str=DEFAULT_TIME):
    """默认取台账到期日；已过期就顺延到明天，避免创建过去时间的一次性任务。"""
    if override:
        return override
    raw = site.get("due", "")
    try:
        due = date.fromisoformat(raw)
    except (ValueError, TypeError):
        due = date.today() + timedelta(days=7)
    day = max(due, date.today() + timedelta(days=1))
    return f"{day.isoformat()}T{time_str}"


def build_prompt(site):
    domain = site.get("domain", "")
    keyword = site.get("keyword") or "<主词>"
    scene = site.get("scene") or "<细分场景>"
    return (
        f"【GEO 第二次提问提醒】站点 {domain}，主词「{keyword}」，细分场景「{scene}」。\n"
        "这是本站的第二次 GEO 提问：把上线第 0 天问过的三问原样再问一遍做对比，"
        "并按状态机推进到基线探测。不要重新通读技能全文，按下面顺序执行。\n\n"
        f"1. 先跑 {STATUS} registry，确认该站仍在待处理列表、当前第几步、到期日；"
        f"再跑 {STATUS} status（当前工作目录就是本站项目目录）。\n\n"
        f"2. 按状态机给出的阶段出题：阶段 4 跑 {PROMPT_PACK} --domain {domain} "
        f'--keyword "{keyword}" --scene "{scene}" --stage check；'
        f"阶段 5 把 --stage 换成 bank 生成五档问题库（主体是找工具题）。"
        "把脚本输出原样贴给用户：普通文字段落直出，不要代码块、不要表格、不要用引号把整段包起来，"
        "变量必须已替换成真实值，一次最多 10~15 条，多了分批。\n\n"
        "3. 同时交代提问规程：同一个账号、登录后临时聊天（无记忆会话）、每题新开会话、"
        "同一题问三遍、未登录与登录后两种环境分开统计、遇人机验证或限流立刻停；"
        "存三样：回答全文、整屏截图、来源面板。三问必须和第 0 天逐字一致，否则没法对比。\n\n"
        "4. 用户回来给结果后：把每条回答按 probe-log.csv 的 16 列记进项目；"
        f"跑 {SUMMARIZE} --csv probe-log.csv 算提到率、联网率、平均位次、竞品榜；"
        "对比第 0 天的答案，写清「开始提你没、排第几、描述有没有过时、"
        "它有没有说直接在对话里帮你做」。\n\n"
        f"5. 记账：按实际完成情况跑 {STATUS} mark 4 或 mark 5；"
        f"跑 {REGISTRY} update --domain {domain} --stage <N> --due-in 7 续下一轮到期；"
        "如果台账里 reminder.status 还是 created，提醒用户这是一次性提醒、已经触发过，"
        "下一轮要重新建一个（用 geo_reminder.py plan 取参数）。\n\n"
        "6. 若三问仍没被推荐，按技能 §7 把 AI 的每句话落到具体代码改动"
        "（SSR、FAQ 六问、一需求一页、价格表），不要只改形容词。\n\n"
        "7. 结尾只给一句结论：现在卡在收录、出词还是引荐，下一件事是什么。\n\n"
        "纪律：没有拿到用户的真实回答就不要伪造探测数据，也不要自行把阶段标记完成；"
        "只输出提醒和待办，保留台账状态。"
    )


def build_plan(site, override="", time_str=DEFAULT_TIME):
    domain = site.get("domain", "")
    fire_at = fire_at_for(site, override, time_str)
    project = site.get("project") or os.getcwd()
    return {
        "name": f"GEO 第二次提问：{domain}",
        "prompt": build_prompt(site),
        "scheduleType": "once",
        "scheduledAt": fire_at,
        "status": "ACTIVE",
        "cwds": project,
    }


def cmd_plan(args):
    data = geo_registry.load()
    site = geo_registry.find(data, args.domain)
    if not site:
        print(f"[FAIL] 台账里没有 {args.domain}，先跑 geo_registry.py add 或在该项目跑一次 geo_status.py status")
        return 1
    rem = site.get("reminder") or {}
    if rem.get("status") == "created" and not args.force:
        print(f"[SKIP] {args.domain} 的定时提醒已创建：{rem.get('automation_id') or '未记 id'} · {rem.get('fire_at') or '未记时间'}")
        print("不要重复建。要建下一轮，先跑 geo_reminder.py clear，或给 plan 加 --force。")
        return 0
    plan = build_plan(site, args.at, args.time)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    print(f"定时提醒创建计划：{args.domain}")
    print(f"触发时间：{plan['scheduledAt']}（台账到期 {site.get('due') or '未设'}；已过期则顺延到明天）")
    print(f"工作目录：{plan['cwds']}")
    print("类型：一次性 once · ACTIVE")
    print()
    print("提醒要做的事：把上线第 0 天的 GPT 三问原样再问一遍做对比，按状态机推进到五档问题库，")
    print("回答记进 probe-log.csv 并汇总，再续下一轮到期。完整自包含提示词在下面的 JSON 里。")
    print()
    print("Agent 必须调用平台的自动化创建工具，参数如下（JSON，直接照抄）：")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print()
    print("创建成功后必须回写台账（否则下次会重复建）：")
    print(f"python3 {os.path.join(SKILL_SCRIPTS, 'geo_reminder.py')} mark-created --domain {args.domain} "
          f"--id <工具返回的自动化 id> --at {plan['scheduledAt']}")
    return 0


def cmd_pending(args):
    data = geo_registry.load()
    sites = [s for s in geo_registry.active(data)
             if (s.get("reminder") or {}).get("status") != "created"]
    print(f"还没建定时提醒的站：{len(sites)} 个 · {geo_registry.registry_path()}")
    if not sites:
        print("都建过了。")
        return 0
    print()
    for s in sites:
        fire = fire_at_for(s)
        print(f"- {s.get('domain')} · 到期 {s.get('due') or '未设'} · 建议触发 {fire} · 项目 {s.get('project') or '未登记路径'}")
    print()
    print("对每个站跑 plan 取参数并创建，创建后跑 mark-created 回写。")
    return 0


def cmd_mark_created(args):
    data = geo_registry.load()
    site = geo_registry.find(data, args.domain)
    if not site:
        print(f"[FAIL] 台账里没有 {args.domain}")
        return 1
    site["reminder"] = {
        "status": "created",
        "automation_id": args.id,
        "fire_at": args.at or fire_at_for(site),
        "created_at": date.today().isoformat(),
    }
    site["updated"] = date.today().isoformat()
    geo_registry.save(data)
    print(f"[OK] {args.domain} 的定时提醒已回写台账：{args.id} · {site['reminder']['fire_at']}")
    return 0


def cmd_clear(args):
    data = geo_registry.load()
    site = geo_registry.find(data, args.domain)
    if not site:
        print(f"[FAIL] 台账里没有 {args.domain}")
        return 1
    old = site.get("reminder") or {}
    site["reminder"] = {"status": "pending", "automation_id": "", "fire_at": ""}
    site["updated"] = date.today().isoformat()
    geo_registry.save(data)
    print(f"[OK] {args.domain} 的提醒标记已清回 pending（旧 id {old.get('automation_id') or '无'}）")
    print("提醒触发过或已删除时用这个；下一轮重新 plan 创建新的一次性提醒。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="首次执行技能时生成「第二次问 GPT」的一次性定时提醒参数")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("plan", help="生成自动化创建参数（默认子命令）")
    p.add_argument("--domain", required=True)
    p.add_argument("--at", default="", help="覆盖触发时刻，ISO 8601，如 2026-11-13T10:00")
    p.add_argument("--time", default=DEFAULT_TIME, help="触发钟点，默认 10:00")
    p.add_argument("--json", action="store_true", help="只输出 JSON，方便脚本接")
    p.add_argument("--force", action="store_true", help="已创建也照样生成（用于换一轮）")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("pending", help="列出还没建提醒的站")
    p.set_defaults(func=cmd_pending)

    p = sub.add_parser("mark-created", help="创建成功后回写台账")
    p.add_argument("--domain", required=True)
    p.add_argument("--id", required=True, help="自动化工具返回的 id")
    p.add_argument("--at", default="", help="触发时刻，默认按台账到期日算")
    p.set_defaults(func=cmd_mark_created)

    p = sub.add_parser("clear", help="把提醒标记清回 pending")
    p.add_argument("--domain", required=True)
    p.set_defaults(func=cmd_clear)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        print("[FAIL] 要给 --domain，例如：python geo_reminder.py plan --domain a.com")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
