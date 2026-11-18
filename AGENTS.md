# 给 AI 代理的项目约定

设计文档在 `docs/`。待开发的功能清单、每项的方案笔记和开发规则见 `docs/backlog.md`；第一期的子代理分工见 `docs/agent-tasks.md`。

## 浏览器验证

改了页面、接口行为或权限之后，按 `.claude/skills/verify-lab/SKILL.md` 在隔离实例里驱动浏览器验证，证据放在 `backend/var/verify-evidence/`。功能清单在 `.claude/skills/verify-lab/features/`，页面文字或流程变了，在同一次改动里更新对应文件。

## 并发模型检查

改了 `backend/equipment/` 的 `views.py`、`serializers.py`、`models.py`，`config/settings.py` 的数据库设置，或 `EquipmentFormDialog.vue` 之后，按 `.claude/skills/verify-equipment-tla/SKILL.md` 运行模型检查，确认模型仍然描述代码。

## 决策笔记

技术决策用 write-notes-like-deepseek 记录：Skill 在 `.claude/skills/write-notes-like-deepseek/`，笔记在 `.agents/notes/`。本节与 Skill 冲突时以本节为准。

- 非平凡改动（改行为、架构、跨文件契约、流程与工具、测试策略、数据或配置格式，或在几个方案之间做选择）：动手前在 `.agents/notes/proposed/<类别>/` 写方案笔记，用户确认后再改代码；做完在同一次提交里转为 `implemented/`。
- 错别字、格式、样式、不改行为的依赖补丁、单模块内一看就懂的修复，不写笔记。
- 动手前先查已有决策：`rg --hidden --glob '!.agents/notes/archived/**' "<关键词>" .agents/notes/`。原 D1–D27 的编号写在笔记标题里，例如搜 `原 D11`。
- 写完或改完笔记后运行校验（`scripts/check.sh` 也会运行）：

  ```bash
  node .claude/skills/write-notes-like-deepseek/scripts/verify-agent-note-tree.ts
  node .claude/skills/write-notes-like-deepseek/scripts/verify-agent-note-format.ts
  node .claude/skills/write-notes-like-deepseek/scripts/verify-archived-agent-notes.ts
  ```

- 生成决策看板（双击打开；`board.html` 不提交）：

  ```bash
  node .claude/skills/write-notes-like-deepseek/scripts/build-board.ts --bundle .agents/notes board.html "课题组管理平台 决策看板"
  ```
