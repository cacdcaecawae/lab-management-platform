# Agent Note: 科研记录二合一：记录自带文件，已提交的在项目内共享（issue #58 P1）

Status: implemented

<!--
  【维护提醒】
  1. 现行法律契约：代码重构、改名或路径变更时，同批就地更新事实。禁止把 Decision 改写成另一个决定。
  2. 时态纪律：严禁 ## Proposal / ## Plan / ## Acceptance criteria 等计划态标题；Decision 用现在时（门禁只拒标题）。
  3. 归档契约：只插 Archived: YYYY-MM-DD 紧邻 Status: implemented。互链写在新笔记，不写进归档篇。
-->

## Problem

- 一次实验要跨三页：先在"原始数据"新建数据集、传文件，再回"实验记录"选它；做数据处理还要先去"原始数据"建"脚本""结果"两个数据集，再回"数据处理"选。
- 数据处理要求脚本数据集或 git 仓库、运行环境、结果数据集都齐，用 Origin、Excel 或仪器软件处理数据的同学提交不了。
- 文件入库后不能删，手滑传错的文件只能留着；项目必填，外部导入或仿真数据也得挂一个项目；拖文件夹会提示不支持。
- 实验数据只有本人和导师能看。[越权返回 404](../architecture/2026-11-16-access-scope-404.md) 定的是同一项目的同学也不能互看，同项目的同学只能用 U 盘传数据。issue #58（项目负责人逐条确认过的总控清单）把它改为：关联了项目并已提交的记录，项目当前成员可以查看、下载、引用。

## Decision

### 记录自带文件

- `Experiment.dataset`（一对一，反向名 `raw_of`）是这条实验自己的原始数据，创建记录时一起建好（`ExperimentViewSet.perform_create`）。原来的多对多 `datasets` 留作"早期关联的数据集"，只读展示。
- 数据处理的 `script_dataset`、`output_dataset` 也随记录创建（`ProcessingRunViewSet.perform_create`），在数据处理页直接上传；复制记录时传原记录的 `script_dataset_id`，两条共用脚本。PATCH 不能把它们设为空。仍然复用数据集的上传、SHA256、同名拒绝、版本、ZIP、预览，见 [处理记录复用数据集](../architecture/2026-11-16-runs-reuse-datasets.md)。
- 现场照片 / 现象附图是单独的 `ExperimentPhoto`：本人在草稿时增删（JPG、PNG、WebP、GIF，不超过 20 MB），提交后随记录锁定；浏览器先压缩大的相机照片（`utils/image.preparePhoto`）。
- 数据处理改为引用实验：`ProcessingRun.experiments`（多对多，反向名 `runs`）。提交时固定被引用实验的原始数据版本（`ProcessingRun.cited_datasets`）；`inputs` 留作早期引用的数据集。
- 拖入文件夹：前端 `utils/dropped.ts` 展开文件夹（`webkitGetAsEntry`，分批读目录），每个文件带 `path` 单独上传；服务器清理路径（去掉空段、`.`、`..`）后作为文件名，同一数据集内仍唯一；ZIP 按路径放进文件夹，下载名取最后一段。
- 新建页第一次上传照片或文件时先保存草稿。保存把地址从 `/new` 换成 `/<id>`（`router/saved-editor.ts`），离开前的提醒（`useUnsavedGuard`）不拦这一步（`isSavedEditorReplacement`）：否则正在上传的那一页会误弹"离开这一页"，地址停在 `/new`。
- 页面：侧栏"科研记录"只有"实验与原始数据"和"数据处理"。`/datasets` 跳到 `/experiments`（带上筛选）；数据集页 `dataset-detail` 保留，给"提交时的数据版本"、搜索结果和旧链接用。文件区是共用组件 `components/DataFilesPanel.vue`（模块的接口由页面传进来），"被引用处"是 `components/RecordReferences.vue`。
- 提交规则：实验只要名称和日期。数据处理要：至少引用 1 条原始数据，且引用的实验现在仍看得到；算法三选一（上传了脚本文件、git 仓库 + commit、软件/方法说明 `method`）；上传了结果文件或写了结论；运行环境选填。

### 项目选填

- `Experiment`、`ProcessingRun`、`Dataset` 的 `project` 可空。草稿里改项目时，记录自己的数据集跟着改（存储统计按项目汇总时用）。

### 删除（P1-2）

- `DELETE /api/files/{id}/`：本人删传错的文件。文件在非草稿记录固定的版本里就不能删（`datasets/versions.py` 的 `held_versions` / `locked_file_ids`）：按名字列出会固定版本的模型（`PIN_HOLDERS`：实验、数据处理、周报），用 `data_versions__has_key` 找出固定了这个数据集的版本码。退回草稿的记录已清空 `data_versions`，不再锁住。删除时去掉含这个文件的旧快照，免得以后同一版本码复用一份缺文件的快照。
- 并发：提交固定版本（`pin_versions`）和删除文件都先对数据集行加 `FOR NO KEY UPDATE`（`lock_datasets`），两者先后进行；上传只引用这一行，不受影响。
- 删除草稿记录：没被数据处理或周报引用、原始数据没被别的记录引用、也没有锁定文件时，记录连同原始数据文件和照片一起删除（存储里的文件在提交后删）。数据处理只删只被它用的脚本、结果文件，和复制出来的记录共用的保留。

### 项目内共享（P1-3）

- `core.permissions.scope_research`：在 `scope_private`（本人 / 本组导师）之外，加上"项目是本组的、自己是当前成员或负责人"的项目里**已提交**的记录。用子查询，避免成员表的连接把一条记录重复成多行。实验、数据处理的列表、详情、历史、照片和"可引用的实验"（`CitableExperimentField`）都用它。
- `datasets/queries.py` 的 `scope_datasets`：数据集和文件在本人 / 导师之外，持有它的记录（`raw_of`、早期的 `experiments`、`script_of_runs`、`produced_by_runs`、早期的 `used_by_runs`）被共享时也可见。数据集页、文件列表、ZIP、预览、下载、被引用处都用它。
- 写操作仍然只有本人，退回仍然只有导师；共享给项目成员的是只读。
- 一条数据处理引用了别的项目的实验时，能看这条数据处理的人看到被引用实验的编号和名称，打开它仍按那条实验自己的范围。
- 提交数据处理时，引用的实验必须仍看得到（例如队友的实验被退回后就不能再固定它），提示里写明是哪条。草稿已经引用的实验之后变得看不到时，草稿仍能保存（页面提交前先保存，`CitableExperimentField` 保留已引用的）；新加的引用必须看得到。

### 升级（`research/migrations/0007_records_own_files_data.py`）

1. 实验只关联了一个本人的原始数据集、且这个数据集只被它关联时，它直接成为这条实验的 `dataset`；否则给实验建一个空的，原来的关联留着。
2. 没有实验显示的原始数据集，各生成一条草稿实验（名称、说明、创建时间取自数据集）。
3. 数据处理引用的输入数据集若已是某条实验的原始数据，改为引用那条实验；缺脚本、结果数据集的补上。
4. 没有任何记录显示的脚本、结果数据集，各生成一条草稿数据处理。

不移动、不删除任何文件；`data_versions` 的数据集 id 不变，快照仍然有效。每一步在记录的修改历史里写一条"系统"操作和原因。再跑一遍不产生变化；回滚只回滚结构。

### 给其他任务包的接口

- P6：`/experiments/new?project=<id>&equipment=<id>&date=YYYY-MM-DD` 预填新建页；`GET /api/experiments/?equipment_item=<id>`、`?specimen=<id>` 列出用了某台设备、某件试件的记录（按看的人的范围）。
- P4：路由名 `experiments`、`experiment-new`、`experiment-edit`、`runs`、`run-new`、`run-edit`、`dataset-detail` 不变；实验、数据处理列表现在包含项目里共享的记录，只能选自己记录的下拉要带 `owner`。
- P5（`workbench`）：全站搜索仍用 `scope_private` 搜实验、数据处理、数据集、文件，项目成员搜不到共享的记录；存储用量不统计实验照片。

## Alternatives considered

- **文件直接挂在实验、数据处理上（新的文件表），不再用数据集**：模型更直观；但上传、SHA256、同名拒绝、版本快照、ZIP、预览、权限都要重写一遍，旧文件还要搬表。保留数据集作文件容器，每条记录一个。
- **实验继续用多对多 `datasets`，新文件传进其中一个**：不用加字段；但"传进哪一个"说不清，旧记录关联了多个数据集时更乱。用一对一的 `dataset` 表示"这条记录自己的原始数据"。
- **照片也放进一个数据集**：能复用版本和共享；但手机拍的照片常都叫 `image.jpg`，同名拒绝会挡住第二张，照片也不需要版本码。照片用单独的小表，随记录锁定。
- **文件只要进过任何快照就不能删**：判断最简单；但导师正是因为文件传错才退回时，学生还是删不掉。改为只看非草稿记录固定的版本。
- **数据集模块 import 研究、周报的模型来判断锁定**：最直接；但 `datasets` 在分层表里低于 `research`、`reports`。按名字列出会固定版本的模型，用 `apps.get_model` 取，和 `references` 用反向关联名的做法一致。
- **升级时把孤立的旧数据集生成为已提交记录**：项目成员马上能看到；但这些数据从没提交过，状态是编出来的，还会把文件锁住。生成草稿，本人决定提交还是删除。
- **数据处理的读者也能看到它引用的别的项目的实验**：复现时更方便；但数据会经由别的项目漏出去。被引用的实验按它自己的范围打开。

## Consequences

- **收益**：一次实验在一页记完；数据处理一页闭环，不写代码的处理方式也能提交；传错的文件能删；项目成员直接查看、下载、引用队友已提交的数据。
- **代价与已知上限**：
  - 每条记录多 1–2 个数据集，升级时为每条旧记录补齐；"提交时的数据版本"里显示的是数据集编号。
  - 升级生成的草稿会出现在工作台的"未提交"里（每类最多 5 条，另有"全部 N 条"）。
  - 锁定判断每次删除查 3 张表的 `data_versions`（`has_key`，没有索引）；记录到几万条时给 `data_versions` 加 GIN 索引。
  - 共享看项目当前成员：移出项目就看不到；不跨课题组。
  - 全站搜索、存储用量还没跟上（属于 P5 的 `workbench`）。
  - 复制的数据处理和原记录共用脚本：在其中一条追加脚本，另一条也看得到。

## Verification

- `DB_TEST_NAME=test_lab_p1 bash scripts/check.sh`：87 篇笔记校验通过，`makemigrations --check` 无变化，后端 621 passed、1 skipped，前端 60 个测试文件 220 项通过，`vue-tsc` 和 `vite build` 通过。
- 后端新测试：项目内共享 `research/tests/test_sharing.py`（13 项）；删除、照片、改项目、设备和试件筛选 `research/tests/test_files_and_photos.py`（14 项）；升级迁移 `research/tests/test_upgrade_migration.py`；文件夹路径 `datasets/tests/test_folders.py`（3 项）。`tests/test_phase1_acceptance.py` 改为新的共享规则。
- 升级演练：用升级前的代码（`origin/main`）在临时库造数据：实验关联数据集、已提交的实验、固定了版本的数据处理和周报、孤立的数据集。再用本分支 `migrate`，通过新接口核对：数据集认领、引用改写、版本码不变、5 个文件都在、固定的文件不能删、项目成员只看到已提交的那条。临时库已删除。
- 浏览器：verify-lab 实例上走了 `experiments.md`、`runs.md`、`datasets.md`，证据在 `backend/var/verify-evidence/2026-11-25-p1-research/`，README 列出走过的和没走的。走查中修了两处："新建页首次上传"误弹离开提醒；队友记录被退回后，保存引用它的草稿报"无效主键"。
- 未验证：手机宽度；真实拖入文件夹（用合成拖放事件代替）；`.claude/skills/verify-lab/scripts/browser/` 的 Selenium pilot 已按新页面改写，没有运行过（只在 pilot 分支的 CI 上跑）。
