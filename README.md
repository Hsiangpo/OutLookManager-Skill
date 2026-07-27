# OutLookManager-Skill

OutLook Manager 账号池的项目级管理 skill（AI agent 用）：增删改查、批量导入、取号/还号、测活、清理过期账号、API Key 管理。

目标服务：<https://outlook-manager.gpteamservices.com>（接口文档：`/docs`）

## 安装（项目级）

```bash
# 在你的项目根目录执行（Claude Code）
git clone https://github.com/Hsiangpo/OutLookManager-Skill .claude/skills/outlook-manager

# Codex 则装到
git clone https://github.com/Hsiangpo/OutLookManager-Skill .agents/skills/outlook-manager

# 配置凭证
cd .claude/skills/outlook-manager
cp references/env.example .env
chmod 600 .env
# 编辑 .env 填入 OUTLOOK_MANAGER_API_KEY（调用方）和/或 OUTLOOK_MANAGER_ADMIN_JWT（管理员）
```

## 用法

```bash
python3 scripts/outlook_manager.py stats
python3 scripts/outlook_manager.py accounts list --status fresh
python3 scripts/outlook_manager.py acquire --count 2
python3 scripts/outlook_manager.py release <uuid> --status fresh
python3 scripts/outlook_manager.py status-batch banned --ids uuid1,uuid2
python3 scripts/outlook_manager.py check-batch --statuses fresh --limit 50
python3 scripts/outlook_manager.py purge-expired            # dry-run
python3 scripts/outlook_manager.py purge-expired --apply --confirm PURGE:expired:12
```

完整命令见 [SKILL.md](SKILL.md)。

## 约定

- 输出默认脱敏（token/key/JWT 截断），`--show-secrets` 才显示完整值。
- 破坏性操作先 dry-run 拿确认短语，再 `--apply --confirm <短语>` 执行。
- 凭证只放 skill 目录的 `.env`（已 gitignore），shell 环境变量优先。
