# WS-EXEC-001-02 — Upload-overlapped trusted intake

- Initiative: WS-EXEC-001
- Durable disposition: Complete
- Intended merge outcome: prepare one bounded trusted intake microVM during the authorized ZIP upload, inspect/extract and run the Workstream default inside it, and feed the existing PRE/POST owners verified material without host ZIP/default execution.

## Intent

Reduce contributor and agent waiting by preparing one clean, bounded VM during
the authorized upload. Both PRE and POST must use the same trusted isolation
boundary for ZIP handling so submitted bytes never select a host parsing path.

## Current behavior

Boundary 1 supplies real Smol execution and recovery through CHECKERS' existing
adapter. Public upload still invokes ART's host `SubmissionArchiveInspector`,
then CHECKERS directly projects the archive and evaluates the default on the
host. Durable POST also projects on the host. Those call paths miss both the
requested overlap and the fresh-VM custody for all ZIP processing.

The user authorized continuing through this boundary and the separate full
public API/durable-worker drill. A node probe is not completion.

## Bounded change

### Allowed

- `backend/app/interfaces/`: narrow typed trusted-intake capability and session;
  shared external adapter convention remains unchanged.
- `backend/app/adapters/artifacts/`, `backend/app/adapters/checkers/__init__.py`,
  `backend/app/core/config.py`: explicit typed factory/constructor registration,
  required ART node configuration and scoped PRE/POST composition.
- ART `api/`, `submission_archive.py`, `submission_admission.py`,
  `submission_materialization.py`, `post_submit_materialization.py` and affected
  imports: canonical structural types, verified raw-file materialization and
  existing request-scoped preparation. `preparation.py` and `sources.py` for the explicit inspection cancellation hook;
  `trusted_intake.py` for the shared PRE/POST preparation lifetime and retained-reader binding.
- CHECKERS `api/default_checker.py`, `api/materialization.py`,
  `selected_pre_submit_execution.py`: typed default execution/material-view
  consumption; ordered project PRE execution and existing result semantics.
- `external_checkers/`: private prepared-intake protocol sharing the existing
  Smol machine/guardian engine, trusted intake image using canonical Python
  inspection/default code, controlled guest scratch/streaming and proof fixtures.
- Focused owner/adapter/conformance tests, their exact architecture inventories, explicit CI catalogue membership, and the four new production modules in `backend/scripts/behavior_ownership.py` and `.ci/behavior-ownership/partition.v1.json`; affected runtime documentation,
  configuration examples, roadmap and initiative records.

### Not allowed

No policy, authorization, database schema, persistent workflow, submission,
review, acceptance, award or artifact-store semantic changes. No project image
may assert ART inspection or Workstream default authority. No host ZIP/default
production fallback, generic command API, project VM handle, new scheduler,
managed service or edits to the independently owned model gateway work.

## Design and decisions

1. Add `trusted_submission_intake/unix_socket` through
   `ExternalServiceAdapterFactory[TrustedSubmissionIntakeAdapter]`, registered
   only in the ART composition root. Its health requires Smol and the node-owned
   pinned intake image/config plus the exact default behavior digest. CHECKERS'
   existing health cannot satisfy ART readiness. A deployment can point both
   typed capabilities to one Smol node; retaining a Docker/runsc project node
   requires a separate Smol intake socket. There is no runtime fallback.
2. Publish canonical structural data types through an ART API leaf and update
   affected callers. Keep one implementation of ZIP validation and default
   rules, packaged into the trusted intake image from this source. Wire encoding
   validates those same contracts; do not fork normalization or checker rules.
3. Start one process-local preparation immediately after the first successful
   TASK/project authorization transaction and before consuming upload bytes.
   Upload and VM preparation run concurrently. The original artifact deadline
   bounds the whole intake session; preparation failure, upload failure,
   cancellation or disconnect aborts and drains its transport/VM cleanup.
4. After sealed upload, preserve the existing relock and materialization AUTH
   transaction ordering. Send the sealed bytes through `PreparedArtifact.inspect`
   with a trusted-session inspector and explicit cancellation hook. Do not call
   `committed_source.stream()`: its one-shot `stream_claimed` flag would prohibit
   the later workspace callback and external grants. Invoke only inspect/extract,
   not default evaluation,
   under that authorization. Return the exact archive identity and canonical
   inventory. Bind the existing manifest, selected PRE reservation and authority
   exactly as today. No early VM action creates a Submission or CHECKERS result.
5. Under the committed selected lease, ART opens its existing
   `_process_prepared_submission` quota-owned scratch callback
   and exports bounded raw files from the sealed intake session. ART independently
   checks normalized containment, inventory, size, executable mode and every hash;
   it alone creates scratch paths and issues existing external material grants.
   CHECKERS receives only a callback-scoped material view and the typed default
   result after ART has invoked its trusted-intake port and confirmed cleanup,
   removing its current direct `_projected_tree` private call. This keeps the
   same required default-before-project order with fewer cross-owner callbacks.
6. The typed default operation binds the exact committed reservation, policy,
   archive, manifest and existing default input. The trusted guest runs the
   canonical evaluator once. After verified export/default, close the intake VM
   before executing any project PRE image, so waiting intake VMs cannot hold
   every node slot while requesting project execution. Preserve locked order,
   stop-on-failure and distinct infrastructure outcomes.
7. POST starts the same ART intake during its authorized artifact download,
   inspects/exports under the existing current CHECKERS lease, then closes the
   intake before invoking the project consumer. Preserve the later authority,
   material identity and lease revalidation before accepting its result.

## Private session and guest mechanics

Use the existing Smol `Machine` and exact guardian cleanup, extracting only a
small private resource tuple where both consumers require it. A random boot epoch,
lease nonce, trusted image/platform/config/default behavior identities, phase,
policy hash, resources and one absolute deadline bind the prepared session. Later
operations add sealed archive hash/size and manifest/reservation identity. The
opaque Python handle cannot be serialized, replayed, substituted or used after
close. The node connection owns it; EOF expires it. Preparation permits at most three attempts, with fixed 100 ms then 200 ms
backoff charged to the original deadline. Only an explicit `runtime_unavailable`
control-process launch/nonzero failure in VM create/start or trusted bootstrap
installation is retryable, and only after confirmed cleanup. Image/config/digest,
peer/custody, resource enforcement, protocol, capacity, cancellation and deadline
failures are final. Guest readiness identity mismatch is final. There is no
in-session retry after any archive byte is accepted, nor after inspect, export
or default invocation. Unknown execution status is final.

The static bootstrap gains a closed trusted-intake mode selected only by node
configuration. The pinned Python worker has bounded writable private VM-disk
scratch and persistent framed control I/O; project-image confinement is unchanged.
It receives bounded raw ZIP bytes, runs canonical inspect/project, exports raw
files, and accepts default input only in the correct later phase. Control frames,
raw byte counts, output and stderr are bounded. No credentials, host socket,
arbitrary host path or public network is exposed. ART host scratch remains under
`ArtifactScratchManager`; VM state is transient processing, not artifact storage.

Transport cancellation explicitly shuts down sockets and drains blocking work;
cancelling an `asyncio.to_thread` await alone is insufficient. A failed or unknown
inspection/default execution does not cause an unsafe in-session retry. Existing
request/retry and durable-worker owners decide the next business attempt.

## Acceptance criteria

| Atomic behavior | Owner and required proof |
|---|---|
| Upload overlaps preparation | Public preparation command fixture blocks upload and observes adapter prepare before upload release; no reservation/default yet |
| Unauthorized upload allocates no VM | AUTH denial fixture observes zero intake prepare calls and unchanged product rows |
| Failed upload/cancel/expiry releases capacity | Real-node session plus upload failure fixture; exact lease, VM disk and cgroup absence; original deadline not reset |
| Work ZIP failures remain bounded intake feedback | Canonical malformed/encrypted/collision/traversal/expansion corpus through guest; no Submission or project check |
| Guest inspection preserves prepared custody | Real `PreparedArtifact.inspect` followed by `_process_prepared_submission` and an external grant on the same artifact; no one-shot committed-source read |
| Smol-only ART readiness | Default-only PRE and POST fail on absent configuration, Docker/runsc runtime or mismatched image/config/default digest; valid split Smol-intake/Docker-project configuration works; poisoned host parser/default is never invoked |
| Inventory and raw export stay authoritative | Alter receipt/archive/hash/path/length/epoch/phase/policy; host rejects before grant/consumer and removes quota scratch |
| Default follows committed reservation | Separate observe-before/after-commit proof; replay/foreign reservation and second default rejected |
| Default failure skips project execution | Exact default findings, no external grant execution and no Submission |
| Successful default releases intake before ordered project PRE | Same Smol socket with `maximum_parallel=1`, default-only and two ordered bindings: observe intake cleanup confirmed, then capacity released, then first project connection; cancellation/uncertain cleanup never reports release |
| POST uses the same guest intake | Real immutable input/lease fixture, exact manifest and late revalidation, no host ZIP invocation |
| Canonical rules have one implementation | Existing corpus remains; source/composition negative checks reject production host inspector/default calls |
| Existing policy branches remain | Required checks still feed existing true-policy review routing and false-policy shared acceptance; full public durable proof belongs to boundary 3 |

## Live-drill repair: sequential material grants

The public two-binding trial exposed that the canonical grant publisher moves
exported files below `workspace/`, but revocation removed only its manifest.
The second binding then inspected an extra directory level and failed before
execution. Restore the sealed exported tree when revoking each exact grant,
including submissions that themselves contain `workspace` or the manifest name.
Keep one bounded scratch reservation and preserve per-request revalidation.
Strengthen the existing ordered lifecycle test to use the real ART grant owner;
verify a restoration-disabled mutant fails. PRE and POST also verify sealed
directory/file permissions after each grant; a permission-restoration mutant is
rejected before a later grant can hide the defect. Retain reserved-name/cleanup tests and rerun
the real public two-binding case. This repair belongs to this boundary's existing
ART preparation scope; it adds no policy or runtime path.

## Evidence

Run relevant owner/adapter suites, canonical archive/default corpus, real
PostgreSQL integration and live KVM intake/cleanup tests. Full suite and public
Celery journey remain blocking before the overall user goal is complete.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture/reuse, security, QA/test-delta, product/operations, documentation; CI integrity if workflow changes become necessary.
- Human review focus: preparation before bytes versus authority, two-phase default ordering, exact material export custody, cancellation/deadline cleanup, and explicit deployment prerequisites.
- Plan review: required before implementation; no implementation proof claimed here.

## Review findings

Plan corrections address WS-EXEC-001-02-PLAN-01..04: safe inspect-then-workspace
custody, distinct Smol readiness cases, discriminating single-slot ordering and
closed preparation retry policy. Plan replay passed on `4b86aa3054d4fe79e92c7253665b9394fd36bbf8` before implementation.

## Reconciliation

After this boundary's verified implementation: deployment composition and the
public PRE -> immutable Submission -> durable POST -> governed outcome drill,
including failure/retry, both review-policy branches and exact contribution facts.

## Implemented boundary and proof limits

The typed adapter, closed guest worker and Rust prepared session connect PRE and
POST to canonical guest ZIP/default processing. Confirmed intake cleanup precedes
ordered project checks. An ART deadline after confirmed cleanup finalizes the
selected run as `deadline_exceeded`; an unconfirmed close retains unresolved lease
recovery. Caller cancellation drains both upload and preparation, and exact
committed reservation fields bind default evaluation before any project grant.

The maintained real-node intake matrix passes PRE/POST retained-reader export,
PRE default and ART grant issuance with host ZIP/default execution poisoned.
Abandoned upload, cancellation, idle deadline and malformed ZIP recover the
one-slot node. The streaming probe exposed and repaired misuse of the one-shot
project trailing-byte guard; its socket-pair regression now protects legitimate
pending ZIP input. The ART exporter accepts the retained directory-FD path while
preserving descriptor-relative child containment.

Real PostgreSQL/MinIO proof covers verified original material, immutable
Submission/lease custody, late authority and content drift, cancellation and
scratch revocation, durable worker materialization and public intake outcomes.
The combined 140-case EC2 run passes with database and MinIO cleanup confirmed.
These transaction fixtures explicitly inject an in-process intake fake; the
separate KVM matrix establishes the real adapter/guest boundary. Neither proof
is mislabeled as a public API -> Smol -> durable worker -> governed outcome drill.
That combined proof and deployment composition remain boundary 3.

Implementation review findings repaired the exact default-binding assertion,
combined upload/preparation cancellation, and recoverable deadline finalization.
Hosted checks also exposed collection-time ZIP timestamps and an oversized test
module. Deterministic ZIP metadata/stable case IDs and a focused intake lifecycle
test module repair those defects without loosening the structural guard or test
selection. Exact architecture and CI inventories retain all prior assignments.
Required full hosted-suite evidence and reviewer receipts belong to the PR's
current candidate; no deployment or complete user-journey claim is made here.
