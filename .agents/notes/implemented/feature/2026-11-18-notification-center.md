# Agent Note: 站内通知：右上角铃铛和通知列表

Status: implemented

## Problem

现在平台的通知有两种：

- **邮件**：要运维配好学校邮箱才有，而且很多同学不常看学校邮箱。
- **工作台卡片**：只显示"当前还要处理的事"，处理完就消失，没有"发生过什么"的记录。

结果是采购被退回、设备被登记异常、成为行动项负责人这些事，没配邮件的组完全收不到通知，配了邮件也容易漏看。

## Decision

**模型**（放在 `core`，因为每个业务模块都会用到；`core` 不引用业务模块）：

```
Notification(recipient → User, group → ResearchGroup, audience_role, title ≤200, body Text, link ≤300（前端路径，如 /purchases/12）,
             created_at, read_at null)
索引：(recipient, group, -created_at, -id)、(recipient, group, read_at)、(read_at)
```

**写入**：`core.notifications.notify(group_id, title, link, *, recipient_ids=None, role="", exclude_ids=(), body="")`，一次 `bulk_create`，跳过停用账号，在业务数据库事务内写入（邮件仍用 on_commit），回滚的操作不会留下通知。读接口按收件人 + 当前组 + 必要角色过滤，组/角色变动后不再显示不符合权限的旧通知。首批接入：

- 采购：现在发邮件的地方（提交待初审、待终审、通过、退回、已到货）同时调用 `notify`；
- 设备：异常登记通知本组管理员；
- 组会：被设为行动项负责人（新建或换人时）；
- 周报：被要求补充、已阅；
- 试件：管理员代为登记归还时通知借用人。
- 实验记录、数据处理记录：被导师或管理员退回时通知本人，正文是记录名称和退回原因（2026-11-22 补上，首版验收时发现缺这一项）。

**接口**：`/api/notifications/`，只返回自己的通知，放在新的 `notifications` 路由文件里，由 `core` 提供视图：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/notifications/?unread=1` | 分页，最新在前 |
| GET | `/api/notifications/unread-count/` | `{count}` |
| POST | `/api/notifications/{id}/read/` | 标记已读；别人的通知 404 |
| POST | `/api/notifications/read-all/` | 全部标记已读 |

**前端**：

- `layouts/AppLayout.vue` 右上角加铃铛按钮，带未读数角标，`aria-label` 为"通知，N 条未读"。
- 页面可见时每 60 秒取一次未读数，路由切换时也取。
- 点开显示最近 10 条，点某条就标记已读并跳转；底部"查看全部"进入 `/notifications` 列表页。
- 接口文件 `src/api/notifications.ts` 属于公共部分：布局是公共代码，不能引用 `src/modules/`。
- **清理**：已读超过 180 天的通知由独立命令 `purge_notifications` 清理，邮件开关不影响；仅提供命令，不启用调度。

## Alternatives considered

- **WebSocket 或服务器推送，做到实时**：体验更好。但要引入 Channels 和 Redis，部署多两个组件；通知不是秒级的事，60 秒轮询足够。
- **每个模块各建自己的通知表**：不用动 `core`。但前端要轮询好几个接口，未读数也没法合并。
- **只做邮件，强制每个组配好 SMTP**：零开发。但做不到，而且很多同学不看邮箱。

## Consequences

- 通知与业务更新同库事务提交；邮件仍在事务提交之后尝试发送。数据库写入失败会回滚业务，避免产生不一致事件。
- PostgreSQL 回归覆盖五类接入、事务回滚、账号/组/角色隔离、已读及清理；Vue 回归覆盖角标、隐藏时停止轮询、读后跳转、仅未读与全部已读。
- 新增浏览器验收清单。真实浏览器逐角色验证尚未完成，不部署清理计划任务。
- 隔离 PostgreSQL 17 全量后端 401 项、前端 77 项、迁移检查、类型和生产构建通过。设备 TLC 10 个场景符合预期，退出码 2 报告同事务新增通知的代码漂移；设备/预约状态与原业务锁顺序未改，SYNC 留给相关草稿集成后处理。

## Risks

- 轮询带来的请求量：70 人同时在线，约每秒 1 个很轻的请求，可以忽略。浏览器标签页不可见时停止轮询。
- 标题为通用动作，不含业务正文；链接目标仍使用原权限，不因通知开放访问。新增接入点要逐个核对收件人权限。
