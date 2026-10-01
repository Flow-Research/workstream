# ARCH-04D1 — Canonical material custody before service activation

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: All retained CHECKERS terminal material facts require the exact canonical ART material tuple in PostgreSQL; live service authority remains unavailable until ARCH-04D2.

## Intent

The product milestone remains claim -> ZIP upload -> pre-submit feedback or
immutable Submission -> automatic post-submit evaluation -> policy-governed
outcome. ARCH-04C supplies hidden durable execution. Its writer copies nine
material facts from ART, but migration 0008 does not independently compare the
admission, verified replica or semantic-manifest digest with canonical ART rows.
The merged ARCH-04D contract requires this guarantee before live activation.

Current main is `b9669dfc`. The existing ART admission guards already verify and
freeze admission ancestry. Some retained-history/REV fixtures still supply
invented ART references; those cannot survive canonical enforcement and must be
replaced with actual stored lineage. Their distinct privacy, authorization,
history and review-queue assertions remain required.

## Design and bounded sequence

Implement ARCH-04D in dependency order: 04D1 canonical persisted custody, then
04D2 exact fixed-service authorization. The five materialization/output/execution/
finalization authority boundaries are not activated in this change. This split
keeps the database and affected fixture cutover independently reviewable; it adds
no new product workflow or parallel implementation.

A fresh migration 0009 adds an ART-owned SQL validator for the exact persisted
Submission/admission/binding/content/verified-replica/manifest tuple. A CHECKERS
terminal constraint trigger requires that validator for every terminal result
with non-null material custody, including infrastructure failures after successful
materialization. Completed results still require material; `material_unavailable`
still requires null material.
Reuse ART's canonical selection semantics and immutable admission custody. Do
not add CHECKERS runtime imports or private queries into ART, duplicate admission
validation, a generic validation framework, or another material facts store.
The validator compares all nine material facts with one exact stored lineage,
not independent existence of each ID. It performs no provider I/O and introduces
no competing feature-row lock order.

Protected relations and helper calls are schema-qualified. Both new functions
pin `search_path` to `pg_catalog, pg_temp`; migration execution places temporary
objects last as well. A caller with temporary-table permission must not replace
the final CHECKERS row or canonical ART ancestry used by enforcement. This
repairs the demonstrated session-name-resolution bypass without adding privileges.

Lock `checker_runs` against inserts and updates before preflight and hold that
migration lock through trigger installation. This closes the scan/install race;
the runtime scalar validator remains a lock-free read.
Preflight every retained terminal run with non-null material before enforcement. Refuse the
upgrade if any row cannot be proven, leaving schema/data and the predecessor
revision intact. Preserve valid retained results, including superseded history;
current mutable replica verification, availability and integrity states are not
retrospective evidence identity; immutable admission/receipt ancestry supplies it.
Infrastructure failures without material custody remain valid; queued/running
reservation and historical replay retain their current semantics. No retained
row is deleted, backfilled or assigned invented lineage.

Update affected fixtures through existing ART creation/verification and admission
owners, retaining production database guards. Remove invented material references
from terminal-run fixtures. Tests that need only queued/running or isolated
value contracts need not execute provider I/O. No fixture-only guard bypass,
compatibility path or alternate history writer is permitted.

## Bounded change

### Allowed files

- `backend/alembic/versions/0009_checker_material_lineage.py` and
  `backend/alembic/env.py` for the new scalar validator, terminal guard,
  preservation preflight and migration-head admission.
- `backend/tests/checkers/execution/` for exact canonical storage prerequisites,
  direct-SQL lineage, retained-data migration, rollback and regression proof.
- `backend/tests/submission_fixtures.py`,
  `backend/tests/post_submit_materialization_helpers.py`,
  `backend/tests/test_artifact_admission.py` for its shared queued-output fixture,
  `backend/tests/test_artifact_internal_authorization.py` for exact verification-job
  receipt assertions, `backend/tests/test_artifact_recovery.py`,
  `backend/tests/test_checker_output_storage.py`,
  `backend/tests/test_checker_output_custody.py` for exact output-only lineage and
  binding assertions, and existing checker-output
  fixture helpers for shared prerequisite ordering, and a cohesive helper
  under `backend/tests/` if needed to reuse canonical ART preparation for retained
  Submission fixtures; existing ART fixture helpers only for that traced reuse.
- Existing affected `backend/tests/authorization/submission_history/`,
  `backend/tests/test_tasks.py`, `backend/tests/test_review_queue_persistence.py`,
  `backend/tests/test_alembic.py`, `backend/tests/test_identifier_schema.py`,
  `backend/tests/test_coverage_contract.py`, and `backend/tests/conftest.py` for
  changed canonical fixture facts and actual schema/head expectations only.
- Existing lane, behavior-ownership, module-boundary and test-structure inventories
  and their validation tests only where new actual proof files require registration;
  no broader ownership or enforcement changes.
- This record, current ARCH overview/plan/chunk map and 04D contract, affected
  ART/AUTH/POL/CON/XINT navigation, Commitrail index, README, checker/data-model/artifact
  specifications, `docs/architecture_system_architecture.md`,
  `docs/spec_authorization_service.md`,
  `docs/operations_project_operating_manual.md`,
  `docs/current_system_data_flow.html`,
  `docs/engineering/authorization_activation_custody.md` and
  `docs/roadmap_status.md` for the exact delivered prerequisite
  and remaining 04D2 activation; local exports if present.

### Prohibited changes

No live service registrations, permissions, AUTH/PREP behavior, public APIs,
Celery handlers, automatic routing, TASK/REV/CON lifecycle effects, acceptance,
new evaluator capabilities, provider configuration, retained-data deletion,
backfill, compatibility layer, alternate executor, or weaker test/CI gates.
The real AUTH finalization-evidence rollback proof remains required in 04D2;
controlled 04D1 phase participants do not constitute that proof.

## Acceptance criteria

- A direct call to the canonical SQL validator rejects a different numeric
  version argument even when all material facts are valid, and independently
  rejects a substituted material version. The exact canonical control succeeds.
  Bind the scalar version argument explicitly to avoid column-name precedence.

- Direct SQL with hostile temporary CHECKERS or ART shadow tables still rejects
  forged terminal material at commit for both outcomes, rolls back all terminal
  facts, and permits an otherwise valid canonical control. The regression must
  fail on the unqualified implementation; all database guards remain enabled.

- Real PostgreSQL rejects each independently substituted `admission_id`,
  `replica_id` and `semantic_manifest_sha256` from a second valid stored lineage.
  Other facts remain valid so rejection reaches the new canonical comparison.
  Cover both completed and infrastructure-failed terminal rows with custody.
- A direct SQL finalization with the exact canonical tuple commits. Rejection
  rolls back terminal result/material, member rows and completion event and
  preserves the running attempt. Finalization receipt references remain unchanged;
  real AUTH audit evidence is not claimed before 04D2.
- Removing each canonical comparison makes its regression fail at the intended
  rejection assertion, not setup, another guard or an unrelated fixture failure.
- Valid retained completed and infrastructure-failed history with material survives
  upgrade; invalid retained lineage
  refuses migration without deleting or altering rows/schema. Null material on
  infrastructure failure and unfinished reservations remain supported.
- A real PostgreSQL independent-session writer waits behind the migration table
  lock across preflight/installation, then meets the installed guard after commit.
  Removing that lock fails the wait/guard assertion rather than fixture setup.
- Local/MinIO execution and retained-history, privacy, authorization and REV queue
  tests pass using canonical stored ART prerequisites. Existing lease/currentness,
  replay, rollback and concurrency behavior remains protected.
- Default production composition still denies before protected reads, scratch,
  provider or evaluator access. No 04D2 activation claim follows from this PR.

## Risk and review routing

Risk: L1, bounded database/evidence integrity with shared fixture consumers.
Human focus: exact cross-owner tuple, immutable historical identity, migration
refusal without data loss, no guard bypass, and no premature activation.

## Evidence

Before implementation, run architecture and security plan review of this scope
and concrete proof feasibility. Before PR readiness, run real PostgreSQL focused
storage/migration/execution and affected history/REV tests, Ruff, module boundaries,
ownership/test structure, Markdown links, Commitrail and stale-wording checks;
then exact-head hosted full-suite completeness and required CI. Coverage remains
diagnostic, not a target. Required final tracks: architecture/reuse, security,
QA/test-delta, documentation/product-operations and CI integrity. No implementation
workers; the lead owns shared checks and all production edits.

Review findings and exact test/CI freshness belong in the PR trust summary.
The executable 04D2 contract must still enumerate exact service actions, resource
facts, PREP transactions, audit custody, revocation races and composition before
activation. No new human decision is required to enforce this already adopted
prerequisite; merge remains a separate human action.


### Implemented proof map

- `test_material_lineage.py`: valid direct-SQL terminal commits and independent
  foreign admission/replica/manifest rejection for both supported material-bearing
  outcomes; closed typed material rejects numeric strings and additional keys;
  terminal/member/event rollback preserves the running attempt. Temporary-table
  substitution of the CHECKERS row or ART ancestry is rejected at commit, while
  valid material commits under the same session environment. A direct scalar call
  rejects a different numeric version argument independently of the material
  version and the checker row’s composite foreign key.
- `test_material_migration.py`: valid superseded history and null-material failure
  survive upgrade, later replica loss or current replica reassignment preserves
  the immutable admission identity, invalid retained rows
  refuse upgrade unchanged, and an independent writer waits across installation.
- Existing Local/MinIO execution, storage, history/privacy and REV tests retain
  their distinct assertions with canonical material prerequisites. The shared
  retained fixture uses actual ART preparation, verification and consumption
  owners with a scripted provider; it is not live provider or public intake proof.
  Output fixtures prepare those prerequisites before minting their bounded source,
  preserving the existing scratch deadline and testing receipts for the exact job.
- Default composition remains deny-only. Real AUTH evidence atomicity and live
  service grants remain mandatory ARCH-04D2 work.
