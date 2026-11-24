#!/usr/bin/env bash
# Model-check the concurrent equipment requests (spec/EquipmentBooking.tla) with TLC and compare every run with
# the expected result below. Exit 0: all as expected and covered code unchanged since SYNC; 1: some result
# differs (or TLC could not run); 2: all as expected, but covered code changed since SYNC (review it, SKILL.md).
# Usage, from the repository root: bash .claude/skills/verify-equipment-tla/scripts/check.sh
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SKILL=$(cd "$HERE/.." && pwd)
REPO=$(cd "$SKILL/../../.." && pwd)

SYNC=4e87fc84c0673ee12679dd2a757636eee3cb4889   # last commit at which the model was confirmed to describe the covered code
COVERED=(
  backend/equipment/views.py
  backend/equipment/serializers.py
  backend/equipment/models.py
  frontend/src/modules/equipment/components/EquipmentFormDialog.vue
)
JAR=${TLA2TOOLS:-$HOME/.tlaplus/tla2tools.jar}
JAR_SHA256=936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88   # TLC 2.19 of 2024-08-08
RUN=${TLA_RUN_DIR:-${TEMP:-${TMPDIR:-/tmp}}/verify-equipment-tla}   # TLC output; outside the repo, kept until the next run

winpath() { (cd "$1" && { pwd -W 2>/dev/null || pwd; }); }   # Java on Windows needs C:/... paths

echo "== covered code changed since $SYNC (committed, staged and unstaged)"
drift=''
for ref in head index worktree; do
  case $ref in
    head) args=("$SYNC" HEAD) ;;
    index) args=(--cached "$SYNC") ;;
    worktree) args=("$SYNC") ;;
  esac
  delta=$(git -C "$REPO" diff --stat "${args[@]}" -- "${COVERED[@]}") ||
    { echo "git diff against $SYNC failed"; exit 1; }
  if [ -n "$delta" ]; then
    printf '%s:\n%s\n' "$ref" "$delta"
    drift=1
  fi
done
db_drift=$("${PYTHON:-python}" "$HERE/check_database_settings.py" "$REPO" "$SYNC")
case $? in
  0) ;;
  2) printf '%s\n' "$db_drift"; drift=1 ;;
  *) printf '%s\n' "$db_drift"; echo "database settings check failed"; exit 1 ;;
esac
[ -n "$drift" ] || echo "none"

[ -f "$JAR" ] || { echo "TLC not found at $JAR (set TLA2TOOLS)"; exit 1; }
sum=$( (sha256sum 2>/dev/null || shasum -a 256) <"$JAR" | cut -d' ' -f1)   # stdin: a backslash in the path would prefix the hash
[ "$sum" = "$JAR_SHA256" ] || { echo "TLC jar SHA256 is $sum, expected $JAR_SHA256 (TLC 2.19)"; exit 1; }
command -v java >/dev/null || { echo "java not found (TLC needs Java 11+)"; exit 1; }

rm -rf "$RUN" && mkdir -p "$RUN"
cp "$SKILL/spec/EquipmentBooking.tla" "$RUN/"   # an ASCII path for Java; the repo path has Chinese characters
RUN_W=$(winpath "$RUN")
JAR_W="$(winpath "$(dirname "$JAR")")/$(basename "$JAR")"

ALL='"create", "report", "cancel", "end", "edit"'
NO_EDIT='"create", "report", "cancel", "end"'
BODIES='"omit", "available", "needs_check", "repair"'
INVARIANTS="NoUseBookingWhileFlagged NoSilentRevert NotCancelledAndReported OneReportNo500 NoOverlap EndsOnlyStartedUse"
failed=0

# run <name> <request kinds> <edit bodies> <mutant> <expected: pass | invariant name | deadlock> <invariants...>
run() {
  local name=$1 kinds=$2 bodies=$3 mutant=$4 expect=$5
  shift 5
  {
    echo "CONSTANTS"
    echo "  Procs = {1, 2, 3}"
    echo "  Slots = {1, 2, 3}"
    echo "  RequestKinds = {$kinds}"
    echo "  EditBodies = {$bodies}"
    echo "  Mutant = \"$mutant\""
    echo "SPECIFICATION Spec"
    for inv in TypeOK "$@"; do echo "INVARIANT $inv"; done
  } >"$RUN/$name.cfg"
  local out got states
  out=$(cd "$RUN" && java -XX:+UseParallelGC -cp "$JAR_W" tlc2.TLC -workers auto \
        -metadir "$RUN_W/states/$name" -config "$RUN_W/$name.cfg" EquipmentBooking.tla 2>&1)
  echo "$out" >"$RUN/$name.log"
  if grep -q "No error has been found" <<<"$out"; then got=pass
  elif grep -qE "Invariant [A-Za-z0-9]+ is violated" <<<"$out"; then
    got=$(grep -oE "Invariant [A-Za-z0-9]+ is violated" <<<"$out" | head -1 | cut -d' ' -f2)
  elif grep -q "Deadlock reached" <<<"$out"; then got=deadlock
  else got=error
  fi
  states=$(grep -oE "[0-9,]+ distinct states found" <<<"$out" | tail -1)
  if [ "$got" = "$expect" ]; then
    printf 'ok    %-34s %-26s %s\n' "$name" "$got" "$states"
  else
    printf 'DIFF  %-34s expected %-17s got %-14s see %s\n' "$name" "$expect" "$got" "$RUN_W/$name.log"
    failed=1
  fi
}

echo "== TLC runs (1 equipment, bookings 1-2 plus one per request, 3 concurrent requests, slots 1-3)"
# The code as it is.
run interleavings              "$NO_EDIT" "$BODIES" none pass $INVARIANTS
run with-edits-patch-no-status "$ALL" '"omit"' none pass $INVARIANTS   # edits that leave status alone (F1)
run with-edits                 "$ALL" "$BODIES" none pass $INVARIANTS   # edits may also change status (R1)
# Breaks of the code: each property must still be able to fail.
run break-create-without-equipment-lock "$NO_EDIT" "$BODIES" create_without_equipment_lock NoUseBookingWhileFlagged NoUseBookingWhileFlagged
run break-cancel-skips-report-check     "$NO_EDIT" "$BODIES" cancel_skips_report_check NotCancelledAndReported NotCancelledAndReported
run break-report-skips-cancelled-check  "$NO_EDIT" "$BODIES" report_skips_cancelled_check NotCancelledAndReported NotCancelledAndReported
run break-report-without-booking-lock   "$NO_EDIT" "$BODIES" report_without_booking_lock OneReportNo500 OneReportNo500
run break-cancel-then-lock-equipment    "$NO_EDIT" "$BODIES" cancel_then_lock_equipment deadlock
run break-end-skips-started-check       "$NO_EDIT" "$BODIES" end_skips_started_check EndsOnlyStartedUse EndsOnlyStartedUse
# The edit guards: F1 (an omitted status keeps the latest value) and R1 (a sent status is checked against status_seen).
run break-edit-writes-stale-status      "$ALL" '"omit"' edit_writes_stale_status NoSilentRevert NoSilentRevert
run break-edit-skips-status-seen-check  "$ALL" "$BODIES" edit_skips_status_seen_check NoSilentRevert NoSilentRevert

echo "TLC logs and configs: $RUN_W"
[ "$failed" = 1 ] && exit 1
[ -n "$drift" ] && { echo "covered code changed since $SYNC: confirm the model still describes it (SKILL.md)"; exit 2; }
exit 0
