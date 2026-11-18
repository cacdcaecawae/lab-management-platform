#!/usr/bin/env bash
# Read-only health check of the verify-lab instance. Exit 0 only if it is ours and usable.
# Usage: .claude/skills/verify-lab/scripts/doctor.sh
set -uo pipefail
source "$(dirname "$0")/env.sh"
fail=0
ok() { echo "ok    $*"; }
bad() { echo "FAIL  $*"; fail=1; }

for pair in backend:$BACKEND_PORT vite:$VITE_PORT chrome:$CHROME_PORT; do
  name=${pair%%:*} port=${pair##*:}
  ours=$(cat "$STATE/$name.port-pid" 2>/dev/null || true)
  owner=$(port_owner "$port")
  if [ -z "$ours" ]; then bad "$name: no PID file, not started by launch.sh"
  elif [ -z "$owner" ]; then bad "$name: nothing listening on :$port (log: $STATE/$name.log)"
  elif [ "$owner" != "$ours" ]; then bad "$name: :$port is owned by PID $owner, launch.sh started PID $ours"
  else ok "$name PID $ours owns :$port"
  fi
done

code=$(curl -s -o /dev/null -w '%{http_code}' "$APP_URL/api/auth/csrf/")
[ "$code" = 204 ] && ok "$APP_URL/api/auth/csrf/ -> 204 (Vite proxy -> Django)" || bad "$APP_URL/api/auth/csrf/ -> $code"

users=$(dj "from accounts.models import User; print(User.objects.filter(username__in=['s_a','s_b','s_new','mgr','adv','x_mgr','ops']).count())" 2>&1 | tail -1)
[ "$users" = 7 ] && ok "database lab_verify has the 7 seeded accounts" || bad "database lab_verify seeded accounts: $users"

echo "info  code: $(git -C "$REPO" log -1 --format='%h %s') ; uncommitted files: $(git -C "$REPO" status --porcelain | wc -l)"
exit $fail
