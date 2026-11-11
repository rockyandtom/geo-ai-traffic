#!/usr/bin/env python3
"""IndexNow 提交：生成 key 文件、核对线上 key、批量推送 URL。

IndexNow 只推给 Bing / Yandex / Naver / Seznam，Google 不参与，所以它是"补 Bing 侧发现速度"，
不是提交给 Google。提交成功也不等于收录。

三个子命令：

    # 1. 生成 key 并写进站点 public 目录（把文件一起提交到仓库，随构建上线）
    python indexnow_submit.py keygen --domain example.com --out ./public

    # 2. 核对线上 key 文件是否真的可访问、内容是否一致（必须是 200，不能是 30x）
    python indexnow_submit.py check --domain example.com --key <key>

    # 3. 提交 URL：从 sitemap 取，或从文本文件逐行取；先 --dry-run 看要推哪些
    python indexnow_submit.py submit --domain example.com --key <key> --sitemap https://example.com/sitemap.xml --dry-run
    python indexnow_submit.py submit --domain example.com --key <key> --urls new-urls.txt

退出码：0 成功 / 1 提交被拒或 key 校验失败 / 2 参数或网络致命错误。
"""

import argparse
import json
import re
import secrets
import ssl
import sys
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

STATUS_MEANING = {
    200: "提交成功",
    202: "已接受，key 待验证（稍后回查）",
    400: "请求格式错误（JSON 结构或参数不对）",
    403: "key 无效：线上找不到 key 文件，或内容与提交的 key 不一致",
    422: "URL 与 host 不匹配，或 key 与 keyLocation 对不上",
    429: "请求过于频繁，今天别重推了",
}


def normalize_domain(raw):
    """去掉协议、路径、结尾斜杠，保留 host 原样（含 www 与否，必须与线上一致）。"""
    d = raw.strip()
    d = re.sub(r"^https?://", "", d, flags=re.I)
    d = d.split("/", 1)[0].strip().rstrip(".")
    return d


def http(url, method="GET", payload=None, timeout=30):
    """返回 (status, body_text, error)。不抛异常。"""
    ctx = ssl.create_default_context()
    handlers = [urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)]
    opener = urllib.request.build_opener(*handlers)
    data = None
    headers = {"User-Agent": BROWSER_UA, "Accept": "*/*"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(20_000).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read(20_000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        return e.code, body, None
    except Exception as e:  # noqa: BLE001
        return None, "", f"{type(e).__name__}: {e}"


def cmd_keygen(args):
    domain = normalize_domain(args.domain)
    key = (args.key or secrets.token_hex(16)).strip()
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,128}", key):
        print("[FAIL] key 只允许字母数字和短横线，长度 8-128")
        return 2
    path = f"{args.out.rstrip('/')}/{key}.txt"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(key + "\n")
    except OSError as e:
        print(f"[FAIL] 写文件失败：{e}")
        print("       → 目录不存在就先建好，例如 mkdir -p ./public")
        return 2
    print(f"[OK] key 文件已写入 {path}")
    print(f"     key            {key}")
    print(f"     上线后应可访问  https://{domain}/{key}.txt")
    print("     下一步         把该文件提交到仓库，部署后用 check 子命令核对线上返回")
    return 0


def cmd_check(args):
    domain = normalize_domain(args.domain)
    key = args.key.strip()
    url = f"https://{domain}/{key}.txt"
    status, body, err = http(url)
    if err:
        print(f"[FAIL] 请求失败：{err}")
        return 2
    print(f"GET {url} → {status}")
    if status != 200:
        print("[FAIL] key 文件线上不可用。必须是 200 直出")
        if status in (301, 302, 307, 308):
            print("       → 被重定向了：www 与非 www 不一致，或路由把 .txt 吃掉了")
        elif status == 404:
            print("       → 文件没部署上去：public 目录放错、构建漏拷、或路径大小写不一致")
        return 1
    if body.strip() != key:
        print("[FAIL] 文件内容与 key 不一致")
        print(f"       期望：{key}")
        print(f"       实际：{body.strip()[:80]}")
        print("       → 文件里只放 key 本身，不要加引号、空格、注释或 BOM")
        return 1
    print("[OK] key 文件 200 且内容一致，可以提交")
    return 0


def extract_urls_from_sitemap(xml, host):
    """从 sitemap 或 sitemapindex 里取 loc，一层子 sitemap 也会跟进去。"""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, flags=re.I)
    return [u for u in locs if host in u]


def collect_from_sitemap(sitemap_url, host, depth=1):
    status, body, err = http(sitemap_url)
    if err or status != 200:
        print(f"[WARN] 取 sitemap 失败：{err or status}")
        return []
    urls = []
    if "<sitemapindex" in body.lower() and depth > 0:
        for child in extract_urls_from_sitemap(body, host):
            urls.extend(collect_from_sitemap(child, host, depth - 1))
        return urls
    return extract_urls_from_sitemap(body, host)


def cmd_submit(args):
    domain = normalize_domain(args.domain)
    key = args.key.strip()
    urls = []

    if args.urls:
        try:
            with open(args.urls, encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except OSError as e:
            print(f"[FAIL] 读 URL 文件失败：{e}")
            return 2
    if args.sitemap:
        urls.extend(collect_from_sitemap(args.sitemap, domain))

    deduped, seen = [], set()
    for u in urls:
        if not u.startswith("http"):
            u = f"https://{u}"
        if domain not in u:
            continue
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)

    if not deduped:
        print("[FAIL] 没有可提交的 URL：sitemap 取不到，或 URL 与 host 不匹配")
        return 2

    if args.limit and args.limit > 0:
        deduped = deduped[: args.limit]

    if len(deduped) > 10000:
        print(f"[WARN] 一次最多 10000 条，本次只提交前 10000 条（共 {len(deduped)} 条）")
        deduped = deduped[:10000]

    print(f"host   {domain}")
    print(f"条数   {len(deduped)}")
    for u in deduped[:10]:
        print(f"       {u}")
    if len(deduped) > 10:
        print(f"       ... 其余 {len(deduped) - 10} 条")

    if args.dry_run:
        print("\n[dry-run] 没有真的提交。去掉 --dry-run 才会推送。")
        return 0

    payload = {
        "host": domain,
        "key": key,
        "keyLocation": f"https://{domain}/{key}.txt",
        "urlList": deduped,
    }
    status, body, err = http(args.endpoint, method="POST", payload=payload)
    if err:
        print(f"[FAIL] 提交失败：{err}")
        return 2
    meaning = STATUS_MEANING.get(status, "未知返回码，看 body")
    print(f"\nPOST {args.endpoint} → {status}  {meaning}")
    if body.strip():
        print(f"body: {body.strip()[:300]}")
    if status in (200, 202):
        print("下一步：Bing Webmaster Tools 里看提交记录与收录状态。提交成功不代表已收录。")
        return 0
    return 1


def main():
    ap = argparse.ArgumentParser(description="IndexNow 提交工具（Bing / Yandex / Naver / Seznam）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("keygen", help="生成 key 并写入站点 public 目录")
    p1.add_argument("--domain", required=True, help="站点域名，含不含 www 要与线上一致")
    p1.add_argument("--out", default="./public", help="key 文件写到哪个目录，默认 ./public")
    p1.add_argument("--key", default="", help="复用已有 key，不给就随机生成 32 位")
    p1.set_defaults(func=cmd_keygen)

    p2 = sub.add_parser("check", help="核对线上 key 文件")
    p2.add_argument("--domain", required=True)
    p2.add_argument("--key", required=True)
    p2.set_defaults(func=cmd_check)

    p3 = sub.add_parser("submit", help="批量提交 URL")
    p3.add_argument("--domain", required=True)
    p3.add_argument("--key", required=True)
    p3.add_argument("--sitemap", default="", help="sitemap 地址，支持 sitemapindex 跟一层")
    p3.add_argument("--urls", default="", help="URL 列表文件，每行一个，只推增量时用它")
    p3.add_argument("--limit", type=int, default=0, help="最多提交多少条，0 表示不限制")
    p3.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"默认 {DEFAULT_ENDPOINT}")
    p3.add_argument("--dry-run", action="store_true", help="只打印要提交什么，不真发")
    p3.set_defaults(func=cmd_submit)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
