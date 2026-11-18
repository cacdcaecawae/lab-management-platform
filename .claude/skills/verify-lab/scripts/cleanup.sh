#!/usr/bin/env bash
# Stop what launch.sh started (by recorded PID, never by process name), drop lab_verify, remove run state.
# Evidence under backend/var/verify-evidence/ is kept.
# Usage: .claude/skills/verify-lab/scripts/cleanup.sh
set -uo pipefail
source "$(dirname "$0")/env.sh"

for name in chrome vite backend; do
  for f in winpid port-pid; do  # tree root (cmd.exe / chrome) and the process that owned the port
    pid=$(cat "$STATE/$name.$f" 2>/dev/null || true)
    [ -n "$pid" ] && taskkill //PID "$pid" //T //F >/dev/null 2>&1 && echo "stopped $name (PID $pid)"
  done
done

(cd "$REPO/backend" && POSTGRES_DB=postgres "$PY" manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute('DROP DATABASE IF EXISTS lab_verify WITH (FORCE)')
") && echo "dropped database lab_verify"

for _ in $(seq 20); do rm -rf "$STATE" 2>/dev/null && break; sleep 0.5; done  # Chrome may hold the profile briefly
[ -e "$STATE" ] && echo "could not remove $STATE" || echo "removed $STATE"
echo "evidence kept in $EVIDENCE_W"
