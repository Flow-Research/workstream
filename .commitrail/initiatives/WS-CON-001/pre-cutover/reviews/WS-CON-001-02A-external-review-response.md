# External Review Response: WS-CON-001-02A

## Review source

CodeRabbit review `8be695bd-33ce-4847-8bf1-905a130804ec` on PR #155,
submitted 2026-07-19 against head
`21b3b167b930878abfaabc31f5b556e7a6b9036d`.

## Comments addressed

1. Added the nine exact required reviewer tracks to the 02A chunk contract.
2. Reconciled the AUTH runtime baseline to 74 PermissionIds, 65 ActionIds,
   17 active actions, and 48 planned actions.
3. Defined `REV-12A` as a non-executable parent and made REV-12A1 controller
   persistence plus REV-12A3 CON fence composition explicit across intent,
   plan, and status records.
4. Defined `REV-13` as a non-executable parent and made REV-13C the sole public
   product release owner.
5. Replaced the stale FinalAcceptance runtime prerequisite `REV-04` with
   `REV-04B` in the source manifest.

## Comments deferred

- The suggestion to implement a background physical purge is intentionally
  deferred to separately started `WS-CON-001-02B`, whose approved scope owns
  retention. CON-02A explicitly forbids dispatcher/retention behavior and its
  reviewed custody contract prohibits physical delete/truncate; adding a
  trigger-disable purge path here would violate both the chunk boundary and
  immutable event-truth decision. CON-02B must reconcile archival-in-place,
  sustained-volume operations, and the then-current custody contract before
  implementing retention behavior.
- CodeRabbit's 42.50 percent docstring warning is not the repository gate. The
  canonical `docstr-coverage --config .docstr.yaml` command passes at 90.4
  percent on this head; no threshold or exclusion is changed.

## Human decisions needed

None for these comments. The existing human-only PR merge decision remains.

## Commands rerun

- Markdown links: passed for 17 changed Markdown files.
- Stale Workstream, AUTH, ART, and REV contract scans: passed.
- Canonical repository docstring coverage: passed at 90.4 percent.
- Agent-loop gates: 88 passed.
- `git diff --check`: passed.
- Exact repair-SHA internal re-review and evidence rebinding after main
  reconciliation: pending.

After these repairs, contributor-foundation PR #153 advanced trusted main to
`8d5eb15b`. CON is being reconciled onto its `0027_contributor_foundation`
migration as `0028_shared_transactional_outbox`; the merge adds no CON
authorization or outbox behavior. The superseded GitHub Backend run is not
accepted as proof. Fresh bounded local evidence and exact-SHA internal review
must pass before the PR update, then GitHub reruns the full suite.

Bounded reconciliation proof now passes: 43 selected outbox/migration tests
with 32 deselected, 95.73 percent outbox coverage, eight assertion-helper
tests, the exact AUTH `0026` lifecycle downgrade/reupgrade test, one Alembic
head at `0028_shared_transactional_outbox`, and Ruff. Markdown links, stale
Workstream/AUTH/ART/REV scans, canonical 90.4 percent docstring coverage, 88
agent-loop gates, and diff hygiene also pass. Exact-SHA internal review remains
before push.

ART-02C1 PR #154 subsequently merged at trusted main `44f2467c` and owns
`0028_artifact_admission`. CON-02A is now reconciled as
`0029_shared_transactional_outbox`. After REV-02A PR #156 advanced trusted main
to `3b1d6379`, the exact bounded `0029` row passes 73 selected tests with 32
deselected and 95.90 percent focused outbox coverage;
all nine exact-SHA reviewers were required before publication.

Exact repair candidate `9be9c88a19c4301f2b7ac606b6782604a48472bb`
passed all nine internal tracks against trusted main `3b1d6379` with no open
findings or reviewer sessions. The prior GitHub Backend run reached 87.19
percent coverage and 1665 passing tests, but exposed a test-helper dictionary
mutation race in two outbox secrecy tests. The helper now snapshots entries and
a deterministic regression covers the mutation failure. A subsequent run
exposed a Celery Mapping Proxy that spoofs `dict` identity without dict
storage; concrete-type dispatch plus an exact secret-detection regression now
cover that path. GitHub Backend and fresh CodeRabbit state must rerun after
publication.

## Remaining risks

- GitHub must complete the full backend suite and repository-wide 78 percent
  coverage gate.
- CodeRabbit must review the repair commit and close or supersede the five
  actionable threads.
- Physical retention remains explicitly outside 02A and cannot be started as
  02B without separate human authorization and refreshed AUTH prerequisites.
