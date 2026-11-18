# Agent Note: 用 verify-lab 技能在隔离实例里驱动浏览器验证

Status: implemented

## 问题

后端 pytest 和前端 vitest 覆盖接口和组件，但真实浏览器里的流程一直靠手工联调。`docs/development-plan.md` 列着一批"未在浏览器验证"的功能（导师角色、退回、修改历史抽屉等）。AI 改完页面后，没有固定的办法证明页面真的能用，也没有地方留证据。

## 决策

- 项目内技能 `.claude/skills/verify-lab/`：`launch.sh` 启动一套与日常开发隔离的实例，`doctor.sh` 只读体检，`query.sh` 只读查询，`cleanup.sh` 清理。浏览器用 chrome-devtools MCP 驱动。
- 隔离方式：数据库 `lab_verify`（每次启动删除重建、迁移、写入种子数据），后端 `:8100`，前端 `:5273`，无头 Chrome `:9222`，上传目录 `backend/var/verify/data`。PostgreSQL 容器与日常开发共用，不启停。端口被占用时拒绝启动。
- 种子数据：同组学生甲/乙、首次登录须改密的新同学、管理员、导师，外组管理员，以及一个项目；密码统一。`seed.py` 检查数据库名，只能写 `lab_verify`。
- 证据放在 `backend/var/verify-evidence/<日期>-<功能>/`（git 忽略，清理时保留）：截图、无障碍快照，再加数据库或磁盘上的第二视角。
- `features/` 是浏览器验证的维护来源，每个用户可见功能一个文件，写明入口、元素名称、步骤和可观察结果；页面变了在同一次改动里更新。

### 后台进程怎么启动

`launch.sh` 通过 PowerShell `Start-Process`（ShellExecute）启动 Django、Vite 和 Chrome，并记录 PID；清理时按 PID 结束进程树，不按进程名结束。

## 曾考虑的替代方案

- **Playwright 端到端测试**：写成代码，可以重复运行，也能接进 CI；但要新增依赖并下载浏览器，而仓库目前没有 CI。先用这个技能补上手工联调的缺口，等接 CI 时再评估。
- **直接驱动日常开发实例（库 `lab`，:8000 / :5173）**：不用另起服务；但验证会往开发数据里写东西，多个会话同时驱动会互相干扰。
- **在 Bash 里用 `&` / `nohup` 启动后台进程**：写法最简单；但实测在 Windows 上，子进程会继承调用方的输出管道，调用 `launch.sh` 的命令（包括 AI 的 Bash 工具）永远不返回。

## 后果

- 收益：一条命令约 10 秒起一套干净实例；AI 改完页面可以按功能文件在浏览器里走一遍并留下证据。
- 代价与已知上限：
  - 只在 Windows + Git Bash + PowerShell 上跑过；路径转换用 `pwd -W`，因为 PATH 里 conda 自带的 `cygpath` 会把 `/f/` 转错。
  - chrome-devtools MCP 固定连接 `:9222`，同一时间只能有一个验证实例。
  - 这不是 CI，靠 AI 或人按步骤执行。需要自动回归时，回到上面的 Playwright 方案。
  - 5 个功能文件里只有 `datasets.md` 实际走通过，其余 4 个是按页面代码写的，第一次走时可能需要修正。

## Verification

2026-11-17 在代码 `d6405d9` 上按 `features/datasets.md` 走通：新建数据集、上传、同名拒绝；本地文件、页面显示、浏览器下载和数据库记录的 SHA256 一致；学生乙打开学生甲的数据集看到"记录不存在或无权查看"，接口和下载都返回 404（对应 [数据范围与 404](../architecture/2026-11-16-access-scope-404.md)）。数据集版本码的行为见 [数据集版本](../feature/2026-11-17-dataset-versions.md)。清理后端口释放、`lab_verify` 删除、证据保留。
