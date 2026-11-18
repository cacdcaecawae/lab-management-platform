#!/usr/bin/env bash
# Restore a backup snapshot: the database, and unless --db-only, the uploaded files (files added since are removed).
# The site is stopped meanwhile. The old database is kept until the restored one is in place.
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

echo "== 停止网站"
dc stop backend web

echo "== 恢复数据库"
# Into a new database first: if the restore fails, the current one is untouched.
dc exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists restoring && createdb -U "$POSTGRES_USER" restoring'
dc exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d restoring --exit-on-error --single-transaction' <"$tmp/lab.dump"
dc exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS before_restore" \
  -c "ALTER DATABASE $POSTGRES_DB RENAME TO before_restore" \
  -c "ALTER DATABASE restoring RENAME TO $POSTGRES_DB" \
  -c "DROP DATABASE before_restore"'

if [ -z "$db_only" ]; then
  echo "== 恢复上传的文件"
  restic restore "$snap:/data" --target /data --delete
fi

echo "== 启动网站"
dc up -d
echo "已恢复到快照 $snap"
