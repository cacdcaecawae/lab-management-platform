# Sourced by backup.sh, restore.sh and update.sh: run from the repository root against the production stack.
# ENV_FILE and COMPOSE_FILE (and COMPOSE_PROJECT_NAME) may point elsewhere, e.g. to try the scripts on a test stack.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SCRIPTS=$PWD/scripts
ENV_FILE=${ENV_FILE:-.env}
export COMPOSE_FILE=${COMPOSE_FILE:-infra/docker-compose.prod.yml}

die() { echo "$*" >&2; exit 1; }
[ -f "$ENV_FILE" ] || die "找不到 $ENV_FILE（模板见 infra/server.env.example）"

dc() { docker compose --env-file "$ENV_FILE" "$@"; }
envget() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'; }
restic() { dc --profile ops run --rm -T restic "$@"; }

# Supported paths are absolute local bind mounts. Ensure the same values are used by shell
# checks and Compose even if an interactive environment inherited a conflicting value.
need_backup_settings() {
  BACKUP_REPO=$(envget BACKUP_REPO)
  unset BACKUP_PASSWORD # Let Compose parse the configured password, not an inherited override.
  BACKUP_MOUNTPOINT=$(envget BACKUP_MOUNTPOINT)
  unset BACKUP_REPO_ID # Keep the expected identity local even if it was inherited as exported.
  BACKUP_REPO_ID=$(envget BACKUP_REPO_ID)
  export BACKUP_REPO
  [[ "$BACKUP_REPO" == /* && -n "$(envget BACKUP_PASSWORD)" ]] ||
    die "先在 $ENV_FILE 里设置 BACKUP_REPO（已存在的绝对路径）和 BACKUP_PASSWORD"
  [[ -d "$BACKUP_REPO" ]] || die "备份目录不存在或不可访问：$BACKUP_REPO"
  if [[ -n "$BACKUP_MOUNTPOINT" ]]; then
    local mount repo
    mount=$(realpath -e -- "$BACKUP_MOUNTPOINT") &&
      [[ "$BACKUP_MOUNTPOINT" == /* && "$mount" != / ]] &&
      mountpoint -q -- "$mount" || die "备份挂载点未挂载：$BACKUP_MOUNTPOINT"
    repo=$(realpath -e -- "$BACKUP_REPO") &&
      [[ "$repo" == "$mount" || "$repo" == "$mount/"* ]] ||
      die "备份目录不在指定挂载点内：$BACKUP_REPO"
  fi
}

# Restic 0.19.1 emits an indented JSON Config with one top-level "id" line.
# Do not accept snapshot IDs or print returned config/error details in unattended jobs.
read_backup_repository_id() {
  local config id
  config=$(restic --no-cache --no-lock cat config 2>/dev/null) || return 1
  id=$(sed -nE 's/^[[:space:]]*"id"[[:space:]]*:[[:space:]]*"([0-9a-f]{64})"[[:space:]]*,?[[:space:]]*$/\1/p' <<<"$config")
  [[ "$id" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$id"
}

need_backup_repository() {
  need_backup_settings
  if [[ -n "$BACKUP_MOUNTPOINT" && -z "$BACKUP_REPO_ID" ]]; then
    die "使用备份挂载点时，须先核实仓库并在 $ENV_FILE 中设置 BACKUP_REPO_ID"
  fi
  if [[ -z "$BACKUP_REPO_ID" ]]; then
    # Preserve compatibility for existing local installations without identity pinning.
    restic --no-cache --no-lock cat config >/dev/null 2>&1 ||
      die "无法读取指定备份仓库，请核对路径、权限和密码；未初始化新仓库"
    return
  fi
  [[ "$BACKUP_REPO_ID" =~ ^[0-9a-f]{64}$ ]] ||
    die "$ENV_FILE 中的 BACKUP_REPO_ID 应是完整的 64 位小写十六进制仓库 ID"
  local actual
  actual=$(read_backup_repository_id) ||
    die "无法读取指定备份仓库的身份，请核对路径、权限和密码"
  [[ "$actual" == "$BACKUP_REPO_ID" ]] || die "备份仓库身份不符，已停止操作"
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
