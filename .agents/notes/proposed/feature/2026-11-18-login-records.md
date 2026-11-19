# Agent Note: 登录记录

Status: proposed

## Problem

平台存的是科研数据和经费单据，账号一旦被盗用，现在没有任何痕迹可查：

- `User.last_login` 只记最近一次成功登录；
- 登录失败只用于限速（`LoginRateThrottle`），过后就没了；
- 有人反复试某个账号的密码，或者某个账号突然在陌生地址登录，运维都看不到。

## Proposal

**模型**（`accounts` app）：

```
LoginEvent(user → User null SET_NULL, username ≤150（尝试登录时填的，原样记录）, ip ≤45,
           user_agent ≤200, success Bool, at DateTime, 索引 (at), (username, at))
```

**写入**：`accounts/views.py` 的 `LoginView` 在认证成功和失败时各写一条。被限速挡下的请求（429）也写一条，`success=False`，`user_agent` 前加"[限速]"。

- 来源地址的取法与登录限速相同：取 Nginx 追加在 `X-Forwarded-For` 末尾的一段，与 `NUM_PROXIES` 一致；复用限速类里已有的取法，不要另写一套。
- 写入失败（例如数据库只读）不能影响登录：写在 try 里，失败只记日志。

**保留**：只保留 180 天。每次写入时，以 1% 的概率顺带删除 180 天前的记录；如果[每日提醒](../../implemented/feature/2026-11-18-scheduled-reminder-mail.md)的命令已经存在，就放进那个命令里。

**接口**：`GET /api/system/logins/?username=&success=&from=&to=`，只给运维，分页，最新在前。

**前端**："系统管理"新增"登录记录"标签页：表格（时间、登录名、对应成员、结果、来源地址、浏览器）、筛选，以及"近 24 小时失败最多的账号"前 5 名。

## Alternatives considered

- **用 django-axes 之类的现成包**：自带锁定账号等功能。但要新增依赖，而且会和现有的"账号 + 地址"限速重复；我们只需要记录和查看。
- **写日志文件，不写数据库**：没有表。但运维要登服务器翻日志，网页上看不到，筛选也不方便。
- **也给每个成员看自己的登录记录**：方便本人发现异常。可以作为第二步：数据结构不用变，只加一个接口。

## Acceptance criteria

- 后端测试：
  - 成功、密码错误、不存在的账号、被限速，各写一条，字段正确；
  - 记录写入失败不影响登录；
  - 只有运维能查；
  - 筛选正确；
  - 清理逻辑删除 180 天前的记录（固定时间测试）。
- 浏览器：用错误密码登录两次、正确登录一次，运维的"登录记录"按时间列出 3 条。更新 `features/system.md`。
- README 和 `docs/architecture.md` 写明会记录登录的地址，保留 180 天。

## Risks

- 来源地址属于个人信息：只有运维能看，到期删除；不在页面上做 IP 归属地查询，不把数据发给外部服务。
- 登录接口每次多一次数据库写入，影响可以忽略。
