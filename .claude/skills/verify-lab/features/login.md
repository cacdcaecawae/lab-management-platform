# 登录、首次登录改密、退出

成员用学号或工号登录。管理员新建的账号带初始密码，首次登录后只能进入"修改密码"页，改完才能使用其他页面。右上角姓名菜单里可以修改密码、退出登录。

## Sub-features

- `login-ok`：正确账号密码登录后进入工作台，左侧栏顶部显示姓名和课题组。
- `login-wrong`：密码错误时登录页出现错误提示，仍停留在登录页。
- `login-first-change`：`s_new` 登录后被带到"修改密码"页，页面提示"首次登录，请先修改初始密码。"；改密后才能进入工作台。
- `login-logout`：姓名菜单 → "退出登录"后回到登录页，再打开 `/datasets` 会被带回登录页。

## How to get to it (user POV)

- 打开任意页面，未登录时自动跳到 `/login`。
- 左侧栏顶部姓名按钮展开的菜单：menuitem "修改密码"、"退出登录"。

## Driving it with chrome-devtools MCP

前提：

- 刚启动的实例。`s_new` 尚未改过密码。
- 证据目录：`backend/var/verify-evidence/<日期>-login/`。

步骤：

- **正常登录。** `new_page` 打开 `http://127.0.0.1:5273/login`，`isolatedContext` 为 `s_a`。textbox "学号 / 工号" 填 `s_a`，textbox "密码" 填 `Verify-2026!`，点 button "登录"。URL 变为 `http://127.0.0.1:5273/`，快照里有 button "学生甲（验证课题组）"。
- **密码错误。** `new_page` 打开登录页，`isolatedContext` 为 `wrong`。填 `s_b` 和 `wrong-password`，点 "登录"。URL 仍为 `/login`，表单里出现错误 alert。截图存证。只试一次，避免触发登录限速。
- **首次改密。** `new_page` 打开登录页，`isolatedContext` 为 `s_new`。用 `s_new` / `Verify-2026!` 登录。页面跳到 `/password`，heading "修改密码"，有文字"首次登录，请先修改初始密码。"。此时 `navigate_page` 到 `/datasets`，仍被带回 `/password`。在 textbox "原密码" 填 `Verify-2026!`，"新密码"和"确认新密码"都填 `Verify-2026-new!`，点 button "确认修改"。页面进入工作台。
- **改密的第二视角。** 运行 `bash .claude/skills/verify-lab/scripts/query.sh 'from accounts.models import User; u = User.objects.get(username="s_new"); print(u.must_change_password, u.check_password("Verify-2026-new!"))'`，输出 `False True`。
- **退出登录。** 在 `s_a` 的页面点 button "学生甲（验证课题组）"，再点 menuitem "退出登录"。回到 `/login`；`navigate_page` 到 `/datasets` 后仍在登录页（URL 带 `next=/datasets`）。

## Gotchas

- 登录按"账号 + 来源地址"限速：同一账号从同一地址每分钟最多 5 次登录请求（验证实例里所有请求都来自 127.0.0.1）。重复跑这个文件前等一分钟，或者重新 launch。
- 改密成功后 `s_new` 的密码不再是 `Verify-2026!`；同一个实例里再验证其他功能时不要用 `s_new`。
- 新密码要通过 Django 的密码校验（长度、常见密码、纯数字等），`Verify-2026-new!` 可以通过。
- 下拉菜单项在点击姓名按钮之后才出现在快照里，点完要重新 `take_snapshot`。

首次改密期间打开受保护的数据集页，完成改密后应回到该页。
