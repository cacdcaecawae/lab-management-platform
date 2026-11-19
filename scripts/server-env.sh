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

# Keep the primary-storage checks out of the independent read-only recovery drill.
need_live_backup_settings() {
  need_backup_settings
  if nas_mode; then check_nas_paths; fi
}

nas_mode() {
  case ":${COMPOSE_FILE}:" in
    *:infra/docker-compose.nas.yml:*|*/docker-compose.nas.yml:*|*:docker-compose.nas.yml:*) return 0 ;;
    *) return 1 ;;
  esac
}

check_nas_paths() {
  local data repo
  data=${LAB_NAS_ROOT:-$(envget LAB_NAS_ROOT)}
  repo=$BACKUP_REPO
  [[ "$data" == /* && "$repo" == /* ]] ||
    die "NAS 模式需要以绝对路径设置 LAB_NAS_ROOT 和 BACKUP_REPO"
  data=$(realpath -e -- "$data") && repo=$(realpath -e -- "$repo") ||
    die "无法确认主存储或备份目录"
  [[ "$data" != / && "$repo" != / && "$data/" != "$repo/"* && "$repo/" != "$data/"* ]] ||
    die "NAS 主存储和备份目录必须独立、不能相互嵌套"
}

need_backup_repository() {
  need_live_backup_settings
  check_backup_repository
}

check_backup_repository() {
  restic --no-lock cat config >/dev/null ||
    die "无法读取指定备份仓库，请核对 NAS 挂载、权限和密码；未初始化新仓库"
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
