# 组会：议程、纪要、附件、行动项

管理员建组会，写议程（汇报人和内容）、纪要和行动项（负责人、事项、截止日期）。议程里的汇报人可以上传自己的附件（汇报 PPT 等，任意类型）；上传人和管理员能删附件。行动项由负责人或管理员勾选完成，完成时间自动记下。负责人的工作台有"我的行动项"卡片，全部完成后卡片消失。本组全员可看，外组 404。

## Sub-features

- `create`：`mgr` 新建组会，保存后进入详情页，提示"已保存"，议程、纪要、行动项都显示出来。
- `presenter-upload`：汇报人 `s_a` 没有 "编辑"，但有 "上传附件"，提示"汇报 PPT 等，任意类型，单个不超过 2 GB"；选 `.pptx` 能上传，列表出现文件名、大小、上传人和时间，以及 "删除"。
- `others-readonly`：`s_b` 看得到组会，行动项复选框 disabled，没有上传和删除；接口勾选完成、上传、编辑、删除附件都是 403。附件下载是 `attachment`，SHA256 与样例一致。
- `my-actions`：`s_a` 工作台"需要你处理"里有一行：类型"行动项"、事项、"2026-xx-xx 截止"，事项链接到组会。
- `mark-done`：`s_a` 勾选完成后"完成时间"出现；回到工作台，"我的行动项"卡片不再显示。
- `isolation`：`x_mgr` 打开组会地址显示"记录不存在或无权查看"，组会和附件接口都是 404，列表为空。

## How to get to it (user POV)

- 左侧展开 "周报组会" → menuitem "组会"，button "新建组会"。
- 新建 / 编辑页：卡片右上角 button "取消"、"保存"（编辑时还有 "删除组会"）；combobox "*日期"，textbox "标题"（默认"组会"）；"议程"每行 combobox "汇报人" 和 textbox "汇报内容"，button "添加汇报"、"删除这一项"；textbox "纪要"；"行动项"每行 combobox "负责人"、textbox "事项"、combobox "截止日期"，button "添加行动项"；底部 "取消"、"保存"。
- 详情页：卡片右上角 button "修改历史"、"编辑"（只有管理员）；行动项表每行 checkbox "完成：<事项>"；"附件"卡片 button "上传附件"。
- 工作台："需要你处理"里类型为"行动项"的行。

## Driving it with chrome-devtools MCP

前提：

- 刚启动的实例。样例文件 `slides.pptx`。
- 证据目录：`backend/var/verify-evidence/<日期>-meetings/`。

步骤：

- **新建。** `mgr` 点 "新建组会"：汇报人选"学生甲"，汇报内容 `相控阵全聚焦成像进展`；纪要随意；点 "添加行动项"，负责人"学生甲"，事项 `整理 TFM 与 PWI 对比数据`，截止日期填一周后（填完点页面空白处收起日历）。点 "保存"，`wait_for` "已保存"。
- **编辑参数校验。** `mgr` 对已有组会 PATCH `{"agenda":[{"topic":"缺汇报人"}]}` 与 `{"actions":[{"content":"缺负责人"}]}`，均为字段级 400，原议程和行动项不变；分别遗漏 topic/content 也应为 400。正常添加完整议程/行动项成功；已有行动项按 id 只改 content 时保留负责人和完成时间。
- **汇报人上传。** `s_a` 打开这个组会：没有 "编辑"；对 "上传附件" 用 `upload_file` 传 `slides.pptx`，`wait_for` "slides.pptx"。
- **其他学生。** `s_b` 打开同一组会：复选框 disabled，没有 "上传附件" 和 "删除"。`evaluate_script` 对 `/api/action-items/<id>/done/` POST、对 `/api/meetings/<id>/files/` 传文件、对 `/api/meetings/<id>/` PATCH、对 `/api/meeting-files/<id>/` DELETE：都是 403（权限反例）。再请求附件下载地址：200，`attachment`，SHA256 与 `slides.pptx` 一致。
- **工作台。** `s_a` 打开工作台，"需要你处理"里有"行动项"一行和事项链接。截图。点链接回到组会。
- **完成。** `s_a` 勾选完成（见 Gotchas），"完成时间"出现。截图。回工作台，卡片消失。
- **外组。** `x_mgr` 打开组会地址：显示"记录不存在或无权查看"；组会和附件接口 404，`/api/meetings/` 的 `count` 为 0。截图。
- **第二视角。** query.sh 读 `meetings.models` 的 `Meeting`、`AgendaItem`、`ActionItem`（`done_at` 有值）、`MeetingFile`（上传人 `s_a`，存储名为随机名）。

## Gotchas

- "汇报人""负责人"是可搜索的下拉框，选项不出现在无障碍快照里；先 `click` 下拉框，再用 `evaluate_script` 点可见的 `.el-select-dropdown__item`。
- 行动项复选框真正的输入框是隐藏的，对快照里的 checkbox 用 `click` 会超时；用 `evaluate_script` 点 `main .el-table .el-checkbox__inner`。
- 截止日期填好后日历浮层不会自己关，点页面标题收起再保存。
- `upload_file` 直接把文件塞给选择框，不受 `accept` 限制，上传成功证明不了用户能选到 `.pptx`。要核对，用 `evaluate_script` 读组会页 `input[type=file]` 的 `accept`：应为空。
