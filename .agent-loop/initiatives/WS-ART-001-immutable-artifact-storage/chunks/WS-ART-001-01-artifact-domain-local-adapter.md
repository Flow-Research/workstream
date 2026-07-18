# WS-ART-001-01: Artifact Domain And Local Adapter

Parent: `WS-ART-001` | Repository: Workstream | Risk: L1 | SLA: P1

## Goal

Implement versioned provider contract fixtures, provider-neutral artifact
records/port, configuration, and `LocalStorageAdapter` conformance.

## Allowed Files

- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/WS-ART-001-01-artifact-domain-local-adapter.md`
- `contracts/artifact-store/version_1/**`
- `backend/app/interfaces/artifacts.py`
- `backend/app/modules/artifacts/**`
- `backend/app/adapters/artifacts/**`
- `backend/app/core/hashing.py`, `backend/app/modules/audit/repository.py`
- `backend/app/core/config.py`, `backend/app/db/models.py`
- `backend/pyproject.toml`
- `.github/workflows/backend.yml`
- `.github/workflows/agent-gates.yml`
- `AGENTS.md`
- one new `backend/alembic/versions/*.py`
- `backend/tests/test_artifacts.py`, `test_config.py`, `test_alembic.py`
- `backend/tests/conftest.py`
- `scripts/check_stale_artifact_contracts.py`
- `scripts/test_agent_gates.py`
- owning artifact docs only

The workflow and repository guidance changes are an explicit human-directed
coverage amendment. This chunk must keep its artifact subsystem at or above 90
percent while preserving the temporary repository-wide 78 percent baseline.
Separate authorized work owns raising global coverage to 90 percent.

## Not Allowed

No public upload API, Flow Node adapter, product cutover, provider call in a
lifecycle transaction, legacy-field removal, or WS-AUTH implementation.

## Implementation Contract

### Workstream Coordination

`ArtifactRepository` and `ArtifactIngestService` under
`backend/app/modules/artifacts/` own transaction A, the provider call outside
the transaction, transaction B, recovery, quarantine, and shared audit writes.
They lock/CAS the session and item, commit reservations before provider I/O,
then re-lock before creating content, replica, and Workstream receipt rows.
Staging never calls binding persistence. The adapter remains independent of
SQLAlchemy, product records, and `AuditRepository`.

Provider-owned local receipts, append-only Workstream
`ArtifactOperationReceipt` rows, and shared `AuditEvent` rows are three distinct
records. Binding, release, quarantine, and reconciliation write audit evidence
in the same caller-owned database transaction as their domain transition.
This merged v1 chunk used automated reconciliation. The object-storage
amendment supersedes that runtime concept: future v2 provider observation is
attributed to `workstream.artifact.verifier`, never to a fabricated human actor.

### Provider Contract

Version 1 covers store, confirmed-store recovery, streamed open with optional
byte range, stat, verify, retain, release, and receipt lookup. Recovery requires
both expected SHA-256 and expected size and always returns a replay. `retain`
requires both an opaque
`retention_reference` and a `retention_class`; release requires the exact same
reference. DTOs define expected digest/size semantics, byte limits,
idempotency scope, typed retryable/terminal/input-mismatch/integrity/not-found
errors, bounded details, and opaque provider identifiers. JSON schemas use
JSON Schema 2020-12, reject unknown fields, and ship canonical request/response
hash vectors plus malformed, oversized, truncated, and replay-conflict cases.
Receipt lookup uses service principal, operation, and idempotency key. Byte
ranges use zero-based offset plus optional nonnegative length with an exclusive
end; offset-at-EOF is empty and offset-past-EOF is invalid. Focused tests
validate every schema and fixture with a pinned development-only `jsonschema`
dependency; no runtime schema dependency is introduced.

### PostgreSQL Invariants

- Sessions: states `open|sealed|consumed|expired|cancelled`; nonnegative limits,
  totals, and CAS; terminal timestamp/state consistency.
- Items: states
  `reserved|uploading|provider_committed|replay_required|ready|failed|cancelled`;
  nonnegative reservation/CAS; unique `(session_id, idempotency_key)`; exact
  request-digest and ready/content consistency.
- Content: exact lowercase `sha256:<64 hex>`, nonnegative byte count, unique
  `(sha256, byte_count)`, and database-enforced immutable update/delete guards.
- Bindings: immutable update/delete guards and monotonic `scope_version` per
  project/resource/logical role. Unique scope/version plus unique predecessor
  serialize concurrent inserts; a constraint trigger requires same-scope,
  immediately-prior supersession. Currentness is derived from maximum version.
- Replicas: unique `(adapter, provider_artifact_id)` physical copies; repeated
  identical content may have multiple provider copies under one adapter.
  Verification, retention, availability, and integrity observations remain
  separately constrained per physical replica.
- Receipts: append-only update/delete guards, unique
  adapter/service/operation/idempotency identity, and exactly one canonical
  request digest for that identity. Retention reference/class/owner are
  structured fields when applicable.
- Session aggregate reservations are enforced by repository row locking, not a
  false cross-row `CHECK` constraint.

### Local Durability And Recovery

The local root is non-symlinked and private. All derived names are validated
opaque identifiers. Directories are `0700`, files are `0600`, links and
non-regular files are rejected, immutable objects use exclusive no-overwrite
publication, and returned values/errors contain no path. A cross-process lock
serializes each idempotency scope. Retention changes additionally lock the
provider artifact, persist the creating service principal, and require that
owner for release.

The adapter pins the verified root with a directory descriptor. Storage
subdirectories and files are opened relative to pinned descriptors with
no-follow semantics, and opened file descriptors are validated directly.

Blocking filesystem calls execute off the event loop. Source chunks are
processed in slices no larger than the configured buffer and open streams close
deterministically. Publication order is durable private operation intent,
temporary write/hash/count, file
`fsync`, exclusive object publish, parent `fsync`, atomic metadata publish and
parent `fsync`, then atomic immutable receipt publish and parent `fsync`.
Cancellation waits for in-flight I/O before cleanup.

Recovery explicitly covers temp-only, object-only, metadata-only, and
receipt-only states. Exact replay fully consumes and independently hashes/counts
the bytes before returning the original object/receipt; changed
request digest fails before a second object; changed replay bytes are fully
hashed then rejected. Initial client commitment mismatch is
`artifact_input_mismatch`; altered persisted object/metadata/receipt/recovery
replay is `artifact_integrity_failure`. The adapter durably quarantines the
provider object and denies open. Before transaction B, Workstream fails the
item and creates no content/replica; for existing ready content, Workstream
separately quarantines the replica and writes audit evidence transactionally.
Reconciliation closes crashes between those systems. An ambiguous provider
exception or cancellation always makes the item `replay_required`, regardless
of supplied commitments. Byte-less recovery is reserved for a provider success
observed by Workstream with both expected SHA-256 and expected size persisted.

Object-only recovery without replay is an explicit recovery path requiring
both persisted expected SHA-256 and expected size. Normal `store` replay always
consumes the complete replay stream, including when commitments exist.

### Proof Matrix

- Adapter tests cover empty, exact-boundary, oversized, process restart,
  concurrent same-key, exact replay, request mismatch, replay-byte mismatch,
  missing/altered/truncated object, malformed/altered receipt, and cancellation.
- Deterministic fault points cover create, open, write, file `fsync`,
  publish, directory `fsync`, metadata publish, receipt publish, verify-read,
  and quarantine; tests assert cleanup, bounded read/write sizes, private modes,
  and sanitized errors.
- Coordinator tests assert exact content/binding/replica/receipt/audit counts.
  Receipt-only and pre-finalization integrity/input failures create zero content
  and zero binding rows; integrity failure on ready content preserves immutable
  content/bindings and quarantines only its affected replica. Replay creates no
  duplicate provider effect or audit event.
- Migration tests upgrade populated `0015` data to `0016`, prove legacy rows are
  byte-for-byte unchanged and artifact tables empty, exercise every PostgreSQL
  invariant directly, refuse non-empty downgrade, and prove empty
  downgrade/re-upgrade.
- The stale scanner has an explicit phase marker. Tests cover inactive, active,
  and malformed phases; current legacy terms remain allowed until their owning
  cutover activates.
- Local storage is allowed only in `local|dev|development|test` and rejected in
  `staging|preview|prod|production`. Enabled storage requires a nonblank
  retention-policy version during `Settings` construction. `flow_node` remains
  reserved and its resolver fails closed until the next chunk supplies it.
- Backend CI preserves the temporary repository-wide 78 percent baseline and
  independently fails this artifact subsystem below 90 percent. Separate
  authorized work owns raising the global gate to 90 percent.

## Acceptance Criteria

- Separate upload session/item, content, immutable binding, replica, and receipt
  records; staging creates no binding.
- Generic port exposes no CID/DAG/pin types.
- Manifest/request/response digests reuse or centrally extend
  `canonical_json_hash`; no artifact-local canonical JSON helper is added.
- Binding/release/quarantine/reconciliation audit evidence uses the shared
  `AuditEvent`/`AuditRepository`; operation receipts do not form a parallel
  audit framework.
- Additive migration succeeds with current legacy rows and promotes none.
- Local adapter performs bounded atomic writes, independent SHA-256/size checks,
  opaque IDs, private permissions, idempotent replay/mismatch, retrieval, verify,
  retain/release/status, cancellation cleanup, and no path leakage.
- Empty/boundary/oversize/disk-failure tests use overridden limits and assert
  cleanup plus bounded buffering.
- Crash recovery after an observed provider success with persisted expected
  digest and size reopens and independently hashes/counts provider bytes;
  ambiguous provider failure or cancellation requires exact client replay under
  the same idempotency key. Receipt-only, altered
  commitment/receipt/object/replay, and truncated-stream fixtures create zero
  content/binding rows and quarantine where integrity is implicated.
- Production configuration rejects local adapter and missing retention policy.
- A phased stale-contract scanner exists in this foundation chunk. It rejects
  obsolete artifact terms only after their owning cutover is active and is
  covered by focused gate tests, so later chunks cannot claim a scanner that
  does not yet exist.

## Verification

```bash
(cd backend && .venv/bin/ruff check app tests scripts)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest -q tests/test_artifacts.py tests/test_config.py tests/test_alembic.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

Reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, test delta.

Human focus: record separation, port neutrality, migration additivity, storage
privacy, and production guards. Stop after this PR.
