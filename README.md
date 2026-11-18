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

## 生产式部署（单机）

```bash
# .env 中至少设置：DJANGO_SECRET_KEY（长随机串）、DJANGO_DEBUG=0、DJANGO_ALLOWED_HOSTS、
# DJANGO_CSRF_TRUSTED_ORIGINS（如 https://lab.example.edu.cn）、POSTGRES_PASSWORD
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.prod.yml --env-file .env exec backend python manage.py createsuperuser
```

- 数据：数据库在卷 `pgdata`，上传文件在卷 `labdata`，两个都要备份。
- 目前只配置了 HTTP。没有 HTTPS 时必须设 `DJANGO_SECURE_COOKIES=0` 才能登录，且只能在校内网 / VPN 内使用；确定域名后在 `infra/nginx.conf` 加证书和 443。
- 上传上限 2GB（`MAX_UPLOAD_SIZE` 与 Nginx `client_max_body_size` 需同时调整）。
- 登录限速按"账号 + 来源地址"计数，来源地址取 Nginx 追加在 `X-Forwarded-For` 末尾的那一段（`config/settings.py` 的 `REST_FRAMEWORK["NUM_PROXIES"] = 1`）。如果在 Nginx 前面再加一层反向代理（例如学校的 HTTPS 网关），要改成 2，否则所有人会被当成同一个地址。
- 邮件（设备异常、采购审批、财务提醒）：运维账号在"系统管理 → 邮件"里填 SMTP，点"发送测试邮件"确认能发，再打开"启用邮件"。没启用时只有工作台提醒。授权码存在数据库里（页面和接口都不返回），数据库备份里也带着它。学校邮箱怎么填、发不出去怎么查，见 [docs/mail-setup.md](docs/mail-setup.md)。
- 每周一 9:00 的财务提醒由宿主机定时任务触发，应用里没有常驻调度进程。先填好财务邮箱（运维在"系统管理 → 课题组"，或各组管理员在"报销与统计 → 统计 → 财务邮箱"），然后在宿主机 `crontab -e` 加一行（路径换成实际的仓库目录）：

  ```cron
  0 9 * * 1 cd /srv/lab-management-platform && docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T backend python manage.py send_finance_reminder >> /var/log/lab-finance-reminder.log 2>&1
  ```

  忘了配置也不会出错，只是没有每周提醒；管理员可以在"报销与统计 → 统计"里点"发送财务提醒"手动发。

## 目录

```
backend/    Django 项目（config/ 配置，core/ 公共底座：权限、文件、修改历史、邮件，accounts/ projects/ datasets/ research/ reports/ equipment/ inventory/ procurement/ knowledge/ meetings/ achievements/ 业务 app，workbench/ 工作台，system/ 系统管理；模块之间能引用什么见 docs/architecture.md）
frontend/   Vue 3 SPA（src/modules/<模块>/ 按业务分目录，目前试点设备和知识库，其余页面在 src/views/）
infra/      Nginx、Dockerfile、生产 Compose，本机试用的 Compose 叠加文件
docs/       架构、数据库、接口约定、开发计划、邮件配置
scripts/    开发辅助脚本，本机试用脚本 trial.ps1
.agents/notes/   技术决策笔记（看板生成方式见 AGENTS.md）
.claude/skills/  决策笔记 Skill 与校验脚本
```
