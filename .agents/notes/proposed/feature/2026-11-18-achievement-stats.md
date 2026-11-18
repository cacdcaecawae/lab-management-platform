# Agent Note: 成果统计：按年份、类型、成员汇总

Status: proposed

## Problem

成果归档已经能按类型、年份、状态、成员筛选，也能导出清单（第四期）。但写年度总结、申报材料、导师考核时，要的往往是一张汇总表："2022–2026 年每年发表论文几篇、授权专利几项、获奖几项，每位成员各多少"。现在只能一类一类地筛，再数行数。

## Proposal

**接口**：`GET /api/achievements/stats/?year_from=&year_to=&status=`，本组全员可看，因为成果本来就是组内公开的。

- 返回 `by_year`：`[{year, paper, patent, award, software, total}]`；`by_member`：`[{user: UserBrief, paper, patent, award, software, total}]`。
- `status` 默认"已录用（含已发表）"，复用列表里那个快捷筛选的定义，不要重写一份。
- 只统计本组成员作者，外单位作者不计；一篇成果有多位本组作者时，每人各计 1，表格下方注明"合计一列按成果去重"。
- `?format=xlsx` 导出两张工作表，用 `core.export.xlsx_bytes`。

**前端**：成果归档页加"统计"标签页（或按钮），显示年份范围选择、两张表和"导出 Excel"。不引入图表库；数字旁边用纯 CSS 的横条表示相对大小。

## Alternatives considered

- **在现有导出里加汇总工作表**：不用新页面。但要先下载再打开才能看到，日常查看不方便。
- **引入 ECharts 画柱状图**：更好看。但要新增一个不小的依赖，只为一张图；纯 CSS 横条已经能看出多少。

## Acceptance criteria

- 后端测试：
  - 按年份、类型计数正确；
  - 多位作者时各计 1、合计去重；
  - 外单位作者不计；
  - 状态筛选与列表的快捷筛选一致（同一组数据，两边计数相同）；
  - 外组看不到；
  - Excel 内容与 JSON 一致。
- 浏览器：登记几条不同年份、类型的成果，统计表数字正确，导出文件能打开。更新 `features/achievements.md`。

## Risks

- "年份"用哪个日期：成果有日期字段，按它取年份；没有日期的成果计入"未填年份"一行，不能直接丢掉。
