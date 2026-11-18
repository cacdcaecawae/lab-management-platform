---
name: verify-lab
description: 在真实浏览器里驱动课题组管理平台（Vue 前端 + Django 后端），验证用户可见的行为。启动一套与日常开发隔离的实例（数据库 lab_verify、后端 :8100、前端 :5273、无头 Chrome :9222），按 features/ 里的功能清单操作页面，留下截图和数据库证据，最后清理。改了页面、接口行为或权限之后，或者需要证明某个流程在浏览器里真的走得通时使用。
---

# 在浏览器里验证课题组管理平台

所有命令都在仓库根目录 `lab-management-platform/` 下用 Bash（Git Bash）运行。浏览器操作用 chrome-devtools MCP 工具（`new_page`、`take_snapshot`、`click`、`fill`、`press_key`、`upload_file`、`wait_for`、`take_screenshot`、`evaluate_script`），它固定连接 `127.0.0.1:9222`。

## 隔离

| 项 | 验证实例 | 日常开发 |
|---|---|---|
| 数据库 | `lab_verify`，每次启动重建 | `lab` |
| 后端 | `127.0.0.1:8100` | `:8000` |
| 前端 | `http://127.0.0.1:5273` | `:5173` |
| 浏览器 | 无头 Chrome `:9222`，临时配置目录 | — |
| 上传文件 | `backend/var/verify/data` | `backend/var/data` |

- PostgreSQL 与日常开发共用同一个容器（`docker compose up -d db`），只多建一个库，不启停容器，不影响其他会话的 `test_lab_*` 测试库。
- 同一时间只能有一个验证实例：任一端口被占用时 launch.sh 拒绝启动。不是本次 launch.sh 启动的实例，不要驱动，也不要清理。

## 启动

```bash
bash .claude/skills/verify-lab/scripts/launch.sh
```

依次重建 `lab_verify`、迁移、写入种子数据，再启动 Django、Vite、无头 Chrome，等到三者都能响应才结束，大约 10 秒。最后一行是 `READY` 才算成功；任何一步失败都会以非 0 退出，这时先运行 cleanup.sh 再重试。

种子数据，密码都是 `Verify-2026!`：

| 账号 | 姓名 | 角色 | 课题组 |
|---|---|---|---|
| `s_a` | 学生甲 | 学生 | 验证课题组 |
| `s_b` | 学生乙 | 学生 | 验证课题组 |
| `s_new` | 新同学 | 学生，首次登录必须改密码 | 验证课题组 |
| `mgr` | 管理员甲 | 管理员 | 验证课题组 |
| `adv` | 导师甲 | 导师 | 验证课题组 |
| `x_mgr` | 外组管理员 | 管理员 | 外组 |
| `ops` | 运维 | 运维账号（超级用户），只能用"系统管理" | 无 |

- 项目：`导波螺栓松动`，属于验证课题组，负责人 s_a，成员 s_a、s_b。没有任何数据集、实验记录、周报、设备、耗材，需要时在页面上创建。
- 上传用的样例文件：`backend/var/verify/files/wave_001.csv`、`wave_002.csv`，设备使用登记用的照片 `photo.png`（1×1 PNG），采购和报销附件用的 `quote.pdf`（一页空白 PDF），以及组会附件用的 `slides.pptx`（内容不是真正的 PPT，服务器不解析），SHA256 在同目录的 `SHA256SUMS`。`upload_file` 需要 Windows 绝对路径，launch.sh 结尾会打印这个目录。
- 登录按账号限速：同一账号每分钟最多 5 次登录请求，超过返回 429。不要反复登录同一个账号。

## 体检（只读）

```bash
bash .claude/skills/verify-lab/scripts/doctor.sh
```

检查三个端口是否由 launch.sh 启动的进程占用、前端代理到后端是否通、`lab_verify` 里是否有 7 个种子账号，并打印当前代码版本和未提交文件数。页面表现异常时先跑它；退出码不是 0 就不要继续驱动。

## 驱动

1. 打开 [`features/README.md`](features/README.md)，找到要验证的功能，按对应文件的 "Driving it with chrome-devtools MCP" 一节操作。
2. 每个账号用一个独立上下文：`new_page` 打开 `http://127.0.0.1:5273/login`，并传 `isolatedContext: "<账号>"`，这样多个账号可以同时登录、互不覆盖会话。
3. 每次操作前先 `take_snapshot` 拿 uid。uid 每次快照都会变，只用最新的。按无障碍名称（按钮文字、输入框标签、菜单项）定位，不按坐标。

Element Plus 页面的几个特点：

- 下拉框（快照里的 `combobox`）展开后，选项不会出现在快照里。点击下拉框后用 `press_key` 按 `ArrowDown` 移到下一项、按 `Enter` 选中；再看快照里下拉框旁显示的文字，确认选对了。
- "上传文件"按钮背后是隐藏的文件输入框，直接对这个按钮用 `upload_file`。
- 成功或失败的浮动提示几秒后就会消失，要用 `wait_for` 等提示文字出现，不要事后再截图找。
- 退回原因、确认框等是页面内的对话框，不是浏览器原生弹窗，在快照里找对话框中的输入框和按钮。

## 证据

证据放在 `backend/var/verify-evidence/<日期>-<功能文件名>/`。这个目录被 git 忽略，cleanup.sh 也不会删除它。每个功能至少要有：

- 操作后的截图（`take_screenshot`，`filePath` 指向证据目录）和无障碍快照（`take_snapshot` 的 `filePath`）。
- 副作用的第二视角：用 query.sh 从数据库读回，或者查看磁盘上的文件。

```bash
bash .claude/skills/verify-lab/scripts/query.sh 'from datasets.models import DataFile; print(list(DataFile.objects.values_list("name", "sha256")))'
```

标准：

- 走用户的真实路径（菜单、按钮、表单）。不调测试专用接口，不直接改数据库造状态；query.sh 只用来读。`evaluate_script` 里用 `fetch` 只限于读当前登录用户本来就能访问的地址，例如下载链接。
- 记录操作和操作后的状态，不只是最后一屏。
- 失败就报告失败。缺前置条件时写清缺什么，不改步骤去凑通过。
- 报告时写明用了哪个功能文件、验证了哪些子功能、哪些没有验证。

## 清理

```bash
bash .claude/skills/verify-lab/scripts/cleanup.sh
```

按 launch.sh 记录的 PID 停掉进程树（不按进程名杀），删除 `lab_verify` 和 `backend/var/verify/`，保留证据目录。驱动失败或中途放弃时也要运行。

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/launch.sh` | 启动 |
| `scripts/doctor.sh` | 只读体检 |
| `scripts/query.sh '<python>'` | 在 Django shell 里只读查询 `lab_verify` |
| `scripts/cleanup.sh` | 清理 |
| `scripts/seed.py` | 种子数据，由 launch.sh 调用；只允许在 `lab_verify` 上运行 |
| `scripts/env.sh` | 端口、路径等公共设置，被其他脚本 source |

依赖：Git Bash；Python `/d/anaconda/conda/envs/lab-platform/python.exe`（可用环境变量 `PYTHON` 覆盖）；`frontend/` 已执行过 `npm ci`；Chrome（可用 `CHROME_W` 覆盖其 Windows 路径）；PowerShell（launch.sh 用它在后台启动进程）。

## 维护功能清单

`features/` 是浏览器验证的维护来源。页面文字、路由或流程变了，在同一次改动里更新对应的功能文件；新增用户可见的功能时，加一个文件并在 `features/README.md` 登记。某个功能实际走通后，在 README 的表里写上日期和代码版本。
