# ARCH-04E3A — Invocation-scoped post-submit materialization runtime

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Risk: L1 — verified artifact bytes, worker cancellation and exact checker authority.
- Intended merge outcome: the existing hidden evaluation-request handler can use the already managed worker ART provider through a real materialization port, with invocation-scoped bounded scratch and full cleanup. Production outbox registration, false-guide activation and public intake remain later 04E3/02I boundaries.

## Intent

[B7](WS-ARCH-001-04E1BB7.md) already owns the hidden request handler and its exact invocation-fenced CHECKERS executor. `app/adapters/tasks.evaluation_request_handler` requires a `PostSubmissionMaterializationPort`, but the concrete constructor, `app/adapters/artifacts.post_submission_materialization`, requires a store, namespace, scratch preparation and inspector supplied by an enclosing runtime. The Celery child already initializes a provider runtime once and closes it on shutdown; ART's guide access adapter already leases that runtime. The outbox request handler lacks the invocation-scoped scratch/materializer composition that can safely lease it. This slice closes that actual lifetime gap by reusing the provider lease and existing materializer, without another evaluator, dispatcher or provider runtime.

The parallel [04F remediation](planning/chunks/WS-ARCH-001-04F-checker-remediation.md) owns failed-checker findings and resubmission. It may proceed at the same time because this slice does not alter CHECKERS results, routing, remediation or public APIs. The final 04E3 registration must use 04F's one completed-event handler for both successful and remediating results; the current completion handler rejects non-`allow_review` results, which would dead-letter them if registered early. Registration also changes the REV controller's reviewed manifest and requires actual admission/drain proof, so it is not part of this PR.

## Bounded change

1. Add one concrete ART adapter implementing the existing `PostSubmissionMaterializationPort`. On `materialize(facts, consumer)` it obtains canonical settings, initializes the existing worker provider runtime if needed and leases it through ART's existing `_artifact_internal_runtime` context. Construct the existing `ArtifactScratchManager`, `ArtifactPreparationService` and `SubmissionArchiveInspector` for that invocation, then delegate to the existing `post_submission_materialization(...)` owner. Construct no provider or scratch resource when the adapter is instantiated. Keep the provider lease and scratch lifetime wholly around that single awaited materialization call. Close the scratch manager and release the lease on success, denial, storage failure and cancellation; do not retain a material view or provider reference in the returned facts.
2. Reuse the same settings-to-limits mapping and process provider runtime used by other ART worker operations. No second provider bootstrap, direct S3/MinIO client, new configuration flag, fallback provider or alternate materializer. Keep the existing materializer's short AUTH/CHECKERS/ART transactions and its post-I/O lineage recheck; this adapter owns only invocation lifetime.
3. Supply the concrete adapter to the existing hidden `evaluation_request_handler` in focused tests and execute its real request-to-result path with PostgreSQL and MinIO. Do not change the hidden handler's event, request, execution or completion semantics. Production registration remains absent and is asserted.

## Allowed files

- `backend/app/adapters/artifacts/__init__.py` for the concrete invocation-scoped adapter and reuse of current ART construction helpers.
- `backend/tests/test_post_submit_materialization.py`, `backend/tests/post_submit_materialization_helpers.py` and focused tests under `backend/tests/tasks/evaluation_delivery/` for real hidden handler, cleanup and provider-lease lifetime. Existing shared fixtures may change only where a real provider-bound test needs them.
- `backend/scripts/test_lane_catalogue.py` and `backend/tests/test_ci_lane_catalogue.py` to place the new PostgreSQL/MinIO module in existing TASK lanes without changing their limits or moving older tests.
- This record, the affected ARCH overview/plan/map and `docs/roadmap_status.md` only if the hidden capability or next dependency changes on merge; relevant ownership inventory/tests if the new adapter changes an enforced boundary. No migration is expected.

## Prohibited

No production outbox handler registration, worker entry-point change, REV controller/manifest or PROJECTS guide-readiness change, false-guide activation, public ZIP/Submission endpoint, checker-result classification, remediation writer, new materialization implementation, new authority action, generic service locator, provider-coordinate response or retained-data rewrite. Do not create an unused interface parallel to `PostSubmissionMaterializationPort`.

## Acceptance criteria

- Constructing the adapter performs no provider initialization or scratch allocation. The existing Celery child provider init/shutdown and ART worker lease continue to own provider lifetime; assignment delivery and outbox scans do not acquire an extra materialization lease.
- A valid B6 committed Submission/request, B7 invoked envelope, real PostgreSQL, MinIO and existing fixed-service authorities reach the existing hidden request handler through this adapter. It persists the exact CHECKERS run/result and completion event; no production registry membership is inferred. A valid control must reach materialization before a negative assertion is credited.
- Wrong or stale Submission, byte/hash/manifest mismatch, absent object, denied authority and unavailable provider fail through the existing owner error path without a trusted result. Cancellation and deadline cleanup leave no active scratch reservation or usable retained material view. Tests inspect provider/scratch closure and durable SQL effects; they do not substitute fake bytes for the PostgreSQL/MinIO claim.
- Resource construction failure closes only what was acquired, and a successful call returns detached result facts after scratch cleanup and provider-lease release. The process provider remains available for other worker operations until normal Celery shutdown. Existing B7 replay/currentness, UNKNOWN and invocation fencing tests remain effective.
- Run focused PostgreSQL/MinIO handler and ART tests, pure construction/cleanup checks, Ruff, module boundaries, ownership inventory, links/stale wording and exact-head hosted CI. Remove any duplicated setup introduced by this slice rather than retaining two worker runtime paths.

## Risk and review routing

This adapter may merge before 04F because it changes no production registration or false-policy availability. After 04F is merged, final 04E3 must register the existing request handler and 04F-aware single completion handler in the sole `production_outbox_delivery`, revise the REV manifest and prove async admission/drain, restart and false-guide readiness before enabling false. Current outbox drain is project-scoped and B6 creation does not yet enter a REV fence; registration cannot be treated as a registry-only edit. ARCH-02I public intake and the realistic first-layer drill follow those proofs. Review the narrow ART resource lifetime, cancellation closure and absence of early activation; hidden execution is not the public contributor milestone.

Plan review precedes implementation. Required implementation review: architecture, security/authorization and QA; add reuse, CI integrity and docs review for affected composition, tests and capability wording.

## Evidence

The focused runtime proofs use a freshly migrated PostgreSQL database and an isolated MinIO namespace. The local provider uses the same hidden handler; neither provider claims production registration.

| Boundary | Proof |
| --- | --- |
| Actual B6 request through B7 with worker ART lease and no registry entry | `backend/tests/tasks/evaluation_delivery/test_worker_materialization.py::test_worker_art_lease_executes_exact_hidden_request` (local and MinIO) |
| Cancellation during provider streaming and consumer evaluation revokes material and releases scratch/lease | `test_worker_art_lease_cancellation_revokes_view_and_scratch` |
| Provider bootstrap uncertainty leaves no trusted result | `test_worker_bootstrap_unavailable_has_no_trusted_result` |
| Failed scratch construction releases an acquired provider lease | `test_worker_scratch_construction_failure_releases_provider_lease` |
| Failure after manager acquisition closes that manager and its provider lease | `test_worker_post_acquisition_failure_closes_scratch_and_lease` |
| Verified object loss yields the existing durable infrastructure outcome | `test_worker_known_missing_object_records_infrastructure_result` |

The existing ART materializer tests retain exact byte/manifest, authority, stale-source and replay proof. This slice has no checker-result or AUTH implementation change.
