# Agent Note: 技术栈：模块化单体，不引入异步任务队列（原 D1、D13）

Status: implemented

## 问题

平台由主代理和若干并行子代理开发，部署在校内单机。需要一套自带认证、后台和迁移的成熟技术栈，并尽量减少要运维的组件。

## 决策

- 前端 Vue 3 + TypeScript + Element Plus + Pinia；后端 Django 5.2 LTS + DRF；数据库 PostgreSQL；用 Docker Compose 部署。
- 结构是模块化单体：一个 Django 项目（`core`、`accounts`、`projects`、`datasets`、`research`、`reports`）+ 一个 Vue SPA + 一个 PostgreSQL。
- 不引入 Celery / Redis。邮件、备份等定时工作在需要时用 cron 调用 Django 管理命令。

## 曾考虑的替代方案

- **Go 后端 / 微服务**：已确定不用，不再讨论。原决策表只记录了结论，没有记录当时的比较理由。
- **Celery + Redis**：第一期没有异步任务需求，而且会多出两个要运维的组件。

## 后果

- 收益：运行组件只有 Nginx、Django（Gunicorn）、PostgreSQL。
- 代价与重访信号：出现耗时的后台任务时（例如服务器端运行处理脚本，目前在 `docs/development-plan.md` 的"不做"清单里），重新评估任务队列。
