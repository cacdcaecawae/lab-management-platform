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
