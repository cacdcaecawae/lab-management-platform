#!/usr/bin/env bash
# Restore a backup snapshot: the database, and unless --db-only, the uploaded files (files added since are removed).
# The site is stopped meanwhile. The database from before is kept (as before_restore_<time>) until the files are back
# and the site answers.
# Usage, from the repository root on the server:
#   scripts/restore.sh                                  list the snapshots
#   scripts/restore.sh <snapshot|latest> [--db-only] [--yes]
set -euo pipefail
source "$(dirname "$0")/server-env.sh"
need_backup_settings

if [ $# -eq 0 ]; then
  restic snapshots --host lab
  exit 0
fi
snap=$1
shift
db_only='' yes=''
for arg in "$@"; do
  case $arg in
    --db-only) db_only=1 ;;
    --yes) yes=1 ;;
    *) die "不认识的参数：$arg" ;;
  esac
done
# Resolve the moving alias once: a cron backup can finish between restoring the DB and the files.
# restic's snapshots JSON has a top-level full "id" per snapshot. Match that field, not the human table's
# short ID; escaped quotes inside JSON strings cannot match. Reject zero/multiple IDs before stopping anything.
if [ "$snap" = latest ]; then
  snapshot_json=$(restic snapshots --json --host lab latest) || die "无法查询 latest，未停止网站"
  snap=$(printf '%s\n' "$snapshot_json" | \
    grep -oE '"id"[[:space:]]*:[[:space:]]*"[0-9a-f]{64}"' | \
    sed -E 's/.*"([0-9a-f]{64})"/\1/') || die "无法确定 latest 的快照编号，未停止网站"
  [[ "$snap" =~ ^[0-9a-f]{64}$ ]] || die "需要唯一的 lab 备份快照，未停止网站"
fi
if [ -z "$yes" ]; then
  what=数据库
  [ -n "$db_only" ] || what=数据库和上传的文件
  read -r -p "用快照 $snap 覆盖当前的$what，期间网站停止。输入 yes 确认：" answer
  [ "$answer" = yes ] || die "已取消"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
restic dump "$snap" /dump/lab.dump >"$tmp/lab.dump"
[ -s "$tmp/lab.dump" ] || die "快照 $snap 里没有数据库导出"

# Names of this run only: never drop a database that an earlier, unfinished restore kept.
stamp=$(date +%Y%m%d%H%M%S)
new=restoring_$stamp old=before_restore_$stamp
in_db() { dc exec -T -e NEW="$new" -e OLD="$old" db sh -c "$1"; }

echo "== 恢复数据库"
# Into a new database while the site still runs: if this fails, nothing has changed.
in_db 'createdb -U "$POSTGRES_USER" "$NEW"'
in_db 'pg_restore -U "$POSTGRES_USER" -d "$NEW" --exit-on-error --single-transaction' <"$tmp/lab.dump" ||
  { in_db 'dropdb -U "$POSTGRES_USER" "$NEW"' || true; die "数据库没有恢复成功，当前的数据没有变化"; }

echo "== 停止网站，换上恢复的数据库"
dc stop backend web
in_db 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -c "ALTER DATABASE $POSTGRES_DB RENAME TO $OLD" \
  -c "ALTER DATABASE $NEW RENAME TO $POSTGRES_DB"'
# A full disk can stop the file restore halfway: keep the database from before until the end.
trap 'rc=$?; rm -rf "$tmp"; [ $rc = 0 ] || echo "恢复没有完成，网站可能停着。恢复前的数据库保留为 $old：处理好原因（例如磁盘空间）后重新运行本脚本，确认无误后按 README 备份与恢复一节删掉它" >&2' EXIT

if [ -z "$db_only" ]; then
  echo "== 恢复上传的文件"
  restic restore "$snap:/data" --target /data --delete
fi

echo "== 启动网站"
dc up -d
healthy || die "网站没有正常启动，请查看：docker compose --env-file $ENV_FILE logs backend"
in_db 'dropdb -U "$POSTGRES_USER" "$OLD"'
echo "已恢复到快照 $snap"
