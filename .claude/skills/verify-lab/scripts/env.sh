# Shared settings for the verify-lab scripts. Sourced, not run.
# Everything here is isolated from the normal dev setup (db "lab", Django :8000, Vite :5173).

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
PY=${PYTHON:-/d/anaconda/conda/envs/lab-platform/python.exe}
CHROME_W=${CHROME_W:-'C:\Program Files\Google\Chrome\Application\chrome.exe'}

BACKEND_PORT=8100
VITE_PORT=5273
CHROME_PORT=9222   # fixed: the chrome-devtools MCP server connects to 127.0.0.1:9222
APP_URL="http://127.0.0.1:$VITE_PORT"

STATE="$REPO/backend/var/verify"             # run state: pids, logs, uploads, chrome profile; removed by cleanup
EVIDENCE="$REPO/backend/var/verify-evidence"  # proof artifacts; never removed by the scripts
# Windows forms for python/chrome. `pwd -W`, not cygpath: a conda cygpath earlier on PATH maps /f/ wrongly.
REPO_W=$(cd "$REPO" && pwd -W)
STATE_W="$REPO_W/backend/var/verify"
EVIDENCE_W="$REPO_W/backend/var/verify-evidence"

# Read by Django settings (real env vars win over .env) and by Vite.
export POSTGRES_DB=lab_verify
export DATA_ROOT="$STATE_W/data"
export DJANGO_CSRF_TRUSTED_ORIGINS="$APP_URL,http://localhost:$VITE_PORT"
export VITE_BACKEND="http://127.0.0.1:$BACKEND_PORT"

# Windows PID listening on a TCP port, or empty.
# No early `exit` in awk: closing the pipe early can SIGPIPE netstat and, under pipefail, abort the caller silently.
port_owner() { netstat -ano | awk -v p=":$1" '$1=="TCP" && $2 ~ p"$" && $4=="LISTENING" && !found {print $5; found=1}'; }
# Run Python inside Django against lab_verify: dj 'from accounts.models import User; print(User.objects.count())'
dj() { (cd "$REPO/backend" && "$PY" manage.py shell -c "$1"); }
