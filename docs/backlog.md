# 待开发清单与开发规则

2026-11-18 整理。每一项都有一篇方案笔记（`.agents/notes/proposed/…`），写了问题、设计、备选方案、验收标准和风险。用户同意由其他 AI 代理按这些方案实现。方案里写着"需要用户确认"的点，先问用户再动手。

## 清单

建议按顺序做。"大小"是粗估：S 半天以内，M 一两天，L 三天以上。"模型检查"指改动是否会碰到设备并发模型检查的覆盖文件（见下文规则 6）。

| # | 内容 | 方案笔记 | 大小 | 依赖 | 模型检查 |
|---|---|---|---|---|---|
| 1 | 设备并发模型检查只看 settings.py 的数据库设置 | [process/…-tla-check-database-settings-only](../.agents/notes/proposed/process/2026-11-18-tla-check-database-settings-only.md) | S | — | 改检查脚本本身 |
| 2 | 前端其余页面迁入 `src/modules/`（迁移完成，浏览器待验收） | [architecture/…-frontend-modules-rest](../.agents/notes/implemented/architecture/2026-11-18-frontend-modules-rest.md) | M | 没有其他未合并的前端 PR | 是（设备表单 import 变更） |
| 3 | 补走浏览器验证欠账 | [testing/…-browser-verification-backlog](../.agents/notes/proposed/testing/2026-11-18-browser-verification-backlog.md) | M（可拆开做） | 最好在 2 之后 | 否 |
| 4 | 工作台提醒：我借的试件、逾期未还、校准到期 | [feature/…-workbench-reminders](../.agents/notes/proposed/feature/2026-11-18-workbench-reminders.md) | S | — | 是（设备列表筛选） |
| 5 | 每日提醒邮件 | [feature/…-scheduled-reminder-mail](../.agents/notes/proposed/feature/2026-11-18-scheduled-reminder-mail.md) | M | 4（共用 `specimens/queries.py`） | 否 |
| 6 | 站内通知（铃铛） | [feature/…-notification-center](../.agents/notes/proposed/feature/2026-11-18-notification-center.md) | M | — | 设备异常的接入点在 `equipment/views.py`：是 |
| 7 | 项目任务看板与里程碑 | [feature/…-project-tasks-milestones](../.agents/notes/proposed/feature/2026-11-18-project-tasks-milestones.md) | L | 最好在 2 之后 | 否 |
| 8 | 每月自动恢复演练 | [process/…-restore-drill](../.agents/notes/proposed/process/2026-11-18-restore-drill.md) | M | — | 否 |
| 9 | 设备使用统计与导出 | [feature/…-equipment-usage-stats](../.agents/notes/proposed/feature/2026-11-18-equipment-usage-stats.md) | M | — | 否（视图放在新文件） |
| 10 | 存储用量统计 | [feature/…-storage-usage](../.agents/notes/proposed/feature/2026-11-18-storage-usage.md) | M | — | 否 |
| 11 | 登录记录 | [feature/…-login-records](../.agents/notes/proposed/feature/2026-11-18-login-records.md) | S | — | 否 |
| 12 | 成果统计 | [feature/…-achievement-stats](../.agents/notes/proposed/feature/2026-11-18-achievement-stats.md) | S | — | 否 |
| 13 | 全站搜索 | [feature/…-global-search](../.agents/notes/proposed/feature/2026-11-18-global-search.md) | M | 最好在 2 之后 | 否 |
| 14 | 耗材批次与有效期 | [feature/…-consumable-batches](../.agents/notes/proposed/feature/2026-11-18-consumable-batches.md) | L | 需要用户确认哪些耗材按批次管 | 否 |
| 15 | 设备与试件二维码标签 | [feature/…-qr-labels](../.agents/notes/proposed/feature/2026-11-18-qr-labels.md) | S | 正式域名定下来之后再大量打印 | 否 |
| 16 | 正式域名的 HTTPS | [process/…-https](../.agents/notes/proposed/process/2026-11-18-https.md) | M | 用户提供域名并完成 ICP 备案 | 否 |

会议明确暂缓、不要做的：AI 额度与 Magpie 对接、培训授权与毕业交接、分片上传与断点续传、在服务器上运行 MATLAB/Python、SOP 学习考核、图表证据卡、对接学校财务系统（见开发手册第 1 节和 `docs/development-plan.md`）。

## 开发规则

先读 `AGENTS.md`、`docs/architecture.md`（尤其是模块分层表和前端模块规则），以及要做的那篇方案笔记。

1. **一项一个分支、一个 PR**：分支名 `feat/<短名>` 或 `test/<短名>`，从最新的 `main` 拉出。不要直接推送 `main`，不要 `push --force`、`reset --hard`、`clean -fd`。提交只 `git add` 具体文件，不要 `git add -A`：别的会话可能同时在改。
2. **方案笔记跟着实现走**：动手时如果发现方案有不合理的地方，先改笔记，在 PR 里说明。做完后在同一个 PR 里把笔记从 `proposed/` 移到 `implemented/`，按模板把 Proposal 改写成 Decision、把验收结果写进 Consequences，写实际跑过的数字，没验证的如实写"未验证"。写完运行三个笔记校验脚本（见 AGENTS.md）。
3. **模块边界**：后端只能引用分层表允许的模块；别的模块只能引用对方的 `models`、`serializers`、`mixins`、`versions.py`、`queries.py`。跨模块汇总放在 `workbench`。新增模块或依赖时，同时改 `scripts/check_module_deps.py` 和 `docs/architecture.md`。前端新页面放在 `src/modules/<模块>/`；页面只能引用别的模块的 `api`；布局、公共组件不能引用 `src/modules/`。
4. **权限和隔离要有测试**：每个新接口都要测"学生看不到别人的个人数据（404）""外组 404""角色不对 403"。权限只在后端判断，前端隐藏按钮只是界面上的处理。
5. **完整检查**：`DB_TEST_NAME=<自己的库名> PYTHON=<python> bash scripts/check.sh` 全部通过，PR 上的 GitHub CI 也要通过。改了数据模型，`makemigrations --check` 要干净，迁移文件随提交一起。
6. **设备并发模型检查**：改了 `backend/equipment/` 的 `views.py`、`serializers.py`、`models.py`，`backend/config/settings.py`（第 1 项完成前是任何改动，之后只算数据库设置），或 `EquipmentFormDialog.vue` 后，运行 `bash .claude/skills/verify-equipment-tla/scripts/check.sh`：
   - 退出码 2 时，按 SKILL.md 核对改动是否影响模型；不影响的，在单独一条提交里更新 `SYNC`；
   - 退出码 1 时，按 SKILL.md 判断是代码缺陷还是模型错误，不要为了通过去改模型。
7. **浏览器验证**：改了页面、接口行为或权限，按 `.claude/skills/verify-lab/SKILL.md` 在隔离实例里走一遍，证据放在 `backend/var/verify-evidence/`（不提交），同时更新或新增 `features/` 下的功能文件和 README 表格。没在浏览器里看过的，不要写成"已验证"。
8. **文档**：接口变了改 `docs/api-contract.md`；权限或分层变了改 `docs/architecture.md`；部署和运维变了改 README；完成一项在 `docs/development-plan.md` 加一节（内容、验证范围、未验证）。
9. **不要写进仓库的东西**：`.env`、密码、授权码、真实人名（开发手册和会议纪要里的人名，在代码、笔记、测试数据里一律用角色或"学生甲"这类称呼）、学校和个人的邮箱、实验数据。提交作者使用仓库配置的 GitHub 匿名邮箱。
10. **依赖**：能用标准库、Django、Element Plus 或已有依赖解决的，不新增依赖（见[依赖最少](../.agents/notes/implemented/process/2026-11-16-minimal-dependencies.md)）。确实要加时，在方案笔记里写明理由；前端的 `package-lock.json` 要在 Linux 容器里重新生成，Windows 上的 npm 会漏掉可选依赖。

## 已知的坑

- **Windows 本机**：
  - Python 是 `/d/anaconda/conda/envs/lab-platform/python.exe`；
  - Git Bash 里调用 `docker` 时，带容器路径的参数（如 `-v x:/data`）要加 `MSYS_NO_PATHCONV=1`；
  - 用 Python 在 Windows 上写文本文件会写出 CRLF，要用 `write_bytes` 或事后转回 LF。
- **路由**：JS 字符串里的正则要写两个反斜杠，`'items/:id(\\d+)'`。只写一个时，`\d` 就是字母 d；点链接能进去，直接打开地址却是"页面不存在"。`router/router.test.ts` 会检查所有详情地址。
- **浏览器自动化**：Element Plus 的 switch、checkbox 把真正的 input 藏起来了，chrome-devtools 的 `click`、`fill` 会超时。绕过办法见 `.claude/skills/verify-lab/features/specimens.md` 的 Gotchas。登录有限速：同一账号每分钟最多 5 次。
- **N+1 测试**：列表接口多预取一个关联时，查询次数断言的上限要相应加 1；上限必须是常数，不能随行数变化。
