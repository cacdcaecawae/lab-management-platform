# 原始数据：新建、上传、同名拒绝、下载

学生在"原始数据"里新建数据集并上传文件。文件入库后只读；同一数据集里不能有同名文件，重复上传会被拒绝且不覆盖原文件。页面显示每个文件的 SHA256 和数据集的当前版本码，下载得到的文件与上传的完全一致。别人的数据集打不开。

## Sub-features

- `datasets-create`：新建数据集后进入详情页，编号形如 `DS-2026-0001`。
- `datasets-upload`：上传文件后出现"已入库"，文件表多一行，显示 SHA256，"当前版本"随之变化。
- `datasets-duplicate`：再次上传同名文件，显示"上传失败：已存在同名文件：<文件名>"，文件数和版本码都不变。
- `datasets-download`：下载链接返回的内容，SHA256 与页面显示、本地文件一致。
- `datasets-isolation`：同组另一个学生打开这个数据集的地址，看到"记录不存在或无权查看"；接口和下载链接都返回 404。

## How to get to it (user POV)

- 左侧菜单"原始数据" → 按钮"新建数据集"。
- 数据集列表里点编号链接，进入详情页；详情页"文件"卡片右上角的"上传文件"按钮。
- 文件表最后一列的"下载"链接。

## Driving it with chrome-devtools MCP

前提：

- 刚启动的实例，`lab_verify` 里没有数据集，所以新建的就是 `DS-2026-0001`，数据集 id 为 1，第一个文件 id 为 1。
- 证据目录：`backend/var/verify-evidence/<日期>-datasets/`。

步骤：

- **登录学生甲。** `new_page` 打开 `http://127.0.0.1:5273/login`，`isolatedContext` 为 `s_a`。在 textbox "学号 / 工号" 填 `s_a`，textbox "密码" 填 `Verify-2026!`，点 button "登录"。页面跳到工作台，右上角是 button "学生甲（验证课题组）"。
- **新建数据集。** 点 menuitem "原始数据"，再点 button "新建数据集"，出现 dialog "新建数据集"。点 combobox "*项目"，按 `ArrowDown`、`Enter`，下拉框旁显示"导波螺栓松动"。在 textbox "*名称" 填 `验证-导波波形`，radio "原始数据" 保持选中，点 button "保存"。页面跳到 `/datasets/1`，显示"DS-2026-0001 验证-导波波形"，"文件"一栏为"0 个，共 0 B"。
- **上传文件。** 对 button "上传文件" 用 `upload_file`，路径为 `<launch.sh 打印的上传目录>\wave_001.csv`。用 `wait_for` 等 "已入库"。文件表出现 `wave_001.csv`、`27 B`，SHA256 为 `8125f9baec3d332ae9f28085aa36435d705a6880239a93d7e67a57dda7d5caf6`（与 `SHA256SUMS` 一致）；"文件"变为"1 个，共 27 B"，"当前版本"不再是空数据集的 `e3b0c44298fc`。
- **同名拒绝。** 再对 button "上传文件" 上传同一个 `wave_001.csv`。用 `wait_for` 等 "上传失败"。出现 alert "上传失败：已存在同名文件：wave_001.csv"；文件表仍只有一行，"文件"和"当前版本"不变。
- **留证。** `take_screenshot`（`fullPage: true`）和 `take_snapshot` 各存一份到证据目录。
- **下载比对。** 用 `evaluate_script` 执行 `async () => { const r = await fetch('/api/files/1/download/'); const b = await r.arrayBuffer(); const h = await crypto.subtle.digest('SHA-256', b); return { status: r.status, sha256: [...new Uint8Array(h)].map(x => x.toString(16).padStart(2, '0')).join('') } }`，`filePath` 存到证据目录。`status` 为 200，`sha256` 与页面显示一致。这个地址就是"下载"链接的地址。
- **第二视角。** 运行 `bash .claude/skills/verify-lab/scripts/query.sh 'from datasets.models import DataFile; print([(f.name, f.sha256, f.file.name) for f in DataFile.objects.all()])'`，只有一行 `wave_001.csv`，存储路径形如 `datasets/1/<32 位十六进制>`；`backend/var/verify/data/datasets/1/` 下只有一个文件。把输出和 `SHA256SUMS` 复制到证据目录。
- **跨账号隔离。** `new_page` 打开登录页，`isolatedContext` 为 `s_b`，用 `s_b` / `Verify-2026!` 登录。`navigate_page` 到 `http://127.0.0.1:5273/datasets/1`，用 `wait_for` 等 "记录不存在或无权查看"，页面上有 button "返回数据列表"。再用 `evaluate_script` 请求 `/api/datasets/1/` 和 `/api/files/1/download/`，两者状态码都是 404。截图存证。

## Gotchas

- combobox "*项目" 的选项不在快照里，只能用键盘选；如果显示的不是"导波螺栓松动"，说明种子数据不对，先跑 doctor.sh。
- "已入库""上传失败"是上传队列里的文字，刷新页面后就没了；要在上传后立刻 `wait_for`。
- 页面上 SHA256 是完整的 64 位，"当前版本"只显示前 12 位。
- 数据集和文件的 id 依赖刚启动的空库；如果之前已经在这个实例里建过数据，从列表里点编号进入，并以详情页的 URL 为准。
