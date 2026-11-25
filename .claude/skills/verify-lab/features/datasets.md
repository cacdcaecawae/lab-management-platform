# 数据集页：一条记录的文件单独打开，看提交时的版本

侧栏不再有"原始数据"：文件跟着"实验与原始数据""数据处理"走。一批文件（数据集）仍有自己的页面，从"提交时的数据版本"、全站搜索的"数据集 / 数据文件"结果和旧链接打开：显示文件、当前版本码、某个提交时的版本（之后上传的标"提交后新增"）、打包下载 ZIP（看版本时只含那个版本），"被引用处"列出持有它的记录和引用它的数据处理、周报。旧的 `/datasets` 地址跳到"实验与原始数据"。

## Sub-features

- `datasets-redirect`：打开 `/datasets?project=1`，地址变成 `/experiments?project=1`，侧栏"实验与原始数据"高亮。
- `datasets-version`：从已提交记录的"提交时的数据版本"（或地址 `/datasets/<id>?version=<版本码>`）进入，文件表上方写"提交时的版本 xxxxxxxxxxxx"，之后上传的标"提交后新增"；卡片头的"打包下载这一版本 ZIP"只含那个版本的文件。
- `datasets-references`：实验原始数据的数据集页，"被引用处"列出那条实验，以及引用它的数据处理（标"引用"）和周报。
- `datasets-download`：下载链接返回的内容 SHA256 与页面显示、本地文件一致。
- `datasets-isolation`：别人草稿的数据集地址，看到"记录不存在或无权查看"；接口和下载链接都返回 404。

## How to get to it (user POV)

- 已提交的记录里"早期关联的数据集"/"提交时的数据版本"的链接；全站搜索结果；旧书签。
- 详情页卡片头：返回、"打包下载 ZIP"、"编辑数据集"（本人）、"删除数据集"（本人、空且没被引用）。

## Driving it with chrome-devtools MCP

前提：按 `experiments.md` 走到"关联项目并提交"，有一条已提交的实验，原始数据里有 `wave_001.csv`，提交后又传了 `wave_002.csv`。用 query.sh 查出它的数据集 id 和版本码：`query.sh 'from research.models import Experiment; e = Experiment.objects.get(); print(e.dataset_id, e.data_versions)'`。证据目录：`backend/var/verify-evidence/<日期>-datasets/`。

步骤：

- **旧地址跳转。** 以 `s_a` 登录，`navigate_page` 到 `http://127.0.0.1:5273/datasets?project=1`，地址变成 `/experiments?project=1`。
- **版本视图。** 打开 `/datasets/<id>?version=<版本码>`。文件表上方写"提交时的版本"，`wave_002.csv` 标"提交后新增"，`wave_001.csv` 没有。用 `evaluate_script` 取 link "打包下载这一版本 ZIP" 的内容，ZIP 里只有 `wave_001.csv`。截图存证。
- **被引用处。** 同一页"被引用处"列出"实验与原始数据（1）"那条实验；按 `runs.md` 建过引用它的数据处理后，"数据处理"一组里有它，标"引用"。
- **下载比对。** 用 `evaluate_script` 执行 `async () => { const r = await fetch('/api/files/1/download/'); const b = await r.arrayBuffer(); const h = await crypto.subtle.digest('SHA-256', b); return { status: r.status, sha256: [...new Uint8Array(h)].map(x => x.toString(16).padStart(2, '0')).join('') } }`，`status` 为 200，`sha256` 与页面显示一致。
- **隔离。** `s_a` 新建一条草稿并上传一个文件，`s_b` 打开它的数据集地址，看到"记录不存在或无权查看"，页面上有 button "返回实验与原始数据"；`evaluate_script` 请求 `/api/datasets/<id>/` 和那个文件的下载地址，都是 404。

## Gotchas

- 数据集 id 依赖刚启动的空库；以 query.sh 读出的为准。
- 看版本时的 ZIP 只含那个版本；不带 `?version=` 时是全部文件。
