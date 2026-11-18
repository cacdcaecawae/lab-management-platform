#!/usr/bin/env bash
# Update the server to a release: pull its images, back up, switch the deployment files and images, check that the
# site answers; if it does not, switch back by itself (and restore the database if the new version migrated it).
# Usage, from the repository root on the server: scripts/update.sh [vX.Y.Z]   (default: the newest release)
set -euo pipefail

main() {
  source "$(dirname "$0")/server-env.sh"
  need_backup_settings
  git diff --quiet HEAD || die "仓库里有未提交的改动（git status 查看），处理后再更新"
  current=$(envget APP_VERSION)
  [ -n "$current" ] || die "$ENV_FILE 里没有 APP_VERSION：先写上正在运行的版本，例如 APP_VERSION=v0.1.0"

  git fetch --quiet --tags origin
  target=${1:-$(git tag -l 'v*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)}
  [ -n "$target" ] && git rev-parse -q --verify "refs/tags/$target" >/dev/null || die "没有这个版本：${target:-（还没有发布过）}"
  [ "$target" != "$current" ] || { echo "已经是 $current"; exit 0; }

  echo "== 拉取 $target 的镜像（失败时什么都没改）"
  APP_VERSION=$target dc pull backend web

  echo "== 更新前备份"
  log=$(mktemp)
  bash "$SCRIPTS/backup.sh" "before-$target" | tee "$log"  # not tee /dev/stderr: that reopens a redirected log
  snap=$(sed -n 's/^snapshot \([0-9a-f]*\) saved$/\1/p' "$log")
  rm -f "$log"
  [ -n "$snap" ] || die "没拿到备份的快照编号，停止更新"
  migrations=$(applied_migrations)
  previous=$(git symbolic-ref -q --short HEAD || git rev-parse HEAD)

  echo "== 切换到 $target"
  git checkout --quiet "$target"
  setenv APP_VERSION "$target"
  # Old containers can still answer after a failed recreation. A healthy response alone is not an update.
  if dc up -d && healthy; then
    echo "已更新到 $target。更新前的备份是快照 $snap"
    exit 0
  fi

  echo "== $target 没有正常启动，退回 $current" >&2
  dc logs --tail 40 backend >&2 || true
  git checkout --quiet "$previous"
  setenv APP_VERSION "$current"
  if [ "$(applied_migrations)" != "$migrations" ]; then
    echo "== $target 已经改了数据库结构，用更新前的备份恢复数据库" >&2
    bash "$SCRIPTS/restore.sh" "$snap" --db-only --yes
  fi
  dc up -d
  healthy || die "退回 $current 后网站也没有正常启动，请查看：docker compose --env-file $ENV_FILE logs backend"
  die "已退回 $current，没有更新。原因见上面的日志"
}

applied_migrations() {
  dc exec -T db sh -c 'psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM django_migrations"'
}

# Ask Nginx inside the web container, so the host's port mapping and firewall do not matter. Django only answers
# hosts it allows, hence the Host header. Up to 3 minutes: the backend runs the migrations before it starts.
healthy() {
  local host
  host=$(envget DJANGO_ALLOWED_HOSTS | cut -d, -f1 | sed 's/^\.//; s/^\*$//')
  for _ in $(seq 60); do
    dc exec -T web wget -q -O /dev/null --header "Host: ${host:-localhost}" http://127.0.0.1/api/auth/csrf/ \
      2>/dev/null && return 0
    sleep 3
  done
  return 1
}

setenv() {
  if grep -q "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >>"$ENV_FILE"; fi
}

# Everything runs from main: git checkout below may replace this file while it runs.
main "$@"
exit
