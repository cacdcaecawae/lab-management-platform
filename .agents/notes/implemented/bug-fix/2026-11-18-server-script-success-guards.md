# Agent Note: 更新成功保留启动前提，恢复固定快照编号

Status: implemented

## Problem

[发版与备份方案](../../implemented/process/2026-11-18-release-update-backup.md)保持有效，但更新脚本忽略 Compose 启动失败，旧容器仍响应时会误报成功。恢复脚本两次解析 latest，期间完成的新备份可使数据库和文件来自不同快照。

## Decision

更新仅在启动和健康检查均成功时返回成功，否则进入现有回退流程。恢复开始时将 latest 解析为 lab 主机的唯一完整快照编号，后续两步复用该编号；解析失败或没有快照时不得停站。从 restic snapshots 的稳定 JSON 提取完整 id 字段，要求恰好一个 64 位十六进制值；字符串内转义引号不能匹配该字段。不依赖 backend 镜像或新增宿主机解释器，灾难恢复时应用镜像不可用也不影响快照选择。

用户授权确定问题以 PR 修复；只在独立分支实现，不修改原 PR、主分支或部署。

## Alternatives considered

- 解析 restic 人类输出：无需解析器，但格式不适合作为脚本契约，且通常仅提供短编号。
- 宿主机新增 jq：通用解析更便利，但增加部署依赖；这里只有 restic 自己输出的固定字段。
- 使用 backend 镜像的 Python：可以完整解析 JSON，但灾难恢复可能正好缺少或无法启动应用镜像，不应为选择快照引入这一前提。
- 全运维互斥锁：可处理更多并发操作，但本次仅固定同一恢复使用的快照，不扩大到整体运维编排。

## Consequences

新增 7 个 unittest 回归，由 backend/tests/test_server_scripts.py 纳入现有 pytest/CI。真实 shell 脚本在隔离临时目录配合命令替身运行，7 项全部通过：启动失败旧健康仍通过也必须回退；正常更新和健康失败回退不变；latest 中途变化仍对数据库和文件使用同一 ID；无快照/查询失败不得停止网站；显式 ID 和 db-only 保持兼容。

### 验证边界

两个核心回归在原 PR 基线失败，修复后通过。另用官方 restic 0.19.1 和隔离临时仓库验证 JSON 选择及编号提取：A 快照固定后新增 B，固定编号 dump 返回 A，latest dump 返回 B。bash -n 和 git diff --check 通过。命令替身不是 Docker/PostgreSQL 集成。本机无 Docker；完整 scripts/check.sh 在三项笔记校验通过后因缺少 Django 停止，迁移、全量后端、前端未运行。快照被删除仍会失败，固定 ID 不是备份锁；现有数据库迁移行数判断和文件恢复失败恢复策略不在本次范围。
