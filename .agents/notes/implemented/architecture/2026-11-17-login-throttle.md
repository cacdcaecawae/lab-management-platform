# Agent Note: 登录按账号限速，Nginx 按 IP 兜底（原 D26，取代 D23）

Status: implemented

## 问题

登录接口需要防止暴力猜密码（见 [认证](./2026-11-16-session-csrf-auth.md)）。生产环境由多个 Gunicorn 进程处理请求；全组可能共用一个校园网出口 IP；学号（登录名）容易猜到。

## 决策

- Django 按账号限速：`LoginRateThrottle`（`backend/accounts/views.py`）对每个用户名每分钟最多 5 次，超出返回 429，不锁账号。后来改为按"账号 + 来源地址"计数，见 [登录限速按账号 + 来源地址](./2026-11-17-login-throttle-per-account-and-ip.md)。
- 计数存在数据库缓存（`config/settings.py` 的 `CACHES` 使用 `DatabaseCache`），所有 Gunicorn 进程共享，不引入 Redis（见 [技术栈](./2026-11-16-modular-monolith-stack.md)）。
- Nginx 对 `/api/auth/login/` 和 `/admin/login/` 按 IP 兜底：每分钟 60 次，突发 20 次（`infra/nginx.conf`）。开发环境没有 Nginx 这一层。

## 曾考虑的替代方案

- **只在 Nginx 按 IP 限速，每分钟 10 次（原 D23）**：不改业务代码，多个进程自然共享计数；但全组可能共用一个出口 IP，一个人输错几次就会让全组都登不上。已被本方案取代。
- **失败次数过多就锁定账号**：能挡住长时间猜测；但学号容易猜，别人可以故意把你的账号锁住。

## 后果

- 收益：一个人猜密码不影响同 IP 的其他人；进程之间共享计数。
- 代价：每次登录多一次数据库缓存读写；Nginx 那一层只能在生产式容器中验证。
