# 手机骨架

宽 ≤ 768px 时页面换一套骨架（DESIGN.md "手机"）：底部四个标签（工作台、预约、通知、菜单），列表页顶栏是页面名和这一页的按钮，表格变成一条一张的卡片，下拉筛选收在"筛选"后面，新建 / 编辑弹窗铺满全屏，详情字段一行一对。电脑宽度下和原来一样。

## Sub-features

- `phone-tabbar`：底部有 link "工作台"、"预约"、"通知" 和 button "打开菜单"（显示文字"菜单"）。在成员页时"菜单"是选中的；点"通知"跳到 `/notifications`，"通知"变成选中；通知有未读时图标上有红色数字。点"菜单"左边滑出抽屉，里面有账号名片、搜索和全部模块。
- `phone-topbar`：设备台账页顶栏左边是 heading "设备台账"，右边是"使用统计""打印标签"两个图标和"新建设备"按钮；页面里没有电脑那排标签。设备详情页没有顶栏，卡片头是"← 返回 | UT-001 超声探伤仪"，下面一行是图标和"预约"。
- `phone-cards`：设备台账每台设备一块：第一行是编号（蓝色链接）和右上角状态"可用"，下面是"名称 超声探伤仪""型号 CTS-9006"这样的灰字；页面不能左右滑（`document.scrollingElement.scrollWidth` 是 390）。成员页每人一块，最下面右边是"编辑 重置密码 停用"。
- `phone-filters`：设备台账只看到搜索框和 button "筛选"；点它出现"全部状态"下拉和"校准到期"胶囊，按钮名变成"收起筛选"。报销页没有搜索框：卡片第一行开头是带字的 button "筛选"，点开后"全部状态""全部类别""全部月份""全部经费""全部人员"一个一行排在下面。通知页只有"仅未读"一个胶囊，不收，直接露着。周报页（管理员）"未交名单"的周选择器不收。组会列表只有"新建组会"一个按钮，移到顶栏后卡片顶上不留空行。
- `phone-dialog`：点顶栏"新建设备"，弹窗铺满屏幕（`.el-dialog.is-fullscreen`），表单一列，"取消""保存"贴在屏幕底部，表单在中间滚动。
- `phone-two-toolbars`：报销页顶栏只有"登记报销"；切到 tab "统计"，"导出 Excel""财务邮箱""发送财务提醒"留在统计卡片里。
- `phone-desktop`：1440 宽打开设备台账，左侧栏、顶上的标签、表格和右上角按钮都和改之前一样，没有底部栏。

## How to get to it (user POV)

- 用手机打开平台，或在电脑浏览器把窗口拉窄到 768px 以下。

## Driving it with chrome-devtools MCP

前提：

- 验证实例（`mgr` / `Verify-2026!`），种子数据里有 4 台设备。
- 证据目录：`backend/var/verify-evidence/<日期>-phone/`。

步骤：

- `emulate` 设 `viewport: 390x844x2,mobile,touch`。打开 `/members`，截图；看底部标签栏和成员卡片。
- 打开 `/equipment`，截图；`evaluate_script` 读 `document.scrollingElement.scrollWidth`（应为 390）、`#phone-actions` 里按钮的名字（`aria-label` 或文字）。点 button "筛选"，再截图。
- 点顶栏"新建设备"，读 `.el-dialog.is-fullscreen` 的大小（390×844）和 `.el-dialog__footer` 的底边（贴近 844），截图后按 Esc 关掉。
- 打开 `/equipment/<id>`，截图：没有顶栏，字段一行一对。
- 打开 `/reimbursements`，读 `#phone-actions` 的按钮；点 tab "统计"，读统计卡片里 `.page-toolbar-actions` 的按钮。
- 点 button "打开菜单"，抽屉打开；点 link "通知"，URL 变成 `/notifications`。
- `emulate` 不带 viewport 恢复电脑宽度，打开 `/equipment` 截图对比。

## Gotchas

- 列表卡片的"表头 值"是页面渲染后由脚本写到格子上的（`data-label`），截图前等表格数据加载完（约 1 秒）。
- 手机模拟下滚动条会盖在全屏弹窗的输入框右边一点；真手机上滚动条是浮在上面的细条，不占位置。
- `emulate` 的设置会一直留在这个页面上，验完记得恢复，不然后面验电脑页面时还是手机宽度。
- 自动场景 `scripts/browser/responsive.py` 用 button "打开菜单" 打开抽屉，底部栏的"菜单"沿用了这个名字。
