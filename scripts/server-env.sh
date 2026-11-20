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
# Tell the site (系统管理 → 存储与备份) how a job ended. A one-off container, because update.sh backs up with backend
# stopped; failing to record only warns, and a job that never records shows as overdue there.
record_ops_run() {
  dc run --rm --no-deps -T backend python manage.py record_ops_run "$@" </dev/null >/dev/null 2>&1 ||
    echo "结果没能记到网站上，不影响这次任务本身" >&2
}

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

# Restic 0.19.1 emits an indented JSON Config with one top-level "id" line.
# Do not accept snapshot IDs or print returned config/error details in unattended jobs.
read_backup_repository_id() {
  local config id
  config=$(restic --no-cache --no-lock cat config 2>/dev/null) || return 1
  id=$(sed -nE 's/^[[:space:]]*"id"[[:space:]]*:[[:space:]]*"([0-9a-f]{64})"[[:space:]]*,?[[:space:]]*$/\1/p' <<<"$config")
  [[ "$id" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$id"
}

check_backup_repository() {
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

# Raw HTTP for new and pre-/healthz images: BusyBox wget follows redirects, so it
# can mistake a redirect for a healthy response (or make a non-loopback request).
http_health_status() {
  local host=$1 path=$2 output pid read_fd write_fd
  # Keep stdin open until the response arrives: some BusyBox nc builds exit
  # immediately on stdin EOF even though Nginx is still waiting for Django.
  coproc LAB_PROBE { dc exec -T web busybox timeout 3 busybox nc 127.0.0.1 80 2>/dev/null; }
  pid=${LAB_PROBE_PID:-}
  read_fd=${LAB_PROBE[0]:-}
  write_fd=${LAB_PROBE[1]:-}
  [ -n "$pid" ] && [ -n "$read_fd" ] && [ -n "$write_fd" ] || return 1
  if ! { printf 'GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n' "$path" "$host" >&"$write_fd" &&
       IFS= read -r -t 3 -u "$read_fd" output; }; then
    exec {write_fd}>&-
    wait "$pid" || :
    return 1
  fi
  # Compose keeps its stdin pump alive until the writer closes, even after nc returns the status.
  exec {write_fd}>&-
  wait "$pid" || return 1
  printf '%s\n' "$output" | awk '$1 ~ /^HTTP\/[0-9.]+$/ && $2 ~ /^[0-9][0-9][0-9]$/ { print $2 }'
}

# Verify the HTTPS listener and real certificate against its canonical name,
# but pin the TCP connection to the web container's loopback (no DNS or host port mapping).
tls_health_status() {
  local host=$1
  dc exec -T web curl -sS --noproxy '*' --connect-timeout 2 --max-time 3 \
    --proto '=https' --resolve "$host:443:127.0.0.1" -o /dev/null -w '%{http_code}' \
    "https://$host/healthz" 2>/dev/null
}

tls_mode() {
  case ":${COMPOSE_FILE}:" in
    *:infra/docker-compose.https.yml:*|*/docker-compose.https.yml:*|*:docker-compose.https.yml:*) return 0 ;;
    *) return 1 ;;
  esac
}

healthy() {
  local host status tls=false http_host_pattern='^([A-Za-z0-9._:-]+|\[[0-9a-fA-F:.]+\])$'
  # The documented Compose overlay sets Django's allowed host to HTTPS_DOMAIN.
  if tls_mode; then
    tls=true
    host=${HTTPS_DOMAIN:-$(envget HTTPS_DOMAIN)}
    [[ "$host" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$ ]] || return 1
  else
    host=${DJANGO_ALLOWED_HOSTS:-$(envget DJANGO_ALLOWED_HOSTS)}
    host=$(printf '%s' "$host" | cut -d, -f1 | sed 's/^\.//; s/^\*$//')
    host=${host:-localhost}
    [[ "$host" =~ $http_host_pattern ]] || return 1
  fi
  for _ in $(seq 60); do
    if [ "$tls" = true ]; then
      status=$(tls_health_status "$host") || status=''
      [ "$status" != 204 ] || return 0
    else
      status=$(http_health_status "$host" /healthz) || status=''
      [ "$status" != 204 ] || return 0
      # Older plain-HTTP images return 200 (Vue history fallback) or 404 for /healthz.
      # Only fall back for those codes, and still require 204 from the actual backend.
      case "$status" in
        200|404)
          [ "$(http_health_status "$host" /api/auth/csrf/)" != 204 ] || return 0 ;;
      esac
    fi
    sleep 3
  done
  return 1
}
