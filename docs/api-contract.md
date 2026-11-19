# API 接口约定

本文件是前后端和各子代理之间的契约。修改须由主代理进行；子代理发现需要改动时，在交付说明中提出。

## 通用约定

- 前缀 `/api/`，JSON，UTF-8。日期 `YYYY-MM-DD`，时间 ISO 8601（带时区）。
- 认证：Session Cookie。所有非 GET 请求带 `X-CSRFToken`（值取 `csrftoken` Cookie）。
- 更新用 `PATCH`（部分更新）。`PUT` 不作为契约的一部分。
- 列表分页：`?page=1&page_size=20`（最大 100），响应 `{"count", "next", "previous", "results": [...]}`。
- 内嵌用户统一为 `UserBrief = {"id": 1, "name": "陈同学"}`；内嵌项目为 `{"id", "name"}`。
- 写入时引用其他对象用 `xxx_id` / `xxx_ids` 字段；读取时返回内嵌对象。
- 编号 `code`（如 `EX-2026-0018`）只读，由年份和主键生成。
- 只读字段（如数据集的 `project_id`、`kind`，成员的 `username`）在 PATCH 中提交会被忽略，不报错。
- 列表过滤参数只作用于列表；带着过滤参数访问详情地址不受影响。非法的整数型参数返回 400。

### 错误格式

```json
{"code": "validation_error", "message": "提交的数据有误", "errors": {"title": ["该字段是必填项。"]}}
{"code": "not_found", "message": "未找到。"}
```

| HTTP | code | 场景 |
|---|---|---|
| 400 | `validation_error` | 字段校验失败，`errors` 为 `{字段: [信息]}`，非字段错误在 `non_field_errors` |
| 403 | `not_authenticated` | 未登录 |
| 403 | `password_change_required` | 初始密码未修改 |
| 403 | `no_group` | 账号未分配课题组（如运维的超级用户），不能使用业务接口 |
| 403 | `invalid_credentials` | 用户名或密码错误 |
| 403 | `permission_denied` | 已登录但无权执行该操作（对象在可见范围内） |
| 404 | `not_found` | 对象不存在**或不在可见范围内**（不区分） |
| 409 | `conflict` / `file_exists` / `invalid_state` / `stale_status` / `stale` / `not_configured` | 唯一性冲突、文件已存在、当前状态不允许该操作、设备状态在编辑期间被他人改过、采购申请在审批人打开后变了、财务邮箱或发信邮箱没配置 |
| 502 | `mail_failed` | 手动发送财务提醒或测试邮件时 SMTP 出错，`message` 带上服务器给的原因 |
| 413 | `file_too_large` | 超过 `MAX_UPLOAD_SIZE` |
| 429 | `throttled` | 登录限速：同一账号从同一来源地址每分钟最多 5 次，不锁定账号；另有 Nginx 按 IP 每分钟 60 次的粗限制（非 JSON 响应） |

后端抛 `core.exceptions.Conflict(detail, code=...)` 得到 409。

### 权限速查

- 个人数据（实验、数据集/文件、处理记录、周报）：本人 + 本组管理员/导师可读；只有本人可写。
- 组内公开（项目、成员公开字段；第二期的设备、预约、使用登记、耗材与流水）：本组全员可读。
- 设备台账、耗材品类、入库、盘点调整只有本组**管理员**（`role=manager`，不含导师）可写。
- 第三期：采购申请、报销和它们的附件是个人数据（本人 + 本组管理员、导师）；经费来源组内公开，只有管理员可写。
- 越权读取一律 404。
- 系统管理 `/api/system/` 只有运维账号（超级用户）可用，其他账号 403；运维账号访问业务接口仍然 403 `no_group`。

---

## 认证 `/api/auth/`（主代理，已实现）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/auth/csrf/` | 204，设置 `csrftoken` Cookie |
| POST | `/api/auth/login/` | `{username, password}` → 200 `Me`；失败 403 `invalid_credentials` |
| POST | `/api/auth/logout/` | 204 |
| GET | `/api/auth/me/` | 200 `Me`（未改初始密码也可访问） |
| POST | `/api/auth/password/` | `{old_password, new_password}` → 204；新密码按 Django 密码规则校验 |

`Me = {id, username, name, role, is_supervisor, is_superuser, group: {id, name} | null, email, phone, research_direction, must_change_password}`（`is_superuser`：运维账号）

`role`: `student` | `manager` | `advisor`

## 工作台 `/api/dashboard/`（主代理，集成阶段实现）

`GET /api/dashboard/` →

```json
{
  "my": {
    "reports_needing_revision": [WeeklyReportBrief],
    "draft_experiments": [ExperimentBrief],
    "current_week_report": WeeklyReportBrief | null,
    "upcoming_bookings": [Booking],     // 本人进行中和将来的预约，按开始时间
    "unreported_bookings": [Booking],   // 本人最近 14 天内结束、还没登记使用结果的"使用"类预约
    "returned_purchases": [Purchase],   // 本人被退回、还没重新提交的采购申请
    "action_items": [MyActionItem],     // 本人未完成的组会行动项，截止日期近的在前，没有截止日期的在最后
    "borrowed_specimens": [BorrowedSpecimenReminder],  // 本人未还，到期日早的在前，无到期日在最后
    "borrowed_specimens_count": 0      // 真实总数，不限于预览
  },
  "supervisor": {                      // 仅管理员/导师，否则为 null
    "week_start": "2026-11-16",
    "missing_reports": [UserBrief],
    "pending_reviews": [WeeklyReportBrief],
    "purchases_to_review": [Purchase]  // 管理员：待初审；导师：待终审（都不含自己的）
  },
  "manager": {                         // 仅管理员（不含导师），否则为 null
    "equipment_to_check": [EquipmentBrief],   // 状态为"待检查"的设备
    "low_stock": [Consumable],                // 库存低于安全库存的耗材
    "overdue_loans": [BorrowedSpecimenReminder + {borrower: UserBrief}],
    "overdue_loans_count": 0,
    "calibration_due": [EquipmentBrief + {calibration_due}],
    "calibration_due_count": 0
  }
}
```

每个列表最多 20 条；上述三个 `*_count` 字段为相同条件下的真实总数。
`BorrowedSpecimenReminder = {loan_id, specimen: SpecimenBrief, borrowed_at, due_date: date | null, overdue}`；不含缺陷参数。
逾期是到期日小于应用所在时区的当日且未归还。校准提醒包含到期日在当日后 30 天以内及已过期的非停用设备。

---

## 成员 `/api/members/`（Agent A）

`Member`（本组成员可见的公开字段）：`{id, name, role, research_direction, is_active}`
`MemberDetail`（本组管理员/导师可见，本人看自己也返回）：在 `Member` 基础上增加 `{username, email, phone, must_change_password}`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/members/?search=&role=&is_active=` | 本组全员 | 只返回本组成员；`search` 匹配姓名、研究方向，管理员/导师另外匹配学号（学生看不到学号，也不能用搜索试探） |
| GET | `/api/members/{id}/` | 本组全员 | 外组成员 404 |
| POST | `/api/members/` | 管理员 | `{username, name, role, email?, phone?, research_direction?, password}` → 201 `MemberDetail`；`role` 只能是 `student`；用户名已存在 → 409 `conflict`；课题组强制为操作者所在组；`must_change_password=true`；密码按 Django 规则校验 |
| PATCH | `/api/members/{id}/` | 管理员 | 可改 `name, role, email, phone, research_direction, is_active`；不可改 `username`、课题组；管理员不能停用自己 |
| POST | `/api/members/{id}/reset-password/` | 管理员 | `{password}` → 204，并置 `must_change_password=true` |

不提供删除（离组用 `is_active=false`）。管理员只能修改、停用、重置**学生**账号（以及修改自己的资料），`role` 只能设为 `student`，不能改自己的角色；导师、管理员账号由运维在"系统管理 → 账号"里管理，运维账号只在 `/admin/` 管理；对它们 PATCH / 重置密码返回 404。

管理命令：`python manage.py import_members <file.csv> --group <课题组名>`。CSV 列：`username,name,role,email,phone,research_direction`（UTF-8，可带 BOM）。为每个新用户生成随机初始密码，`must_change_password=true`；已存在的用户名跳过并报告；结果（用户名, 初始密码）输出到 stdout 或 `--output` 指定的 CSV。

## 项目 `/api/projects/`（Agent A）

`Project = {id, name, leader: UserBrief, members: [UserBrief], stage, status, description, latest_log: ProjectLog | null, created_at, updated_at}`
`status`: `active` | `closed`
`ProjectLog = {id, date, content, author: UserBrief, created_at}`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/projects/?status=&search=&mine=1` | 本组全员 | `mine=1` 只看自己是负责人或成员的项目 |
| POST | `/api/projects/` | 管理员/导师 | `{name, leader_id, member_ids, stage, status, description}`；负责人和成员必须是本组在籍成员；负责人自动计入成员；同组项目名唯一（409 `conflict`） |
| GET | `/api/projects/{id}/` | 本组全员 | |
| PATCH | `/api/projects/{id}/` | 管理员/导师/项目负责人 | 同 POST 字段；**只有管理员/导师能改 `leader_id`**，负责人提交 `leader_id` 变更 → 403 |
| GET | `/api/projects/{id}/logs/` | 本组全员 | 分页，按日期倒序 |
| POST | `/api/projects/{id}/logs/` | 管理员/导师/项目负责人 | `{date, content}`，`author` 为当前用户 |

不提供删除（结束用 `status=closed`）。

---

## 数据集与文件（Agent C）

`Dataset = {id, code, project: {id,name}, owner: UserBrief, name, kind, description, file_count, total_size, version, created_at, updated_at}`
`kind`: `raw` 原始数据 | `script` 脚本 | `result` 处理结果 | `other`
`DataFile = {id, dataset_id, name, size, sha256, uploaded_by: UserBrief, uploaded_at, download_url}`（`download_url` = `/api/files/{id}/download/`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/datasets/?project=&kind=&owner=&search=` | 个人数据范围 | |
| POST | `/api/datasets/` | 登录成员 | `{project_id, name, kind, description}`；`owner` = 当前用户；项目必须在本组 |
| GET | `/api/datasets/{id}/` | 个人数据范围 | |
| PATCH | `/api/datasets/{id}/` | 本人 | 只可改 `name, description` |
| DELETE | `/api/datasets/{id}/` | 本人 | 仅当没有文件、且未被实验/处理记录/周报引用；否则 409 `invalid_state` |
| GET | `/api/datasets/{id}/files/?version=` | 个人数据范围 | 不分页，按文件名排序；带 `version`（完整版本码）时只列该版本的文件，未知版本 404 |
| POST | `/api/datasets/{id}/files/` | 本人 | `multipart/form-data`：一个或多个 `file` 字段；可选 `sha256`（仅单文件时，客户端算好的校验值）。→ 201 `[DataFile]` |
| GET | `/api/files/{id}/` | 个人数据范围 | `DataFile` |
| GET | `/api/files/{id}/download/` | 个人数据范围 | 流式下载，`Content-Disposition: attachment`（文件名用 RFC 5987 编码） |

上传规则（前端目前每个文件单独发一个请求，以便显示单文件进度；接口仍支持一次多文件）：
- 同一数据集内已有同名文件、或同一请求内重名 → 409 `file_exists`，**整个请求不保存任何文件**。
- 提供了 `sha256` 且与服务器计算值不一致 → 400 `validation_error`（`errors.sha256`），不保存。
- 单文件超过 `MAX_UPLOAD_SIZE` → 413 `file_too_large`。
- 文件只读：不提供 PATCH / DELETE / 覆盖接口。
- 版本码 `version`（64 位十六进制，界面显示前 12 位）：数据集内所有文件按文件名排序，逐行拼接 `<文件 sha256>  <文件名>` 后再算 SHA256。文件相同则版本码相同，追加文件后版本码改变。数据集可以一直追加文件；实验、处理记录、周报**提交时**为引用的每个数据集记下当时的版本码和文件清单（退回草稿时清空，再次提交时重新记录）。错误的数据另建数据集；确需删除由运维在后台处理。
- 文件名只取 basename，去掉路径分隔符；空文件名 400。

## 实验记录 `/api/experiments/`（Agent B）

`Experiment = {id, code, project: {id,name}, owner: UserBrief, title, date, equipment_item: EquipmentBrief | null, equipment, specimen, specimen_items: [SpecimenBrief], params: object, steps, anomalies, datasets: [DatasetBrief], status, submitted_at, created_at, updated_at}`
`DatasetBrief = {id, code, name, kind}`；内嵌在实验、处理记录、周报里的数据集另有 `version`（提交时记下的版本码，草稿和旧记录为 `null`）和 `changed`（提交后是否追加过文件）
`status`: `draft` | `submitted`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/experiments/?project=&status=&owner=&search=` | 个人数据范围 | |
| POST | `/api/experiments/` | 登录成员 | `{project_id, title, date, equipment_item_id, equipment, specimen, specimen_item_ids, params, steps, anomalies, dataset_ids}` → 草稿 |
| GET | `/api/experiments/{id}/` | 个人数据范围 | |
| PATCH | `/api/experiments/{id}/` | 本人，且为草稿 | 已提交时 409 `invalid_state` |
| DELETE | `/api/experiments/{id}/` | 本人，且为草稿、未被周报引用 | |
| POST | `/api/experiments/{id}/submit/` | 本人 | 草稿 → 已提交；校验必填：`title, date, project`；返回 `Experiment` |
| POST | `/api/experiments/{id}/return/` | 本组管理员/导师 | `{reason}`（必填）→ 已提交 → 草稿；返回 `Experiment` |
| GET | `/api/experiments/{id}/history/` | 个人数据范围 | `[HistoryEntry]` |

校验：`project_id` 必须是本组项目；`equipment_item_id`（可为 `null`）必须是本组台账里的设备；`specimen_item_ids` 必须是本组的台账试件（`SpecimenBrief = {id, code, name, status}`，不带缺陷参数）；`dataset_ids` 必须是**记录所有者本人**的数据集；`params` 必须是 JSON 对象。`equipment` 是自由文本的"设备说明"。

## 数据处理记录 `/api/runs/`（Agent B）

`ProcessingRun = {id, code, project: {id,name}, owner: UserBrief, title, inputs: [DatasetBrief], script_dataset: DatasetBrief | null, script_repo, script_commit, script_path, method_version, params: object, environment, output_dataset: DatasetBrief | null, conclusion, status, submitted_at, created_at, updated_at}`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/runs/?project=&status=&owner=&search=` | 个人数据范围 | |
| POST | `/api/runs/` | 登录成员 | `{project_id, title, input_ids, script_dataset_id, script_repo, script_commit, script_path, method_version, params, environment, output_dataset_id, conclusion}` → 草稿 |
| GET / PATCH / DELETE | `/api/runs/{id}/` | 同实验记录 | |
| POST | `/api/runs/{id}/submit/` | 本人 | 可复现性校验：至少 1 个输入；脚本二选一（`script_dataset` 或 `script_repo`+`script_commit`）；`environment` 非空；有 `output_dataset`。不满足 → 400，`errors` 的键为 `inputs`、`script_dataset`（只填了一半时为 `script_repo` / `script_commit`）、`environment`、`output_dataset`。创建/修改时的校验错误用写入字段名（`input_ids` 等） |
| POST | `/api/runs/{id}/return/` | 本组管理员/导师 | `{reason}` |
| GET | `/api/runs/{id}/history/` | 个人数据范围 | |

校验：引用的数据集必须属于记录所有者；`script_dataset` 的 `kind` 必须是 `script`，`output_dataset` 的 `kind` 必须是 `result`。

## 周报 `/api/reports/`（Agent D）

`WeeklyReport = {id, owner: UserBrief, week_start, goals, done, findings, next_plan, experiments: [ExperimentBrief], datasets: [DatasetBrief], runs: [RunBrief], status, submitted_at, feedback: [Feedback], created_at, updated_at}`
`WeeklyReportBrief = {id, owner: UserBrief, week_start, status, submitted_at}`
`ExperimentBrief = {id, code, title, status}`；`RunBrief = {id, code, title, status}`
`Feedback = {id, author: UserBrief, verdict, content, created_at}`
`status`: `draft` | `submitted` | `needs_revision` | `reviewed`；`verdict`: `reviewed` | `needs_revision`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/reports/?owner=&week_start=&status=` | 个人数据范围 | |
| POST | `/api/reports/` | 登录成员 | `{week_start, goals, done, findings, next_plan, experiment_ids, dataset_ids, run_ids}`；`week_start` 必须是周一（400）；同人同周重复 → 409 `conflict` |
| GET | `/api/reports/{id}/` | 个人数据范围 | |
| PATCH | `/api/reports/{id}/` | 本人，状态为 `draft` 或 `needs_revision` | 否则 409 `invalid_state` |
| DELETE | `/api/reports/{id}/` | 本人，仅 `draft` | |
| POST | `/api/reports/{id}/submit/` | 本人 | `draft`/`needs_revision` → `submitted` |
| POST | `/api/reports/{id}/feedback/` | 本组管理员/导师，且不是周报本人 | `{verdict, content}`；仅 `submitted` 状态可反馈；`needs_revision` 时 `content` 必填；状态随 `verdict` 变化；返回 `WeeklyReport` |
| GET | `/api/reports/{id}/history/` | 个人数据范围 | `[HistoryEntry]` |
| GET | `/api/reports/missing/?week_start=` | 本组管理员/导师 | 本组在籍学生中该周没有 `submitted`/`reviewed`/`needs_revision` 周报的人 → `[UserBrief]`；`week_start` 缺省为本周一 |

校验：关联的实验、数据集、处理记录必须属于周报所有者本人。状态变化与反馈写入在同一事务中。

---

## 设备 `/api/equipment/`（第二期）

`EquipmentBrief = {id, code, name, status}`
`Equipment = {id, code, name, model, category, location, custodian: UserBrief | null, status, in_use, purchase_date, calibration_due, notes, purchase: PurchaseRef | null, created_at, updated_at}`
`status`: `available` 可用 | `needs_check` 待检查 | `repair` 维修 | `retired` 停用；`in_use`（只读）：当前时间落在某个未取消的预约里

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/equipment/?status=&search=&calibration_within=30` | 本组全员 | `search` 匹配编号、名称、型号、类别、存放位置；`calibration_within` 为 0 至 3650 的整数，包含已过期、不含停用和无到期日，按到期日再按 ID 排序；无效值 400 |
| POST | `/api/equipment/` | 管理员 | `{code, name, model, category, location, custodian_id, status, purchase_date, calibration_due, notes, purchase_id}`；`code` 组内唯一（409 `conflict`）；保管人必须是本组在籍成员；`purchase_id` 只能选本组已到货的采购申请 |
| GET | `/api/equipment/{id}/` | 本组全员 | `Equipment` 加 `recent_usage: [Booking]`：已开始、未取消的"使用"类预约，最近 20 条，含使用登记 |
| PATCH | `/api/equipment/{id}/` | 管理员 | 同 POST 字段，只提交要改的字段；没提交的字段保留数据库里的最新值（在行锁下重读，不会把并发的"待检查"写回成旧值）。提交 `status` 时必须同时提交 `status_seen`（打开编辑框时看到的状态，缺了 400）；锁下的当前状态既不是 `status_seen` 也不是新状态时 → 409 `stale_status` |
| GET | `/api/equipment/{id}/history/` | 本组全员 | `[HistoryEntry]`；登记异常引起的状态变化，`reason` 写明登记人和说明 |

不提供删除（报废用 `status=retired`）。

## 预约与使用登记 `/api/bookings/`（第二期）

`Booking = {id, equipment: EquipmentBrief, user: UserBrief, project: {id,name} | null, kind, start_at, end_at, purpose, cancelled_at, report: UsageReport | null, created_at}`
`kind`: `use` 使用 | `maintenance` 维护
`UsageReport = {condition, description, photo_url, reported_at}`；`condition`: `normal` | `abnormal`；`photo_url` 为 `/api/bookings/{id}/photo/` 或 `null`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/bookings/?from=&to=&equipment=&mine=1` | 本组全员 | **不分页**。`from`、`to` 必填（ISO 8601），范围大于 0 且不超过 62 天；返回与 `[from, to)` 重叠的未取消预约，按开始时间排序 |
| POST | `/api/bookings/` | 本组全员 | `{equipment_id, kind, start_at, end_at, project_id?, purpose?}` → 201 `Booking`。规则见下 |
| GET | `/api/bookings/{id}/` | 本组全员 | |
| POST | `/api/bookings/{id}/cancel/` | 本人（尚未开始）或管理员 | → `Booking`；已取消、已登记使用结果 → 409 `invalid_state`；本人取消已开始的预约 → 409；取消别人的 → 403 |
| POST | `/api/bookings/{id}/report/` | 预约人 | `multipart/form-data`：`condition`、`description`、可选 `photo` → 201 `Booking`。规则见下 |
| GET | `/api/bookings/{id}/photo/` | 本组全员 | 照片原图（`Content-Disposition: inline`），没有照片 → 404 |

新建预约：
- `end_at` 必须晚于 `start_at`（400，`errors.end_at`）；`start_at` 最多比当前早 5 分钟（400，`errors.start_at`）。
- `kind=use` 一次最长 7 天，超过 400（`errors.end_at`）；`kind=maintenance` 不限时长。
- `kind=maintenance` 只有管理员能建（403），不受设备状态限制。
- `kind=use` 只能约状态为 `available` 的设备，否则 409 `invalid_state`。
- 与同一设备未取消的预约时段重叠 → 409 `conflict`。由数据库排他约束保证，并发提交也只有一个成功。`[)` 区间：结束时刻等于下一个的开始时刻不算重叠。
- 不提供修改，改时间就取消后重约。

使用登记：
- 只能登记 `kind=use`、未取消、已经开始的预约，每个预约一次；不满足 → 409 `invalid_state`。
- `condition=abnormal` 时 `description` 必填（400）。照片只收 `.jpg .jpeg .png .webp`，不超过 10 MB（400，`errors.photo`）。
- 登记异常时，设备如果是 `available` 就改为 `needs_check`（记入修改历史）；此后不能新建"使用"类预约，已有预约保留，由管理员决定是否取消。
- 启用了邮件（系统管理）时，提交成功后给本组有邮箱的在籍管理员发邮件；发送失败只记日志和"最近一次发送失败"，不影响登记。

## 耗材 `/api/consumables/`（第二期）

`Consumable = {id, name, spec, unit, location, safety_stock, stock, stock_version, low, notes, created_at, updated_at}`；`stock`（只读）为全部流水之和，`low` = `stock < safety_stock`
`StockTxn = {id, kind, quantity, handler: UserBrief, project: {id,name} | null, purchase: PurchaseRef | null, note, created_at}`
`kind`: `in` 入库 | `out` 领用 | `return` 退回 | `adjust` 盘点调整；`quantity` 带符号（领用为负）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/consumables/?search=&low=1` | 本组全员 | `search` 匹配名称、规格、存放位置；`low=1` 只列低于安全库存的 |
| POST | `/api/consumables/` | 管理员 | `{name, spec, unit, location, safety_stock, notes}`；(name, spec) 组内唯一（409 `conflict`） |
| GET | `/api/consumables/{id}/` | 本组全员 | |
| PATCH | `/api/consumables/{id}/` | 管理员 | 同 POST 字段 |
| GET | `/api/consumables/{id}/txns/` | 本组全员 | 分页，最新在前 |
| POST | `/api/consumables/{id}/txns/` | 见说明 | `{kind, quantity, project_id?, purchase_id?, note?}`（`purchase_id` 只用于入库，只能选本组已到货的采购申请，其他类型带了 400） → 201 `StockTxn`。`in`、`adjust` 只限管理员（403）；`out`、`return` 本组全员，经手人为当前用户。`in`/`out`/`return` 的 `quantity` 传正整数，`adjust` 传实际与账面之差（不能为 0）。结果库存小于 0 → 400（`errors.quantity`："库存不足：当前 N 单位"） |

不提供删除；流水不可修改，记错用一笔盘点调整纠正。Django admin 的流水内联也只读，禁止新增/编辑/删除，写流水统一通过上述加锁 API。

`stock_version`（只读）为该耗材最新流水 id，空账本为 0；与 `stock` 在同一查询中读取。`adjust` 必须另传 `stock_version_seen`（打开盘点时看到的版本，非负整数）；缺少/非法返回 400。锁内版本已变则返回 409 `stale_stock`，即使库存先减后增回到原值也拒绝，且不新增流水。客户端必须刷新并重新核对，不能自动重发旧差额。普通 `in/out/return` 无版本要求。旧客户端缺少版本的盘点将安全失败，前后端须同步更新。

---

## 试样与标准件 `/api/specimens/`

`Specimen = {id, code, name, kind, material, dimensions, location, custodian: UserBrief | null, status, defects_public, defects: [Defect] | null, current_loan: Loan | null, notes, created_at, updated_at}`
`kind`: `standard` 标准试块 | `reference` 对比试块 | `sample` 试样 | `other` 其他；`status`: `available` 可用 | `damaged` 损坏 | `retired` 停用。"借出"不是状态，看 `current_loan`。
`Defect = {id, kind, size_mm, depth_mm, position, note}`，`kind`: `fbh` 平底孔 | `sdh` 横通孔 | `notch` 刻槽 | `crack` 裂纹 | `delamination` 分层 | `other`；`size_mm`、`depth_mm` 是两位小数的字符串或 `null`
`Loan = {id, borrower: UserBrief, project: {id,name} | null, purpose, due_date, borrowed_at, returned_at, returned_by: UserBrief | null, return_note}`

**缺陷参数可能是盲测的真值**：`defects_public` 为 `false` 时，学生拿到的 `defects` 是 `null`（不是空列表，也不给个数）；管理员和导师总能看到。搜索不匹配缺陷字段。修改历史只记"修改了缺陷参数"，不记数值。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/specimens/?search=&kind=&status=&on_loan=1&mine=1&overdue=1` | 本组全员 | `search` 匹配编号、名称、材料、存放位置；`on_loan=1` 借出未还的；`mine=1` 我借出未还的；`overdue=1` 借用已逾期（按应用时区）且未归还；可叠加 |
| POST | `/api/specimens/` | 管理员 | `{code, name, kind, material, dimensions, location, custodian_id, status, defects_public, notes, defects: [{kind, size_mm, depth_mm, position, note}]}`；编号组内唯一（409） |
| GET | `/api/specimens/{id}/` | 本组全员 | |
| PATCH | `/api/specimens/{id}/` | 管理员 | 同 POST 字段；带 `defects` 时整份替换 |
| GET | `/api/specimens/{id}/history/` | 本组全员 | `[HistoryEntry]` |
| GET | `/api/specimens/{id}/loans/` | 本组全员 | 分页，最新在前 |
| POST | `/api/specimens/{id}/borrow/` | 本组全员 | `{project_id?, purpose?, due_date?}` → 201 `Loan`，借用人是当前用户。状态不是"可用" → 409 `not_available`；已借出 → 409 `on_loan`（同一试件同时只有一条未归还的借用，数据库约束） |
| POST | `/api/specimens/{id}/return/` | 借用人或管理员 | `{loan_id_seen, note?}` → `Loan`；`loan_id_seen` 为打开归还确认框时的借用 id（必填正整数）；当前借用不同 → 409 `stale_loan`，刷新后重新核对；没借出 → 409 `not_on_loan`；别人借的 → 403。旧客户端缺少该字段返回 400，前后端须同步更新 |

不提供删除；不再使用的改为"停用"。

---

## 采购与报销（第三期）

金额一律是两位小数的字符串（`"1200.00"`，人民币元），由后端用 `Decimal` 计算，前端只做显示。

### 经费来源 `/api/funds/`

`FundBrief = {id, code, name, active}`；`Fund = FundBrief + {owner: UserBrief | null, notes, created_at, updated_at}`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/funds/?active=1&search=` | 本组全员 | 填单时要选，所以组内公开；`search` 匹配经费号、名称 |
| POST | `/api/funds/` | 管理员 | `{code, name, owner_id?, active, notes}`；`code` 组内唯一（409 `conflict`） |
| PATCH | `/api/funds/{id}/` | 管理员 | 同 POST 字段 |

不提供删除：停用（`active=false`）后不能在新的采购、报销里选择，旧单据照常显示。

### 采购申请 `/api/purchases/`

`PurchaseRef = {id, code}`（设备、入库流水里内嵌这个，组内公开，不暴露申请人和用途）
`PurchaseBrief = PurchaseRef + {owner: UserBrief, purpose, status}`
`Purchase = PurchaseBrief + {fund: FundBrief | null, items: [PurchaseItem], total, returned, submitted_at, created_at, updated_at}`
`PurchaseDetail = Purchase + {approvals: [Approval], attachments: [Attachment], linked_equipment: [{id, code, name}], linked_stock: [{id, consumable, quantity, created_at}]}`
`PurchaseItem = {id, name, spec, quantity, unit_price, subtotal, link}`（`subtotal`、`total` 只读，现算）。`quantity` 为 1～1 000 000；明细合计超过 9 999 999 999.99 元时 400，错误在 `errors.items`（字符串列表）
`Approval = {id, stage, reviewer: UserBrief, verdict, comment, total, created_at}`；`stage`: `initial` 初审 | `final` 终审；`verdict`: `approve` 通过 | `return` 退回修改；`total` 是审批人当时看到的合计
`status`: `draft` 草稿 | `pending_initial` 待初审 | `pending_final` 待终审 | `approved` 已批准 | `purchased` 已采购 | `arrived` 已到货
`returned`（只读）：草稿，并且最近一次提交是被退回的（撤回不算）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/purchases/?status=&mine=1&todo=1&search=` | 个人数据范围 | 本人 + 本组管理员、导师；`todo=1` 只列等当前用户审批的（管理员：待初审；导师：待终审；都不含自己的）；`search` 匹配用途、品名、申请人 |
| POST | `/api/purchases/` | 本组全员 | `{purpose, fund_id?, items?: [{name, spec?, quantity, unit_price, link?}]}` → 201 `PurchaseDetail`（草稿）。`fund_id` 只能选本组可用的经费 |
| GET | `/api/purchases/{id}/` | 个人数据范围 | `PurchaseDetail` |
| PATCH | `/api/purchases/{id}/` | 见说明 | 草稿：本人。已批准、已采购：本人或管理员。审批中 → 409 `invalid_state`（先撤回）；已到货 → 409。`items` 整体替换。已批准后品名、数量或单价有变化 → 回到待初审（管理员的申请回到待终审），审批记录保留，修改历史的 `reason` 写明改前改后；改后的整单要通过和提交时一样的检查（至少 1 条明细、合计大于 0 等），否则 400，这次修改不生效 |
| DELETE | `/api/purchases/{id}/` | 本人 | 只能删从未提交过的草稿，否则 409；有报销关联这张草稿时 409 `in_use` |
| POST | `/api/purchases/{id}/submit/` | 本人 | 草稿 → 待初审；管理员本人的申请 → 待终审。用途、经费来源、至少 1 条明细、合计大于 0，缺了 400；经费已停用 400 |
| POST | `/api/purchases/{id}/withdraw/` | 本人 | 审批中 → 草稿 |
| POST | `/api/purchases/{id}/review/` | 见说明 | `{verdict, comment, status_seen, total_seen, submitted_seen}`。初审只能管理员、终审只能导师，都不能审自己的（403）。退回必须写意见（400）。`submitted_seen` 必填，为详情的 `submitted_at`（缺失、null 或格式错误 → 400）；锁下的状态、合计或提交时间与 `status_seen`、`total_seen`、`submitted_seen` 不同 → 409 `stale`；状态不需要审批 → 409 `invalid_state`。初审通过 → 待终审（导师本人的申请直接已批准）；终审通过 → 已批准；退回 → 草稿 |
| POST | `/api/purchases/{id}/purchased/` | 管理员 | 已批准 → 已采购，否则 409 |
| POST | `/api/purchases/{id}/arrived/` | 管理员 | 已采购 → 已到货，否则 409 |
| POST | `/api/purchases/{id}/attachments/` | 本人或管理员 | `multipart/form-data`：`file`、`kind`（`quote` 报价单 \| `invoice` 发票 \| `other`）→ 201 `Attachment` |
| GET | `/api/purchases/{id}/history/` | 个人数据范围 | `[HistoryEntry]`；审批、撤回、改明细都写 `reason` |

每一步状态变化都先锁住这张单再检查状态。启用了邮件时，提交后通知本组管理员，初审通过后通知导师，退回、终审通过、到货后通知申请人；发送失败只记日志。

### 附件 `/api/attachments/`

`Attachment = {id, kind, name, size, uploaded_by: UserBrief, url, created_at}`；`url` 为 `/api/attachments/{id}/file/`

- 只收 `.pdf .jpg .jpeg .png`，单个不超过 20 MB（400，`errors.file`）。存储名由服务器生成，`name` 保留原文件名。
- `GET /api/attachments/{id}/file/`：能看到所属采购申请或报销的人可以下载（inline），否则 404。
- `DELETE /api/attachments/{id}/`：上传人或管理员。采购申请：草稿可删；待初审、待终审 409；之后只能删最近一次审批之后上传的附件，否则 409（"审批人已经看过这份附件"）。报销：只有待提交可删，否则 409。

### 报销 `/api/reimbursements/`

`Reimbursement = {id, code, owner: UserBrief, fund: FundBrief, purchase: PurchaseBrief | null, category, amount, occurred_on, description, status, submitted_at, paid_at, attachments: [Attachment], created_at, updated_at}`
`category`: `equipment` 设备 | `consumable` 耗材 | `travel` 差旅 | `ai_tool` AI 工具 | `other` 其他
`status`: `pending` 待提交 | `submitted` 已交财务 | `paid` 已到账

列表、统计、导出共用这些过滤参数：`status`、`category`、`fund`、`owner`、`month`（`YYYY-MM`）、`from` / `to`（`YYYY-MM-DD`，按发生日期）。非法值 400。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/reimbursements/?…` | 个人数据范围 | 分页 |
| POST | `/api/reimbursements/` | 本组全员 | `{fund_id, category, amount, occurred_on, description?, purchase_id?}`；`amount` 大于 0；`purchase_id` 只能是报销人自己的采购申请 |
| GET | `/api/reimbursements/{id}/` | 个人数据范围 | |
| PATCH / DELETE | `/api/reimbursements/{id}/` | 本人或管理员 | 只有待提交可以改、删，否则 409 |
| POST | `/api/reimbursements/{id}/advance/` | 本人或管理员 | `{status}`：待提交 → 已交财务（必须已有发票类附件，400 `errors.attachments`）→ 已到账；已交财务 → 待提交只限管理员（403），修改历史记下退回人。其他变化 409 |
| POST | `/api/reimbursements/{id}/attachments/` | 本人或管理员 | 同采购申请；只有待提交可以上传，否则 409 `invalid_state` |
| GET | `/api/reimbursements/{id}/history/` | 个人数据范围 | |
| GET | `/api/reimbursements/stats/?by=&…` | 管理员、导师 | `by`: `fund` \| `category`（默认）\| `owner` \| `month`。→ `{by, rows: [{key, label, count, total}], count, total}`，合计由数据库按同样条件求和 |
| GET | `/api/reimbursements/export/?by=&…` | 管理员、导师 | `.xlsx`：工作表"汇总"（按 `by` 分组，最后一行合计）和"明细" |
| POST | `/api/reimbursements/remind-finance/` | 管理员 | 给课题组的财务邮箱发一封"已交财务、尚未到账"的清单 → `{sent, to}`（`sent=0` 表示没有待到账的报销，没有发）。没设财务邮箱或平台没启用邮件 → 409 `not_configured`；SMTP 失败 → 502 `mail_failed` |
| GET / PATCH | `/api/reimbursements/finance-email/` | 管理员 | 本组的财务邮箱 `{finance_email}`；PATCH 同样的结构，空字符串表示不设 |

每周提醒由管理命令 `python manage.py send_finance_reminder` 发送，见 README"生产式部署"。

---

## 知识库、组会、成果（第四期）

三块都是组内公开数据：本组全员可看，外组 404。上传文件的存储名由服务器生成，`name` 保留原文件名；下载时 PDF 和图片 inline，其他类型 attachment。

### 知识库 `/api/docs/`

`DocVersion = {id, number, name, size, sha256, note, uploaded_by: UserBrief, url, created_at}`；`url` 为 `/api/docs/{id}/versions/{number}/file/`
`Doc = {id, title, category, equipment: EquipmentBrief | null, tags: [string], description, author: UserBrief, latest: DocVersion | null, created_at, updated_at}`；`DocDetail = Doc + {versions: [DocVersion]}`（新版本在前）
`category`: `sdk` 设备 SDK | `manual` 使用手册 | `experience` 调试经验 | `procedure` 操作规范 | `template` 代码模板

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/docs/?search=&category=&equipment=&tag=` | 本组全员 | 分页 `Doc`；`search` 按子串匹配标题、说明、标签、设备编号和设备名 |
| POST | `/api/docs/` | 本组全员 | `{title, category, equipment_id?, tags?, description?}` → 201 `DocDetail`；标签最多 10 个，每个不超过 30 字 |
| GET | `/api/docs/{id}/` | 本组全员 | `DocDetail` |
| PATCH | `/api/docs/{id}/` | 作者或管理员 | 同 POST 字段；否则 403 |
| DELETE | `/api/docs/{id}/` | 管理员 | 连同所有版本的文件一起删 |
| POST | `/api/docs/{id}/versions/` | 作者或管理员 | `multipart/form-data`：`file`、`note?` → 201 `DocVersion`。任意类型，单个不超过上传上限（2 GB）。旧版本保留，版本号逐一递增；同时上传撞号 409 |
| GET | `/api/docs/{id}/versions/{number}/file/` | 本组全员 | 下载这一版 |
| GET | `/api/docs/{id}/history/` | 本组全员 | `[HistoryEntry]`；上传新版本不算字段修改，不写历史 |

### 组会 `/api/meetings/`

`AgendaItem = {id, presenter: UserBrief, topic}`；`ActionItem = {id, owner: UserBrief, content, due_date, done_at}`（`due_date` 可空）；`MyActionItem = ActionItem + {meeting: {id, date, title}}`
`MeetingFile = {id, name, size, uploaded_by: UserBrief, url, created_at}`；`url` 为 `/api/meeting-files/{id}/file/`
`Meeting = {id, date, title, minutes, agenda: [AgendaItem], actions: [ActionItem], files: [MeetingFile], created_by: UserBrief, created_at, updated_at}`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/meetings/` | 本组全员 | 分页，日期新的在前 |
| POST | `/api/meetings/` | 管理员 | `{date, title?, minutes?, agenda?: [{presenter_id, topic}], actions?: [{owner_id, content, due_date?}]}` → 201 |
| GET | `/api/meetings/{id}/` | 本组全员 | |
| PATCH | `/api/meetings/{id}/` | 管理员 | `agenda` 整体替换；`actions` 按 `id` 更新已有项、没有 `id` 的新增、没列出的删除，已有项的 `done_at` 保留；`id` 不属于这次组会 400 |
| DELETE | `/api/meetings/{id}/` | 管理员 | 连同附件文件一起删 |
| POST | `/api/meetings/{id}/files/` | 议程里的汇报人或管理员 | `multipart/form-data`：`file` → 201 `MeetingFile`；任意类型，单个不超过上传上限 |
| GET | `/api/meeting-files/{id}/file/` | 本组全员 | 下载 |
| DELETE | `/api/meeting-files/{id}/` | 上传人或管理员 | |
| POST | `/api/action-items/{id}/done/` | 负责人或管理员 | `{done}` → `ActionItem`；`done=true` 记下完成时间，`false` 清空 |
| GET | `/api/meetings/{id}/history/` | 本组全员 | |

### 成果 `/api/achievements/`

`Achievement = {id, type, title, authors, members: [UserBrief], venue, date, status, link, fulltext_name, fulltext_url, notes, created_by: UserBrief, created_at, updated_at}`；写入时用 `member_ids`。`authors` 是按署名顺序的文本（含外单位），`members` 是署名里的本组成员。
`type` 与可用的 `status`：`paper` 论文（`submitted` 投稿中 \| `accepted` 已录用 \| `published` 已发表）、`patent` 专利（`filed` 申请中 \| `granted` 已授权）、`award` 获奖（`awarded`）、`software` 软著（`registered`）。类型与状态不匹配 400。

列表和导出共用过滤参数：`type`、`status`（可逗号分隔多个，如 `accepted,published`）、`year`（按 `date` 的年份）、`member`、`search`（标题、作者、出处）。非法值 400。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/achievements/?…` | 本组全员 | 分页，日期新的在前 |
| POST | `/api/achievements/` | 本组全员 | 同 `Achievement` 的可写字段 → 201 |
| PATCH | `/api/achievements/{id}/` | 登记人、署名的本组成员或管理员 | 否则 403 |
| DELETE | `/api/achievements/{id}/` | 管理员 | 连同全文一起删 |
| GET / POST / DELETE | `/api/achievements/{id}/fulltext/` | 读：本组全员；写：同 PATCH | POST `multipart/form-data` 的 `file`：只收 PDF，单个不超过 50 MB；替换时旧文件在提交后删除。没有全文时 GET 404 |
| GET | `/api/achievements/export/?…` | 本组全员 | `.xlsx`，工作表"成果清单"；加 `files=1` 返回 `成果清单与全文-<日期>.zip`：清单加 `全文/<序号>-<标题>.pdf`，清单的"全文"列写对应路径 |
| GET | `/api/achievements/{id}/history/` | 本组全员 | |

---

## 系统管理 `/api/system/`

只有运维账号（Django 超级用户，通常不属于任何课题组）可用；未改初始密码时 403 `password_change_required`，其他账号 403。

`MailSettings = {mail_enabled, mail_host, mail_port, mail_security, mail_username, mail_from, password_set, last_mail_error, last_mail_error_at}`
`mail_security`: `ssl` | `starttls` | `none`。授权码 `mail_password` 只写：任何响应里都没有它，只有 `password_set`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/system/mail/` | `MailSettings` |
| PUT | `/api/system/mail/` | 整张表单；`mail_password` 省略或为空表示不改。启用时必须有 `mail_host`；账号不是邮箱地址时必须有 `mail_from`（没启用时也一样，因为测试邮件会用它）；有账号时必须已有或同时提交授权码。保存后立即生效 |
| GET | `/api/system/mail/history/` | `[HistoryEntry]`，不含授权码；改了授权码的那次 `reason` 为"修改了授权码" |
| POST | `/api/system/mail/test/` | `{to}` → `{to}`。用已保存的设置发一封测试邮件，邮件没启用时也发。没填 SMTP 服务器 409 `not_configured`；SMTP 失败 502 `mail_failed`，`message` 是服务器给的原因加上要检查什么，如"发送失败：535 Error: authentication failed。账号或授权码不对……" |
| GET | `/api/system/version/` | `{current, latest, url, error, checked_at, update_available}`。`current` 是正在运行的镜像版本（环境变量 `APP_VERSION`，从源码构建时为 `local`）；`latest`、`url` 是 GitHub 上最新的正式发布（`UPDATE_REPO`），还没有发布过或连不上 GitHub 时 `latest` 为 null，连不上时 `error` 说明原因。结果缓存 6 小时，失败时缓存 10 分钟。`update_available`：两者都是 `vX.Y.Z` 且最新的更大。不提供一键更新，更新在服务器上运行 `scripts/update.sh` |
| GET / POST | `/api/system/groups/` | 课题组 `{id, name, finance_email, member_count, created_at}`（`member_count`：在籍成员）；名称重复 400 |
| PATCH | `/api/system/groups/{id}/` | `{name?, finance_email?}`；不能删除 |
| GET | `/api/system/accounts/?search=&group=&role=&is_active=` | 所有课题组的成员账号，分页，不含运维账号 |
| POST | `/api/system/accounts/` | `{username, name, role, group_id, password, email?, phone?, research_direction?}` → 201，`must_change_password=true`；用户名重复 409 |
| PATCH | `/api/system/accounts/{id}/` | `{name?, role?, email?, phone?, research_direction?, is_active?}`；课题组和登录名创建后不能改；运维账号 404 |
| POST | `/api/system/accounts/{id}/reset-password/` | `{password}` → 204，对方下次登录需改密码 |

`Account = {id, username, name, role, group: {id, name} | null, email, phone, research_direction, is_active, must_change_password, last_login}`

邮件的发送失败（业务通知和测试邮件都算）记为 `last_mail_error` / `last_mail_error_at`，格式同上（原因 + 要检查什么，见 `docs/mail-setup.md`），之后发送成功一次就清空。

---

## 历史记录 `HistoryEntry`

由 `core.history.serialize_history(obj)` 生成，最新在前。外键字段（项目、保管人、台账设备等）的 `old` / `new` 是对象的名称，成员显示姓名；对象已删除时退回为 id。

```json
{"id": 12, "date": "2026-11-16T10:32:00+08:00", "type": "changed", "user": {"id": 3, "name": "陈同学"},
 "reason": "", "changes": [{"field": "status", "old": "draft", "new": "submitted"}]}
```

退回操作的 `reason` 通过 `obj._change_reason = reason` 写入历史记录，在 `HistoryEntry.reason` 中可见。

内嵌对象的序列化器放在对象所属模块的 `serializers.py`：`UserBrief` 在 `accounts`，`ProjectBrief` 在 `projects`，`DatasetBrief` 在 `datasets`，`EquipmentBrief` 在 `equipment`，`ExperimentBrief`、`RunBrief` 在 `research`，`WeeklyReportBrief` 在 `reports`。各 app 直接引用，不要各自重复定义；能引用哪些模块见 `docs/architecture.md` 的分层表。

`type`: `created` | `changed` | `deleted`
