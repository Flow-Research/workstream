# Decisions: Parallel Initiative Execution

## D1: Concurrency unit is the initiative

Permit one active chunk in each distinct initiative. This matches the existing
ledger key and keeps cancellation, successor, and merge ownership unambiguous.

## D2: No arbitrary global cap

The signed loop will not invent a numeric repository-wide limit. Human dispatch,
available worktrees, CI capacity, and merge review provide operational bounds.

## D3: Worktrees are execution isolation, not authority

A separate worktree is recommended operationally but is not signed proof. Exact
main contracts and authority events remain canonical.

## D4: Conflicts are resolved before merge

Parallel starts allow work to proceed; they do not promise conflict-free merge.
Branches rebase onto trusted main and rerun proof before merge. Rebase does not
replace the signed selected contract or authorize scope drift.

## D5: Exact self-bootstrap only

Because the old global rule blocks this change while AUTH is active, the owning
PR may use a schema-v2 exact single-target certificate for WS-ENG-005-01 only.
It cannot authorize any later merge or start.

## D6: Parallel history requires forward-compatible recovery

Once a second initiative start is signed, the old global replay invariant is
historically incompatible. Any later restriction must preserve validation of
existing parallel events; rollback cannot rewrite or reinterpret the ledger.
