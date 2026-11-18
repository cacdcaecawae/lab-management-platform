#!/usr/bin/env bash
# Read stored state from the verify-lab database (lab_verify), for side-effect proof.
# Usage: .claude/skills/verify-lab/scripts/query.sh '<python run inside Django shell>'
# Example: query.sh 'from datasets.models import DataFile; print(list(DataFile.objects.values_list("name", "sha256")))'
set -euo pipefail
source "$(dirname "$0")/env.sh"
dj "$1"
