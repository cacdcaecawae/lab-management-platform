# 代理任务分配与状态

## 工作区

| 代理 | 分支 | Worktree（仓库外） | 测试库名 `DB_TEST_NAME` | 可修改范围 |
|---|---|---|---|---|
| 主代理 | `main` | `lab-management-platform/` | `test_lab_main` | 公共文件、集成 |
| A 成员与项目 | `feat/projects` | `../lab-worktrees/projects` | `test_lab_projects` | `backend/projects/**`（除 models.py 外的新文件可自由建）、`backend/accounts/member_urls.py`、`backend/accounts/member_views.py`、`backend/accounts/member_serializers.py`、`backend/accounts/management/**`、`backend/accounts/tests/test_members*.py` |
| B 实验与处理 | `feat/research` | `../lab-worktrees/research` | `test_lab_research` | `backend/research/**` |
| C 数据与文件 | `feat/datasets` | `../lab-worktrees/datasets` | `test_lab_datasets` | `backend/datasets/**` |
| D 周报与反馈 | `feat/weekly-reports` | `../lab-worktrees/weekly-reports` | `test_lab_reports` | `backend/reports/**` |
| E 前端 | `feat/frontend` | `../lab-worktrees/frontend` | — | `frontend/src/**`（`api/client.ts` 除外）、`frontend/src/api/types.ts` 可增加类型 |
| 审查 | — | 只读 | — | 不修改代码，只出问题清单 |

## 所有子代理共同规则

1. 只在自己的 worktree 和可修改范围内工作。公共文件（`config/*`、`core/*`、`conftest.py`、`accounts/models.py`、`accounts/views.py`、`docs/*`、`frontend/src/api/client.ts`、`package.json`、`requirements*.txt`）不改；需要改时写进交付说明。
2. 改本 app 的 `models.py` 需在交付说明中说明原因，并只生成本 app 的新迁移。
3. 严格按 `docs/api-contract.md` 实现；契约有歧义时按最保守（权限更严）的理解实现并在说明里列出。
4. 每个视图的 `get_queryset()` 必须使用 `core.permissions.scope_private` / `scope_group`。
5. 测试使用 `backend/conftest.py` 的夹具；每个资源都要有"学生 A 用 B 的 id 读/写/下载 → 404""外组管理员 → 404""本组管理员/导师可读"的测试。
6. Python：`/d/anaconda/conda/envs/lab-platform/python.exe`；运行测试前 `export DB_TEST_NAME=<自己的库名>`，在 `backend/` 下执行 `python -m pytest`。PostgreSQL 已在 `127.0.0.1:5432` 运行，不要启停容器。
7. 提交：Conventional Commits，小步提交，只 `git add` 具体文件；不合并、不推送、不 rebase main、不 `reset --hard`、不 `clean`。
8. 交付说明：变更摘要、提交列表、实际执行的测试命令与结果、已知问题、对公共代码/契约的修改请求。
9. 非平凡的技术决策按 `AGENTS.md` 在 `.agents/notes/` 写笔记（不属于公共文件，各写各的文件）：已落地的写 `implemented/`，需要主代理拍板的写 `proposed/`；交付说明里列出笔记路径。

## 状态

| 任务 | 状态 | 说明 |
|---|---|---|
| M0 基线 | 完成 | |
| D `feat/weekly-reports` | 已合并 | 35 个测试；提出 history reason 100 字限制 → 主代理改为 TextField |
| A `feat/projects` | 已合并 | 52 个测试；集成时修复：过滤参数影响详情、并发重名 500 |
| C `feat/datasets` | 已合并 | 63 个测试 |
| B `feat/research` | 已合并 | 59 个测试；集成时修复：过滤参数影响详情 |
| E `feat/frontend` | 已合并 | 36 个测试；集成时加入会话过期跳转 |
| 集成 `fix/phase1-integration` | 已合并 | 工作台接口、跨模块验收测试、浏览器联调、审查修复 |
| 审查 | 完成 | 高 1 / 中 4 / 低 8：H1、M1–M3、L1–L6 已修复并有回归测试；M4 文档化；L7、L8 及 select_for_update 的真实并发测试未做 |
