# 成员管理：新建学生、角色限制、重置密码

管理员在"成员"页新建本组学生账号、编辑学生资料、重置密码、停用账号。管理员只能管理学生账号和自己的资料：不能把成员设为导师或管理员，导师、管理员账号没有"编辑"按钮。学生看不到学号，也不能按学号搜索。

## Sub-features

- `members-create`：管理员新建学生，列表多一行；新账号首次登录要改密码。
- `members-role-limit`：新建或编辑时把角色设为导师或管理员，出现"管理员只能设置学生账号；导师和管理员账号请联系运维在“系统管理”里设置"。
- `members-no-edit-supervisors`：导师甲那一行没有"编辑"按钮。
- `members-reset`：对学生"重置密码"后，学生用新密码可以登录。
- `members-student-view`：学生打开"成员"页，看不到"学号 / 工号"列，搜索框占位为"搜索姓名、研究方向"。

## How to get to it (user POV)

- 左侧菜单"成员"。管理员看到按钮"新建成员"，每行有"编辑""重置密码"和启用/停用按钮。

## Driving it with chrome-devtools MCP

前提：

- 刚启动的实例。
- 证据目录：`backend/var/verify-evidence/<日期>-members/`。

步骤：

- **新建学生。** 以 `mgr` 登录，点 menuitem "成员"，点 button "新建成员"，出现 dialog "新建成员"。"*学号 / 工号（登录名）"填 `s_c`，"*姓名"填 `学生丙`，"角色"保持学生，"*初始密码"填 `Init-2026-pass!`，点 button "保存"。列表出现"学生丙"。
- **角色限制。** 再点 "新建成员"，填 `s_d` / `学生丁` / `Init-2026-pass!`，"角色"用键盘选"导师"，点 "保存"。对话框里出现"管理员只能设置学生账号；导师和管理员账号请联系运维在“系统管理”里设置"，列表里没有"学生丁"。点 "取消"。
- **不能编辑导师。** 在快照里找"导师甲"那一行：有"重置密码"，没有"编辑"。
- **重置密码。** 在"学生丙"那一行点 "重置密码"，dialog "重置密码"的"新密码"填 `Reset-2026-pass!`，点 button "重置"。
- **第二视角。** 运行 `bash .claude/skills/verify-lab/scripts/query.sh 'from accounts.models import User; u = User.objects.get(username="s_c"); print(u.role, u.group.name, u.check_password("Reset-2026-pass!"))'`，输出 `student 验证课题组 True`。
- **学生视角。** 以 `s_b` 登录，点 menuitem "成员"。表头没有"学号 / 工号"，搜索框占位为"搜索姓名、研究方向"，没有"新建成员"按钮。截图存证。

## Gotchas

- "导师甲"行虽然没有"编辑"，但仍有"重置密码"按钮；点了会被后端拒绝。这是当前界面的样子，如要验证拒绝提示，记下实际显示的文字。
- 初始密码和重置的密码都要通过 Django 的密码校验。
- 新建的 `s_c` 首次登录会被带到改密页，这是 `login.md` 的 `login-first-change` 行为。
