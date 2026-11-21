# 界面规范

改前端页面之前先读这份文件。颜色、字号这些取值写在 `frontend/src/styles/theme.css`，页面骨架用 `frontend/src/components/` 里的共用组件；页面里不写死颜色和字号，不自己拼弹窗、工具栏和页头。`frontend/src/components/components.test.ts` 里的源码检查会拦住常见的走样。

方向是类苹果风：浅灰底、白卡片、一种蓝色。看的人大多在 Windows 上用微软雅黑，天天对着表格和表单，所以清楚、好认排在好看前面。

## 颜色

| 用途 | 变量 | 取值 |
|---|---|---|
| 页面底色 | `--lab-bg` | `#f5f5f7` |
| 侧栏 | `--lab-bg-side` | `#ebebef` |
| 卡片、表格、弹窗、输入框 | `--lab-bg-card` | `#ffffff` |
| 悬停 | `--lab-bg-hover` | `#e8e8ed` |
| 选中（菜单、切换按钮） | `--lab-selected-bg` / `--lab-selected-fg` | `#e1ecfb` / `#0066cc` |
| 主按钮、自己的预约 | `--el-color-primary` | `#0071e3` |
| 链接 | `--lab-link` | `#0066cc` |
| 分隔线、卡片描边 | `--lab-border` | `#e5e5ea` |
| 输入框边框 | `--el-border-color` | `#c7c7cc` |
| 成功 / 警告 / 危险 | `--el-color-success` / `-warning` / `-danger` | `#1f7a35` / `#a34a00` / `#c4001a` |

- 蓝色只用在主按钮、链接、选中的菜单和自己的预约上。其他按钮都是白底灰边。
- 状态用 `StatusTag`（带圆点的胶囊标签），不要自己写 `el-tag` 配颜色，也不要只靠颜色区分状态。
- 毛玻璃只用在顶栏（半透明加模糊）。表格、表单、日历、弹窗都是不透明的白底；系统设置了"减少透明度"或"高对比度"时，顶栏也换成实色。

## 文字

- 字体：`-apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif`；编号、哈希用等宽字体（`.code`、`.mono`）。
- 字号：正文 14px；表头、辅助说明、时间 13px；页头标题、弹窗标题 16px；中文不小于 13px。
- 颜色只有三档，在白底上对比度都不低于 4.5:1：

  | 档 | 变量 | 取值 | 用在 |
  |---|---|---|---|
  | 主要 | `--lab-text` | `#1d1d1f` | 正文、标题、表格内容 |
  | 常规 | `--lab-text-2` | `#3a3a3c` | 表单标签、表头 |
  | 次要 | `--lab-text-3` | `#6e6e73` | 说明、时间、输入框占位、空状态 |

## 形状和层次

- 圆角：输入框、按钮 8px；卡片 12px；弹窗 14px；复选框 4px；状态标签是胶囊形。
- 卡片：白底、`--lab-border` 描边、很淡的阴影，浮在灰底上。一页的内容放在一张或几张卡片里，不直接铺在灰底上。
- 间距只用 4 的倍数：控件之间 8px，表单行之间 12–16px，卡片内边距 20px，卡片之间 16px，内容区四周 24px。

## 布局

- 左侧菜单固定宽度，右侧内容区铺满剩下的宽度，不居中、不限最大宽度。宽表格由列宽撑开，不靠整页留白。
- 顶栏只放当前页面名、搜索、通知和账号。

## 页面骨架

### 列表页

一张卡片：上面是 `PageToolbar`，下面是表格和分页。

```vue
<PageToolbar>
  <el-input ... />            <!-- 筛选放默认插槽，左侧，放不下就换行 -->
  <el-select ... />
  <template #actions>          <!-- 按钮固定在右上角，不跟着换行 -->
    <el-button>打印标签</el-button>
    <el-button type="primary">新建设备</el-button>
  </template>
</PageToolbar>
```

- 右侧放主按钮和最多两个次要按钮，主按钮在最右。同类操作合成一个下拉（例如"导出"下面两种导出）；菜单里已有入口的页面不再放跳转按钮。
- 表格里能点开的名称、编号用链接（`RouterLink`），是蓝色的。
- 表格加载时用 `v-loading`，不要整页转圈。

### 详情页、编辑页

一张卡片，卡片头放 `PageHeader`：左边是返回和标题（状态标签跟在标题后面），右边是这一页的所有按钮，主按钮在最右。

```vue
<el-card class="card">
  <template #header>
    <PageHeader :back="{ name: 'experiments' }" :title="record ? record.code : '新建实验记录'">
      <template #tags><StatusTag :status="record.status" /></template>
      <el-button>修改历史</el-button>
      <el-button>保存草稿</el-button>
      <el-button type="primary">提交</el-button>
    </PageHeader>
  </template>
  ...
</el-card>
```

- 页面下面不再放第二组保存按钮。唯一的例外是审批：审批意见框和"退回 / 通过"放在页面最后的一张卡片里，看完申请再审批。
- 页面里的标签页（进展、任务、里程碑）放在卡片里。

### 弹窗

带表单的弹窗都用 `FormDialog`，只展示内容的弹窗（成果统计、本组存储用量）才直接用 `el-dialog`。

```vue
<FormDialog v-model="open" :title="editing ? '编辑设备' : '新建设备'" :loading="saving" @submit="save">
  <div class="form-grid">
    <el-form-item label="设备编号" required>...</el-form-item>
    <el-form-item label="名称" required>...</el-form-item>
    <el-form-item label="备注" class="span-all">...</el-form-item>
  </div>
</FormDialog>
```

- 宽度只有三档：`size="sm"` 460px（一两个字段，例如重置密码）、`md` 620px（默认）、`lg` 800px（字段多或有明细行）。
- 底部右下角固定是"取消"和主按钮；主按钮默认叫"保存"。删除这类危险操作放在底部左边（`#extra` 插槽）。只读时（`readonly`）表单变灰，只留"关闭"。
- 表单外的内容（创建人一行、全文上传、附件）放 `#before` / `#after` 插槽，它们不会跟着表单变灰。
- 关闭按钮的文字可以用 `cancel-text` 改（预约详情里叫"关闭"，免得和"取消预约"混淆）；主按钮后面还要别的按钮时放 `#actions` 插槽。

### 表单

- 标签在字段上方（`label-position="top"`）。
- 多列用 `.form-grid`：列宽至少 180px，每行的列都对齐，窄屏自动变一列；长字段（说明、备注、多选）加 `.span-all` 占满一行，稍长的加 `.span-2`。不用 `el-row` / `el-col` 排表单。
- 占满整页的表单（实验记录、周报这类编辑页）加 `.form-page`，最宽 960px，不跟着屏幕拉得很长。
- 必填字段加 `required`（显示红色星号）。字段错误显示在字段下面（`useFieldErrors` 的 `fe`），对不上字段的错误放在表单最后的红色提示里。

### 预约日历

左栏是小月历（点哪天跳到哪天）和设备列表（每台设备一个颜色，勾选的才显示），右边是日历。日历的翻页、今天、月 / 周 / 日切换用站内按钮，和筛选放在同一个工具栏；日历不在框里滚动，一天 24 小时都在页面上。

## 用词

| 场合 | 用 | 不用 |
|---|---|---|
| 新建按钮、新建弹窗标题 | 新建设备、新建耗材 | 新增、创建、添加（"添加一行""添加缺陷"这类往表单里加一行的可以用） |
| 登记已经发生的事 | 登记报销、登记成果、登记归还 | |
| 弹窗主按钮 | 保存 | 创建、确定；有专门动作时用动作本身：预约、借用、重置、登记 |
| 草稿 | 保存草稿 | 保存 |
| 空列表 | 暂无文件、暂无组会记录 | 还没有……；筛选后为空用"没有符合条件的……" |
| 只读弹窗的关闭 | 关闭 | 取消 |

## 状态

- **空**：表格用 `empty-text`，卡片里用 `el-empty`，文字按上表。
- **加载**：表格、卡片用 `v-loading`。
- **出错**：接口错误用 `showError` / `showActionError` 弹出提示；表单错误按"表单"一节显示；整页打不开用 `el-result` 加一个返回按钮。
- **确认**：删除、撤回、关闭注册链接这类不能撤销的操作先用 `ElMessageBox.confirm` 确认，说清楚会发生什么。

## 检查

`frontend/src/components/components.test.ts` 读 `src/modules/` 的源码，下面这些会让测试失败：

- `<el-dialog>` 里有表单（应该用 `FormDialog`）；
- 用 `<el-row` / `<el-col` 排表单；
- 自己拼工具栏（`class="page-toolbar"`）或页头（`<el-page-header`）；
- 按钮或标题里出现"新增"。
