# Discovery: WS-CON-001 Current-Main Reconciliation

> Historical PLAN4 discovery snapshot. Live 03A implementation state is in
> `STATUS.md`, `SOURCE_MANIFEST.md`, and the `WS-CON-001-03A` contract.

## Baseline

- Protected `main`: `2feaf47dd5bb448db076179d96751caa55fb0994`.
- Latest Backend run for that SHA failed one unrelated AUTH actor-profile
  concurrency test in `shared_foundations`; the same failure also occurred on
  the prior PR head. This planning diff changes no AUTH/runtime/test/CI files.
- Current Alembic head: `0050_guide_source_v2`.
- ART PR #249 merged the guide-source v2 cutover. No CON migration number is
  reserved before a fresh main update at implementation start.
- CON-01 merged in PR #144; CON-02A merged in PR #155 as migration
  `0029_shared_transactional_outbox`.
- Current runtime has generic outbox persistence/append but no dispatcher,
  contribution, compensation, award, delivery, or fulfillment modules.

## Repository process

Current repository entry documents use the simple engineering loop in
`CONTRIBUTING.md` and treat `.agent-loop` records as durable planning context,
not product state. Code, migrations, tests, canonical specifications, current
capability status, and merged history establish implemented behavior.

The old authored CON status and signed-loop narrative are historical. They do
not show live runtime behavior and must not be used to restart CON-02A.

## AUTH findings

Merged AUTH/XINT work now provides:

- canonical actors, project-role grants, fixed-service runtime admission, and
  prepared authorization foundations;
- project create/guide mutation/read foundations;
- immutable review/revision policy identity and active policy mutations;
- all approved REV actions, principals, typed resource/PREP/read contracts,
  and PostgreSQL readiness evidence through PRs #242, #248, #255, and #257.

Still absent from runtime:

- PermissionId and ActionId `outbox.dispatch`;
- ServiceIdentity `workstream.outbox.dispatcher` and its singleton matrix row;
- fixed-service prepared claim support for the outbox event context;
- CON policy, binding, contribution, award, delivery, callback, operations,
  executor, and read ActionIds/evaluators/activations.

The existing `operations.outbox.retry` permission is an Operator recovery
permission and is not dispatcher authority.

## ART findings

Merged ART now owns verified guide-source byte ingest, binding generation,
materialization, bounded PDF/DOCX/PPTX/XLSX/image extraction, and sufficiency
continuation. AUTH guide binding/read activation merged through PR #245.

ART PR #249 merged the verified guide-source clean cut and migration `0050`.
Its guide setup continuation and verified-source contracts are current runtime
evidence; they do not implement CON behavior or alter CON ownership.

ART's remaining submission/reviewer work preserves the CON boundary:

- one verified Submission/binding identity reaches REV and CON;
- ART-07B will hand accepted Submission/ART identity to CON without provider
  I/O in the review transaction;
- evidence upload is outside the approved v0.1 reviewer workflow.

## REV findings

Main contains REV policy/AUTH readiness but no runtime ReviewQueueEntry,
ReviewLease, Review, finding, FinalAcceptance, or revision tables/services.

Merged REV PLAN4 PR #258 is a planning-only current-main refresh. Its reviewed
dependency shape is aligned with CON ownership:

- REV-03A1 queue/admission persistence can start independently;
- REV-03A2 owns ReviewLease persistence but needs CON-03B's
  ContributionPolicyVersion table as a non-null FK target;
- REV-04B needs CON-02C shared lifecycle-audit participant and then enables
  CON-03C to reference Review/ReviewLease/FinalAcceptance;
- REV-06A copies the immutable Submission-attempt policy version carried by
  canonical admission and checks Task/Assignment only for upstream equality;
  the former CON-06 lookup is planned for retirement without transferring
  lease ownership;
- REV-10 consumes CON-07's flush-only contribution/award participant and owns
  the single commit;
- REV-12P1 needs the shared dispatcher only much later.

PR #258 merged as `10720382`. It is current planning evidence, not runtime
Review behavior and does not satisfy any runtime predecessor by itself.

## Existing CON runtime and tests

Relevant current files:

- `backend/app/modules/outbox/**` — persistence and caller-transaction append;
- `backend/tests/test_outbox.py` — validation, idempotency, custody, migration,
  and negative no-dispatch proof;
- `backend/alembic/versions/0029_shared_transactional_outbox.py`;
- `docs/spec_contribution_compensation.md` and ADR 0016 — canonical target.

Absent files are meaningful: there is no `backend/app/modules/contributions`,
`backend/app/modules/compensation`, dispatcher executor, or CON API.

## Planning correction

The old linear order `02B -> 02C -> 03A -> 03B` is no longer useful:

- 03A adapter-binding persistence is independent of dispatcher mechanics;
- 03B policy persistence depends on 03A and unblocks REV-03A2;
- 02C audit participation is independent of dispatcher and is needed only
  before REV-04B;
- 02B remains blocked on exact AUTH dispatcher registration and is needed much
  later for REV projection and CON fulfillment execution.

Therefore the first useful CON path is `03A -> 03B`, with 02C scheduled before
REV-04B and 02B deferred until AUTH supplies its exact service authority.

## Risks and unknowns

- Later migration-bearing merges may change the migration head; every
  implementation chunk must refresh current main. REV PLAN4 is merged, but
  each REV child still refreshes its exact runtime contract.
- The deterministic classification of legacy economic rows remains a human
  data-migration decision before CON-05A/05B.
- Exact CON ActionIds, service identities, dual-principal behavior, and
  activation owners require separate AUTH review; CON cannot invent them.
- Provider fulfillment and callback authentication remain design inputs, not
  implemented behavior.
