# Agent Note: 认证用 Django Session + CSRF，登录接口也校验 CSRF（原 D4）

Status: implemented

## 问题

平台需要登录认证。前后端同源：开发时由 Vite 代理 `/api`、`/admin`，生产时由 Nginx 转发（见 [技术栈](./2026-11-16-modular-monolith-stack.md)）。

## 决策

- 使用 Django Session（HttpOnly Cookie）+ CSRF。SPA 先请求 `GET /api/auth/csrf/` 拿到 `csrftoken` Cookie，之后所有非 GET 请求带 `X-CSRFToken` 头。
- 登录接口也校验 CSRF，防止登录 CSRF。DRF 不对匿名请求检查 CSRF，所以 `LoginView` 显式加了 `csrf_protect`（`backend/accounts/views.py`）。
- 密码哈希、会话、CSRF 都用 Django 自带实现。

## 曾考虑的替代方案

- **JWT**：适合跨域和多客户端；但这里前后端同源，框架自带的 Session 实现更安全，也不必自己处理令牌存储和吊销。

## 后果

- 收益：认证相关代码几乎全部来自框架。
- 代价：前端必须与 API 同源部署。
