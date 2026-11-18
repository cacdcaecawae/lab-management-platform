---------------------------- MODULE EquipmentBooking ----------------------------
(***************************************************************************)
(* Concurrent requests on one piece of equipment and its bookings, as the  *)
(* code runs them on PostgreSQL (READ COMMITTED, no ATOMIC_REQUESTS):      *)
(*   create  BookingViewSet.perform_create        backend/equipment/views.py *)
(*   report  BookingViewSet.report                backend/equipment/views.py *)
(*   cancel  BookingViewSet.cancel                backend/equipment/views.py *)
(*   edit    EquipmentViewSet.partial_update -> EquipmentSerializer.update *)
(*           (serializers.py), sent by EquipmentFormDialog.vue             *)
(* One action = one SQL statement on a shared row; the Python checks on   *)
(* its result are folded into it. SKILL.md maps every action to the code. *)
(***************************************************************************)
EXTENDS Naturals

CONSTANTS
    Procs,         \* concurrent requests, e.g. {1, 2, 3}; each process makes one request
    RequestKinds,  \* subset of {"create", "report", "cancel", "edit"}
    EditBodies,    \* status values an edit PATCH may carry: "omit" (no status in the body) and/or Statuses
    Slots,         \* booking times, abstracted: two bookings overlap iff same slot; must contain 1 and 2
    Mutant         \* "none" = the code as it is; otherwise one named break (see the Mutant = ... branches)

None == 0
\* "repair" stands for every status a manager sets by hand (repair, retired): not bookable, not needs_check.
Statuses == {"available", "needs_check", "repair"}
\* Bookings 1 and 2 exist at the start; process p's create inserts booking 2 + p.
NewBooking(p) == 2 + p
Bookings == {1, 2} \cup {NewBooking(p) : p \in Procs}

VARIABLES
    eStatus,    \* equipment.status, committed
    eLock,      \* holder of the equipment row lock (SELECT ... FOR UPDATE or UPDATE), or None
    eNewBy,     \* process with an uncommitted write of equipment.status, or None
    eNewVal,    \* that uncommitted value ("available" when there is none)
    bExists,    \* booking row committed
    bInsBy,     \* process with an uncommitted INSERT of the booking, or None
    bKind,      \* "use" | "maintenance"
    bSlot,      \* booking time slot
    bStarted,   \* start_at <= now
    bCancelled, \* cancelled_at set, committed
    bCancelBy,  \* process with an uncommitted UPDATE of cancelled_at, or None
    bLock,      \* holder of the booking row lock, or None
    rCount,     \* committed usage reports of the booking
    rInsBy,     \* process with an uncommitted INSERT of a usage report for the booking, or None
    pc,         \* per process: next step
    loc,        \* per process: request parameters, what it read, and its response
    flagged,    \* ghost: an abnormal report turned the equipment to needs_check; no manager has handled it yet
    bookedWhileFlagged  \* ghost, per booking: a use booking committed while flagged

eqVars == <<eStatus, eLock, eNewBy, eNewVal>>
bkVars == <<bExists, bInsBy, bKind, bSlot, bStarted, bCancelled, bCancelBy, bLock>>
rVars == <<rCount, rInsBy>>
ghost == <<flagged, bookedWhileFlagged>>
vars == <<eqVars, bkVars, rVars, pc, loc, ghost>>

DefaultLoc == [req |-> "none", bk |-> "use", slot |-> 1, tgt |-> None, cond |-> "normal",
               role |-> "student", formSeen |-> "available", sent |-> "omit", seen |-> "available",
               out |-> "none"]

Init ==
    /\ eStatus = "available" /\ eLock = None /\ eNewBy = None /\ eNewVal = "available"
    /\ bExists = [b \in Bookings |-> b \in {1, 2}]
    /\ bInsBy = [b \in Bookings |-> None]
    /\ bKind = [b \in Bookings |-> "use"]
    /\ bSlot = [b \in Bookings |-> IF b = 2 THEN 2 ELSE 1]
    /\ bStarted = [b \in Bookings |-> b = 1]   \* booking 1 is under way, booking 2 is in the future
    /\ bCancelled = [b \in Bookings |-> FALSE]
    /\ bCancelBy = [b \in Bookings |-> None]
    /\ bLock = [b \in Bookings |-> None]
    /\ rCount = [b \in Bookings |-> 0]
    /\ rInsBy = [b \in Bookings |-> None]
    /\ pc = [p \in Procs |-> "idle"]
    /\ loc = [p \in Procs |-> DefaultLoc]
    /\ flagged = FALSE
    /\ bookedWhileFlagged = [b \in Bookings |-> FALSE]

-----------------------------------------------------------------------------
Free(holder, p) == holder \in {None, p}
Release(f, p) == [b \in DOMAIN f |-> IF f[b] = p THEN None ELSE f[b]]
Goto(p, step) == pc' = [pc EXCEPT ![p] = step]

\* The transaction rolls back: p's uncommitted writes and its locks go away; the response is o.
Rollback(p, o) ==
    /\ eLock' = IF eLock = p THEN None ELSE eLock
    /\ eNewBy' = IF eNewBy = p THEN None ELSE eNewBy
    /\ eNewVal' = IF eNewBy = p THEN "available" ELSE eNewVal
    /\ bInsBy' = Release(bInsBy, p)
    /\ bCancelBy' = Release(bCancelBy, p)
    /\ bLock' = Release(bLock, p)
    /\ rInsBy' = Release(rInsBy, p)
    /\ pc' = [pc EXCEPT ![p] = "done"]
    /\ loc' = [loc EXCEPT ![p].out = o]
    /\ UNCHANGED <<eStatus, bExists, bKind, bSlot, bStarted, bCancelled, rCount, ghost>>

\* A manager handles the abnormal report: the edit form showed "needs_check" and the PATCH sets another status.
Handles(p) == loc[p].req = "edit" /\ loc[p].formSeen = "needs_check" /\ loc[p].sent \notin {"omit", "needs_check"}

\* The transaction commits: p's writes become visible to everyone and its locks are released.
Commit(p) ==
    /\ eStatus' = IF eNewBy = p THEN eNewVal ELSE eStatus
    /\ eNewBy' = IF eNewBy = p THEN None ELSE eNewBy
    /\ eNewVal' = IF eNewBy = p THEN "available" ELSE eNewVal
    /\ eLock' = IF eLock = p THEN None ELSE eLock
    /\ bExists' = [b \in Bookings |-> bExists[b] \/ bInsBy[b] = p]
    /\ bInsBy' = Release(bInsBy, p)
    /\ bCancelled' = [b \in Bookings |-> bCancelled[b] \/ bCancelBy[b] = p]
    /\ bCancelBy' = Release(bCancelBy, p)
    /\ bLock' = Release(bLock, p)
    /\ rCount' = [b \in Bookings |-> rCount[b] + (IF rInsBy[b] = p THEN 1 ELSE 0)]
    /\ rInsBy' = Release(rInsBy, p)
    /\ flagged' = CASE loc[p].req = "report" /\ eNewBy = p -> TRUE
                    [] Handles(p) -> FALSE
                    [] OTHER -> flagged
    /\ bookedWhileFlagged' =
          [b \in Bookings |-> bookedWhileFlagged[b] \/ (bInsBy[b] = p /\ bKind[b] = "use" /\ flagged)]
    /\ pc' = [pc EXCEPT ![p] = "done"]
    /\ loc' = [loc EXCEPT ![p].out = "ok"]
    /\ UNCHANGED <<bKind, bSlot, bStarted>>

-----------------------------------------------------------------------------
(* create: POST /api/bookings/. A maintenance booking is a manager's (a    *)
(* student's is a 403 before any SQL, so it is not modelled).             *)

CreateStart(p) ==
    /\ pc[p] = "idle" /\ "create" \in RequestKinds
    /\ \E k \in {"use", "maintenance"}, s \in Slots :
          loc' = [loc EXCEPT ![p].req = "create", ![p].bk = k, ![p].slot = s]
    /\ Goto(p, "create_lock_equipment")
    /\ UNCHANGED <<eqVars, bkVars, rVars, ghost>>

\* transaction.atomic(); Equipment.objects.select_for_update().get(pk=...);
\* a use booking needs status "available", else Conflict (409).
CreateLockEquipment(p) ==
    LET noLock == Mutant = "create_without_equipment_lock" IN   \* break: a plain SELECT, no row lock
    /\ pc[p] = "create_lock_equipment"
    /\ noLock \/ Free(eLock, p)
    /\ IF loc[p].bk = "use" /\ eStatus # "available"
       THEN Rollback(p, "409")
       ELSE /\ eLock' = IF noLock THEN eLock ELSE p
            /\ Goto(p, "create_insert_booking")
            /\ UNCHANGED <<eStatus, eNewBy, eNewVal, bkVars, rVars, loc, ghost>>

\* serializer.save(): INSERT INTO booking. The exclusion constraint no_overlapping_bookings first waits for any
\* other open transaction that is inserting or cancelling an overlapping booking, then rejects a live overlap:
\* IntegrityError, which perform_create turns into Conflict (409).
Overlaps(p, b) == b # NewBooking(p) /\ bSlot[b] = loc[p].slot
Undecided(p, b) == bInsBy[b] \notin {None, p} \/ (bExists[b] /\ bCancelBy[b] \notin {None, p})
Live(b) == bExists[b] /\ ~bCancelled[b]

CreateInsertBooking(p) ==
    LET nb == NewBooking(p) IN
    /\ pc[p] = "create_insert_booking"
    /\ ~\E b \in Bookings : Overlaps(p, b) /\ Undecided(p, b)
    /\ IF \E b \in Bookings : Overlaps(p, b) /\ Live(b)
       THEN Rollback(p, "409")
       ELSE /\ bInsBy' = [bInsBy EXCEPT ![nb] = p]
            /\ bKind' = [bKind EXCEPT ![nb] = loc[p].bk]
            /\ bSlot' = [bSlot EXCEPT ![nb] = loc[p].slot]
            /\ Goto(p, "create_commit")
            /\ UNCHANGED <<eqVars, bExists, bStarted, bCancelled, bCancelBy, bLock, rVars, loc, ghost>>

CreateCommit(p) == pc[p] = "create_commit" /\ Commit(p)

-----------------------------------------------------------------------------
(* report: POST /api/bookings/{id}/report/ by the booking's user (anyone  *)
(* else gets a 403 before any SQL).                                        *)

ReportStart(p) ==
    /\ pc[p] = "idle" /\ "report" \in RequestKinds
    /\ \E b \in Bookings, c \in {"normal", "abnormal"} :
          /\ bExists[b]   \* get_object() finds committed rows only
          /\ loc' = [loc EXCEPT ![p].req = "report", ![p].tgt = b, ![p].cond = c]
    /\ Goto(p, "report_lock_booking")
    /\ UNCHANGED <<eqVars, bkVars, rVars, ghost>>

\* transaction.atomic(); lock_booking() = SELECT ... FOR UPDATE; then 409 unless: kind is "use", not cancelled,
\* started, and UsageReport.objects.filter(booking=booking).exists() is false.
ReportLockBooking(p) ==
    LET b == loc[p].tgt
        noLock == Mutant = "report_without_booking_lock"   \* break: a plain SELECT, no row lock
    IN
    /\ pc[p] = "report_lock_booking"
    /\ noLock \/ Free(bLock[b], p)
    /\ IF \/ bKind[b] # "use"
          \/ (bCancelled[b] /\ Mutant # "report_skips_cancelled_check")   \* break: check removed
          \/ ~bStarted[b]
          \/ rCount[b] > 0
       THEN Rollback(p, "409")
       ELSE /\ bLock' = IF noLock THEN bLock ELSE [bLock EXCEPT ![b] = p]
            /\ Goto(p, "report_insert")
            /\ UNCHANGED <<eqVars, bExists, bInsBy, bKind, bSlot, bStarted, bCancelled, bCancelBy, rVars, loc, ghost>>

\* body.save(booking=booking): INSERT INTO usage report. UsageReport.booking is a OneToOneField (unique): the
\* insert waits for another open transaction inserting a report for the same booking; a duplicate raises
\* IntegrityError, which report() does not catch: 500.
ReportInsert(p) ==
    LET b == loc[p].tgt IN
    /\ pc[p] = "report_insert"
    /\ rInsBy[b] \in {None, p}
    /\ IF rCount[b] > 0
       THEN Rollback(p, "500")
       ELSE /\ rInsBy' = [rInsBy EXCEPT ![b] = p]
            /\ Goto(p, IF loc[p].cond = "abnormal" THEN "report_mark_equipment" ELSE "report_commit")
            /\ UNCHANGED <<eqVars, bkVars, rCount, loc, ghost>>

\* Abnormal: Equipment.objects.select_for_update().get(...); if status is "available", set "needs_check", save().
ReportMarkEquipment(p) ==
    /\ pc[p] = "report_mark_equipment"
    /\ Free(eLock, p)
    /\ eLock' = p
    /\ IF eStatus = "available"
       THEN eNewBy' = p /\ eNewVal' = "needs_check"
       ELSE UNCHANGED <<eNewBy, eNewVal>>
    /\ Goto(p, "report_commit")
    /\ UNCHANGED <<eStatus, bkVars, rVars, loc, ghost>>

ReportCommit(p) == pc[p] = "report_commit" /\ Commit(p)

-----------------------------------------------------------------------------
(* cancel: POST /api/bookings/{id}/cancel/ by the booking's user (a       *)
(* student) or a manager.                                                  *)

CancelStart(p) ==
    /\ pc[p] = "idle" /\ "cancel" \in RequestKinds
    /\ \E b \in Bookings, r \in {"student", "manager"} :
          /\ bExists[b]
          /\ loc' = [loc EXCEPT ![p].req = "cancel", ![p].tgt = b, ![p].role = r]
    /\ Goto(p, "cancel_lock_booking")
    /\ UNCHANGED <<eqVars, bkVars, rVars, ghost>>

\* transaction.atomic(); lock_booking(); then 409 if cancelled, if a student's booking has started, or if
\* UsageReport.objects.filter(booking=booking).exists().
CancelLockBooking(p) ==
    LET b == loc[p].tgt IN
    /\ pc[p] = "cancel_lock_booking"
    /\ Free(bLock[b], p)
    /\ IF \/ bCancelled[b]
          \/ (loc[p].role = "student" /\ bStarted[b])
          \/ (rCount[b] > 0 /\ Mutant # "cancel_skips_report_check")   \* break: check removed
       THEN Rollback(p, "409")
       ELSE /\ bLock' = [bLock EXCEPT ![b] = p]
            /\ Goto(p, "cancel_update")
            /\ UNCHANGED <<eqVars, bExists, bInsBy, bKind, bSlot, bStarted, bCancelled, bCancelBy, rVars, loc, ghost>>

\* booking.save(update_fields=["cancelled_at"]): UPDATE booking (the row is already locked).
CancelUpdate(p) ==
    /\ pc[p] = "cancel_update"
    /\ bCancelBy' = [bCancelBy EXCEPT ![loc[p].tgt] = p]
    /\ Goto(p, IF Mutant = "cancel_then_lock_equipment" THEN "cancel_lock_equipment" ELSE "cancel_commit")
    /\ UNCHANGED <<eqVars, bExists, bInsBy, bKind, bSlot, bStarted, bCancelled, bLock, rVars, loc, ghost>>

\* Break only: the equipment row is locked after the booking was updated (the opposite order to create).
CancelLockEquipment(p) ==
    /\ pc[p] = "cancel_lock_equipment"
    /\ Free(eLock, p)
    /\ eLock' = p
    /\ Goto(p, "cancel_commit")
    /\ UNCHANGED <<eStatus, eNewBy, eNewVal, bkVars, rVars, loc, ghost>>

CancelCommit(p) == pc[p] = "cancel_commit" /\ Commit(p)

-----------------------------------------------------------------------------
(* edit: a manager changes the equipment. EquipmentFormDialog.vue fills   *)
(* its form, status included, when it opens; on save it PATCHes only the  *)
(* fields that differ from what it opened with, so status is sent only    *)
(* when the manager changed it ("omit" otherwise), together with          *)
(* status_seen = the status the form showed (formSeen).                    *)

EditOpenForm(p) ==
    /\ pc[p] = "idle" /\ "edit" \in RequestKinds
    /\ \E s \in {b \in EditBodies : b # eStatus} :
          loc' = [loc EXCEPT ![p].req = "edit", ![p].formSeen = eStatus, ![p].sent = s]
    /\ Goto(p, "edit_read")
    /\ UNCHANGED <<eqVars, bkVars, rVars, ghost>>

\* PATCH /api/equipment/{id}/: UpdateModelMixin.update -> get_object(), a plain SELECT (no lock). What it read is
\* only used by the edit_writes_stale_status break.
EditRead(p) ==
    /\ pc[p] = "edit_read"
    /\ loc' = [loc EXCEPT ![p].seen = eStatus]
    /\ Goto(p, "edit_update")
    /\ UNCHANGED <<eqVars, bkVars, rVars, ghost>>

\* EquipmentSerializer.save(): transaction.atomic(); EquipmentSerializer.update() re-reads the row with
\* Equipment.objects.select_for_update().get(pk=...) (waits for the row lock, then sees the latest commit) and saves it
\* with the sent fields applied: status is the sent value, or the value read under the lock when the body has none.
\* A sent status is refused (Conflict stale_status, 409) when the status under the lock is neither status_seen nor
\* the sent value: the manager decided on a picture that has since changed.
EditUpdate(p) ==
    LET sent == loc[p].sent
        stale == /\ sent # "omit" /\ eStatus \notin {loc[p].formSeen, sent}
                 /\ Mutant # "edit_skips_status_seen_check"   \* break: no status_seen check
    IN
    /\ pc[p] = "edit_update"
    /\ Free(eLock, p)
    /\ IF stale
       THEN Rollback(p, "409")
       ELSE /\ eLock' = p
            /\ eNewBy' = p
            /\ eNewVal' = CASE sent # "omit" -> sent
                           [] Mutant = "edit_writes_stale_status" -> loc[p].seen   \* break: save get_object()'s copy
                           [] OTHER -> eStatus
            /\ Goto(p, "edit_commit")
            /\ UNCHANGED <<eStatus, bkVars, rVars, loc, ghost>>

EditCommit(p) == pc[p] = "edit_commit" /\ Commit(p)

-----------------------------------------------------------------------------
\* Time passes: a booking's start time arrives (BookingSerializer.validate keeps new start times from the past).
Tick ==
    /\ \E b \in Bookings : bExists[b] /\ ~bStarted[b] /\ bStarted' = [bStarted EXCEPT ![b] = TRUE]
    /\ UNCHANGED <<eqVars, bExists, bInsBy, bKind, bSlot, bCancelled, bCancelBy, bLock, rVars, pc, loc, ghost>>

\* Every request has finished: a normal end, not a deadlock.
Done == (\A p \in Procs : pc[p] = "done") /\ UNCHANGED vars

Next ==
    \/ Tick
    \/ Done
    \/ \E p \in Procs :
        \/ CreateStart(p) \/ CreateLockEquipment(p) \/ CreateInsertBooking(p) \/ CreateCommit(p)
        \/ ReportStart(p) \/ ReportLockBooking(p) \/ ReportInsert(p) \/ ReportMarkEquipment(p) \/ ReportCommit(p)
        \/ CancelStart(p) \/ CancelLockBooking(p) \/ CancelUpdate(p) \/ CancelLockEquipment(p) \/ CancelCommit(p)
        \/ EditOpenForm(p) \/ EditRead(p) \/ EditUpdate(p) \/ EditCommit(p)

Spec == Init /\ [][Next]_vars

-----------------------------------------------------------------------------
Holder == Procs \cup {None}
TypeOK ==
    /\ eStatus \in Statuses /\ eLock \in Holder /\ eNewBy \in Holder /\ eNewVal \in Statuses
    /\ bExists \in [Bookings -> BOOLEAN] /\ bInsBy \in [Bookings -> Holder]
    /\ bKind \in [Bookings -> {"use", "maintenance"}] /\ bSlot \in [Bookings -> Slots]
    /\ bStarted \in [Bookings -> BOOLEAN] /\ bCancelled \in [Bookings -> BOOLEAN]
    /\ bCancelBy \in [Bookings -> Holder] /\ bLock \in [Bookings -> Holder]
    /\ rCount \in [Bookings -> Nat] /\ rInsBy \in [Bookings -> Holder]
    /\ flagged \in BOOLEAN /\ bookedWhileFlagged \in [Bookings -> BOOLEAN]

\* 1. While an abnormal report waits for a manager, no use booking is created.
NoUseBookingWhileFlagged == \A b \in Bookings : ~bookedWhileFlagged[b]

\* 2. Meanwhile the equipment does not become "available" again.
NoSilentRevert == flagged => eStatus # "available"

\* 3. A booking is never both cancelled and reported.
NotCancelledAndReported == \A b \in Bookings : ~(bCancelled[b] /\ rCount[b] > 0)

\* 4. At most one usage report per booking, and a second report gets 409, not a server error.
OneReportNo500 ==
    /\ \A b \in Bookings : rCount[b] <= 1
    /\ \A p \in Procs : loc[p].out # "500"

\* 5. No cycle of lock waits: TLC's deadlock check (on by default; Done marks the normal end).
=============================================================================
