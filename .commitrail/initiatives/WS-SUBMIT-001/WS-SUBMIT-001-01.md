# WS-SUBMIT-001-01 — Single-request submission execution

- Initiative: WS-SUBMIT-001
- Durable disposition: Planned
- Intended merge outcome: the complete single-request submission specification, including durable intake, one-session PRE, accepted handoff, finalization, clients and end-to-end proof.

## Intent

Implement the [approved specification](../../../docs/spec_submission_execution.md)
in one PR with focused commits for each stage. The user explicitly requires the
complete end-to-end behavior and tests before requesting merge; intermediate
contract, schema or runtime stages are not separate merge checkpoints.

The first stage gives database, upload and execution owners one representation
of the original command and sealed source, separate from credentials and later
manifest facts.

## Current behavior

`artifacts/submission_admission.py` consumes process-local prepared ZIPs;
`interfaces/artifacts.py` derives keys from content SHA. The new design needs
operation-based keys before bytes are known and exact durable identity afterward.

## Bounded change

### Allowed

- `backend/app/modules/artifacts/api/submission_intake.py`: command and source values.
- `backend/tests/artifacts/test_submission_intake_contracts.py`: pure contract proof.
- `backend/scripts/test_lane_catalogue.py` and `backend/tests/test_ci_lane_catalogue.py`:
  register the new tests in the shared-foundations lane, preserving every existing member.
- `docs/spec_submission_execution.md`: user-supplied specification, with technical
  Celery-worker vocabulary qualified for repository documentation checks.
- `scripts/check_stale_authorization_docs.py`, `scripts/check_stale_review_contracts.py`,
  `scripts/test_lightweight_agent_gates.py` and `scripts/test_stale_review_contracts.py`:
  exact storage example exemptions and tests in already-selected CI modules;
  public API prefix enforcement remains unchanged elsewhere.
- This initiative, index and capability ledger: target and limited delivered scope.

- `backend/scripts/behavior_ownership.py`, its existing test module and
  `.ci/behavior-ownership/partition.v1.json`: register only the new immutable
  contract target in the protected partition after CI exposed the missing entry.

- Existing ART/TASK/AUTH/CHECKERS owners, composition roots, routes, migrations,
  storage/runtime adapters, durable continuation, CLI/MCP and their tests and
  current documentation as required by the specification. Each stage records
  concrete proof; incomplete stages remain unexposed until coordinated cutover.

### Not allowed

- Retained evidence deletion or rewriting, unrelated product changes, fabricated
  deployment defaults or unsupported storage/runtime qualification claims.
- Unrelated preparations or another open PR's branch.

## Design and decisions

Reuse canonical JSON hashing and the archive ceiling. Keys derive from server
UUIDv7 operation identity. Sealed values bind ART's `primary` namespace ID and
fingerprint, provider profile, raw SHA/count,
generation and fence. Metadata identity preserves exact packet and revision
selectors; actor/key scope and locked context remain separate operation facts.
Constructing these internal values grants no authority or provider qualification.

## Foreground custody stage

ART now has a private operation model/repository and TASK has a narrow custody
port plus a composite-bound active-operation pointer. Migration 0069 adds these
without rewriting retained rows. Actor/key uniqueness and one active operation
per task protect concurrent intake. Command, actual locked TASK snapshot,
namespace and source key are immutable. Recorded EOF precedes source sealing;
completed generation, raw digest/count and sealed upload fence cannot change.
A database-time lease fences stale publishers. Recovery can abandon expired
foreground work, never resume PRE or accept it.

Only receiving, pre_checking and pre-handoff terminal outcomes are currently
permitted. Accepted states remain denied until exact AUTH/CHECKERS/outbox handoff
is implemented. These flush-only persistence primitives provide neither storage
capacity nor provider capability nor authorization. Root transaction composition,
streaming, accepted handoff and public cutover remain work.

The schema comparison from 0068 to 0069 added one table, 33 columns (including
the TASK pointer), 24 constraints, six indexes, three functions and four triggers;
no previous schema objects or reference rows changed. Model registration uses
ART's `intake/models.py` through the canonical database model registry.

## Physical reservation stage

Source accounting extends ART's intake model/repository and migration 0069
with per-operation source-byte charges. The existing SHA-deduplicated admission
ledger remains intact for its consumers: it cannot count separate equal-content
source objects. Source quotas are a distinct configured allocation for this
managed prefix, not a claim to measure every existing object in the bucket.

Use one immutable namespace capacity profile and serialize reservation/sealing
under its row lock, after TASK and operation locks. Sum actual charge rows rather
than adding a second mutable counter that could drift. Explicit required limits
cover the source allocation, with optional task/project/producer caps. No
production defaults are selected. Declared size reserves exactly that bounded
amount; otherwise reserve the operation raw limit. EOF must match a declaration.
Sealing converts to actual raw bytes and releases only unused allowance. Failure,
lease expiry and registration do not release physical charges. Reclamation will
require the subsequent exact cleanup implementation; it is not exposed here.

Allowed files are the existing intake models/repository, a cohesive ART capacity
owner and typed limits in the intake API, migration0069, their targeted tests,
canonical reset/ownership catalogues and this current record. This stage adds no
provider writes, route or AUTH authority. Proof must cover simultaneous spending,
rollback, same-content distinct operations, declared-size equality, sealed-byte
conversion and failed/expired charge retention on real PostgreSQL.

## Streaming provider stage

Extend `interfaces/artifacts.py`, the existing S3-compatible and local adapters,
ART intake values/receipt persistence and their existing focused suites. Keep
composition through the current ArtifactStore factory. Submission keys remain
operation-derived; generic committed SHA-object consumers keep their protections.
Explicit upload bounds and deadline accompany typed handles and ordered part
receipts. Commit the handle before parts and EOF/completion intent before external
completion. Provider calls never hold database locks. Receipt values alone grant
no authorization. No public cutover occurs before root orchestration is complete.

Verification covers bounded backpressure, lost begin/complete acknowledgement,
conditional completion, exact-version read/delete, scoped handle reconciliation,
and retained charge until confirmed cleanup. Use real pinned MinIO for protocol
claims; do not treat existing AWS activation as qualification of new capabilities.
Update the architecture guard's obsolete blanket multipart ban with exact scoped
capability restrictions, preserving copy/ACL/bulk-delete prohibitions. This stage
has the same L0 risk and reviewer routing as the full change.

The receiver holds at most two configured parts plus one 1 MiB ingress chunk,
separate from SDK/TLS overhead. It awaits each part before reading further and
enforces explicit idle and immutable aggregate upload deadlines. Part size is an
explicit 5–16 MiB supported input, with one in flight; neither part size nor idle
timeout has a deployment default. Provider source methods bind the claimed
namespace and operation key, require versioning, complete with `IfNoneMatch`,
and verify raw bytes when resolving uncertain completion. Lost initiation can
be enumerated only at the already-owned key. Abort acknowledgement never releases
a charge. Existing AWS activation remains insufficient for this new surface.

The methods are hidden prerequisites. Durable handle/completion persistence is
implemented, together with local source methods. Root orchestration and exact cleanup authority/
reclamation and AWS qualification remain required before public use.

## Acceptance criteria

Durable receipt integration extends the existing intake models/repository,
migration 0069, registry/reset/identifier catalogues and custody suite. One
operation-owned row records immutable part/deadline bounds before initiation,
then its opaque handle before parts, then ordered bounded completion receipts
with EOF. Fenced owner methods flush only; root transactions commit each external
I/O boundary. SQL closure must prohibit EOF without matching receipts, malformed
part sequences and mutation/deletion of recorded custody. Test rollback, stale
owners, mismatched handles/locations and direct-SQL substitutions on PostgreSQL.
This does not authorize late foreground callbacks, cleanup charge release or PRE.

- [x] Exact metadata round-trip and identity changes for each command selector.
- [x] Packet metadata validation preserves empty-text warning semantics.
- [x] Source keys derive only from UUIDv7; no arbitrary path/URL selection.
- [x] Namespace, generation, bytes and fence remain distinct identity inputs.
- [x] Unknown fields, mutation and coercive values fail closed.
- [ ] Focused tests, lint, boundary/docs checks and scoped frozen-candidate reviews.

- [x] Task/operation commit and rollback, real parent substitution, retained-key
  uniqueness, TASK-lock concurrency, EOF/seal immutability and stale-owner proof.
- [x] Retained-submission migration and model/schema parity proof.
- [ ] Complete D01–D18, I01–I12 and T1–T5 behavior with executed A01–A35 evidence.
- [ ] Single API/CLI/MCP cutover, durable recovery and cleanup, existing downstream
  policy branches and full-suite/end-to-end verification.

- [x] Physical source reservations enforce every enabled scope, retain failed and
  expired obligations, reject declared-length mismatch and count equal-content
  sources separately; concurrent tasks cannot spend the same remaining bytes.

## Risk and review routing

- Risk class: L0
- Required reviewers: architecture, security, QA/test_delta, documentation, CI integrity
- Human review focus: authorization, immutable lineage, custody, quota/cleanup,
  atomic handoff, recovery, client truthfulness and complete end-to-end proof.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline | Fetch main and inspect open PRs | Reconciled 94334ccf4 | Recheck before publication |
| Contracts and CI selection | `pytest -q tests/artifacts/test_submission_intake_contracts.py tests/test_ci_lane_catalogue.py`; ruff | 118 tests passed; lint passed | No database/storage/runtime proof |
| Documentation guard regression | `python -m unittest scripts.test_lightweight_agent_gates scripts.test_stale_review_contracts -q` | 35 tests passed | Narrow storage examples only |
| Module boundaries | `python -m scripts.module_boundaries validate --protected-base origin/main` | Passed | Existing private-import debt unchanged |
| Foreground custody and retained-data upgrade | `pytest tests/artifacts/test_submission_intake_custody.py 'tests/test_alembic.py::test_preceding_head_upgrades_to_current_without_recreation[0068_issuer_profile_email]' tests/test_alembic.py::test_repeated_upgrade_head_preserves_current_database tests/tasks/submission_dispatch/test_migration.py -q` through the isolated PostgreSQL 16 runner | 21 passed; isolated database and role cleanup confirmed | Pre-handoff persistence only; no provider, PRE, acceptance or public-route proof |
| Physical source accounting | `pytest tests/artifacts/test_submission_intake_custody.py -q` through isolated PostgreSQL 16 | 34 passed on the capacity-stage working tree; cleanup confirmed | No provider bytes written or cleanup/reclamation claim |
| Capacity-stage static ownership | UUID inventory, behavior partition, semantic lane catalogue and module boundary tests | 254 passed; ruff passed | Final integrated suite still required |
| Bounded receive | Contract/stream tests including provider backpressure, byte bounds, idle expiry and in-flight cancellation | 70 passed; ruff passed | Transport/server buffers and real provider proof remain separate |
| Durable provider receipts | Real PostgreSQL custody suite at `7c23981f7`; immutable handles/parts, direct-SQL malformed receipts, rollback and stale-owner checks | 37 passed; isolated database/role cleanup confirmed; 61 identifier/boundary checks passed | Root foreground orchestration and live provider integration remain required |
| Protected target partition | `pytest tests/test_behavior_ownership.py -q` | 170 passed | Exact added paths only; no relaxed selection |
| Model registration | UUID inventory and protected module-boundary tests | Both passed | No new cross-owner private imports |

## Review findings

- S3-QUAL-001: QA found the deliberate AWS source qualification denial lacked
  a negative regression. The existing offline AWS activation suite now constructs
  a real AWS-profile adapter with an allowed SHA-object activation and a provider
  I/O tripwire. An in-memory removal of the source gate fails that test at the
  tripwire. The documentation next-stage line now names durable receipt
  orchestration explicitly. Neither change asserts AWS source qualification.

- The retained store conformance vector still allowed only the former four
  generic methods. Invoking that vector against the new S3 store reproduced its
  surface mismatch without provider I/O. Its closed assertion now includes the
  seven explicit source operations for both local and S3 stores.
  No unrelated public methods or removed capability aliases are allowed.

- Hosted CI exposed stale migration test assumptions after adding 0069: the
  explicit revision graph omitted 0068, the exact 0062 table list included new
  intake tables, and current TASK reads lacked a null-only active-operation
  projection while seeding historical schemas. Update only those test fixtures;
  keep captured archives and historical schema fingerprints unchanged, and
  require the temporary projection to remain null before removing it. Align the
  intake model's UUIDv7 constraint text with the existing canonical guard without
  changing its SQL semantics or weakening the identifier assertion.
  Register the namespace and operation-owned shared keys in the identifier
  schema test's closed natural-key list. The historical payment cleanup proof
  explicitly expects the new TASK pointer to stay null. The shared scale-data
  fixture validates deferred foreign keys before restoring user triggers;
  foreign keys remain enabled throughout, and no performance budget is changed.

- Custody review found nullable predecessor/revision selector types and UUID
  shape unchecked in the SQL insert guard. A direct-SQL regression recomputed
  the digest and installed the matching task pointer; it reproduced acceptance
  of a numeric predecessor before the repair. The guard now requires canonical
  UUID strings for both non-null selectors, matching stored typed commands.

- Hosted CI exposed an unregistered contract file in the protected behavior
  partition. The exact target is now registered; unrelated additions and removal
  of retained targets remain rejected. The 170-test ownership suite passed.

- Architecture/security found a synthetic UUID namespace fixture incompatible
  with ART's natural singleton ID, and missing fingerprint binding. The value
  now uses `primary` and its fingerprint; an actual adapter-derived namespace
  regression replaces the unsupported assumption. No namespace schema changed.
- Documentation found a mechanically altered implementation path. Restored the
  exact path and scoped the vocabulary exception to that literal token only.
- CI review found the new wording regression unselected. Moved it into existing
  selected suites. Registered backend contracts in the semantic lane catalogue;
  updated only that lane's expected member count/fingerprint.

## Reconciliation

- Current-source reconciliation: rebased onto 94334ccf4 (PR #707); preserved issuer
  profile roadmap changes and schema head 0068. Submission owner contracts unchanged.
- Next implementation stage: shared foreground authorization/heartbeat and exact cleanup
  custody in the same PR, followed by PRE, handoff/finalization and clients.
- Remaining risks: A01–A35 integration and C01–C07 qualification.


Hosted storage CI passed all 121 selected tests but exposed incomplete runner
cleanup after enabling versioning. The runner must abort remaining multipart
uploads and delete exact versions and delete markers in its freshly claimed test
bucket, reject per-object deletion errors, and prove bucket removal. The S3 suite
must use the runner-provided bucket when supplied. Earlier standalone 47-pass
runs exercised the real provider but their cleanup metadata covered a different
empty bucket; they do not prove cleanup of the test objects. This repair changes
only test-infrastructure disposal, never product cleanup authority or charge
release. Re-run the real suite and cleanup regression before crediting this proof.

## Local source stage

Extend the existing local ArtifactStore with the seven source methods through a
private helper in the same adapter package. Preserve the existing namespace
fingerprint, factory and SHA-object layout. Create each operation ZIP directly
at its final key and retain that inode through sealing; never copy or rename raw
ZIP bytes. Use exact operation locks, no-follow private descriptors, bounded
metadata publication and cancellation-resistant off-loop I/O. A completed source
survives late abort; receiving abort retains a tombstone and bytes for separate
cleanup authority. No charge reclamation or public cutover is included.

Allowed changes: local adapter and cohesive helper, existing local/conformance
suites, exact behavior partition registration and affected current documentation.
Required proof covers bounded parts and exact read/hash, inode substitution,
namespace/handle substitution, late writes and abort, interrupted metadata/seal,
startup during a live writer, and cancellation without a surviving writable fd.
Architecture/security plan review passed with low risks after requiring abort
under the operation lock to preserve any completed source. Runtime evidence is
still required. Risk/reviewer routing remains the initiative's existing L0 scope.


Local source implementation evidence: 67 local/conformance cases passed on the
restored working tree, covering exact inode preservation, restarted reads,
completed-source protection on late abort, rejected inode substitution,
cancellation draining before abort, interrupted sealing, namespace/handle and
receipt substitutions, lost-initiation discovery and symlink rejection. The
170-test protected ownership suite passed after registering the new helper;
existing targets and the protected base remain unchanged. These results cover
provider primitives, not the absent public orchestration or physical reclamation.
Metadata publication uses a private temporary file, fsync and rename under the
operation lock; raw ZIP bytes are never renamed or copied. Every caller uses the
same operation lock, and existing metadata is rejected before publication.
New directories are fsynced through their parents before begin acknowledgement.

LOCAL-SOURCE-01: architecture/security fault injection found a child directory
descriptor leak when parent fsync failed before cleanup registration. The focused
regression reproduced the open descriptor on that failure. Register the child
immediately after opening it, before any failing fsync; the failure path must
close it before releasing the operation lock.

## Foreground upload composition stage

Connect an already committed T1 operation to the existing provider and bounded
receiver through one private ART orchestrator. Inject the existing async session
factory, a factory for the public TASK custody port, and ArtifactStore. Commit
intent before begin, handle before parts, and EOF/completion before external
completion. No provider call may retain SQL row locks. Bind the returned source
to original namespace/location, raw digest/count and upload fence before sealing
under the live database owner fence. Compute explicit PRE deadline/initial lease
from database time; no default profile values are introduced.

A single exact observation may resolve unavailable completion acknowledgement
within the immutable upload deadline. Never retry complete blindly, adopt a
precondition conflict, continue on cancellation, or start background PRE. Errors
retain operation/physical ownership for the shared foreground lifecycle and
cleanup owner. This stage does not replace that lifecycle's heartbeat, authorize
T1, expose a route, accept work or release a charge. Long-upload readiness remains
unproven until the common lifecycle heartbeat is connected.

Allowed files: one cohesive private intake foreground uploader, existing custody
suite and fixture, exact protected partition registration, and affected capability
records. Keep repositories flush-only and module edges through public ports.
Risk remains L0; architecture/security plan and implementation review plus QA
proof review are required. Real PostgreSQL plus real local storage must prove
cross-transaction visibility and NOWAIT row locks at provider calls, rollback
before any initiation, lost begin/complete acknowledgement, cancellation and
false source identity rejection. Provider generation truth comes from qualified
adapter complete/observe/read behavior; comparing a returned generation with its
own newly persisted copy is not independent physical-version verification.

Hosted local-stage CI exposed a type-only concrete adapter import in the private
filesystem helper and two unclassified UUID generation sites. Remove the
unnecessary concrete adapter type dependency; the helper still receives the
existing adapter's private filesystem operations and creates no adapter/factory.
Use cryptographic opaque tokens for provider upload handles and temporary names,
which are not Workstream surrogate record IDs. Existing composition and UUID
inventory guards reproduced both failures and remain unchanged.

Private upload composition at `e83ee8642` passed 10 real PostgreSQL/local-store
cases with database/role cleanup confirmed and 390 static/local checks. Independent
provider-call transactions proved committed receipts and NOWAIT acquisition of
TASK, operation and capacity locks. A removed raw-SHA binding check made its
negative test fail. Scoped architecture/security and QA/test-delta/CI reviews
passed; none establish the still-missing public foreground lifecycle.
DOC-UPLOAD-01 corrected summary wording to distinguish intent before begin,
handle before parts and EOF before completion; receipts do not all precede
every provider call.

## Shared foreground lease stage

Add one private runner for the same foreground command across upload and PRE.
Renew the existing operation lease from database time in short TASK-first owner
transactions, bounded by the persisted phase deadline. Renewal must never shorten
a live lease, including a longer PRE lease installed by sealing: use the greater
of current expiry and the deadline-capped database-now plus duration. Replace the unused
absolute-expiry heartbeat input with a positive duration; preserve its stale-owner
proof. Explicit heartbeat interval must be positive and shorter than lease duration.
No defaults, new lease identity, generation takeover, background continuation,
acceptance, automatic terminalization or charge release are allowed.

The runner renews before invoking the callback, then runs one renewal task beside
that callback, passing the pinned operation/lease/generation tuple to its factory.
Subtract whole-transaction monotonic elapsed time from the database remaining
lease measured after flush; reject an exhausted post-commit budget before invoking
work. Sleep at most half the remaining budget and at most the explicit interval.
A renewal failure cancels and drains callback work; caller
cancellation cancels both children before draining them together with
`gather(..., return_exceptions=True)` under the existing cancellation-preserving
helper. Repeated cancellation must not return while provider writes remain live.
A completed callback's
already-known result takes precedence if it finishes alongside a renewal failure.
The full lifecycle must return only committed owner results and resolve uncertain
handoff before choosing an API response; this helper does not infer rollback.

Allowed files: intake lease runner/repository, existing custody and contract suites,
exact protected partition registration and affected current records. L0 review
routes remain architecture/security and QA/test-delta/CI. Prove real delayed local
upload success beyond the initial lease, unchanged owner identity/generation,
immutable phase deadline caps, non-shortening PRE renewal, exhausted commit budget,
stale/terminal/wrong-lease/wrong-generation startup without callback invocation,
fencing during blocked foreground work, and cancellation without surviving child
work. Shared caller authorization, PRE and public handoff remain separate work.

Human review focus: same-owner custody across upload/PRE, cancellation drainage,
and expiry authority without authorization or acceptance claims.

The private runner now implements the pinned-owner duration renewal and shared
cancellation drainage. Ten real PostgreSQL/local cases passed at `fc52a1b42`,
with isolated database/role cleanup, alongside 256 contract/partition and 109
boundary checks. A completed-command-priority mutation failed its intended test.
Review finding LEASE-QA-001 identified missing runner proof across the phase
transition; the delayed-upload case now holds the same callback in PRE beyond
its initial PRE lease and independently observes unchanged owner and renewed
expiry. This is private custody proof, not executed PRE or public T1–T4 proof.
