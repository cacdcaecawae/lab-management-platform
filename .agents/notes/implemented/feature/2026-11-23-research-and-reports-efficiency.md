# Agent Note: 周报汇总导出与科研记录/数据集效率增强（Issue #48 N4、N5、S2）

Status: implemented

## Problem

- 周报是课题组每周高频流程，但存在多处断点：导师批阅时需逐份点开、无法在一页通览本周全组进展或导出组会汇总文档；批完一份还要退回列表再点下一份；周报列表不支持关键词搜索与成员筛选；学生新建周报时无法把上周的「下周计划」带入「本周目标」，且已有本周周报时点击「写本周周报」会进新建页并在保存时撞 409。
- 科研记录与数据集存在后端已有能力未接前端、以及高频缺口：后端早已支持 `DELETE` 草稿、`PATCH/DELETE` 数据集和 `?owner=` 成员筛选，但前端页面都没有入口；批量重复参数实验/数据处理只能手填重录，没有「复制为新草稿」；数据集只支持逐个文件下载，无法打包 ZIP，也看不到被哪些实验/处理记录/周报引用。

## Decision

- **周报汇总、导出与搜索（`backend/reports/views.py` + `ReportsView.vue` / `ReportEditView.vue`）**：
  - `WeeklyReportViewSet` 启用 `SearchFilter`，覆盖学生姓名与四段正文（`owner__name`, `goals`, `done`, `findings`, `next_plan`）。
  - 新增导师专属 `GET /api/reports/digest/?week_start=` 与 `GET /api/reports/digest/export/?week_start=`：仅汇总本组非草稿周报与未交名单，导出 UTF-8 Markdown（`Cache-Control: private, no-store`）。
  - 前端新增「本周汇总」标签页（含一键导出 Markdown `IconButton`）、搜索框与导师端成员筛选；「本周汇总」与「未交名单」切换周次/标签及详情页切换周报时，结合单调请求序号与 `AbortController` 中止过期请求并清空旧周缓存，避免快速切换周次时旧响应晚到覆盖当前日期；学生点击「写本周周报」先查询本周是否已有记录，有则直接打开；未交名单查询失败时显示重试入口；新建周报按所选周一减七天精确查询本人的周报，从列表响应直接带入计划；本人草稿支持「删除草稿」；导师反馈完成后自动探测下一份待反馈周报并提供「下一份待反馈」连续批阅按钮。
- **科研记录与数据集效率增强（`backend/datasets/views.py` + `research`/`datasets` 前端）**：
  - 新增 `GET /api/datasets/{id}/download-zip/?version=`：复用快照版本查询，空集 409 `empty_dataset`，总大小超上限（默认 200 MB，可通过 `DATASET_ZIP_MAX_BYTES` 配置）413 `too_large_for_zip`，通过 `SpooledTemporaryFile` + `ZIP_STORED` 分块流式写入并捕获底层文件缺失返回 404。
  - 新增 `GET /api/datasets/{id}/references/`：直接通过 Django 反向关联管理器（`experiments`、`used_by_runs`、`script_of_runs`、`produced_by_runs`、`weekly_reports`）并施加 `scope_private` 返回反向引用，**不引入 `datasets → research/reports` 模块依赖**，完整遵守 `scripts/check_module_deps.py` 分层边界。
  - 实验记录、数据处理记录与数据集列表为导师补齐成员（`?owner=`）筛选下拉；实验/处理详情页补齐「复制为新草稿」（仅复制本人可见的数据集引用，结果数据集与异常清空）与本人草稿「删除草稿」；数据集详情页补齐 `FormDialog` 编辑名称/说明、打包下载 ZIP、空且无引用时删除数据集、以及「被引用处」卡片。

## Alternatives considered

- **在 `datasets/views.py` 中直接 import `ExperimentSerializer` / `WeeklyReportBriefSerializer` 序列化反向引用**：会破坏 `datasets` 仅依赖 `BASE` 的模块边界规则（`scripts/check_module_deps.py` 报错）。改用模型实例上的反向管理器直接拼装轻量字典，零跨层 import。
- **周报汇总直接复用 `/api/reports/?week_start=` 在前端拼接**：列表接口返回分页结果且包含草稿、不含未交名单，也不便于后端导出单文件 Markdown；独立的 `digest` 与 `digest/export` 复用同一查询方法 `_digest_data`，保证页面展示与导出文件严格一致。
- **后端为实验/处理记录新增 `POST /{id}/clone/` 端点**：会在用户确认前直接落库脏草稿；改为前端路由 `/experiments/new?copy={id}` 预填表单，用户调整后再保存，避免产生垃圾草稿。

## Consequences

- 导师可一页通览并导出全组周报、按内容与成员检索、连续批阅待反馈周报；学生写周报与重复参数实验更省力；数据集具备完整的编辑、安全删除、整包 ZIP 下载与双向引用追踪能力。
- 未改动数据库表结构，无需迁移。
- 验证：
  - `scripts/check_module_deps.py`：0 violation。
  - `scripts/check.sh`：决策笔记校验通过（75 notes）；`makemigrations --check` 无待生成迁移；后端 `pytest` 496 passed, 1 skipped（`DB_TEST_NAME=test_lab_reports`）；前端 `vitest` 49 个测试文件 175 passed（含 `ReportsView.test.ts` 快速切换周次中止旧请求并忽略晚到旧响应的回归测试）；`vue-tsc --noEmit && vite build` 通过。
  - 浏览器（`verify-lab`）：已在隔离实例实测通过（导师在「本周汇总」快速从暂停的 `2026-11-09` 切到 `2026-11-16`，旧请求在 Chrome 网络层被中止，日期框、周报正文与未交名单严格对应 `2026-11-16`，切回 `2026-11-09` 亦正常显示，`query.sh` 核对数据库），证据在 `backend/var/verify-evidence/2026-11-23-pr52-report-digest/`。
