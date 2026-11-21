# 成员管理：新建学生、角色限制、重置密码

管理员在"成员"页新建本组学生账号、编辑学生资料（包括改正填错的学号 / 工号）、重置密码、停用账号。管理员只能管理学生账号和自己的资料：不能把成员设为导师或管理员，导师、管理员账号没有"编辑"按钮。学生看不到学号，也不能按学号搜索。

## Sub-features

- `members-create`：管理员新建学生，列表多一行；新账号首次登录要改密码。
- `members-role-limit`：新建成员时角色固定显示“学生”，没有角色下拉框；不能把学生升为导师或管理员。
- `members-no-edit-supervisors`：导师甲那一行显示“由运维管理”，没有“编辑”或“重置密码”按钮。
- `members-reset`：对学生"重置密码"后，学生用新密码可以登录。
- `members-rename`：`mgr` 编辑"新同学"，textbox "*学号 / 工号（登录名）" 能改。改成 `s_a` 保存，字段下出现"这个学号 / 工号已经有账号在用"，弹窗不关；改成 `2026099` 保存，提示"已保存。学号 / 工号改成了 2026099，下次登录要用新的"，列表里是 2026099，用 2026099 / `Verify-2026!` 能登录、`s_new` 不能。改回 `s_new`。
- `members-student-view`：学生打开"成员"页，看不到"学号 / 工号"列，搜索框占位为"搜索姓名、研究方向"。

## How to get to it (user POV)

- 左侧菜单"成员"。管理员看到按钮"新建成员"，每行有"编辑""重置密码"和启用/停用按钮。

## Driving it with chrome-devtools MCP

前提：

- 刚启动的实例。
- 证据目录：`backend/var/verify-evidence/<日期>-members/`。

步骤：

- **新建学生。** 以 `mgr` 登录，点 menuitem "成员"，点 button "新建成员"，出现 dialog "新建成员"。"*学号 / 工号（登录名）"填 `s_c`，"*姓名"填 `学生丙`，"角色"保持学生，"*初始密码"填 `Init-2026-pass!`，点 button "保存"。列表出现"学生丙"。
- **角色限制。** 打开“新建成员”和学生的“编辑”对话框，查看“角色”一栏只显示“学生”，不是下拉框。
- **不能编辑导师。** 在快照里找"导师甲"那一行：显示“由运维管理”，没有“编辑”或“重置密码”。
- **重置密码。** 在"学生丙"那一行点 "重置密码"，dialog "重置密码"的"新密码"填 `Reset-2026-pass!`，点 button "重置"。
- **第二视角。** 运行 `bash .claude/skills/verify-lab/scripts/query.sh 'from accounts.models import User; u = User.objects.get(username="s_c"); print(u.role, u.group.name, u.check_password("Reset-2026-pass!"))'`，输出 `student 验证课题组 True`。
- **学生视角。** 以 `s_b` 登录，点 menuitem "成员"。表头没有“学号 / 工号”，搜索框占位为“搜索姓名、研究方向”，没有“新建成员”按钮。按新账号的登录名搜索，确认不按登录名匹配。截图存证。

## Gotchas

- 导师账号的维护在“系统管理”，不在本组成员页面。
- 初始密码和重置的密码都要通过 Django 的密码校验。
- 新建的 `s_c` 首次登录会被带到改密页，这是 `login.md` 的 `login-first-change` 行为。
