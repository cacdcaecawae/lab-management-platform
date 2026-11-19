# 课题组管理平台

课题组内部使用的科研管理平台：成员与项目、实验记录、原始数据与处理记录、周报与反馈、设备预约与耗材、采购审批与报销统计、知识库、组会、成果归档，以及运维用的系统管理。设计文档见 `docs/`，技术决策见 `.agents/notes/`（写法见 `AGENTS.md`）。

技术栈：Vue 3 + TypeScript + Element Plus ｜ Django 5.2 LTS + DRF ｜ PostgreSQL ｜ Docker Compose。

许可证：[MIT](LICENSE)。`.claude/skills/write-notes-like-deepseek/` 改编自 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（MIT），见该目录下的 LICENSE。

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

首次使用：用运维账号登录网页（首次登录要先改密码），在"系统管理"里新建课题组、开通导师和管理员账号，学生由各组管理员在"成员"页新建（或用 `import_members` 命令批量导入）。新成员首次登录必须修改初始密码。`/admin/` 仍然保留，用于删除数据集这类少见的操作。

## 测试

```bash
cd backend && python -m pytest       # 需要 PostgreSQL 在运行
cd frontend && npm test && npm run build
```

浏览器里的端到端验证（隔离实例，给 AI 代理用）：见 `.claude/skills/verify-lab/SKILL.md`。

## 服务器部署（单机）

前置：Linux 服务器，装好 Docker（带 compose 插件）和 git。镜像由 GitHub 在每次发版时构建，放在 ghcr.io，服务器上不用编译。

首次安装（版本号见 GitHub 的 Releases 页）：

```bash
git clone https://github.com/cacdcaecawae/lab-management-platform.git /srv/lab-management-platform
cd /srv/lab-management-platform
git checkout v0.1.0                     # 要安装的版本
cp infra/server.env.example .env        # 逐项填写；APP_VERSION 写上一行的版本
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d          # 拉取该版本的镜像并启动
docker compose -f infra/docker-compose.prod.yml --env-file .env exec backend python manage.py createsuperuser
```

更新：运维账号在"系统管理 → 版本"看到新版本后，在服务器上运行：

```bash
cd /srv/lab-management-platform && bash scripts/update.sh v0.2.0   # 不写版本号就更新到最新版本
```

- 更新会先拉取镜像，再停站备份。备份命令成功并返回快照编号后，脚本才切换部署文件。新版本启动前遇到错误或按 Ctrl-C，脚本会尝试恢复原版本。更新和回退都要等网站能访问（最多 3 分钟），并核对 backend、web 实际运行的镜像版本。
- 新版本起不来就自动退回原版本；如果新版本已经改了数据库结构，先用刚才的备份恢复数据库。备份前网站已经停止，所以恢复不会丢掉更新前保存的内容。
- 如果断电或脚本被强制终止，先看更新日志。确认新版本**尚未启动**时，切回更新前的 Git 版本，把 `.env` 的 `APP_VERSION` 改回原值，在仓库根目录执行 `env -u APP_VERSION docker compose -f infra/docker-compose.prod.yml --env-file .env up -d`。如果新版本可能已启动，先核对迁移状态；需要回退数据库时，切回原版本并改回 `.env` 后，运行 `env -u APP_VERSION bash scripts/restore.sh <更新日志中的快照编号> --db-only`。恢复会覆盖备份之后的数据库写入。
- 没有一键更新按钮：网页只提示版本和命令，更新要在服务器上操作。

备份与恢复：

- `.env` 里设 `BACKUP_REPO`（另一块硬盘上的目录）和 `BACKUP_PASSWORD`。备份用 restic，在容器里运行，服务器不用另装；加密、增量、去重。**密码丢了备份就打不开**，要另外抄一份保存。
- 每天备份一次，保留每天一份 30 天、每月一份 12 个月。在宿主机 `crontab -e` 加一行：

  ```cron
  30 2 * * * cd /srv/lab-management-platform && bash scripts/backup.sh >> /var/log/lab-backup.log 2>&1
  ```

- 列出备份：`bash scripts/restore.sh`；恢复：`bash scripts/restore.sh <快照编号或 latest>`，同时恢复数据库和上传的文件，加 `--db-only` 只恢复数据库。数据库先恢复到一个新库（这一步网站照常运行，失败了什么都没变），再停止网站换上它。原来的数据库改名为 `before_restore_<时间>`，等文件恢复完、网站能访问后才删除；中途失败（例如磁盘满了）它会留着，处理好原因后重新运行恢复即可。确认不再需要后删除：`docker compose -f infra/docker-compose.prod.yml --env-file .env exec db sh -c 'dropdb -U "$POSTGRES_USER" before_restore_<时间>'`。
- 开发手册要求每月在测试机上还原一次，抽查几条记录和文件。没有还原验证过的备份不算可靠。
- 每天的备份里，数据库导出和文件是先后读取的，网站一直在运行：两步之间被删除的附件，恢复后会缺这一个文件。更新前的那次备份是停了网站做的，没有这个问题。

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

HTTPS 启用后，**备份、恢复、更新、运维 Compose 和续期钩子始终带上同一套 `COMPOSE_FILE` 和项目名**；定时任务需要单独写明，不能依赖交互式 shell 的 export。先在已支持本配置的版本上开启 HTTPS，更新脚本在停站前拒绝缺少 HTTPS 配置的目标版本，自动回退只面向支持该覆盖文件的版本。要跨过第一个支持 HTTPS 的版本，须提前安排维护窗口，先备份，手工准备旧版兼容的 TLS 终止/恢复方案（或暂时关闭外部入口，仅在私网恢复），不要自动降级成公开 HTTP。此前在浏览器启用的 HSTS 仍会生效。

## 目录

```
backend/    Django 项目（config/ 配置，core/ 公共底座：权限、文件、修改历史、邮件，accounts/ projects/ datasets/ research/ reports/ equipment/ inventory/ procurement/ knowledge/ meetings/ achievements/ 业务 app，workbench/ 工作台，system/ 系统管理；模块之间能引用什么见 docs/architecture.md）
frontend/   Vue 3 SPA（src/modules/<模块>/ 按业务分目录，目前试点设备和知识库，其余页面在 src/views/）
infra/      Nginx、Dockerfile、生产 Compose、服务器 .env 模板，本机试用的 Compose 叠加文件
docs/       架构、数据库、接口约定、开发计划、邮件配置
scripts/    开发辅助脚本（check.sh 完整检查），本机试用 trial.ps1，服务器上的 update.sh、backup.sh、restore.sh
.github/    GitHub Actions：推送和 PR 时跑完整检查，推送 vX.Y.Z 标签时发版
.agents/notes/   技术决策笔记（看板生成方式见 AGENTS.md）
.claude/skills/  决策笔记 Skill 与校验脚本
```
