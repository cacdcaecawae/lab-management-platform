# Agent Note: 列表补齐筛选、按列排序、编号可搜、下拉远程搜索、自由文本联想、搜索框即时生效（issue #48 S2 余下、S3、S4、U2）

Status: implemented

## Problem

- 后端早就支持、前端没接出来的筛选（S2 的另一部分已由 PR #52 做完）：报销的起止日期、知识库的标签、任务看板的负责人和里程碑。
- 组会列表、报销列表没有搜索框。
- 常用筛选缺：设备按类别、位置、保管人、空闲；试件按材料、位置、盲测公开；耗材按分类、位置（耗材原来没有"分类"这个字段）；采购按经费、申请人；经费按负责人；成果按有没有全文。
- 全站列表没有一处能按列排序。
- 页面上的编号（`EX-2026-0012`、`RUN-`、`DS-`、`PR-`、`RB-`）是按年份和行号现算的，数据库里没有这一列，搜编号搜不到。
- 表单里的下拉（数据集、采购申请、试件、记录）只取前 100 条，第 101 条以后选不到。
- 设备类别、存放位置、试件材料、耗材单位、研究方向、成果出处、知识库标签都是自由文本，同一个地方被写成 `A302`、`A-302`、`302室`，筛选和统计就分裂了。
- 13 个列表的搜索框要按回车或点开别处才生效；组会附件上传没有进度条，上传中离开页面不提醒。
- 相关决定：[周报汇总与科研记录效率](./2026-11-23-research-and-reports-efficiency.md)（S2 已做的成员筛选）。

## Decision

### 后端：`core/filters.py`

- `Search`：DRF 的 `SearchFilter`，视图写了 `code_prefix` 时，搜索词是一个完整编号就只按编号查那一行：`<前缀>-<年>-<行号>`，年份按 UTC 的创建时间，与模型的 `code` 属性一致。不新增数据库列。实验（`EX`）、处理（`RUN`）、数据集（`DS`）、采购（`PR`）、报销（`RB`）。
- `Ordering`：DRF 的 `OrderingFilter`，只认视图 `ordering_fields` 里的列，其余忽略；同值按 id 倒序，翻页不重复。默认顺序不变。
- `equal(queryset, params, 参数=查找)`：文本原样精确匹配；`_id` 结尾的要整数；不是整数或含 NUL 返回空列表，和别处的"不认识的值给空列表"一致。
- 各列表：
  - 设备：`category`、`location`、`custodian`、`idle=1`（现在没有进行中的预约）；排序 `code`、`calibration_due`。
  - 试件：`material`、`location`、`defects_public`；排序 `code`。
  - 耗材：新加 `category` 字段（迁移 `inventory/0004`）；筛选 `category`、`location`；排序 `name`、`stock`、`nearest_expiry_on`（还有库存的批次里最早的有效期，子查询）。
  - 采购：`fund`、`owner`；排序 `submitted_at`、`total_amount`（合计按子查询算，搜索的联表不会把它乘倍）。
  - 经费：`owner`。
  - 报销：`search`（说明、报销人、编号）、排序 `occurred_on`、`amount`；列表、统计、导出都走 `filter_queryset`，合计一致。
  - 组会：`search`（标题、纪要、议程的汇报内容和汇报人）。
  - 成果：`has_fulltext`；排序 `date`。
  - 实验 / 处理记录、数据集、周报、知识库、成员：按下表排序。导出（采购、报销、成果）带 `ordering` 时按同样顺序。

  | 页面 | 可排序的列 |
  |---|---|
  | 实验记录 | 日期、更新时间 |
  | 处理记录 | 更新时间（没有日期字段） |
  | 数据集 | 更新时间、总大小 |
  | 周报 | 周一日期、提交时间 |
  | 知识库 | 更新时间 |
  | 成员 | 姓名、入学年份 |

- 填写提示 `GET /api/suggestions/<字段>/?search=`（`workbench/suggestions.py`）：
  - 白名单字段：设备类别和位置、试件材料和位置、耗材分类、位置和单位、研究方向、成果出处、知识库标签。其余 404。
  - 返回本组这一列已有的值，用得多的在前，最多 20 个，原样返回。标签是数组，在 Python 里计数（一个组的文档不多）。

### 前端

- `useLiveSearch(filters)`：输入停 300 ms 写进 `filters.search`；`@change` 让回车立刻生效。Element Plus 的输入框在输入法组字时不更新模型，拼音没选字前不搜。14 个列表都换成它，组会、报销加了搜索框。
- `usePagedList` 多给一个 `sort`：表格 `@sort-change="sort"`，列的 `prop` 就是服务器的排序名，`sortable="custom"`。
- `useRemoteOptions(fetch)`：下拉打开时列最近 20 条，输入时按 `?search=` 去服务器查（el-select 自带 300 ms 等待）。从早先搜索里选中的项记在一张表里，换了搜索词标签名也不丢。替换了实验、处理、周报里选数据集、记录、试件的下拉，以及报销、设备、入库里选采购申请的下拉；选成员、项目、经费的下拉不换（一个组不会超过 100）。
- 联想：表单里的自由文本框换成 `el-autocomplete :fetch-suggestions="suggest(字段)"`，知识库标签的 `allow-create` 下拉列出候选；筛选下拉用 `useSuggestions(字段)`，写成 `filterable remote`。运维的账号页不提示（运维不属于任何课题组）。
- 附件：`AttachmentList` 上传中用 `useUnsavedGuard` 拦离开；上传函数报告进度时显示进度条。组会附件改走数据集的 `uploadForm`（XMLHttpRequest），所以有进度。
- 任务看板加"负责人""里程碑"下拉，"只看我的"优先。

## Alternatives considered

- **前端在当前页内排序**：不用改后端；但只排了这一页的 20 条，翻页后顺序是错的。
- **给每张表加一列存编号**：搜索可以直接 `icontains`；但编号由年份和行号算出，存一份就要处理一致性和迁移，拆编号查行号更简单。
- **下拉一次取全部（不分页）**：代码最少；但数据集、采购申请会一直增长，几年后下拉会很慢。
- **联想值做成管理员维护的字典表**：最规整；但要多一套维护页面，issue 要的只是"提示用过的写法"。
- **耗材不加分类字段、只做位置筛选**：不用迁移；但 issue 要按分类筛，耗材多了以后只按名称很难找。加一个可空的文本字段，代价是一次迁移。

## Consequences

- 测试：
  - `core/tests/test_list_filters.py`：每个新筛选和排序的结果、编号搜索（含别人的、外组的编号搜不到）、报销统计与列表同一个搜索。
  - `workbench/tests/test_suggestions.py`：按用量排序、外组隔离、标签、未知字段 404、NUL 400。
  - `core/tests/test_odd_input.py` 加了新参数的非法值；探测脚本把新参数也试了一遍，没有 500。
  - 前端 `useLiveSearch.test.ts`：停手 300 ms 才生效、离开页面丢弃；远程下拉保留早先选中项的标签。
- 浏览器验证清单：`.claude/skills/verify-lab/features/lists.md`。
- 搜索即时生效会让请求变多：停手才发，`usePagedList` 只用最后一次的结果。
- 排序在手机上不可用（手机上表格是卡片，没有表头）。
- 设备表单（`EquipmentFormDialog.vue`）只是把两个输入框换成联想框、采购申请下拉换成远程搜索，打开时记值、只提交改了的字段、带 `status_seen` 都没变；设备模型检查的同步点随后更新。
