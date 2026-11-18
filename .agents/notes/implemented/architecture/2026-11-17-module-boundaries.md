# Agent Note: 模块边界：core 不再引用业务模块，前端按模块分目录，依赖由脚本检查

Status: implemented

## Problem

[模块化单体](2026-11-16-modular-monolith-stack.md)定了"一个 Django 项目，按 app 分模块"，但没有规定模块之间谁能引用谁。四期做完后（不算测试和迁移）：

- **后端业务模块之间没有循环**，依赖是单向的：`projects` 在下，`procurement` 被 `equipment`、`inventory` 引用（到货登记），`research` 引用 `datasets`、`equipment`，`reports` 引用 `research`、`datasets`。
- **最底层的 `core` 反过来引用了 9 个业务模块**：
  - `core/views.py`：工作台汇总，引用设备、耗材、组会、采购、周报、实验的模型和序列化器，还从 `procurement.views`、`reports.views` 引入待审批、退回、未交周报的查询。
  - `core/serializers.py`：项目、设备、数据集、实验、处理记录、周报的简要序列化器，以及数据集版本标注 `add_pinned_versions`。
  - `core/files.py`：从 `datasets/views.py`（HTTP 视图）引入 `clean_file_name`、`FileTooLarge`；`knowledge/views.py` 也从那里引入 `sha256_of`。
  - `core/system_*.py`（系统管理）引用 `accounts`，而 `accounts` 又引用 `core`，形成循环。
- **前端没有模块**：30 个页面平铺在 `src/views/`，`src/api/equipment.ts` 里还混着耗材的接口。
- **没有任何检查**：哪天在 `core` 里再引用一个业务模块，测试照样通过。

检查脚本第一次运行，在改动前的代码上报出 26 条违规。

## Decision

只搬视图、序列化器、工具函数和前端文件，不搬模型、不改 app 名、不改接口和页面行为。

**后端分层**（下层不引用上层），表格和"模块的对外部分"写在 `docs/architecture.md`：

- 底座 `core` 只用 Django / DRF；`accounts` → core；`projects` → accounts、core。
- 业务：`datasets`、`procurement`、`meetings`、`achievements` 只引用 projects 及以下；`equipment`、`inventory` 另可引用 `procurement`；`research` 另可引用 `datasets`、`equipment`；`knowledge` 另可引用 `equipment`；`reports` 另可引用 `research`、`datasets`。
- 汇总：新 app `workbench`（工作台，可引用所有业务模块）和 `system`（系统管理，只引用 accounts、core），都没有模型。
- 别的模块只能引用 `models`、`serializers`、`mixins` 和专门对外的 `versions.py`、`queries.py`；`views`、`urls`、`admin` 属于模块内部。

具体改动：

- `clean_file_name`、`FileTooLarge`、`sha256_of` 移到 `core/files.py`。
- `awaiting_review`、`returned_flag` 移到 `procurement/queries.py`，`current_week_start`、`missing_students` 移到 `reports/queries.py`；采购列表和工作台共用同一个"等我审批"的定义。
- `core/serializers.py` 删除，简要序列化器回到各自模块，`add_pinned_versions` 移到 `datasets/versions.py`。
- 工作台移到 `workbench`，系统管理移到 `system`；`SiteSettings` 模型和邮件发送留在 `core`。系统管理和成员页共用的重置密码动作移到 `accounts/mixins.py`。
- URL 不变。

**前端按业务分目录，依赖按页面职责定**，不套用后端分层表：后端是知识库文档关联设备（`knowledge → equipment`），前端的设备详情页却要调用知识库接口列出这台设备的文档。

- `src/modules/<模块>/`：`api.ts` 对外；`views/`、`components/` 属于模块内部；`index.ts` 导出路由，`router/index.ts` 把它们拼起来。
- 页面可以引用任何模块的 `api`，不能引用别的模块的页面和组件；还没搬的 `src/views/` 也按页面对待。公共部分（`api/client.ts`、`api/types.ts`、`components/`、`composables/`、`utils/`、`stores/`、`layouts/`）不能引用 `src/modules/`。
- 类型暂时都留在 `src/api/types.ts`。
- **先试点**：只搬了 `equipment`（设备台账、详情、预约，`EquipmentFormDialog`、`BookingFormDialog`）和 `knowledge`。耗材接口从 `api/equipment.ts` 拆到 `api/inventory.ts`。`EquipmentFormDialog` 的测试跟着组件搬到 `modules/equipment/components/EquipmentFormDialog.test.ts`。

**检查**：`scripts/check_module_deps.py` 用 `ast` 读后端的 import、用正则读前端的引用，对照规则表；测试、迁移、`conftest.py` 不检查。`backend/tests/test_module_deps.py` 用人为制造的违规确认脚本会报错，并在当前代码上运行它，所以 `scripts/check.sh` 和以后的 CI 都会检查。

## Alternatives considered

- **前后端共用一张依赖表**：规则简单。但设备详情页列文档这类"按页面职责调用别的模块"的情况会直接撞墙。
- **工作台做成插件注册**：`core` 也能不依赖业务模块。但工作台只有这一处汇总，放进可以引用所有模块的 `workbench` app，代码更少。
- **每个模块再分 service / repository 层**：视图大多是 DRF 的标准增删改查，多一层只是转手；被别的模块复用的查询放进 `queries.py`，收益更具体。
- **拆成微服务**：组内隔离、跨模块查询（工作台、报销关联采购单）都要跨服务，事务也没法保证。以后真要拆，单向依赖加上"各模块只写自己的表"就是前提。
- **按部署开关模块**：`equipment`、`inventory` 用外键关联采购单，关掉下层模块要拆外键；目前没人提这个需求。
- **把 `SiteSettings` 模型一起搬到 `system`**：要做跨 app 的模型迁移，已有数据库得跟着迁，风险大于收益。
- **前端一次搬完 30 个页面**：规则没在真实页面上试过，搬完发现不合适还得再搬一遍。
- **import-linter / eslint 插件**：要新增依赖，而这里只要两张规则表（[依赖最少](../process/2026-11-16-minimal-dependencies.md)）。

## Consequences

- 验证（2026-11-18）：后端 319 个测试（原 316 个加检查脚本的 3 个）、前端 60 个测试（11 个文件）、生产构建通过；检查脚本退出码 0。设备并发模型检查 10 项运行全部符合预期；覆盖范围内的改动逐项核对过：`EquipmentFormDialog.vue` 只改了 import 路径，`equipment/serializers.py` 只新增了只读的 `EquipmentBriefSerializer`，`settings.py` 只改了 `INSTALLED_APPS`。
- 浏览器（verify-lab，证据在 `backend/var/verify-evidence/2026-11-18-module-boundaries/`）：管理员新增设备、编辑存放位置、在知识库新建关联这台设备的文档并上传文件，设备详情页"资料"一栏列出该文档；新建预约；耗材页、新建实验记录页的设备选项、工作台正常；运维账号打开系统管理的邮件和账号页，并重置了一个账号的密码。数据库读回的结果一致，控制台只有登录前 `/api/auth/me/` 的 403（未登录时本来就是 403）。
- **还没做**：其余页面要不要搬进 `src/modules/`、类型要不要按模块拆，看试点效果后另行确认。在那之前，新旧两种目录结构并存。
- 新增模块或新增依赖时，要同时改 `scripts/check_module_deps.py` 和 `docs/architecture.md`，否则测试失败。这是故意的：新增依赖必须有人看过。
