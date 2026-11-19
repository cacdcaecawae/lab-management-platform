# Agent Note: 工作台提醒：我借的试件、逾期未还、设备校准到期

Status: implemented

## Problem

[试样与标准件](../../implemented/feature/2026-11-18-specimens.md)上线后，借了试件的人只有打开试件页才知道自己还没还、是否已经逾期，管理员也看不到全组的逾期情况。设备台账一直有"下次校准日期"（`Equipment.calibration_due`），但没有任何地方提醒，过期了也没人知道。工作台（`/api/dashboard/`，`backend/workbench/views.py`）是大家每天打开的页面，提醒应该放在这里。

## Decision

**接口**（`GET /api/dashboard/`，新增字段与各自的真实总数，旧字段不变）：

- `my.borrowed_specimens`：当前用户未归还的借用，预览最多 20 条，到期日早的在前，没有到期日的放最后。每条为 `{loan_id, specimen: SpecimenBrief, borrowed_at, due_date, overdue}`，`overdue` 按服务器本地日期判断。
- `manager.overdue_loans`：本组所有逾期未还的借用，含借用人 `UserBrief`，预览最多 20 条。只给管理员，与 `equipment_to_check` 一样。
- `manager.calibration_due`：本组状态不是"停用"、`calibration_due` 在今天之后 30 天以内或已经过期的设备，按日期升序，预览最多 20 条。每条为 `EquipmentBrief` 加 `calibration_due`。

**实现**：

- 写在 `workbench/views.py`；汇总层可以引用所有业务模块，依赖规则不用改。
- 逾期判断放在 `specimens/queries.py`（新建，作为对外部分），供工作台和以后的提醒邮件共用，与 `procurement/queries.py` 一样。

**前端**（`views/WorkbenchView.vue`）：

- 新增三张卡片，和顶部对应的数字块。数字块的链接：
  - "我借的试件"指向 `/specimens?mine=1`；
  - "逾期未还"指向 `/specimens?overdue=1`；
  - "校准到期"指向 `/equipment?calibration_within=30`。
- 为此，`SpecimensView` 要从地址栏读 `mine`、`on_loan`、`overdue` 作为初始筛选（参照 `EquipmentView` 读 `status`）。
- 设备列表接口新增筛选 `calibration_within=<天数>`：`calibration_due <= 今天 + N`，包含已过期的，不含停用及无到期日的设备。工作台和列表共用筛选函数；借用查询供待办第 5 项复用。

## Alternatives considered

- **单独做一个"提醒"页面**：内容集中。但大家每天看的是工作台，多一个页面就多一次点击，大概率没人看。
- **校准提醒按设备设置提前天数**：更灵活。但目前没有人提过不同设备要不同的提前量，统一 30 天就够；需要时再加字段。

## Consequences

- 服务端 PostgreSQL 用例覆盖：本人和外组隔离、管理角色可见、到期当天和无日期不逾期、已归还排除、真实计数不截断、校准含当天与第 30 天并排除停用和其他组、无效校准天数返回 400。
- 前端用例覆盖：卡片展示真实总数并链接正确筛选；列表打开时按链接查询参数筛选。
- 完整检查在隔离 PostgreSQL 17 通过：后端 397 项，前端 78 项，迁移检查、类型检查、生产构建通过。TLC 10 个用例符合预期；退出码 2 的漂移限于只读设备列表，SYNC 等相关草稿集成后再同步。
- 待隔离实例逐角色浏览器验收；详见 verify-lab 的设备和试件检查项。
- 此项独立于前端目录迁移草稿 #15；二者可能在工作台页面及模块 API 引用产生冲突，后合并者要重新对齐。
- 共用选择器返回 QuerySet，可供后续按日期执行的邮件提醒使用；本项不会发送邮件。

## Risks

- 工作台多了三组查询。工作台已经有十几个查询，每组都有上限 20 条，影响不大；`workbench` 测试里如果有查询次数断言，要相应调整，不能放宽成和行数有关。
