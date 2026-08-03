# Discovery: WS-REV-001 Review And Revision Lifecycle

## Current-main baseline

Discovery was refreshed read-only from `origin/main` at `3479ee71`, merged PR
#257, on 2026-08-03. The sole Alembic head is
`0049_rev_auth_readiness`. No `backend/app/modules/reviews/` package or REV
runtime table currently exists.

The active product contract is `docs/spec_review_lifecycle.md`. The supplied
WS-REV/WS-IMP Markdown and PDF files under `docs/reference_specs/` are immutable
historical inputs governed by the precedence rules in that active contract.

## Implemented upstream facts

### AUTH

- `backend/app/modules/authorization/review_contracts.py` defines frozen typed
  contracts for all approved REV reads, mutations, services, recovery, and
  release control.
- `backend/tests/test_review_authorization_contracts.py` proves strict shapes,
  action/mode parity, scalar serialization, and absence of handles/ORM values.
- `catalogue.py`, migration `0049_rev_auth_readiness`, and fixed service
  identity registration contain all approved REV actions and six service
  identities. Lifecycle actions remain unavailable.
- Policy configuration is already active through
  `policy_mutation_router.py`, `policy_mutation_service.py`, and migration
  `0048_review_revision_policy_authority.py`; it is setup authority, not REV
  lifecycle behavior.

REV must compose the exact models from `review_contracts.py`. It must not add a
parallel resource-context family or import AUTH repositories.

### Project, Task, Submission, and Checker

- ReviewPolicy and RevisionPolicy are immutable identities with generation,
  digest, semantic status, and predecessor lineage.
- ProjectGuide selects exact policy triples. Task, Submission, and CheckerRun
  copy and foreign-key the same lineage.
- `backend/app/modules/tasks/models.py` owns Task, TaskAssignment, and the
  existing versioned Submission identity.
- `backend/app/modules/checkers/models.py` owns CheckerRun;
  `backend/app/modules/checkers/service.py` defines `allow_review` routing.
- Current checker tests prove final `allow_review` outcomes, but there is no REV
  queue admission participant yet.

REV consumes these facts and never edits their general intake semantics.

### ART

- ART owns immutable bytes, verified bindings, extraction, materialization,
  and provider access through typed capability ports.
- Reviewer evidence upload/binding is not approved v0.1 behavior. Findings and
  contributor responses are records only.
- ART reviewer packet materialization remains future `WS-ART-001-07A` and
  requires a hidden REV packet manifest.
- The current ART plan does not yet publish the contract-only packet membership
  identifier/port that REV-03B needs. ART must publish that type first without
  depending on REV runtime; REV then owns normalized lifecycle membership and
  ART-07A consumes the resulting manifest for byte materialization.
- ART's submission/checker cutover remains incomplete. Until the final typed
  admission handoff merges, REV may build persistence and pure rules but must
  not guess binding identifiers or call the raw ArtifactStore.

### CON, audit, and outbox

- Shared transactional outbox persistence exists under
  `backend/app/modules/outbox/`.
- Shared audit services exist under `backend/app/modules/audit/`, but that does
  not by itself prove the planned CON-02C lifecycle-audit participant.
- CON runtime review integration remains future. The stable boundary is one
  ordered reviewer operation for every Review and one submitter operation only
  after REV creates FinalAcceptance on accept.
- Core decision composition performs no ART/provider I/O.

## REV-owned runtime to add

- ReviewQueueEntry and admission idempotency.
- ReviewLease, preference state, and completed lease history.
- ReviewPacketManifest and normalized membership.
- Review, ReviewFinding, FindingResolution, and decision idempotency.
- FinalAcceptance.
- RevisionContextPreparation, SubmissionFindingResponse, and immutable episode
  lineage.
- Recovery/reconciliation findings, projection inputs, and lifecycle release
  control.
- Thin routers only at the final product release.

## Existing conventions to preserve

- Async SQLAlchemy 2.x models/repositories/services and caller-owned sessions.
- Alembic single-head migrations allocated only from then-current main.
- PostgreSQL partial unique constraints, database time, `FOR UPDATE`, stable
  lock order, and direct-SQL invariant tests.
- Pydantic schemas and closed enums.
- AUTH PREP handles remain opaque, process-local, session/transaction/action/
  principal/request/resource-bound, and single use.
- Typed participant/port boundaries; no generic service locator or concrete
  adapter import.
- GitHub Actions owns the full suite and repository-wide coverage run.

## Tests and gaps

Existing tests cover policy lineage, checker routing, task/Submission behavior,
AUTH contracts, audit, and outbox. Missing tests necessarily include all REV
schema, queue, lease, decision, revision, recovery, projection, and release
behavior because those modules do not exist.

Each implementation child must add focused tests for its own constraints and
both orders of every relevant race. No child may weaken existing checker-caused
revision coverage.

## Dependencies and integration gates

- Queue/admission-idempotency persistence: AUTH 02D merged; safe to begin.
- Lease persistence requires merged CON-03B canonical
  ContributionPolicyVersion target; it is not yet evidenced merged.
- Packet-manifest persistence requires a published ART contract-only membership
  identifier/port without an ART-07A runtime dependency; it is currently an
  owner gap.
- Automatic queue admission: exact final TASK/CHECKER/ART handoff merged.
- Claim packet creation: queue/lease persistence, CON reviewer-policy freeze,
  and exact ART packet membership/materialization contracts.
- Decision commit: Review/FinalAcceptance persistence, TASK participant, CON
  contribution participant, audit, and outbox.
- Product reads/routes: matching AUTH activation plus lifecycle release gate.

## Risks discovered

- Current planning contains large historical sections that can be mistaken for
  live authority.
- ART and CON status documents contain stale historical snapshots; only exact
  merged symbols and current capability ledger are implementation evidence.
- Far-future file and migration paths cannot be frozen safely now. Their chunk
  contracts remain skeletons until refreshed at start.
- The human revision round/deadline semantics remain intentionally undecided.

## Unknowns requiring later owner evidence

- Final typed ART/CHECKER-to-REV admission manifest.
- ART contract-only reviewer packet membership input and later ART-07A
  materialization input/output types.
- Final CON reviewer-policy freeze and two-operation decision participant.
- Exact TASK decision and human-revision participant interfaces.

These unknowns do not block 03A1. They do block their named later consumers.
