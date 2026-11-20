# Agent Note: 前端其余页面迁入 src/modules（模块化试点第二步）

Status: implemented

## Problem

[模块边界](../../implemented/architecture/2026-11-17-module-boundaries.md)先只把 `equipment`、`knowledge` 搬进了 `src/modules/`，约定试点之后再决定其余页面怎么搬。之后新做的 `specimens` 也直接放进了 `src/modules/`，规则（页面只能引用别的模块的 `api`）在设备详情页、知识库页、实验记录页上都没有遇到问题。

但现在新旧两种结构并存：

- 21 个业务页面和对应的 `api/*.ts` 还在 `src/views/`、`src/api/`；
- 新人或别的代理不知道该放哪里；
- `scripts/check_module_deps.py` 只能把 `src/views/` 整体当成"页面"，检查不出其中的跨模块引用。

## Decision

业务页面按模块组织，接口和路由契约不变。

| 模块目录 | 页面 | 接口文件 | 只有本模块用的组件 |
|---|---|---|---|
| `research` | ExperimentsView、ExperimentEditView、RunsView、RunEditView | `api/research.ts` | ParamsEditor |
| `datasets` | DatasetsView、DatasetDetailView | `api/datasets.ts` | PinnedDatasets（如果实验、周报也用它，就留在公共 components） |
| `reports` | ReportsView、ReportEditView | `api/reports.ts` | — |
| `projects` | ProjectsView、ProjectDetailView | `api/projects.ts` | ProjectFormDialog |
| `members` | MembersView | `api/members.ts` | — |
| `inventory` | ConsumablesView | `api/inventory.ts` | — |
| `procurement` | PurchasesView、PurchaseDetailView、ReimbursementsView、FundsView | `api/procurement.ts` | — |
| `meetings` | MeetingsView、MeetingDetailView | `api/meetings.ts` | — |
| `achievements` | AchievementsView | `api/achievements.ts` | — |
| `workbench` | WorkbenchView | `api/dashboard.ts` | — |
| `system` | SystemView | `api/system.ts` | SystemMail、SystemGroups、SystemAccounts、SystemVersion |

- 留在 `src/views/` 的只有应用外壳：LoginView、ChangePasswordView、NotFoundView。
- 留在 `src/api/` 的只有 `client.ts`、`auth.ts`、`types.ts`，以及以后的 `notifications.ts`、`search.ts` 这类给布局用的公共接口。
- 每个模块一个 `index.ts` 导出路由；`router/index.ts` 只负责拼接。路由的 `name`、`path`、`meta` 一个字都不改。
- 测试文件跟着被测文件走。`api/modules.test.ts` 里的用例按模块拆到各自目录，内容不变。
- `scripts/check_module_deps.py`：迁完后 `src/views/` 只剩外壳，删掉"`views/` 视为页面"那个特例，外壳页面不能引用业务模块。`backend/tests/test_module_deps.py` 相应改测试。
- `PinnedDatasets` 被实验、处理记录、周报三个模块使用，留在公共 `components/`。动手前用 `grep` 确认每个组件的实际使用者，再决定搬不搬。
- 类型（`api/types.ts`）这次不拆，理由见下文。

## Alternatives considered

- **维持两种结构**：不冒冲突的风险。但结构会一直不统一，依赖检查也一直有洞。
- **一个模块一个 PR**：每次改动小。但每个 PR 都要改 `router/index.ts` 和依赖检查脚本，十几个 PR 来回冲突，反而更乱。
- **同时把 `api/types.ts` 按模块拆开**：更彻底。但类型被大量跨模块引用（UserBrief、ProjectBrief、DatasetBrief……），拆开后要么到处跨模块引用 types，要么再建一个公共 types 文件，收益不大。等它真的难以维护了再拆。

## Consequences

- 前端全量 74 项通过；类型检查、生产构建、模块依赖检查通过。
- 临时探针分别加载迁移前后全部业务页面组件；37 项归一化路由的名称、路径、meta 及顺序一致。探针不等于真实浏览器逐角色验收。
- 共用 PinnedDatasets、AttachmentList 留在公共组件目录。附件组件由调用方显式传入原来的删除函数，从而解除公共组件到采购模块的依赖；删除接口不变。
- 设备表单只变更两个 API import，不改变提交逻辑。完整历史和固定版本 TLC 下，10 个模型用例符合预期。检查退出码 2 只因设备表单的两个 API import 路径发生漂移，SYNC 不在本次迁移中改动。
- 真实浏览器逐角色验收（本环境 Chromium 启动时 socket 被拒绝）和后端整套检查尚未验证；待补证据后再评估合并。

## Risks

- **合并冲突**：迁移会碰到几乎所有页面。动手前确认没有其他未合并的前端 PR；做的期间不要并行开发前端功能；合并后，其他分支要先 rebase。
- **懒加载**：路由用的是懒加载，路径写错只有打开页面时才报错。上面要求的浏览器逐页打开不能省。
