#!/usr/bin/env bash
# Update the server to a release: pull its images, stop the site and back up, switch the deployment files and images,
# check that the site answers with them; if not, switch back by itself (and restore the database if the new version
# migrated it).
# Usage, from the repository root on the server: scripts/update.sh [vX.Y.Z]   (default: the newest release)
set -euo pipefail

main() {
  local file
  source "$(dirname "$0")/server-env.sh"
  need_backup_settings
  git diff --quiet HEAD || die "仓库里有未提交的改动（git status 查看），处理后再更新"
  current=$(envget APP_VERSION)
  [ -n "$current" ] || die "$ENV_FILE 里没有 APP_VERSION：先写上正在运行的版本，例如 APP_VERSION=v0.1.0"
  export APP_VERSION="$current"

  git fetch --quiet --tags origin
  target=${1:-$(git tag -l 'v*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)}
  [ -n "$target" ] && git rev-parse -q --verify "refs/tags/$target" >/dev/null || die "没有这个版本：${target:-（还没有发布过）}"
  [ "$target" != "$current" ] || { echo "已经是 $current"; exit 0; }

  if tls_mode; then
    for file in infra/docker-compose.https.yml infra/nginx.https.conf.template infra/nginx.acme.inc \
      infra/nginx.health.inc infra/nginx.site.inc; do
      git cat-file -e "refs/tags/$target:$file" 2>/dev/null ||
        die "$target 不支持当前的 HTTPS 配置（缺少 $file），未停止网站；跨旧版本请按 README 手动处理"
    done
  fi

  echo "== 拉取 $target 的镜像（失败时什么都没改）"
  APP_VERSION=$target dc pull backend web
  previous=$(git symbolic-ref -q --short HEAD || git rev-parse HEAD)
  migrations=$(applied_migrations)
  log=$(mktemp)
  switching=false
  trap 'resume_before_start' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  # Stopped from here on: a change saved after the backup would be lost if the rollback restores it.
  echo "== 停止网站，更新前备份"
  dc stop backend web
  bash "$SCRIPTS/backup.sh" "before-$target" | tee "$log" || die "备份没有完成，没有更新"
  snap=$(sed -n 's/^snapshot \([0-9a-f]*\) saved$/\1/p' "$log")
  [[ "$snap" =~ ^[0-9a-f]+$ ]] || die "备份没有返回唯一快照编号，没有更新"
  rm -f "$log"

  echo "== 更新前的版本是 $current，快照是 $snap；切换到 $target"
  switching=true
  git checkout --quiet "$target"
  setenv APP_VERSION "$target"
  export APP_VERSION="$target"
  # Once the target can run migrations, recovery must account for the database.
  echo "== 启动 $target 并检查网站"
  trap - EXIT INT TERM
  if start_version; then
    echo "已更新到 $target。更新前的备份是快照 $snap"
    exit 0
  fi

  echo "== $target 没有正常启动，退回 $current" >&2
  dc logs --tail 40 backend >&2 || true
  git checkout --quiet "$previous"
  setenv APP_VERSION "$current"
  export APP_VERSION="$current"
  after=$(applied_migrations) || die "无法核对数据库迁移，退回未完成，更新前快照为 $snap"
  if [ "$after" != "$migrations" ]; then
    echo "== $target 已经改了数据库结构，用更新前的备份恢复数据库" >&2
    bash "$SCRIPTS/restore.sh" "$snap" --db-only --yes
  fi
  start_version || die "退回 $current 未通过启动、健康或镜像检查，请查看生产 Compose 的 ps 和 logs"
  die "已退回 $current，没有更新。原因见上面的日志"
}

applied_migrations() {
  dc exec -T db sh -c 'psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM django_migrations"'
}

start_version() {
  local service image
  dc up -d && healthy || return 1
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
