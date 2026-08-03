# Status: WS-XINT-003 REV-AUTH End-to-End Contract

## Current status

WS-XINT-003-01 and WS-XINT-003-02A are merged. WS-XINT-003-02B policy mutation
activation is the active bounded implementation chunk from `origin/main` at
`2c24c91d`. No policy mutation action or public surface was active at its
starting baseline.

## Baseline

- Planning branch began from `origin/main` at `99dc0b34` after AUTH-12D merged.
- Existing REV actions remain planned/unreleased as product surfaces.
- XINT-002 remains the owner of review artifact materialization/binding and
  human-review submission-artifact activation.

## Main finding

REV-03P and AUTH-12D2 overlap around review/revision policy persistence and
mutation. The first implementation wave must settle one persistence path:
REV-owned semantics with AUTH-owned mutation authorization.

## Current reconciliation

- `ACTION_CUSTODY.md` is the canonical action/principal/resource/wave table.
- REV-03P and AUTH-12D2 name one future append-only policy writer path.
- Runtime owner XINT-002-07 has one approved v0.1 sub-wave: 07A packet
  materialization. Evidence binding remains planned/unavailable and 07B is
  reserved pending separate REV-owned intent.
- All registered review actions remain planned; four lifecycle/recovery actions
  remain missing until 08R; no service identity is provisioned by chunk 01.

## WS-XINT-003-02A implementation

- ReviewPolicy and RevisionPolicy are append-only identities with generation,
  canonical digest, semantics status, and predecessor lineage.
- ProjectGuide selects exact policy identities; Task locks them, and Submission
  and CheckerRun copy and foreign-key chain the same immutable facts.
- Historical rows become readable `legacy_incomplete` records and fail the
  canonical readiness predicate. No preference or lease meaning is inferred.
- PostgreSQL rejects update, delete, truncate, cross-project/guide lineage, and
  unsafe populated downgrade.
- Focused migration, activation, task, submission/checker, digest, and coverage
  proof is green. Repository-wide coverage remains assigned to hosted CI.

## Next step

WS-XINT-003-02B implementation and internal review are complete. Open the PR,
run exact-head hosted review, resolve every valid external finding, obtain human
merge, and stop before review lifecycle activation.
