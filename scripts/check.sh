#!/usr/bin/env bash
# Full local check: decision notes, migrations up to date, backend tests, frontend tests + typecheck + build.
# Usage: PYTHON=/path/to/python scripts/check.sh   (PostgreSQL must be running)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python}"

# Node 22.18+ runs these .ts scripts directly, no tsx needed.
for s in verify-agent-note-tree verify-agent-note-format verify-archived-agent-notes; do
  node ".claude/skills/write-notes-like-deepseek/scripts/$s.ts"
done

"$PYTHON" -m unittest discover -s scripts/tests
(cd backend && "$PYTHON" manage.py makemigrations --check --dry-run && "$PYTHON" -m pytest)
(cd frontend && npm test && npm run build)
echo "ALL CHECKS PASSED"
