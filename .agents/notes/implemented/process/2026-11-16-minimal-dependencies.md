# Agent Note: 依赖从简：不用 django-environ 和 axios，TypeScript 锁定 5.9（原 D14、D15、D16）

Status: implemented

## 问题

每多一个依赖，就多一份升级和兼容性负担。第一期的配置读取和 HTTP 请求都很简单；前端类型检查依赖 vue-tsc 与 TypeScript 版本相互配合。

## 决策

- 后端 `config/settings.py` 自己读取 `.env`，不用 django-environ。
- 前端用 `fetch` 封装请求，唯一入口是 `frontend/src/api/client.ts`，负责 CSRF 和统一错误；不用 axios。
- TypeScript 锁定 5.9.x。

## 曾考虑的替代方案

- **django-environ**：功能完整，但这里几行代码就够，少一个依赖。
- **axios**：拦截器等功能方便，但需求简单，`fetch` 足够。
- **TypeScript 7.x（原生编译器）**：编译更快，但 vue-tsc 对它的兼容性没有验证。

## 后果

- 收益：少两个运行时依赖，类型检查结果稳定。
- 代价与重访信号：vue-tsc 确认支持 TypeScript 7 后，再评估升级。
