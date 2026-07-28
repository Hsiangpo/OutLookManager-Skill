#!/usr/bin/env python3
"""OutLook Manager CLI — 账号池管理命令行。

认证优先级：环境变量 > skill 目录 .env
  OUTLOOK_MANAGER_BASE_URL  服务地址
  OUTLOOK_MANAGER_ADMIN_JWT 管理员 JWT（管理接口）
  OUTLOOK_MANAGER_API_KEY   调用方 Key（取号/还号/上报）
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://outlook-manager.gpteamservices.com"


class CliError(Exception):
    pass


def skill_dir():
    return Path(__file__).resolve().parents[1]


def load_env_file(path):
    if not path or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def redact(text):
    """默认脱敏：长 token 只留前缀。"""
    if not text:
        return text
    s = str(text)
    # MSA token
    s = re.sub(r"(M\.C[0-9A-Z_]+[._-])[A-Za-z0-9*!$_-]{20,}", r"\1...REDACTED", s)
    # om_ key
    s = re.sub(r"(om_[A-Za-z0-9_-]{4})[A-Za-z0-9_-]{16,}", r"\1...REDACTED", s)
    # JWT
    s = re.sub(r"(eyJ[A-Za-z0-9_-]{8})[A-Za-z0-9_.-]{20,}", r"\1...REDACTED", s)
    return s


def print_json(data, show_secrets=False):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    print(text if show_secrets else redact(text))


class Client:
    def __init__(self, base_url):
        if not base_url:
            raise CliError("缺少 OUTLOOK_MANAGER_BASE_URL（写进 skill 目录 .env 或环境变量）")
        self.base = base_url.rstrip("/") + "/api/v1"

    def request(self, method, path, token=None, payload=None, form=None):
        url = self.base + path
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            # 简单 multipart：字段都是文本时用 data= 的形式（import 用）
            body = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8")
                return resp.status, json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {"raw": text[:300]}
            return exc.code, data
        except urllib.error.URLError as exc:
            raise CliError(f"请求失败: {exc.reason}")


def get_config():
    load_env_file(skill_dir() / ".env")
    return {
        "base_url": os.environ.get("OUTLOOK_MANAGER_BASE_URL", DEFAULT_BASE_URL),
        "admin_jwt": os.environ.get("OUTLOOK_MANAGER_ADMIN_JWT", ""),  # 可选：Web 会话凭证
        "api_key": os.environ.get("OUTLOOK_MANAGER_API_KEY", ""),
    }


def _token(cfg):
    """统一凭证：API Key 优先（全能），没有则回退管理员 JWT。"""
    return cfg["api_key"] or cfg["admin_jwt"]


def need_admin(cfg):
    if not _token(cfg):
        raise CliError("该命令需要凭证：在 .env 填 OUTLOOK_MANAGER_API_KEY（Web /keys 页创建）")
    return _token(cfg)


def need_key(cfg):
    if not cfg["api_key"]:
        raise CliError("该命令需要 API Key：在 .env 填 OUTLOOK_MANAGER_API_KEY（Web /keys 页创建）")
    return cfg["api_key"]


def check(resp_status, data, expect=(200, 201, 204)):
    if resp_status not in expect:
        raise CliError(f"HTTP {resp_status}: {json.dumps(data, ensure_ascii=False)[:300]}")
    return data


# ---------- 命令实现 ----------

def cmd_login(client, cfg, args):
    status, data = client.request("POST", "/auth/login", payload={"password": args.password})
    check(status, data)
    if args.show_secrets:
        print_json(data, show_secrets=True)
        print("\n把 access_token 填进 .env 的 OUTLOOK_MANAGER_ADMIN_JWT", file=sys.stderr)
    else:
        tok = data.get("access_token", "")
        print_json({"access_token": tok[:12] + "...（--show-secrets 看完整）", "token_type": data.get("token_type")})


def cmd_stats(client, cfg, args):
    status, data = client.request("GET", "/stats", token=need_admin(cfg))
    print_json(check(status, data), args.show_secrets)


def cmd_accounts_list(client, cfg, args):
    qs = []
    if args.status:
        qs.append(f"status_filter={urllib.parse.quote(args.status)}")
    if args.search:
        qs.append(f"search={urllib.parse.quote(args.search)}")
    qs.append(f"page={args.page}")
    qs.append(f"page_size={args.page_size}")
    status, data = client.request("GET", "/accounts?" + "&".join(qs), token=need_admin(cfg))
    check(status, data)
    if args.json:
        print_json(data, args.show_secrets)
        return
    print(f"total={data['total']} page={data['page']}/{-(-data['total']//data['page_size'])}")
    for a in data["items"]:
        token_disp = a["refresh_token"][:10] + "…" if a["refresh_token"] else "-"
        print(f'{a["id"]}  {a["email"]:<38} {a["status"]:<9} rt={token_disp:<12} checked={a["last_checked_at"] or "-"}')


def cmd_accounts_get(client, cfg, args):
    status, data = client.request("GET", f"/accounts/{args.id}", token=need_admin(cfg))
    print_json(check(status, data), args.show_secrets)


def cmd_accounts_delete(client, cfg, args):
    jwt = need_admin(cfg)
    status, data = client.request("GET", f"/accounts/{args.id}", token=jwt)
    check(status, data)
    expected = f"DELETE:{args.id}"
    if not args.apply:
        print_json({"dry_run": True, "action": "delete", "account": data.get("email"),
                    "confirm": expected}, args.show_secrets)
        return
    if args.confirm != expected:
        raise CliError(f"确认短语不匹配，需要: {expected}")
    status, data = client.request("DELETE", f"/accounts/{args.id}", token=jwt)
    check(status, data)
    print_json({"applied": True, "deleted": args.id}, args.show_secrets)


def cmd_purge_expired(client, cfg, args):
    """删除所有 expired（可选含 banned）账号。"""
    jwt = need_admin(cfg)
    statuses = ["expired"] + (["banned"] if args.include_banned else [])
    # 拉全量
    doomed = []
    page = 1
    while True:
        status, data = client.request(
            "GET", f"/accounts?status_filter={','.join(statuses)}&page={page}&page_size=100", token=jwt)
        check(status, data)
        doomed.extend(data["items"])
        if page * 100 >= data["total"]:
            break
        page += 1
    expected = f"PURGE:{','.join(statuses)}:{len(doomed)}"
    if not args.apply:
        print_json({"dry_run": True, "action": "purge",
                    "statuses": statuses, "count": len(doomed),
                    "sample": [a["email"] for a in doomed[:10]],
                    "confirm": expected}, args.show_secrets)
        return
    if args.confirm != expected:
        raise CliError(f"确认短语不匹配，需要: {expected}")
    deleted = 0
    for a in doomed:
        status, _ = client.request("DELETE", f"/accounts/{a['id']}", token=jwt)
        if status == 204:
            deleted += 1
    print_json({"applied": True, "deleted": deleted, "requested": len(doomed)}, args.show_secrets)


def cmd_import(client, cfg, args):
    path = Path(args.file)
    if not path.is_file():
        raise CliError(f"文件不存在: {path}")
    text = path.read_text(encoding="utf-8")
    status, data = client.request(
        "POST", "/accounts/import", token=need_admin(cfg),
        form={"text": text, "imported_from": args.source})
    print_json(check(status, data), args.show_secrets)


def cmd_acquire(client, cfg, args):
    status, data = client.request(
        "POST", "/accounts/acquire", token=need_key(cfg),
        payload={"count": args.count, "prefer_verified": args.prefer_verified})
    if status == 404:
        print_json({"ok": False, "error": "无可用账号", "accounts": []}, args.show_secrets)
        return
    check(status, data)
    print_json(data, args.show_secrets)


def cmd_release(client, cfg, args):
    status, data = client.request(
        "POST", f"/accounts/{args.id}/release", token=need_key(cfg),
        payload={"status": args.status})
    check(status, data)
    print_json({"applied": True, "id": args.id, "status": args.status}, args.show_secrets)


def cmd_status(client, cfg, args):
    status, data = client.request(
        "PATCH", f"/accounts/{args.id}/status", token=need_key(cfg),
        payload={"status": args.status, "notes": args.notes})
    check(status, data)
    print_json({"applied": True, "id": args.id, "status": args.status}, args.show_secrets)


def cmd_status_batch(client, cfg, args):
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    status, data = client.request(
        "POST", "/accounts/status-batch", token=need_key(cfg),
        payload={"ids": ids, "status": args.status, "notes": args.notes})
    print_json(check(status, data), args.show_secrets)


def cmd_delete_batch(client, cfg, args):
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    expected = f"DELETE-BATCH:{len(ids)}"
    if not args.apply:
        print_json({"dry_run": True, "action": "delete-batch", "count": len(ids), "confirm": expected}, args.show_secrets)
        return
    if args.confirm != expected:
        raise CliError(f"确认短语不匹配，需要: {expected}")
    status, data = client.request("POST", "/accounts/delete-batch", token=need_admin(cfg),
                                  payload={"ids": ids})
    print_json(check(status, data), args.show_secrets)


def cmd_check(client, cfg, args):
    status, data = client.request("POST", f"/accounts/{args.id}/check", token=need_admin(cfg))
    print_json(check(status, data), args.show_secrets)


def cmd_check_batch(client, cfg, args):
    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
    status, data = client.request(
        "POST", "/accounts/check-batch", token=need_admin(cfg),
        payload={"filter_status": statuses, "limit": args.limit})
    print_json(check(status, data), args.show_secrets)


def cmd_keys_list(client, cfg, args):
    status, data = client.request("GET", "/keys", token=need_admin(cfg))
    check(status, data)
    if args.json:
        print_json(data, args.show_secrets)
        return
    for k in data:
        flag = "已撤销" if k["revoked"] else "生效中"
        print(f'{k["id"]}  {k["name"]:<24} {k["key_prefix"]}…  {flag}  last_used={k["last_used_at"] or "-"}')


def cmd_keys_revoke(client, cfg, args):
    jwt = need_admin(cfg)
    expected = f"REVOKE:{args.id}"
    if not args.apply:
        print_json({"dry_run": True, "action": "revoke-key", "id": args.id, "confirm": expected})
        return
    if args.confirm != expected:
        raise CliError(f"确认短语不匹配，需要: {expected}")
    status, data = client.request("DELETE", f"/keys/{args.id}", token=jwt)
    check(status, data)
    print_json({"applied": True, "revoked": args.id})


# ---------- 参数解析 ----------

def add_common(p):
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--show-secrets", action="store_true", help="显示完整凭证（默认脱敏）")


def add_apply(p):
    p.add_argument("--apply", action="store_true", help="确认执行写操作")
    p.add_argument("--confirm", help="dry-run 输出的确认短语")


def build_parser():
    parser = argparse.ArgumentParser(prog="outlook-manager", description="OutLook Manager 账号池 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="管理员登录获取 JWT")
    p.add_argument("--password", required=True)
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("stats", help="统计概览")
    add_common(p)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("accounts", help="账号查询")
    acc_sub = p.add_subparsers(dest="sub", required=True)
    l = acc_sub.add_parser("list")
    l.add_argument("--status", help="状态过滤，逗号分隔")
    l.add_argument("--search", help="邮箱模糊搜索")
    l.add_argument("--page", type=int, default=1)
    l.add_argument("--page-size", type=int, default=20)
    add_common(l)
    l.set_defaults(func=cmd_accounts_list)
    g = acc_sub.add_parser("get")
    g.add_argument("id")
    add_common(g)
    g.set_defaults(func=cmd_accounts_get)
    d = acc_sub.add_parser("delete")
    d.add_argument("id")
    add_apply(d)
    d.add_argument("--show-secrets", action="store_true")
    d.set_defaults(func=cmd_accounts_delete)

    p = sub.add_parser("purge-expired", help="删除所有 expired 账号（--include-banned 连 banned 一起删）")
    p.add_argument("--include-banned", action="store_true")
    add_apply(p)
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_purge_expired)

    p = sub.add_parser("import", help="从文件导入账号")
    p.add_argument("file")
    p.add_argument("--source", default="cli-import", help="来源标记")
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("acquire", help="取号")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--prefer-verified", action="store_true")
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_acquire)

    p = sub.add_parser("release", help="还号")
    p.add_argument("id")
    p.add_argument("--status", default="fresh", choices=["fresh", "banned", "locked", "expired"])
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("status", help="上报单账号状态")
    p.add_argument("id")
    p.add_argument("status", choices=["fresh", "verified", "banned", "locked", "expired"])
    p.add_argument("--notes", default="")
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("status-batch", help="批量上报状态")
    p.add_argument("status", choices=["fresh", "verified", "banned", "locked", "expired"])
    p.add_argument("--ids", required=True, help="逗号分隔的账号 ID")
    p.add_argument("--notes", default="")
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_status_batch)

    p = sub.add_parser("delete-batch", help="批量删除账号")
    p.add_argument("ids", help="逗号分隔的账号 ID")
    add_apply(p)
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_delete_batch)

    p = sub.add_parser("check", help="单账号测活")
    p.add_argument("id")
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("check-batch", help="批量测活")
    p.add_argument("--statuses", default="fresh,in_use,verified")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--show-secrets", action="store_true")
    p.set_defaults(func=cmd_check_batch)

    p = sub.add_parser("keys", help="API Key 管理")
    k_sub = p.add_subparsers(dest="sub", required=True)
    kl = k_sub.add_parser("list")
    add_common(kl)
    kl.set_defaults(func=cmd_keys_list)
    kr = k_sub.add_parser("revoke")
    kr.add_argument("id")
    add_apply(kr)
    kr.set_defaults(func=cmd_keys_revoke)

    return parser


def main():
    args = build_parser().parse_args()
    cfg = get_config()
    client = Client(cfg["base_url"])
    try:
        args.func(client, cfg, args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
