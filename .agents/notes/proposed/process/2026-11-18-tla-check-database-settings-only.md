# Agent Note: 设备并发模型检查只看 settings.py 的数据库设置

Status: proposed

## Problem

`.claude/skills/verify-equipment-tla/scripts/check.sh` 把整个 `backend/config/settings.py` 列在覆盖范围里，只要这个文件有改动就返回退出码 2（"被覆盖的代码变了，要人工核对"）。模型真正依赖的只是数据库的事务行为：隔离级别（默认 READ COMMITTED）和没有开 `ATOMIC_REQUESTS`（见 SKILL.md 的"假设"）。

2026-11-18 一天里，三次与设备无关的改动都触发了它：新增 `workbench`、`system`、`specimens` 三个 app，以及 `APP_VERSION` 设置。每次都要人工核对一遍，再提交一条只改 `SYNC` 的提交。以后每加一个模块都会这样，提醒变成了噪音，真正改数据库设置的那一次反而容易被当成又一次例行公事。

## Proposal

- `check.sh` 的覆盖清单里不再放整个 `settings.py`，改为比较两段文字：
  - `DATABASES = {` 到与它配对的 `}` 之间的内容，用 `git show "$SYNC":backend/config/settings.py` 和工作区文件各取一次，再比较；
  - 全文里含 `ATOMIC_REQUESTS`、`isolation_level`、`CONN_MAX_AGE`、`DISABLE_SERVER_SIDE_CURSORS` 的行。
- 任何一段不同就和现在一样列出差异、返回 2；其余覆盖文件（`equipment/views.py`、`serializers.py`、`models.py`、`EquipmentFormDialog.vue`）不变。
- SKILL.md 的覆盖范围表和"假设"一节同步改写，说明 settings.py 现在只看这两段。
- 提取用 `sed -n '/^DATABASES = {/,/^}/p'`，不新增工具。

## Alternatives considered

- **维持现状**：最保守。但每加一个 app 都要多一条 SYNC 提交，提醒会被忽视。
- **把 settings.py 整个移出覆盖范围**：最省事。但真改了隔离级别或开了 `ATOMIC_REQUESTS` 时，模型的前提就不成立了，必须有人重新核对。
- **把数据库设置拆到单独的 `config/database.py`**：覆盖清单可以继续按文件列。但要改设置的加载方式，Django 的惯例是放在 settings.py 里，为了检查脚本去改项目结构不划算。

## Acceptance criteria

- 只在 `INSTALLED_APPS` 里加一行时，`check.sh` 退出码为 0，"covered code changed" 一节显示 none。
- 改 `DATABASES` 里的任意一行（例如加 `"OPTIONS": {"isolation_level": ...}`），或在任意位置加 `ATOMIC_REQUESTS = True`，退出码为 2，并列出差异。
- 两种情况都在临时工作区里实际跑过，写进 SKILL.md 的"运行"一节。

## Risks

- 别的数据库相关设置如果写在 `DATABASES` 之外、又不含上面几个关键词（例如自定义的数据库路由），就会漏检。这类设置目前不存在；以后出现时，把关键词加进清单。
