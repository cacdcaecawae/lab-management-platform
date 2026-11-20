#!/usr/bin/env bash
# Recover into a dedicated temporary stack; never call the live restore script.
set -euo pipefail
cd "$(dirname "$0")/.."
env_file=${ENV_FILE:-.env}
[[ -f "$env_file" ]] || { echo "找不到环境文件：$env_file" >&2; exit 1; }
envget() { sed -n "s/^$1=//p" "$env_file" | tail -n 1 | tr -d '\r'; }
unset BACKUP_REPO_ID # Ignore an interactive shell override.
repo_id=$(envget BACKUP_REPO_ID)
backup_mountpoint=$(envget BACKUP_MOUNTPOINT)
BACKUP_REPO=$(envget BACKUP_REPO)
export BACKUP_REPO
unset BACKUP_PASSWORD # Use the same configured credentials as the scheduled backup.
if [[ -n "$backup_mountpoint" ]]; then
  [[ -n "$repo_id" ]] || {
    echo "使用备份挂载点时，须先核实仓库并在 $env_file 中设置 BACKUP_REPO_ID" >&2
    exit 1
  }
  mount=$(realpath -e -- "$backup_mountpoint") &&
    [[ "$backup_mountpoint" == /* && "$mount" != / ]] &&
    mountpoint -q -- "$mount" || { echo "备份挂载点未挂载" >&2; exit 1; }
  repo=$(realpath -e -- "$BACKUP_REPO") &&
    [[ "$BACKUP_REPO" == /* && -d "$repo" && ( "$repo" == "$mount" || "$repo" == "$mount/"* ) ]] ||
    { echo "备份目录不在指定挂载点内" >&2; exit 1; }
fi
[[ -z "$repo_id" || "$repo_id" =~ ^[0-9a-f]{64}$ ]] || {
  echo "$env_file 中的 BACKUP_REPO_ID 应是完整的 64 位小写十六进制仓库 ID" >&2
  exit 1
}

version=${1:-}
snap=${2:-latest}
limit=${3:-20}
[[ $# -le 3 && "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ &&
   ( "$snap" == latest || "$snap" =~ ^[0-9a-f]{8,64}$ ) &&
   "$limit" =~ ^([1-9]|[1-9][0-9]|100)$ ]] || {
  echo "用法：$0 vX.Y.Z [latest|快照ID] [每类抽样数 1–100]" >&2
  exit 1
}
umask 077
DRILL_DIR=$(mktemp -d "${TMPDIR:-/tmp}/labdrill.XXXXXXXXXX")
export DRILL_APP_VERSION=$version DRILL_SCRIPT=$PWD/scripts/restore-drill-verify.py
export COMPOSE_PROFILES=
project=labdrill-${DRILL_DIR##*.}
project=${project,,}
started=no
dc() { docker compose --project-name "$project" --file infra/docker-compose.drill.yml --env-file "$env_file" "$@"; }
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "$started" == yes ]] && ! dc down --volumes --remove-orphans >&2; then
    echo "演练清理失败：项目 $project，请核对项目后手动清理" >&2
    rc=1
  fi
  rm -rf -- "$DRILL_DIR" || rc=1
  if [[ $rc != 0 ]]; then echo "演练失败（项目 $project，退出码 $rc，见上方日志）" >&2; fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# A unique label plus a preflight prevents cleanup from claiming an existing project.
for listing in "container ls -aq" "volume ls -q" "network ls -q"; do
  read -r -a words <<< "$listing"
  owned=$(docker "${words[@]}" --filter "label=com.docker.compose.project=$project")
  [[ -z "$owned" ]] || { echo "项目名已存在：$project" >&2; exit 1; }
done
started=yes
rt() { dc run --rm -T --no-deps restic "$@"; }
verify() { dc run --rm -T --no-deps verifier "$@"; }

if [[ -n "$repo_id" ]]; then
  # Restic 0.19.1 emits an indented JSON Config with one top-level id.
  # Use the same read-only isolated mount as the subsequent snapshot reads.
  config=$(rt --no-cache cat config 2>/dev/null) || { echo "无法读取指定备份仓库的身份" >&2; exit 1; }
  actual=$(sed -nE 's/^[[:space:]]*"id"[[:space:]]*:[[:space:]]*"([0-9a-f]{64})"[[:space:]]*,?[[:space:]]*$/\1/p' <<<"$config")
  [[ "$actual" == "$repo_id" ]] || { echo "备份仓库身份不符，未恢复任何数据" >&2; exit 1; }
fi

id=$(rt snapshots --json --host lab "$snap" | verify snapshot)
[[ "$id" =~ ^[0-9a-f]{64}$ ]] || { echo "无法固定快照 ID" >&2; exit 1; }
echo "恢复演练：快照 $id，后端镜像 $version"
# Compose uses a separate database with no host port. Stop before importing if readiness fails.
dc up -d --wait --wait-timeout 120 db
rt dump "$id" /dump/lab.dump | dc exec -T db pg_restore --no-owner --no-privileges \
  --exit-on-error --single-transaction -U lab_drill -d lab_drill
# Use a new deterministic sample each month for the same snapshot, without printing names or paths.
verify sample "$limit" "$id:$(date -u +%Y-%m)" > "$DRILL_DIR/manifest"
verify includes < "$DRILL_DIR/manifest" > "$DRILL_DIR/includes"
checked=0
while IFS=$'\t' read -r kind path checksum; do
  rt dump "$id" "$path" | verify verify-file "$kind" "$checksum"
  checked=$((checked + 1))
done < "$DRILL_DIR/includes"
if [[ "$checked" == 0 ]]; then
  echo "备份无这两类附件；未验证文件内容"
else
  echo "附件校验：$checked 项"
fi
dc down --volumes --remove-orphans
started=no
echo "演练通过"
