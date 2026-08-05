# Discovery: WS-ART-001 S3-Compatible Object Storage Amendment

## Repository State

- `WS-ART-001-01` merged through PR #101 as `050eb15`.
- `backend/app/interfaces/artifacts.py` defines `ArtifactStore`.
- `backend/app/adapters/artifacts/local.py` implements LocalStorage.
- `backend/app/modules/artifacts/service.py` coordinates provider I/O outside
  PostgreSQL transactions.
- `backend/app/modules/artifacts/models.py` already contains upload, content,
  replica, receipt, and binding foundations.
- `backend/app/adapters/artifacts/__init__.py` has one resolver with a dormant
  `flow_node` branch that always fails.
- `backend/app/core/config.py` accepts `disabled|local|flow_node`; no
  S3-compatible object-storage configuration exists.
- `backend/pyproject.toml` has no asynchronous S3 SDK dependency.
- `docker-compose.yml` contains Postgres and Redis but no S3-compatible local
  service.

## Contract Mismatch Found

The merged v1 port makes providers own `verify`, `retain`, `release`, and
operation receipts. Those methods reflect the earlier Flow Node design and are
not the correct boundary for S3-compatible byte storage.

For v0.1:

- provider operations are immutable conditional put, open/range read, and
  head/status;
- Workstream independently verifies bytes through the read port;
- PostgreSQL owns operation receipts, bindings, reference state, and audit;
- physical delete is absent.

The v2 port must therefore replace v1 in one clean cut. No adapter alias or
compatibility shim is required because Workstream is still pre-production.

## AWS S3 Provider Facts Used By The Plan

- AWS S3 defines the production protocol contract and supports conditional
  writes, object head, full/range reads, workload identity, Block Public
  Access, bucket policy, and lifecycle inspection.
- Workstream independently computes SHA-256; ETag and provider metadata are not
  content identity.
- Production credentials come from one explicitly allowlisted AWS workload
  identity method. Static access keys are limited to local/CI MinIO.
- v0.1 uses one conditional single-request put and rejects objects above the
  hard size limit. Multipart completion is deferred until separately designed
  and proven.
- MinIO is protocol proof, not evidence that an AWS deployment is private or
  correctly authorized. AWS requires its own live readiness proof.

Canonical references:

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
- https://docs.aws.amazon.com/sdkref/latest/guide/standardized-credentials.html

## v0.1 Storage Algorithm

1. Prepare every untrusted source completely, compute Workstream SHA-256 and
   exact size, and reject any mismatched client commitment before provider I/O.
2. Seal that commitment with the exact second-pass stream.
3. Derive the private key
   `artifacts/sha256/<first-two-hex>/<remaining-hex>`.
4. Upload with one conditional no-overwrite `PutObject`; reject objects above
   the v0.1 512 MiB hard maximum before provider I/O.
5. Treat a precondition failure as a replay candidate, not success.
6. Head the existing object, then independently stream and hash the complete
   object before accepting it.
7. Mark the replica bindable only after SHA-256 and size match.

## Recovery Simplification

The S3-compatible object-storage design removes provider retain/release and
physical delete from v0.1.
Durable background work has one class:

- `provider_observation`: complete-object verification through fresh read;

There is no exact provider replay, destructive requeue, or ambiguous logical
provider effect in v0.1 recovery.

Operator authorization creates a reason-bound recovery envelope and linked
verification job. The job is the sole Celery execution owner. PostgreSQL
coordinates its invocations with a fixed lease, fresh executor UUID, and
generation fence. A periodic PostgreSQL scanner guarantees that a committed
job is eventually published even if the first broker call fails.

## Security Boundaries

- Authorization Service owns product decisions.
- S3 credentials authorize transport only and never imply product authority.
- Credentials come from deployment secret injection and never enter Postgres,
  Redis, Celery payloads, logs, receipts, or API responses.
- Only artifact-storage orchestration consumes the writable `ArtifactStore`
  through dependency injection and never imports the S3 implementation.
  Product modules and Celery jobs consume typed artifact operations instead.
- The S3 endpoint is trusted configuration. Production requires HTTPS and a
  private bucket; localhost HTTP is allowed only in local/test MinIO.
- No public bucket, custom-domain cache, or client-visible object key is used.
- Runtime credentials are bucket/prefix/action scoped. They cannot delete,
  copy, or administer provider configuration. AWS has bucket-level
  `s3:ListBucket` only so missing `HeadObject` can return 404; the port and
  application expose and call no object-list operation.
- Production release evidence proves AWS public-access controls, lifecycle
  safety, and anonymous-read denial.

## Deferred Flow Node

The previous Flow Node analysis is preserved on branch
`codex/ws-art-001-fn01-isolation-amendment`. A new deferred initiative will
retain the provider-conformance, focused-service, adapter, and migration plan.
It cannot block or modify v0.1 S3-compatible object-storage work.

## Deferred R2

Exact-head internal review found that the dual-provider plan introduced an R2
parent-credential and credential-issuer boundary that was not required to ship
v0.1. The user selected AWS S3 as the only production provider. R2 therefore
has no active runtime profile, credential service, deployment proof, or chunk;
later adoption requires separate discovery and approval.

The current pre-cutover application still accepts legacy caller-declared
provider schemes in guide-source, task, project-policy, checker, API-drill, and
template contracts. Those values have no active v0.1 provider meaning and do
not prove that Workstream can store or retrieve provider bytes. Chunk 03
removes direct provider schemes from guide-source identity. Chunk 05 removes
the remaining caller storage transport when submissions move to sealed
artifact-set bindings. No compatibility alias remains after either owning
cutover.

## ART-03B Materialization And Extraction Discovery

Merged ART-03A and AUTH `WS-XINT-002-04A` provide the covered Project Manager
upload boundary. AUTH preparation happens before request-body intake; final
transaction-bound consumption locks the guide lineage and server-computed byte
facts before durable intent or provider I/O. Upload stores opaque immutable
bytes and does not parse them.

The current setup pipeline cannot yet consume those bytes safely:

- its Celery payload has four identifiers but no setup generation;
- `ProjectSetupRun` has no explicit generation fence;
- `GuideSourceMaterial` uses caller-originated metadata and optional excerpts,
  not verified ART bindings;
- no authorized integrity-checking guide read exists in project services;
- no typed detector, extractor registry, extraction policy, or canonical
  extraction record exists.

AUTH's reviewed `WS-XINT-002-04B` activates only fixed-service guide binding
and read. It does not grant a derived-artifact write. v0.1 therefore persists a
bounded canonical extraction record and provenance in PostgreSQL; a future
derived provider artifact requires a separately planned action and activation.

No document-parsing production dependencies are installed. Any new production
dependency requires explicit human approval through 03B3B1 before format implementation. OOXML ZIP
containers must pass one bounded classifier that distinguishes DOCX, PPTX, and
XLSX by internal markers. Audio/video transcription and OCR are not required by
current v0.1 setup and remain unsupported. PNG/JPEG/WebP classification and
metadata do not imply OCR or textual sufficiency.

## 2026-08-02 End-to-End v0.1 Planning Audit

Current `main` contains all ART guide implementation through `03B4`. During
this audit AUTH-04B was still pending; it subsequently merged in PR #245 at
`6babf81b`. Both fixed-service guide binding/read actions are now active, so
ART-03C may start after this planning reconciliation merges.

The remaining map had four material defects:

1. statuses still described merged 03B chunks as proposed or active;
2. 04A, 04C, 05, and 07 crossed too many L1 boundaries for one PR;
3. XINT-05A would activate contributor preparation before the fixed
   `artifact.pre_submit.checker_input.materialize` service action, even though
   hidden 04B makes that authority mandatory inside the continuous request;
4. ART ended at checker routing while XINT expected later reviewer artifact
   capabilities and the product intent required accepted contribution records
   to retain the same artifact identity.

The corrected finish line is bounded: ART owns guide cutover, one-ZIP intake,
semantic identity, prechecks, durable ready admission, atomic Submission
binding, checker materialization/output custody, reviewer packet byte access,
and accepted-contribution identity projection. REV owns review lifecycle and
notes/findings; CON owns ContributionRecord; client delivery remains a future
owner and is not silently implemented by ART v0.1.

## 2026-08-04 ART-04A1 Legacy Contributor Intake Discovery

Observations on merged `main` at `2feaf47d`:

- No HTTP route currently exposes upload-session or upload-item creation, but
  `ArtifactUploadSession` and `ArtifactUploadItem` remain active SQLAlchemy
  metadata in `app/modules/artifacts/models.py` and `app/db/models.py`.
- `ContributorArtifactAdmissionRequest` in
  `app/modules/artifacts/schemas.py` remains an internal command that accepts
  caller authorization plus an upload-item id. `ArtifactAdmissionService`
  still dispatches that type through `_contributor_facts`, so the obsolete
  contributor intake remains reachable to internal callers even without an
  HTTP route.
- `ArtifactRepository` still exposes upload-item/session locks, contributor
  relationship lookup, and upload-item receipt lookup. These methods are used
  only by the retired contributor path and compatibility state projection.
- Shared put recovery and verification still conditionally mutate an upload
  item when `ArtifactPutAttempt.upload_item_id` is present. Removing the two
  ledgers therefore also requires removing those compatibility mutations while
  preserving guide and checker-output recovery.
- `ArtifactPutAttempt.upload_item_id` and
  `ArtifactOperationReceipt.upload_item_id` still foreign-key the legacy item
  table. Receipt contract version 1 identifies historical acknowledgements only
  through `upload_item_id`; version 2 may also carry it for contributor puts.
  Historical audit values cannot remain readable if the column is dropped.
- Existing migration tests already seed populated legacy sessions/items,
  attempts, and receipts and exercise database invariants. ART-04A1 needs a new
  head migration that refuses unsafe populated cutover instead of fabricating a
  replacement identity or silently deleting evidence.
- AUTH has already removed the obsolete action identifiers from the active
  catalogue and service matrix; `tests/test_authorization.py` retains the
  deterministic historical-only proof. ART must not edit AUTH availability or
  create aliases.

Implementation constraints derived from the current code:

- Remove the contributor admission request variant, service dispatch, repository
  relationship methods, upload-ledger models, and conditional upload-item state
  projection from shared recovery/verification.
- Do not detach or preserve nullable `upload_item_id` compatibility columns.
  Refuse any populated historical reference before dropping the columns and
  ledgers, leaving that deployment unchanged for a separate maintenance decision.
- The migration must fail closed when rows exist whose deletion would discard
  non-represented contributor state. Upgrade/downgrade behavior and the exact
  safe-empty condition require plan-review approval before implementation.
- No replacement route, ZIP parser, scratch orchestration, provider write, AUTH
  action activation, Submission, checker, or review behavior belongs to 04A1.

Plan-review resolution:

- 04A1 is a complete safe-empty clean cut. It takes exclusive locks and refuses
  atomically when any session/item row, contributor put attempt, contract-v1
  receipt, or non-null upload-item reference exists. Refusal preserves the old
  schema and all historical identifiers for a separately approved maintenance
  decision. A successful upgrade therefore removes the contributor columns and
  ledger tables completely; it does not retain detached compatibility fields.
- Downgrade recreates only the exact empty legacy schema proven by the upgrade
  precondition. It never fabricates a session/item lineage from newer facts.

## 2026-08-04 Default Pre-Submission Checker Catalogue Discovery

Merged ART-04A2/04A3 already own outer-ZIP safety, resource bounds, archive
identity, canonical semantic manifests, executable normalization, and the
unchanged-work gate. These trusted capabilities must be registered into
pre-submission execution, not reimplemented as another checker stack.

Projects already merge `WorkstreamDefaultSubmissionArtifactPolicy` with the
approved `SubmissionArtifactPolicy`, and the trusted compiler emits a locked
`PreSubmitCheckerPolicy`. The remaining defects are execution shape and
catalogue ownership:

- checker names/defaults are spread across policy constants, compiler
  primitives, legacy registry code, templates, and historical docs;
- the legacy `/tasks/{task_id}/submission-precheck` accepts caller-owned packet
  and manifest facts and cannot be the authoritative one-ZIP execution path;
- combined 04B crosses catalogue, sealed materialization, platform execution,
  project execution, persistence, and API-result boundaries;
- broad forbidden-name patterns can false-positive legitimate generic projects;
- `disabled` has no safe canonical meaning for non-bypassable defaults.

PLAN4 splits 04B into catalogue/effective-plan composition, sealed default
execution, and locked-project execution/evidence. v0.1 catalogue state is
startup-validated deployment configuration. Disabling mandatory custody,
integrity, or accountability fails preparation closed; only advisory entries
may be disabled while remaining execution continues. Project policy and
task/runtime input cannot toggle catalogue availability.

The catalogue snapshot is immutable. Its version, canonical manifest digest,
ordered entry ID/version/configuration hashes, and enabled/disabled state are
embedded in the compiled `PreSubmitCheckerPolicy`. The existing task-locked
compiled-bundle hash therefore commits to the exact default snapshot without a
second task-lock field; runtime derives and records the effective-plan hash from
that same snapshot plus the locked project rules.

## 2026-08-05 ART-04B2 Default Checker Execution Discovery

Observations on merged `main` at `bb77ff4a`:

- `ArtifactPreparationService` already owns the one process-local
  `PreparedArtifact`, its server-computed archive commitment, a read-only
  anonymous second-pass stream, deadline enforcement, and idempotent release.
  `PreparedArtifact.inspect()` is therefore the only acceptable outer-ZIP read
  seam for 04B2.
- `ArtifactScratchManager.extraction_workspace()` already provides the bounded,
  private, crash-recoverable workspace required for a projected checker tree.
  04B2 must extend this existing custody path; it must not create another scratch
  manager or use direct temporary paths.
- Its current recursive cleanup incorrectly reuses `maximum_files` (default 8),
  while archive admission permits 2,000 entries, and workspace expansion is not
  charged as a separate byte/entry reservation. 04B2 must repair that shared
  quota contract before projecting any untrusted tree.
- `SubmissionArchiveInspector` is the canonical 04A2 ZIP implementation and
  returns normalized paths, entry types, per-file SHA-256/size, and normalized
  executable intent. `SubmissionManifest` is the sole 04A3 semantic identity.
  Materialization must reuse those exact facts and reject any projected mismatch
  before exposing the tree to checker adapters.
- `PreparedBundleMaterializationRequest` and
  `ArtifactMaterializationPort.materialize_prepared_bundle()` already reserve
  the hidden fixed-service seam. The AUTH catalogue maps
  `artifact.pre_submit.checker_input.materialize` exclusively to
  `workstream.artifact.materializer`; `AUTH_ART_04B` is its catalogue custodian,
  while XINT-06A is the later planned activation point after hidden 04B3.
- ART-04B1 now owns the single immutable catalogue and effective execution plan.
  No execution module exists yet. The platform/default executor must consume the
  exact plan identity and ordered entries rather than reconstructing checker
  names, dependencies, classifications, or enabled state.
- The legacy checker runner consumes mutable pre-Submission/task ORM objects and
  caller-shaped packet manifests. Its small pure validation helpers may inform
  behavior, but its registry/context is not the authoritative 04B2 boundary and
  must not become a second catalogue or a dependency of the sealed tree.
- No `SealedSubmissionTree`, bounded catalogue-result type,
  `test_checker_materialization.py`, or
  `test_default_pre_submit_execution.py` exists on current main.

Implementation constraints derived from current code:

- Add one canonical projection capability alongside the canonical ZIP inspector,
  so structural validation and extraction cannot drift into separate ZIP
  implementations. Projection re-reads each member once, compares the exact 04A
  entry facts, writes with no-follow/exclusive semantics, and seals fixed modes
  before returning a process-local capability.
- A sealed-tree capability may expose bounded trusted reads to checker adapters,
  but it may not expose a serializable scratch path, execute a submitted file, or
  outlive its `ArtifactScratchManager` workspace.
- The implementation uses callback-scoped ownership: the prepared-artifact owner
  authorizes first, reserves an expanded-byte/entry workspace, projects and seals
  the tree, dispatches adapters, then cleans the workspace before returning only
  bounded results. This removes any optional-close or escaped-path lifetime.
- Execute only custody, identity, materialization, and default-policy entries in
  04B2. Project-policy entries remain untouched for 04B3, and no result becomes
  durable in this chunk.
- Default-policy configuration is not read back from the merged project policy.
  Each adapter's closed Workstream-default semantics are versioned by the exact
  catalogue entry ID/version and catalogue-manifest hash already committed into
  the effective plan. Changing those semantics requires a definition-version and
  catalogue-version decision rather than an untracked runtime constant change.
- Custody and identity adapters validate the already-produced 04A typed facts;
  they do not perform a third archive inspection or compute a competing identity.
  The materialization entry is the gate after which default-policy adapters may
  receive the sealed-tree capability.
- Result envelopes must be fixed-size, path-redacted, plan-bound, and explicit
  about pass, blocking failure, advisory warning, or advisory-disabled state.
  Dependency failure stops dependent dispatch; a disabled mandatory definition
  is infrastructure-unavailable and can never be emitted as success.
- Prepared authorization is consumed through the existing opaque handle at the
  hidden fixed-service composition seam before any prepared-byte read, ZIP open,
  workspace reservation, or checker fact. Until XINT-06A activates the action
  owned in the catalogue by `AUTH_ART_04B`, production composition remains fail
  closed. Because AUTH intentionally has not activated this action, tests use a
  typed, bounded protocol double and opaque handle sentinel; the denial path
  uses production `DenyPreSubmitMaterializationAuthorization`. Live AUTH proof
  remains owned by XINT-06A.

Plan-review correction: the canonical projection must be a method of
`SubmissionArchiveInspector` or use a private traversal shared solely inside
`submission_archive.py`. The 04B2 executor accepts a closed phase slice and
rejects or ignores no entries: encountering a project-policy or policy-primitive
entry in its dispatch set is a caller/plan error, while the normal complete plan
is sliced deterministically before dispatch. Tests must also prove the legacy
checker registry and standalone precheck path are not consulted.
