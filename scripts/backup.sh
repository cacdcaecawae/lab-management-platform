#!/usr/bin/env bash
# Back up the database and the uploaded files into one restic snapshot in BACKUP_REPO (encrypted with
# BACKUP_PASSWORD), then keep 30 daily and 12 monthly snapshots (handbook §7). The last line names the snapshot.
# Usage, from the repository root on the server: scripts/backup.sh [tag]   (cron runs it daily; update.sh before updating)
set -euo pipefail
source "$(dirname "$0")/server-env.sh"
need_backup_settings

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "== 导出数据库"
# shortcut: the dump and the files are read one after the other while the site runs; a file deleted in between is
# missing after a restore. Stop backend and web around the backup if an exact pair matters.
dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$tmp/lab.dump"
[ -s "$tmp/lab.dump" ] || die "数据库导出是空的"

echo "== 写入备份仓库"
restic cat config >/dev/null 2>&1 || restic init
dc --profile ops run --rm -T -v "$tmp:/dump:ro" restic backup --host lab --tag "${1:-daily}" /data /dump

echo "== 清理旧备份（每天一份留 30 天，每月一份留 12 个月）"
restic forget --host lab --keep-daily 30 --keep-monthly 12 --prune
