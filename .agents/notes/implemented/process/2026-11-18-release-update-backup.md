# Agent Note: 发版、更新与备份：标签发版到 ghcr.io，服务器用 update.sh 更新，失败自动退回

Status: implemented

## Problem

仓库开源以后，用户希望像 sub2api 一样"有新版本时有提示，一条命令就能更新"。上线前还缺三样东西：

- **没有发版**：服务器只能 `up -d --build` 从源码构建，哪个提交在运行、和 GitHub 上差了什么都说不清。
- **没有备份脚本**：开发手册第 7 节要求每天备份、保留 30 天、每月一份，并且每月做恢复演练；[架构文档](../../../../docs/architecture.md)只写了"脚本在部署阶段提供"。
- **检查只在本机跑**：`scripts/check.sh` 要自己记得运行，提交到 GitHub 的代码没人检查。

[开源发布](2026-11-17-open-source-fresh-history.md)记录了参考 sub2api 的做法：后端查 GitHub 的最新发布，只有管理员看得到；它自己替换程序文件后退出，靠 systemd 重启。我们是 Docker 部署，它对 Docker 的推荐做法是 `docker compose pull` 加 `up -d`。

## Decision

跨迁移自动还原的策略由[集成审查](../../implemented/bug-fix/2026-11-19-pr-integration.md)更新。失败版本若已迁移或迁移状态不明，网站保持停止，当前数据库和上传文件留给运维核对。

用户 2026-11-18 说"直接继续迭代"，以下几点按之前列出的建议做：镜像放 ghcr.io；只更新到打了标签的正式版本；网页只提示，不做一键更新；备份按手册保留。

- **CI**（`.github/workflows/ci.yml`）：推送 `main` 和每个 PR，在 GitHub 上起 PostgreSQL 17，运行和本机一样的 `scripts/check.sh`。设备并发模型检查（要 Java 和 TLC）和浏览器验证不在里面。
- **发版**（`.github/workflows/release.yml`）：推送 `vX.Y.Z` 标签后，先调用同一个 CI 工作流检查这条提交，通过后从同一条提交构建 `backend`、`web` 两个镜像，推到 `ghcr.io/<仓库>/backend:vX.Y.Z` 和 `web:vX.Y.Z`，再用 `gh release create --generate-notes` 生成发布说明。
- **镜像怎么选**：`infra/docker-compose.prod.yml` 给两个服务加上 `image: ${IMAGE_PREFIX}/…:${APP_VERSION:-local}`，保留 `build`。
  - 服务器 `.env` 写 `APP_VERSION=v0.1.0`，`up -d` 自动拉取；不写时镜像名是 `local`，`up -d --build` 照旧从源码构建，本机试用不受影响。
  - `APP_VERSION` 也传给后端，作为当前版本。
  - `IMAGE_PREFIX` 留给国内服务器换镜像仓库。
  - 服务器 `.env` 的模板是 `infra/server.env.example`。
- **更新**（`scripts/update.sh [版本]`，默认最新的 `vX.Y.Z` 标签），按顺序：
  1. 拉取新镜像；失败时什么都没改。
  2. 调用 `backup.sh` 备份，记下快照编号和 `django_migrations` 的行数。
  3. `git checkout` 到新版本的标签，让部署文件跟着版本走；改写 `.env` 里的 `APP_VERSION`，然后 `up -d`。
  4. 在 web 容器里经 Nginx 请求 `/api/auth/csrf/`，带上 `DJANGO_ALLOWED_HOSTS` 的第一个域名，最多等 3 分钟。
  5. 不通过就切回原来的提交和版本。如果 `django_migrations` 的行数变了，说明新版本已经改了数据库结构，先用第 2 步的快照恢复数据库，再启动。
  6. 整个脚本在 `main` 函数里，所以运行中 `git checkout` 换掉脚本文件也不受影响。
- **备份**（`scripts/backup.sh`）：
  - 先 `pg_dump -Fc`，再和 `labdata` 卷一起写进同一个 restic 快照。
  - restic 是 Compose 里的 `restic` 服务（`restic/restic:0.19.1`，profile `ops`），服务器上只要装 Docker。
  - 仓库在 `BACKUP_REPO`，用 `BACKUP_PASSWORD` 加密；仓库不存在时自动初始化。
  - 每次备份后执行 `forget --keep-daily 30 --keep-monthly 12 --prune`。
- **恢复**（`scripts/restore.sh <快照> [--db-only] [--yes]`）：
  - 先把快照里的数据库导出取出来，确认不是空的，再停网站。
  - 数据库先恢复到新库 `restoring`，成功后再和原库改名对调，所以中途失败不会动到原库。
  - 文件用 `restic restore <快照>:/data --delete` 恢复，快照之后新加的文件会被删掉。
- **版本提示**（`GET /api/system/version/`，只有运维账号能看）：
  - 后端用标准库 `urllib` 查 GitHub 的 `releases/latest`，存在数据库缓存里：成功缓存 6 小时，失败缓存 10 分钟。
  - 连不上 GitHub 时，页面显示原因，其他功能照常。
  - "系统管理"新增"版本"标签页，显示当前版本、最新版本（链接到发布说明）和更新命令；有新版本时标签名写"版本 · 有更新"。

## Alternatives considered

- **网页里一键更新**（sub2api 的做法）：sub2api 是单个程序，可以替换自己的文件再退出；我们在容器里，网页要更新就得把 Docker 的控制权（`docker.sock`）交给后端容器，等于把整台服务器交给 Web 应用。更新前的备份、失败后的退回也要在网页里重做一遍。
- **Watchtower 之类的自动更新容器**：省事，但不会先备份，也不会在数据库迁移失败后退回；而且会在任意时间更新，用户正在上传大文件也照样重启。
- **镜像放 Docker Hub 或阿里云**：Docker Hub 匿名拉取有次数限制，还要另配账号和密钥；ghcr.io 用仓库自带的 `GITHUB_TOKEN` 就能推送。国内服务器拉不动时，把镜像同步到阿里云，再改 `IMAGE_PREFIX`。
- **退回时总是恢复数据库**：最省事。但如果只是新版本起不来、数据库没动，就会白白丢掉备份之后写入的数据。所以只在迁移行数变了时才恢复。
- **退回时只换回旧镜像，不碰数据库**：迁移改过的结构会留下，旧代码可能读不了。
- **用 pg_dump 加 tar 打全量包**：不用额外工具。但手册的数据量按 TB 估计，每天全量打包装不下，过期清理也要自己写；restic 自带增量、去重、加密和保留策略，手册本来就选了它。
- **只在本机跑 check.sh，不上 CI**：现在已经有别的会话在开 PR（2026-11-18 合并的 #5–#8），没有 CI 时，PR 有没有检查过只能靠人记。

## Consequences

- 验证（2026-11-18，本机 Windows：Git Bash 加 Docker Desktop）：用一个本地镜像仓库代替 ghcr.io，造了三个测试版本，用真实的 Docker 和 restic 走过：
  - 服务器上没有镜像时 `up -d` 自己拉取，健康检查通过；
  - 备份后删组、删文件、加文件，`restore.sh latest` 把数据库和文件都恢复回来，后加的文件被删掉，临时库也清理干净；输入 yes 以外的内容会取消；
  - `update.sh` 正常升级，`.env`、容器和部署文件都切到新版本，再运行一次提示"已经是"；
  - 坏版本先加一张表再崩溃：`update.sh` 退回原版本，迁移行数回到原值，那张表消失，更新前刚建的数据还在。
- 测试中发现并修好：`tee /dev/stderr` 在输出被重定向到日志文件时，会重新打开文件，盖掉日志开头；改为 `tee` 到临时文件。
- 未验证：
  - 两个 GitHub Actions 工作流要推送后才会运行；
  - ghcr.io 上的镜像第一次推送后是否公开，要到 Packages 页确认；
  - 在真正的 Linux 服务器上运行；
  - 大数据量下的备份时长。
- 运维要做的：`.env` 填 `APP_VERSION`、`BACKUP_REPO`、`BACKUP_PASSWORD`；crontab 加每日备份；备份密码另外保存；每月在测试机上演练一次恢复。
- 已知限制：
  - 备份时网站在运行，导出数据库和读取文件之间被删除的附件，恢复后会缺这一个文件。
  - 健康检查最多等 3 分钟，数据迁移特别慢的版本会被误判为失败并退回。
  - 版本提示要求服务器能访问 api.github.com。
