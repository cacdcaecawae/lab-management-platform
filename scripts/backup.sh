#!/usr/bin/env bash
# Back up the database and the uploaded files into one restic snapshot in BACKUP_REPO (encrypted with
# BACKUP_PASSWORD), then keep 30 daily and 12 monthly snapshots (handbook §7). Prints `snapshot <id> saved` (update.sh
# reads it) and records the result on the site, 系统管理 → 存储与备份.
# Usage, from the repository root on the server: scripts/backup.sh [tag]   (cron runs it daily; update.sh before updating)
set -euo pipefail
source "$(dirname "$0")/server-env.sh"
[[ $# -le 1 ]] || die "用法：scripts/backup.sh [标签|--init|--repo-id]"
if [[ ${1:-} == --init ]]; then
  need_live_backup_settings
  [[ -z "$BACKUP_REPO_ID" ]] || die "已固定备份仓库身份，拒绝初始化替代仓库"
  first_entry=$(find "$BACKUP_REPO" -mindepth 1 -maxdepth 1 -print -quit) ||
    die "无法检查备份目录"
  [[ -z "$first_entry" ]] || die "只允许在已存在的空目录初始化备份仓库"
  restic init >/dev/null 2>&1 || die "无法初始化备份仓库，请核对路径、权限和密码"
  echo "备份仓库已初始化；核实地址后可用 --repo-id 读取身份"
  exit
fi
if [[ ${1:-} == --repo-id ]]; then
  # Interactive bootstrap; intentionally available before BACKUP_REPO_ID is saved.
  need_live_backup_settings
  read_backup_repository_id || die "无法读取指定备份仓库的身份，请核对路径、权限和密码"
  exit
fi
tag=${1:-daily} step=检查备份仓库 snap=
tmp=$(mktemp -d) log=$(mktemp)  # the log stays out of $tmp, which is backed up
# Every run ends with one record on the site (系统管理 → 存储与备份); recording never changes the exit code.
finish() {
  local rc=$?
  trap - EXIT
  rm -rf "$tmp" "$log"
  if [[ $rc == 0 ]]; then
    record_ops_run backup ok --snapshot "$snap" --detail "标签 $tag"
  else
    record_ops_run backup failed --snapshot "$snap" --detail "${step}失败（标签 $tag，退出码 $rc）"
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
need_backup_repository

step=导出数据库
echo "== 导出数据库"
# shortcut: the dump and the files are read one after the other while the site runs; a file deleted in between is
# missing after a restore. Stop backend and web around the backup if an exact pair matters.
dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$tmp/lab.dump"
[ -s "$tmp/lab.dump" ] || die "数据库导出是空的"

step=写入备份仓库
echo "== 写入备份仓库"
dc --profile ops run --rm -T -v "$tmp:/dump:ro" restic backup --host lab --tag "$tag" /data/files /dump | tee "$log"
snap=$(sed -n 's/^snapshot \([0-9a-f]*\) saved$/\1/p' "$log")
[[ "$snap" =~ ^[0-9a-f]+$ ]] || { snap=; die "备份没有返回唯一快照编号"; }

step=清理旧备份
echo "== 清理旧备份（每天一份留 30 天，每月一份留 12 个月）"
restic forget --host lab --keep-daily 30 --keep-monthly 12 --prune
