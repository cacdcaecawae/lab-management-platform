# 课题组管理平台

课题组内部使用的科研管理平台：成员与项目、实验记录、原始数据与处理记录、周报与反馈、设备预约与耗材、采购审批与报销统计、知识库、组会、成果归档，以及运维用的系统管理。设计文档见 `docs/`，技术决策见 `.agents/notes/`（写法见 `AGENTS.md`）。

技术栈：Vue 3 + TypeScript + Element Plus ｜ Django 5.2 LTS + DRF ｜ PostgreSQL ｜ Docker Compose。

许可证：[MIT](LICENSE)。`.claude/skills/write-notes-like-deepseek/` 改编自 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（MIT），见该目录下的 LICENSE。

## 一键安装

在装好 Docker（带 compose 插件）、git 和 curl 的电脑上，一条命令装好 GitHub 上最新发布的正式版本：

```bash
curl -fsSL https://raw.githubusercontent.com/cacdcaecawae/lab-management-platform/main/scripts/install.sh | bash
```

- 支持 Linux。Windows 在 WSL 里运行（Docker Desktop 打开 WSL 集成）。暂不支持 Mac：装好以后的更新和每日备份脚本在 Mac 上还不能运行。
- 要能访问 `api.github.com`（查最新发布的版本）和拉取镜像；在仓库里运行 `bash scripts/install.sh` 时也一样。
- 脚本依次：下载仓库并切到最新发布的版本 → 生成 `.env`（随机密钥和密码，只有本人能读，按 HTTP 配好）→ 拉取这个版本的镜像 → 在安装目录旁边建备份仓库 → 启动，核对运行的镜像和监听地址 → 新建运维账号 `ops`，打印一次性密码，第一次登录必须改。
- 端口、版本、数据库用户名等都以生成的 `.env` 和 Compose 文件里的默认值为准，终端里导出的同名变量（例如 `HTTP_PORT`、`APP_VERSION`、`POSTGRES_USER`）不起作用。
- 默认装在当前目录的 `lab-management-platform/`，只有这台电脑能打开 <http://localhost:8090>。参数加在 `bash -s --` 后面：

  ```bash
  curl -fsSL https://raw.githubusercontent.com/cacdcaecawae/lab-management-platform/main/scripts/install.sh | bash -s -- --host 192.168.1.20 --port 80 --dir /srv/lab-management-platform
  ```

  `--host` 让别的电脑用这个 IP 或域名访问，`--port` 改端口，`--dir` 改安装目录。已经 clone 了仓库的，在仓库里运行 `bash scripts/install.sh`，就装在这份仓库里；国内打不开 `raw.githubusercontent.com` 时也这样装。
- 装好后是 HTTP，只在内网或 VPN 里用；放到公网前，先按下文"正式域名 HTTPS"配好证书。
- 备份和网站在同一块硬盘上：换到第二块硬盘或 NAS 见下文"备份与恢复"。安装时已把每天备份和更新助手写进当前用户的 crontab（`crontab -l` 查看）。
- 更新：在"系统管理 → 版本"点"立即更新"，或者 `cd lab-management-platform && bash scripts/update.sh <新版本号>`，见下文"服务器部署"。国内拉不动 ghcr.io 时，安装前先 `export IMAGE_PREFIX=<镜像仓库地址>`，以后更新也会用它；postgres、restic 来自 Docker Hub，拉不到时给 Docker 配置镜像加速。
- Docker 上已经有 Compose 项目 `infra` 的数据卷或容器（同名的数据卷带不带标签都算，也可能属于别的应用，脚本不会动它们）、查不出有没有、目录已经装过、备份目录已存在、这台电脑的 Docker 上另一个安装正在进行（不论在哪个目录）时，脚本直接停下，不覆盖任何东西。安装被强行中断后，如果提示有另一个安装正在进行，确认没有在运行，再 `docker network rm lab-platform-install`。

## 本机试用（和服务器上同一套）

前置：装好 Docker Desktop 并启动。在仓库根目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 up      # 构建并启动，第一次要几分钟
powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 admin   # 新建运维账号：依次输入用户名、邮箱（可直接回车）、密码两遍
```

- 平台：<http://localhost:8090>；本机收件箱：<http://localhost:8025>，平台发出的每封邮件都能在这里看到。
- 第一次使用：
  1. 用运维账号登录，先改密码，之后进入"系统管理"。
  2. "邮件"页：SMTP 服务器填 `mailpit`，端口 `1025`，加密方式选"不加密"，账号填一个邮箱地址（例如 `lab@example.edu`，作为发件人），授权码随便填。点"保存"，再点"发送测试邮件"，到本机收件箱里查看；收到后打开"启用邮件"再保存。
  3. "课题组"页新建课题组；"账号"页开通管理员和导师。要收通知的人记得填邮箱。
  4. 管理员登录（首次登录要改密码），在"成员"里新建学生；学生登录后试用各项功能。
- 换成学校邮箱：按 [docs/mail-setup.md](docs/mail-setup.md) 在"系统管理 → 邮件"里填学校的 SMTP，发一封测试邮件就知道能不能用。
- `scripts\trial.ps1 down` 停止（数据保留）；`scripts\trial.ps1 reset` 删除全部试用数据，从头再来；`scripts\trial.ps1 logs` 看日志。
- 说明：
  - 只监听本机地址，同一网络里的其他电脑访问不到；只有 HTTP。
  - 数据库和上传的文件分别在 Docker 卷 `lab-trial_pgdata`、`lab-trial_labdata` 里。
  - 本机没有每周一的财务提醒定时任务，可以在"报销与统计 → 统计"里点"发送财务提醒"手动发送。
  - 8090 端口被占用时，把 `trial.env.local` 里的 `HTTP_PORT` 和 `DJANGO_CSRF_TRUSTED_ORIGINS` 两处端口一起改掉，再运行 `up`。

## 本地开发

前置：Docker、Python 3.12、Node.js 22.18+。

```bash
cp .env.example .env              # 按需修改
docker compose up -d db           # 只启动 PostgreSQL

# 后端
cd backend
python -m pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser  # 运维账号：登录网页后进入"系统管理"
python manage.py runserver        # http://127.0.0.1:8000

# 前端（另开终端）
cd frontend
npm ci
npm run dev                       # http://localhost:5173 ，/api 与 /admin 代理到 8000
```

首次使用：用运维账号登录网页（首次登录要先改密码），在"系统管理"里新建课题组、开通导师和管理员账号，学生由各组管理员在"成员"页新建（或用 `import_members` 命令批量导入），新建的成员首次登录必须修改初始密码。也可以让学生自己注册：管理员在"成员"页打开"允许学生用链接注册"，把链接发到组里的群，学生用链接填学号、姓名和密码申请，管理员在同一页逐个或一键通过，通过后就能登录。`/admin/` 后台仍然保留，用于删除数据集这类少见的操作，它能看到并修改所有课题组的数据，所以不在对外的端口上：只在服务器本机的 `http://localhost:8091/admin/`（`.env` 的 `ADMIN_PORT` 可改）。从自己电脑打开先建 SSH 隧道 `ssh -L 8091:127.0.0.1:8091 用户@服务器`，再在浏览器打开同一个地址。安装时打印的一次性密码要先在网页上改掉，才能进后台。

## 测试

```bash
cd backend && python -m pytest       # 需要 PostgreSQL 在运行
cd frontend && npm test && npm run build
```

浏览器里的端到端验证（隔离实例，给 AI 代理用）：见 `.claude/skills/verify-lab/SKILL.md`。

## 服务器部署（单机）

前置：Linux 服务器，装好 Docker（带 compose 插件）和 git。镜像由 GitHub 在每次发版时构建，放在 ghcr.io，服务器上不用编译。

首次安装用上面的"一键安装"。要自己逐项配置时，手动安装（版本号见 GitHub 的 Releases 页）：

```bash
git clone https://github.com/cacdcaecawae/lab-management-platform.git /srv/lab-management-platform
cd /srv/lab-management-platform
git checkout v0.1.0                     # 要安装的版本
cp infra/server.env.example .env        # 逐项填写；APP_VERSION 写上一行的版本
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d          # 拉取该版本的镜像并启动
docker compose -f infra/docker-compose.prod.yml --env-file .env exec backend python manage.py createsuperuser
```

更新：运维账号在"系统管理 → 版本"看到新版本后，点"立即更新"，页面会显示进度，完成后自动刷新。也可以在服务器上运行：

```bash
cd /srv/lab-management-platform && bash scripts/update.sh v0.2.0   # 不写版本号就更新到最新版本
```

- "立即更新"由服务器上的更新助手 `scripts/update-agent.sh` 执行：当前用户的 crontab 每分钟启动它一次，它每 2 秒看一次网页上有没有更新请求，有就运行上面的 `update.sh`，用正在运行的网站的同一套 Compose 文件和项目名。容器不拿 Docker 的控制权。一键安装已经装好了它；v0.1.3 及更早装的站点，先用命令更新到带它的版本，再在安装目录运行一次 `bash scripts/update-agent.sh --install`（同时补上每天备份）。日志在安装目录的 `run/update/update.log`。助手没在运行时，页面显示命令。

- 通过 SSH 运行时请在 `tmux` 或 `screen` 里运行：新版本开始启动后断线，脚本会被中断，网站可能停着。启动之前断线，脚本会恢复原版本。
- 更新前先核对版本是有 Git 祖先关系的较新正式标签并检查 Compose、备份仓库和迁移记录，再拉取镜像、停站备份。不支持用更新命令直接降级。备份命令成功并返回快照编号后，脚本才切换部署文件。新版本启动前遇到错误或按 Ctrl-C，脚本会尝试恢复原版本。更新和回退都要等网站能访问（最多 3 分钟），并核对 backend、web 实际运行的镜像版本。
- 新版启动后，验收期间可能已有用户写入。验收失败会先停止网站。只有数据库迁移名单与更新前完全相同时，脚本才自动切回旧版。迁移已变或暂时无法核对时，数据库、上传文件以及新版部署保留在现场，日志给出原版本、新版与更新前快照。
- 手动恢复前，回到原部署目录，使用与上线时相同的 Compose 项目名、配置文件和 `.env`。以下以同时启用 HTTPS 和 NAS 为例；只保留实际使用的覆盖文件。项目名可从现有 db 容器的 `com.docker.compose.project` 标签核对。

  ```bash
  export COMPOSE_PROJECT_NAME=实际部署项目名
  export COMPOSE_FILE=infra/docker-compose.prod.yml:infra/docker-compose.https.yml:infra/docker-compose.nas.yml
  export ENV_FILE=.env
  unset APP_VERSION
  ```

  若确认新版尚未启动，切回原 Git 版本并改回 `.env` 中的版本，运行 `docker compose --env-file "$ENV_FILE" up -d`。如果新版可能已接收写入，先保持停站，暂停定时清理，在独立位置保存当前数据库导出和上传文件，并核对更新窗口内的新记录。在隔离环境确认恢复与补回写入的方案后，才切回选定版本；如确需回到更新前的数据库，使用 `bash scripts/restore.sh <日志中的快照编号> --db-only`。恢复会覆盖当前数据库。保存现场时请勿对唯一的更新前快照执行清理。
- 更新时只停 backend（所有写入都经过它），web 留着显示进度页；页面上的保存会失败，不会写进数据库。

备份与恢复：

- `.env` 里设 `BACKUP_REPO`（另一块硬盘上已存在的绝对路径）和 `BACKUP_PASSWORD`。备份用 restic，在容器里运行，服务器不用另装；加密、增量、去重。**密码丢了备份就打不开**，要另外抄一份保存。 首次在已核实的空目录建仓时，请显式运行 `bash scripts/backup.sh --init`。常规备份不会自动创建仓库，读取配置失败直接退出。使用 NAS 时，在同一 `.env` 中填写实际挂载点 `BACKUP_MOUNTPOINT`（例如 `/mnt/nas`）；请勿并发卸载或更换挂载。

- 配置 `BACKUP_MOUNTPOINT` 时，首次初始化（或接入已有仓库）后，在确认挂载目标确实是预期 NAS 仓库的情况下，交互运行 `bash scripts/backup.sh --repo-id`，把返回的完整 64 位小写仓库 ID 保存到**同一** `.env` 的 `BACKUP_REPO_ID`。不要从尚未核实的挂载或失败日志复制 ID。常规备份、恢复、更新遇到缺失或不同的 ID 都会在导库或停站前退出，即使另一个仓库使用同一密码。非挂载点部署可省略此项以保留原行为，也可以主动设定以固定仓库。已固定仓库 ID 时，`--init` 不会新建替代仓库。仓库迁移时，单独核对新仓库身份，再有意更新配置；不要让计划任务自动发现或覆盖 ID。
- 每天备份一次。最近 14 天的备份全部保留（包括更新前和手动做的），更早的保留每天一份 30 天、每月一份 12 个月。一键安装已经写好了定时任务；手动安装的在安装目录运行一次 `bash scripts/update-agent.sh --install`，或者在宿主机 `crontab -e` 加一行：

  ```cron
  30 2 * * * cd /srv/lab-management-platform && bash scripts/backup.sh >> /var/log/lab-backup.log 2>&1
  ```

- 备份、恢复、更新脚本用的 Compose 文件和项目名，以正在运行的网站后端容器为准：打开 HTTPS 或 NAS 以后，定时任务不用另写 `COMPOSE_FILE`。终端里导出了 `COMPOSE_FILE` 但和网站用的不一致时（比如少了 NAS 那份），脚本什么都不做就退出。

- 列出备份：`bash scripts/restore.sh`；恢复：`bash scripts/restore.sh <快照编号或 latest>`，同时恢复数据库和上传的文件，加 `--db-only` 只恢复数据库。数据库先恢复到一个新库（这一步网站照常运行，失败了什么都没变），再停止网站，以单个 PostgreSQL 事务换上它。任一步换名失败都不提交；仅确认原库仍在且并非内部升级回退时，脚本才尝试启动原站。原来的数据库改名为 `before_restore_<时间和随机后缀>`，等文件恢复完、网站能访问后才删除；中途失败（例如磁盘满了）它会留着，处理好原因后重新运行恢复即可。确认不再需要后删除：`docker compose -f infra/docker-compose.prod.yml --env-file .env exec db sh -c 'dropdb -U "$POSTGRES_USER" before_restore_<时间>'`。
- 服务器坏了、换新机器：要有两样东西，备份盘和一份 `.env`。所以平时就把 `.env` 另存一份到服务器以外（它含备份密码和密钥，像密码一样保管）。新机器上不要运行一键安装，它会生成新的密钥和新的备份仓库，打不开原来的备份。按下面的步骤做（版本号换成备份时运行的版本，"系统管理 → 版本"或更新日志里有）：

  ```bash
  git clone --branch v0.1.1 https://github.com/cacdcaecawae/lab-management-platform.git
  cd lab-management-platform
  cp /保存的/.env .env && chmod 600 .env    # 备份盘挂到 .env 里 BACKUP_REPO 的同一路径，或者改这一项
  docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --wait
  bash scripts/restore.sh latest
  ```

  恢复完用原来的账号和密码登录，核对几条记录和文件，再按上面加回每日备份的定时任务。
- 开发手册要求每月在测试机上还原一次，抽查几条记录和文件。没有还原验证过的备份不算可靠。
- 结果在网页上看：运维账号打开"系统管理 → 存储与备份"，显示最近一次成功的备份（时间、快照编号）、最近一次失败、最近一次恢复演练。超过 26 小时没有成功的备份，或超过 35 天没有通过的演练，标为"逾期"，标签名变成"存储与备份 · 需处理"。结果由 `backup.sh` 和 `restore-drill.sh` 结束时用一次性的 backend 容器写进数据库；写不进去只打印一行提示，不改变备份或演练本身的结果，这时页面会显示逾期。刚装好、还没加定时任务时显示"尚无成功备份"。
- 每天的备份里，数据库导出和文件是先后读取的，网站一直在运行：两步之间被删除的附件，恢复后会缺这一个文件。更新前的那次备份是停了网站做的，没有这个问题。

- 隔离恢复演练：先检查 Docker 存储空间至少可容纳一份解压后的数据库，在测试机用合成备份验收；再按需要在服务器运行 `bash scripts/restore-drill.sh v0.1.0 latest 20`（将版本换为与该快照兼容的 backend 发行版镜像）。无 Web 端口，不调用生产恢复脚本，备份仓库只读。每类最多抽 20 个数据集或知识库文件；未抽到、未纳入样本的文件不算已验证。脚本以非零退出报告失败。
- 演练使用 restic 无锁只读方式，不能与 `forget --prune`、修复或其他仓库维护重叠；安排在不同维护窗口。以下只示例，不会自动安装任务，也需要维护所选镜像版本：

  ```cron
  0 4 1 * * cd /srv/lab-management-platform && bash scripts/restore-drill.sh v0.1.0 latest 20 >> /var/log/lab-restore-drill.log 2>&1
  ```


发版（维护者）：在 `main` 上打标签并推送，例如 `git tag v0.2.0 && git push origin v0.2.0`。GitHub Actions 先在这条提交上跑完整检查，再构建 backend、web 两个镜像推到 `ghcr.io/cacdcaecawae/lab-management-platform/`，并生成发布说明。第一次发版后，到 GitHub 的 Packages 页确认两个镜像是 Public，否则服务器拉取前要先 `docker login ghcr.io`。

其他：

- 不设 `APP_VERSION` 时镜像名是 `local`，`up -d --build` 从当前代码构建，本机试用（`scripts/trial.ps1`）就是这样。
- 数据：数据库在卷 `pgdata`，上传文件在卷 `labdata`，`scripts/backup.sh` 备份这两个。
- 默认只启用 HTTP。没有 HTTPS 时必须设 `DJANGO_SECURE_COOKIES=0` 才能登录，且只能在校内网 / VPN 内使用；不要把这套默认配置直接开放到公网。正式 HTTPS 见下文。
- 上传上限 2GB（`MAX_UPLOAD_SIZE` 与 Nginx `client_max_body_size` 需同时调整）。
- 登录限速按"账号 + 来源地址"计数，来源地址取 Nginx 追加在 `X-Forwarded-For` 末尾的那一段（`config/settings.py` 的 `REST_FRAMEWORK["NUM_PROXIES"] = 1`）。学校统一 HTTPS 网关或其他多层代理不适用下面的直连配置，由网络管理员核实可信代理链、正确传递 HTTPS 和客户端地址，并按实际跳数配置；不要直接照搬。
- 邮件（设备异常、采购审批、财务提醒）：运维账号在"系统管理 → 邮件"里填 SMTP，点"发送测试邮件"确认能发，再打开"启用邮件"。没启用时只有工作台提醒。授权码存在数据库里（页面和接口都不返回），数据库备份里也带着它。学校邮箱怎么填、发不出去怎么查，见 [docs/mail-setup.md](docs/mail-setup.md)。
- 每周一 9:00 的财务提醒由宿主机定时任务触发，应用里没有常驻调度进程。先填好财务邮箱（运维在"系统管理 → 课题组"，或各组管理员在"报销与统计 → 统计 → 财务邮箱"），然后在宿主机 `crontab -e` 加一行（路径换成实际的仓库目录）：

  ```cron
  0 9 * * 1 cd /srv/lab-management-platform && docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T backend python manage.py send_finance_reminder >> /var/log/lab-finance-reminder.log 2>&1
  ```

  忘了配置也不会出错，只是没有每周提醒；管理员可以在"报销与统计 → 统计"里点"发送财务提醒"手动发。

### 正式域名 HTTPS（可选）

这套配置用于 **单台 Linux 服务器直连公网、由自带 Nginx 终止 TLS**。运维先确认域名、主机位置和网络策略，按部署地及校方要求确认是否需备案和办理手续。让所用域名只解析到能到达该服务器的地址（配置了 AAAA 就必须同时验证 IPv6）。HTTP-01 时外部须能访问 TCP 80，正式网站还须能访问 443；若学校网关终止 TLS 或不能开放 80，先由网络管理员确定替代方案，不要执行下列步骤。域名和网络未落实前，继续使用私网 HTTP 或 VPN。

1. **只启动 ACME 引导页。** 使用已经包含本节配置的新版本。复制模板，在 `.env` 设置 `HTTPS_DOMAIN`（完整域名、不含协议或端口）和 `HTTP_PORT=80`。下面的 `domain` 必须与 `HTTPS_DOMAIN` 一致。默认 `ACME_WEBROOT=/srv/lab-certbot/www` 和 `ACME_CERT_ROOT=/etc/letsencrypt`，先创建 webroot；已有站点应安排维护窗口，切到引导期间只对外提供挑战文件，其他 URL 返回 503，不曝光 HTTP 登录。若曾导出 TLS 的 `COMPOSE_FILE`，引导时以这里显式的两个 `-f` 为准。

   ```bash
   domain='你的正式域名'
   sudo install -d -m 0755 /srv/lab-certbot/www/.well-known/acme-challenge
   docker compose --env-file .env -f infra/docker-compose.prod.yml -f infra/docker-compose.acme.yml up -d --no-deps web
   sudo certbot certonly --webroot -w /srv/lab-certbot/www --cert-name "$domain" -d "$domain"
   ```

   签发前可放一个无敏感数据的测试文件，由独立网络检查 `http://<域名>/.well-known/acme-challenge/<文件名>` 能取到，而非应用主页。如果改用非默认目录，Certbot 的 `-w`（以及必要时 `--config-dir` 和续期配置）必须与 Compose 挂载一致。证书私钥不要复制到仓库或放到 webroot。

2. **证书存在后启用 HTTPS。** 必须有 `live/<域名>/fullchain.pem` 和 `privkey.pem`，仅该域名的 `live/` 和 `archive/` 目录只读挂载（保留 Certbot 管理的符号链接，不挂载账户凭据）。不要同时叠加 ACME 引导和 HTTPS。HTTPS 配置自动用 `HTTPS_DOMAIN` 限制 Django 的 Host/CSRF Origin、开启 Secure Cookie，HTTP 只保留挑战文件，其他业务路径跳固定域名。变量不加引号，避免 Bash 运维脚本读取 `.env` 时将引号视为域名的一部分。

   ```bash
   export COMPOSE_FILE=infra/docker-compose.prod.yml:infra/docker-compose.https.yml
   docker compose --env-file .env config --quiet
   docker compose --env-file .env up -d
   curl --fail --silent --show-error -o /dev/null "https://$domain/api/auth/csrf/"
   ```

   运维用外部真实网络检查证书链、域名、时钟、HTTP 固定跳转、TLS 和登录的 Secure Cookie。从容器外访问 `/healthz` 应拒绝；更新/恢复在 web 容器内以证书域名及系统信任链校验真实 HTTPS 监听，要求 Django 返回 204，不能代替外部网络或浏览器验收。默认 HSTS 300 秒，确认稳定后再评估升至一年（31536000）；不要贸然加 `includeSubDomains` 或 preload。发布前可做公开 TLS 评级检查，先取得对该域名执行第三方检测的许可。

3. **让 Certbot 续期并重载 Nginx。** 使用宿主机安装的 Certbot 自带 timer 或已有的等效定时任务，不要重复开多个。用只针对该证书的可执行 deploy hook：放在默认 `/etc/letsencrypt/renewal-hooks/deploy/lab-nginx`，按实际绝对路径和正式域名替换；自定义 Certbot 配置目录时应使用对应 hook 目录。仅成功续期后重载，先 `nginx -t`；将续期失败/证书到期纳入运维告警。

   ```sh
   #!/bin/sh
   set -eu
   case " ${RENEWED_DOMAINS:-} " in
     *" 你的正式域名 "*) ;;
     *) exit 0 ;;
   esac
   cd /srv/lab-management-platform
   export COMPOSE_FILE=infra/docker-compose.prod.yml:infra/docker-compose.https.yml
   docker compose --env-file .env exec -T web nginx -t
   docker compose --env-file .env exec -T web nginx -s reload
   ```

   配置后由运维运行 `sudo certbot renew --cert-name "$domain" --dry-run --run-deploy-hooks` 验证挑战和重载；成功后再看实际 timer 日志，检查线上仍提供期望的证书。参见 [Certbot 续期与钩子文档](https://eff-certbot.readthedocs.io/en/stable/using.html)。

HTTPS 启用后，**备份、恢复、更新、运维 Compose 和续期钩子始终带上同一套 `COMPOSE_FILE` 和项目名**。备份、恢复、更新脚本会自己按运行中的网站取；运维 Compose 命令和续期钩子的定时任务要单独写明，不能依赖交互式 shell 的 export。先在已支持本配置的版本上开启 HTTPS，更新脚本在停站前拒绝缺少 HTTPS 配置的目标版本，自动回退只面向支持该覆盖文件的版本。要跨过第一个支持 HTTPS 的版本，须提前安排维护窗口，先备份，手工准备旧版兼容的 TLS 终止/恢复方案（或暂时关闭外部入口，仅在私网恢复），不要自动降级成公开 HTTP。此前在浏览器启用的 HSTS 仍会生效。

### 每日提醒（可选）

按 Asia/Shanghai 的业务日期计算：试件逾期、设备校准、行动项和周五尚未提交的本周周报。周五早上的周报邮件是**提交前提示**，不表示逾期。邮件由“系统管理 → 邮件”配置；`SITE_URL` 可以填写站点 HTTP(S) 地址（不含账号、路径、查询或片段），不填就只写页面路径。修改环境变量后请按部署流程重建 backend 容器。

先在隔离实例执行 `python manage.py send_due_reminders --dry-run`：不会发送邮件或写发送记录；预览包含内部组内工作内容，只在受控终端查看，不重定向到共享或 cron 日志；不打印 SMTP 凭据。`--date YYYY-MM-DD` 用于指定业务日期（例如合成数据测试；补发历史日期前先人工核对）；晚于上海当前业务日的日期仅允许预览。

验证后再由运维人工添加以下 crontab 示例；项目不会自动启用：

```cron
CRON_TZ=Asia/Shanghai
0 8 * * * cd /srv/lab-management-platform && docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T backend python manage.py send_due_reminders >> /var/log/lab-due-reminders.log 2>&1
```

只使用支持 `CRON_TZ` 的 cron；若不支持，须先让调度端按 Asia/Shanghai 触发，再使用该时刻。每个账号每天只认领一份合并邮件。明确的 SMTP 临时拒绝可在**同一业务日**重跑，总尝试最多三次；永久拒绝须修复配置。SMTP 超时、接受后写库失败或进程中断时无法保证恰好一次送达；发送中/结果不明的记录不会自动重发，避免重复，请先在 SMTP 侧核对。命令对未确认的条目返回非零；发送日志只报告状态计数，不打印邮件正文。


- 站内通知不依赖邮件。运维可以先运行 `python manage.py purge_notifications --dry-run` 查看待清理数量，再手动运行 `python manage.py purge_notifications` 清理已读超过 180 天的通知。不会清理未读，不会自动部署计划任务。

### NAS 作为附件主存储（可选）

默认仍使用本机卷。先发布支持该功能的版本，再考虑切换；不要改正在使用的共享目录或让公网直接访问 SMB/NFS。只启用一台后端的写入实例。

1. 在 Linux 服务器的私网或 VPN 上挂载 NAS。为本系统准备**独立的应用目录**，例如 `/mnt/lab-nas/platform`；不要使用共享盘根目录。运维在该目录创建 `files/` 和 `.lab-storage-id`（仅一行唯一随机 ASCII 标识，非密码），使后端容器 UID 1000 能读标识、读写 `files/`。在 `.env` 写入 `LAB_NAS_ROOT`（绝对路径）与匹配的 `LAB_NAS_STORAGE_ID`。禁止将标识复制到 NAS 未挂载时的宿主机底层目录。
2. **已有文件先迁移再切换。** 独立备份并确认可恢复。维护窗口停止旧后端和 web 写入；把旧 `labdata` 的 `files/` 内容复制到新的专用 NAS 目录，保留旧卷，不复制 `tmp/`。先在隔离环境对比路径、数量、字节和 SHA256，再启动新配置并检查关键上传、下载。切换后不要简单改回旧卷，它没有 NAS 上的新写入。
3. 将 `infra/docker-compose.nas.yml` 加入部署实际使用的 `COMPOSE_FILE` 文件列表，并保持原项目名、HTTPS 覆盖和配置文件。上传暂存仍使用后端容器所在服务器的 `/tmp`，须预留足够空间。数据库保持服务器本地卷。运维到「系统管理 → 存储与备份」检查后端所见目录；单独用备份脚本和隔离恢复确认备份容器看到相同的数据。
4. 将 `BACKUP_REPO` 用绝对路径指向**独立于主存储的备份目标**，不能位于主存储目录内。恢复只覆盖专用目录中的 `files/`，不碰标识、暂存或 NAS 其他资料。挂载离线时不回落本地；网络文件系统读写可能由系统缓存或阻塞，页面只检查识别状态，不表示可写或备份成功。宿主机重挂后重新创建后端容器，并复核备份容器视图；不要假设原有容器会自动看到新挂载。

## 目录

```
backend/    Django 项目（config/ 配置，core/ 公共底座：权限、文件、修改历史、邮件，accounts/ projects/ datasets/ research/ reports/ equipment/ inventory/ procurement/ knowledge/ meetings/ achievements/ 业务 app，workbench/ 工作台，system/ 系统管理；模块之间能引用什么见 docs/architecture.md）
frontend/   Vue 3 SPA（src/modules/<模块>/ 按业务分目录，目前试点设备和知识库，其余页面在 src/views/）
infra/      Nginx、Dockerfile、生产 Compose、服务器 .env 模板，本机试用的 Compose 叠加文件
docs/       架构、数据库、接口约定、开发计划、邮件配置
scripts/    开发辅助脚本（check.sh 完整检查），本机试用 trial.ps1，一键安装 install.sh，服务器上的 update.sh、backup.sh、restore.sh
.github/    GitHub Actions：推送和 PR 时跑完整检查，推送 vX.Y.Z 标签时发版
.agents/notes/   技术决策笔记（看板生成方式见 AGENTS.md）
.claude/skills/  决策笔记 Skill 与校验脚本
```

### 登录记录保留

运维「系统管理 → 登录记录」仅显示近 180 天的应用记录。认证事件记录已有账号归属（若可识别）和来源 IP，不保存表单的原样登录名、密码或浏览器标识。限流只保留应用 DRF 层的发生分钟，不记录来源或被拦次数；Nginx 等代理独自拒绝的请求不计。后端必须保持在受信任代理后，不应直接暴露，且代理跳数必须与实际部署一致。

新采集默认关闭。先确认正在运行的生产实例实际使用的 **Compose 项目名、配置文件列表及顺序、环境文件**。以下用基本部署作示例，必须替换为实际值。使用 HTTPS 覆盖时，文件列表应包含生产基本文件和 HTTPS 覆盖文件（例如 `infra/docker-compose.prod.yml:infra/docker-compose.https.yml`）；不要用仅含基本文件的命令操作已启用 HTTPS 的实例。

```bash
cd /srv/lab-management-platform
export COMPOSE_PROJECT_NAME=实际项目名
export COMPOSE_FILE=infra/docker-compose.prod.yml
docker compose --env-file .env ps backend
docker compose --env-file .env exec -T backend python manage.py purge_login_events --dry-run
```

启用前，部署负责人必须安装并验证每日清理任务。宿主机 crontab 不继承交互式 shell 的 export，因此在任务中显式填写上面已经验证的同一项目和文件列表，并安排日志及失败告警检查：

```cron
15 3 * * * cd /srv/lab-management-platform && COMPOSE_PROJECT_NAME=实际项目名 COMPOSE_FILE=infra/docker-compose.prod.yml docker compose --env-file .env exec -T backend python manage.py purge_login_events >> /var/log/lab-login-events-purge.log 2>&1
```

确认一次计划任务成功且失败告警可见后，在同一个环境文件设 `LOGIN_AUDIT_ENABLED=1`，再用同一套已验证的 Compose 配置执行 `docker compose --env-file .env up -d backend`，使新环境变量生效。清理任务未运行或失败时，接口仍隐藏过期记录，但数据库仍可能保有过期行；关闭采集并不删除旧记录，需继续清理。备份、代理访问日志和数据库日志由部署单独管理。本改动不启用生产采集或任务。

### 耗材批次的升级顺序

批次功能默认不开启，应用数据库迁移本身不会整理、分配或启用现有库存。先迁移数据库，再更新所有前后端库存写入端，最后由管理员对约定的耗材逐件开启。不要在已开启批次管理时混跑旧版后端。未使用批次功能时可逆迁移；一旦发生过模式变更或写入批次数据（包括后来关闭），迁移会在反向变更前明确拒绝，不会清除账本。需要回退时，请由管理员保存当前数据、在隔离实例验证从启用批次前的备份恢复，并确认切回旧备份会失去哪段后续记录。
