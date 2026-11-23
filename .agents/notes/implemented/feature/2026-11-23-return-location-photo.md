# Agent Note: 设备与试件（工件）非强制放回位置实拍与找物线索（Issue #48 F2）

Status: implemented

## Problem

- 课题组的便携超声设备与试块/试件经常由不同成员借用后放回不同实验台或试块柜，下一个人经常找不到物品放在哪里。
- 原先只有设备使用登记支持 1 张照片，且页面上只有一个原生 `<input type="file">`，无压缩、无选图前缩略图，保存后在设备详情页也只是底部表格里的两个字链接"照片"；试件归还则完全不支持照片和更新实际放回位置。
- 用户在 Issue #48 讨论中明确：拍照只是为了方便下一个人知道设备/工件放哪了，**不能做成强制要求**，聚焦在设备使用与试件归还即可。

## Decision

- **前端共用 `PhotoPicker` 与客户端压缩**（`frontend/src/components/PhotoPicker.vue`、`frontend/src/utils/image.ts`）：
  - 扩展 `image.ts` 增加 `resizeJpeg` / `preparePhoto`，在浏览器内将大图等比压缩为长边 ≤ 1920px 的标准 JPEG（保持不引入 Pillow 依赖），自动处理手机大体积拍照；同时支持 `Ctrl+V` 粘贴截图、上传前缩略图预览和清空/重选，且切换记录时彻底重置 DOM 文件状态。
  - `PhotoPicker` 增加 `v-model:processing` 压缩中状态与请求序号防竞态（快速重选、移除或关闭弹窗时丢弃过期的慢速压缩结果）；试件归还弹窗（`SpecimenDetailView.vue`）与设备使用登记弹窗（`BookingsView.vue`）在照片处理期间均禁用 `FormDialog` 提交按钮并在提交函数内二次拦截，避免大图压缩未结束就提交导致漏传照片。
- **试件归还支持可选照片与放回位置**（`backend/specimens/`、`SpecimenDetailView.vue`）：
  - `SpecimenLoan` 新增 `return_location`、`return_photo`（`specimens/<uuid>.<ext>`，JPG/PNG/WebP，≤ 10 MB）、`return_photo_size`、`return_photo_uploaded_at`（迁移 `0002_specimenloan_return_location_photo`）。
  - `POST /api/specimens/{id}/return/` 同时兼容原 JSON 与 `multipart/form-data`，全部新字段均为可选；事务内先锁 `Specimen` 再锁未归还的 `SpecimenLoan`（与 `borrow()` 和编辑保持一致的加锁顺序），保存失败回滚时清理已写入的存储文件；填写了 `return_location` 且与当前位置不同时，同步更新 `Specimen.location` 并写入修改历史原因。
  - 新增 `GET /api/specimens/{id}/loans/{loan_id}/photo/`，按课题组隔离（外组 404），内联返回图片。
  - `SpecimenDetailView.vue` 将归还确认从单行 `prompt` 升级为 `FormDialog`（放回位置、归还说明、可选 `PhotoPicker`），在详情页顶部显眼展示"最近放回实拍"缩略图（`el-image` 点击放大）与位置/归还人，借用记录表格中同样显示缩略图；列表接口不预取照片记录，避免列表查询 N+1。
- **设备详情与预约登记同步升级**（`EquipmentDetailView.vue`、`BookingsView.vue`）：
  - `EquipmentDetailView.vue` 直接复用 `recent_usage` 中最近一条带照片的记录，在顶部信息卡展示"最近使用实拍"缩略图，表格中"照片"文字链接改为可点击放大缩略图。
  - `BookingsView.vue` 使用登记弹窗改用共用 `PhotoPicker`，不触碰 `backend/equipment/`（不影响设备并发 TLA+ 模型）。
- **存储用量统计**：`backend/workbench/storage.py` 与 `SystemStorage.vue` 增加 `specimens` 桶，统计试件归还照片大小与月度趋势。

## Alternatives considered

- **在实验记录、项目进展也统一加拍照**：用户明确否决，认为拍照定位是找工件位置而非过程打卡，保持聚焦设备和试件更克制。
- **给设备 `UsageReport` 也加 `return_location` 字段**：会改动 `backend/equipment/` 的模型、序列化器和视图并需要同步重跑 TLA+ 检查；设备已有使用说明与照片，本次先不动设备后端模型，等需要时单独演进。
- **后端引入 Pillow 压缩图片**：违背最少依赖原则；延续头像上传的浏览器端 Canvas 压缩方案，服务器只做扩展名和 10 MB 上限校验。

## Consequences

- 归还试件与登记设备使用依然零强制门槛，不拍照片照常提交；拍了照片后，下一个人打开设备或试件详情页第一眼即可看到放回位置和实拍图。
- `Specimen` 列表接口查询次数不变；详情只预取按归还时间、编号倒序的第一条有照片记录，下载照片和查看借用历史无需预取。
- 验证：
  - `scripts/check.sh`：75 篇决策笔记校验通过，`makemigrations --check` 无漂移，`scripts/check_module_deps.py` 0 违规；后端 `pytest` 511 passed, 1 skipped；前端 `vitest` 51 个测试文件 178 passed（含 `PhotoPicker.test.ts`、`SpecimenDetailView.test.ts` 与 `BookingsView.test.ts` 压缩期间禁提交回归测试）且 `vue-tsc --noEmit && vite build` 通过。
  - 浏览器（`verify-lab`）：已在隔离实例实测通过（2.88 MB PNG 压缩期间试件归还「登记归还」与设备使用登记「登记」按钮均禁用、点击不发请求，压缩为 684 KB JPEG 后提交成功并在详情页展示缩略图，`query.sh` 核对数据库与文件落盘），证据在 `backend/var/verify-evidence/2026-11-23-pr49-photo-race/`。
