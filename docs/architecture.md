# 系统架构

依据：`../2026-11-16_课题组管理平台研讨_会议纪要.md`（业务意图）、`../2026-11-16_课题组管理平台_开发手册_v0.1.md`（功能细节）。冲突时以会议纪要和最新开发指令为准（例：[AI 模块本期不做](../.agents/notes/implemented/feature/2026-11-16-ai-module-deferred.md)）。

## 总体

模块化单体：一个 Django 项目 + 一个 Vue SPA + 一个 PostgreSQL。

```
浏览器 ──HTTPS──> Nginx ──┬── /            Vue 打包后的静态文件
                          ├── /api/  /admin/ ──> Gunicorn ──> Django ──> PostgreSQL
                          └── （文件下载也走 /api/，由 Django 校验权限）      └──> 文件存储（DATA_ROOT 或以后的对象存储）
```

开发环境：PostgreSQL 用 Docker 启动；Django（`runserver`）和 Vite 在本机运行；Vite 把 `/api`、`/admin` 代理到 Django，浏览器只看到一个源，Session 和 CSRF Cookie 的行为与生产环境一致。

AI 网关（Magpie）是独立系统，本期不开发，平台中不留 AI 相关代码。

## 后端 Django Apps

| App | 负责人 | 职责 | 依赖 |
|---|---|---|---|
| `core` | 主代理 | 数据范围（`scope_private` / `scope_group`）、权限类、统一错误格式、分页、历史记录序列化；工作台汇总接口 | — |
| `accounts` | 主代理（模型、登录）/ Agent A（成员接口） | 课题组 `ResearchGroup`、自定义用户 `User`、登录/退出/改密、成员管理接口 | core |
| `projects` | Agent A | 项目、项目成员、项目进展 | accounts |
| `datasets` | Agent C | 数据集、数据文件、上传/下载、SHA256、不可覆盖 | projects |
| `research` | Agent B | 实验记录、数据处理记录、提交/退回、修改历史 | projects, datasets |
| `reports` | Agent D | 周报、反馈、状态流转、未交统计 | research, datasets |
| `equipment` | 主代理（第二期） | 设备台账、预约（排他约束防冲突）、使用登记与照片、异常邮件 | projects |
| `inventory` | 主代理（第二期） | 耗材品类、出入库流水（库存由流水汇总） | projects |

模块边界：
- **第一期全部模型和 0001 迁移由主代理在基线中定义。** 子代理只写序列化器、视图、`urls.py`、业务校验和测试；确需改模型时，只能改自己 app 的 `models.py` 并生成本 app 的迁移，同时在交付说明里写明。
- 公共文件（`config/*`、`core/*`、`conftest.py`、`accounts/models.py`、`docs/*`、`frontend/src/api/client.ts`）只由主代理修改。
- 每个 app 在 `config/urls.py` 中已挂载到 `/api/`，子代理只改本 app 的 `urls.py`。

## 权限与数据隔离

角色（`User.role`）：`student` 学生、`manager` 管理员、`advisor` 导师。管理员和导师合称 supervisor。运维使用 Django 超级用户（通常不属于任何课题组），登录网页后只有"系统管理"（邮件、课题组、账号，接口 `/api/system/`），在业务接口中不获得特殊权限；`/admin/` 留作少见操作的后备。

| 数据类别 | 内容 | 读 | 写 |
|---|---|---|---|
| 个人数据 | 实验记录、数据集/文件、处理记录、周报 | 本人 + 本组 supervisor | 本人；提交后锁定，supervisor 可退回 |
| 组内公开 | 项目与进展、成员公开信息 | 本组全员 | 项目：supervisor 或项目负责人；成员：管理员 |
| 组内公开（第二期） | 设备、预约与使用登记、耗材与流水 | 本组全员 | 台账、入库、盘点：管理员（不含导师）；预约、领用、退回：本人；取消：本人（未开始）或管理员 |
| 成员隐私 | 学号（登录名）、电话、邮箱 | 本人 + 本组 supervisor | 管理员 |

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
- 备份：每日 `pg_dump` + restic 增量备份 `DATA_ROOT`（脚本在部署阶段提供）。

## 前端

Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router。
- `src/api/client.ts`：唯一的请求入口，处理 CSRF 与统一错误（`ApiError`）。
- `src/api/types.ts`：与 `api-contract.md` 一一对应的类型。
- `src/stores/auth.ts`：登录状态；路由守卫负责未登录跳转登录页、未改初始密码跳转改密页。
- 菜单按开发手册 §5，只显示已上线的模块；`meta.supervisor` 只控制界面显示，权限以后端为准。
