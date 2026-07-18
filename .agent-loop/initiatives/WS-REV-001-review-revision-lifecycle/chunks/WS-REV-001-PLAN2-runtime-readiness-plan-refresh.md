# Chunk Contract: WS-REV-001-PLAN2 - REV-02A Runtime Readiness Plan Refresh

## Parent initiative

`WS-REV-001` - Review And Revision Lifecycle

## Goal

Reconcile the complete REV initiative against trusted main, current owner plans,
and internal review before any REV-02 runtime or migration work begins.

## Risk class

L1 planning and cross-initiative contract integrity.

## Preconditions

- `WS-REV-001-02` is merged through PR #147 on trusted main.
- AUTH-09D-A is merged through PR #148 at
  `99ae4c963e53f317175dcb308b9e47c93ccf19ed`; its profile-lifecycle behavior and
  migration `0026` are trusted, while the separate contributor foundation is not.
- The user explicitly authorized planning and read-only preparation while the
  remaining AUTH contributor-foundation runtime dependency remains unmerged.
- No AUTH, ART, CON, backend runtime, migration, or persistence test is edited.

## Allowed files

```text
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-PLAN2.json
docs/spec_review_lifecycle.md
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/operations_revision_replay.md
```

## Not allowed changes

```text
backend runtime, migrations, schemas, models, repositories, services, routes, or tests
frozen `docs/reference_specs/` source specifications, archival inputs, or cross-initiative owner artifacts
AUTH, ART, or CON action availability, ownership, runtime, or planning contracts
implementation or activation of any review, revision, adjudication, or release behavior
completion of WS-REV-001-02A or automatic start of WS-REV-001-02B
```

## Acceptance criteria

- Trusted merged authority is separated from unmerged worktree evidence and
  human-approved prospective dependencies. Every runtime gate requires its
  eventual exact owner chunk ID, merged PR/SHA, migration head, constraints, and
  test evidence before implementation.
- The 02A guide-activation contract defines Project-first publication and
  Task-screening locking, immutable Task guide identity, exact status/provenance
  invariants, database time, unchanged superseded-candidate denial, and complete
  allowed-file/test scope. Proposed 02A2 owns prepared-authorized stale-retry
  protection before AUTH-12 activation.
- The initiative uses one explicit command-specific lock order for the review
  decision transaction and identifies every cross-domain owner prerequisite.
- Pure decision-contract work is separated from the first canonical
  Review/FinalAcceptance transaction. Oversized L1 chunks are split into
  independently reviewable same-initiative successors before implementation.
- ART packet-read, review-evidence, stabilized artifact-digest, CON persistence/
  participant, AUTH identity/action, and release-control dependencies are
  fail-closed owner gates. REV does not invent or start owner chunks.
- Every executable chunk has a canonical title, explicit allowed/not-allowed
  scope, acceptance criteria, verification commands, required reviewer tracks,
  and a stop condition. Migration numbers remain unreserved until each chunk
  starts from the then-current single head.
- v0.1 remains limited to immutable Review/finding/resolution history,
  `accept -> FinalAcceptance -> accepted_submission`, revision rebase, and
  terminal reject. Adjudication remains disabled and unimplemented.
- The merge intent returns to `WS-REV-001-02A` and requires a new explicit start
  after all runtime gates merge. This planning chunk activates no successor.

## Verification commands

```text
git diff --check
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
```

Run the initiative-specific AUTH/ART/CON dependency scans. Verify that the only
active product documents changed are the four enumerated allowed files,
including `docs/spec_review_lifecycle.md`, and that the diff contains no
backend, migration, frozen `docs/reference_specs/` or archival specification,
cross-initiative handoff, or owner-plan files.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, and CI integrity.

## Human review focus

Dependency authority, chunk boundaries, transaction and locking ownership,
future-compatible but dormant adjudication boundary, and absence of runtime
changes.

## Stop condition

Merge, allow automated memory to record this planning chunk, and stop.
`WS-REV-001-02A` requires its exact external dependencies and a separate human
start; do not implement it or begin 02B automatically.
