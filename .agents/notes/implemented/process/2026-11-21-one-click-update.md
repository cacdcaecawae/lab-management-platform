# Agent Note: 网页一键更新：页面上点"立即更新"，服务器上的更新助手运行 update.sh

Status: implemented

## Problem

用户把 v0.1.2 更新到 v0.1.3 时，在"系统管理 → 版本"只看到一条命令，要自己登录服务器、找到安装目录再敲。他用过的 sub2api 是点"立即更新"，看着进度条走完。

- [发版、更新与备份](./2026-11-18-release-update-backup.md)当时把"网页一键更新"列为不做，理由是：给后端 `docker.sock` 等于把整台服务器交给 Web 应用，而且备份、退回都要在网页里重写一遍。这一条用户没有单独确认过，当时只说了"直接继续迭代"。
- sub2api 的做法（`update_service.go`、`restart.go`）是在容器里下载新的二进制、原子替换自己再退出，由 `restart: unless-stopped` 拉起同一个容器。这只适用于单文件程序。我们有 backend、web 两个镜像，nginx 配置和 Compose 文件每版也可能变，后端在自己的容器里换文件改不到这些。
- 版本检查缓存 6 小时，刚发版时页面很久都不提示。

## Decision

执行更新的进程在宿主机上，任何容器都不挂 `docker.sock`。备份、核对、退回仍然只有 `scripts/update.sh` 这一份。

- **更新助手 `scripts/update-agent.sh`**：
  - 当前用户的 crontab 每分钟启动一次。拿到 `run/update/agent.lock`（`flock -n`）的那一份常驻，每 2 秒看一次有没有请求；拿不到锁的立即退出。
  - 看到请求就运行 `update.sh`，跑完退出。`git checkout` 可能已经换掉了脚本文件，由 cron 在一分钟内启动新版本里的那一份。整个脚本包在 `main` 里，和 `update.sh` 一样。
  - 不需要 sudo。
- **请求**：目录 `run/update/request/` 随代码入库，bind mount 进 backend，可写。
  - `POST /api/system/update/` 只允许运维账号调用，核对三件事：目标就是缓存里的最新正式版本，比当前版本新，助手在运行。核对通过后新建一个以版本号命名的空文件。
  - 助手只看文件名，用严格正则校验；不读内容，不跟随符号链接；看过的文件全部删除。`update.sh` 再按原规则核对一遍（正式标签、祖先关系、备份仓库）。
- **状态**：目录 `run/update/status/` 只有宿主机能写，backend 和 web 都是只读挂载。
  - `agent` 是心跳，每 30 秒写一次。backend 看到 90 秒内的心跳，页面才显示"立即更新"；否则照旧显示命令，并提示运行一次 `bash scripts/update-agent.sh --install`。
  - `status.json` 的内容是 `{state, step, target, started}`。更新期间 backend 停着，没法鉴权，所以由 Nginx 以 `/update-status.json` 直接提供，不需要登录。因此只放步骤号，不放日志、路径和快照号；用 `expires -1`，保留 server 级的安全头。日志写在宿主机的 `run/update/update.log`。
- **权限**：助手启动时把 `run/update` 设为 700，挡住服务器上的其他用户；`request/` 设为 1777，因为 backend 容器是 uid 1000，宿主用户可能是 root 或别的 uid，粘滞位下目录属主仍能删除文件；`status/` 设为 755。
- **Compose 文件**：以正在运行的 backend 容器（不含一次性容器）的 `com.docker.compose.project.config_files` 和 `project` 标签为准，由 `scripts/server-env.sh` 的 `running_stack` 读取，备份、恢复、更新和助手都用它。cron 的环境里没有运维 shell 里导出的 HTTPS、NAS 覆盖文件，不这样取的话，更新后站点会丢掉 HTTPS 或 NAS，夜间备份会备到旧的本地卷。
  - 读 backend 而不是 web：HTTPS、NAS 两份覆盖文件都改 backend，打开其中一份时 Compose 会重建 backend、换上新标签。web 只被 HTTPS 改，打开 NAS 时不重建，标签停在装机时。v0.1.4、v0.1.5 读的是 web，在 WSL 测试站上实测：打开 NAS 后，助手取到的只有基础文件，按它 `up -d` 会让后端的 `/data` 从 NAS 换回本地卷。
  - 显式给了 `COMPOSE_FILE`、又和运行中的不一致时（相对路径按仓库根目录展开后比较），脚本在做任何事之前退出。
- **`update.sh` 的改动**：
  - 停站备份时只停 backend。所有写入都经过 backend，数据安全上和原来停两个服务等价；web 留着显示进度。
  - 每次启动后执行 `restart web`。Nginx 在启动时解析 backend 的地址，backend 重启后地址可能变了。
  - 失败后停站也只停 backend，页面还能显示结果。
  - 由助手运行时（设置了 `LAB_UPDATE_STATUS`）写入第 1–3 步；在命令行运行时不写。
- **页面**：
  - 点按钮先弹确认框，说明会停站，以及失败时怎么退回。
  - 进度条依次显示：等待服务器开始、拉取新版本、停止网站并备份、启动新版本并检查。忽略 `started` 早于本次请求的旧状态。
  - 完成后等 `/api/system/version/` 报出新版本，再刷新页面。
  - 失败时，能连上后端就显示"网站仍是 vX"，连不上就显示"网站已停止，需要到服务器上处理"。
- **安装**：`install.sh` 直接把每日备份和更新助手两行写进 crontab，同一目录、同一脚本已有的行不重复写。已经装好的站点运行一次 `bash scripts/update-agent.sh --install`。
- **版本检查**：缓存 1 小时，失败时 10 分钟。版本页加了"重新检查"（`?refresh=1`）。

## Alternatives considered

- **后端容器挂 `docker.sock`，直接执行更新**：做法最直接，但 Django 一旦被攻破，就等于拿到了宿主机 root。
- **单独一个挂 `docker.sock` 和安装目录的更新助手容器**（最初的方案）：同样拥有 root 权限，而且现有脚本放进容器后会出错。Fable 评审时指出了以下几处，已按代码逐一核对：
  - `backup.sh` 先 `mktemp -d`，再用 `-v "$tmp:/dump"` 挂载。Docker 会按宿主机路径去挂，备份里就没有数据库导出了。
  - `server-env.sh` 用 `realpath`、`mountpoint` 检查备份挂载点，检查的是宿主机路径。
  - 覆盖文件里的相对路径也按宿主机解析。
- **宿主机 cron 每分钟去数据库查请求**（Fable 的第一版建议）：不需要新增挂载，但点完最多要等一分钟才开始。如果改成每 2 秒执行一次 `docker compose exec db psql`，开销又太大。最后选了常驻进程加文件。
- **systemd 的 path unit**：文件一出现就触发，比每 2 秒检查一次还快，也是 Linux 上的标准做法。但安装 systemd 单元需要 sudo，而现在的安装全程不用 sudo。
- **Watchtower 这类自动更新容器**：更新前不备份，迁移失败后不退回，部署文件也不跟着版本走。
- **保持只提示命令**：用户明确要按钮和进度条。没有运行助手的站点，页面仍然显示命令。

## Consequences

- 运维点"立即更新"后几秒内就开始更新，页面一路显示进度。
- 后端被攻破时，最多只能触发更新到 origin 上已有的、更高的正式版本（每个新版本停站一次），伪造不了公开的进度和心跳。
- 开销：cron 每分钟启动一次，拿不到锁立即退出；常驻进程每 2 秒一次文件检查，可以忽略。
- 第一次需要先用命令更新到带助手的版本，再运行一次 `--install`。没有 cron 的机器（部分 WSL、Docker Desktop）仍然显示命令。
- 更新途中刷新页面会丢掉进度视图（backend 停着，页面载不出来），更新完再打开就是新版本。
- 命令行更新和网页更新同时进行时没有互斥。
- 验证：
  - 后端测试：只有运维能请求；只能更新到最新且更新的版本，路径形式的目标被拒绝；助手没在运行时被拒绝；重复请求被拒绝。
  - 脚本测试：助手只接受版本号形式的文件名，不跟随符号链接，按运行中容器的 Compose 文件和项目执行，失败写入 `failed`，`--install` 不重复写入，已有的手写备份行不重复；`update.sh` 只停 backend 并重启 web，只有设置了 `LAB_UPDATE_STATUS` 时才写进度。
  - 前端测试：有助手时显示按钮，没有时显示命令；忽略早于本次请求的旧状态。
  - WSL 实测：用本地镜像仓库和测试标签 v0.9.0–v0.9.2，建一个独立测试站（项目 `labtest`，端口 8099），由 `--install` 写入的 cron 拉起助手。
    - 从页面把 v0.9.0 更新到 v0.9.1：进度条依次显示第 1、2、3 步；更新前的快照里有 `/dump` 和 `/data/files`；backend、web 都运行 v0.9.1；页面自动刷新后显示"已是最新版本"；"存储与备份"的"需处理"消失；一分钟内 cron 拉起新版本里的助手。
    - `/update-status.json` 返回 `no-cache` 和 `nosniff`，只有四个字段。
    - 失败路径：v0.9.2 的 backend 起不来，健康检查等满 3 分钟后，迁移没变，自动退回 v0.9.1，`restart web` 之后网站可以访问。页面显示"没有更新，网站仍是 v0.9.1"，`status.json` 为 `failed`。
    - 测试站、本地镜像仓库和临时写入的 crontab 行，验证完都已删除。
- 未验证：Docker Desktop 以外的 Linux 服务器上 uid 不同时的写入（逻辑由 1777 保证，没有实测）；HTTPS 和 NAS 覆盖文件下的网页更新；rootless Docker。
