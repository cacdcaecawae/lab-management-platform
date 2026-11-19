#!/usr/bin/env bash
# Only valid for a newly provisioned loopback PostgreSQL service named lab_verify.
set -euo pipefail
case "${1:-}" in experiments|reports) ;; *) exit 2;; esac
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_ENVIRONMENT:-}" = github-hosted
test "${POSTGRES_DB:-}" = lab_verify
test "${POSTGRES_USER:-}" = lab_verify
test "${POSTGRES_PASSWORD:-}" = synthetic-ci-only
test "${DJANGO_SECRET_KEY:-}" = synthetic-browser-verification-only
test "${DJANGO_DEBUG:-}" = 1
test "${DB_HOST:-}" = 127.0.0.1
test "${DB_PORT:-}" = 5432
test "${DJANGO_SETTINGS_MODULE:-config.settings}" = config.settings
test -z "${PYTHONPATH:-}"
test "${VITE_BACKEND:-}" = http://127.0.0.1:8100
: "${RUNNER_TEMP:?Missing GitHub-hosted temporary directory}"
test "${BROWSER_EVIDENCE:-}" = "$RUNNER_TEMP/lab-browser-evidence"
test "${DATA_ROOT:-}" = "$RUNNER_TEMP/lab-browser-data"
test ! -e "$root/.env" && test ! -L "$root/.env"
test ! -e "$BROWSER_EVIDENCE" && test ! -L "$BROWSER_EVIDENCE"
test ! -e "$DATA_ROOT" && test ! -L "$DATA_ROOT"
export DJANGO_SETTINGS_MODULE=config.settings
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost
mkdir -m 700 "$BROWSER_EVIDENCE" "$DATA_ROOT"
logs=$(mktemp -d)
backend_pid='' frontend_pid=''
cleanup() {
  if [[ -n $frontend_pid ]]; then kill "$frontend_pid" 2>/dev/null || true; fi
  if [[ -n $backend_pid ]]; then kill "$backend_pid" 2>/dev/null || true; fi
  rm -rf "$logs"
}
trap cleanup EXIT
# Refuse to connect to a pre-existing app process. These ports belong only to this run.
python - <<'PY'
import socket
for port in (8100, 5273):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
PY
(
  cd "$root/backend"
  # Fail closed before any writes: inspect effective Django settings and confirm
  # this is the fresh PostgreSQL service, not an existing lab_verify database.
  python - <<'PYCODE'
import django
from django.conf import settings
from django.db import connection

django.setup()
database = settings.DATABASES["default"]
assert database["ENGINE"] == "django.db.backends.postgresql"
assert [database[key] for key in ("NAME", "USER", "HOST", "PORT", "PASSWORD")] == [
    "lab_verify", "lab_verify", "127.0.0.1", "5432", "synthetic-ci-only"
]
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user")
    assert cursor.fetchone() == ("lab_verify", "lab_verify")
    assert not connection.introspection.table_names(cursor)
PYCODE
  python manage.py migrate --noinput
  python manage.py shell < "$root/.claude/skills/verify-lab/scripts/seed.py"
)
(cd "$root/backend"; exec python manage.py runserver 127.0.0.1:8100 --noreload) >"$logs/django.log" 2>&1 &
backend_pid=$!
(cd "$root/frontend"; exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5273 --strictPort) >"$logs/vite.log" 2>&1 &
frontend_pid=$!
for _ in {1..40}; do
  if curl -fsS --max-time 2 http://127.0.0.1:5273/api/auth/csrf/ >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -fsS --max-time 2 http://127.0.0.1:5273/api/auth/csrf/ >/dev/null; then
  tail -n 30 "$logs/django.log" "$logs/vite.log"
  exit 1
fi
test -d "$root/backend"
(
  cd "$root/backend"
  PYTHONPATH="$root/backend" python \
    "$root/.claude/skills/verify-lab/scripts/browser/scenarios.py" "$1"
)
