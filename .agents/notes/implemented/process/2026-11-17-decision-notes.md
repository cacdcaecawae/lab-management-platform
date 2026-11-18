# Agent Note: 技术决策改用 write-notes-like-deepseek 笔记记录

Status: implemented

## 问题

第一期两天里积累了 27 条技术决策（原 D1–D27），都记在 `docs/decisions.md` 的一张表里，每条一行"决策 + 原因"。

- 放弃了哪些方案、什么情况下要重新评估，没有固定位置，混在"原因"里，到第二期容易漏掉（如 [设备字段](../architecture/2026-11-16-equipment-as-text.md)、[文件上传](../architecture/2026-11-16-file-upload-and-storage.md)）。
- 决策之间的关系看不出来；被取代的决策只能在表里划掉（原 D22、D23），理由也跟着丢了。
- `docs/*` 是公共文件，只有主代理能改；子代理在并行开发中做的决策只能写在交付说明里。

## 决策

- 使用 [write-notes-like-deepseek](https://github.com/czm15053/write-notes-like-deepseek)（MIT 许可）。Skill 复制在 `.claude/skills/write-notes-like-deepseek/`，取自原仓库提交 `72573a5`（2026-10-18）；笔记在 `.agents/notes/`。
- 原 D1–D27 合并为 16 篇 `implemented` 笔记，标题保留原编号；被取代的 D22、D23、D24 并入取代它们的笔记，写在"曾考虑的替代方案"里。`docs/decisions.md` 只留指向说明。
- 规则写在仓库根目录的 `AGENTS.md`（`CLAUDE.md` 引用它）；子代理规则写在 `docs/agent-tasks.md` 共同规则 9。
- 校验（目录结构、格式、归档封印）写进 `scripts/check.sh`，直接用 `node` 运行 Skill 里的 `.ts` 脚本，不新增依赖。
- 决策看板按需生成，`board.html` 不入库。

## 曾考虑的替代方案

- **保留 `docs/decisions.md`，加一列"退出条件"**：改动最小；但仍然是一张表，被放弃的方案和决策之间的关联还是没有结构，也没有看板。
- **按 Skill 默认用 `npx tsx` 运行脚本**：对 Node 版本要求更低；但每次要联网下载 tsx。Node 22.18 起可以直接运行 `.ts`。

## 后果

- 收益：每条决策一个文件，子代理并行写笔记不会冲突；看板汇总关键决策、被放弃的方案和时间线。
- 代价：每条决策要写一篇短文，不再是一行；本地 Node 需要 22.18 以上。
- Skill 是复制进来的，不会自动更新；升级时从原仓库重新复制，并跑一遍 `scripts/check.sh` 里的笔记校验。
