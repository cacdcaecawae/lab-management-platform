# Agent Note: 一键安装：一条命令装好最新正式版本，并补上漏洞报告和依赖安全更新

Status: implemented

## Problem

仓库开源以后，别人或我们自己换一台新电脑部署，只有两条路：

- `scripts/trial.ps1`：只能在 Windows 上跑，从源码构建，只监听本机，是给开发者试用的。
- README 的手动步骤：复制 `.env` 模板，自己生成并填写密钥和密码；只有 HTTP 时还要记得把 `DJANGO_SECURE_COOKIES` 改成 0，否则登录不了；再单独运行建运维账号的命令。

用户 2026-11-19 看了 sub2api 的部署方式，要求后续的部署、维护和更新尽量参考这类开源项目，确认"改成这个形式"。sub2api 用 Docker 时是一条 `curl | bash`：下载 compose 文件和模板，生成随机密钥，写好 `.env`；第一次启动自动建管理员。同时，开源项目通常有私下报告漏洞的入口、依赖的自动安全更新，以及写明升级方法的发布说明，这三样我们也没有。

## Decision

- **`scripts/install.sh`**，用法 `curl -fsSL https://raw.githubusercontent.com/cacdcaecawae/lab-management-platform/main/scripts/install.sh | bash`，可加 `--host`、`--port`、`--dir`：
  - 检查 bash 4 以上、git、Docker 和 compose 插件；在 Git Bash 里直接拒绝，提示到 WSL 里运行（服务器脚本里带容器路径的参数会被 Git Bash 改写）。
  - `git clone` 后切到最新的 `vX.Y.Z` 标签，选法和 `update.sh` 相同。在已有的 clone 里运行，就装在这份 clone 里。
  - 从 `infra/server.env.example` 生成 `.env`：密钥、数据库密码、备份密码各取 32 字节随机数；文件权限 600；`DJANGO_SECURE_COOKIES=0`。模板缺少要填的项时报错，不写半份配置。设了 `IMAGE_PREFIX`（国内镜像仓库）就写进 `.env`，以后更新也用它。
  - 不带 `--host` 时，只监听 `127.0.0.1`，允许的主机和 CSRF 来源只有 `localhost`、`127.0.0.1`。带 `--host` 时监听所有网卡，并把这个地址加进去。端口是 80 时，来源地址不带端口号。
  - 备份仓库放在安装目录旁边的 `<目录>-backup`，用 `backup.sh --init` 初始化。这样 `update.sh` 第一次更新时，就有地方做更新前备份。
  - 用 `server-env.sh` 的 `dc` 和 `healthy` 启动并检查网站；用 `manage.py shell` 从标准输入建超级用户 `ops`，密码不出现在任何命令行里。打印网址、一次性密码、更新命令和每日备份的 crontab 行；不打印数据库密码和密钥。
  - **不覆盖任何东西**：目录已经装过（有 `.env`）、备份目录已存在、这台机器上已经有同一个 Compose 项目的数据卷，都直接停下。还没启动就失败时，删掉本次生成的 `.env` 和备份目录，可以直接重跑；启动后才失败时保留现场，打印查看日志和从头重装的命令。
  - 整个脚本包在 `main` 里：从管道读入时要先读完再执行；`git checkout` 也可能在运行中替换这个文件。
- 发布说明（`release.yml`）在自动生成的 PR 列表上方，固定写新安装和升级的命令。
- `SECURITY.md` 说明怎么私下报告漏洞。仓库打开了 GitHub 的私密漏洞报告、Dependabot 漏洞提醒和 Dependabot 安全更新。
- 更新方式不变：网页提示新版本，服务器上运行 `scripts/update.sh`。

## Alternatives considered

- **像 sub2api 那样只下载 compose 文件和模板，不 clone 仓库** — 下载的东西少，也不用装 git。但我们的 `update.sh` 要靠 Git 标签切换部署文件，备份、恢复、HTTPS、NAS 的脚本和配置也都在仓库里；不 clone，这些就得另外打包发布。
- **镜像用 `latest` 标签** — 新装时永远拿最新的。但 `update.sh` 要知道"从哪个版本升到哪个版本"，才能比较迁移、失败时退回；用 `latest` 以后就说不清现在跑的是哪个版本。所以安装时写死具体的版本号。
- **第一次启动时由后端自动建管理员（sub2api 的做法）** — 不依赖安装脚本，手动安装也能用。但要在后端加启动逻辑和环境变量，还要防止它在已有数据上重复建账号。现在建账号只在安装脚本里做一次，手动安装仍用 `createsuperuser`。
- **再写一个 PowerShell 版** — Windows 用户不用装 WSL。但 `update.sh`、`backup.sh`、`restore.sh` 都是 bash 写的，装好以后照样要在 bash 里维护；只做一个安装用的 PowerShell 版，后面的维护就接不上。
- **把数据库密码等打印出来（sub2api 会打印）** — 方便抄下来。但会留在终端的滚动记录和日志里。它们都在 `.env` 里，只打印 `.env` 的位置。

## Consequences

- **收益**：新电脑上一条命令就能装好最新正式版本；用 HTTP 能直接登录；第一次更新前已经有备份仓库。别人发现漏洞时有不公开的报告入口；依赖出了漏洞，Dependabot 会自动开 PR。
- **代价与已知上限**：
  - 要先发过正式版本，并且 ghcr.io 上的镜像是 Public，否则只能拉取失败。
  - 备份默认和网站在同一块硬盘上，只能防误删和软件出错，防不了硬盘坏掉；有第二块硬盘或 NAS 后要按 README 换过去。
  - 备份仓库里的文件属于 root（restic 容器的用户），删掉或移走要用 sudo。
  - `--host` 只接受主机名和 IPv4，不接受 IPv6 地址。
  - Mac 要自己装 bash 4 以上；这次没有在 Mac 上试过。
  - 同一台机器只能装一套：Compose 项目名来自 `infra/` 目录名，第二套会被数据卷检查拦下。

## Verification

- `scripts/tests/test_install.py` 有 8 个用例，用模拟的 git 和 docker 运行真实脚本，覆盖：新装的 `.env` 内容和权限、密钥互不相同、密码不出现在命令行和输出里、选中最新的正式标签、`--host` 和 80 端口、保留 `IMAGE_PREFIX`、已安装目录不动、在 clone 里运行、启动前失败不留东西、启动后失败保留现场、参数错误或 Docker 没开时什么都不做。由 `backend/tests/test_server_scripts.py` 纳入 Linux CI。在 WSL Ubuntu 里，`scripts/tests` 下的 55 个测试全部通过。
- 2026-11-19 在 WSL Ubuntu（Docker Desktop 29.3.1）上做了一次真实安装：用临时仓库造了标签 `v9.9.9`，镜像用本机构建的，把脚本用管道喂给 bash 运行。安装成功，`.env` 权限 600；Windows 这边能打开网站；用打印出的一次性密码登录 `ops`，接口返回必须改密码，改密码前系统管理返回 403、改完返回 200，旧密码随后被拒绝。之后 `backup.sh` 做了一次备份；再次运行安装脚本被拒绝；临时起一个本地镜像仓库发布 `v9.9.10` 后，`update.sh` 停站备份、切换、检查都通过，backend、web 都运行新版本镜像。测试环境、镜像标签和临时仓库都已清理。
- 没有验证：从 ghcr.io 真实拉取（还没发过版本）、Mac、`--host` 下别的电脑访问、发布说明的实际渲染（要等第一次发版）。
