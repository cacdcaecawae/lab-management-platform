# Agent Note: 站内通知：右上角铃铛和通知列表

Status: proposed

## Problem

现在平台的通知有两种：

- **邮件**：要运维配好学校邮箱才有，而且很多同学不常看学校邮箱。
- **工作台卡片**：只显示"当前还要处理的事"，处理完就消失，没有"发生过什么"的记录。

结果是采购被退回、设备被登记异常、成为行动项负责人这些事，没配邮件的组完全收不到通知，配了邮件也容易漏看。

## Proposal

**模型**（放在 `core`，因为每个业务模块都会用到；`core` 不引用业务模块）：

```
Notification(recipient → User, title ≤200, body Text, link ≤300（前端路径，如 /purchases/12）,
             created_at, read_at null)
索引：(recipient, read_at, -created_at)
```

**写入**：`core.notifications.notify(users, title, link, body="")`，一次 `bulk_create`，跳过停用账号，在事务提交后执行（`transaction.on_commit`），回滚的操作不会留下通知。首批接入：

- 采购：现在发邮件的地方（提交待初审、待终审、通过、退回、已到货）同时调用 `notify`；
- 设备：异常登记通知本组管理员；
- 组会：被设为行动项负责人（新建或换人时）；
- 周报：被要求补充、已阅；
- 试件：管理员代为登记归还时通知借用人。

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
- **清理**：已读超过 180 天的通知，由[每日提醒邮件](2026-11-18-scheduled-reminder-mail.md)的命令顺带删除；那篇还没做时，就加一个独立命令 `purge_notifications`。

## Alternatives considered

- **WebSocket 或服务器推送，做到实时**：体验更好。但要引入 Channels 和 Redis，部署多两个组件；通知不是秒级的事，60 秒轮询足够。
- **每个模块各建自己的通知表**：不用动 `core`。但前端要轮询好几个接口，未读数也没法合并。
- **只做邮件，强制每个组配好 SMTP**：零开发。但做不到，而且很多同学不看邮箱。

## Acceptance criteria

- 后端测试：
  - 每个接入点触发后，收件人收到一条，带正确的 `link`；
  - 事务回滚时没有通知；
  - 只能看到和标记自己的通知；
  - 未读数正确；
  - 停用账号不收。
- 前端测试：铃铛显示未读数；点一条后调用"标记已读"并跳转。
- 浏览器：学生提交采购，管理员铃铛出现 1；管理员退回，学生铃铛出现 1，点击后进入采购详情、角标消失。按 verify-lab 留证据，新增功能文件 `features/notifications.md`。
- 模块依赖检查通过：业务模块引用 `core.notifications`，`core` 不引用业务模块。

## Risks

- 轮询带来的请求量：70 人同时在线，约每秒 1 个很轻的请求，可以忽略。浏览器标签页不可见时停止轮询。
- 通知里的标题会带上单号、设备编号等信息；只发给本来就有权限看到这些记录的人。新增接入点时要逐个核对收件人的权限。
