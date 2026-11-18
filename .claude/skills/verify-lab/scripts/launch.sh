#!/usr/bin/env bash
# Start a fresh, isolated verification instance:
#   database lab_verify (dropped, migrated, seeded) -> Django :8100 -> Vite :5273 -> headless Chrome :9222.
# Refuses to start if any of those ports is already taken: never drive an instance this run did not start.
# Usage: bash .claude/skills/verify-lab/scripts/launch.sh
set -euo pipefail
source "$(dirname "$0")/env.sh"

for port in $BACKEND_PORT $VITE_PORT $CHROME_PORT; do
  owner=$(port_owner "$port")
  if [ -n "$owner" ]; then
    echo "port $port is already in use by PID $owner. Run cleanup.sh if it is a previous verify-lab run; otherwise stop." >&2
    exit 1
  fi
done

rm -rf "$STATE"
mkdir -p "$STATE/data" "$STATE/files" "$EVIDENCE"

echo "== database lab_verify: recreate, migrate, seed"
(cd "$REPO/backend" && POSTGRES_DB=postgres "$PY" manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute('DROP DATABASE IF EXISTS lab_verify WITH (FORCE)')
    c.execute('CREATE DATABASE lab_verify')
" >/dev/null)
(cd "$REPO/backend" && "$PY" manage.py migrate --noinput >"$STATE/migrate.log")
SEED="$REPO_W/.claude/skills/verify-lab/scripts/seed.py" dj "import os; exec(open(os.environ['SEED'], encoding='utf-8').read())" | tail -1

# Upload fixtures with known content; their SHA256 is written next to them for comparison.
printf 't,amp\n0,0.00\n1,0.42\n2,0.31\n' >"$STATE/files/wave_001.csv"
printf 't,amp\n0,0.00\n1,0.57\n2,0.12\n' >"$STATE/files/wave_002.csv"
# 1x1 PNG for the equipment usage-report photo
printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==' | base64 -d >"$STATE/files/photo.png"
# one-page PDF for procurement attachments (quotes, invoices)
printf '%s\n' '%PDF-1.4' '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj' '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj' \
  '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj' 'trailer<</Root 1 0 R>>' '%%EOF' >"$STATE/files/quote.pdf"
# stand-in for meeting slides: the server keeps any file type and never opens it
printf 'PK slides\n' >"$STATE/files/slides.pptx"
(cd "$STATE/files" && sha256sum wave_*.csv photo.png quote.pdf slides.pptx >SHA256SUMS)

# spawn <name> <windows workdir> <windows exe> <argument string>
# Starts the process detached through Start-Process (ShellExecute). A child started with `&` would inherit this
# shell's stdout pipe on Windows, and the caller (e.g. an agent's Bash tool) would never return.
# Records the Windows PID of the process-tree root; cleanup.sh kills that tree.
spawn() {
  powershell.exe -NoProfile -Command \
    "(Start-Process -FilePath '$3' -ArgumentList '$4' -WorkingDirectory '$2' -WindowStyle Hidden -PassThru).Id" \
    | tr -d '\r' >"$STATE/$1.winpid"
}
# wait_for <name> <port> <url>: poll until the URL answers 2xx (csrf/ is 204), then record which PID owns the port.
wait_for() {
  for _ in $(seq 120); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' "$3")" == 2* ]]; then
      port_owner "$2" >"$STATE/$1.port-pid"
      return 0
    fi
    sleep 0.5
  done
  echo "$1 did not become ready at $3" >&2
  tail -20 "$STATE/$1.log" >&2 2>/dev/null
  exit 1
}
PY_W=$(cd "$(dirname "$PY")" && pwd -W)/$(basename "$PY")
PY_W=${PY_W//\//\\}   # cmd.exe needs backslashes

echo "== Django :$BACKEND_PORT"
spawn backend "$REPO_W/backend" cmd.exe \
  "/c $PY_W manage.py runserver 127.0.0.1:$BACKEND_PORT --noreload > var\\verify\\backend.log 2>&1"
wait_for backend "$BACKEND_PORT" "http://127.0.0.1:$BACKEND_PORT/api/auth/csrf/"

echo "== Vite :$VITE_PORT"
spawn vite "$REPO_W/frontend" cmd.exe \
  "/c node node_modules\\vite\\bin\\vite.js --host 127.0.0.1 --port $VITE_PORT --strictPort > ..\\backend\\var\\verify\\vite.log 2>&1"
wait_for vite "$VITE_PORT" "$APP_URL/api/auth/csrf/"   # through the Vite proxy, so both hops work
wait_for vite "$VITE_PORT" "$APP_URL/login"

echo "== headless Chrome :$CHROME_PORT"
spawn chrome "$STATE_W" "$CHROME_W" "--headless=new --remote-debugging-port=$CHROME_PORT \
--user-data-dir=$STATE_W/chrome-profile --no-first-run --no-default-browser-check --window-size=1440,960 about:blank"
wait_for chrome "$CHROME_PORT" "http://127.0.0.1:$CHROME_PORT/json/version"

echo
echo "READY  app: $APP_URL   accounts: s_a s_b s_new mgr adv x_mgr ops / Verify-2026!"
echo "upload fixtures: $STATE_W/files"
echo "evidence root:   $EVIDENCE_W"
