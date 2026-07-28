---
name: outlook-manager
description: Use when managing the OutLook Manager account pool (outlook-manager.gpteamservices.com): account CRUD, batch import, acquire/release accounts for signup workers, health checks, purging expired/banned accounts, API key management, or any Outlook account-pool administration.
---

# OutLook Manager Skill

Manage the OutLook Manager account pool via the bundled CLI. Do not use ad hoc `curl`.

## Setup

1. Copy `references/env.example` to `.env` in this skill directory and fill `OUTLOOK_MANAGER_API_KEY` — an `om_` key created in the Web UI `/keys` page. One key covers every command (acquire/release/status/import/check/purge/keys/stats).
   - `OUTLOOK_MANAGER_ADMIN_JWT` is optional and only needed for Web-console-style workflows; the API key alone is enough.
2. `chmod 600 .env`. The `.env` is gitignored; never commit credentials.
3. Shell environment variables take precedence over `.env` (useful for switching between prod/test).

## Workflow

1. Read first: `stats`, `accounts list --status fresh`, `accounts get <id>`.
2. Writes: destructive commands (`accounts delete`, `purge-expired`, `keys revoke`) print a dry-run with a `confirm` phrase; re-run with `--apply --confirm <phrase>` to execute.
3. Verify after writes: re-list or check `stats`.

## Commands

```bash
SKILL=.claude/skills/outlook-manager   # or .agents/skills/outlook-manager

# Auth（可选：仅需要管理员 JWT 的场景；平时一个 API Key 就够）
python3 $SKILL/scripts/outlook_manager.py login --password <pwd> --show-secrets

# Read
python3 $SKILL/scripts/outlook_manager.py stats
python3 $SKILL/scripts/outlook_manager.py accounts list --status fresh
python3 $SKILL/scripts/outlook_manager.py accounts list --search alice --json
python3 $SKILL/scripts/outlook_manager.py accounts get <uuid>

# Import (admin)
python3 $SKILL/scripts/outlook_manager.py import /path/to/pool.txt --source OutlookRegister

# Caller flow (API key)
python3 $SKILL/scripts/outlook_manager.py acquire --count 2
python3 $SKILL/scripts/outlook_manager.py acquire --count 1 --purpose gpt      # 排除GPT已用，取出后标记gpt_used
python3 $SKILL/scripts/outlook_manager.py acquire --count 1 --purpose claude   # 排除Claude已用
python3 $SKILL/scripts/outlook_manager.py acquire --count 1 --show-secrets   # full refresh_token
python3 $SKILL/scripts/outlook_manager.py release <uuid> --status fresh
python3 $SKILL/scripts/outlook_manager.py status <uuid> banned --notes "GPT signup banned"
python3 $SKILL/scripts/outlook_manager.py status-batch banned --ids uuid1,uuid2,uuid3
python3 $SKILL/scripts/outlook_manager.py flags uuid1,uuid2 --gpt true          # 标记GPT已用
python3 $SKILL/scripts/outlook_manager.py flags uuid1,uuid2 --sold true         # 标记已出售
python3 $SKILL/scripts/outlook_manager.py flags uuid1 --claude false            # 取消Claude已用
python3 $SKILL/scripts/outlook_manager.py delete-batch --ids uuid1,uuid2
python3 $SKILL/scripts/outlook_manager.py delete-batch --ids uuid1,uuid2 --apply --confirm DELETE-BATCH:2

# Health (admin)
python3 $SKILL/scripts/outlook_manager.py check <uuid>
python3 $SKILL/scripts/outlook_manager.py check-batch --statuses fresh,in_use --limit 50

# Destructive (dry-run first, then --apply --confirm)
python3 $SKILL/scripts/outlook_manager.py accounts delete <uuid>
python3 $SKILL/scripts/outlook_manager.py accounts delete <uuid> --apply --confirm DELETE:<uuid>
python3 $SKILL/scripts/outlook_manager.py purge-expired
python3 $SKILL/scripts/outlook_manager.py purge-expired --apply --confirm PURGE:expired:12
python3 $SKILL/scripts/outlook_manager.py purge-expired --include-banned
python3 $SKILL/scripts/outlook_manager.py keys list
python3 $SKILL/scripts/outlook_manager.py keys revoke <uuid>

# Raw escape hatch is intentionally absent: use the documented commands only.
```

## Safety Notes

- Output is redacted by default (refresh_token / API keys / JWTs truncated). Use `--show-secrets` only on a local operator machine; never paste that output into chat, docs, commits, or tickets.
- `acquire` returns `{"ok": false, "error": "无可用账号"}` when the pool is empty (server is HTTP 404).
- Accounts left in `in_use` are auto-recycled to `fresh` after 30 minutes by the server.
- Server auto health-checks hourly; failed checks mark accounts `expired`.
