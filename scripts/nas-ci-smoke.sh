#!/usr/bin/env bash
# GitHub-hosted PR smoke only. Never points at a deployment or loads its environment.
set -euo pipefail
umask 022
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted && -d "${RUNNER_TEMP:-}" ]] || { echo "Hosted CI only" >&2; exit 1; }
cd "$(dirname "$0")/.."
[[ ! -e .env && ! -L .env ]] || { echo "Do not load deployment configuration" >&2; exit 1; }
scratch=$(mktemp -d "$RUNNER_TEMP/labnas-smoke.XXXXXXXXXX")
project=labnassmoke-${scratch##*.}
export COMPOSE_PROJECT_NAME=${project,,}
export ENV_FILE="$scratch/fixture.env"
export COMPOSE_FILE="infra/docker-compose.prod.yml:infra/docker-compose.nas.yml:$scratch/safety.yml"
# No inherited settings can redirect tests to a deploy or substitute built images.
unset APP_VERSION IMAGE_PREFIX LAB_NAS_ROOT LAB_NAS_STORAGE_ID BACKUP_REPO BACKUP_PASSWORD BACKUP_MOUNTPOINT BACKUP_REPO_ID
unset DOCKER_HOST DOCKER_CONTEXT COMPOSE_PROFILES COMPOSE_PATH_SEPARATOR
export DOCKER_CONTEXT=default
dc() { docker compose --env-file "$ENV_FILE" "$@"; }
started=no
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "$started" == yes ]]; then
    if (( rc != 0 )); then dc logs --tail 60 >&2 || true; fi
    dc --profile ops down --volumes --remove-orphans || rc=1
  fi
  sudo rm -rf -- "$scratch" || rc=1
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -m 0755 "$scratch/primary" "$scratch/repository"
sudo install -d -m 0755 -o 1000 -g 1000 "$scratch/primary/files"
printf 'synthetic-only-marker\n' >"$scratch/primary/.lab-storage-id"
cat >"$ENV_FILE" <<CONFIG
APP_VERSION=local
POSTGRES_DB=lab
POSTGRES_USER=lab
POSTGRES_PASSWORD=synthetic-smoke-db
DJANGO_SECRET_KEY=synthetic-smoke-django
DJANGO_ALLOWED_HOSTS=localhost
DJANGO_SECURE_COOKIES=0
LAB_NAS_ROOT=$scratch/primary
LAB_NAS_STORAGE_ID=synthetic-only-marker
BACKUP_REPO=$scratch/repository
BACKUP_PASSWORD=synthetic-smoke-repo
CONFIG
cat >"$scratch/safety.yml" <<'CONFIG'
services:
  web:
    ports: !reset []
networks:
  default:
    internal: true
CONFIG

dc --profile ops config --format json | python3 -c '
import json, sys
plan = json.load(sys.stdin)
assert all(not config.get("ports") for config in plan["services"].values())
assert plan["networks"]["default"]["internal"] is True
'
for resource in "container ls -aq" "volume ls -q" "network ls -q"; do
  read -r -a words <<<"$resource"
  existing=$(docker "${words[@]}" --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME")
  [[ -z "$existing" ]] || {
    echo "Fixture project already exists" >&2; exit 1;
  }
done
started=yes
dc up -d --build --wait --wait-timeout 120 db backend web
for _ in {1..30}; do
  if dc exec -T web wget -q -O /dev/null --header "Host: localhost" http://127.0.0.1/api/auth/csrf/; then break; fi
  sleep 2
done
dc exec -T web wget -q -O /dev/null --header "Host: localhost" http://127.0.0.1/api/auth/csrf/

# Use Django's real storage implementation in the backend container.
dc exec -T backend python manage.py shell <<'PY'
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
assert default_storage.save("smoke.bin", ContentFile(b"synthetic-smoke-bytes")) == "smoke.bin"
PY
[[ "$(cat "$scratch/primary/files/smoke.bin")" == synthetic-smoke-bytes ]]
psql_in_fixture() { dc exec -T db psql -X -qtA -v ON_ERROR_STOP=1 -U lab -d lab "$@"; }
psql_in_fixture -c "CREATE TABLE smoke_sentinel (token text); INSERT INTO smoke_sentinel VALUES ('pre-backup');"
printf 'outside-fixture-stays\n' >"$scratch/primary/outside.txt"
bash scripts/backup.sh --init
repo_id=$(bash scripts/backup.sh --repo-id)
[[ "$repo_id" =~ ^[0-9a-f]{64}$ ]]
printf 'BACKUP_REPO_ID=%s\n' "$repo_id" >>"$ENV_FILE"
bash scripts/backup.sh smoke
psql_in_fixture -c "UPDATE smoke_sentinel SET token='after-backup';"
sudo rm -- "$scratch/primary/files/smoke.bin"
printf 'obsolete\n' | sudo tee "$scratch/primary/files/obsolete" >/dev/null
bash scripts/restore.sh latest --yes
[[ "$(cat "$scratch/primary/files/smoke.bin")" == synthetic-smoke-bytes ]]
[[ "$(psql_in_fixture -c 'SELECT token FROM smoke_sentinel;')" == pre-backup ]]
[[ ! -e "$scratch/primary/files/obsolete" ]]
[[ "$(cat "$scratch/primary/outside.txt")" == outside-fixture-stays ]]
[[ "$(cat "$scratch/primary/.lab-storage-id")" == synthetic-only-marker ]]

# An unexpected mount identity must not silently write to the storage destination.
printf 'wrong-synthetic-marker\n' >"$scratch/primary/.lab-storage-id"
dc exec -T backend python manage.py shell <<'PY'
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from core.nas_storage import StorageUnavailable
try:
    default_storage.save("must-not-write.bin", ContentFile(b"blocked-synthetic-bytes"))
except StorageUnavailable:
    pass
else:
    raise AssertionError("backend accepted a mismatched NAS marker")
PY
[[ ! -e "$scratch/primary/files/must-not-write.bin" ]]
if bash scripts/backup.sh smoke; then
  echo "Backup unexpectedly accepted wrong NAS marker" >&2
  exit 1
fi
echo "Synthetic NAS marker, backup and restore passed"
