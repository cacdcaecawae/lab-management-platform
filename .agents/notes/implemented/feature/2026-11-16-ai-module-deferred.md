# Agent Note: AI 模块本期不做（原 D2）

Status: implemented

## 问题

开发手册第一期包含 AI 额度管理（AIAccount）和两条 AI 验收标准；AI 网关（Magpie）是独立系统。开发指令明确 AI 暂缓。

## 决策

- 不建 AIAccount，不留 Magpie 接口，平台中没有 AI 相关代码。
- 开发手册第一期的 AI 额度条目和两条 AI 验收标准不执行。
- "AI 额度与 Magpie 对接"列在 `docs/development-plan.md` 的"不做 / 暂缓"里。

## 曾考虑的替代方案

- **先预留 AIAccount 模型或 Magpie 接口**：方便以后接入；但开发指令明确暂缓，所以不留。

## 后果

- 收益：第一期范围更小。
- 代价与重访信号：重新启动 AI 模块时，需要按开发手册的 AI 部分重新设计模型、接口和验收标准；届时新写一篇笔记并链接本篇。
