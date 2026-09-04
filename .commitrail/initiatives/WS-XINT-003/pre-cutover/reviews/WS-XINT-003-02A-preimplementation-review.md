# Preimplementation Review: WS-XINT-003-02A

## Result

Parent `WS-XINT-003-02` failed L1 architecture, security, product/operations,
and QA plan review before runtime edits. It is superseded by 02A and 02B.

## Blocking findings incorporated

- Existing unique `(project_id, guide_version)` policy rows cannot express
  immutable replacements for one draft guide.
- Task, Submission, and CheckerRun incorrectly use guide version as policy
  identity; activation before lineage repair would be unsafe.
- A new generic policy repository risked duplicating the sole writer. 02B may
  add only a replay-ledger repository; `ProjectRepository` remains the only
  policy-table persistence owner.
- Draft-only final consumption, active-guide freeze, exact provenance, committed
  replay recovery, and typed REV policy semantics were not strong enough.
- Focused test, coverage, and API-contract commands were not fully isolated or
  complete.

## Corrective boundary

02A owns immutable policy identity, explicit typed semantics, guide selection,
and exact Task/Submission/CheckerRun locks while both actions stay unavailable.
02B later owns the sole public writer, PREP, replay custody, provenance, and
activation of exactly two actions.

The refreshed 02A candidate requires a new focused L1 plan-review pass before
implementation.
