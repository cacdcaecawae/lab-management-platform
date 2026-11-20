---
name: verify-equipment-tla
description: 用 TLA+ 模型检查器（TLC）穷举设备预约的并发交错：建预约、使用登记、取消预约、管理员编辑设备同时发生时，"登记异常后到管理员处理前不能建使用预约"等 5 条规则是否成立。改了 backend/equipment 的 views.py / serializers.py / models.py、config/settings.py 的数据库设置，或 EquipmentFormDialog.vue 之后使用；也用于判断这些代码是否还和模型一致。
---

# 设备预约并发交错的模型检查

模型 `spec/EquipmentBooking.tla` 描述一台设备、它的预约和同时进行的请求，按 PostgreSQL 的加锁行为一步步交错。TLC 检查所有交错顺序，不是抽样。命令都在仓库根目录 `lab-management-platform/` 下用 Bash（Git Bash）运行。

## 检查什么

| # | 规则（模型里的名字） | 一句话 | 被打破时的后果 |
|---|---|---|---|
| 1 | `NoUseBookingWhileFlagged` | 异常登记把设备改成"待检查"后，到管理员处理之前，不能新建使用预约 | 有故障的设备被继续预约使用 |
| 2 | `NoSilentRevert` | 这期间设备状态不会变回"可用" | 工作台的"待检查"提醒消失，规则 1 随之失守 |
| 3 | `NotCancelledAndReported` | 一个预约不会既被取消又被登记 | 统计和使用记录对不上 |
| 4 | `OneReportNo500` | 每个预约最多一条使用登记，重复登记得到 409 而不是服务器错误 | 用户看到 500 |
| 5 | TLC 死锁检查 | 锁等待不会成环 | PostgreSQL 会杀掉其中一个请求，用户看到 500 |

"管理员处理"在模型里的意思是：编辑表单打开时显示的是"待检查"，并且请求里明确给出了状态（`Handles`）。服务器无法区分"故意改回可用"和"旧表单把可用带回来"，所以按表单看到的状态判断。

维护预约在"待检查"时允许建（`c21d993`），规则 1 只管使用预约。设备原本就不是"可用"时，异常登记不改状态，模型也不把它算作待处理。

## 运行

```bash
bash .claude/skills/verify-equipment-tla/scripts/check.sh
```

依赖：Java 11 以上（本机 Java 17），以及 `~/.tlaplus/tla2tools.jar`，也可以用环境变量 `TLA2TOOLS` 指定路径。脚本会核对 jar 的 SHA256，要求是 tla2tools v1.7.4，也就是 TLC 2.19。数据库设置检查需要 Python 3（默认使用 `python`，可传 `PYTHON`）。全部运行约 30 秒。

脚本先列出被覆盖的代码自 `SYNC` 以来的改动（分别检查 HEAD、暂存区及工作区），再跑 10 次 TLC，把每次结果和脚本里写的预期比对：

- 退出码 0：结果全部符合预期，被覆盖的代码也没变。
- 退出码 1：有一行是 `DIFF`，或者 TLC 没能运行。
- 退出码 2：结果全部符合预期，但被覆盖的代码变了。这时 TLC 的通过不说明任何问题，因为模型描述的还是旧代码。按下面"代码改了以后"的步骤处理。

TLC 的输出和配置在 `$TEMP/verify-equipment-tla/`（每次运行时清空），每次运行一个 `<名字>.log` 和 `<名字>.cfg`。

| 运行 | 内容 | 当前预期 |
|---|---|---|
| `interleavings` | 建预约、登记、取消，3 个并发请求 | 通过 |
| `with-edits-patch-no-status` | 再加上管理员编辑，编辑不改状态 | 通过（F1） |
| `with-edits` | 编辑也可以改状态 | 通过（R1） |
| `break-*`（7 个） | 各自去掉代码里的一处保护（模型里的 `Mutant` 分支） | 各自打破对应规则，证明检查还能失败 |

其中 `break-edit-writes-stale-status`（没带状态时，服务器写回 `get_object()` 读到的旧状态）对应 F1 的修复，`break-edit-skips-status-seen-check`（服务器不核对 `status_seen`）对应 R1 的修复。表单只提交改过的字段，在模型里已经不是安全所必需：多提交一个没改的状态，会被 `status_seen` 核对拦成 409。它的作用是避免这种无谓的 409。

## 读结果

- 读每个失败结果时用 `/statechart` 技能：它给出每条被打破规则的最短路径，用读者的话描述，没有违反时会画出状态图。`spec/view.mjs` 是本模型的视图，把状态归并成管理员看到的设备状态；它通过了 `/statechart` 的视图校验，但还没有真正画出过图。
- 2026-11-17 在 Windows 上试了两次 `/statechart`，它要启动 `/bin/sh`，在 Windows 上跑不起来。这时直接读 log：每个 `State N: <动作名 ...>` 是一步，下面是这一步之后的变量值。用下表把动作名换成代码里的那一步。
- 预期违反的运行（`break-*`）在第一个违反处就停止，并不完整探索。含编辑的完整检查由 `with-edits-patch-no-status` 和 `with-edits` 完成，它们查全部规则和死锁。

## 真缺陷还是模型错

拿反例的每一步对照下表，去真实代码里看这一步能不能这样发生：

- **某一步在代码里不可能发生**：模型错了。改模型，并在报告里写明错在哪里。不要为了通过去改规则。
- **每一步都能发生**：这是代码缺陷。在仓库外的临时 `git worktree` 里写一个按反例顺序调用接口的 pytest 来复现（用自己的 `DB_TEST_NAME`，跑完删除 worktree），然后用代码里的话报告：每一步是什么、后果是什么。不要改产品代码，除非用户要求；修复先写 `bug-fix` 方案笔记。

## 覆盖范围（模型的每一步对应的代码）

截至 `SYNC=e731809`。从同一基线对照设备模块的三个覆盖文件、设备表单及 `settings.py` 的数据库部分。数据库部分使用 Python AST 识别简单的顶层 `DATABASES` 字典、相关覆盖配置和环境初始化，不执行设置文件；注释和纯格式变化不触发复核。提取不确定（例如动态表达式、二次赋值、通配符导入）时按有改动复核。基线提交不可读取时退出 1，不自动改 `SYNC`。

| 模型动作 | 代码 | 说明 |
|---|---|---|
| `CreateStart` | `BookingViewSet.perform_create` 开头；`BookingSerializer.validate` | 学生的维护预约在任何 SQL 之前返回 403，不建模 |
| `CreateLockEquipment` | `perform_create`：`transaction.atomic()` 内 `Equipment.objects.select_for_update().get(...)`，使用预约要求状态为"可用" | 加锁并检查 |
| `CreateInsertBooking` | `perform_create`：`serializer.save(...)`；`models.py` `Booking.Meta.constraints` 的 `no_overlapping_bookings`；`except IntegrityError` → 409 | 同一时间段有别的事务正在插入或取消预约时先等待，有有效重叠就返回 409 |
| `ReportStart` | `BookingViewSet.report`：`self.get_object()`、`UsageReportSerializer` 校验 | 非预约人在任何 SQL 之前返回 403 |
| `ReportLockBooking` | `report`：`lock_booking()`，然后检查类型、未取消、已开始、`UsageReport...exists()` | |
| `ReportInsert` | `report`：`新建 UsageReport 后调用 report.save()`；`UsageReport.booking` 是 `OneToOneField` | 数据库插入仍在预约行锁内；事务回滚时清理新照片，随后重新抛出原异常 |
| `ReportMarkEquipment` | `report`：异常时 `Equipment.objects.select_for_update()`，状态为"可用"才改成"待检查"再 `save()` | |
| `CancelLockBooking` | `BookingViewSet.cancel`：`lock_booking()`，然后检查未取消、学生只能在开始前取消、`UsageReport...exists()` | |
| `CancelUpdate` | `cancel`：`booking.save(update_fields=["cancelled_at"])` | |
| `EditOpenForm` | `frontend/src/modules/equipment/components/EquipmentFormDialog.vue`：打开时记下表单值（`opened`），保存时只 PATCH 和它不同的字段；改了状态时带上 `status_seen: opened.status` | 状态没改就不带（`"omit"`），所以只能带和打开时不同的状态；`status_seen` 就是 `formSeen` |
| `EditRead` | `EquipmentViewSet.partial_update` → DRF `UpdateModelMixin.update` → `get_object()` | 普通 SELECT，不加锁；读到的值只在 `edit_writes_stale_status` 变体里用 |
| `EditUpdate` | `EquipmentSerializer.save()`：`transaction.atomic()` 内 `EquipmentSerializer.update()` 先 `Equipment.objects.select_for_update().get(pk=...)` 重读；带了状态而锁下的状态既不是 `status_seen` 也不是新状态时 `Conflict`（409 `stale_status`），否则写上请求里的字段并 `save()` | 等行锁；没带状态时写锁下读到的最新状态 |
| `*Commit` / `Rollback` | `transaction.atomic()` 结束或抛异常 | |
| `Tick` | 时间推进，预约到达开始时间 | |

假设：

- 编辑设备的客户端只有 `EquipmentFormDialog.vue`。服务器要求改状态时必带 `status_seen`，别的客户端只要如实填写打开时看到的状态，就同样受保护。
- PostgreSQL 默认的 READ COMMITTED。`backend/config/settings.py` 的 `DATABASES` 里没有设隔离级别，也没有开 `ATOMIC_REQUESTS`。
- `SELECT ... FOR UPDATE` 和 `UPDATE` 等待行锁，拿到锁后读到的是最新提交的值。
- 插入预约时，排他约束只等待正在插入或修改重叠预约的事务；对只被 FOR UPDATE 锁住的行，插入直接冲突，不等待。
- 每一步是一条访问共享行的 SQL 语句，Python 里的检查并入它所依赖的那条语句。
- 设备的采购关联（第三期的 `purchase_id`）和存放位置一样，是在 `EditUpdate` 的行锁下写入的非状态字段，不在模型里。它只能选"已到货"的采购申请；已到货是终态，申请也不能再删除，所以校验时那次不加锁的查询不会读到过期状态。

界限：

- 1 台设备。
- 预约 1（已开始，时间段 1）、预约 2（未开始，时间段 2），每个请求最多再插入一个预约。
- 3 个并发请求，每个进程发一个请求。
- 时间段 {1, 2, 3}，同一时间段即视为重叠。
- 设备状态 {可用, 待检查, 维修或停用}。

检查通过只说明在这个界限内没有反例。

范围外：

- 权限与 404。
- 邮件通知、照片存储。
- `/admin/` 后台（它可以绕过这些检查直接改数据）。
- 耗材库存。
- 多台设备。
- 同一个用户连续发多个请求。

## 问题 F1（已修复）：管理员保存设备会把"待检查"写回"可用"

修复前，管理员打开编辑框后，学生登记异常把设备改成"待检查"；管理员再保存，表单里旧的"可用"随整张表单提交，状态被改回"可用"，之后又能建使用预约。只发 `{location}` 的 PATCH 也会出现：`get_object()` 不加锁读到"可用"，异常登记在 `instance.save()` 之前提交，读到的"可用"被整行写回。

修复（见 `.agents/notes/implemented/bug-fix/2026-11-17-equipment-edit-stale-status.md`）：

- 表单只提交改过的字段，状态没改就不带。
- `EquipmentSerializer.update()` 在行锁下重读设备，没提交的字段保留最新值。

回归测试：`backend/equipment/tests/test_equipment.py` 的 `test_patch_racing_abnormal_report_keeps_needs_check`（两个数据库连接，异常登记在 `get_object()` 和保存之间提交），以及 `frontend/src/modules/equipment/components/EquipmentFormDialog.test.ts`。

## 问题 R1（已修复）：旧表单里主动选的状态，会盖掉期间的"待检查"

F1 修复后，`with-edits` 还有一个反例：管理员打开编辑框时看到"可用"，选了"维修"还没保存；这期间学生登记异常，设备变为"待检查"；管理员保存，明确提交的"维修"盖掉了"待检查"，工作台提醒消失。之后有人把"维修"改回"可用"，没有管理员看到过这次异常。4 个请求时还有同类路径：A 在"维修"时打开表单选了"可用"，B 先改回"可用"，学生登记异常，A 保存。

修复（见 `.agents/notes/implemented/bug-fix/2026-11-17-equipment-status-seen-check.md`）：

- 改状态的 PATCH 必须带 `status_seen`，即表单打开时看到的状态。
- `EquipmentSerializer.update()` 在行锁下比对：当前状态既不是 `status_seen` 也不是新状态时，返回 409 `stale_status`。表单弹出警告、关闭，并让详情页重新加载。

`with-edits` 现在完整通过；`break-edit-skips-status-seen-check` 去掉比对，规则 2 随之失败。4 个并发请求的一次性运行结果见 R1 笔记。
