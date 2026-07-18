# Internal Review Evidence: WS-ART-001-02A3

## Chunk

`WS-ART-001-02A3`: ArtifactStore v2 Local Clean Cut

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `c8eccaafb6b4f0615b1b37049edfcb0368dd6fb2`

Reviewed at: 2026-07-18T01:31:17Z

Reviewer run IDs: senior-engineering=019f72b5-2d70-7471-a006-3580f3844107; architecture=019f72b5-3692-70a2-9713-2cdd4b9d403e; QA/test=019f72b5-438d-71e3-bc2a-43a078865dbd; security/auth=019f72b5-52c6-7980-a3c7-451a66ce3f9d; product/ops=019f72ce-c029-76b1-9291-104b691f6014; reuse/dedup=019f72ce-cdb9-7fe2-8dea-d5820d675a38; CI-integrity=019f72ce-d8f1-7b00-a5bb-d8a7f835f2e4; test-delta=019f72d5-7d3c-7cd2-90c4-9b5facd31041; docs=019f72ce-e898-7d80-97da-9ec76ac6296a

Only review artifacts may change after this reviewed SHA while follow-up review
and evidence closure complete. No implementation, migration, test, workflow,
policy, or chunk-contract change is permitted without invalidating this record.

## Reviewed Change

- Replaced ArtifactStore v1 with the four-operation byte-only v2 port and one
  typed factory path.
- Rebuilt LocalStorage around immutable content-derived paths, exact replay,
  bounded range reads, no-follow descriptors, exclusive publication, and
  sanitized failures.
- Added the immutable storage-namespace fence and recorded provider
  acknowledgement as `stored_pending_verification` with replica state
  `pending/unknown/unknown`.
- Made LocalStorage layout-marker publication exclusive and crash recoverable,
  including the durable marker-plus-temporary hard-link state.
- Made same-object replica finalization atomic across concurrent PostgreSQL
  transactions while retaining one append-only receipt per upload item and
  allowing independent items in one upload session to finalize concurrently.
- Guaranteed best-effort resource cleanup always attempts digest-lock release
  without masking the original sanitized error or caller cancellation.
- Removed v1 provider-retention/receipt semantics, dormant Flow Node
  configuration, and invented authorization ownership.
- Activated only bounded startup and Celery Beat scratch cleanup. Product
  ingest, S3, verification, recovery, review, and AUTH actions remain inactive.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | The v2 port remains narrow; namespace validation, transaction boundaries, crash recovery, migration refusal, and cleanup activation have no remaining operational defect. |
| QA/test | PASS | None | V2 surface, crash states, namespace fencing, migration refusal, cleanup wiring, concurrency, and shared preparation helpers have complete focused regression proof. |
| security/auth | PASS | None | Filesystem ownership/mode/link checks, namespace fencing, sanitized errors, and ART/AUTH separation have no remaining actionable security finding. |
| product/ops | PASS | None | Acknowledgement remains non-bindable; no Operator route, review/revision decision, contribution, compensation, or reputation behavior is activated. |
| architecture | PASS | None | One ADR 0014 factory path remains; writable storage stays inside ART orchestration and product modules receive only closed capabilities. |
| ci integrity | PASS | None | The exact five cumulative 90 percent gates and the 78 percent whole-app floor remain fail closed with no workflow bypass. |
| docs | PASS | None | ADR, specification, glossary, migration wording, links, and future-chunk boundaries match the implementation. |
| reuse/dedup | PASS | None | Sealed-source preparation is centralized in the shared test helper; no factory bypass, production duplication, or cross-initiative runtime coupling remains. |
| test delta | PASS | None | V1 vectors were replaced by stronger v2 assertions without skips, weakened expectations, or false concurrency proof. |

## Valid Findings Addressed

- GitHub Backend CI passed the full repository coverage and first three focused
  gates, then reported 88.20 percent cumulative `app/workers/*` coverage. Added
  real-PostgreSQL coverage for the known `ProjectServiceError` worker path,
  including sanitized result, persisted `setup_blocked` state, and bounded log
  metadata. The new test executes the previously missed lines 174-193 without
  narrowing or weakening the 90 percent worker gate.

- Replaced the replica read-then-insert race with PostgreSQL
  `ON CONFLICT DO NOTHING` plus a current-row load and strict content,
  namespace, adapter, and provider-profile validation.
- Added a real two-session concurrency test proving two exact replay
  finalizations produce one replica and two receipts.
- Made LocalStorage cleanup attempt digest-lock release in an independent
  `finally` even when temporary unlink or fsync fails.
- Added regression coverage proving cleanup errors cannot leak the owned lock
  or replace the caller's sanitized failure/cancellation semantics.
- Added a namespace-only populated-v2 downgrade refusal test so the deployment
  fence cannot be discarded by a clean-cut rollback.
- Applied every still-valid CodeRabbit finding: atomic marker publication,
  complete upload-result metadata constraints, per-item rather than shared
  session CAS fencing, exact reservation accounting, full downgrade cleanup,
  typed receiver provenance, complete import scanning, cache teardown,
  mutually exclusive failure handlers, deterministic concurrent test results,
  cutover-phase binding, exact coverage-source alignment, and removed-field
  assertions. External dispositions are recorded separately.
- Restored AUTH status to trusted `main` and kept ART gate assertions within
  the ART boundary.
- Reconciled the merged AUTH `0024` migration with ART `0025` and shifted only
  inactive AUTH-10 through AUTH-15 reservations to `0026` through `0031`, with
  an explicit superseding decision and no AUTH runtime activation.
- Strengthened the concurrent first-namespace proof through the real provider
  operation: the winner observes the committed namespace before `put`, while
  the conflicting loser performs zero provider I/O.
- Consolidated sealed-source test preparation into one shared helper after the
  reuse reviewer found two residual duplicate paths; the repair received a
  clean exact-SHA reuse review before the final nine-track fanout.

## Commands Run

```bash
cd backend && .venv/bin/ruff check app/modules/artifacts/repository.py app/modules/artifacts/service.py app/adapters/artifacts/local.py tests/test_artifacts.py tests/test_local_artifact_store.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest -q tests/test_artifacts.py::test_concurrent_same_object_finalization_reuses_one_replica
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest -q tests/test_artifacts.py::test_put_acknowledgement_stops_at_pending_verification tests/test_artifacts.py::test_concurrent_same_object_finalization_reuses_one_replica tests/test_artifacts.py::test_independent_items_in_one_session_finalize_without_shared_cas_replay tests/test_artifacts.py::test_database_rejects_partial_upload_result_metadata tests/test_artifacts.py::test_reservation_accounting_rejects_drift_without_clamping tests/test_artifacts.py::test_same_item_replay_finalizes_once_without_double_accounting tests/test_artifacts.py::test_terminal_put_failure_releases_reservation_and_fails_item tests/test_artifacts.py::test_namespace_mismatch_fails_before_provider_io tests/test_artifacts.py::test_concurrent_different_first_namespace_writers_have_one_winner
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test COVERAGE_FILE=.coverage.art02a3 .venv/bin/coverage run -m pytest -q tests/test_artifacts.py tests/test_artifact_preparation.py tests/test_config.py tests/test_app.py tests/test_api_controls.py tests/test_artifact_architecture.py tests/test_artifact_cleanup_wiring.py tests/test_artifact_store_conformance.py tests/test_local_artifact_store.py
cd backend && .venv/bin/pytest -q tests/test_artifact_architecture.py tests/test_artifact_cleanup_wiring.py tests/test_artifact_store_conformance.py tests/test_local_artifact_store.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/pytest -q tests/test_alembic.py::test_alembic_upgrade_and_downgrade tests/test_alembic.py::test_artifact_store_v2_empty_clean_cut_and_reversible_shape tests/test_alembic.py::test_artifact_store_v2_refuses_populated_v1_before_ddl tests/test_alembic.py::test_artifact_store_v2_refuses_populated_v2_downgrade_before_ddl tests/test_alembic.py::test_artifact_store_v2_waits_for_concurrent_v1_writer_and_refuses
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest -q tests/test_projects.py::test_project_setup_worker_persists_sanitized_domain_failure
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

Results: the prior complete focused run passed 268 ART tests; the final repaired
candidate passed 73 filesystem/architecture/wiring tests, 59 final
LocalStorage/conformance tests, nine critical real-PostgreSQL orchestration
cases, and five migration-chain cases, including all four ART clean-cut safety
cases. The corrected exact ART scope
coverage was 93.31 percent. Ruff, 92.0 percent docstring coverage, stale
contract/authorization/wording,
Markdown links, 80 agent-gate tests, and diff checks passed.
The added real-PostgreSQL worker test passed and executes the ten statements in
the previously missed known-domain-failure branch. GitHub must confirm the
cumulative worker percentage on the republished head.

The isolated full repository suite, 78 percent whole-app floor, cumulative
worker/main gates, and real API drill remain authoritative in GitHub Backend CI.
The intentionally aborted broad local project/task run is not completion
evidence; it was stopped because full regression is assigned to GitHub Actions.

## Remaining Risks

- The migration intentionally refuses any populated pre-production v1 artifact
  table rather than fabricating v2 provenance.
- LocalStorage remains development/test only. Hosted bytes remain disabled
  until the separately approved S3-compatible adapter and AWS activation proof.
- `stored_pending_verification` remains non-bindable. Admission, verification,
  publication, and recovery belong to later chunks.

## Stop Condition

Publish the evidence-bound head for GitHub CI, a fresh CodeRabbit review, and
human review.
Do not merge without explicit user approval and do not start
`WS-ART-001-02B1`.
