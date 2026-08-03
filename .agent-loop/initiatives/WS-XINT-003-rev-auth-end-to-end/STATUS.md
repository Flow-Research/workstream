# Status: WS-XINT-003 REV-AUTH End-to-End Contract

## Current status

WS-XINT-003-01, WS-XINT-003-02A, WS-XINT-003-02B, and WS-XINT-003-02C are
merged. PR #255 merged 02C as `745d9c3f` on 2026-08-03 after Backend, Agent
Gates, and CodeRabbit passed on the final PR head. Exactly
`project.review_policy.update` and
`project.revision_policy.update` are active; review/revision lifecycle actions
remain planned or unavailable.

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
- All 23 registered review/revision lifecycle actions remain planned; 02C adds
  the four recovery/lifecycle rows and provisions/admits six fixed-service
  identities without execution authority because every associated lifecycle
  action remains unavailable. The superseded 08R placeholder is never executable. The
  two policy mutation actions activated by 02B are setup authority, not
  lifecycle activation.

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

WS-XINT-003-02D implements the complete typed, fail-closed PREP/read contract
handoff on top of merged 02C. Its merge permits REV to begin hidden lifecycle
implementation against that stable surface. AUTH then returns to its independent
agenda; later XINT activation waves reconnect only to exact merged REV behavior.
Do not infer review lifecycle
activation from readiness: later action activation still requires exact merged
REV behavior and integrated proof.
