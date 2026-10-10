# WS-ARCH-001-04E2B — Commit authorized post-submit outcomes

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: One hidden callable operation commits exact routing
  authority with its full governed outcome; completion delivery and production
  registration remain separate consumers.

## Intent

Close group 1's authorization/effect gap on the first contribution journey.
Passing required checks under locked false policy must produce FinalAcceptance,
accepted TASK/completed assignment, the submitter ContributionRecord and the
complete applicable award set atomically. Locked true retains its independent
TASK human-review handoff without a REV queue or invented Review. Preparation
alone must never be acknowledged as a completed outcome.

B4/B5/B6/B7 and REV-12A4A are delivered foundations, not public end-to-end
readiness. This record also carries the reviewed current-plan reconciliation:
five remaining groups, authorized outcomes before completion delivery, and no
repeated initial-dispatch work. It supersedes the local planning-only record;
no separate planning PR or new prerequisite is introduced.

## Starting behavior

TASK `post_submit_routing/source.py` and `requests.py` retain exact current
source proposals and a stable request/manifest identity. AUTH
`post_submit_routing_authorization.py` initially prepared a planned/unavailable action.
REV `acceptance/participant.py` composes TASK and CON under the existing fence
but lacks mandatory source AUTH custody. Existing positive acceptance fixtures
are mechanical human-source proof, not genuine acceptance authorization.

The starting AUTH contract required `TaskPostSubmitManifestFacts.created_at` before source
publication, although the INSERT guard owns that timestamp. False consequence
also omits lifecycle generation. Both gaps are corrected in the same
canonical contracts before activating the exact operation.

## Bounded change

### Allowed

- Existing TASK `api/post_submit_routing.py`, immutable outcome identity values in
  `api/routing_outcome.py`, owner-local `post_submit_routing/`
  request/source/models and cohesive outcome/consumer-port files; affected
  `repository.py` and `accepted_effects.py` only for exact outcome/replay custody.
- Existing AUTH `api/acceptance_source.py`, `acceptance_source_contracts.py`,
  `post_submit_routing_authorization.py`, `domain/post_submit_routing.py`,
  canonical catalogue/parity/resource/audit/PREP matching and exact replay paths.
  No alternate authorization service.
- REV `api/acceptance.py`, `acceptance/{models,repository,participant}.py`, and
  existing lifecycle service/manifest readiness only where mandatory source
  custody changes its retained-source validation. Existing fence is reused through
  a REV-owned prepared acceptance capability and transaction-bound held-fence
  view injected into the existing TASK/CON participants.
- ART `post_submit_materialization.py` and CHECKERS `api/materialization.py`,
  `api/execution.py`, execution/coordinator/models plus their focused material
  custody tests, only to retain the actual input-materialization decision that
  the current result discards. Reuse B6 creation/binding receipts; no reverse
  audit search or borrowed phase receipt. Keep pre-consumption material facts
  distinct from the post-consumption receipt, without a compatibility default.
- PROJECTS `api/locked_policy.py` and `locked_policy_repository.py`, only for a
  project-qualified nonlocking review-mode observation, revalidated under custody.
- Existing TASK/REV/CON typed participants and explicit `app/adapters/` roots;
  shared AUDIT/outbox append participants and bounded outcome event contracts.
- One successor migration after 0028, model registration if necessary, Alembic
  preflight/head inventory and measured schema reset fingerprint.
- Focused AUTH routing/source, TASK routing, REV acceptance/lifecycle and CON
  participation tests and their affected fixtures; migration/storage/replay,
  branch and concurrency regressions; current service-vocabulary migration tests
  and outbox fixture cleanup affected by the new deferred outcome reference;
  required ownership/lane inventories and the AUTH structural-debt inventory
  with an exact assertion map for the affected catalogue-test extraction.
- This record, current ARCH plan/map/overview and active 04E child, index,
  affected AUTH/POL/REV/CON current navigation and canonical specs, README,
  architecture lockdown, product brief, authorization custody/operator docs and
  roadmap. Update local XLSX/CSV only if present.

### Not allowed

No completion handler or production registration, public route, false-guide
activation, human decision/queue/revision runtime, contributor lease timers,
fulfillment/payment delivery, new service/action/role/dispatcher/source store,
compatibility receipt or retained-data rewrite/deletion. No weakened gates,
skips, coverage quotas or replacement of required proof with permissive mocks.

## Design

- Reuse one TASK outcome operation and explicit composition root; existing owners
  remain sole writers. Consumer-owned ports/adapters prevent TASK/REV/AUTH cycles.
  The caller-owned root transaction contains all writes; only the transaction
  root commits. The return value is not an outbox acknowledgment.
- Observe the locked-policy branch through a bounded nonlocking TASK read before
  locks, then revalidate exact lineage under mutation custody. False acquires
  REV-12A4A before TASK/Assignment/Submission, PROJECTS and CHECKERS, then AUTH;
  true never acquires REV/CON. Acquire a REV-owned prepared FinalAcceptance
  capability before TASK locking; consume it after AUTH without reacquiring the
  controller. Its held-fence view checks the original root transaction and exact
  generation for existing TASK/CON participants instead of issuing another REV
  lock. Detached lifecycle facts cannot substitute for this capability; use after
  transaction end, rollback or a savepoint fails. Retain exact outbox invocation custody through
  commit using the existing port. Prove actual interleavings, not just order lists.
- Prepare/consume AUTH over `TaskPostSubmitSourceProposal`; keep persisted
  `ManifestFacts` for stored reads. One canonical semantic digest excludes only
  database-created time. Never invent a timestamp or publish a receipt-less row.
- Bind the original authorized false lifecycle generation in the strict
  consequence and resource digest. New acceptance requires that exact current
  LIVE generation. Terminal replay separately acquires the current controller
  generation, verifies the original receipt with its stored authorized generation,
  and proves complete replay disposition before allowing those generations to
  differ. Current generation never authorizes new effects with an old receipt.
  Reuse canonical fixed-router PREP and fresh-authority replay; only the existing
  `task.post_submit.route` action becomes executable internally.
- Extend the existing manifest with mandatory actual immutable decision-event
  custody and the exact reconstructible authority context. Harden the same
  FinalAcceptance input/row with a mandatory same-source decision reference.
  Detached receipts remain untrusted until AUTH verifies the retained event.
- Source publication binds distinct original Submission creation/binding,
  input-materialization, execute/finalize and routing decisions from their
  canonical retained owners. Propagate the materialization decision through
  its existing result/finalization custody; a material-bearing terminal result
  cannot support routing without it. No-material infrastructure outcomes do
  not fabricate a materialization receipt.
- Refuse upgrade with retained pre-authority manifests/acceptances or terminal
  checker finalize receipts unchanged.
  SQL independently verifies exact service/link/action/permission, project,
  request/source/claim/consequence and generation, using schema-qualified tables
  and safe function search paths. No NULL/default compatibility path.
- Deferred database closure rejects a standalone routing allow, incomplete or
  crossed manifest/outcome, missing TASK/assignment/contribution/award members,
  and missing shared audit/outbox consequence. A constructed, not-invoked,
  expired, finalized or foreign outbox claim cannot produce an outcome;
  the callable operation uses actual committed invocation custody. Reuse existing award-set guard;
  do not implement a second compensation evaluator.
- Exact replay verifies the original complete tuple with fresh authority,
  returning its original IDs without new receipts/events/effects. Partial
  retained effects are errors, never repaired by replay. Stopped false replay
  follows the existing controller generation contract without new acceptance.

## Acceptance criteria

- Real AUTH and PostgreSQL commit each exact true/false outcome, with paid zero,
  one and two applicable award sets as governed. False creates no Review or
  reviewer contribution; true creates no acceptance or CON effects.
- Cross-project and mixed valid-record selections, wrong receipt/source/claim,
  altered consequence/generation and revoked principal deny with no effects.
- Direct SQL cannot commit partial or mismatched outcomes or an orphan allow;
  safe-path controls succeed. Retained data is preserved on refused migration.
- Rollback after each participant including audit/outbox leaves no partial
  outcome. Duplicate/restarted delivery preparation can invoke select-only
  replay, without executing a handler in this PR.
- PostgreSQL tests observe branch revalidation and actual intermediate waits for
  REV/TASK/AUTH, acceptance/successor and outbox custody races in both orders.
- Replace obsolete receipt-less acceptance positives with real authorized false
  outcomes while retaining their distinct lineage, rollback and immutability
  proof. Human runtime stays unavailable; do not fabricate allowed AUTH events.
- Clearly scoped test setup may seed otherwise unreachable, internally valid
  false guide lineage; routing authority/effects must use real owners. This does
  not establish public false-guide activation or first-layer readiness.

## Risk and review routing

Risk: L1, cohesive multi-owner atomic authorization outcome. The migration,
source/effect custody and affected fixture replacements may exceed the preferred
500-line guide because splitting a genuine allow from its mandatory consequence
would permit incomplete commits. Keep modules cohesive and scope bounded.
Required reviewers: architecture/reuse, security, QA/test-delta, CI integrity and
substantive docs/product-ops. Human focus: exact source authority, complete
transaction/database closure, lock order and truthful hidden-versus-live scope.

## Evidence

Before implementation: inspect existing owner seams and review this contract.
During implementation: focused pure contract tests and real PostgreSQL outcome,
SQL guard, migration, rollback and concurrency tests. Each reproduced defect
needs a discriminating guard-removal or pre-fix failure, not just a happy path.
Verify all affected tests, module/AUTH boundaries, ownership/lane catalogue,
lint, links, current wording and Commitrail; full hosted suite remains required.
No percentage gate. Real storage/broker first-layer drill remains group 5;
this operation does not claim production delivery.

### Implementation proof map

These tests identify the required behavior. Execution evidence belongs to the
reviewed candidate and PR; this map does not claim hosted or live readiness.

| Requirement | Proof | Custody |
| --- | --- | --- |
| True handoff without acceptance | `backend/tests/tasks/post_submit_routing/test_outcome.py::test_true_branch_does_not_acquire_acceptance` | Real PostgreSQL/AUTH; forbidden REV participant and absent economic rows |
| False atomic acceptance with no awards or Review | `backend/tests/tasks/post_submit_routing/test_outcome.py::test_false_branch_records_one_acceptance_and_submitter_contribution` | Real PostgreSQL/AUTH and independently selected committed rows |
| Zero awards | `backend/tests/contributions/participation/test_postgresql.py::test_create_and_exact_replay_all_frozen_award_shapes[unpaid]` | Real outcome, retained source and zero stored awards |
| One money award | `backend/tests/contributions/participation/test_postgresql.py::test_create_and_exact_replay_all_frozen_award_shapes[money]` | Real outcome; stored award equals frozen definition |
| One points award | `backend/tests/contributions/participation/test_postgresql.py::test_create_and_exact_replay_all_frozen_award_shapes[points]` | Real outcome; stored award equals frozen definition |
| Both awards | `backend/tests/contributions/participation/test_postgresql.py::test_create_and_exact_replay_all_frozen_award_shapes[money-and-points]` | Real outcome; complete stored set equals both frozen definitions |
| Rollback across every participant | `backend/tests/tasks/post_submit_routing/test_outcome.py::test_participant_failure_rolls_back` | Real caller transaction, injected failure at one boundary |
| Exact terminal replay after shutdown | `backend/tests/reviews/lifecycle/test_participant_control.py::test_stopped_terminal_replay_is_select_only` | Actual controller transition, original receipt and unchanged row sets |
| No REV/CON acquisition for true branch | `backend/tests/tasks/post_submit_routing/test_outcome.py::test_true_branch_does_not_acquire_acceptance` | Forbidden participant invocation plus committed TASK/AUTH control |
| Source/claim/event substitutions and orphan/partial SQL | `backend/tests/tasks/post_submit_routing/test_outcome_storage.py::test_incomplete_or_crossed_outcome_rejected` | Direct SQL with internally consistent digests; assert intended constraint failure |
| REV/TASK/AUTH intermediate wait | `backend/tests/reviews/lifecycle/test_participant_control.py::test_task_read_acceptance_and_transition_intermediate_waits` | Independent PostgreSQL sessions and observed lock waits |
| Acceptance wins before successor | `backend/tests/tasks/post_submit_routing/test_evaluation_currentness.py::test_acceptance_blocks_successor_and_retains_exact_replay` | Independent sessions and observed lock wait |
| Successor wins before outcome | `backend/tests/tasks/post_submit_routing/test_evaluation_currentness.py::test_successor_blocks_then_invalidates_old_routing_completion` | Independent sessions; actual outcome rejects after successor commits |
| Outcome retains invocation | `backend/tests/tasks/post_submit_routing/test_outcome_concurrency.py::test_outcome_holds_invocation_until_commit` | Real finalizer blocked until caller commits |
| Finalization invalidates observed invocation | `backend/tests/tasks/post_submit_routing/test_outcome_concurrency.py::test_finalization_between_observation_and_fence_denies_outcome` | Real finalizer commits between observation and custody; no outcome |
| Held acceptance capability lifetime | `backend/tests/reviews/acceptance/test_prepared.py::test_prepared_acceptance_requires_original_root` | PostgreSQL root, rollback, new transaction and raw savepoint probes |
| Retained materialization decision, Local | `backend/tests/checkers/execution/test_execution.py::test_verified_material_execution_and_replay[local]` | Actual materialization receipt equals stored CHECKERS evidence |
| Retained materialization decision, MinIO | `backend/tests/checkers/execution/test_execution.py::test_verified_material_execution_and_replay[minio]` | Actual S3-compatible materialization receipt equals stored CHECKERS evidence |
| TASK request binds exact stored content hash | `backend/tests/tasks/accepted_effects/test_postgresql.py::test_routing_source_rejects_only_substituted_request_hash` | Actual authorized false-policy outcome; valid replay control, hash-only substitution rejected and unchanged retained state |
| Exact event excludes administrative mutation identity | `backend/tests/tasks/post_submit_routing/test_outcome_storage.py::test_routing_event_excludes_administrative_idempotency_reference` | Real stored event, malformed insert SQL rejection and independent replay-field rejection |
| Upgrade refusal preserves old data | `backend/tests/tasks/post_submit_routing/test_outcome_migration.py::test_pre_authority_rows_refuse_upgrade_without_rewriting` | Isolated predecessor schema, rejected upgrade and unchanged rows |

## Reconciliation

Base is merged #516/#517. Carry the reviewed five-group plan correction in this
product PR. After this operation, complete hidden completion delivery, then
remediation, live composition, public intake and the real drill. Default-true
review policy stays independent; human runtime and payment delivery stay deferred.

## Review refinements

The detached routing receipt does not claim an administrative AUTH-mutation
idempotency reference. Its operation is bound through request/correlation, source
and resource digests. Python replay and SQL independently require the actual
event's administrative idempotency field to remain NULL. Current documentation and the proof map distinguish delivered
hidden guarantees from remaining production and human-runtime work.

Before the next completion-delivery consumer, replace the operation's internal
dictionary return with one strict frozen TASK-owned outcome value. There is no
production consumer yet; add no compatibility wrapper or parallel operation.

Retained-history fixtures provision the actual materialization principal without
reactivating an existing actor or identity link. The obsolete current-router
unavailability assertion is removed: fixed-principal, revocation and complete
outcome proofs cover the now-active hidden action. Historical vocabulary migration
proof remains storage-only. Outbox fixture cleanup validates pending deferred
constraints before re-enabling table triggers, matching the shared reset order.

Obsolete fake repository transport tests are replaced by retained PostgreSQL
source-lineage, exact TASK lineage, policy-polarity and complete outcome tests.
Takeover fixtures obtain new materialization authority for the new lease; stale
receipts remain invalid. Material-lineage tests explicitly fire their named
deferred constraint under the altered search path so newer receipt guards do
not mask that proof. New audit references preserve their referenced owners'
string representation internally and convert to native UUID values at typed ports.

The removed fake transport hash case has a distinct real PostgreSQL replacement:
the TASK participant compares the request hash with its stored routing manifest
alongside the existing canonical acceptance predicate. Upstream source validation
is not a substitute for this request boundary.

The affected fixed-service catalogue assertions move from the oversized AUTH
test module to its existing focused catalogue module. All nine original assertion
spans have explicit retained/extracted dispositions; the original module shrinks,
and the structural inventory records that reduction without changing limits.
