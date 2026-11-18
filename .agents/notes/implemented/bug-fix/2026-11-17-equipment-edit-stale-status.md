# Agent Note: 管理员保存设备时不再把旧状态写回（问题 F1）

Status: implemented

## Problem

[TLA+ 模型检查](../testing/2026-11-17-tla-equipment-booking.md) 找到问题 F1，并已在真实代码上复现：

1. 管理员打开设备编辑对话框，`EquipmentFormDialog.vue` 把当时的状态"可用"填进表单。
2. 学生登记使用"异常"，`BookingViewSet.report` 把设备改为"待检查"，管理员工作台出现提醒。
3. 管理员改了存放位置，点保存。整张表单连同 `status: "available"` 一起 PATCH 过去，`EquipmentSerializer.save()` 写回整行，状态变回"可用"，提醒消失。
4. 另一个学生预约这台设备，预约成功（201）。

后果是有故障的设备被继续预约使用。这个时间窗口是对话框打开的整段时间，正常使用就会碰到。

只带 `{location}` 的 PATCH 也会出同样的问题，只是窗口很窄：`get_object()` 不加锁读到"可用"，异常登记在 `instance.save()` 之前提交，读到的"可用"仍被整行写回。

两条路径根子相同：请求里没打算改的字段，被写成了之前读到的旧值。2026-11-17 用户确认按本方案修复。

## Decision

- **前端只提交改过的字段**：`EquipmentFormDialog.vue` 打开时记下表单值，编辑保存时只 PATCH 和它不同的字段。管理员没动"状态"，请求里就没有 `status`；什么都没改时直接关闭对话框，不发请求。新建设备仍提交整张表单。比较前把 `undefined` 当作 `null`：清空下拉框或日期得到的 `undefined` 会被 JSON 丢掉，现在以 `null` 发出，字段能真正清空。
- **后端在行锁下重新读设备**：`EquipmentSerializer.update()` 在 `save()` 已有的事务里先 `Equipment.objects.select_for_update().get(pk=...)`，再写上请求里的字段并保存。请求没带的字段保留数据库里的最新值，修改历史记录的也是正确的状态。重读时不带 `select_related`（可空外连接不能配 `FOR UPDATE`）；响应里的 `in_use` 沿用 `get_object()` 的注解值。
- **模型同步**：`EditOpenForm` 只能带和打开时不同的状态；`EditUpdate` 写锁下读到的最新状态。新增两个改坏的变体：`edit_writes_stale_status`（服务器写回 `get_object()` 读到的值）和 `form_sends_unchanged_status`（表单把没改的状态也提交），各自让规则 2 失败，说明两处修改都不能少。

## Alternatives considered

- **版本号校验（乐观并发）**：表单带上打开时的 `updated_at`，后端在锁下比较，不一致就返回 409，让管理员刷新后再保存。它最通用：任何 API 客户端提交旧状态都会被拦住，两个管理员同时编辑其他字段也不会互相覆盖。但要改接口契约和前端的冲突处理。而且每次使用登记都会刷新 `updated_at`，开着对话框的管理员保存时常会被打回。
- **只在后端加锁，不改前端**：堵住了竞态路径，但表单路径里 `status` 是明确提交上来的，服务器照样写入，F1 的主要路径还在。模型里的 `break-form-sends-unchanged-status` 就是这种情况。
- **服务器忽略和 `get_object()` 读到的值相同的 `status`**：能堵住表单路径的常见情况，但规则不直观；管理员确实想把状态设回读到的值时，也会被忽略。

## Consequences

- 收益：管理员只改其他字段时，"待检查"不会再被改回"可用"。验证结果：
  - 模型检查中 `with-edits-patch-no-status`（编辑不改状态）和 `with-edits-no-repair`（编辑可以设"可用 / 待检查"）都通过了全部规则和死锁检查。
  - 两个新变体按预期失败。
- 测试：
  - 后端 `test_patch_racing_abnormal_report_keeps_needs_check` 用两个数据库连接让异常登记在 `get_object()` 和保存之间提交。它在修复前失败（状态变回 `available`），修复后通过。`test_patch_keeps_status_set_by_abnormal_report` 覆盖顺序的情况。
  - 前端 `components.test.ts` 的 3 个 `EquipmentFormDialog` 用例（只发改过的字段、改了状态才发状态、没改就不发请求）在修复前都失败。
- 浏览器（verify-lab，2026-11-17）：
  - 管理员先打开编辑框；学生甲随后登记异常；管理员只改存放位置后保存。
  - PATCH 请求体只有 `{"location": …}`，响应和数据库里的状态都是 `needs_check`，修改历史这一条记的也是 `needs_check`。
  - 学生再预约，得到"设备当前为“待检查”，不能预约"。
  - 再打开编辑框不改任何字段直接保存，没有发出请求。
- 顺带解决：保管人离组后，管理员改这台设备的其他字段不再因为保管人一栏报 400（没改保管人就不提交它）。清空保管人或日期以前不会生效，现在会。
- **残留问题 R1**（模型 `with-edits` 的反例；2026-11-17 已由 [修改设备状态时核对打开表单时看到的状态](./2026-11-17-equipment-status-seen-check.md) 修复，`break-form-sends-unchanged-status` 随之删除）：
  - 管理员在旧表单里**主动**选了"维修 / 停用"，而表单打开后设备被异常登记改成了"待检查"。保存时明确提交的状态会覆盖"待检查"：设备仍不能预约，但工作台提醒消失；之后有人看到"维修"改回"可用"，就没有管理员看到过这次异常。
  - 这是"明确提交旧状态"一类问题，本方案挡不住。要挡住，需要提交状态时带上打开时看到的状态，后端在锁下比对，不一致返回 409；这要改接口约定，留待用户决定。
- 两个管理员同时编辑同一台设备的不同字段，现在各自只改自己那部分；改同一个字段时，后保存的覆盖先保存的，和以前一样。
