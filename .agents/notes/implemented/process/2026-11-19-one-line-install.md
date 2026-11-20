# Agent Note: 一键安装：一条命令装好最新正式版本，并补上漏洞报告和依赖安全更新

Status: implemented

## Problem

仓库开源以后，别人或我们自己换一台新电脑部署，只有两条路：

- `scripts/trial.ps1`：只能在 Windows 上跑，从源码构建，只监听本机，是给开发者试用的。
- README 的手动步骤：复制 `.env` 模板，自己生成并填写密钥和密码；只有 HTTP 时还要记得把 `DJANGO_SECURE_COOKIES` 改成 0，否则登录不了；再单独运行建运维账号的命令。

用户 2026-11-19 看了 sub2api 的部署方式，要求后续的部署、维护和更新尽量参考这类开源项目，确认"改成这个形式"。sub2api 用 Docker 时是一条 `curl | bash`：下载 compose 文件和模板，生成随机密钥，写好 `.env`；第一次启动自动建管理员。同时，开源项目通常有私下报告漏洞的入口、依赖的自动安全更新，以及写明升级方法的发布说明，这三样我们也没有。

## Decision

- **`scripts/install.sh`**，用法 `curl -fsSL https://raw.githubusercontent.com/cacdcaecawae/lab-management-platform/main/scripts/install.sh | bash`，可加 `--host`、`--port`、`--dir`：
  - 检查 bash 4 以上、git、curl、Docker 和 compose 插件；在 Git Bash 里直接拒绝，提示到 WSL 里运行（服务器脚本里带容器路径的参数会被 Git Bash 改写）。
  - `git clone` 后，切到 **GitHub 上最新发布的正式 Release** 对应的标签（`releases/latest` 的 `tag_name`，不含草稿和预发布），而不是最大的标签：标签推送后发版流程才开始检查、构建和推送镜像，发版失败时标签也还在；Release 是在两个镜像都推送之后才创建的。在已有的 clone 里运行，就装在这份 clone 里。
  - 同一个安装目录同时只允许一个安装：用原子的 `mkdir .install-lock` 加锁，"是否已安装"等检查都在锁内再做一次。
  - 从 `infra/server.env.example` 生成 `.env`：先写进 `mktemp` 新建的私有文件（权限 600），再改名为 `.env`；密钥、数据库密码、备份密码各取 32 字节随机数；`DJANGO_SECURE_COOKIES=0`。模板缺少要填的项时报错。设了 `IMAGE_PREFIX`（国内镜像仓库）就写进 `.env`，以后更新也用它。
  - **只以 `.env` 为准**：写好后，把 `.env` 里出现的每个变量从当前 shell 里清掉，并清掉 `COMPOSE_PROJECT_NAME`、`COMPOSE_PROFILES`，固定 `COMPOSE_FILE=infra/docker-compose.prod.yml`、`ENV_FILE=.env`。Compose 会优先用 shell 里导出的变量；以后的 `update.sh` 只读 `.env`，安装时也必须一样。
  - 不带 `--host` 时，只监听 `127.0.0.1`，允许的主机和 CSRF 来源只有 `localhost`、`127.0.0.1`。带 `--host` 时监听所有网卡，并把这个地址加进去。端口是 80 时，来源地址不带端口号。
  - 查询这台机器上同一 Compose 项目的数据卷：查询失败就停，查到了也停。然后先 `pull` 这个版本的 backend、web 镜像，拉不到就停；再用 `backup.sh --init` 在安装目录旁边的 `<目录>-backup` 初始化备份仓库；最后 `up -d --no-build`，不会退回到用这份代码现场编译。
  - 健康检查通过后，还要核对两项：`compose ps` 显示 backend、web 运行的都是这个版本的镜像；`compose port web 80` 只有预期的地址（本机模式只有 `127.0.0.1:<端口>`，`--host` 模式是 `0.0.0.0` 或 `[::]`）。都对上才用 `manage.py shell` 从标准输入建超级用户 `ops`，密码不出现在任何命令行里。
  - 打印网址、一次性密码、更新命令和每日备份的 crontab 行；不打印数据库密码和密钥。打印的命令里，路径都用单引号括起，crontab 行里的 `%` 转义。
  - **只清理本次运行自己创建的东西**：记下这次建了 `.env`、临时文件、备份目录、锁中的哪几样，失败时只删这些。启动前失败，删掉本次生成的 `.env` 和备份目录，可以直接重跑；启动后才失败，保留现场，打印查看日志和从头重装的命令（这时的数据卷是本次新建的，安装前已确认没有旧数据）。目录已经装过、备份目录已存在、锁被别人持有时，什么都不删。
  - 整个脚本包在 `main` 里：从管道读入时要先读完再执行；`git checkout` 也可能在运行中替换这个文件。
- 发布说明（`release.yml`）在自动生成的 PR 列表上方，固定写新安装和升级的命令。
- `SECURITY.md` 说明怎么私下报告漏洞。仓库打开了 GitHub 的私密漏洞报告、Dependabot 漏洞提醒和 Dependabot 安全更新。
- 更新方式不变：网页提示新版本，服务器上运行 `scripts/update.sh`。

## Alternatives considered

- **像 sub2api 那样只下载 compose 文件和模板，不 clone 仓库** — 下载的东西少，也不用装 git。但我们的 `update.sh` 要靠 Git 标签切换部署文件，备份、恢复、HTTPS、NAS 的脚本和配置也都在仓库里；不 clone，这些就得另外打包发布。
- **装最大的 `vX.Y.Z` 标签（第一版的做法，和 `update.sh` 选版本的方式一样）** — 不用访问 GitHub API。但标签比镜像先出现，发版失败标签也不会消失；这时装上的版本要么拉不到镜像，要么落到 Compose 的本地编译上。
- **镜像用 `latest` 标签** — 新装时永远拿最新的。但 `update.sh` 要知道"从哪个版本升到哪个版本"，才能比较迁移、失败时退回；用 `latest` 以后就说不清现在跑的是哪个版本。所以安装时写死具体的版本号。
- **用 `flock` 加锁** — 进程退出时锁自动释放，不会因为被强行中断而留下锁。但 macOS 默认没有 `flock`；用 `mkdir` 加锁处处可用，被强行中断后要按提示手动删掉 `.install-lock`。
- **第一次启动时由后端自动建管理员（sub2api 的做法）** — 不依赖安装脚本，手动安装也能用。但要在后端加启动逻辑和环境变量，还要防止它在已有数据上重复建账号。现在建账号只在安装脚本里做一次，手动安装仍用 `createsuperuser`。
- **再写一个 PowerShell 版** — Windows 用户不用装 WSL。但 `update.sh`、`backup.sh`、`restore.sh` 都是 bash 写的，装好以后照样要在 bash 里维护；只做一个安装用的 PowerShell 版，后面的维护就接不上。
- **把数据库密码等打印出来（sub2api 会打印）** — 方便抄下来。但会留在终端的滚动记录和日志里。它们都在 `.env` 里，只打印 `.env` 的位置。

## Consequences

- **收益**：新电脑上一条命令就能装好最新正式版本；用 HTTP 能直接登录；第一次更新前已经有备份仓库。别人发现漏洞时有不公开的报告入口；依赖出了漏洞，Dependabot 会自动开 PR。
- **代价与已知上限**：
  - 要先发过正式版本，并且 ghcr.io 上的镜像是 Public，否则拉取失败、安装停下。
  - 安装要能访问 `api.github.com`（未登录时每个 IP 每小时 60 次）和 `raw.githubusercontent.com`；后者在国内常常打不开，这时先 `git clone` 再在仓库里运行 `bash scripts/install.sh`。
  - 备份默认和网站在同一块硬盘上，只能防误删和软件出错，防不了硬盘坏掉；有第二块硬盘或 NAS 后要按 README 换过去。
  - 备份仓库里的文件属于 root（restic 容器的用户），删掉或移走要用 sudo。
  - 安装被强行中断（`kill -9`、断电）会留下 `.install-lock`，要人工确认后删除。
  - `--host` 只接受主机名和 IPv4，不接受 IPv6 地址。
  - Mac 要自己装 bash 4 以上；没有在 Mac 上试过。
  - 同一台机器只能装一套：Compose 项目名来自 `infra/` 目录名，第二套会被数据卷检查拦下。
  - 安装脚本总是从 `main` 下载，装的却是最新发布的版本；改安装脚本时，要保证它对已发布的版本仍然可用。

## Verification

- `scripts/tests/test_install.py` 有 12 个用例，用模拟的 git、docker 和本地的 Release JSON 运行真实脚本，由 `backend/tests/test_server_scripts.py` 纳入 Linux CI。覆盖：
  - 新装的 `.env` 内容和权限，密钥互不相同，密码不出现在命令行和输出里，选中已发布的 Release 而不是更新的未发布标签，先拉镜像、再初始化备份、最后 `up --no-build`；
  - 导出的 `HTTP_PORT`、`APP_VERSION`、`COMPOSE_FILE`、`COMPOSE_PROJECT_NAME`、`ENV_FILE` 不影响启动；
  - 运行的镜像版本不对、监听地址不对时失败，并且不建运维账号；
  - `--host` 和 80 端口、保留 `IMAGE_PREFIX`、路径里有空格和单引号时打印的命令仍是正确的 shell 词；
  - 已安装目录不动，锁被别人持有时不删它的锁和临时文件，不沿用已有的固定名临时文件；
  - 已有数据卷、数据卷查询失败、拉不到镜像、没有已发布版本、Release 的标签不在仓库里，这几种都在启动前停下，什么都不留，也不提示 `down -v`；启动后失败保留现场；参数错误或 Docker 没开时什么都不做。
  2026-11-20 对提交 `94b53d0` 的外部审查提了这些问题；新测试在 `94b53d0` 的脚本上有 11 个失败，修复后 12 个全部通过。WSL Ubuntu 里 `scripts/tests` 全部通过。
- 2026-11-19、11-20 在 WSL Ubuntu（Docker Desktop 29.3.1）上做了真实安装。用临时仓库造了标签，镜像用本机构建的，脚本用管道喂给 bash 运行。
  - 第一轮（`94b53d0`）：只有标签 `v9.9.9`，镜像在本机。安装成功，`.env` 权限 600，从 Windows 能打开网站。用一次性密码登录 `ops` 后，接口要求先改密码；改之前系统管理返回 403，改完返回 200，旧密码随后被拒绝。`backup.sh` 备份成功；再次运行安装脚本被拒绝。临时起一个本地镜像仓库发布 `v9.9.10` 后，`update.sh` 停站备份、切换、检查都通过，backend、web 都运行新版本镜像。
  - 第二轮（修复后）：本地镜像仓库只有 `v9.9.9` 的镜像，临时仓库另有未发布的标签 `v9.9.10`，Release JSON 指向 `v9.9.9`。终端里先导出 `HTTP_PORT=18090` 和 `APP_VERSION=v0.9.0` 再安装：装的是 `v9.9.9`；网站只监听 `127.0.0.1:18093`，18090 没有打开；两个服务都运行 `v9.9.9` 的镜像；没有留下 `.install-lock`。把打印出的每日备份命令原样执行，备份成功。清掉后用 `--host lab.local --port 18094` 重装：Compose 报告的地址是 `0.0.0.0:18094`，检查通过。
  - 测试环境、镜像标签、临时镜像仓库和临时目录都已清理。
- 没有验证：从 ghcr.io 和真实 GitHub API 安装（还没发过版本）、Mac、`--host` 下别的电脑访问、发布说明的实际渲染（要等第一次发版）。
