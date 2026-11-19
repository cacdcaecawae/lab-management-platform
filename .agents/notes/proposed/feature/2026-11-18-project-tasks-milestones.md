# Agent Note: 项目任务看板与里程碑

Status: proposed

## Problem

开发手册第 11 节："任务看板、里程碑——先只做项目进展记录，看板以后再加。"现在项目页只有进展日志（`ProjectLog`）和"阶段"文本。谁在做什么、哪件事卡住了、下一个节点是什么时候，只能在组会上口头问。原型里有任务看板，组里也提过需要。

## Proposal

**模型**（`projects` app，新迁移）：

```
Milestone(project → Project CASCADE, title ≤200, due_date null, done_at null, created_at)
Task(project → Project CASCADE, title ≤200, description Text, assignee → User null PROTECT,
     status: todo 待办 | doing 进行中 | done 完成, milestone → Milestone null SET_NULL,
     due_date null, created_by → User PROTECT, created_at, updated_at, history)
```

**权限**（与项目的现有规则一致：项目和进展组内公开，管理员、导师和项目负责人能改）：

- 看：本组全员。
- 建任务、改任务：项目成员、项目负责人、管理员和导师。学生只能把负责人设为本项目成员。
- 删任务：创建人、项目负责人、管理员和导师。
- 里程碑的增删改：项目负责人、管理员和导师。
- 外组一律 404。

**接口**：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/projects/{id}/tasks/` | `?status=&assignee=&milestone=` |
| PATCH / DELETE | `/api/tasks/{id}/` | 改状态就是 PATCH `{status}` |
| GET / POST | `/api/projects/{id}/milestones/` | 返回时附上 `task_total`、`task_done` |
| PATCH / DELETE | `/api/milestones/{id}/` | 删除时，任务的里程碑置空 |

**前端**（项目详情页 `views/ProjectDetailView.vue`，如果前端已按模块迁移，则是 `modules/projects/`）：

- 新增标签页"任务"：三列看板（待办、进行中、完成），卡片显示标题、负责人、截止日期（过期标红）、所属里程碑。
- 卡片上用"→ 进行中""→ 完成""↩ 待办"按钮移动，不引入拖拽库；可以筛选"只看我的"。
- 新增标签页"里程碑"：按日期排列，显示进度（已完成任务数 / 总数）和是否完成。
- 工作台：`my.tasks`，我负责的、未完成的任务，截止日期早的在前，最多 20 条。

## Alternatives considered

- **接入现成的看板工具**（如 Focalboard、Plane）：功能全。但数据不和项目、成员打通，要再维护一套账号，和手册"不拼系统"的原则冲突。
- **前端拖拽（vuedraggable / SortableJS）**：操作直观。但要新增依赖，还要做列内排序的字段和并发处理；三列看板用按钮移动已经够用，手机上按钮也比拖拽好操作。
- **任务挂在里程碑下，不直接挂项目**：层级清楚。但很多小任务不属于任何里程碑，强制挂靠会让大家随手建一个"杂项"里程碑。

## Acceptance criteria

- 后端测试：
  - 每类操作各角色的权限（成员能建能改、非成员学生 403、外组 404）；
  - 负责人只能是本项目成员；
  - 删除里程碑后，任务保留、里程碑为空；
  - 里程碑的计数正确；
  - 任务的修改历史。
- 前端测试：看板分列正确；点"→ 进行中"后调用 PATCH `{status: 'doing'}`。
- 浏览器：项目成员建任务、移动、完成；非成员学生看得到但没有按钮；负责人建里程碑，进度随任务变化；工作台"我的任务"。新增功能文件 `features/project-tasks.md`。
- `docs/api-contract.md`、`docs/architecture.md`（权限表）同步更新。

## Risks

- 两个人同时移动同一张卡片，后提交的生效。这类冲突后果很小，不做版本号校验；修改历史能查到谁改的。
- 项目成员变动后，离开的人仍是某些任务的负责人。这些任务保留原样，在卡片上标"已不在项目中"，不自动改动。
