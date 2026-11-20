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

- 更新前先核对版本是有 Git 祖先关系的较新正式标签并检查 Compose、备份仓库和迁移记录，再拉取镜像、停站备份。不支持用更新命令直接降级。备份命令成功并返回快照编号后，脚本才切换部署文件。新版本启动前遇到错误或按 Ctrl-C，脚本会尝试恢复原版本。更新和回退都要等网站能访问（最多 3 分钟），并核对 backend、web 实际运行的镜像版本。
- 新版本起不来就自动退回原版本；如果新版本已经改了已应用迁移名单（不仅是迁移数量），先用刚才的备份恢复数据库。失败的新版先停下来；无法确认回退时不会把旧镜像启动到新库上。备份前网站已经停止，所以恢复不会丢掉更新前保存的内容。
- 如果断电或脚本被强制终止，先看更新日志。确认新版本**尚未启动**时，切回更新前的 Git 版本，把 `.env` 的 `APP_VERSION` 改回原值，在仓库根目录执行 `env -u APP_VERSION docker compose -f infra/docker-compose.prod.yml --env-file .env up -d`。如果新版本可能已启动，先核对迁移状态；需要回退数据库时，切回原版本并改回 `.env` 后，运行 `env -u APP_VERSION bash scripts/restore.sh <更新日志中的快照编号> --db-only`。恢复会覆盖备份之后的数据库写入。
- 没有一键更新按钮：网页只提示版本和命令，更新要在服务器上操作。

备份与恢复：

- `.env` 里设 `BACKUP_REPO`（另一块硬盘上已存在的绝对路径）和 `BACKUP_PASSWORD`。备份用 restic，在容器里运行，服务器不用另装；加密、增量、去重。**密码丢了备份就打不开**，要另外抄一份保存。 首次在已核实的空目录建仓时，请显式运行 `bash scripts/backup.sh --init`。常规备份不会自动创建仓库，读取配置失败直接退出。使用 NAS 时，在同一 `.env` 中填写实际挂载点 `BACKUP_MOUNTPOINT`（例如 `/mnt/nas`）；请勿并发卸载或更换挂载。

- 配置 `BACKUP_MOUNTPOINT` 时，首次初始化（或接入已有仓库）后，在确认挂载目标确实是预期 NAS 仓库的情况下，交互运行 `bash scripts/backup.sh --repo-id`，把返回的完整 64 位小写仓库 ID 保存到**同一** `.env` 的 `BACKUP_REPO_ID`。不要从尚未核实的挂载或失败日志复制 ID。常规备份、恢复、更新遇到缺失或不同的 ID 都会在导库或停站前退出，即使另一个仓库使用同一密码。非挂载点部署可省略此项以保留原行为，也可以主动设定以固定仓库。已固定仓库 ID 时，`--init` 不会新建替代仓库。仓库迁移时，单独核对新仓库身份，再有意更新配置；不要让计划任务自动发现或覆盖 ID。
- 每天备份一次，保留每天一份 30 天、每月一份 12 个月。在宿主机 `crontab -e` 加一行：

  ```cron
  30 2 * * * cd /srv/lab-management-platform && bash scripts/backup.sh >> /var/log/lab-backup.log 2>&1
  ```

- 列出备份：`bash scripts/restore.sh`；恢复：`bash scripts/restore.sh <快照编号或 latest>`，同时恢复数据库和上传的文件，加 `--db-only` 只恢复数据库。数据库先恢复到一个新库（这一步网站照常运行，失败了什么都没变），再停止网站，以单个 PostgreSQL 事务换上它。任一步换名失败都不提交；仅确认原库仍在且并非内部升级回退时，脚本才尝试启动原站。原来的数据库改名为 `before_restore_<时间和随机后缀>`，等文件恢复完、网站能访问后才删除；中途失败（例如磁盘满了）它会留着，处理好原因后重新运行恢复即可。确认不再需要后删除：`docker compose -f infra/docker-compose.prod.yml --env-file .env exec db sh -c 'dropdb -U "$POSTGRES_USER" before_restore_<时间>'`。
- 开发手册要求每月在测试机上还原一次，抽查几条记录和文件。没有还原验证过的备份不算可靠。
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
- 目前只配置了 HTTP。没有 HTTPS 时必须设 `DJANGO_SECURE_COOKIES=0` 才能登录，且只能在校内网 / VPN 内使用；确定域名后在 `infra/nginx.conf` 加证书和 443。
- 上传上限 2GB（`MAX_UPLOAD_SIZE` 与 Nginx `client_max_body_size` 需同时调整）。
- 登录限速按"账号 + 来源地址"计数，来源地址取 Nginx 追加在 `X-Forwarded-For` 末尾的那一段（`config/settings.py` 的 `REST_FRAMEWORK["NUM_PROXIES"] = 1`）。如果在 Nginx 前面再加一层反向代理（例如学校的 HTTPS 网关），要改成 2，否则所有人会被当成同一个地址。
- 邮件（设备异常、采购审批、财务提醒）：运维账号在"系统管理 → 邮件"里填 SMTP，点"发送测试邮件"确认能发，再打开"启用邮件"。没启用时只有工作台提醒。授权码存在数据库里（页面和接口都不返回），数据库备份里也带着它。学校邮箱怎么填、发不出去怎么查，见 [docs/mail-setup.md](docs/mail-setup.md)。
- 每周一 9:00 的财务提醒由宿主机定时任务触发，应用里没有常驻调度进程。先填好财务邮箱（运维在"系统管理 → 课题组"，或各组管理员在"报销与统计 → 统计 → 财务邮箱"），然后在宿主机 `crontab -e` 加一行（路径换成实际的仓库目录）：

  ```cron
  0 9 * * 1 cd /srv/lab-management-platform && docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T backend python manage.py send_finance_reminder >> /var/log/lab-finance-reminder.log 2>&1
  ```

  忘了配置也不会出错，只是没有每周提醒；管理员可以在"报销与统计 → 统计"里点"发送财务提醒"手动发。

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
