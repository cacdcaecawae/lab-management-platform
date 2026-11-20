# Agent Note: 设备使用统计与导出

Status: implemented

## Problem

设备预约和使用登记已经积累了数据（`Booking`、`UsageReport`），但没有统计：

- 申报设备购置、写开放共享报告、核算机时费时，要知道每台设备每月用了多少小时、谁在用、用在哪个项目上；
- 管理员想知道哪台设备几乎没人用、哪台总是排满；
- 现在只能在预约日历里一周一周地翻。

## Decision

**接口**：`GET /api/equipment/usage-stats/?from=YYYY-MM-DD&to=YYYY-MM-DD&by=equipment|user|project|month`，只给本组管理员和导师。

- 时间范围为左闭右开，最长 366 天，超过返回 400。
- 统计未取消的"使用"类预约，跨越边界的按与 `[from, to)` 的交集计时。
- 每行：`{key: {id, label}, booked_hours, reported_hours, bookings, abnormal}`：
  - `booked_hours`：预约时长；
  - `reported_hours`：已登记使用结果的那部分预约的时长；
  - `abnormal`：登记为"异常"的次数。
- `by=month` 按上海时区自然月切分小时；预约和异常次数只计入查询窗口内第一相交月。设备分组保留零预约设备，项目分组保留未关联项目。已登记预约小时不是实测机时。
- `GET /api/equipment/usage-stats/export/` 返回 Excel，与 JSON 共用查询与权限，用 `core.export.xlsx_bytes`。

**实现**：

- 视图放在新文件 `equipment/stats_views.py`，路由加在 `equipment/urls.py`，不要写进 `equipment/views.py`。设备并发模型检查覆盖 `views.py`、`serializers.py`、`models.py`，放在新文件里不会触发它。
- 用 PostgreSQL 在数据库里算：对预约区间和 `[from, to)` 取交集，`upper - lower` 求和，换算成小时。不要把预约全部取回 Python 再加。

**前端**：

- 设备台账工具栏加"使用统计"按钮，只对管理员和导师显示，进入新页面 `equipment/stats`（`modules/equipment/views/EquipmentStatsView.vue`）。
- 页面上有日期范围（默认本月）、分组方式，一张表，"导出 Excel"按钮，以及"预约时长不等于实际使用时长"的说明。

- 历史预约按设备归属计入总量；按成员或项目展开时，只显示当前仍属本组的关联标识，其他记录合并到未归属行。

## Alternatives considered

- **只统计已登记使用结果的预约**：更接近实际使用。但很多人用完不登记，这样数字会严重偏低；两列都给，由看的人判断。
- **前端拿到全部预约后自己算**：后端不用写。但一年的预约可能上千条，接口本来限制 62 天，前端还要自己处理跨边界切分，容易算错。
- **做成图表**：更直观。但要引入图表库；表格加 Excel 已经能满足申报材料的需要，以后要图表再说。

## Verification checklist

- 后端测试：
  - 跨月、跨边界的预约正确切分；
  - 取消的预约和维护类预约不计入；
  - 学生 403、外组看不到；
  - 超过 366 天返回 400；
  - Excel 的表头和数值与 JSON 一致，单元格按文字或数字保存（参照 `xlsx_bytes` 的公式防护）。
- 设备并发模型检查的覆盖范围没有变化（`check.sh` 退出码 0）。
- 浏览器：管理员造几条预约（含一条跨月的），统计页按设备、按人、按月各看一次，导出的文件能打开、数字一致。学生看不到按钮，直接打开地址回到工作台。更新 `features/equipment.md`。

## Risks

- 时区：预约以 UTC 存储，按月分组要先换到 Asia/Shanghai 再截断，否则月初 8 点前的预约会算进上个月。测试里要有一条这样的边界数据。

## Consequences

- PostgreSQL 17 定向 5 项通过，含跨月、裁剪、排除取消/维护、角色/隔离、Excel。前端及完整检查见 PR 验证记录。
- 这组数字是计划和登记口径，不用于直接计收实测机时。
