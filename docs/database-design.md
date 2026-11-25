# 数据库与模型设计

PostgreSQL。模型定义即权威来源（`backend/*/models.py`），本文说明关系和约束。第一期全部模型由主代理在基线中定义，0001 迁移随基线提交；第二期新增 `equipment`、`inventory` 两个 app。

## 关系图

```
ResearchGroup 1─* User
ResearchGroup 1─* Project ─* ProjectLog
Project *─* User (members)      Project *─1 User (leader)

User 1─* Dataset *─1 Project (可空)   Dataset 1─* DataFile
User 1─* Experiment *─1 Project (可空) Experiment 1─1 Dataset (dataset，自己的原始数据)   Experiment 1─* ExperimentPhoto
                                      Experiment *─* Dataset (datasets，早期关联)
User 1─* ProcessingRun *─1 Project (可空) ProcessingRun *─* Experiment (experiments，引用的原始数据)
                                      ProcessingRun *─* Dataset (inputs，早期引用)
                                      ProcessingRun *─1 Dataset (script_dataset, kind=script)
                                      ProcessingRun *─1 Dataset (output_dataset, kind=result)
User 1─* WeeklyReport ─* ReportFeedback
WeeklyReport *─* Experiment / Dataset / ProcessingRun

ResearchGroup 1─* Equipment ─* Booking ─1 UsageReport      （第二期）
Booking *─1 User (user)   Booking *─1 Project (可空)
Experiment *─1 Equipment (equipment_item，可空)
ResearchGroup 1─* Consumable ─* StockTxn *─1 User (handler)   StockTxn *─1 Project (可空)
```

## 表

| 模型 | App | 关键字段 | 约束 / 说明 |
|---|---|---|---|
| `ResearchGroup` 课题组 | accounts | name | name 唯一 |
| `User` 成员 | accounts | username（学号/工号）, name, group, role, phone, research_direction, must_change_password | 继承 `AbstractUser`；`AUTH_USER_MODEL = accounts.User` |
| `Project` 项目 | projects | group, name, leader, members, stage, status, description | (group, name) 唯一 |
| `ProjectLog` 项目进展 | projects | project, date, content, author | 只增 |
| `Dataset` 数据集 | datasets | owner, project（可空）, name, kind, description | 一条记录的一组文件，随记录创建；有修改历史 |
| `DataFile` 数据文件 | datasets | dataset, name（拖入文件夹时是相对路径）, file, size, sha256, uploaded_by | (dataset, name) 唯一；存储路径 `datasets/<id>/<uuid>`；无修改接口；没被已提交记录固定的本人可删 |
| `DatasetSnapshot` 数据集版本 | datasets | dataset, digest（版本码）, files | (dataset, digest) 唯一；记录提交时生成，文件清单相同则复用 |
| `Experiment` 实验与原始数据 | research | owner, project（可空）, title, date, equipment_item（台账设备，可空）, equipment（设备说明，文本）, specimen（试件说明）, specimen_items, params(JSON), steps, anomalies, dataset（自己的原始数据）, datasets（早期关联）, status, submitted_at | 有修改历史 |
| `ExperimentPhoto` 实验照片 | research | experiment, file, name, size, uploaded_by | 存储路径 `experiment-photos/<uuid>.<扩展名>`；草稿时增删 |
| `ProcessingRun` 数据处理 | research | owner, project（可空）, title, experiments, inputs（早期）, script_dataset / script_repo + script_commit + script_path / method（软件/方法说明）, method_version, params(JSON), environment, output_dataset, conclusion, status | 有修改历史 |
| `WeeklyReport` 周报 | reports | owner, week_start（周一）, goals, done, findings, next_plan, experiments/datasets/runs, status, submitted_at | (owner, week_start) 唯一；有修改历史 |
| `ReportFeedback` 周报反馈 | reports | report, author, verdict, content | 只增 |
| `Equipment` 设备 | equipment | group, code, name, model, category, location, custodian, status, purchase_date, calibration_due, notes | (group, code) 唯一；status 只有 可用 / 待检查 / 维修 / 停用，"使用中"按预约推算不入库；有修改历史；不删除 |
| `Booking` 设备预约 | equipment | equipment, user, project, kind（使用 / 维护）, start_at, end_at, purpose, cancelled_at | end_at > start_at；排他约束 `no_overlapping_bookings`：同一设备、未取消的 `tstzrange(start_at, end_at)`（`[)` 区间）不重叠，需要 `btree_gist` 扩展；取消只记 cancelled_at |
| `UsageReport` 使用登记 | equipment | booking（一对一）, condition（正常 / 异常）, description, photo, reported_at | 每个预约最多一条；照片存 `usage-photos/<uuid>.<扩展名>` |
| `Consumable` 耗材 | inventory | group, name, spec, unit, location, safety_stock, notes | (group, name, spec) 唯一；库存不入库，等于流水 quantity 之和 |
| `StockTxn` 出入库流水 | inventory | consumable, kind（入库 / 领用 / 退回 / 盘点调整）, quantity（带符号整数）, handler, project, note, created_at | quantity ≠ 0；只增不改 |

## 约定

- **外键删除策略**：指向用户、项目、数据集的外键一律 `PROTECT`。成员离组用 `is_active=False`，项目结束用 `status=closed`，科研数据不随人或项目删除。
- **修改历史**：`django-simple-history`（`HistoricalRecords`）记录每次保存的字段快照和操作者（`HistoryRequestMiddleware` 自动取当前用户）。多对多关联的变化不进入历史快照（限制，见 [修改历史](../.agents/notes/implemented/architecture/2026-11-16-change-history.md)）。
- **数据版本**：实验、处理记录、周报的 `data_versions` 存 `{数据集 id: 版本码}`，提交时写入，算法见 `datasets/versions.py`。处理记录引用实验时固定的是那条实验的原始数据。非草稿记录固定的版本里的文件不能删除（`versions.locked_file_ids`）。
- **编号**：`code` 不入库，由 `created_at` 年份 + 主键生成（`EX-2026-0018`、`DS-…`、`RUN-…`）。
- **数据范围**：个人数据通过 `owner__group_id` 判断所属课题组，不在每张表冗余 group 字段。
- **实验记录的设备**：`equipment_item` 是指向台账的可空外键，`equipment` 文本保留为"设备说明"，用于台账外的设备和第一期的旧记录；没有做数据迁移。见 [第二期设备与耗材](../.agents/notes/implemented/feature/2026-11-17-phase2-equipment-and-consumables.md)。
- **并发**：预约冲突靠排他约束（撞约束返回 409）；建预约和登记异常都先对 `Equipment` 行加锁；领用和盘点先对 `Consumable` 行加锁再汇总库存。

## 迁移规则

- 0001 迁移由主代理生成。子代理若修改本 app 模型，只生成本 app 的新迁移，不改别的 app，不改已提交的迁移。
- 合并后主代理执行 `makemigrations --check --dry-run`，确认没有遗漏或冲突的迁移。
