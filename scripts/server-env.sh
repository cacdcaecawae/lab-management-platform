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

need_backup_settings() {
  [ -n "$(envget BACKUP_REPO)" ] && [ -n "$(envget BACKUP_PASSWORD)" ] ||
    die "先在 $ENV_FILE 里设置 BACKUP_REPO（另一块硬盘上的目录）和 BACKUP_PASSWORD（备份的加密密码，另外抄一份保存）"
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
    wait "$pid" || :
    return 1
  fi
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
