# ARCH-04D2 — Exact post-submit service authority

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Risk: L1 (fixed-service authorization, retained evidence and concurrent execution).
- Intended merge outcome: existing post-submit materialization, execution and finalization use live AUTH/PREP with exact current execution custody; automatic dispatch, routing, recovery and public intake remain subsequent boundaries.

## Intent

Continue the contribution milestone: claim -> ZIP upload -> intake feedback or
immutable Submission -> automatic post-submit evaluation -> governed outcome.
The input baseline includes 04D1's canonical ART material validator through migration
`0009_checker_material_lineage`. CHECKERS already owns reservations, worker
leases, execution, retained results and completion events. Before this change, production composition
still denies materialization, execution and finalization.

The current catalogue produces no output files. Output reservation slots and
finalization output bindings are empty by contract. Therefore activate exactly
three current actions, not the older skeleton's five. Keep output ingestion and
binding unavailable until a real registered producer and its atomic binding
proof exist. Controlled output fixtures do not justify live authority.

Terminal replay currently calls ordinary consume and discards its new receipt.
Live AUTH would duplicate audit evidence. Replace that behavior with exact stored
receipt validation through the existing PREP replay machinery. No second replay
protocol or compatibility consume path is permitted.

## Design

Register `workstream.checker.post_submit` with only
`checker.post_submit.execute` and `checker.post_submit.finalize`, each with its
same-named permission. Activate the existing
`artifact.post_submit.checker_input.materialize` action only for
`workstream.artifact.materializer`. Keep human roles, dispatcher, output writers,
review services and artifact binding services unable to execute/finalize checks.
Use existing explicit service provisioning; absent, revoked or inactive actors
deny. Do not create principals automatically.

Extend CHECKERS' existing nominal execution/finalization contracts with stored
receipt replay methods. One canonical CHECKERS authority-digest helper commits a bounded envelope:
domain/phase, action/permission/service, checker-run resource and project scope,
project/task/submission/version, immutable request ID/digest/generation,
attempt/result IDs and worker lease ID/generation/UTC expiry. Finalization adds
the stored execute receipt, accepted result digest/outcome/failure code, exact
material object or null and empty output tuple. The guarded request digest
already commits the complete locked request, policy and catalogue; do not copy
private packet text into audit evidence. AUTH's
phase-specific resource context binds these facts to the exact action and project;
its audit contains bounded identities/digests, not guide text, evaluator text or
provider coordinates. Finalization also binds the stored execute receipt.
Execution preparation binds the immutable request before owner locks; the
owner creates or recovers its lease under locks before final consumption.
Finalization preparation binds the immutable request before owner locks;
consumption extends the final resource with the execute receipt read from the
locked run. Caller input cannot select or replace that stored receipt.

Change the CHECKERS-owned materialization port to accept `ExecuteFacts` rather
than an unleased request. Add a typed `CurrentExecutionPort` at CHECKERS' public
API, implemented using `ExecutionRepository.require_lease` and injected into ART
through composition. ART must not query CHECKERS persistence privately. ART maps
its resolved selection into exact bounded materialization facts (admission,
evidence, binding/content/replica, receipt/job/generation, namespace commitment,
semantic manifest and execution facts); storage coordinates stay inside ART.
A nominal context-manager `prepare_materialization(ExecuteFacts)` keeps AUTH
preparation alive in the caller transaction while currentness and selection are
checked. Pre-I/O consumption returns the materialization receipt; post-I/O
preparation validates that same receipt under fresh authority and exact facts,
without inserting another allow. The receipt is a bounded ID, not a transferable
PREP handle.
The materialization authority seam remains a typed consumer contract, implemented
by AUTH, without exposing an opaque PREP handle or importing ART selection models
into AUTH.

Each short materialization transaction follows AUTH fixed-service locks ->
CHECKERS fence -> current run -> TASK/ART selection -> AUTH audit consumption.
Repeat fresh currentness, selection and stored-receipt authority validation after I/O. Compare
the complete selected identity across phases. Close all sessions, transactions
and PREP handles before provider, scratch or evaluator work. Known foreign,
substituted, expired or superseded executions deny before byte access. A takeover
or revocation after this check cannot undo a prior authorized read; fresh
post-I/O checks and finalization prevent publication. No lease pinning or locks
across I/O are introduced.

Execution/finalization follow AUTH fixed-service locks -> CHECKERS fence -> run
-> AUTH evidence -> member rows/completion event/terminal facts. Finalization
uses fresh authority after I/O and verifies exact current lease. The final
receipt, result members, terminal material/outcome and completion event commit
or roll back together. Do not add ART feature locks to finalization.

Exact terminal replay rechecks live authority and validates the stored
phase-specific audit receipt, returning existing result identities without new
audit rows, storage access or product effects. Expired historical leases may be
read for exact terminal replay; unfinished execution still requires a live lease.
A replaced principal cannot borrow an old principal's receipt. On terminal
`evaluate_post_submission` replay, `_claim` validates the stored execute receipt
and returns the existing `FinalizeFacts` rebuilt from the locked terminal run.
After that transaction closes, orchestration calls the existing `finalize` method
with those retained facts. A second fresh AUTH-first transaction validates the
current fence, unchanged terminal facts and stored finalize receipt before
returning the result. This reuses the existing finalization operation, calls no
provider and validates both receipts; revocation or a successor between the two
transactions denies rather than returning stale authority.

Migration `0010_post_submit_authority` follows 0009. Update the closed actor
identity and authorization evidence constraints required by the three actions,
keeping ORM/catalogue/database parity. Require exact retained receipt provenance,
not merely a non-null UUID or an audit-row foreign key. Reuse the existing outbox
pattern: a schema-qualified `checker_post_submit_authority_digest(checker_runs,
phase)` reconstructs the same bounded envelope from guarded run columns,
request/result digests and material. Use the existing canonical-JSON and UTC SQL
helpers; add no parallel JSON framework or caller-writable authority-digest column.

Deferrable evidence foreign keys and a semantic constraint trigger validate each
non-null execute/finalize receipt against the immutable authority event: allow
kind/domain, exact action/permission, fixed checker service principal, no denial
or grant, exact project/attempt resource, and recomputed context digest. Finalize
must chain a non-null stored execute receipt and use a distinct event. Existing run
custody alone permits replacement only with the valid next lease; terminal
receipt identities stay immutable. Attaching a new receipt requires the active
fixed actor and identity link; unchanged historical references and migration
preflight validate identity without requiring current activity. Historical proof does not depend on the
principal remaining active after its authorized operation.

Lock against writers across preflight and installation. Refuse unprovable
retained receipt references without deleting rows, rewriting IDs or inventing
allow events. Preserve provable rows and queued reservations. Schema-qualify
protected tables/functions and pin safe search paths. Evolve the installed schema
with 0010; do not rewrite the frozen 0001 baseline snapshot. Update head and
schema fingerprint proof.

Current-head running/terminal fixtures must obtain real typed AUTH receipts
through the existing service/PREP owner; remove random-UUID authority participants
from those paths. A narrowly scoped predecessor-migration fixture may represent
that predecessor's persisted shape to prove preservation/refusal, without
claiming live authorization. Pin earlier migration-specific tests to their actual
revision rather than implicitly upgrading through unrelated later migrations.
This affected-consumer conversion is part of this one authority change; it adds
no production compatibility path or repository-wide cleanup prerequisite.

## Bounded change

### Allowed files

- `backend/app/modules/actors/api/service_identities.py` and
  `backend/app/modules/actors/models.py` for the one fixed identity.
- `backend/app/modules/authorization/catalogue.py`, `admin_schemas.py`, `runtime.py`, `prepared.py`,
  `kernel.py`, `domain/prepared_service.py`, `domain/resource_digest.py`,
  `domain/action_groups.py`, `domain/audit.py`, `domain/audit_targets.py`, and existing prepared replay
  helpers; cohesive new `domain/post_submit.py`, `post_submit_authorization.py`
  and `prepared_post_submit_replay.py` for the exact three-action integration.
- `backend/app/modules/checkers/api/execution.py`, `api/materialization.py`,
  `execution.py`, `execution_authority.py`, `execution_coordination.py`,
  `execution_repository.py`, `models.py`, and `backend/app/adapters/checkers/__init__.py`.
- `backend/app/modules/audit/schemas.py` for the closed checker-run resource
  vocabulary and safe exact audit facts.
- `backend/app/adapters/auth/__init__.py` for AUTH-owned concrete composition
  consumed by the CHECKERS/ART composition roots.
- `backend/app/modules/artifacts/post_submit_materialization.py`,
  `post_submit_selection.py`, `sources.py`, `preparation.py` and
  `backend/app/adapters/artifacts/__init__.py`. The existing scratch-close and
  processing owners must preserve cleanup errors during cancellation.
- `backend/alembic/versions/0010_post_submit_authority.py`,
  `backend/alembic/env.py` and existing schema/head verification fixtures.
- New focused `backend/tests/authorization/post_submit/` tests and helpers;
  existing CHECKERS execution/currentness, materialization and service catalogue,
  provisioning, PREP, schema and audit-contract tests whose expectations change;
  `backend/tests/test_artifact_preparation.py` retains retryable scratch ownership
  proof while replacing obsolete cancellation-masks-cleanup expectations.
  Shared `backend/tests/post_submit_materialization_helpers.py`,
  `backend/tests/tasks/submission_lineage_support.py`,
  `backend/tests/submission_fixtures.py`, CHECKERS storage/material/migration
  helpers, and their retained-history/task/review-queue consumers for real
  authority receipt custody and required leased-materialization calls. Preserve
  every distinct isolation, privacy, lineage and historical-material assertion.
- `mcp_server/contracts/authorization_context_get.json` for the existing MCP
  consumer's exact action-enum snapshot; no MCP tool or permission expansion.
- Existing behavior-ownership, module-boundary, lane catalogue and test-structure
  inventories/tests only to register real changed owners and proof; no gate
  weakening or unrelated CI refactoring.
- This record and adopted 04D contract; current ARCH/AUTH/ART/POL/CON/XINT
  navigation, Commitrail index, README, checker/artifact/authorization/data-model
  specifications, architecture/operating documents, authorization custody page,
  current system data-flow HTML and roadmap for affected capability claims.
  Include the architecture brief source diagrams and their rendered SVG/PNG/PDF
  exports so current diagrams agree with the same authority boundary.
  Local roadmap exports only if present.

### Prohibited changes

No public routes, automatic dispatcher handlers, routing or TASK/REV/CON
transitions, final acceptance, reviewer fabrication, compensation changes,
new checker capabilities or output-file authority, operator retries, arbitrary
service identities, generic artifact reads, external adapter changes, retained
data deletion, compatibility aliases or parallel implementation. Do not weaken
module boundaries, test selection, timeouts or completeness checks. The separate
CI impact-reporting and service-provisioning-test PRs are not this scope.

## Acceptance criteria

Use existing real PostgreSQL `material_fixture` canonical Submission/ART lineage,
existing fixed-service provisioning and Local/MinIO stores. The tests below
must reach the named assertion with real guards enabled, not permissive AUTH
participants or a fictitious output producer. The live fixture explicitly
provisions checker/materializer principals and composes the production
AUTH/CHECKERS/ART adapters. The former controlled materialization authority is removed.

Named proof atoms in `tests/authorization/post_submit/`:

- `test_terminal_replay_validates_both_stored_receipts_without_side_effects`:
  canonical success, invalid final receipt with a valid execute receipt denies,
  unchanged audit count and zero additional provider opens.
- `test_materialization_rejects_substituted_live_lease_before_io`: well-typed
  independently changed lease IDs/generations/expiry deny before any protected
  access; canonical control succeeds.
- `test_materialization_rejects_mixed_valid_stored_lineage_before_io`: two valid
  graphs with shared service actors; mixed selectors deny without side effects.
- `test_revoked_after_consumer_cannot_publish[workstream.artifact.materializer]`: paused consumer
  and one provider read; materializer revocation denies its post-I/O receipt check.
- `test_revoked_after_consumer_cannot_publish[workstream.checker.post_submit]`: materializer remains
  active and completes revalidation; checker revocation denies finalization.
- `test_execution_identity_substitution_denies_before_material_access`: typed
  request, project, attempt, result and generation substitution with valid controls.
- `test_outer_deadline_revalidates_material_after_cleanup`: actual executor deadline
  after consumer entry; revoked authority or changed replica denies after cleanup,
  while unchanged custody permits the existing infrastructure-failure outcome.
- `test_outer_deadline_cannot_hide_failed_scratch_cleanup`: cancellation during
  prepared release, extraction-workspace or projection cleanup propagates the
  integrity failure, retains
  cleanup ownership and the running attempt, and publishes no terminal evidence.
  The same retained cleanup can succeed afterward. Ordinary callback errors
  after abort remain distinct: successful cleanup preserves cancellation or the
  preparation deadline, so post-I/O material authority is still revalidated.
  `test_submission_processing_preserves_cancellation_over_aborted_callback_error`
  protects that shared pre/post owner contract. Cleanup lock deadlines are
  sanitized as scratch-integrity failures, not recordable provider failures;
  callback, projection, workspace and prepared-source ownership remain distinct.
- `test_revocation_and_finalization_serialize`: independent sessions and
  observed lock waiting prove both valid commit/denial orderings.
- `test_real_audit_insert_failure_rolls_back[execute/materialize/finalize]`: action-filtered real
  insert failures, observed trigger execution, exact rollback and valid control
  after trigger cleanup.
- Convert `test_finalization_outbox_failure_rolls_back` to real AUTH and inspect
  staged final audit/member rows before failing the actual completion insert.
- `test_actual_upgrade_preserves_or_refuses_without_repair[False/True]`: 0009 -> 0010 migration
  snapshot preservation/refusal. Pin the existing 0008 -> 0009 material tests to
  `0009_checker_material_lineage`, keeping their distinct preservation proof.

The 0010 writer-exclusion regression pauses the real migration after preflight,
observes an independent old-schema writer waiting on its table lock, then proves
that writer cannot commit an unproven receipt after upgrade. A real authorized
claim remains usable afterward. Earlier material-selection tests call the ART
selection owner directly when proving ART rejection, so a prior CHECKERS lease
guard cannot mask the intended assertion.

The shared scope validator factors the existing non-artifact selector rejection
once, preserving its error and allowed combinations without growing the large
runtime module. Catalogue and migration-graph assertions remain exact.

Each boundary receives a discriminating removal/substitution probe as described
below; fixture or unrelated type-validation failures do not count.

1. Exact valid execution and finalization persist the exact respective AUTH
   receipt with the protected state. Real Local and MinIO execution retain all
   canonical material facts; current zero-output behavior remains explicit.
2. Missing/inactive/revoked service and foreign service/action combinations deny.
   Human/dispatcher/output identities gain no checker permissions. Verify SQL
   closed-identity and audit action/permission/resource parity after upgrade.
3. Independently substitute request, project, submission, attempt, result, lease
   ID/generation/expiry or evaluation generation, including mixed identifiers
   from a second valid stored lineage. Deny before provider/scratch/consumer when
   the defect is known at entry; leave run, audit and event state unchanged.
4. Exact terminal replay returns original IDs and validates original execute and
   finalize receipts with no extra audit/provider/product effect. Substituted
   action, principal, resource digest or stored receipt denies. Revoke after
   success and prove replay denies rather than borrowing the old allow.
5. Revoke after provider/evaluator work and prove fresh finalization denies with
   no members, final receipt, result/material/routing or completion event. Keep
   the committed running lease and execute receipt. Prove both independent-
   session orderings: finalization custody before revocation commits first;
   revocation first causes denial. Reuse real-AUTH stale-worker takeover and
   fence-generation serialization tests without lock-order reversal.
6. Fail the actual AUTH audit insert using an ordinary action-filtered test
   trigger/function installed on audit_events and removed in finally.
   Execute failure leaves the run queued with no lease or execute receipt;
   materialization failure prevents provider and scratch access; finalization
   failure leaves the committed running lease and execute receipt intact while
   all terminal writes roll back. Separately fail completion-event
   insertion after real AUTH evidence is staged and prove that evidence, members
   and final state roll back together. These are distinct failure boundaries.
7. Preserve scratch cleanup and no-open-transaction behavior on cancellation and
   provider failure. Materialization audit may remain as evidence of an authorized
   read; it never substitutes for a CHECKERS finalization receipt.
8. Direct SQL rejects nonexistent receipt IDs and valid stored allows from a
   wrong action, principal, project/attempt or prior lease, including same-attempt
   wrong result/material digests and a finalize receipt chained to another
   execute receipt. Otherwise valid controls commit. Reject at the semantic
   receipt boundary, not an unrelated missing-field guard; preserve the prior
   run and roll back staged members/event/evidence. Compare Python/SQL digests
   for execute, completed finalize and infrastructure-failed finalize, with null
   and non-null material. Upgrade preserves valid/queued facts and refuses
   unprovable retained receipts atomically.
9. Mutation probes must disable the specific request/lease/replay/revocation
   check and fail at the intended behavioral assertion. Do not count fixture,
   missing-field or unrelated guard failures as regression proof.

The final-receipt validator independently rejects a missing execute receipt.
Its direct-SQL regression isolates that semantic guard from the earlier run-state
trigger, supplies an otherwise matching finalize event/digest, and proves commit
rejection and rollback. A positive receipt-chain control commits; restoring the
old nullable comparison must make the negative assertion fail. This strengthens
receipt custody without changing the roadmap's exposure or next boundary.

## Evidence

Base for the reviewed plan: main `39a6b827`; installed migration head 0009.
The focused proof modules are under `tests/authorization/post_submit/`. Run focused PostgreSQL cases via the existing
`backend/scripts/run_isolated_tests.py` isolated database runner, including the
new AUTH suite, `tests/checkers/execution/`,
`tests/test_post_submit_materialization.py`, and affected catalogue/PREP/schema
suites. Real MinIO cases use the existing service fixture. Run affected Ruff,
`git diff --check`, module-boundary/behavior-ownership/test-structure validators,
markdown links, stale Workstream/authorization/artifact wording and Commitrail
validation. Complete hosted backend lanes and aggregate manifest with no skipped
or deselected tests; coverage remains diagnostic.

## Risk and review routing

Required focused plan and candidate tracks: security; architecture/reuse;
QA/test delta; documentation/product operations; CI integrity; senior engineering
for phase/lock/replay simplicity. Lead owns shared checks and exact candidate
custody. Plan reviews inspect feasibility before code, not claim runtime proof.

Human review focus: exact service matrix and bounded audit facts, database receipt
provenance, replay's stored
receipt validation, short transaction lock order, revoked worker finalization,
real audit rollback, and accurate unavailable output/dispatch/public boundaries.

## Remaining boundary

After this change, ARCH-04E coordinates automatic dispatch and governed outcomes;
04F supplies contributor remediation; shared final acceptance is still required
for `human_review_required=false`; public intake remains gated by that complete
path. Human review is still the default. Do not start these chunks automatically
inside this PR or claim the full public lifecycle is delivered.
