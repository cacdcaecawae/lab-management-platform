# Agent Note: 归还试件绑定借用批次，缺陷整表替换保留必填校验

Status: implemented

## Problem

归还只携带试件编号，旧管理员页面可能归还后来的借用。PATCH 的 partial 标记也会让缺陷条目跳过类型必填，随后比较条目抛出 KeyError。

## Decision

归还必填 loan_id_seen，前端打开确认框前捕获当前借用 id；锁内不匹配返回 409 stale_loan。缺陷条目显式验证 kind 必填，保持父记录 PATCH 和缺陷整体替换语义。

## Alternatives considered

仅加行锁不能识别旧页面。允许旧客户端省略借用 id 会保留错误归还路径，因此不兼容旧归还请求，前后端须一起更新。

## Consequences

- 旧管理员页面以及同一借用人归还后又借的旧请求返回 409 stale_loan，不写入新借用的归还人或说明。无未归还借用仍返回 409 not_on_loan。
- 缺陷条目缺 kind、null、空字符串、非法值返回字段级 400，不保存父字段、缺陷或历史；未传 defects 保留原缺陷，空列表删除全部缺陷。
- 旧客户端归还缺少 loan_id_seen 返回 400，需前后端一起更新并刷新页面。不使用可选字段兼容旧请求，否则无法阻断错误归还。
- 不涉及数据库结构、设备代码或并发模型，因此无新迁移、不触发设备 TLC 同步。
- 当场检索：既有 [试件设计](../feature/2026-11-18-specimens.md) 与本修复部分重叠，仍保留其借用和盲测规则；[组会必填校验](2026-11-18-meeting-nested-required-fields.md) 为同类 DRF 原因，但不新增跨模块依赖。提醒、二维码、通知及模块迁移提案与本修复无关。
- 验证：隔离 SQLite、真实 APIClient/视图/serializer/ORM 的试件测试 21 项通过（原 7 项及新增 14 项；实验记录关联测试不在此隔离配置中）。SQLite 不是 PostgreSQL 并发验证。
- 前端完整 74 项通过，生产构建与类型检查通过（保留原有大包体积警告）。独立只读复核再次通过 21 项后端、4 项新前端和类型检查，未发现阻塞草稿 PR 的问题。原始失败通过相同依赖版本的隔离视图调用复现。
- 标准 scripts/check.sh：笔记校验通过，makemigrations 显示无变更，但 PostgreSQL 127.0.0.1:5432 拒绝连接，数据库测试 setup 无法运行；不声称全后端通过。
- 未验证：真实 PostgreSQL（含并发）、浏览器隔离流程。仓库浏览器启动脚本要求 Windows/PowerShell，当前环境未启动该流程；已经维护对应验收清单。
