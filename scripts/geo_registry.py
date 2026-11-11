#!/usr/bin/env python3
"""GEO 跨站台账：回答「有哪些站要做 GEO、各在第几步、哪些到期了」。

为什么有这个文件：
    .geo-state.json 只记当前工作目录那一个站，换个项目、换次会话就看不见。
    GEO 是持续动作（上线当天三问 → 7 天对比 → 每次改版复测），但原来唯一
    的触发点挂在「首次上线」这个一次性事件上，所以第二次必然想不起来。
    台账是按站累加、路径固定的唯一清单：每个站上线时由 ai-subscription-site
    第 11 步追加一行，geo-ai-traffic 每次开工先读它。

数据：~/.workbuddy/geo-sites.json（可用 GEO_REGISTRY 环境变量覆盖，测试用）

用法：
    python geo_registry.py list
    python geo_registry.py due
    python geo_registry.py scan --root ~/WorkBuddy      # 只读：找出做过 GEO / 留过待办的存量项目
    python geo_registry.py add --domain a.com --project /abs/path --keyword "..." --scene "..."
    python geo_registry.py update --domain a.com --stage 5
    python geo_registry.py update --domain a.com --due-in 7
    python geo_registry.py done --domain a.com
    python geo_registry.py path --domain a.com

`scan` 只读、不写台账，只输出报告与建议命令；要登记需显式跑 add。
输出一律纯文本段落，不用表格、不用代码块 —— 要能整段复制。
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

DEFAULT_REGISTRY = os.path.expanduser("~/.workbuddy/geo-sites.json")

STAGE_NEXT = {
    0: "跑 geo_status.py status 看现在在第几步",
    1: "按 §2 改 Title / H1 / FAQ / SSR，再跑一次审计",
    2: "按 §3 配 robots、llms.txt、边缘层、IndexNow",
    3: "把审计 FAIL 清零（§4.1 每项都写了改哪个文件）",
    4: "问体检三问，回答与截图存档，改完再问一次",
    5: "跑五档问题库，每题三遍、两环境分开，记进 probe-log.csv",
    6: "按 AI 反馈改代码，重跑审计与探测，对比两次数字",
    7: "写一句结论：卡在收录、出词还是引荐",
}

STAGE_NAME = {
    0: "未开始", 1: "页面改造", 2: "基建", 3: "审计",
    4: "体检三问", 5: "基线探测", 6: "改动与复测", 7: "复盘",
}


def registry_path():
    return os.environ.get("GEO_REGISTRY") or DEFAULT_REGISTRY


def load():
    path = registry_path()
    if not os.path.exists(path):
        return {"version": 1, "sites": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[FAIL] 台账读不了（{path}）：{e}")
        sys.exit(2)
    data.setdefault("sites", [])
    return data


def save(data):
    path = registry_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FAIL] 台账写不进去（{path}）：{e}")
        sys.exit(2)


def find(data, domain):
    domain = (domain or "").strip().lower().rstrip("/")
    for s in data["sites"]:
        if s.get("domain", "").lower() == domain:
            return s
    return None


def parse_day(value):
    """接受 YYYY-MM-DD；空串返回 None；格式错直接报错退出。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        print(f"[FAIL] 日期要写成 YYYY-MM-DD，收到的是 {value}")
        sys.exit(2)


def due_label(site, today=None):
    today = today or date.today()
    raw = site.get("due", "")
    d = parse_day(raw) if raw else None
    if not d:
        return "未设到期日"
    delta = (d - today).days
    if delta < 0:
        return f"已逾期 {-delta} 天（{raw}）"
    if delta == 0:
        return f"今天到期（{raw}）"
    return f"还有 {delta} 天（{raw}）"


def is_due(site, today=None):
    today = today or date.today()
    d = parse_day(site.get("due", "")) if site.get("due") else None
    return bool(d and d <= today)


def show(sites, title, today=None):
    print(title)
    if not sites:
        print("没有待处理站点。新站上线时由 ai-subscription-site 第 11 步自动登记，也可以手动 add。")
        return
    print()
    for i, s in enumerate(sites, 1):
        stage = int(s.get("stage", 0))
        head = f"{i}. {s.get('domain', '?')} —— 阶段 {stage}/7 {STAGE_NAME.get(stage, '?')} · {due_label(s, today)}"
        print(head)
        print(f"   项目：{s.get('project') or '未登记路径'}")
        print(f"   下一步：{s.get('next') or STAGE_NEXT.get(stage, '')}")
        if s.get("last_audit"):
            print(f"   上次审计：{s['last_audit']}")
        rem = s.get("reminder") or {}
        if rem.get("status") == "created":
            print(f"   定时提醒：已创建 {rem.get('automation_id') or '（未记 id）'} · {rem.get('fire_at') or '未记时间'}")
        else:
            print("   定时提醒：未创建（首次执行技能时必须建，见 geo_reminder.py plan）")
        if s.get("note"):
            print(f"   备注：{s['note']}")
        print()
    status_cmd = "python3 " + os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo_status.py") + " status"
    print(f"共 {len(sites)} 个站待处理。要处理某个站：cd <上面那个项目路径>，再跑 {status_cmd}")


def active(data):
    return [s for s in data["sites"] if s.get("status", "active") != "done"]


def sorted_sites(sites):
    """没到期日的排最后，其余按到期日升序。"""
    return sorted(sites, key=lambda s: (s.get("due") or "9999-12-31", s.get("domain", "")))


def cmd_list(args):
    data = load()
    sites = data["sites"] if args.all else active(data)
    show(sorted_sites(sites), f"GEO 台账：{len(sites)} 个站" + ("（含已完成）" if args.all else "待处理") + f" · {registry_path()}")
    return 0


def cmd_due(args):
    data = load()
    sites = [s for s in active(data) if is_due(s)]
    show(sorted_sites(sites), f"GEO 台账：{len(sites)} 个站已到期或今天到期 · {registry_path()}")
    return 0


def cmd_add(args):
    data = load()
    domain = args.domain.strip().lower().rstrip("/").replace("https://", "").replace("http://", "")
    if find(data, domain):
        print(f"[SKIP] {domain} 已经在台账里，要改内容用 update")
        return 0
    launched = parse_day(args.launched) or date.today()
    if args.due:
        due = parse_day(args.due)
    elif args.due_in is not None:
        due = launched + timedelta(days=args.due_in)
    else:
        due = launched + timedelta(days=7)
    stage = args.stage
    site = {
        "domain": domain,
        "project": os.path.abspath(os.path.expanduser(args.project)) if args.project else "",
        "keyword": args.keyword,
        "scene": args.scene,
        "launched": launched.isoformat(),
        "due": due.isoformat(),
        "stage": stage,
        "next": args.next or STAGE_NEXT.get(stage, ""),
        "last_audit": "",
        "status": "active",
        "reminder": {"status": "pending", "automation_id": "", "fire_at": ""},
        "note": args.note,
        "updated": date.today().isoformat(),
    }
    data["sites"].append(site)
    save(data)
    print(f"[OK] 已登记 {domain} · 阶段 {stage}/7 · 到期 {due.isoformat()}")
    print(f"项目：{site['project'] or '未登记路径'}")
    print(f"下一步：{site['next']}")
    print(f"台账：{registry_path()}")
    print("首次执行还没建定时提醒：跑 python3 <本技能>/scripts/geo_reminder.py plan --domain " + domain + " 生成参数并创建")
    return 0


def cmd_update(args):
    data = load()
    site = find(data, args.domain)
    if not site:
        print(f"[FAIL] 台账里没有 {args.domain}，先用 add 登记")
        return 1
    if args.stage is not None:
        site["stage"] = args.stage
        site["next"] = STAGE_NEXT.get(args.stage, "")
    if args.next:
        site["next"] = args.next
    if args.due:
        site["due"] = parse_day(args.due).isoformat()
    if args.due_in is not None:
        site["due"] = (date.today() + timedelta(days=args.due_in)).isoformat()
    if args.last_audit:
        site["last_audit"] = parse_day(args.last_audit).isoformat()
    if args.project:
        site["project"] = os.path.abspath(os.path.expanduser(args.project))
    if args.keyword:
        site["keyword"] = args.keyword
    if args.scene:
        site["scene"] = args.scene
    if args.note:
        site["note"] = args.note
    site["updated"] = date.today().isoformat()
    save(data)
    print(f"[OK] {site['domain']} → 阶段 {site['stage']}/7 · 到期 {site.get('due') or '未设'}")
    print(f"下一步：{site['next']}")
    if (args.due or args.due_in is not None) and (site.get("reminder") or {}).get("status") == "created":
        print(f"注意：到期日改了，已创建的一次性提醒 {site['reminder'].get('automation_id') or ''} 仍按旧时刻触发；"
              "要么同步改那个自动化，要么跑 geo_reminder.py clear 后重新 plan")
    return 0


def cmd_done(args):
    data = load()
    site = find(data, args.domain)
    if not site:
        print(f"[FAIL] 台账里没有 {args.domain}")
        return 1
    site["status"] = "done"
    site["stage"] = 7
    site["next"] = "已完成，七步走完。后续改版时把 status 改回 active 再跑一轮"
    site["updated"] = date.today().isoformat()
    save(data)
    print(f"[OK] {site['domain']} 已标记完成，不再出现在待处理列表（list --all 仍可查）")
    rem = site.get("reminder") or {}
    if rem.get("status") == "created":
        print(f"注意：这个站还有一次性定时提醒 {rem.get('automation_id') or ''}，走完了记得用自动化工具删除或暂停，别再空跑一轮")
    return 0


def cmd_scan(args):
    """只读扫描：找出做过 GEO 或留过 7 天对比待办的存量项目，绝不写入台账。"""
    import re

    root = os.path.abspath(os.path.expanduser(args.root))
    if not os.path.isdir(root):
        print(f"[FAIL] 目录不存在：{root}")
        return 1
    reg = load()
    skip = {".git", "node_modules", ".output", "dist", "build", ".next", "__pycache__", ".workbuddy", "skills", "Library"}
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if dirpath != root and dirpath[len(root):].count(os.sep) > args.depth:
            dirnames[:] = []
            continue
        state_path = os.path.join(dirpath, ".geo-state.json")
        domain = keyword = scene = ""
        stage = 0
        if os.path.exists(state_path):
            try:
                with open(state_path, encoding="utf-8") as f:
                    d = json.load(f)
                domain = (d.get("domain") or "").strip()
                keyword = d.get("keyword", "")
                scene = d.get("scene", "")
                marks = [int(k) for k in d.get("marks", {}) if str(k).isdigit()]
                stage = max(marks) if marks else 0
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        trace = "geo-state.json" if domain else ""
        if not domain:
            for name in ("TODO.md", "SEO-BACKLOG.md", "DEPLOY.md"):
                p = os.path.join(dirpath, name)
                if not os.path.exists(p):
                    continue
                try:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        head = f.read(20000)
                except OSError:
                    continue
                if re.search(r"ChatGPT 三问|geo_audit|geo_status|GEO", head, flags=re.I):
                    trace = name
                    break
        if not trace:
            continue
        known = find(reg, domain) if domain else None
        hits.append({
            "project": dirpath, "domain": domain, "keyword": keyword,
            "scene": scene, "stage": stage, "trace": trace,
            "known": bool(known),
        })

    print(f"存量项目扫描（只读，没有写入台账）：{root}")
    if not hits:
        print("没找到带 .geo-state.json 或 GEO 待办痕迹的项目。也可以直接对每个已上线项目跑一次 geo_status.py status，它会自动补登记。")
        return 0
    print(f"找到 {len(hits)} 个候选项目，其中 {sum(1 for h in hits if not h['known'])} 个不在台账里。\n")
    for i, h in enumerate(hits, 1):
        flag = "已在台账" if h["known"] else "未登记"
        print(f"{i}. {h['project']} · {flag} · 痕迹 {h['trace']}")
        if h["domain"]:
            print(f"   域名 {h['domain']} · 主词 {h['keyword'] or '未记'} · 已做到第 {h['stage']} 步")
        else:
            print("   没读到域名，需要从项目里的 DEPLOY.md / wrangler 配置或线上地址确认")
        if not h["known"]:
            dom = h["domain"] or "<域名>"
            print(
                f"   登记命令：python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geo_registry.py')}"
                f" add --domain {dom} --project {h['project']}"
                f' --keyword "{h["keyword"] or "<主词>"}" --scene "{h["scene"] or "<场景>"}"'
                f" --stage {min(h['stage'] + 1, 7)}"
            )
        print()
    print("以上只是报告，台账没有变。确认哪些站还要做 GEO 之后，再逐条跑登记命令。")
    return 0


def cmd_path(args):
    data = load()
    site = find(data, args.domain)
    if not site:
        print(f"[FAIL] 台账里没有 {args.domain}")
        return 1
    print(site.get("project") or "")
    return 0


def main():
    ap = argparse.ArgumentParser(description="GEO 跨站台账：有哪些站要做、各在第几步、哪些到期了")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="列出待处理站点（默认子命令）")
    p.add_argument("--all", action="store_true", help="连已完成的站一起列")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("due", help="只列已到期或今天到期的站")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("scan", help="只读扫描存量项目，列报告与建议命令，不写台账")
    p.add_argument("--root", required=True, help="要扫的项目根目录（绝对路径或 ~ 开头）")
    p.add_argument("--depth", type=int, default=4, help="最多往下几层，默认 4")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("add", help="登记新站（上线当天由 ai-subscription-site 第 11 步调用）")
    p.add_argument("--domain", required=True)
    p.add_argument("--project", default="", help="项目在本机的绝对路径")
    p.add_argument("--keyword", default="")
    p.add_argument("--scene", default="")
    p.add_argument("--launched", default="", help="上线日 YYYY-MM-DD，默认今天")
    p.add_argument("--due", default="", help="到期日 YYYY-MM-DD，默认上线日 +7")
    p.add_argument("--due-in", type=int, default=None, help="上线日起 N 天后到期，默认 7")
    p.add_argument("--stage", type=int, default=0)
    p.add_argument("--next", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="更新某站的阶段 / 到期日 / 下一步")
    p.add_argument("--domain", required=True)
    p.add_argument("--stage", type=int, default=None)
    p.add_argument("--next", default="")
    p.add_argument("--due", default="")
    p.add_argument("--due-in", type=int, default=None)
    p.add_argument("--last-audit", default="")
    p.add_argument("--project", default="")
    p.add_argument("--keyword", default="")
    p.add_argument("--scene", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("done", help="标记某站七步走完")
    p.add_argument("--domain", required=True)
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("path", help="输出某站项目绝对路径（给脚本用）")
    p.add_argument("--domain", required=True)
    p.set_defaults(func=cmd_path)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        args.all = False
        return cmd_list(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
