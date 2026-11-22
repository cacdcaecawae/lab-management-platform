#!/usr/bin/env bash
# Update the server to a release: pull its images, stop the site and back up, switch the deployment files and images,
# check the running release. After a schema change leave failed releases stopped for recovery.
# Usage, from the repository root on the server: scripts/update.sh [vX.Y.Z]   (default: the newest release)
set -euo pipefail

main() {
  local file
  source "$(dirname "$0")/server-env.sh"
  git diff --quiet HEAD || die "仓库里有未提交的改动（git status 查看），处理后再更新"
  if [[ -n ${SSH_CONNECTION:-} && -z ${TMUX:-}${STY:-} ]]; then
    echo "提示：建议在 tmux 或 screen 里运行；SSH 断线时，新版本启动之后的步骤会被中断，网站可能停着" >&2
  fi
  current=$(envget APP_VERSION)
  [[ "$current" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || die "$ENV_FILE 里需要正在运行的正式版本（例如 APP_VERSION=v0.1.0）"
  export APP_VERSION="$current"

  git fetch --quiet --tags origin
  target=${1:-$(git tag -l 'v*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)}
  [[ "$target" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] ||
    die "目标须为正式版本：${target:-（还没有发布过）}"
  git rev-parse -q --verify "refs/tags/$target^{commit}" >/dev/null || die "没有这个版本：$target"
  [ "$target" != "$current" ] || { echo "已经是 $current"; exit 0; }
  [[ "$(printf '%s\n' "$current" "$target" | LC_ALL=C sort -V | tail -n 1)" == "$target" ]] &&
    git merge-base --is-ancestor "refs/tags/$current" "refs/tags/$target" ||
    die "无法证明 $target 是 $current 的后续正式版本，未停止网站；不支持直接降级"

  if nas_mode; then
    for file in infra/docker-compose.nas.yml infra/nas-restic.sh backend/core/nas_storage.py; do
      git cat-file -e "HEAD:$file" 2>/dev/null && git cat-file -e "refs/tags/$target:$file" 2>/dev/null ||
        die "当前 checkout 或 $target 不支持 NAS 主存储（缺少 $file），未停止网站"
    done
  fi

  if tls_mode; then
    for file in infra/docker-compose.https.yml infra/nginx.https.conf.template infra/nginx.acme.inc \
      infra/nginx.health.inc infra/nginx.site.inc; do
      git cat-file -e "refs/tags/$target:$file" 2>/dev/null ||
        die "$target 不支持当前的 HTTPS 配置（缺少 $file），未停止网站；跨旧版本请按 README 手动处理"
    done
  fi

  need_live_backup_settings
  dc --profile ops config --quiet || die "当前 Compose 配置无法解析，未停止网站"
  check_backup_repository

  echo "== 拉取 $target 的镜像（失败时什么都没改）"
  progress running 1
  APP_VERSION=$target dc pull backend web
  previous=$(git symbolic-ref -q --short HEAD || git rev-parse HEAD)
  migrations=$(applied_migrations) || die "停站前无法核对数据库迁移"
  log=$(mktemp)
  switching=false
  trap 'resume_before_start' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP  # an SSH session dropped before the new release starts: resume the old site

  # Stopped from here on: a change saved after the backup would be lost if the rollback restores it. Every write goes
  # through backend; web stays up to show the progress page.
  echo "== 停止网站，更新前备份"
  progress running 2
  dc stop backend
  bash "$SCRIPTS/backup.sh" "before-$target" | tee "$log" || die "备份没有完成，没有更新"
  snap=$(sed -n 's/^snapshot \([0-9a-f]*\) saved$/\1/p' "$log")
  [[ "$snap" =~ ^[0-9a-f]+$ ]] || die "备份没有返回唯一快照编号，没有更新"
  rm -f "$log"

  echo "== 更新前的版本是 $current，快照是 $snap；切换到 $target"
  switching=true
  git checkout --quiet "refs/tags/$target"
  setenv APP_VERSION "$target"
  export APP_VERSION="$target"
  # Once the target can run migrations, recovery must account for the database.
  echo "== 启动 $target 并检查网站"
  progress running 3
  trap - EXIT INT TERM HUP
  if start_version; then
    echo "已更新到 $target。更新前的备份是快照 $snap"
    exit 0
  fi

  echo "== $target 验收失败，停止网站并核对迁移" >&2
  dc logs --tail 40 backend >&2 || true
  dc stop backend || die "无法停止失败的版本，不执行回退；更新前快照为 $snap"
  recovery="网站保持停止，数据库与上传文件保留在现场。原版本 $current，当前部署 $target，更新前快照 $snap。请按 README 备份现场并核对更新期间的写入，再决定恢复。"
  after=$(applied_migrations) || die "无法核对数据库迁移。$recovery"
  if [ "$after" != "$migrations" ]; then
    die "新旧数据库迁移记录不同。$recovery"
  fi
  git checkout --quiet "$previous"
  setenv APP_VERSION "$current"
  export APP_VERSION="$current"
  start_version || die "退回 $current 未通过启动、健康或镜像检查，请查看生产 Compose 的 ps 和 logs"
  die "已退回 $current，没有更新。原因见上面的日志"
}

applied_migrations() {
  dc exec -T db sh -c 'psql -X -tA -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT to_json(ARRAY[app, name]) FROM django_migrations ORDER BY app, name"'
}

start_version() {
  local service image
  # web kept running while backend restarted: Nginx resolved backend's address at its start.
  dc up -d && dc restart web && healthy || return 1
  for service in backend web; do
    image=$(dc ps --format '{{.Image}}' "$service") || return 1
    [[ "$image" != *$'\n'* && "$image" == *"/$service:$APP_VERSION" ]] || return 1
  done
}

resume_before_start() {
  rm -f "$log" || true
  export APP_VERSION="$current"
  if [[ $switching == true ]]; then
    git checkout --quiet "$previous" || die "无法切回 $previous，请按 README 手动恢复 $current"
    if [ "$(envget APP_VERSION)" != "$current" ]; then
      setenv APP_VERSION "$current" || die "无法写回 $ENV_FILE，请按 README 手动恢复 $current"
    fi
  fi
  start_version || die "原版本 $current 未通过启动、健康或镜像检查，请按 README 手动恢复"
  echo "原版本 $current 的网站已重新启动" >&2
}

setenv() {
  if grep -q "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >>"$ENV_FILE"; fi
}

# Everything runs from main: git checkout below may replace this file while it runs.
main "$@"
exit
