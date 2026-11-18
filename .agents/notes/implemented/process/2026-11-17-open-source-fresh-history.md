# Agent Note: 开源发布：公开仓库从一条初始提交开始，内部历史只留在本机

Status: implemented

## Problem

2026-11-17 用户决定开源（MIT），仓库 `github.com/cacdcaecawae/lab-management-platform`（公开）。开源之后可以像 sub2api 那样发版、自动构建镜像、在平台里提示新版本，后续另写方案。

发布前检查了当时的 114 条提交和全部文件：

- 每条提交的作者都是本人的真名和 QQ 邮箱，公开即暴露。
- 一个测试账号用了导师的姓（"赵老师"）。
- `.claude/skills/write-notes-like-deepseek/` 改编自 DeepSeek Harness（MIT），没有附它的版权声明。
- 仓库没有许可证文件。
- 没有提交过 `.env`、密钥、数据库文件，也没查到学校名、邮箱、手机号或会议纪要里的人名和金额。开发手册和会议纪要在仓库外面。

仓库一旦公开，推上去的历史就收不回来。

## Decision

- **公开仓库只有当前代码**：
  - 先用 `git clone --mirror` 把内部历史备份到同级目录 `lab-management-platform-history.git`，不设远程，核对提交数和分支。
  - 原目录的 `.git` 移走（不删），重新 `git init`，按原来的被跟踪文件清单加入，作者设为 GitHub 用户名和 `109055297+cacdcaecawae@users.noreply.github.com`，提交一条初始提交。核对新提交的文件树和内部历史最后一条完全一致。
  - 第二条提交只把设备模型检查的 `SYNC` 改成初始提交，代码没有变化，模型的确认仍然成立。
  - 只推送 `main`。
- **发布前的清理在内部历史上先做完**：根目录加 MIT 许可证；Skill 目录加 DeepSeek Harness 的版权声明；测试账号改为"导师乙"（`t_adv2`）；README 写明许可证。
- **旧提交编号不逐条改写**：笔记和功能清单里 2026-11-17 及以前的编号指内部历史，在开发计划开头说明一句。

## Alternatives considered

- **改写全部提交的作者后整段推送**：保留开发过程，`git blame` 能看到每一行的来历。但所有提交编号都会变，笔记里几十处引用要按对照表改写；而且历史里删掉过的内容也会一起公开，没法逐条审。为什么这样改、放弃了什么，已经写在 `.agents/notes/` 里，跟着公开，丢掉的主要是逐次改动的过程。
- **保持私有仓库（Gitee / 学校 GitLab）**：最安全；但用户要开源，而且公开仓库才能免费用 GitHub 的自动构建和镜像仓库。
- **直接删除旧的 `.git`**：省一步；但万一镜像备份不完整就无法恢复，移走更稳妥。

## Consequences

- 公开仓库里看不到 2026-11-17 以前的提交；笔记里引用的旧编号要到本机的 `lab-management-platform-history.git` 里查（`git --git-dir=../lab-management-platform-history.git show <编号>`）。
- 内部历史只有本机一份，需要用户另存到移动硬盘或私人网盘。
- 以后每条推送的提交都是公开的。本地提交的作者用匿名邮箱（仓库级 `git config`），推送前照旧不提交 `.env`、证据文件和实验数据。
- 重建当天不能有别的会话在这个仓库里提交，否则它们的改动接不上新历史。
