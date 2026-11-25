# 实验与原始数据：一页记完采集背景和原始数据，提交锁定，项目内共享

一条"实验与原始数据"是一次采集：上半部分写背景（项目选填、设备、试件、参数、步骤、异常、现场照片），下半部分直接上传这次的原始数据文件，可以选文件、拖文件，也可以把整个采集文件夹拖进来（按子文件夹保存）。文件有 SHA256，同名拒绝、不覆盖；还没被已提交记录固定的文件本人可以删除。提交后记录锁定并记下文件版本，导师可退回。关联了项目并提交的记录，项目里的同学可以查看、下载，但不能改；草稿和没选项目的只有本人和导师看得到。

## Sub-features

- `experiments-draft`：新建页不选项目也能"保存草稿"，出现"草稿已保存"，地址变成 `/experiments/<id>`。
- `experiments-photo`：在"现场照片 / 现象附图"上传一张图，出现缩略图，点名称打开预览。
- `experiments-upload`：在"原始数据"卡片点"上传文件"传 `wave_001.csv`，表里多一行，SHA256 与 `SHA256SUMS` 一致；再传同一个文件，出现"wave_001.csv 上传失败：已存在同名文件：wave_001.csv"，行数不变。
- `experiments-folder`：把一个文件夹（含子文件夹）拖进"原始数据"卡片，卡片出现虚线框和"松开上传"；松开后每个文件以"文件夹/子文件夹/文件名"出现在表里；"打包下载 ZIP"里是同样的目录结构。
- `experiments-delete-file`：草稿里点某个文件的"删除"并确认，出现"文件已删除"，文件从表里和磁盘上消失。
- `experiments-submit`：提交后出现"已提交，记录已锁定"；"保存草稿""提交"按钮消失；"原始数据"写"提交时的版本 xxxxxxxxxxxx"；已固定的文件没有"删除"。之后再上传的文件标"提交后新增"，它可以删除。
- `experiments-return`：导师点"退回"并填原因，出现"已退回"，状态回到"草稿"；之前固定的文件又能删除。
- `experiments-history`：点"修改历史"能看到提交和退回，包括退回原因。
- `experiments-shared`：学生乙（同一项目的成员）在"实验与原始数据"列表里看到学生甲已提交的记录，打开后只读（"……提交，记录已锁定。"），能预览、下载文件，没有"上传文件""删除"。
- `experiments-isolation`：学生甲的草稿、没选项目的已提交记录，学生乙打开都看到"记录不存在或无权查看"；管理员甲（不在项目里）打开已提交记录也是。
- `experiments-prefill`：打开 `/experiments/new?project=1&equipment=<id>&date=2026-11-20`，项目、台账设备、日期已填好。

## How to get to it (user POV)

- 左侧展开 "科研记录" → menuitem "实验与原始数据" → 按钮"新建实验与原始数据"。
- 列表里点编号进入记录页。学生在工具栏勾"只看我的"只看自己的。
- 记录页：卡片头的按钮（"复制为新草稿""修改历史""退回""删除记录""保存草稿""提交"），表单下面是"现场照片 / 现象附图"；第二张卡片"原始数据"是文件表和"上传文件""打包下载 ZIP"，下面是"被引用处"。

## Driving it with chrome-devtools MCP

前提：刚启动的实例。证据目录：`backend/var/verify-evidence/<日期>-experiments/`。

步骤：

- **新建草稿。** 以 `s_a` 登录，展开 "科研记录"、点 menuitem "实验与原始数据"，点 button "新建实验与原始数据"。textbox "*实验名称" 填 `验证-螺栓预紧力扫描`，"*实验日期"填 `2026-11-17`（填后按 `Enter`），项目先不选。点 button "保存草稿"，`wait_for` "草稿已保存"。
- **照片。** 对 button "上传附件"（照片区）用 `upload_file` 传 `photo.png`。出现缩略图和文件名 `photo.png`，点文件名打开预览弹窗。
- **上传与同名拒绝。** 对 "原始数据" 卡片的 button "上传文件" 用 `upload_file` 传 `wave_001.csv`，`wait_for` "已上传 1 个文件"。表里一行 `wave_001.csv`，SHA256 与 `SHA256SUMS` 一致。再传一次同一文件，`wait_for` "上传失败"。
- **拖入文件夹。** chrome-devtools 不能拖真实文件夹：用 `evaluate_script` 在 "原始数据" 卡片上派发一个 `drop` 事件，`dataTransfer.items` 的 `webkitGetAsEntry()` 返回模拟的目录项（`isDirectory`、`createReader().readEntries` 分批返回、文件项的 `file()` 返回 `new File(...)`），目录 `采集/ch1/a.csv`、`采集/ch2/a.csv`。`wait_for` "已上传 2 个文件"，表里出现 `采集/ch1/a.csv` 和 `采集/ch2/a.csv`。用 `evaluate_script` 取 "打包下载 ZIP" 链接的内容，确认 ZIP 里的路径（或用 query.sh 读 `DataFile.name`）。
- **删除文件。** 点 `采集/ch2/a.csv` 那一行的 button "删除"，确认框点 "删除"，`wait_for` "文件已删除"。
- **关联项目并提交。** 点 combobox "项目"，`ArrowDown`、`Enter` 选"导波螺栓松动"，点 button "提交"，`wait_for` "已提交，记录已锁定"。"原始数据"写着"提交时的版本"，各文件没有"删除"。再上传 `wave_002.csv`，它标"提交后新增"，有"删除"。截图存证。
- **第二视角。** `query.sh 'from research.models import Experiment; e = Experiment.objects.get(); print(e.status, e.project_id, e.data_versions, list(e.dataset.files.values_list("name", flat=True)))'`。
- **项目内共享。** 新开 `isolatedContext` 为 `s_b` 的页面登录，打开"实验与原始数据"，列表里有这条记录；打开后显示"学生甲 于 …… 提交，记录已锁定。"，文件能预览，没有"上传文件""删除""保存草稿"。截图存证。
- **不共享的情况。** `s_a` 再新建一条不选项目的记录并提交，`s_b` 打开它的地址看到"记录不存在或无权查看"。`mgr` 打开第一条的地址也是。
- **导师退回、修改历史。** 以 `adv` 登录打开第一条，点 button "退回"，原因填 `参数表缺少采样率`，`wait_for` "已退回"。点 button "修改历史"，能看到提交和退回（"原因：参数表缺少采样率"）。`s_a` 刷新后"保存草稿""提交"重新出现，已固定的文件又有"删除"。
- **预填。** 用 query.sh 查出设备 id（没有设备时先按 `equipment.md` 建一台），打开 `/experiments/new?project=1&equipment=<id>&date=2026-11-20`，三个字段已填好。

## Gotchas

- 日期框是 Element Plus 日期选择器，`fill` 后要按 `Enter` 或点别处才生效。
- 新建页第一次上传照片或文件时会先保存草稿（实验名称、日期必填）；名称没填时提示"请先填好实验名称和日期"。
- 照片较大时浏览器会先压缩成 JPEG 再上传，文件名可能从 `.png` 变成 `.jpg`。
- "已上传 N 个文件""文件已删除"几秒后消失，要在操作后立刻 `wait_for`。
- Element Plus 的确认框按钮文字以快照为准。
