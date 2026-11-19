# Agent Note: 每日提醒邮件：试件逾期、校准到期、行动项到期、周报未交

Status: proposed

## Problem

工作台提醒要人主动打开才看得到。有几件事拖了会造成实际损失，需要主动推送：

- 试件借出逾期，下一个要用的人找不到；
- 设备校准过期还在用，数据不可信；
- 组会行动项到了截止日期没人记得；
- 周报到周五还没交。

现在平台只在审批、设备异常、每周财务提醒时发邮件。财务提醒用的是宿主机 cron 调用管理命令（`procurement/management/commands/send_finance_reminder.py`），应用里没有常驻调度进程（[模块化单体](../../implemented/architecture/2026-11-16-modular-monolith-stack.md)不引入 Celery）。

## Proposal

新增管理命令 `python manage.py send_due_reminders [--date YYYY-MM-DD] [--dry-run]`，放在 `workbench/management/commands/`（汇总层，可以引用各模块的 `queries.py`）。每天由 cron 运行一次，README 给出 `0 8 * * *` 的示例。

**规则**（`today` 为服务器本地日期，`--date` 可覆盖，便于测试）：

| 事项 | 收件人 | 什么时候发 |
|---|---|---|
| 试件逾期未还 | 借用人 | 到期日的第二天；之后每周一，直到归还 |
| 逾期未还汇总 | 本组管理员 | 每周一，列出全部逾期 |
| 设备校准 | 本组管理员 | `calibration_due` 等于今天 + 30、今天 + 7、今天 |
| 组会行动项 | 负责人 | 截止日期是明天；截止日期是昨天且仍未完成 |
| 周报未交 | 本周未交的学生 | 每周五（`reports.queries.missing_students`） |

- **每人每天只收一封**：把同一个人当天的所有事项合并成一封，标题为"[课题组管理平台] 今日提醒（N 项）"，正文按事项分段，每项附上页面链接。
- **链接**：用新设置 `SITE_URL`（环境变量，例如 `https://lab.example.edu.cn`）拼完整地址；没设时只写页面路径。
- **发送**：通过 `core.mail.send_quietly`。邮件没启用时只打印"邮件未启用，跳过"，退出码 0；`--dry-run` 只打印将要发给谁、什么内容。
- **收件人**：没有邮箱的用户跳过；停用账号不发。
- 不记录"已发送"：规则只按日期判断，每天运行一次不会重复。README 写明不要一天运行多次。

## Alternatives considered

- **记录每封已发邮件，按"上次发送时间"去重**：允许一天运行多次，也不怕 cron 重跑。但要新建一张表，还要处理清理；按日期判断的规则已经足够，cron 一天一次也是现在财务提醒的做法。
- **每个事项单独发邮件**：实现最直接。但一个管理员一天可能收到五六封，很快会被当成垃圾邮件忽略。
- **引入 Celery beat 做定时任务**：在应用里调度更灵活。但要多运维 Redis 和两个进程，而决策笔记已经否掉了这个方向。

## Acceptance criteria

- 测试用 locmem 邮件后端，固定 `--date`：
  - 每条规则各有一个"该发"和一个"不该发"的日期；
  - 同一个人多个事项只收到一封；
  - 外组的数据不会出现在别组的邮件里；
  - 邮件没启用时不发且退出码为 0；
  - 学生的邮件里没有试件的缺陷参数。
- `--dry-run` 的输出有测试。
- README 新增 cron 示例和 `SITE_URL` 说明；`infra/server.env.example` 加上 `SITE_URL`。
- 本机试用栈（Mailpit）实际运行一次，收件箱截图作为证据。

## Risks

- 服务器时区：命令按 Django 的 `TIME_ZONE`（Asia/Shanghai）取日期，cron 按宿主机时区触发；两者不一致时，可能在"错误的一天"运行。README 要写清楚宿主机时区设为 Asia/Shanghai。
- 学校 SMTP 可能限制每天的发信量。课题组 70 人以内，最坏一天几十封，通常在限额内；遇到限额时，`send_quietly` 只记录失败，不影响其他功能。
