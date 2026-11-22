# Sourced by backup.sh, restore.sh and update.sh: run from the repository root against the production stack.
# ENV_FILE and COMPOSE_FILE (and COMPOSE_PROJECT_NAME) may point elsewhere, e.g. to try the scripts on a test stack.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SCRIPTS=$PWD/scripts
ENV_FILE=${ENV_FILE:-.env}

die() { echo "$*" >&2; exit 1; }
[ -f "$ENV_FILE" ] || die "找不到 $ENV_FILE（模板见 infra/server.env.example）"

dc() { docker compose --env-file "$ENV_FILE" "$@"; }
envget() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'; }

# The Compose files and project this checkout's site was started with, from its backend container's labels. A cron
# line or a fresh shell names no HTTPS or NAS overlay, and fewer files back up the old local volume or restart the site
# without them. backend, not web: both overlays change backend, so switching one on recreated (and relabelled) it,
# while web keeps its install-time labels. Anything unclear stops the script before it touches anything: Docker not
# answering, two sites here, a COMPOSE_PROJECT_NAME or COMPOSE_FILE other than the site's, or (no site here) a project
# name another directory's site uses. SITE_BACKEND: the site's backend container, empty when none was found here.
running_stack() {
  local ids id labels site='' other='' files given='' f list=() dirs
  SITE_BACKEND=
  ids=$(docker ps -aq --filter "label=com.docker.compose.project.working_dir=$PWD/infra" \
    --filter label=com.docker.compose.service=backend --filter label=com.docker.compose.oneoff=False) ||
    die "查不到这台电脑上 Docker 的容器，没有做任何操作"
  for id in $ids; do
    labels=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}|{{index .Config.Labels "com.docker.compose.project"}}' "$id") &&
      [[ $labels == ?*'|'?* ]] || die "读不出网站后端容器 $id 的 Compose 配置，没有做任何操作"
    if [[ -n ${COMPOSE_PROJECT_NAME:-} && ${labels##*|} != "$COMPOSE_PROJECT_NAME" ]]; then other=${labels##*|}; continue; fi
    [[ -z $site || $site == "$labels" ]] ||
      die "这个目录有两套网站（Compose 项目 ${site##*|} 和 ${labels##*|}），用 COMPOSE_PROJECT_NAME 指定是哪一套，没有做任何操作"
    site=$labels SITE_BACKEND=$id
  done
  if [[ -z $site ]]; then
    [[ -z $other ]] || die "这个目录的网站是 Compose 项目 $other，不是 $COMPOSE_PROJECT_NAME，没有做任何操作"
    # Compose names the project after the first file's directory, infra/, unless told otherwise.
    dirs=$(docker ps -a --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME:-infra}" \
      --format '{{.Label "com.docker.compose.project.working_dir"}}') || die "查不到这台电脑上 Docker 的容器，没有做任何操作"
    dirs=$(grep -vxF -e "$PWD/infra" -e '' <<<"$dirs") &&
      die "Compose 项目 ${COMPOSE_PROJECT_NAME:-infra} 是另一个目录（${dirs%%$'\n'*}）的网站，没有做任何操作"
    return 0
  fi
  files=${site%|*} files=${files//,/:}
  if [[ -n ${COMPOSE_FILE:-} ]]; then
    IFS=: read -r -a list <<<"$COMPOSE_FILE"
    for f in "${list[@]}"; do [[ $f == /* ]] || f=$PWD/$f; given+=${given:+:}$f; done
    [[ $given == "$files" ]] ||
      die "COMPOSE_FILE 和正在运行的网站不一致，没有做任何操作。网站用的是 ${files//$PWD\//}；现在是 $COMPOSE_FILE"
  fi
  export COMPOSE_FILE=$files COMPOSE_PROJECT_NAME=${site##*|}
}
COMPOSE_FILE_GIVEN=${COMPOSE_FILE:-} SITE_BACKEND=
# Installing (install.sh, update-agent.sh --install) acts on no site: install.sh checks the project name itself.
[[ ${LAB_INSTALL:-} == yes ]] || running_stack
export COMPOSE_FILE=${COMPOSE_FILE:-infra/docker-compose.prod.yml}
# Backing up, restoring or updating needs the site's own files: without a site here (never started, or removed with
# down), only a COMPOSE_FILE naming them will do, or a NAS site would be backed up, restored or restarted on the local
# volume. A new server is restored onto a site started first (README), so it has one.
need_site() {
  [[ -n $SITE_BACKEND || -n $COMPOSE_FILE_GIVEN ]] ||
    die "没有找到这个目录正在运行的网站（$PWD/infra 的 backend 容器），没有做任何操作。网站先 up 起来，或者用 COMPOSE_FILE 写明它的 Compose 文件"
}
restic() { dc --profile ops run --rm -T restic "$@"; }
# Tell the site (系统管理 → 存储与备份) how a job ended. A one-off container, because update.sh backs up with backend
# stopped; failing to record only warns, and a job that never records shows as overdue there.
record_ops_run() {
  dc run --rm --no-deps -T backend python manage.py record_ops_run "$@" </dev/null >/dev/null 2>&1 ||
    echo "结果没能记到网站上，不影响这次任务本身" >&2
}

# Progress of an update started from 系统管理 → 版本: update-agent.sh sets LAB_UPDATE_STATUS. Nginx serves the file
# without a login (the backend is stopped meanwhile), so it holds only a state, a step number and the target.
progress() {
  [ -n "${LAB_UPDATE_STATUS:-}" ] || return 0
  printf '{"state":"%s","step":%s,"target":"%s","started":%s}\n' "$1" "$2" "$LAB_UPDATE_TARGET" "$LAB_UPDATE_STARTED" \
    >"$LAB_UPDATE_STATUS.tmp" && mv -f -- "$LAB_UPDATE_STATUS.tmp" "$LAB_UPDATE_STATUS" || true
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
  local data repo serving
  data=${LAB_NAS_ROOT:-$(envget LAB_NAS_ROOT)}
  repo=$BACKUP_REPO
  [[ "$data" == /* && "$repo" == /* ]] ||
    die "NAS 模式需要以绝对路径设置 LAB_NAS_ROOT 和 BACKUP_REPO"
  data=$(realpath -e -- "$data") && repo=$(realpath -e -- "$repo") ||
    die "无法确认主存储或备份目录"
  # The directory restic would mount must be the one the site serves: a LAB_NAS_ROOT changed in .env or this shell
  # since it started (an old copy of the disk keeps the same storage id) would back up or restore the wrong files.
  if [[ -n $SITE_BACKEND ]]; then
    serving=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$SITE_BACKEND") &&
      serving=$(realpath -e -- "$serving") || die "无法确认网站正在用的 NAS 目录，没有做任何操作"
    [[ $serving == "$data" ]] ||
      die "LAB_NAS_ROOT（$data）不是网站正在用的 NAS 目录（$serving），没有做任何操作"
  fi
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
