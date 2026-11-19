# Agent Note: 补走浏览器验证欠账

Status: proposed

## Problem

AGENTS.md 要求改了页面、接口行为或权限后，按 verify-lab 在浏览器里走一遍。但 `docs/development-plan.md` 和 `.claude/skills/verify-lab/features/README.md` 里还留着一批"未在浏览器验证"或"未走过"的项目。它们有后端测试，但页面上的按钮、提示和权限显示从来没有人看过：

- `experiments.md`、`reports.md` 两个功能文件整份"未走过"。
- `login.md` 的 `login-logout`；`members.md` 的 `members-role-limit`、`members-reset`、`members-student-view`。
- 第一期：导师角色、退回、修改历史抽屉、处理记录完整提交、窄屏（手机宽度）。
- 第四期：编辑组会时保留完成状态、删除组会、替换论文全文、按成员和标签筛选、过期行动项标红、手机宽度。
- 试样与标准件：列表的筛选（类别、状态、只看借出的、我借的）、外组隔离。

之前浏览器验证查出过只有走一遍才能发现的问题，例如试件详情的地址直接打开是"页面不存在"、只读页面上的上传提示不对。

## Proposal

- 每个功能文件单独一个分支、一个 PR，标题写"验证：<文件名>"。
- 按功能文件里 "Driving it with chrome-devtools MCP" 一节操作。文件里的文字和页面不一致时，以页面为准改文件。
- 每个子功能都留截图或快照，副作用用 `query.sh` 从数据库读回；证据放在 `backend/var/verify-evidence/<日期>-<功能文件名>/`（不提交）。
- 走完后更新 `features/README.md` 表格里的"实际走通"一列：写日期、代码提交号，以及哪些没走、为什么。
- 发现缺陷时：
  - 一看就懂、只改一个模块的，直接修，并补回归测试；
  - 改行为、改规则的，先在 `.agents/notes/proposed/bug-fix/` 写方案，等用户确认；
  - PR 说明里写清是怎么发现的。
- 窄屏统一用 `emulate` 的 `390x844x3,mobile,touch`，每个主菜单页面截一张图，只记录挤压、遮挡、按钮够不着这类问题。

顺序：`experiments.md` → `reports.md` → `members.md` → `login.md` → 第四期遗留 → 窄屏 → 试样筛选。前两份覆盖第一期的核心流程。

## Alternatives considered

- **用 Playwright 写成自动化端到端测试，放进 CI**：可以长期防回归。但要新增依赖和浏览器下载，CI 时间翻几倍；而且现在连人工走一遍都没做，先走通再决定哪些值得固化。
- **只看截图，不读数据库**：省时间。但"页面显示成功、数据其实没写进去"这类问题会漏掉。

## Acceptance criteria

- 上面列出的每一项，在 `features/README.md` 里要么写着走通的日期和提交号，要么写着没走的原因。
- 发现的每个缺陷都有修复提交（附回归测试），或者有一篇 proposed 的 bug-fix 笔记。
- 证据目录里的截图数量和功能文件的子功能数大致对得上。

## Risks

- 登录有限速：同一账号每分钟最多 5 次。多个上下文反复登录同一个账号会被 429，要复用已登录的上下文。
- Element Plus 的 switch、checkbox 把真正的 input 藏起来了，`click`、`fill` 会超时；绕过办法见 `features/specimens.md` 的 Gotchas。

## Linux 托管试跑边界（仅前两份）

Windows 验证脚本和本地浏览器限制当前环境。试跑分支先用 Ubuntu 自带 Chrome/ChromeDriver 运行实验记录和周报的合成场景，不给常规 CI 加浏览器门禁，也不改变其余项目的验收顺序。每项使用独立临时库和目录；通过前不把待走查项标记为完成。
