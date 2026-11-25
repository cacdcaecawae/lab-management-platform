# 系统架构

依据：`../2026-11-16_课题组管理平台研讨_会议纪要.md`（业务意图）、`../2026-11-16_课题组管理平台_开发手册_v0.1.md`（功能细节）。冲突时以会议纪要和最新开发指令为准（例：[AI 模块本期不做](../.agents/notes/implemented/feature/2026-11-16-ai-module-deferred.md)）。

## 总体

模块化单体：一个 Django 项目 + 一个 Vue SPA + 一个 PostgreSQL。

```
浏览器 ──HTTPS──> Nginx ──┬── /            Vue 打包后的静态文件
                          ├── /api/  ──> Gunicorn ──> Django ──> PostgreSQL
                          │   （/admin/ 只在服务器本机的 127.0.0.1:8091，见 infra/nginx.admin.inc）
                          └── （文件下载也走 /api/，由 Django 校验权限）      └──> 文件存储（DATA_ROOT 或以后的对象存储）
```

开发环境：PostgreSQL 用 Docker 启动；Django（`runserver`）和 Vite 在本机运行；Vite 把 `/api`、`/admin` 代理到 Django，浏览器只看到一个源，Session 和 CSRF Cookie 的行为与生产环境一致。

AI 网关（Magpie）是独立系统，本期不开发，平台中不留 AI 相关代码。

## 后端 Django Apps

按层排列，下层不引用上层。"可以引用"一列由 `scripts/check_module_deps.py` 检查（后端测试 `backend/tests/test_module_deps.py` 会运行它），新增模块或依赖时同时改脚本和这张表。方案见[模块边界](../.agents/notes/implemented/architecture/2026-11-17-module-boundaries.md)。

| 层 | App | 职责 | 可以引用 |
|---|---|---|---|
| 底座 | `core` | 数据范围（`scope_private` / `scope_research` / `scope_group`）、权限类、统一错误格式、分页、修改历史、文件存取（`files.py`）、Excel 导出、邮件发送与 SMTP 配置（`SiteSettings`）、站内通知 | 运行期只用 Django / DRF；通知迁移引用账号及课题组模型 |
| 账号 | `accounts` | 课题组 `ResearchGroup`、自定义用户 `User`、登录/退出/改密、成员管理接口 | core |
| 项目 | `projects` | 项目、项目成员、项目进展、任务、里程碑 | accounts、core |
| 业务 | `datasets` | 记录的文件（数据集）：上传/下载、SHA256、不可覆盖、版本、未锁定文件的删除；文件的共享范围（`queries.py`） | projects 及以下 |
| 业务 | `procurement` | 经费来源、采购申请与两级审批、报销与统计、财务提醒 | projects 及以下 |
| 业务 | `meetings` | 组会、议程、行动项、附件 | projects 及以下 |
| 业务 | `achievements` | 论文、专利、获奖、软著，导出 | projects 及以下 |
| 业务 | `specimens` | 试样与标准件台账、缺陷参数（盲测时对学生隐藏）、借用登记 | projects 及以下 |
| 业务 | `equipment` | 设备台账、预约（排他约束防冲突）、使用登记与照片、异常邮件 | procurement、projects 及以下 |
| 业务 | `inventory` | 耗材品类、出入库流水（库存由流水汇总） | procurement、projects 及以下 |
| 业务 | `research` | 实验与原始数据（自带原始数据文件和现场照片，可关联台账设备和试件）、数据处理（引用实验，自带脚本和结果文件）、提交/退回、修改历史 | datasets、equipment、specimens、projects 及以下 |
| 业务 | `knowledge` | 知识库文档与版本 | equipment、projects 及以下 |
| 业务 | `reports` | 周报、反馈、状态流转、未交统计 | research、datasets、projects 及以下 |
| 汇总 | `workbench` | 工作台与存储汇总接口、每日提醒发送去重账本 | 所有业务模块 |
| 汇总 | `system` | 系统管理 `/api/system/`：邮件配置、课题组、所有组的账号（无模型） | accounts、core |

模块的对外部分：别的模块只能引用 `models`、`serializers`（简要序列化器、"本组对象"选择字段）、`mixins` 和专门给别人用的文件（`versions.py`、`queries.py`）；`views`、`urls`、`admin` 属于模块内部。被几个模块共用的查询放进 `queries.py`，例如"哪些采购单等我审批"（`procurement/queries.py`）由采购列表和工作台共用。测试、迁移、`conftest.py` 不受这些规则限制。

模块边界（第一期多代理开发时的分工规则）：
- **第一期全部模型和 0001 迁移由主代理在基线中定义。** 子代理只写序列化器、视图、`urls.py`、业务校验和测试；确需改模型时，只能改自己 app 的 `models.py` 并生成本 app 的迁移，同时在交付说明里写明。
- 公共文件（`config/*`、`core/*`、`conftest.py`、`accounts/models.py`、`docs/*`、`frontend/src/api/client.ts`）只由主代理修改。
- 每个 app 在 `config/urls.py` 中已挂载到 `/api/`，子代理只改本 app 的 `urls.py`。

## 权限与数据隔离

角色：基础角色 `User.role` 是 `student` 学生或 `advisor` 导师；另有两个可叠加的标签 `is_manager` 管理员、`is_approver` 终审人（[笔记](../.agents/notes/implemented/architecture/2026-11-23-roles-and-identity.md)）。导师看全组的科研记录并批阅；管理员管事务（任何基础角色都可以是管理员，学生 + 管理员看不到别的同学的科研记录）；终审人做采购终审，并能给本组账号加或去掉管理员。下表的 supervisor 指"导师或管理员"。身份、入学年份、在籍状态和词条只用于展示和筛选，不参与权限。运维使用 Django 超级用户（通常不属于任何课题组），登录网页后只有"系统管理"（邮件、课题组、账号，接口 `/api/system/`），在业务接口中不获得特殊权限；`/admin/` 留作少见操作的后备，只在服务器本机的端口上开放（SSH 隧道访问），且要先改掉初始密码。

| 数据类别 | 内容 | 读 | 写 |
|---|---|---|---|
| 个人数据 | 实验与原始数据、数据处理（含它们的文件和照片）、周报 | 本人 + 本组导师 | 本人；提交后锁定，导师可退回、批阅 |
| 项目内共享 | 关联了项目并已提交的实验与原始数据、数据处理，连同文件和照片（[笔记](../.agents/notes/implemented/feature/2026-11-25-research-records-merge-and-project-sharing.md)） | 另加该项目的当前成员和负责人 | 只读；可以在自己的数据处理里引用 |
| 个人数据（经费） | 采购申请、报销 | 本人 + 本组管理员和终审人 | 本人；初审：管理员；终审：终审人；报销退回、到账：管理员 |
| 组内公开 | 项目与进展、成员公开信息 | 本组全员 | 项目：supervisor 或项目负责人；成员：管理员 |
| 组内公开 | 项目任务与里程碑 | 本组全员 | 任务建改：项目成员、项目负责人、supervisor；删：任务创建者、项目负责人、supervisor；里程碑增删改：项目负责人或 supervisor |
| 组内公开（第二期） | 设备、预约与使用登记、耗材与流水 | 本组全员 | 台账、入库、盘点：管理员（不含导师）；预约、领用、退回：本人；取消：本人（未开始）或管理员 |
| 组内公开（试样） | 试样与标准件、借用记录；缺陷参数在盲测时（`defects_public=false`）只给管理员和导师 | 本组全员 | 台账：管理员（不含导师）；借用：本人；归还：本人或管理员 |
| 成员隐私 | 学号（登录名）、电话、邮箱 | 本人 + 本组 supervisor | 管理员（普通学生和自己）；管理员标签：终审人；基础角色和终审人：运维 |

实现规则（必须遵守）：
1. 所有业务视图的 `get_queryset()` 必须用 `core.permissions.scope_private()` 或 `scope_group()` 构造。越权对象因此返回 **404**（不泄露是否存在），而不是 403。
2. 写权限在对象级检查（`IsOwnerOrReadOnly` 等），状态流转在视图里显式检查角色和状态。
3. 引用其他对象（如实验关联数据集、周报关联实验）时，被引用对象也必须在同一范围内校验，不能只信任前端传来的 id。
4. 文件下载只能通过带权限检查的视图；`MEDIA_URL` 不对外路由。
5. 默认权限 `IsActiveMember`：未登录 403；初始密码未修改时业务接口 403（`code=password_change_required`）。

## 认证

Django Session（HttpOnly Cookie）+ CSRF。SPA 先 `GET /api/auth/csrf/` 取得 `csrftoken` Cookie，此后所有非 GET 请求带 `X-CSRFToken` 头。登录接口也做 CSRF 校验（防登录 CSRF）。密码哈希、会话、CSRF 全部使用 Django 自带实现。

## 文件存储

- 所有读写都经过 Django Storage API（`FileField`）。开发和单机部署用本地目录 `DATA_ROOT`（持久化卷）；以后改对象存储只需安装 `django-storages[s3]` 并修改 `STORAGES`。
- 磁盘上的文件名由服务器生成（`datasets/<数据集id>/<uuid>`，使用登记照片为 `usage-photos/<uuid>.<扩展名>`），用户文件名只存数据库，杜绝路径穿越。
- 入库时流式计算 SHA256；同一数据集内文件名唯一（数据库约束），重复上传返回 409，不覆盖。
- 未实现：分片上传、断点续传、浏览器直传对象存储、Nginx `X-Accel-Redirect` 下载加速。见 [文件上传与存储](../.agents/notes/implemented/architecture/2026-11-16-file-upload-and-storage.md)。

## 持久化与备份

- PostgreSQL 数据：Docker 卷 `pgdata`。
- 上传文件：`DATA_ROOT`（生产环境挂载数据盘）。
- 配置：环境变量（`.env`，不入库）。
- 备份：`scripts/backup.sh` 把 `pg_dump` 的导出和上传文件写进同一个 restic 快照（restic 跑在 Compose 的 `restic` 服务里，profile `ops`），每天一份留 30 天、每月一份留 12 个月；`scripts/restore.sh` 恢复。
- 发版与更新：推送 `vX.Y.Z` 标签后，GitHub Actions 检查通过再把 backend、web 镜像推到 ghcr.io；服务器 `.env` 的 `APP_VERSION` 选用镜像，`scripts/update.sh` 拉取、备份、切换、检查，失败后仅在迁移记录未变时自动退回；有变化或无法核对时停站保留数据。"系统管理 → 版本"只提示，不在网页里更新。方案见[发版、更新与备份](../.agents/notes/implemented/process/2026-11-18-release-update-backup.md)。

## 前端

Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router。
- `src/api/client.ts`：唯一的请求入口，处理 CSRF 与统一错误（`ApiError`）。
- `src/api/types.ts`：与 `api-contract.md` 一一对应的类型。
- `src/stores/auth.ts`：登录状态；路由守卫负责未登录跳转登录页、未改初始密码跳转改密页。
- 菜单按开发手册 §5，只显示已上线的模块；`meta.supervisor`、`meta.manager`、`meta.finance`（管理员或终审人）只控制界面显示，权限以后端为准。
- 模块目录 `src/modules/<模块>/`（所有业务页面）：`api.ts` 对外，`views/`、`components/` 属于模块内部，`index.ts` 导出路由。前端的依赖按页面承担的职责定，不套用后端分层表：任何模块都可以引用别的模块的 `api`（例如设备详情页列出这台设备的知识库文档），但不能引用别的模块的页面和组件；公共部分（`api/client.ts`、`api/types.ts`、`components/`、`composables/`、`utils/`、`stores/`、`layouts/` 和 `views/` 的外壳页）不能引用 `src/modules/`，只有 `router/index.ts` 引用各模块的 `index.ts`。由同一个脚本检查。

### 登录记录

最小化的登录审计记录由 `accounts` 持有，`system` 只向运维提供 180 天窗口。失败表单里的原样标识、密码和 UA 不入库。应用限流仅保留全站发生分钟，不记录每次请求。按受信任反向代理配置解析来源 IP。

全站搜索由 `workbench/search.py` 汇总，沿用各模块数据范围，匹配和返回字段使用显式白名单。新增模块时按需接入并补权限对照测试，不自动搜索序列化器字段。
