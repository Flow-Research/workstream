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

## Implementation snapshot

The current completion checklist and next blocking integration live in
[OVERVIEW.md](OVERVIEW.md). This record retains chronological implementation and
verification evidence; older entries are not the current work queue. Evidence
belongs to its stated commit/worktree and provider, not automatically to later
heads. The full specification remains unfinished.

## Original behavior being replaced

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

## Intake authorization stage

T1 cannot reuse the old prepared-generation or formal Submission authority:
reservation precedes both. Extend the existing AUTH prepared service with exact
`submission.intake.reserve` (existing `submission.create` permission), and its
contributor read family with `task.submission_operation.read` (existing
`submission.read_own` permission). Keep retained audit vocabulary. This stage
supplies the real transaction-bound authority consumed by the forthcoming ART
T1 composition; it does not expose a route or claim that reservation is wired.

The reservation resource pins operation, task, assignment, current actor/link,
idempotency key, immutable command metadata and locked context digests, and
eligible task status. Prepared handles remain exact, single-use and bound to the
same root transaction; AUTH checks the live human identity and exact-project
Submitter grant without administrator bypass. TASK/ART remain responsible for
loading and locking canonical facts. The operation ID is never a Submission ID.
Own-operation reads use the current actor/link/grant and recorded project,
independent of current task eligibility. A later login does not replace original
operation identity-link provenance. ART must narrow by actor and key/operation
before invoking read authority; the read grant alone cannot select another owner.

Allowed files: AUTH public intake contract and adapter, typed domain resources,
existing prepared/project-submitter and contributor-read dispatch, action catalogue
and definitions, audit vocabulary migration/model-derived schema fingerprint,
focused AUTH tests and exact partition registration, affected current records.
No role/permission expansion, acceptance/finalization authority, data rewrite,
provider work, production defaults, route exposure or relaxed guard is allowed.
Risk L0; architecture/security, QA/test-delta/CI and affected docs review required.
Human review focus: exact operation binding, current authority and historical
replay separation. Plan review precedes implementation.

Verify real PostgreSQL prepared consume/rollback and exact audit evidence;
reject foreign actor, service/admin-only actor, revoked grant/link and substituted
operation/task/key/metadata/context. Reject repeated or cross-transaction handles.
Prove own-operation read under current grant after task eligibility changes and
under its current active identity link; deny revoked/foreign links and wrong-project grants. Preserve all
existing TASK prepared and contributor-read tests. Extend the closed catalogue
and audit migration together and verify migrated schema equality. Full T1
currentness/cardinality/readiness, actor-key concurrency, body discard replay and
public concealment proof remain the next composition work, not this AUTH proof.

Reservation extends the existing project-submitter evaluator with its own exact
resource and prepared binding; TASK claim/manager/read guards stay unchanged.

Canonical identity currently permits one link per actor (database uniqueness).
A renewed login uses that stable link; this stage does not invent a second active
link or weaken identity custody to exercise a hypothetical replay configuration.

Migration 0070 adds only the two action/permission pairs and exact operation audit
target to the existing closed constraints. A real before/after schema manifest
comparison confirmed that only those two audit constraints change. Initial real
AUTH negatives exposed missing prepared-denial registration: rejected actors
raised an unsupported-denial error instead of canonical evidence. Register the
exact new action/resource pair and compare the denial binding; the fixed-service
matrix then passed. Live own-operation reads consume resolved historical facts
without an eligible-status input. ART must still prove stored-operation replay
after task progression and denied-body nonconsumption in T1 composition.

AUTH-only review found no grant bypass. ARCH-AUTH-01 corrects the new read action's
catalogue owner to this initiative while preserving its contributor evaluator.
The CI review found the new PostgreSQL test module absent from the explicit
semantic lane catalogue; register it with the existing task-authority modules.
The focused migration comparison is replayed at the repaired commit so its
receipt identifies the same reviewed source. These are necessary verification
and metadata corrections, not expanded authority or public exposure.

## T1 admission and exact replay composition

Connect the private foreground path to real AUTH/TASK/PROJECT owners. Add a
strict selector-only reservation preflight under the existing intake action;
it checks current human/Submitter authority without issuing a handle or staging
an allow. Full prepare/consume continues to require exact locked context/status.
TASK's existing lock returns the stored project ID. Preserve the actual AUTH
lock sequence: TASK, actor/link, exact grant, canonical TASK context/PROJECT
policy, new operation, capacity. No body or provider call occurs in these short
root transactions. Old preparation and accepted execution retain their contracts.

The ART admission composition generates the operation UUID before preflight and
passes it into the existing repository reservation. It validates current task,
assignment, predecessor/revision acknowledgement and capacity, exactly one locked
PRE and POST selection, and the configured claimed storage namespace/profile.
Unqualified AWS source capability fails closed before reservation. Explicit
positive raw/deadline/lease/capacity limits have no deployment defaults. The full
PRE runtime/readiness and public rate/framing gates remain cutover dependencies;
this private composition cannot expose a public accepted response.

Resolve actor/key first. An existing operation uses its stored task/project and
current own-operation read authority before metadata comparison or ordinary new
submission eligibility. Active/no-EOF and terminal/no-EOF never consume a retry
body. Complete EOF identity permits bounded hash/count into a discard sink,
including unresolved provider completion; no new object or PRE is created.
Reauthorize and reread the same operation after hashing. Metadata or raw mismatch
is conflict; an exact replay returns the operation's own current state/failure,
not another task submission or a takeover. Cancellation cannot mutate the original.
Share ingress framing/count/hash enforcement with upload rather than duplicate it.

Recheck actor/key after serialization. A raced-in key or exact uniqueness loser
rolls back its root transaction, then resolves the committed original under read
authority. Do not lock another task while holding the requested task. If commit
acknowledgement is lost, never infer rollback or begin upload from an in-memory
row: resolve in a fresh authorized read or leave an unknown infrastructure result.
Caller cancellation drains transaction cleanup and remains cancellation; it cannot
start upload. Retained uncertain custody stays charged for later recovery.

Allowed files: intake AUTH public/domain/adapter preflight and existing prepared
service; TASK custody API/owner and canonical revision acknowledgement helper;
ART intake repository/streaming/admission and existing preparation helper caller;
exact partition and semantic CI test registration, focused custody/contract/AUTH
tests, affected current records. No accepted state, source deletion/release,
background PRE, new provider/config parser, fabricated readiness, public route or
production default. Risk L0; architecture/security, QA/test-delta/CI and affected
docs reviews. Human review focus: fresh authority before disclosure, same-key
concurrency/commit uncertainty, exact context and bounded replay without writes.

Prove real PostgreSQL/local admission with canonical AUTH grants; denied/revoked
and foreign callers leave no operation/pointer/charge/allow or provider work.
Prove metadata/raw conflicts, EOF-unsealed replay, terminal replay after TASK
advances, concurrent same/different keys and cross-task key reuse, capacity
rollback, wrong namespace/unqualified AWS, revision/cardinality refusal, lost
commit acknowledgement and cancelled retry. Existing upload/lease/custody and
old preparation authority proof must remain intact. Integrated accepted replay
and public API concealment remain required after T4 and route cutover.

T1 component evidence (implementation worktree based on `00aab633d`, not a
frozen candidate): selector-only AUTH preflight now checks the current Submitter
grant without an allow or prepared handle. Full reservation preparation still
requires locked context/status. The shared bounded ingress reader supports
provider-free discard hashing, including exact EOF, size/framing refusal,
idle/total deadlines and cancellation propagation. TASK owns the shared revision
acknowledgement validation used by existing preparation and future T1 admission.

Verification: 518 focused intake-contract/prepared-authority tests passed;
17 isolated PostgreSQL intake-authority tests passed (47.92s, migration head
0070, database/role cleanup confirmed); 14 existing selected-PRE tests passed,
including revision acknowledgement checks. Ruff and whitespace checks passed.
The PostgreSQL runner was initially invoked from the repository root and failed
migration import before tests; rerunning from backend corrected that invocation.
Local evidence: `/tmp/workstream-t1-preflight-static.log` and
`/tmp/workstream-t1-preflight-pg.log` with matching metadata JSON. These results
prove components only: ART admission/replay transaction composition, races,
commit-acknowledgement uncertainty and integrated T1 acceptance remain unproven.

T1 composition now exists privately in `foreground_admission.py`. It owns short
root transactions, TASK/actor/grant/context ordering, capacity reservation and
full reservation authorization. Only acknowledged commit yields a foreground
owner. Existing/raced keys and uncertain commit acknowledgements use a fresh
current-authority read; replay hashes outside the transaction and reauthorizes
before returning the same operation. Commit cancellation drains cleanup and
preserves cancellation without issuing upload ownership.

Initial composition evidence on the implementation worktree: six PostgreSQL
cases passed (73.30s) for atomic custody/allow, EOF-unsealed replay, same-key race,
lost acknowledgement, revocation and namespace refusal. Three further cases
passed (33.85s) for conflicting retries, capacity rollback and repeated commit
cancellation. Both isolated databases and roles were cleaned up. Protected owner
registration and module boundaries passed 207 tests. The initial older policy
fixture had no project checker selections and correctly failed T1 cardinality;
the positive fixture now registers and selects one image in each phase through
canonical policy setup. This is not yet frozen T1 review evidence or public API
acceptance proof; remaining planned refusal/race/advanced-context cases and
full custody regression must be assessed before declaring this stage complete.

Hosted verification of pushed `2cdf10ee4` exposed structural-debt mismatch and
an omitted exact active-action inventory assertion (Backend run 43170021484;
shared-foundations-c otherwise reported 2093 passing tests). Repair remains in
this T1 worktree: extract cohesive prepared preflight handling, keep exact intake
audit selectors in their own target helper, split admission integration tests
from custody tests and explicitly register the new module/protected paths, and
include both intake actions in the existing active-action inventory. Structural
limits and the frozen debt ledger remain unchanged. New admission test family
membership is checked against the previous fingerprint with only that exact
module added. Fetched `origin/main` remains `94334ccf4`, already an ancestor.

The focused CI repair checks passed 709 tests in 60.80s, covering prepared
AUTH, exact active-action inventory, lane membership, behavior ownership and
structural-boundary contracts (`/tmp/workstream-t1-ci-repair.log`). Ruff and
whitespace checks passed. The full custody regression was launched before the
cohesive file split; its eventual result must be distinguished from verification
of the final split modules and extracted preflight helper.

Additional T1 evidence: the full pre-split custody regression passed 65 tests in
551.27s with isolated cleanup confirmed. The final split admission/AUTH suites
passed 30 tests in 213.09s, including missing phase-selection refusal, cross-task
same-key serialization and cancelled discard replay. Two additional PostgreSQL
cases passed in 34.74s: canonical configured AWS namespace refusal before source
reservation, and current grant revocation during replay body hashing. All three
isolated database/role cleanups completed. The AWS case proves refusal only,
not AWS provider qualification. Direct AUTH and test-structure CLI validators
passed without changing their ledgers. The terminal EOF replay case retains the
original failure even after another operation claims the same task. Integrated
accepted replay, revision journey, public framing/runtime readiness, and the
full T1–T5 public drill remain later required evidence; these tests do not prove
the public submission cutover.

Frozen candidate `dfdcfa181` subsequently passed all 15 admission cases against
that exact commit in 173.76s, with isolated cleanup confirmed. Documentation
review passed its scoped claims. Architecture/security and QA independently
found a concrete deadline escape: a non-yielding async body reader can return
bytes or EOF after an `asyncio.timeout` deadline without running the cancellation
callback. The shared upload reader and final provider-part response had the same
boundary risk. Repair checks elapsed idle time after each read, including EOF,
and absolute time before/after read boundaries and before upload completion;
cooperative timeout cancellation remains. Nine new regressions all fail against
the frozen pre-fix implementation in memory; all 105 intake contract tests pass
with the repair. No test skips or deadline relaxation were introduced.

Remaining hosted failures were traced to concrete current-consumer omissions:
Alembic's supported-head constant still named 0069 after installing 0070, the
independent linear-graph assertion omitted 0069, and the MCP authorization-context
snapshot lacked the two new ActionId values. Repair scope includes Alembic env
and its existing graph/resume tests, plus that exact generated MCP snapshot and
its canonical digest. It preserves the allowed historical revisions and refusal
of unknown revisions, and changes no MCP tool or product route. Targeted repeated
upgrade/downgrade/historical-resume checks and real OpenAPI comparison gate
publication/readiness. Source may be frozen for conditional review while a long
integration run finishes; a live run is not passing evidence.

The selected MCP contract checks now pass all 144 tests against actual backend
OpenAPI (58.94s). The snapshot delta is exactly the two intake action values,
canonical digest and capture source revision; no tool behavior changed. The
migration repair run remains separate from this contract evidence.

The full backend Ruff check passed. The existing app docstring check initially
fell just below its unchanged threshold after the new admission class; documenting
its constructor, transaction ownership, reservation validation and authorized-read
contracts restores the check (80.1%). This is documentation of the actual owner
boundaries, with no behavior or threshold change.


The historical migration repair run completed: 35 passed, 33 deselected in
1524.15s; migration head 0070 and database/role cleanup were confirmed. The
receipt records HEAD `dfdcfa181` because it ran the repair worktree before freeze;
architecture/security inspected the narrow code delta on clean `3e9157ce` and
ran the exact-head migration graph check. Its independent total/idle deadline
probes now reject the formerly accepted late reads. Documentation review found
and corrected the earlier freeze/publication sequencing sentence. Upload deadline
regressions now use an explicit forbidden-write assertion instead of relying on
a missing provider method; replay and late-part regressions retain their direct
late-success assertions. No full public API or T1–T5 readiness is inferred.

## One-session PRE: owner trace and implementation boundary

Inspection at `0051687fc` confirms that the existing submission PRE cannot be
used unchanged after source sealing. `submission_materialization.py` consumes
an API-prepared archive and exports the trusted guest's verified tree;
`SelectedPreSubmitProcessor.process` then starts a separate execution for each
locked PRE entry. The trusted worker requires `export` before `default`, and
selected-PRE reservation requires a semantic manifest and default-input digest
before runtime invocation. These are the precise call paths to replace for the
single-source execution, rather than wrap as an ostensibly single call.

The next implementation boundary must cover source-bound CHECKERS custody,
ART's exact-generation read authorization, the typed `execute_pre` invocation,
guest inspection/default/project composition and validation of combined evidence.
It must not stop at a type-only adapter with the two-guest implementation behind
it. Core requests carry locked facts and the sealed source without an extracted
manifest; runtime derives the manifest and nested project request, and CHECKERS
independently reconstructs that request from locked facts and observed manifest.
Expiring delivery authority stays separate from the immutable request digest.

Reuse the existing canonical archive inspector, semantic-manifest construction,
four default checks, registered external request/result validation, foreground
lease and runtime guardian/capacity ownership. Retain shared POST consumers while
replacing submission PRE callers. An unsafe archive may complete defaults with
no manifest or project run; raw source mismatch is an infrastructure failure.
Neither project output nor matching echoed digests establish platform evidence.

Runtime feasibility is a specific design dependency: `Machine::prepare` boots
one cache image and injects the static guest bootstrap before the image command.
The existing trusted defaults require Python and Workstream code from the pinned
intake image; project images need not contain either. The existing image-archive
validator verifies layer identities and bounds but does not materialize a second
root filesystem. Therefore neither a second mounted image nor a safe layer
extractor may be assumed to exist. Architecture/security review must resolve
independent trusted-platform provisioning inside that one guest before runtime
implementation. Loading trusted Python from the project image is forbidden.

Allowed impact cone for the resulting L0 plan: CHECKERS selected-PRE public
contracts/coordination and validation; ART source grants and submission
materialization; typed execution interface and concrete adapter; checker service,
static guest, trusted intake worker and image-cache provisioning; necessary
custody migration, explicit ownership/lane registrations and focused tests;
affected operational documentation. No acceptance/finalization shortcut,
second PRE guest, host verified-tree export, project network/model/trial
privileges, retained-data deletion, provider qualification claim or deployment
default is authorized by this boundary. T4 and public cutover remain subsequent
integration work in the same PR.

Required proof includes one invocation and one guest on pass; no project launch
on default rejection; hostile project output, filesystem/process/control-channel
access and resource exhaustion; substituted source/image/fence/derived request;
unchanged canonical default/manifest semantics; cancellation and uncertain create
with retained cleanup/capacity obligations; and a managed-style adapter fixture
without host paths. Native guest isolation needs actual qualified runtime proof,
not just collection of its fixtures. This checkout currently has neither a Smol
executable on PATH nor `/dev/kvm`; portable proof can proceed, but cannot establish
native runtime qualification. Human review focuses on platform-code provenance,
the supervisor/project boundary and durable evidence binding before T4.

### Trusted platform provisioning and guest ingestion plan

The architecture review selected project-image boot with an independently pinned
trusted Python root as the smaller viable change. Provision the root offline,
before runtime admission, using the already approved intake image graph. The
provisioning Docker daemon is trusted build infrastructure, never a PRE runtime
or a source of submission bytes. Validate the local Docker-save graph through
the existing cache provisioner, require the exact config image ID already loaded
in the daemon, and verify its platform and rootfs diff IDs. Create an isolated
container with pulling disabled; never start it or invoke its entrypoint. Export
its root filesystem through bounded storage, then remove only that invocation's
container. Before export, inspect the returned container ID and require its exact
image ID and never-started created state. Use that ID for cleanup; uncertain
creation retains a unique invocation label/name for discovery and exact-owner
cleanup. Reuse the existing bounded subprocess runner with a binary stdout sink,
preserving aggregate output/time limits and process-group termination rather
than exporting to an unbounded Docker output path.
Docker's documented create/export operations support this without
executing the image. Reject image-declared volumes for this trusted profile.

Produce a closed, length-framed root bundle rather than asking the guest to
interpret OCI layers or arbitrary tar extensions. Normalize a bounded export
into directories, regular files and symlinks; resolve hard links to regular file
content without host extraction. Reject duplicate paths, traversal, special
files, link-parent ancestry, invalid link targets and excessive bytes/entries.
Directories precede files; symlinks are installed last. File permissions are
read-only, preserving only executable intent; set-ID bits, ownership, devices,
xattrs and host identities confer no authority. A canonical descriptor binds
the bundle digest/count, platform manifest, config, default behavior and bounds.
Outputs are exclusive, sealed and fsynced; failure removes only owned partial
files. No implicit image pull, image registration or policy change occurs.

The static guest receives the bundle into a private bounded guest spool and
verifies its complete digest/count before writing into its fresh private root,
then validates the closed framing and bounds during staging. Charge both the
bundle spool and expanded root against guest disk capacity and clean both on
cancellation or failure. Recheck the consumed digest while staging so a changed
spool cannot authorize execution. It
must never follow a link while writing. Absolute symlink targets are meaningful
only inside the eventual chroot, never during host/guest unpack. The trusted
worker uses that root's interpreter/libraries and a separate protected workspace;
project execution remains disabled until the combined-purpose supervisor exists.
The bundle is a necessary executable dependency for that supervisor, not proof
that the one-session PRE path is complete.

Allowed first implementation files: the existing cache provisioner and a cohesive
trusted-root provisioning module, its existing test family, guest bundle reader
and focused tests, exact test registration if needed, this record and runtime
documentation. Risk L0; architecture/security plan and implementation review,
QA/test-delta review and affected documentation review. Prove source-image
substitution refusal, no-start/no-pull behavior, bounded export and cleanup,
hardlink/symlink/path attacks, truncation/digest/bounds refusal and a valid Python
root round trip. Native mount/chroot isolation remains a subsequent guest
integration gate. No backend public cutover, second PRE guest, deployment default
or provider qualification is included in this provisioning step.

The provisioning implementation now reuses the existing verified image graph
and bounded subprocess runner. `checker_trusted_root.py` exports only the
inspected never-started container, resolves uncertain create acknowledgement by
unique label/name and rechecks ownership before removal. It writes a sealed
`WSROOT1` bundle and separate descriptor; completed verified cache files may
remain after bundle failure. Parsing and hardlink expansion have explicit byte,
entry and deadline checks. No host extraction or image execution occurs.

The guest `trusted_root` library verifies the bounded spool, enforces exact
platform/config/default identities, rejects invalid path ancestry and record
ordering, installs links last, and hashes consumed bytes again before returning.
It creates only a fresh root and removes partial staging on cancellation or
failure. Its caller must own a protected parent, charge spool plus expanded root,
and mount the result read-only. The combined PRE supervisor is not wired yet.

Initial focused checks passed 75 Python tests and 170 ownership tests, plus nine
guest-library tests including source mutation after first verification. The real
pinned intake image built locally. Its first export hit the subprocess helper's
unrelated default 120-second timeout despite an explicit 600-second provisioning
budget; owned-container cleanup succeeded. Export now uses the remaining
aggregate deadline. Real-image export/staging and final verification remain
publication gates. A newer local Clippy reports existing workspace warnings;
the required runtime gate uses CI's pinned Rust 1.84.0 and unchanged test command.
No native Smol qualification follows from portable guest-library execution.

The first review wave found three actionable gaps: escaping relative symlink
targets were accepted, inspected container IDs were not compared with the exact
selector, and initial directory permission setup sat outside the cleanup guard.
Repairs reject lexical root escape in producer and guest, compare exact returned
IDs for create and recovery, and guard every post-create staging action. Cleanup
restores writable owned directories after late failures; filesystem cleanup
failure remains an error and cannot release capacity. The guest now verifies a
supervisor-owned private parent, opens it without following its final symlink,
and anchors writes through its held descriptor across ancestor renames.

The repair checks passed 80 Python and 12 guest tests. Running the updated Python
regressions against the frozen pre-repair producer produced exactly three
failures for the two escaping links and wrong container ID, with 12 controls
passing. Export tests also assert the explicit remaining timeout reaches the
runner. The prior pinned Rust 1.84.0 serial workspace gate completed 213 tests;
the repaired candidate needs its final gate before publication.

Real-image provisioning produced a 460,208,808-byte bundle describing
457,060,353 expanded bytes and 24,549 entries; the repaired Rust reader staged
that whole bundle successfully. The temporary container was removed. These are
local image/bundle composition facts, not a PRE invocation or native isolation
qualification. Exact repaired producer replay and staged-interpreter execution
remain separate final proof checks.

### Live image-content mismatch and corrected provisioning boundary

The repaired candidate's Rust 1.84.0 serial gate passed 216 tests. Its real
producer completed and cleaned its container, but comparison with the earlier
bundle disproved the assumption that daemon image metadata proves exported
filesystem contents. Both bundles have the same pinned config, platform,
default identity, byte/entry counts and valid self-digests. They differ only in
`urllib3/connectionpool.py` and its uv-cache hardlink: four bytes at offset 45088
changed from `try:` to `00 90 01 00`. The later file is not valid UTF-8.

Independent reads from the verified canonical image archive retain the correct
file digest `6a147869216b94449a053e869d4311cba23294551c83ee20fe5d2f1eaff50a3e`.
Two fresh never-started containers copied directly through Docker reproduce
the different digest `9b1a4e8c373fa4abc73c1b9e68cd39c7a6f8cb2ef2a558b4e7363d8f2f0e466e`
while reporting the same image config ID. Reviewer mutations were in-memory
only. This establishes a mismatch in the daemon's materialized image contents;
it does not establish its cause. The producer must not be published as qualified
or used for execution on this evidence. Runtime staging correctly authenticates
the bundle it is given, but cannot repair incorrect provenance upstream.

Replace the daemon-export dependency with direct construction from the existing
verified canonical image archive. Preserve the bundle format and guest reader.
Build a bounded in-memory final-path inventory from the exact ordered layers,
with bounded private file-content spooling instead of host path extraction.
Use the OCI 1.1.1 layer changeset rules: process whiteouts against lower-layer
entries before same-layer additions, distinguish opaque directory removal,
merge directories, and replace other paths. Resolve regular hardlinks against
known file identities; reject unsupported entry types, ambiguous link ancestry,
duplicates, cycles and root escapes rather than assuming generic image support.
Preserve executable intent and the existing read-only normalization deliberately.
Bind every output file's size/hash to its source layer and the closed approved
graph; verify retained input identity through completion. The trusted platform
profile must accept the actual pinned intake image before this change qualifies.

Allowed correction scope: the existing cache graph helper, trusted-root producer
and one cohesive layer-inventory helper if needed, its existing tests and exact
ownership registration, runtime documentation and this record. Remove the
superseded Docker create/export path, flags, sink-only helper changes and tests
once no required consumer remains. No second provisioner, fallback to daemon
contents, changed guest format, source-image repair/deletion, runtime cutover or
qualification shortcut. This remains L0 with architecture/security plan and
implementation review plus QA/test-delta and docs review.

Acceptance: faithful layered replacement/whiteout/hardlink behavior, bounded
aggregate data/entries/deadline, no host extraction, wrong layer/config refusal,
deterministic complete root construction, and publication cleanup. The live
counterexample must yield the canonical archive's correct file bytes without
consulting the divergent daemon filesystem; two builds from identical approved
bytes must agree. Then repeat guest staging and trusted-interpreter checks and
retain the unchanged four-default behavior identity. This correction is a
prerequisite for the same one-session supervisor, not a separate completion goal.

Architecture/security approved this corrected direction with explicit parser
requirements: whiteout markers must be empty regular entries with valid nonempty
targets, with exact handling for `.wh..wh..opq`; complete layer streams must match
their approved compressed digests and config diff IDs, and retained file bytes
must be rehashed during spool/output. Reuse the existing graph/member index.
Read-only inventory of the actual ten-layer intake image found only directories,
regular files, symlinks and hardlinks, with no duplicate layer paths, whiteouts,
or writes through nondirectory ancestors. That makes the restricted profile
concrete; synthetic whiteout/replacement regressions are still required.

Direct verified-layer construction now replaces Docker export completely.
`checker_root_layers.py` reuses the canonical graph/member index, verifies each
consumed layer and its temporary spool, and constructs only an in-memory path
inventory plus bounded content bytes. Lower-layer whiteouts precede same-layer
additions; directory merges, replacements and immutable regular hardlink content
are explicit. Unsupported links, special/sparse files, duplicate paths and
invalid/nonempty whiteouts fail closed. Complete tar trailers are required.
The graph helper now accepts explicit byte/deadline bounds for this caller, so
its preliminary decompression cannot bypass the provisioning limit.

The producer rehashes retained file bytes, checks the serialized bundle against
an independently accumulated write digest, and revalidates its retained cache
through completion before publishing the descriptor. The Docker flag/export
budget was replaced by the explicit layer byte bound. The now-unused subprocess
sink extension and its tests were removed; original image-publisher process
behavior remains. Docker ownership tests were replaced by layer semantics,
determinism and a real prohibition on subprocess materialization, while unsafe
path/link and publication cleanup proof remain.

Focused verification passed 254 tests (84 image/cache/root tests and 170 ownership
tests), plus Ruff, Commitrail and Markdown links. Two independent constructions
of the actual pinned ten-layer intake image produced the same bundle digest,
`sha256:273ca6b9ffa7abed0dd5252d86e35fe0a218d09624cb9921cdbec734ebe049cb`:
460,208,569 serialized bytes, 457,060,471 expanded bytes and 24,543 entries.
The unchanged Rust reader staged the complete root; its urllib3 file matches
the canonical archive's correct hash rather than the daemon's altered bytes.
This validates the corrected content source, not native PRE isolation. The
existing single-request integration, combined supervisor and native runtime
qualification remain outstanding.

The next review identified two pre-parser bounds gaps. The outer archive scan
could read an arbitrarily long zero trailer before reaching guarded graph work,
and `tarfile` consumed PAX headers before the logical entry counter. The root
command now requires `maximum_archive_bytes` for both original and prepared
archives; preflight, member reads, cache copy and hashing share the deadline.
Raw layer preflight charges every physical header before parsing and accepts only
one local PAX path/linkpath envelope, at most 16 KiB, followed by a supported
entry. Other attributes, global/stacked/dangling envelopes and oversized payloads
are refused before `tarfile` interpretation. The real pinned image contains
579 such local headers, only path/linkpath keys, with a largest payload of
281 bytes, so this is an exercised restricted profile rather than an assumed one.

The repaired checks passed 264 tests. Updated extension regressions against
pre-repair `982417ab3` failed all eight unsafe/count cases while retaining the
ordinary-layer control. Disabling outer bounds made both outer-archive
regressions fail. A real repaired construction completed in 86.10 seconds and
retained the same canonical bundle digest and counts; no daemon materialization
or deployment configuration default was added. The unchanged guest reader and
in-chroot Python successfully load the canonical urllib3, archive inspector and
the existing default behavior identity from that root.

## Next bounded change: source-bound single-session PRE

Risk: L0 (untrusted archive/project code, process isolation, immutable execution
identity). This change connects the verified platform root to the execution
path. It is not complete when only new types or a standalone worker pass tests.
Its reviewable outcome is one typed `execute_pre` call that streams one sealed
source into one guest, runs canonical defaults there, conditionally runs the
selected project there, and returns independently verifiable combined evidence.
The public submission cutover and accepted transaction remain later work in this
same PR; no intermediate implementation is a merge milestone.

### Inspected constraints and replacement decisions

- `SelectedPreSubmitReservationFacts` and its database row currently require
  prepared generation, manifest and default-input digests before execution.
  They cannot represent T3's source-first reservation. Evolve this existing
  CHECKERS owner and row; never substitute an operation UUID into a prepared
  generation field or create a second PRE job owner.
- Python external identity/material contracts and the Rust SDK both require
  prepared generation today. Replace that PRE custody with operation/run/source
  identity together with affected builders, validators and fixtures. POST's
  submission/binding identity remains distinct. Retained historical row values
  remain data; they are not authority for new source-bound invocations.
- `IntakeWorker` currently requires inspect -> host export -> default. Replace
  its PRE sequence with guest-local inspect -> derive -> default. Trace and
  preserve POST's currently shared inspection/export consumer until its own
  retained-source replacement; do not add an alternative PRE export path.
- ART's `_projected_tree` closes its sealed in-memory content at context exit;
  the projected directory is separate from that content snapshot. Keep the
  trusted projection lifetime through project execution and let the supervisor
  own workspace teardown. Do not infer byte identity from directory existence.
- The current guest mounts the project image as root and has one hard-coded
  workload cgroup. A combined purpose must stage the approved platform bundle
  in a private supervisor directory, chroot the platform worker into it, and
  keep project execution in the approved project root. Separate mount namespaces,
  users, cgroups and descriptors are mandatory. The project must not see the
  platform root, raw archive, staging directories or trusted control endpoints.

### Allowed files and owners

- Existing CHECKERS `api/selected_pre_submit.py`, `api/external.py`,
  `selected_pre_submit*` implementation, `models.py`, corresponding migration
  and exact owner tests: source-first reservation and independent result binding.
- `backend/app/interfaces/external_checker_execution.py`, existing checker
  adapters/factory composition, and ART's public source/read grant boundary:
  one typed source-based PRE call and separately supplied expiring delivery.
- `external_checkers/intake/worker.py`, the existing guest `lib.rs`, `main.rs`
  and cohesive PRE helper, service `smol.rs`, `smol/intake.rs`, transport and
  SDK: combined guest purpose, streaming, protected worker/project sequencing.
- Canonical ART manifest/archive and CHECKERS default APIs only where an
  owner-public entry point or shared derivation is required; reuse their
  semantics, do not copy inspection/default algorithms into Rust.
- Existing affected tests, new focused PRE tests, exact behavior ownership and
  lane registrations, SDK fixtures, this record and affected current docs.

Prohibited: host/API whole-ZIP spool or verified-tree export for PRE; another
PRE VM/runner; project-selected platform code; manufactured manifests, default
input or prepared-generation IDs; changed default behavior; acceptance before
T4; deletion of retained evidence; POST semantic changes; capabilities/network
expansion; fabricated runtime limits or provider qualification.

### Execution and authority sequence

1. Reserve existing CHECKERS run under TASK/operation/fence custody after T2.
   Persist immutable source descriptor, locked task/packet/rules/predecessor,
   exact approved image/config/default/profile and explicit budgets. Manifest
   and default-input evidence are absent until observed, not placeholder hashes.
2. Record discoverable runtime invocation/cleanup obligation before create;
   use existing guardian/capacity ownership. Deliver exact authorized source
   with bounded reads over the existing transport, outside database locks.
   The platform bundle and guest spool/expanded workspace remain explicitly
   charged. No caller path is part of the provider-neutral request.
3. In the guest, stage the trusted root with the verified reader, validate raw
   SHA/count, inspect/extract and derive canonical manifest/default input from
   locked facts. Run the unchanged four defaults. A source mismatch is an
   infrastructure failure; unsafe ZIP can be a default rejection with no
   manifest. Blocking defaults produce project `not_run`.
4. On default pass, supervisor permits exactly the registered project command
   with verified input read-only and a separately bounded writable workspace.
   The nested request is derived in trusted code after inspection. Project
   output is bounded data on separate pipes, never a trusted response frame.
   Close inherited control/source/root descriptors before project exec; forbid
   mount/ptrace/signal access to the supervisor and keep it outside workload OOM.
5. CHECKERS validates the manifest and reconstructs expected nested request and
   default-input digests from its persisted locked facts. Matching echoed
   digests alone cannot establish eligibility. Validate every operation/run,
   source generation, image/config/default/profile and fence before persistence.
   Capture evidence independently of cleanup; uncertain destruction retains its
   obligation and charged capacity, not a fabricated checker failure.

### Acceptance, verification and review focus

Future implementation tests must exercise the connected call, not only parsing:
valid ZIP -> four defaults -> exactly one selected project invocation; malformed
ZIP and secret/unchanged rejection -> no project invocation; source SHA/count
mismatch -> infrastructure failure; swapped image/config/run/fence or manifest
-> rejection; forged project stdout -> cannot supply trusted facts; deadline,
EOF, output excess, cancellation and uncertain create/destroy -> bounded terminal
behavior with retained cleanup custody. Revision/current-predecessor checks and
warning-only packet omissions preserve canonical behavior.

Use existing real PostgreSQL harness for T3 reservation/replay/fence/rollback and
migration parity, existing Rust workspace checks under pinned 1.84.0, and real
Python canonical inspector/default fixtures for derived evidence. Include a
portable guest composition drill with the actual approved root, plus a mutation
that bypasses defaults and a mutation that trusts echoed request digests; both
must fail meaningful assertions. Namespace/cgroup/Smol isolation needs native
qualification and cannot be established by mocks or the portable drill. This
host currently has neither Smol nor `/dev/kvm`; retain that explicit evidence gap
and do not enable unqualified production execution as a fallback.

Architecture/security review the plan and frozen implementation, specifically
source-first ownership, SDK replacement and supervisor privilege separation.
QA/test-delta review assertion reachability and discriminating mutations.
Documentation review reconciles exposure and qualification claims. Lead owns
shared checks, exact CI handles and the same PR; human review focus is the
source-to-result authority chain and confinement evidence, not test counts.

### Plan review corrections: exact cutover and confinement boundaries

Architecture/security and QA/test-delta inspected `03a09b353` and found the
single-session direction feasible with the following required corrections.
These are part of the allowed implementation and acceptance scope above:

- Explicitly include ART `submission_admission.py`,
  `selected_pre_submit_execution.py`, `submission_materialization.py`,
  `selected_pre_submit_admission.py`, `submission_custody.py`, affected
  trusted-intake contracts, AUTH selected-PRE facts, and
  `backend/app/adapters/tasks/__init__.py` plus TASK's intake public port.
  Replace the current composition in place; no second transaction owner.
- Introduce an explicit stored request schema discriminator. Historical
  prepared-source rows keep their original fields and canonical JSON/digests
  unchanged and remain readable. New source-bound rows require operation/source
  identity and forbid a prepared-generation value. Before inspection their
  manifest/default-input columns are NULL; after inspection those are immutable
  result evidence. SQL and typed decoders enforce mutually exclusive historical
  and new shapes. Historical decoding is read-only evidence interpretation,
  never another executable PRE path. The migration does not rewrite old hashes
  or delete rows. Completed unsafe-archive rejection permits absent derived
  fields but forbids eligibility/project evidence.
- Replace `SelectedPreSubmitAdmissionCapability` and its ART consumer together.
  New source-bound completion cannot mint or satisfy the old
  `SubmissionBundlePreparedCustody` capability requiring `PreparedArtifact`.
  Until T4 is installed, retain the source-bound terminal as CHECKERS evidence
  only; it cannot authorize old create/admission consumption. The old live
  prepare/reserve producer is removed with its affected callers in the same
  coordinated replacement, not kept as an execution compatibility option.
- Extend the existing TASK-first guard: lock TASK intake custody, verify its
  active operation, then check ART's exact operation/source generation and
  current foreground lease/fence in that root before CHECKERS run locks.
  Reserve, claim and finalize must all enforce the relevant current custody.
  A valid task/assignment/lineage alone is insufficient. Keep source ownership
  in ART and task pointer ownership in TASK through public ports.
- CHECKERS reconstruction consumes bounded guest-observed canonical inspection
  entries tied to the exact raw source plus persisted locked task/project facts.
  Recompute manifest/default-input/nested-request canonical bodies and digests;
  neither locked facts alone nor a mutually consistent pair of returned hashes
  proves the inspected input.
- Stage the trusted root/raw input under a supervisor-owned private directory
  hidden by the project child's mount namespace (not an unmasked `/work`
  directory). Before exec close inherited bundle, archive, directory and trusted
  control descriptors; retain only explicitly allowed project stdin/stdout/stderr.
  Separate fixed trusted/project UIDs and cgroups are part of the qualified
  profile, not project image choices. Drop privileges and apply the existing
  workload syscall filter after mounting. The supervisor remains outside both
  killable workload groups. Namespace hiding must also prevent `/proc`/inherited
  descriptor access to the trusted root and control process.

The connected fixture must begin with a real sealed operation/generation and
NULL derived fields, then drive the existing coordinator/ART composition into
one typed PRE call. Count session creation and conditional project launch.
Add negative controls for foreign/cleared TASK active operation, stale foreground
fence, substituted provider generation, and attempted old-capability consumption
of a new source-bound terminal. Existing prepared-file/mock-execution fixtures
cannot establish these claims. Retain their still-required semantic assertions
while replacing their obsolete preparation setup. Lead plan checks passed
Commitrail, Markdown links and diff whitespace; the review is feasibility
inspection, not runtime or migration proof.

The first implementation step separates `WorkstreamDefaultContext` (locked
predecessor/rules/packet facts available before inspection) from the derived
`WorkstreamDefaultCheckerInput`. Both use one context validator. ART's existing
builder now binds its inspected source/manifest through that context; the trusted
worker independently derives its input from its own raw receipt and projected
entries and compares the supplied input before evaluation. The canonical input
body and four-default behavior identity are unchanged. Eighty focused default,
predecessor, trusted-worker and selected-PRE tests pass, including late binding
and digest sensitivity to locked facts and observed input. This is an internal
step in the reviewed replacement: the worker still has its old command sequence,
and source-first reservation, combined guest and T4 are not implemented yet.

Scoped architecture/security passed the default-context step at `517370267`.
QA's in-memory stale-binding mutation failed the new digest-sensitivity test.
Both tracks independently rejected forged executable metadata with a recomputed
supplied input/binding digest before the worker evaluator; that case is now a
permanent worker regression. The ownership partition regenerated identically,
and 229 ownership/lane-catalogue checks passed. These checks do not qualify a
rebuilt platform image or the still-unimplemented combined guest path.
The repaired focused suite passes 81 tests. Disabling only the worker's observed
input comparison in memory makes the new regression fail at its evaluator-entry
sentinel, confirming the assertion reaches and distinguishes that boundary.

The T3 source-first reservation dependency is now an explicit ART public port:
`SubmissionIntakePreSourcePort.lock_pre_source` uses the current TASK-first
repository lock, checks the live foreground lease, requires TASK's exact active
operation, and compares every sealed-source field before returning detached
actor/task/assignment/context and deadline facts. `IntakeTaskCustody.require_active`
owns the pointer comparison. These values grant neither AUTH nor provider I/O;
they must be consumed within the same root before CHECKERS locks. Source
reconstruction is shared with sealing. Existing upload/terminal behavior is not
replaced by this port, and CHECKERS reservation wiring remains the next step.
Thirteen real PostgreSQL controls passed for valid source custody and altered
source generation/hash/count/namespace/profile, lease/fence, cleared/foreign
pointer, expiry, terminal and unsealed source. The pointer tests exercise an
uncommitted state before deferred constraints, proving the in-root check matters.

CI for `592959410` reported one shared-foundations-b failure among 2,118 tests:
`test_handler_suppressing_cancellation_cannot_ack_after_deadline` timed out waiting
two seconds for finalization after cancellation was observed. This is unresolved
failure evidence, not a passed run or grounds to relax the assertion. Exact
job 131093141927 and its lane artifact were inspected; diagnosis/reproduction
remains required. Other jobs were still running at that observation.

### Bounded CI failure diagnosis: cancellation versus database finalization

Allowed test-only repair: `backend/tests/outbox/test_recovery_postgresql.py`
and this record. The failed test waits two seconds after observing cancellation
for all of real `finalize`, which includes multiple database roots and AUTH.
`invoke` explicitly cancels without awaiting the handler, then awaits durable
finalization. The test currently conflates those separate waits. Preserve the
prompt non-wait assertion with a two-second event at entry to real finalization,
while the uncooperative handler is still blocked. Gate that finalization in the
test to make ordering explicit, then allow a bounded ten-second database
observation and retain every UNKNOWN/replay/no-ack assertion. No production
outbox code, timeouts, authority or retry policy may change. QA must verify an
implementation that awaits the uncooperative handler before finalizing still
fails, and that the original CI timeout is not called a confirmed production
root cause merely because this scheduling defect is reproducible. The original
focused test is already running unchanged in the full custody command; do not
restart it or misattribute its eventual result to the repair.

The source-custody boundary passed scoped architecture/security and QA at
`3cee7cc5f`; 371 contract/ownership/lane/architecture tests also passed, with an
unchanged ownership partition. The full PostgreSQL run at `3cee7cc5f` passed
all 69 custody cases plus the original unmodified outbox cancellation test:
70 passed in 642.52 seconds, with database cleanup confirmed. The earlier CI
timeout did not reproduce locally; this does not erase that failed CI result.

The outbox observation repair passed two focused real-PostgreSQL tests and QA
at `16704ddd6`. Mutating only `invoke` in memory to await the cancelled handler
before finalization made the repaired test fail at the two-second finalization
entry event. The mutation receipt records the exact commit and successful database
cleanup. This proves the test retains the cancellation-ordering boundary; it is
not a production outbox change or a claim that the original full CI run passed.


Source-first reservation review resolved the remaining historical-data boundary:
retain v1 JSON/digests/status verbatim, including nonterminal historical rows;
make them read-only rather than fabricating terminal outcomes or migration AUTH.
Reject new v1 writes/transitions and v1 actor/key collisions as conflicts. The
live coordinator is v2-only; old prepared-bundle producer and capability consumer
are replaced together. A frozen v1 read decoder is evidence interpretation only.

The concrete SQL transition must cover the existing 0036 insert, immutable-row,
execute/finalize audit-digest and receipt guards, not just ORM columns. Add a
nullable source operation reference with the existing `(id, task_id)` ART
composite key and uniqueness per non-null operation. The v2 insert guard also
compares project/assignment/actor/link and the full sealed descriptor under the
locked operation. Explicitly confine old ART admission guards to historical v1.
Request facts bind source, locked context/packet/predecessor, exact selected
policy/image/config/default/profile/resource limits and immutable PRE deadline;
manifest/default input become terminal evidence. Mutable heartbeat expiry is
excluded. Claims/finalization use DB time and cannot outlive ART's hard deadline.
Architecture/security found this replacement feasible; it is not implemented by
the preceding source-lock port. Fetched `origin/main` remains `94334ccf4`, already
an ancestor of this branch.

The retained v1 reader now uses a separate frozen data decoder, containing only
lineage/request/lease/result/terminal values and no coordination or capability
ports. The read projection uses that decoder, so the live source-first request
can be changed without rewriting historical canonical bytes. A fixed v1 request
and terminal vector preserves both hashes; altered request binding/timing and
row terminal digest are rejected. Historical values cannot enter the live
reservation or lease constructor, even with identical field values. The first
test used an incomplete session stub; it now opens a real unbound SQLAlchemy root
and proves rejection before TASK/DB access. All 250 focused decoder/projection,
owner and lane checks pass. This is the read side of the coordinated replacement;
new v1 write prohibition, v2 live request/SQL guards and removal of the prepared
producer remain pending and are not implied by this checkpoint.

QA found that the inherited read projection compared terminal hash/run ID but
could accept divergent row actor/archive selectors. The repaired reader decodes
the independent retained request, compares every v1 indexed identity and source/
policy/default/budget field, then checks terminal reservation, outcome, lease,
eligibility and timestamps. All thirteen new row-substitution controls fail with
the exact prior `18d3a5663` reader injected in memory and pass the repair. The
historical decoder also rejects an unknown outcome token explicitly; no valid
retained outcome is changed. Queued/running history stays readable without a
fabricated terminal state.

A second fixed vector now covers complete lineage, canonical default results
and a selected project member. It was generated once through the existing ZIP/
default pipeline with a controlled project-result adapter, not native runtime
execution or a database-origin attestation. Nested lineage/member/default
mutations are rejected. All 270 focused checks pass. The four PostgreSQL
read-consistency tests also passed with cleanup, but their fixture produced no
completed selected PRE row, so that run is not credited as historical payload
coverage. The reader's direct frozen-row tests establish that narrower claim.

### Live source-first replacement in progress

The live reservation now uses schema v2 with exact sealed source and source hash,
metadata/locked-context hashes, foreground lease ID/generation, immutable PRE
hard deadline, complete selected policy, default context and explicit runtime
profile. Prepared-generation/current-manifest/default-input facts are removed
from this request and its live lineage. The frozen v1 decoder is unchanged.
Runtime profile values have no deployment defaults and do not assert provider
or isolation qualification. Exactly one selected PRE image is required here;
policy-approval cardinality enforcement remains part of the wider cutover.

The existing coordinator now requires ART's public source-custody port after
TASK checks and before CHECKERS locks. It compares exact source, actor/link,
project/task/assignment, metadata/context and foreground fence/deadline. Claim
expiry is capped at the existing absolute deadline. Finalization no longer
mints the old prepared-bundle capability. ORM source-operation linkage and
nullable historical derived-input columns are drafted; execute/finalize/terminal
facts use v2. A type-only import in ART's preparation feedback contract removes
an eager API import cycle exposed by the source dependency.

This is an unfinished coordinated replacement, not a passing review candidate.
The matching SQL migration/guards, source-first ART producer, old capability and
consumer removal, derived result envelope, v2 read projection, SDK/runtime and
remaining affected fixtures still require implementation. Do not push or treat
this checkpoint as deployable. The last pushed branch remains unchanged.

Twenty-four focused source-first tests pass, including source substitution,
forbidden derived/mutable fields, packet/deadline binding, ten current ART
custody substitutions refused before CHECKERS queries, claim deadline capping,
lease overrun and exact-one policy. These use controlled owner ports, not real
PostgreSQL migration or native execution. The full coordination module exposed
eight transition failures: seven obsolete live fixtures/capability expectations
and the historical rejection test's newly required source port. The historical
test now supplies that port and asserts neither owner is called. Remaining
failures must be replaced alongside the corresponding live callers, not hidden
by narrowing CI. Scoped Ruff and diff whitespace checks passed. Freshly fetched
main remains an ancestor of the branch. Remote CI for the prior pushed commit
was still running when polled; no green outcome is inferred.

The source-first SQL transition now adds migration 0071: nullable historical
columns, unique source-operation/composite TASK linkage, TASK/ART source checks,
exact approved PRE and POST policy comparisons, closed v2 request keys and
versioned execute/finalize audit digests. Existing revision-expiry/exhaustion
lineage logic is retained by exact guarded function replacements. Historical v1
run updates are refused and old prepared-bundle admission joins are v1-only.
No retained row is rewritten or terminalized. The TASK adapter now supplies the
existing context port required by `IntakeTaskCustody`; its missing constructor
argument was found while tracing the real composition path.

Fresh PostgreSQL migration succeeded. Schema setup correctly refused the old
fingerprint; the new fingerprint was measured from the migrated database as
`dead223f93cd881dc9710b44c91a146bbba890073c857b88ff11b137a778460b`.
The first source-guard fixture had an approved policy with no selected PRE image
and failed at the new exact-one constructor, before SQL. The test now requests
one registered image through the genuine approval fixture; production cardinality
was not relaxed. Its positive control passes the composed ART source port and
inserts a queued v2 row through the real SQL insert and deferred receipt guards.
Two separate PostgreSQL tests prove Python/SQL execute/finalize digest agreement
for both the frozen v1 vector and a v2 request. Database cleanup was confirmed.
The full eight source substitution/control cases plus those two digest tests are
running for the frozen SQL candidate; pending results are not a pass.

This remains part of the unfinished live replacement: production source-first
producer/callers, result envelope, v2 read dispatch, old capability removal and
native one-session runtime remain outstanding. Full retained-row upgrade and
new receipt lifecycle proof are still needed; the frozen-vector digest checks
are narrower evidence. The full earlier pushed Backend run at `d8677d2f8` has
now completed successfully; it does not qualify these local changes. Scoped
Ruff/whitespace checks pass and the protected ownership partition is unchanged.

Scoped architecture/security and QA held `d8de93372`: terminal updates could
rebind committed lease/execute receipt fields; separate default predecessor
facts lacked authoritative comparison; terminal outer JSON lacked row/hash
binding; and Alembic's accepted starting-revision list omitted 0071. QA also
required recomputed-hash forgeries and negative INSERT coverage. The 10 prior
PostgreSQL tests passed with cleanup, but their receipt records base `a99d05036`
and dirty-tree code later committed as `d8de93372`; credit them as compatible
scope proof, not exact-head execution.

The repair freezes committed claim fields, binds closed terminal outer facts and
canonical digest to row identity/timing/outcome, and derives the entire default
context from locked TASK policy identities, approved policy hash, original packet
and exact consumed predecessor admission. The predecessor lookup uses existing
Submission TASK/assignment ownership plus ART admission project/source/rules
custody. Live latency arithmetic now uses integer milliseconds to agree exactly
with SQL; frozen historical serialization is unchanged. Alembic accepts both
0070 upgrades and already-current 0071. Tests recompute source/packet/request
hashes, send negative INSERTs, and use real fixed-service AUTH claim/finalize with
attempted claim/terminal substitutions. The existing repeat-upgrade test is reused.

Forty-nine source-first/historical contract tests pass. The repaired migration
applies with measured schema fingerprint
`d12af28660d6d712d4c97828a39831c34e7c7bf2aec96efe0ba104cee1512b2a`.
The repaired PostgreSQL lifecycle/negative/repeat-upgrade command will run after
this candidate is committed, so its receipt can identify the actual head.
Required re-review and full live caller/result/read/runtime cutover remain open.

The repaired exact-head PostgreSQL run at `2910cdef5` completed with 13 passes,
one failure and cleanup confirmed. Source/packet/rules/predecessor substitutions,
versioned digest comparison and repeat migration passed. The positive lifecycle
case stopped before claim because its fixture lacked the fixed PRE service actor
(`ACTOR_NOT_FOUND`); no terminal-guard claim is credited from that run. Both
review tracks confirmed the prior code findings repaired but held proof pending
this fixture correction. The positive case now provisions only
`CHECKER_PRE_SUBMIT` through the existing real service-principal fixture helper,
without altering production authorization or resetting an existing principal.

The corrected positive PostgreSQL lifecycle case passed at exact clean
`15f3cd372`, with cleanup confirmed. It provisions the fixed principal, claims
through real AUTH/coordinator composition, rejects ten committed-claim/terminal
substitutions and commits one valid infrastructure finalization. The 13 source,
digest and repeat-upgrade passes remain attributed to `2910cdef5`; production
code did not change between those heads. Both architecture/security and
QA/test-delta/CI passed the bounded SQL custody stage at `15f3cd372` with that
provenance distinction. Forty-nine contract tests, 229 ownership/lane checks,
Commitrail and changed Markdown links passed; the protected partition is unchanged.
These checks do not establish completed-result eligibility, a real revision
predecessor upgrade, the retained-row migration round trip or the public source
submission journey. The next implementation remains the live source-first
producer/result path and removal of its prepared-bundle consumers, followed by
the single-session runtime and the rest of the original end-to-end objective.

The live ART reservation producer is now source-first: it accepts locked ART
source facts and original metadata, compares TASK/PROJECT references and exact
approved policy/rules/packet, and produces v2 without current manifest,
prepared-generation or derived default-input facts. Its default-context binder
uses only locked policy and retained predecessor facts; it no longer inspects
or binds a current archive/change gate. The source-first PostgreSQL control now
commits sealing before opening the TASK/PROJECT/ART binding root and calls this
production builder instead of constructing a reservation from test row fields.
The initial positive source/SQL/real-AUTH lifecycle run passed with cleanup on
the dirty tree based at `7dd8ca6f5`; exact-head evidence is pending. Added builder
substitution probes cover metadata, actor/source custody, rules and packet.

This is not the completed producer-to-runtime cutover. The old public preparation
caller still passes the removed inputs, and its prepared-bundle capability and
consumer chain still require coordinated removal when source execution/T4 replace
them. The old attempt-request hash helper is still referenced only by that chain
and its obsolete tests; it is not a second v2 request identity. No new route,
compatibility adapter, placeholder manifest or executable authority was added.
The existing reviewed L0 single-session plan and file/reviewer scope still apply.

The production-builder PostgreSQL run passed 13 cases at exact `61871924d`,
with cleanup confirmed, and 49 source-first/historical contract checks passed.
QA passed that bounded producer/proof scope. Architecture/security found one
remaining provenance gap: separately supplied lineage storage scheme could
contradict the sealed source profile. The builder now derives the scheme from
the same currently admitted `local-v2`/`minio-v1` profiles as T1 and refuses other
profiles; AWS qualification is not inferred. SQL source custody independently
requires the same profile/scheme relationship. A raw INSERT substitution changes
only the scheme and recomputes the request digest, preserving all source facts.
The repaired migration applies with measured fingerprint
`3b71e6b86dea2b6b525fc1fdc3a130b83c070e74e826ef65f4cf6976d1e58d01`.
Exact-head repaired proof and focused re-review are pending. The broader caller,
capability, completed result and one-session runtime replacement remains open.

The `63d025b19` native run was red: twelve source cases reached a syntax error
in the new PL/pgSQL IF expression; two audit-digest cases passed. Migration
installation alone did not compile the exercised body. A minimal real-PostgreSQL
DO block reproduced the unparenthesized CASE/THEN parsing failure and passed
with the CASE parenthesized. The guard now uses that correction, without changing
its policy. A structurally revalidated `aws-s3-v1` source descriptor is also
submitted to the producer's explicit unsupported-profile refusal in the positive
fixture; this is data-validation proof, never AWS provider qualification.
The corrected fresh migration fingerprint is
`41e1b52d8d9807e8ca3c1d1975b73f1e338a519ab5b73ee40bfe1e086eb2700d`.
Native re-execution and renewed scoped reviews remain required before recording
the scheme fix as proven.

The corrected exact-head PostgreSQL run passed all 14 cases at `2798f370b`,
with database cleanup confirmed. It exercises the production source-first builder,
committed-source TASK/PROJECT/ART port sequence, metadata/source/rules/packet
substitution controls, supported-profile scheme forgery with recomputed request
hash, unsupported AWS descriptor refusal, real SQL INSERT and fixed-service AUTH
claim/finalization with terminal substitutions. Both architecture/security and
QA/test-delta/CI passed that bounded scope at the same clean head. The earlier
syntax-error run remains failed evidence, not a green migration proof. Nothing
in this result qualifies the unfinished public caller/capability/result/runtime
or accepted T4 path; those remain required by the original single-PR objective.

### Live result selection validation during execution replacement

Tracing the old executor exposed an independent result-binding gap: finalization
and terminal reconstruction compared only the echoed policy digest, while the
result could declare zero required members or substitute a self-consistently
rehashable registry/phase/requirement/image. Live execution now requires exactly
one selected project check, verifies returned members against the reservation's
actual locked binding, and refuses a missing project result after defaults pass.
A blocking default still permits no project execution. Finalization and terminal
reconstruction share this validation; historical v1 read-only decoding is unchanged.
The existing external-result owner supplies registry schema and canonical output
size checks, reused by both request validation and selected-result validation.

Focused contracts plus source-first/historical tests passed 88 cases. Removing
both selection-validation calls caused all six substitution/omission controls to
fail, while the positive control passed; the production code was restored.
This is structural selection proof only. It neither establishes observed source
custody nor reconstructs the derived project request. The combined response,
single-session runtime, SQL deep completed-result guard, old caller replacement
and T4 remain unfinished. This local change is part of the same coordinated PR,
not a publishable or merge-ready endpoint. Scoped reviewer evidence is pending.

Architecture/security review found that direct shared-helper calls could accept
an in-memory Pydantic copy with a forged external result digest, even though
later JSON decoding would reject it. The helper now revalidates both result and
registry before selection/schema/size checks. New controls exercise rejection
before both finalization and terminal construction; the expanded focused suite
passes 90 cases. The earlier QA pass did not cover this reviewer-reproduced
integrity path. Renewed review of the repaired candidate is required.

Both renewed scoped reviews passed the clean repaired candidate `1e151a388`.
Architecture/security replayed the original forged-digest probe and observed
rejection at finalization and terminal construction. QA independently substituted
the exact pre-repair helper in memory: both new boundary controls failed as
expected, then the helper was restored. Ownership/lane checks passed 229 cases;
the ownership partition is unchanged, and record/link checks pass. These reviews
close the selection/digest findings only, not the remaining combined-execution
or accepted-handoff requirements.

### Source-bound combined-result client and nested request derivation

The CHECKERS PRE processor now invokes one typed `execute_pre` operation instead
of exporting an ART tree and dispatching a second project invocation. Its existing
factory and lazy configured adapter use the same external-service capability.
The Unix client streams an ART grant's exact source in at most 64 KiB frames,
checks count/SHA before EOF, bounds request/result framing, refuses success after
the lease/configured deadline, and closes source/transport on cancellation. The grant is a separate
process-local port; no token or host path enters immutable request identity.

Live nested Python/Rust PRE identity now binds operation, sealed-source digest,
run/request and execution lease/fence, with no prepared-generation field. Shared
wire fixtures were regenerated for this deliberate contract replacement. Live
execution evidence is v2 and retains observed source, fence, canonical manifest
and default-input digest. CHECKERS uses ART's existing canonical manifest parser
with the locked invocation limits and reconstructs default input plus the nested
project request from the reservation, then validates the returned project result
against that reconstructed request. Unsafe-archive default rejection may omit
manifest/project evidence; a passing default cannot. Historical v1 decoding and
its retained fixtures remain separate read-only data.

The focused contract/transport selection passed 120 cases, including source,
lease, manifest and mutually rehashed request/result substitutions; source-short,
source-long and wrong-hash transport; trailing frames; expired lease before source
open; one invocation only; and cancellation closing source and socket. The Rust
SDK passed eight tests including rehashed source/fence substitutions. Ownership
and lane checks passed 229 cases. The entire runtime test module was also run:
29 passed and one obsolete prepared-ZIP grant test failed because its removed
prepared-generation identity is correctly refused. That failure is retained,
not skipped or adapted into a second PRE path.

This is an intermediate local implementation in the coordinated single PR, not
a completed bounded-change or merge milestone. The actual ART source-grant issuer
and its materializer AUTH replacement, native service/guest `execute_pre` handler,
provider invocation/profile/conformance/cleanup envelope, old ART caller/tree-grant
removal, SQL deep-result guard and T4 remain required. The old ART materializer and
Rust PRE tree-grant service still refer to the superseded preparation identity;
they must be removed during the connected replacement, not made into compatibility
adapters. The current public path remains unfinished and these local commits must
not be pushed as a publishable cutover. No source grant authority, native guest
execution, provider qualification or accepted handoff is proved by a socket fake.


The first combined-client review found three defects: manifest-present default
rejection incorrectly validated an unrun project input schema; synchronous
response decoding could return success after the timeout; and upstream source
chunks had no byte ceiling before socket framing. The repair separates default
input derivation from conditional project request construction, checks monotonic
and lease deadlines after decode/validation, and requires nonempty source chunks
of at most 64 KiB before hashing or forwarding. The source-grant port declares
that ceiling for the forthcoming issuer. Synchronous bounded JSON parsing is
not physically preempted; its late result is refused.

New regression cases use a real incompatible registered input schema for both
secret and unchanged-work default rejection (the latter with matching predecessor
and current-rule facts), slow decode after successful wire receipt, and a source
chunk larger than the cap. Removing each corresponding guard made the intended
controls fail: two default-blocker cases, one late-decode case and one oversized
chunk case. Production code was restored after each probe. The expanded focused
suite passes 124 cases; renewed review of these repairs remains pending. The
broader native/ART/T4 integration and the retained old-path failure are unchanged.

Architecture/security and QA/test-delta passed the repaired client scope at clean
`e29c637ae`. The targeted mutations discriminate all three repaired defects;
late synchronous decode is refused, not physically interrupted. The full runtime
module rerun at this candidate reports 31 passed and the same one obsolete
prepared-grant identity failure. Record/link checks pass and the ownership
partition remains unchanged. The combined native execution boundary is still
unfinished; the next work is the exact ART source-read grant/AUTH issuer and the
native single-session handler, followed by removing their obsolete prepared
callers and completing SQL/T4 custody. This evidence does not authorize a push
or readiness claim for the incomplete public cutover.

The ART source-read implementation now projects exact sealed-source, foreground
and execution fences into the existing fixed-materializer AUTH action. Issuance
consumes committed CHECKERS authority, rechecks locked TASK/ART custody, commits
the independent materializer audit, and only then exposes a one-use stream.
Reads enforce the earlier foreground/execution deadline, exact byte count and
64 KiB chunk ceiling outside database transactions. The provider port accepts a
smaller explicit read cap without changing source identity.

Real PostgreSQL/local-provider integration passed authorized and denied service
cases (two tests), including independent NOWAIT TASK/ART lock probes during I/O
and visibility of the committed materializer audit. The guest is deliberately
replaced by a capacity-failure consumer in this proof; no native guest or success
handoff is claimed. Three real authorization tests passed, including revocation.
Controlled tests cover failed commit acknowledgement and changed custody.
A new abandoned-reader regression exposed that callback revocation alone left
an opened provider generator suspended. Callback exit now closes that generator
with cancellation-resistant cleanup before closing the authority adapter.
Owner/lane checks passed 229 tests. This source-read work remains pending scoped
review, and the native handler and obsolete public caller replacement remain
required before the coordinated cutover can be published.

Review of source-read candidate `951627305` passed architecture/security but QA
reproduced a concurrent-reader cleanup defect: a detached task could remain in a
provider read while callback exit attempted to close its running generator.
The repair binds grant consumption and every read resume to the issuing
foreground task. This matches the existing client's inline backpressured reads
and refuses detached consumption before provider I/O. Tests cover transferring
an already-created reader to a child task and expiry both before first read and
after the first chunk. All ten focused grant cases pass after the repair.

The earlier integration receipt used the dirty tree's base SHA. A fresh isolated
run on clean `951627305` passed five PostgreSQL/local/AUTH cases and confirmed
cleanup; it does not cover the subsequent task-binding repair. Authorization
import validation and record/link checks passed. Structural validation separately
found new oversize custody-test debt and stale spans/hashes for the shrinking
existing authorization test file. These must be repaired by cohesive test
extraction and exact ledger/assertion-map reconciliation, not a new exception.
A full native workspace baseline reached the service tests: 114 passed and five
failed on removed prepared-generation fields in old fixtures. Those failures
remain required work in the native/public cutover; no full-suite pass is claimed.

The first task-binding repair was rejected on review: although the Unix client
reads inline, its CHECKERS processor created a child task. The earlier assertion
that task binding matched the complete existing call path was incorrect. A new
issuer-plus-production-processor regression failed with `material_unavailable`
before provider access. The processor now awaits execution inline and tracks the
foreground task for abort; a cancellation test proves abort unwinds the issuer
and closes the provider. Twelve focused source-grant/composition cases pass.
A broader old selected-PRE test module still fails 13 cases on the removed
`semantic_manifest_id` prepared-lineage argument; these remain pending connected
replacement, alongside the separately recorded Rust old-fixture failures.

Architecture/security and QA/test-delta passed the repaired source-task scope at
clean `d9d635199`. The exact-head isolated PostgreSQL/local/AUTH replay passed
five cases with database and overall cleanup confirmed on migration 0071. Ten
single-PRE transport cases passed. QA's independent blocked-provider abort probe
also confirmed cancellation closes both provider and authority. This resolves
the concurrent-reader and processor-task findings; it does not resolve the
structural gate, obsolete native fixtures, public cutover or T4 requirements.

The structural-gate repair extracts the five PRE source/SQL/execution tests from
`test_submission_intake_custody.py` into `test_submission_pre_source.py`. Upload,
quota and foreground lease tests keep their original module and fixtures; the
new module imports those exact fixtures rather than creating a second setup.
Source/request substitution helpers separate setup from SQL assertions without
changing the tested cases. The assertion map preserves all 23 direct assertions
from the prior five tests at ancestor `c4949e117`; helper assertions remain on
the same exercised path. This is a test-only repair within the existing source
custody scope, with QA/test-delta review required. Acceptance requires the same
29 collected PRE cases, real PostgreSQL replay, no new structural debt, and
unchanged ownership partition. No gate limits, product behavior, schema, fixture
policy or production authorization change is permitted by this repair.

The refreshed structural ledger records only the earlier authorization test
file's shrinkage and shifted spans of otherwise unchanged functions. It adds no
oversize exception or new debt entry. The existing remaining oversized AUTH
files remain explicit debt; this repair does not claim to eliminate them.

The extracted PRE module passed all 29 real PostgreSQL cases in 259.16 seconds;
its receipt records the pre-freeze worktree base `c4949e117`, so this is compatible
working-tree proof rather than an exact frozen-head receipt. Combined collection
retains all 85 cases. AST comparison after expanding the two helper calls and
ignoring import placement confirms identical executable statements for the five
moved tests and the existing terminal-guard helper. Structural validation passed,
as did its 29 regression tests, new-module undefined/unused-name checks, and
record/link checks. The ownership partition is byte-for-byte unchanged.

QA/test-delta and CI-integrity review of `38440d466` confirmed assertion fidelity
but found the extracted module missing from the explicit shared-foundation CI
catalogue. The existing inventory test reproduced that omission. The repair
registers the module in that same family and updates its independent membership
fingerprint from 272 to 273 modules. All 229 ownership/catalogue tests pass.
Mapping the real 85-node collection through the production lane manifest builder
selects every node once; the 29 moved cases distribute across the three shared
foundation lanes as 3, 13 and 13. This proves selection, not another PostgreSQL
execution. CI review also independently confirmed a corrupted assertion-map
hash is rejected, with the original mapping as the passing control.

QA/test-delta and CI-integrity replay passed the repaired selection at clean
`83467c478`. The source tests and assertion map are unchanged from the reviewed
extraction. A fresh manifest build on that exact head also selects the same 85
collected nodes once, including all 29 moved cases; this remains selection proof,
not a second database execution. Record/link checks pass. The structural repair
is complete within its scope. Native one-session execution, obsolete prepared
callers/fixtures, SQL result custody and T4/public delivery remain unfinished.

### Native combined PRE implementation boundary

The next runtime change replaces the PRE branch of trusted intake plus exported
host tree plus separate project execution with one `execute_pre` handler on the
existing checker socket/factory. It is L0 security-sensitive work. Allowed files
are the existing Rust service/Smol lifecycle, guest/bootstrap/confinement code,
trusted Python worker/image, CHECKERS result/profile contracts and existing
adapter composition, their tests/fixtures, and affected ownership/lane/docs
records. Shared POST/trial behavior and retained evidence must remain intact.
No second PRE VM, host ZIP/tree spool, compatibility PRE grant, general egress,
new adapter factory, invented qualification or deployment resource defaults are
allowed. Architecture/security and QA/test-delta plan and implementation reviews
are required; human review should focus on trusted/project separation and
uncertain-create/destroy custody, not only completed-result shape.

The existing Smol `Machine` writes a private lease and starts its guardian before
provider creation. Extend that same custody with exact PRE operation/run/request
and execution fence, and retain unsettled capacity through its existing admission
quarantine. Boot the selected approved project image once with the independent
static Workstream bootstrap. Inject the independently pinned platform root using
the existing verified root-bundle reader, then stream the sealed source with
bounded frames directly into protected guest storage. Runtime/profile matching
must precede allocation and byte admission; all quantities remain explicit.

Inside that guest, the protected supervisor invokes the canonical Python archive
and default-checker owners from the independent platform root. The worker derives
the manifest, default input and nested project request from the locked source
reservation and inspected tree. A default blocker returns without starting project
code. Otherwise the supervisor launches exactly the selected project command in
its own user/mount/cgroup boundary with a read-only verified input view and
separate writable scratch. Trusted worker/control descriptors must not survive
into project code; project stdout/stderr cannot become trusted framing. The
supervisor remains outside the project OOM group. The existing project runner
should be refactored where needed rather than copied into a second confinement
implementation. The trusted worker validates the bounded project result and
constructs the combined evidence; CHECKERS independently validates it again.

Extend the same response to carry actual invocation identity, exact runtime/profile
and typed conformance evidence, stage timing and cleanup obligation/disposition.
Source/member results alone remain insufficient for T4. Cleanup uncertainty may
retain a captured valid result only with its independently persisted obligation;
it must not release unsettled capacity. Native handler errors and disconnects
must unwind the same lease/guardian path. Remove obsolete PRE export/grant/default
commands and their consumers as the connected replacement lands, preserving the
separate POST archive consumer rather than adding a compatibility PRE branch.

Proof must include real ZIP/default/request derivation; default rejection without
project start; wrong source/root/profile/fence refusal; bounded source/output and
aggregate deadline; cancellation during receive/default/project/cleanup; exact
pre-create lease and uncertain-destroy accounting; and adversarial project attempts
to alter input, signal the supervisor or forge control output. Shared POST/trial
regressions remain required. Portable workers/socket fakes and Rust tests prove
only their exercised contracts. This workspace currently has neither a Smol
binary nor `/dev/kvm`, and hosted backend CI only collects native qualification
fixtures; actual one-guest isolation qualification remains a required distinct
execution prerequisite, not an inferred pass from portable tests.

The native plan review required the following concrete decisions before code:

- PRE does not use `Resources::from(ValidatedRequest)` and its fixed 1 GiB disk.
  Resolve the pinned root descriptor and qualified PRE envelope first. Checked
  peak disk admission sums root bundle spool + expanded platform root + exact raw
  ZIP + maximum expanded submission tree + explicit project scratch + image
  overlay + filesystem overhead. Reject arithmetic overflow or a total above
  the locked temporary-disk budget. Round provider storage and overlay separately
  to GiB and charge their full rounded amounts to node admission before create.
  Root, ZIP, tree, scratch, inode/entry and control-buffer caps are enforced at
  their writers. Scratch/overlay/overhead bounds are explicit qualified values,
  never inferred from the old 1 GiB path or supplied as new deployment defaults.
- The existing persisted `Lease.name` is the discoverable invocation and cleanup
  obligation identity. Its pre-create record additionally binds PRE operation,
  run, request, source, profile and execution fence. A captured valid result may
  return with cleanup `pending` only if that exact durable obligation remains
  verified and the existing guardian/reaper owns it; node admission stays
  quarantined. Confirmed destruction yields `destroyed`. Missing or rebound
  obligation custody fails closed. PRE uses one create attempt, not the generic
  project path's three-attempt loop. Shared POST/trial semantics are unchanged.
- One supervisor stays outside both child roots and both workload OOM groups.
  First run a trusted child chrooted into the verified platform root, with only
  the exact read-only source/request and protected extraction workspace. Then,
  only after passing defaults, run the project child in its private namespace,
  cgroup and non-root identity. Refactor the existing project confinement/output
  machinery for this second phase instead of duplicating its policy. Before
  either exec, duplicate only intended stdin/stdout/stderr/control descriptors
  and close all others. Project code receives no platform worker pipe, source
  spool, platform root, supervisor control or storage credential. Explicit
  control/default/project resource partitions must fit the qualified aggregate;
  a project OOM cannot put the supervisor in the same killable group.
- The canonical projection's in-memory snapshot closes after defaults, while
  its verified files remain. The supervisor walks only the exact manifest via
  anchored no-follow descriptors, sets root-owned directories to 0555 and files
  to 0444 (0555 for executable entries), and binds that view read-only into the
  project namespace. Its private parent remains 0700 and inaccessible there.
  Test readable exact bytes alongside denied writes, chmod and rename; no host
  tree copy or export is involved. The supervisor owns final guest cleanup.
- Qualified PRE configuration points to the existing WSROOT1 producer bundle,
  its `RootDescriptor`, and explicit `RootLimits`. Match the bundle digest to
  the locked profile's platform-root digest. Transfer the bounded bundle to a
  guest-private spool and call `trusted_root::stage_root` before trusted worker
  launch, validating manifest/config/default pins and expanded size/entry limits.
  A library verifier with no caller is not evidence of this path.
- Use separate trusted control and project output frames. Project output is
  bounded by both selected registry and profile limits, logs by the profile log
  ceiling; trusted frames remain within the existing 64 MiB protocol ceiling
  and the explicit control memory budget. Refuse partial, oversized or trailing
  frames. Only the trusted supervisor/worker constructs source/default/profile
  evidence. Project output is parsed solely as its registered result.
- Before allocation/source reads, the Rust handler validates the closed header,
  canonical reservation/request/source digests, lease/fence relationships,
  selected cached image and exact configured runtime/profile/root pins. The
  authenticated local caller and backend ART grant own command/read authority;
  self-consistent hashes are not independent authorization. Negative controls
  must distinguish inconsistencies/rebound configured pins (refused before
  create) from raw-byte mismatch (provable only during actual input loading).
  Do not claim that a new internally consistent run identity can be rejected
  without an independent authority reference. Guest and CHECKERS bind all
  captured evidence back to this exact invocation.
- Add a dedicated pinned native PRE qualification case/harness; the existing
  trial qualifier is not suitable. It must observe exactly one machine name,
  persisted lease and create, worker then optional project under that guest,
  root/source/profile pins, adversarial isolation probes, and cleanup or retained
  quarantine. Portable tests instead use real ZIPs and an independent expected
  manifest/default/request vector, including secret/unchanged blockers with an
  incompatible project schema and a project-start sentinel. They reject host
  manifest/default-input/export/prepared-generation commands. Native Smol/KVM
  qualification remains unavailable locally and must not be relabeled portable
  proof. Existing shared POST/trial fixtures retain their own behavior coverage.

Architecture/security and QA plan replay passed `e47c89a48` for implementation,
not runtime qualification. The first implementation replaces the trusted worker's
PRE export/default dialogue with a closed source-reservation `execute_pre` entry.
The old prepared worker now accepts POST only and retains its archive export.
The PRE worker checks source byte count/hash, uses canonical ZIP inspection and
default evaluation, derives the manifest/default input/project request itself,
and never requests a project result after a blocker. Its private supervisor
control exchange binds the lease and request; a project result is schema-,
registry- and request-validated before combined source evidence is emitted.
Expiry is checked against both monotonic budget and the absolute lease. The
supervisor must still enforce interruption during blocking pipe reads and guest
work; these checks alone are not physical preemption.

The focused worker module passes 45 tests, including real ZIP independent
manifest/hash expectations, unsafe archives, source substitution before parsing,
host-derived input refusal, rebound project results, one-use execution and POST
export retention. Secret and unchanged-work blockers use an incompatible selected
project schema and a project-request sentinel. Removing the blocker branch made
both controls fail; the production branch was restored. Ownership/catalogue
checks passed 229 tests, the protected partition is unchanged, and undefined/
unused-name checks pass. Removed worker tests exercised the superseded PRE
export/default dialogue; their required source/default identity and no-repeat
invariants are covered by the source-derived and one-use replacements.

This is an intermediate worker candidate. The Rust native handler/supervisor,
protected tree handoff, actual runtime/profile/cleanup envelope, old ART/public
caller removal, trusted image/root rebuild and actual Smol/KVM qualification are
still required. The existing old PRE controller cannot use the now POST-only
prepared worker and must be replaced, not shimmed. No runnable public cutover or
T4/accepted result authority is claimed by these portable worker tests.

Worker review at `b3aefe559` found no code defect but required two stronger proof
atoms. The positive ZIP case now builds the default-input body independently of
the production derivation/serializer and checks its digest plus all four exact
passing default outcomes. A same-length corrupt ZIP joins the source substitutions.
The expanded module passes 46 cases. Removing only the raw SHA comparison makes
exactly the same-length case fail while the three size controls pass. Changing
the shared default-input serializer's rules digest makes the independent expected
digest assertion fail even though production producer and validator agree with
each other. Both mutations were reverted. These probes establish portable source
and default derivation checks, not runtime/profile or native isolation evidence.

Architecture/security and QA/test-delta replay passed the worker scope at clean
`7f7b5c122`. Both reviewers verified the independent default vector and the
same-length SHA negative control against the discriminating mutation logs.
Record/link checks pass. The next connected implementation is the native
single-guest supervisor/service path with the reviewed storage, FD, profile and
cleanup boundaries; the portable worker does not complete that path.

The native guest's existing project runner now returns captured child evidence
instead of writing completion and exiting the trusted supervisor itself. Its
ordinary Project entry still emits the same completion header, opaque stdout/
stderr bytes and classified exit code. This lets the combined PRE caller consume
the result in a later phase of the same guest without duplicating confinement or
starting another VM. Kernel OOM evidence remains authoritative; a project-chosen
capacity exit code still becomes infrastructure failure rather than forged OOM.

Both existing workload exec sites now mark every non-stdio descriptor
close-on-exec in the forked child before the syscall filter and exec. Intended
stdio is installed by the existing `Command::exec` setup. This closes the future
trusted-worker/control descriptor inheritance boundary for PRE while preserving
the parent's live descriptors. Unsupported close-range enforcement fails closed.
A real local fork/exec test creates a deliberately inheritable high descriptor,
proves it is absent after exec, confirms redirected stdout still works, and
checks the parent descriptor remains inheritable. Replacing the guard with a
no-op makes that test fail; production code was restored. Separate framing tests
keep project-written fake completion JSON opaque under the trusted header and
preserve OOM/output-overflow classification.

The guest crate passes 12 library and 27 binary tests; 38 shared Smol service
unit tests also pass. These are host-process/kernel and contract checks, not
native guest isolation qualification. The PRE service handler, two-child guest
orchestration, bounded root/source staging, resource/profile/cleanup envelope and
public cutover remain the connected implementation work. This supporting guest
refactor is not a new readiness or merge milestone.

Architecture/security and QA/test-delta passed this supporting guest refactor at
clean `2625b2062`. Both confirmed preserved ordinary Project framing/classification
and the real fork/exec descriptor negative control. Their verdict is limited to
captured-result continuation and child descriptor sealing; the combined PRE
orchestration and native isolation remain unproved. Record validation passes.

The same project runner now accepts explicit CPU, memory, process, scratch,
output/log and paired run/cleanup deadline bounds for the planned PRE caller.
Ordinary POST keeps its existing values and host-owned deadline. Local deadlines
refuse model/execution capabilities because those relays can block. On expiry
the supervisor issues cgroup kill and kills its unreaped owned PID, covering the
pre-membership race, then reaps before returning failure. A failed cgroup command
still kills/reaps the direct child and cannot produce successful evidence.

The guest crate passes 12 library and 29 binary tests after restoring production
code. A real fork/pause child proves termination and reaping both with an
available command sink and a missing group path; the regular-file command sink
is expressly not kernel cgroup isolation proof. Disabling the direct PID kill
makes the regression fail on unreaped custody, and fallback test cleanup reaps
the child. Formatting and whitespace checks pass. This remains within the
approved native supervisor scope and does not qualify PRE or complete its wiring.

QA review of `4aebc604a` identified that setup could exhaust the deadline after
initial validation but before fork. The launch boundary now rechecks immediately
before fork, and the child rechecks before exec after confinement setup. A real
fork control plus an expired-during-setup case exercises the launch helper;
removing its deadline check makes the latter fail and reaps the unexpected child.
Production code was restored. The guest suite passes 12 library and 30 binary
tests. Architecture/security had passed the earlier scope; both tracks must
replay this repair before a scoped review claim applies to the new candidate.

Architecture/security and QA replay passed the repaired scope at clean
`d3975f59a`. Both verified the pre-fork deadline regression and its failing
guard-removal mutation. The child-side pre-exec check is code-inspected; this
is not hard real-time preemption or native cgroup qualification. The parent
still rejects late evidence. Record validation passes. Combined PRE guest
orchestration and service dispatch remain the next connected implementation.

The PRE guest module now implements the worker-to-project phase. It validates
the closed worker frame and the shared SDK request, binds source/lease/request/
image/registry/configuration and manifest digest to bootstrap facts, then seals
the exact projected tree through anchored no-follow descriptors. It rejects
links, extra/missing entries, file-byte changes and expansion bounds; production
sealing transfers ownership to root and sets public read/execute modes under a
root-owned private parent. The mount source retains the verified directory FD.
The request is reopened read-only before being passed as project stdin.

The phase calls the existing confined project runner with the tighter selected
and profile limits, validates only its opaque stdout as a registered result, and
returns a lease-bound private response for the trusted worker. No project bytes
construct default/profile/cleanup evidence. This module is compiled but still
needs its PRE bootstrap caller: trusted-root/source staging, worker launch and
control dialogue, service dispatch and runtime result envelope remain pending.
The dead-code annotation identifies that missing connection, not completion.

Portable guest verification passes 12 library and 34 binary tests. Real local
filesystem tests cover readable exact content, readonly modes, same-length
content substitution, size changes, file/directory symlinks, hard links, extra
and missing files, missing manifest parents, ordering, bounds and deadline
refusal. Tests use the local owner for inode changes, not a simulated root
authority. This environment refuses unprivileged UID mapping and has no
passwordless privilege elevation; distinct project-UID chmod/rename denial and
actual readonly mounts remain native qualification work. Closed frame tests
include a positive shared SDK vector and rehashed foreign source requests.
Removing file hashing accepts a same-length substitution and fails its test;
removing the raw-source binding accepts a rehashed foreign request and fails its
test. Both mutations were restored. Formatting and whitespace checks pass.

Both reviews of `f8596ed77` found that the nested project input could disagree
with the bound material while retaining valid input/request hashes. The repair
compares input archive SHA/count, semantic digest and the complete directory/file
entry projection with the same locked source and frame manifest. It additionally
binds project/task/assignment/attempt, plan and selected requirement to explicit
bootstrap facts; the input identity is checked too. The portable positive vector
now includes both a directory and a file with independent expected input fields.
Rehashed foreign input and identity vectors first pass the SDK hash/shape check,
then fail the phase binding. Removing input-source, input-manifest or project-ID
comparison separately makes the corresponding vector fail its assertion. All
mutations were restored; 12 library and 34 binary tests and formatting checks
pass. These checks do not establish the selected image's JSON-schema behavior,
privileged launch or the still-missing bootstrap/service connection.

Architecture/security and QA replay passed the repaired handoff scope at clean
`abbd94ee0`, including all three discriminating binding mutations. Packet content
and other canonical default derivations still belong to the pinned worker; this
supervisor phase does not claim independent rederivation of the entire request.
The PRE bootstrap caller, early control envelope, staged trusted-root worker,
service/profile/cleanup envelope and native qualification remain necessary.
A fresh fetch confirms current main `94334ccf4` is already an ancestor; the
single draft PR remains the only PR, and this cutover has not been pushed.

The PRE guest bootstrap now calls the reviewed project handoff. A separate
`--pre-limits` entry uses closed explicit control/default/project partitions,
source/control/output/log/scratch bounds, distinct worker UID/GID and paired
deadlines. It charges the supervisor to its own cgroup before allocating the job
body, verifies the repeated limits and canonical source/request/profile binding,
and refuses resource sums outside the locked profile. All quantities remain
explicit; no qualified deployment values or compatibility PRE path are added.

The guest spools the bounded WSROOT1 bundle and invokes `stage_root`, then stages
the exact-count source and a closed transfer marker in a supervisor-private
directory. It runs the fixed trusted Python worker in the verified readonly
chroot with private source/request and extraction workspace, separate cgroup,
non-root identity, descriptor sealing and the existing syscall filter. After
defaults it permits at most one project request, calls the existing handoff/
runner, and returns only its validated result on the private worker pipe. A
default blocker invokes no project phase. Worker frames/logs, source reads,
result writes and cleanup have finite bounds; completion requires worker exit,
empty cgroup, no worker OOM and no trailing control bytes. Final VM destruction
and quarantine remain the host lease guardian's responsibility.

Connecting these scopes exposed a child-error unwinding hazard: a failed project
setup could return into the inherited supervisor worker guard. Both forked exec
paths now exit directly on setup/exec failure. A real fork regression places a
destructor sentinel outside the exec helper and proves that failed setup exits
125 without running supervisor cleanup. Ordinary POST still uses its existing
limits, framing and result classification; the PRE flag does not change trial
argument parsing.

The guest passes 12 library and 40 binary tests, and 38 shared Smol tests pass.
New portable tests exercise the Python-owner-generated `pre_startup.json`
canonical source vector (schema-tagged source hashing), closed scalar limits,
profile/source/root/identity rejection before input, exact-count spool reads,
stalled input deadlines, truncated/oversized frames, log limits, foreign fences,
default blockers and repeat-project refusal. Removing source-digest binding or
forcing a project phase after default rejection makes its focused test fail;
both mutations were restored. The fixture is synthetic and its timestamp does
not prove live lease validity. The dialogue tests use local socket peers and a
project-phase sentinel; they are not a privileged worker or VM execution test.

Formatting/whitespace checks pass. The environment still cannot run privileged
mount/cgroup/chroot or Smol/KVM qualification. Host `execute_pre` dispatch, exact
configured pins and lease admission, the invocation/profile/cleanup response
envelope, trusted-root rebuild, native qualification and public cutover remain
required. This is a connected guest code path, not a runnable end-to-end service
or accepted-submission claim.

Architecture/security passed the guest bootstrap scope at clean `7ad19cb35`,
with no concrete defect found. QA passed the exercised local bootstrap contracts
at that same candidate while explicitly retaining a separate proof gap: run a
real Python `PreSubmitWorker` with a real ZIP through the Rust supervisor socket
dialogue, checking the exact project frame and typed completion. Synthetic
frames and phase sentinels do not establish that cross-language compatibility.
Neither verdict establishes privileged chroot/cgroup/UID behavior, a one-VM
provider run, host pin/lease authority or the complete PRE service. The next
connected proof is that portable real-worker exchange, followed by the native
host dispatch and full runtime/profile/cleanup envelope.

The next proof closes the review's real-worker dialogue gap without claiming
privileged isolation. Allowed scope is guest test-only Cargo feature/test module,
a portable Python proof driver under external checker tests, the existing
checker CI job and its necessary scope selection, the matching README command,
and this record. It launches
the actual `PreSubmitWorker` on real ZIPs over Rust-owned sockets, invokes the
production Rust terminal/request validators, returns an SDK-constructed project
result, and validates the received completion with Python's typed owner contract.
Use a passing directory/file ZIP and canonical rejection cases with a project
start sentinel. Project execution is intentionally a protocol-test result, not
a substitute VM or confinement implementation.

A test-only Cargo feature separates the backend Python dependency from ordinary
Rust unit tests. The existing checker CI job must explicitly install the frozen
backend dependencies and execute the exact feature test, with no ignored failure
or empty selection. Preserve existing gates, timeout and authority. Acceptance
requires actual exchange, typed completion, a discriminating mutation and traced
CI selection/exit propagation. QA/test-delta and CI-integrity review apply; no
new runtime mode, deployment default, public route or native qualification claim
is allowed. Human review focus is actual process/protocol custody and proof
selection rather than synthetic frame counts.

The feature proof now runs the real Python worker and Rust terminal/request
validators over live sockets for passing, secret-bearing and malformed ZIPs.
The passing input includes an explicit directory and file; Rust checks their
exact projected input fields. The secret case uses an incompatible project
schema and both blockers assert zero project calls. Rust supplies a typed SDK
protocol result, and a separate Python process validates the exact received
completion through `SelectedPreSubmitExecutionFacts.validate_lease`, including
source bytes, independent expected manifest, default status and member count.
The helper's simulated reply is explicitly unused. Child guards own termination
and reaping; fixture cleanup begins only after successful directory creation.

The live proof passes, along with the ordinary 12 library/40 binary guest tests
and 47 CI-scope tests. Rebinding the Rust reply's lease generation makes the
live passing case fail after exactly one project call; production transport was
restored. An earlier negative probe used a resolved base interpreter and failed
test-helper import before startup; it is excluded from mutation evidence. The
corrected probe preserves the frozen virtualenv interpreter path.

The existing checker job now installs its frozen Python dependencies and runs
the feature proof. One shared exact Cargo selection is checked through `--list`,
then its result must report one passed and zero ignored tests. Local execution
of that workflow step passes. Executing the exact guard snippets rejects zero
or duplicate selection, missing results and ignored execution. Existing backend/
checker/workflow changes already select full scope, so no selection policy was
changed. Formatting, name checks, record and link checks pass. This closes the
live dialogue proof gap, not native isolation or host/public integration.

QA/test-delta, CI-integrity and documentation review passed this portable proof
at clean `d6387472b`. Reviewers confirmed the live Python/Rust exchange, the
corrected after-one-project-call mutation, exact CI selection/result guards and
required-status propagation. Hosted CI has not run on this unpushed cutover.
Native host `execute_pre` dispatch, independent configured pins and persisted
invocation custody, the runtime/profile/timing/cleanup response, public handoff
and actual VM qualification remain the next implementation and proof boundaries.

### Host PRE invocation journal

This implements the pre-create custody portion of the reviewed native plan:
use the existing Smol lease and startup recovery owner, persisting PRE operation,
CHECKERS run ID (the reservation attempt ID), source operation, request/source/
profile/image/configuration digests and execution fence before guardian or
provider creation. The allowed scope is the existing Smol service implementation,
its PRE module and tests, and this record. Public dispatch, response assembly,
policy decisions, source streaming and provider qualification are not claimed by
this step. Shared POST/trial creation and cleanup remain the same operations.

This is architecture/security-sensitive L1 work under the prior native plan
review. Acceptance requires one PRE create attempt, malformed binding refusal
before persistence, and pending cleanup evidence only for the exact retained
private journal captured at creation. Node admission is quarantined even when
that evidence cannot be recovered. Recovery remains owned by the existing
lease guardian/startup reaper. Human and architecture/security review should
focus on pre-create ordering, identity binding, replaced-file refusal and the
absence of any inferred native qualification. QA/test-delta review should
exercise fence/source changes, inode replacement, links and permission loss,
plus the existing shared Smol tests. The public execute_pre handler and use of
this journal in its response remain required subsequent integration.

The portable journal suite passes all 42 selected shared Smol tests, including
four PRE tests. Real filesystem probes reject changed source/fence, replacement
inode, symlink, hardlink and unsafe file/parent permissions. A failed guardian
handshake leaves one pre-bound journal; malformed input leaves none. Separate
probes prove quarantine both with retained custody and after journal loss. These
are journal/admission proofs, not successful guardian recovery or VM execution.
Formatting, diff, Commitrail and Markdown link checks pass. The new PRE entry
methods are not yet called by the public host dispatch; compiler dead-code
warnings reflect that unfinished integration rather than a runtime proof.

Architecture/security and QA/test-delta review passed clean `9292eec4e` for
this custody scope. Reviewers inspected creation ordering and the exact
filesystem counterexamples; source/fence reserialization changes both the
in-memory expected lease and the on-disk body, thereby discriminating the
captured digest check. Replacement and link cases discriminate inode and
metadata custody. No additional mutation was claimed. Invocation validation is
structural only: the host handler must still compare it to locked source,
selection and configured runtime/profile facts. Successful PRE guardian recovery,
public dispatch, provider execution and native qualification are not proved.

### Host PRE admission and configured envelope

Continue the reviewed native host plan by binding the closed PRE header to the
exact configured runtime/profile/root and selected cached image before resource
allocation or source reads. Allowed files are the existing Rust service PRE
module/configuration/tests, shared image configuration reader, guest bootstrap
limits library/caller/tests, SDK registry validator and this record. Reuse the
SDK's registry check without inventing source input or evaluating an unrun
project's input schema. Reuse one early bootstrap limits validator on host and
guest. Shared image configuration parsing must consume the exact bounded bytes
whose digest was verified. No new deployment default, authority source, provider
qualification claim, host source spool, second VM or compatibility PRE path is
permitted. Host stream dispatch and the complete runtime response remain required.

Acceptance for this architecture/security-sensitive L1 boundary is refusal of
mismatched request/source/configured pins, stale UTC deadlines, ambiguous selected
cache entries and unchecked capacity arithmetic before create; exact reservation
attempt/run identity; separate GiB rounding of storage and overlay; and bounded
bootstrap job construction with no project capabilities or fabricated input.
Tests must start from a passing control before each adverse mutation and retain
shared Smol/guest/SDK coverage. Architecture/security and QA/test-delta reviews
focus on configured-versus-self-consistent identities, refusal ordering, integer
arithmetic and the distinction between local admission proof and actual native
qualification. Structural configuration alone does not qualify a provider.

The final portable checks pass 45 selected Smol tests, 52 guest tests and eight
SDK tests. Admission's 21 adverse cases each first pass an unchanged control;
mutation requests recompute registry/policy/request digests where necessary so
internally consistent rebinding reaches the relevant configured-pin checks.
UTC tests reject calendar normalization, leap seconds, unsupported offsets and
excess precision, flooring submillisecond expiry conservatively. Shared image
checks retain digest/platform and hardlink coverage and add bounded-size,
unsafe-mode and symlink refusal. The held root descriptor checks regular-file
custody and exact byte count; full root bytes remain verified by the guest's
existing WSROOT loader. No source bytes or provider calls occur in these tests.
An initial fixture inherited group-write permissions and failed before the
intended checks; that failed run is excluded, and fixtures now set explicit
permissions and require passing controls. Formatting, diff, record and link
checks pass. Host dispatch still does not call admission or stream the source;
these checks do not establish provider qualification, authorization independent
of the trusted caller, or a complete execution response.

Architecture/security review passed clean `2f8eb812b` for admission and the shared
image reader. The broader service binary run passes 121 tests and retains the
same five obsolete prepared-PRE fixture failures as the earlier source-cutover
baseline; the full service suite is not green. The host's returned absolute
deadline must govern reservation, journal/create, streaming and reads. At actual
guest launch, the caller must shorten guest run/cleanup ceilings to the remaining
budget (and retain guardian lifetime enforcement); configured phase ceilings do
not independently establish the current lease's remaining lifetime.

QA identified that the original source mutation proved stale-digest refusal,
not the configured source-count cap. A separate boundary test now recomputes
source and request digests: the exact configured maximum passes, one byte above
it fails, and neither allocates a lease. All 46 selected Smol tests pass after
this test-only repair. Guest/SDK implementation is unchanged from the 52/eight
passing run. No production guard or test expectation was weakened.

QA/test-delta replay passed clean `95949369f`: the self-consistent source-cap
boundary test closes the reported gap. Architecture/security's `2f8eb812b`
production review remains compatible because the replay changes only that test
and this record. This establishes the portable admission boundary, not a callable
host PRE service, native provider qualification or end-to-end acceptance.

### Host PRE dispatch and bounded guest transport

Continue the approved native plan through the existing service connection owner,
Smol guardian and guest bootstrap. Allowed files are Rust service dispatch,
existing bounded command collection/Smol preparation, PRE admission fixtures and
PRE transport/tests, plus this record. Create once, retain pre-create journal
custody, charge rounded resources, permit already queued ZIP chunks during
preparation, enforce the absolute deadline and clamp both guest timer ceilings
at actual launch. Deliver root bytes and framed source chunks with bounded
buffers and simultaneous bounded stdout/stderr draining; never spool source or
export a tree on the host. Require exact counts/hashes, source terminator,
successful guest exit and one bound terminal frame. Preserve POST/trial's
existing refusal of unexpected queued bytes through the default connection
predicate. Prompt cleanup yields destroyed or independently retained pending
custody with quarantine; uncertain cleanup must never release an admitting node.

This L1 architecture/security change requires those review tracks plus
QA/test-delta. Portable socket/process tests must discriminate buffered input
from disconnect, source truncation/overflow/hash/trailing data, root mutation,
output/log bounds and deadlines, and observe child reaping. Native creation,
privileged guest isolation and real provider qualification remain separate.
The host emits a versioned invocation envelope carrying worker facts, runtime
pins, stage timing and cleanup ownership. The existing Python adapter still
expects bare worker facts: it must be changed with CHECKERS durable evidence
retention before the cutover can accept this response. Qualification/conformance
receipt validation and complete cross-provider outcome contracts also remain
required; do not label this interim envelope fully qualified or merge-ready.

Portable verification passes 51 selected Smol tests and 42 trial integration
checks. Full service binary verification passes 127 and retains the same five
obsolete prepared-PRE fixture failures; it is not a green end-to-end suite.
Real socket/process probes transfer a 128 KiB-plus source in multiple chunks and
verify received root/source hashes. Adverse cases cover changed/truncated root,
changed/short/excess source, oversized chunks, partial frames, disconnect,
stalled child, logs/output bounds, trailing/empty output and nonzero exit; owned
processes are reaped. A Python executable standing in for the runtime verifies
that host launch argv and the actual job carry identical lease-shortened limits,
that a second launch is refused, and that the first process is reaped. Its
cgroup.procs stand-in is an ordinary private file: no native cgroup or VM proof
is claimed. Worker/payload fence/source/policy probes test host binding only;
typed QC semantics remain CHECKERS' responsibility. Shared POST/trial retains
its original connection predicate. Formatting, diff, record and link checks
pass. The checker README is also updated to distinguish the now-wired host
caller from still-required backend receipt retention and native qualification.

At clean `d5a4a9ffb`, QA/test-delta and documentation review passed their scoped
transport and claim checks. Architecture/security found a concrete host-memory
accounting defect: stderr retention could grow to a configured multi-GiB log
allowance despite fixed host overhead, and continuous draining lacked an inner
deadline check. The repair counts and discards logs with an 8 KiB scratch buffer,
limits each drain pass to 64 KiB per pipe, and checks deadline/cancellation
between reads. Control output still has its explicit retained-byte bound. A
continuous-log child with a u32-maximum allowance expires and is reaped; another
child writes exactly its 4 MiB allowance and completes successfully. All 52
selected Smol tests pass after repair. The earlier 42 trial tests and 127-pass/
five-failure full service run remain compatible prior evidence, not relabeled
exact-head runs. Backend receipt retention and native qualification remain open.

Architecture/security and QA/test-delta replay passed clean `3ba1cdf64`, resolving
the log-retention and inner-deadline finding. Reviewers confirmed fixed scratch
space, checked byte counting, bounded per-pipe passes and the actual-process
controls. Documentation review of `d5a4a9ffb` remains compatible with the repair's
scope and limitations. The next required composition is Python adapter parsing
and CHECKERS/AUTH-bound durable retention of invocation/runtime/timing/cleanup
facts; returning only the worker payload would discard required ownership
 evidence. Native qualification and the public submission cutover remain open.

### Backend PRE invocation receipt retention plan

The host now returns invocation/runtime/timing/cleanup evidence, while the Python
adapter and CHECKERS currently accept only worker facts. Complete this owner
composition without discarding metadata: introduce a closed invocation receipt
and a typed result pairing that receipt with optional existing worker facts.
The worker facts type and worker protocol remain separate and cannot manufacture
host cleanup custody. Native runtime/cleanup evidence and a managed-style test
variant have distinct closed provider evidence; shared ports require no host
paths, file descriptors, local UIDs or Smol journal fields from every provider.
Configured identities are evidence, not a claim of native qualification; complete
qualification/conformance enforcement remains a separate explicit requirement.

Validate exact operation/run/source/request/profile/image/fence, outcome/result
presence, finite stage timing and cleanup disposition. Existing CHECKERS worker
validation still derives and checks default input, manifest, registry and project
result. The processor and ART foreground composition carry the typed response
through finalization; transport failures may have no receipt, but a completed
result must have one. Bind the receipt into AUTH finalization facts and CHECKERS
terminal bytes/digest. Preserve typed infrastructure outcomes and do not convert
cleanup pending into QC rejection or release local runtime capacity.

Allowed changes: CHECKERS API receipt/terminal facts, existing external execution
port/adapters/processor, ART source-execution composition, CHECKERS coordinator and
retained reads, the next Alembic migration, affected owner/adapter/PG/read tests
and fixtures, and this record. No new provider factory, compatibility execution
path, default qualification values, public handoff shortcut, retained-data rewrite
or migration-0071 edit is allowed. Use a new terminal/finalization schema version
for receipt-bearing evidence; retain old source-terminal decoding strictly for
reads, without inventing missing runtime custody. Existing prepared v1 retention
continues. The SQL finalization facts digest and closed terminal guards must match
Python, require bound receipts for completed new terminals, and preserve earlier
immutable rows/digests. Replay cannot mint acceptance from a historical receipt.

This is architecture/security-sensitive L1 work requiring plan review before
implementation and architecture/security plus QA/test-delta after tests. Human
review focus is authority-digest parity, exact receipt retention, historical read
limits and provider-neutral ownership. Acceptance includes destroyed/pending
receipts, receipt/source/fence/profile/runtime mismatch rejection, malformed
outcome/timing refusal, AUTH digest sensitivity, actual PostgreSQL terminal
retention/guard rejection, native wire decoding and a managed-style no-host-access
contract test. Public T4, finalization/POST, qualification and full acceptance
scenarios remain required subsequent work, not completion claims for this step.

Plan-review resolutions:

- Completed responses carry both receipt and typed worker facts. Received
  `infrastructure_failure` and `deadline_exceeded` responses carry their receipt
  through finalization with the corresponding closed infrastructure code;
  transport failure before receipt delivery may carry none. Native `cancelled`
  and task cancellation propagate `CancelledError`, without manufacturing QC or
  a finalization decision. Independent runtime cleanup ownership still applies;
  abandoned execution leases use the existing owner recovery path.
- Migration 0072 takes the run-table lock and refuses upgrade if any source-v2
  run is queued/running. Deployment must quiesce/drain those runs through their
  current owner before migration; no migration fabricates a terminal outcome or
  rewrites an immutable request. After upgrade, new source-v2 reservations still
  use the current request contract but can finalize only to the receipt-bearing
  terminal schema. Read dispatch explicitly handles prepared-v1, historical
  source-v2 terminal, current source-v3 terminal, and source-v2 nonterminal rows.
  Historical terminal evidence never enters current finalization/acceptance.
- The concrete Unix-socket adapter accepts only native runtime/cleanup evidence.
  It attaches its trusted factory `provider_key` to the retained receipt; that
  key is not accepted from the native wire. The processor independently compares
  it with the selected adapter identity. The managed-style test adapter uses its
  own explicit factory key, configured deployment identity, provider invocation
  and provider cleanup acknowledgement; native journal fields are not required
  of it and it cannot substitute for a Unix-socket/Smol invocation.
- Completed PostgreSQL proof uses a separate actual-ZIP source admitted through
  ART and builds worker facts from the exact claimed database lease/source.
  Existing non-ZIP infrastructure fixtures stay as failure-boundary coverage;
  synthetic worker leases are never transplanted into real DB rows. Tests cover
  retained queued/running/completed/infrastructure source-v2 reads and the
  migration's refusal to proceed over in-flight v2 work.
- Extract the native host's existing response serializer and emit a portable
  Rust fixture through that same function for Python wire-decoding proof. Add
  the serializer/test fixture files to scope; no fake native Machine creation
  or qualification is claimed. A received infrastructure receipt with pending
  cleanup must be retained, not collapsed into a code-only exception.

Receipt implementation now carries typed provider observations through the PRE
adapter, processor, ART foreground owner and AUTH-bound terminal v3. Migration
0072 adds a locked in-flight drain check, receipt guards and version-sensitive
finalization digest; 0071 is unchanged. Source-first coordination contract tests
pass (51), as do receipt substitution/timing/outcome, retained-read and managed
port tests (35), and single-PRE socket tests (12). These are portable contract proofs, not native qualification.
The migration applies to isolated PostgreSQL; all 12 SQL digest-parity and
receipt-substitution probes pass. The broader source integration run passes
41 cases, with a six-case affected replay after fixture extraction and addition
of received-failure retention. The actual migration entry refuses queued and running source
runs without row changes. A shared synthetic fixture matches the production Rust
response serializer and Python decoder; 53 selected Smol tests and the live
Python/Rust worker dialogue pass. None of these portable checks qualifies native
VM operation. The real-ZIP database test initially expected a removed prepared
handoff capability; source finalization correctly supplies no such capability.
The corrected proof checks eligible worker facts and exact retained receipts,
leaving T4 acceptance explicitly open. The six-case replay proves both completed real-ZIP receipt persistence and
received infrastructure receipts with pending cleanup. Python also decodes the
actual bytes emitted by the production Rust serializer in a separate portable
probe. Structural validation and Markdown links pass. Implementation review
remains required; public submission/acceptance and native qualification remain
outstanding parts of the overall objective.

Architecture/security and QA review of `a3748997f` found a selected-adapter
contract gap: a managed adapter could label self-consistent native receipt facts
with its own matching factory key. The repair adds a read-only expected PRE
runtime family to the capability and native adapter, and checks both factory key
and runtime family before AUTH finalization. A managed-port substitution test
now rejects native evidence. SQL retains its structural/source/fence/profile/
digest boundary; it cannot independently select a factory because the immutable
v2 request carries no trusted provider-selection fact. No test-only key mapping
is added to product SQL.

QA also found the new receipt module missing from explicit CI ownership. It now
belongs to the existing checker-delivery family, with the independent project
membership and ownership fingerprints updated. Actual collection selects all
36 receipt nodes exactly once across the project lifecycle partitions. The
36 receipt and 12 socket cases pass; all 59 catalogue tests pass after updating
the separate exact membership expectation. All six affected PostgreSQL outcome
cases and structural validation also pass after the family-binding repair.
These repairs require affected review replay. Documentation review passed the original candidate's scoped
claims; public acceptance and native qualification remain open.

Replay at `ceeccaaa6` found the expected-family property was missing from the
configured execution wrapper and its model-aware wrapper. Both now preserve the
family, and the socket proof builds the processor through the actual selected
PRE factory and the configured model-aware factory, refusing any PRE model
session. All 14 affected socket cases pass after fixture extraction; the earlier
combined wrapper/receipt run passed 50 cases. Documentation independently ran all
36 receipt cases on clean `ceeccaaa6`. The composition repair requires affected
review replay before scoped readiness.

Architecture/security, QA/test-delta and documentation replay passed clean
`cbd445d4a`, resolving the missing-wrapper-property finding. Architecture verified
both configured compositions expose `unix_socket`/`smolvm`; the affected socket
proof exercises both, including the prohibition on PRE model-session use.
CI-integrity remains compatible with the unchanged catalogue repair. Earlier
PostgreSQL and portable-runtime evidence remains scoped compatible evidence,
not relabeled as exact-head reruns. This closes backend receipt retention and
its reviewed repairs; it does not complete the initiative. The next concrete
journey gap is the authorized T4 source-pass handoff, followed by accepted
finalization/POST and the coordinated public API, CLI and MCP replacement.
Native qualification/conformance and full acceptance verification remain open.

### Atomic accepted source handoff (T4) plan

The reviewed PRE path now ends in an immutable, eligible source-bound terminal,
but no owner can accept that work: ART permits only foreground/terminal failure
states, TASK has no authorized intake-to-evaluation transition, and no durable
finalization event exists. Close that concrete gap with one short composed T4
transaction. This is a prerequisite for the required single public submission
command, not a second contributor workflow or an acceptance-by-checker shortcut.
T5 finalization and the coordinated public/CLI/MCP cutover remain required next
steps in this same PR; this internal transaction is not exposed until its
continuation is wired.

Plan and owner boundaries:

- Extend the existing ART intake owner with `finalization_pending`, immutable
  accepted evidence and a stable accepted receipt. Preserve operation/source
  identity, the original ZIP generation/SHA/count, command metadata, actor,
  assignment, predecessor, frozen policies and capacity charges. No placeholder
  Submission, retained artifact binding or POST dispatch is created at T4.
- Acquire TASK, intake operation, then CHECKERS run custody in the established
  order. Add a narrow CHECKERS port to lock and validate the exact current v3
  completed/eligible run for this source and its lease. It returns immutable
  facts for T4; raw detached terminal objects and historical v1/v2 evidence
  cannot confer acceptance. Bind ART's source/manifest identity to those facts.
- Revalidate current contributor/link/grant authority, task/assignment status,
  active operation pointer, foreground lease/fence/deadline, predecessor,
  revision acknowledgement/deadline/cap, locked TASK/PROJECT context and one
  selected image per phase. Reuse existing canonical context and revision
  checks; no alternate eligibility calculator or renewed foreground owner.
- Retain action/permission identity `submission.create`, with a closed
  operation-scoped acceptance resource and prepared/consumed AUTH facts. Extend
  the existing AUTH exact-resource dispatch for this lifecycle boundary; do not
  invent a submission UUID to satisfy the old creation resource. The old
  prepared-admission public producer is superseded by the later coordinated
  cutover in this PR, not preserved as a supported compatibility API. Its
  retained audit/evidence decoding must remain valid.
- TASK's existing intake custody participant gains a narrowly authorized
  transition from `in_progress`/`needs_revision` to `evaluation_pending` while
  preserving the exact pending operation pointer. ART writes accepted state,
  receipt and authorization provenance; the existing outbox append port writes
  one unique identifier/digest-only finalization event. These effects and the
  exact CHECKERS terminal reference must commit or roll back together.
- Already accepted replay validates immutable operation/evidence/receipt/event
  associations under current own-operation read authority before returning the
  stable receipt. It does not require the task to remain contributor-eligible,
  mint new acceptance, rerun PRE, refresh a lease or consume another revision.
  Lost commit acknowledgement resolves the same operation in a fresh root;
  unresolved outcome remains unknown and cannot be reported as known failure.
- Add migration 0073 without editing 0069–0072. Extend active-owner uniqueness,
  deferred TASK/intake/assignment closure, state-transition guards and AUTH/
  outbox closure to protect accepted pending work. Foreground expiration and
  cleanup must not terminalize or release accepted work. Accepted source,
  context, receipt, PRE reference and provenance are immutable. Finalizer lease
  and actual Submission registration belong to T5, not a fabricated T4 result.

Allowed files: ART intake APIs/owner/models/repository/replay and composition;
TASK intake custody/context/lifecycle ports and composition; CHECKERS exact
terminal-consumption API/coordinator; AUTH operation-scoped resource, evaluator,
prepared-handle/audit integration and adapters; outbox event contract/append
composition; migration 0073; affected real PostgreSQL/owner/AUTH tests and explicit
CI catalogue/schema fingerprint; this record and directly affected contracts.
No storage re-upload, host ZIP inspection, new checker factory, POST execution
redesign, new public alias, retained-row rewrite, qualification default or
provider deployment is allowed. The finalization event is an internal durable
contract; registration of its real T5 handler and public exposure must occur
before this PR is ready.

Risk is L0 authorization/workflow/atomicity. Plan review precedes implementation;
architecture/security and QA/test-delta review follow deterministic proof, with
CI-integrity review for catalogue changes and docs review for capability claims.
Human focus: fresh acceptance authority versus durable accepted continuation,
exact source/run ownership, rollback/commit uncertainty and revision accounting.

Acceptance proof uses actual ZIP upload, actual CHECKERS claim and receipt-bearing
worker completion through the existing portable fixture, then T4 on PostgreSQL.
Require one accepted receipt/event, task `evaluation_pending`, protected source
and capacity, and no Submission/binding/POST rows. Probe forged/stale or consumed
run/source/lease, historical terminal, changed packet/context, revoked authority,
wrong assignment/predecessor/revision acknowledgement, expired deadline, rollback
at participant boundaries, same-key replay, concurrent acceptance and lost commit
acknowledgement. Direct SQL probes must reject detached accepted state, missing
or mismatched decision/event/PRE evidence, accepted mutation and foreground
cleanup of accepted work. Keep native-provider qualification and public journey
completion explicitly unproven by these internal portable tests.

T4 plan-review resolutions:

- The receipt is acceptance of the source command for durable finalization. Its
  operation ID and exact PRE terminal identify that accepted command; it is not
  a formal Submission, POST verdict or final task acceptance. The snapshot fields
  say `evaluation_pending`/`finalization_pending` at acceptance, never the task's
  later current state. TASK gains a T4-specific authorized direct transition for
  both initial `in_progress` and governed `needs_revision` work. Do not enable an
  unguarded generic lifecycle shortcut or persist an intermediate `submitted`
  state. Require successful initial and revision tests as well as denial cases.
- The closed acceptance resource under `submission.create` has
  `resource_id == operation_id`. Its exact canonical digest binds operation,
  actor/link, project/task/assignment, command/context/source digests, selected
  PRE run/request/terminal and manifest identities, and accepted policy lineage.
  Prepared consumption and replay explicitly dispatch on this operation-scoped
  resource shape; a Submission-creation resource, another operation or changed
  digest must not replay it. Retained old audit facts remain readable, without
  fabricating a Submission ID for the new action.
- T4 performs fresh authority, revision and owner checks. After T4 commits, T5
  relies on the immutable accepted receipt/source/run/decision/event under its
  own continuation fence. It must not repeat foreground lease, revision
  deadline/cap, submitter grant or contributor-eligibility checks which can expire
  after valid acceptance. T4 tests prove later deadline/grant changes cannot
  invalidate or expose accepted source to foreground cleanup; T5's required
  proof must additionally finalize across those changes before overall completion.
- The foreground composer must keep the existing heartbeat over PRE through T4.
  T4 uses short SQL-only roots and rejects expiration at its final deferred commit
  boundary, not merely when it initially read the lease. The accepted-state
  transition check is distinct from later accepted custody: a later T5/read must
  not reapply the old foreground expiry condition. No lease extension beyond the
  absolute PRE deadline is allowed.
- PostgreSQL concurrency proof uses independent sessions for both orders of
  T4 versus expiry/abandonment. Acceptance winning leaves source/charge/pointer
  protected and abandonment refused; expiry/abandonment winning prevents an
  accepted receipt, event or task transition. Also race duplicate T4 commands
  and prove one stable accepted result/event. Preserve the actual ZIP and real
  database lease fixture while explicitly treating its simulated runtime/Smol
  observations as portable transaction evidence only.

T4 authorization implementation checkpoint:

- Added a closed operation-scoped `submission.create` acceptance resource and
  exact prepared consumption binding for source, PRE request/terminal, lease,
  context and receipt evidence. No formal Submission identifier is fabricated.
  The persisted audit target uses the existing `submission_operation` identity.
- Retained receipt validation checks the original immutable decision digest;
  callers must first authorize a current own-operation read. This does not issue
  a new acceptance handle or continuation authority.
- Real PostgreSQL verification: 29 tests passed in
  `/tmp/t4-auth-final.log` (isolated-run metadata `/tmp/t4-auth-final.json`).
  Coverage includes exact acceptance/receipt, consumed-handle reuse, changed
  custody evidence, and missing/reviewer/foreign/revoked/admin grant denial.
  The tests exposed and drove repairs to the closed decision vocabulary and
  prepared-denial audit dispatch. Structure validation and diff checks passed.
- This checkpoint is AUTH participation only. ART accepted-state storage,
  TASK transition, CHECKERS terminal consumption, atomic outbox/migration and
  acceptance race/rollback proofs remain T4 work. It is not proof of public
  exposure, T5 continuation, native qualification or end-to-end completion.

T4 CHECKERS participation checkpoint:

- Added `lock_acceptance` on the existing coordinator: exact run/request/terminal,
  completed eligible execution, invocation receipt and persisted execute/finalize
  decision references under the existing live TASK/source/run locks. Actor/key
  replay normalization cannot substitute another run for acceptance. ART must
  still atomically consume the immutable reference in the accepted transaction.
- Current and retained reads share indexed terminal/lease/timing validation.
  Actual upload/PRE fixtures exercise eligible acceptance and reject infrastructure
  outcomes, substituted run/request identities and terminal digests.
- Final source/receipt verification: 79 passed in `/tmp/t4-pre-final.log`, metadata
  `/tmp/t4-pre-final.json`; structure and diff checks passed. The simulated runtime
  remains portable evidence, not native provider qualification.
- Wider coordination regression: 115 passed and seven failed in
  `/tmp/t4-pre-record-regression.log`; failures construct obsolete prepared
  admission lineage with `semantic_manifest_id`. Those fixtures must be converted
  to source contracts during the cutover; the wider suite is not green.
- Accepted-state persistence, composed TASK/ART/outbox commit and T4 race/rollback
  proof remain unfinished. No public acceptance or continuation is exposed here.

### Composed accepted handoff implementation and remaining proof

The existing foreground admission owner now composes T4 under its root transaction:
current own-read/Submitter authority, canonical TASK/PROJECT/revision context,
exact locked eligible PRE, operation-scoped acceptance consumption, identifier-only
finalization event, immutable receipt/context and the direct TASK pending transition.
Replay validates the retained decision, receipt, PRE and event without rechecking
foreground eligibility. Connection/acknowledgement uncertainty resolves the same
operation in a fresh root. A PostgreSQL constraint rejection is a known rollback,
not a transport-unknown outcome.

Migration 0073 extends active custody to `finalization_pending`, retains unique
PRE/decision/event references, and adds deferred exact context, receipt, authority,
event and TASK closure. Only transition into accepted custody checks the current
foreground deadline. Revision head/acknowledgement, cap, predecessor and deadline
are also checked at that transition; accepted reads do not reapply them. Source
charge and accepted fields remain immutable. No formal Submission, retained binding
or POST event is created by T4.

Evidence for this worktree:

- `/tmp/t4-transaction-proofs.log`: five composed initial acceptance/replay,
  outbox/TASK rollback, concurrent duplicate and lost-acknowledgement cases passed.
- `/tmp/t4-all-admission.log`: 25 passed, including existing T1/replay behavior and
  accepted mutation/cleanup refusal, revoked authority, both independent-session
  acceptance/abandonment winner orders and expiry at the deferred commit boundary.
- `/tmp/t4-lifetime-final.log`: six passed after adding cancellation/late revocation
  and changing expiry fixtures to observe database time rather than infer it from
  a host sleep. These replay the changed race/deadline cases as well.
- Earlier runs exposed multi-statement asyncpg execution and deferred PL/pgSQL
  expression errors in the draft migration; both were repaired before the above
  passing runs. One composed run was rejected during sealing because observed
  `sealed_at` preceded EOF. The guard was retained; subsequent composed runs
  passed. None of this is native-provider qualification.

The current schema fingerprint is
`5a1f343869d5599158b74372e1a150fe913659313b03f71185a4360c8163e186`.
The original seven obsolete prepared-coordination fixture failures remain open;
these passing runs do not claim a green full backend suite.

T4 is not declared complete: a real revision handoff, the foreground heartbeat
across the whole composed command, all planned denial/SQL substitution cases and
focused implementation review remain required. Current revision fixture setup
calls the removed prepared-source producer (`submission_admission.py` still passes
`commitment`/`manifest` and prepared-generation selectors to source-only builders).
Restoring that obsolete execution path would move away from the requested contract.
The new T5 path must create the predecessor for the actual revision proof. This
changes proof sequencing, not the required revision behavior or completion bar.
No public accepted route or live finalization handler is exposed by this checkpoint.

### Durable accepted finalization (T5) plan

Close the concrete remaining gap: an accepted source currently holds TASK/capacity
and an outbox event but cannot become a formal Submission or start POST. Extend
existing ART custody, TASK Submission construction and CHECKERS evaluation dispatch;
do not implement a second independent Submission writer or restore prepared PRE.

Required behavior:

1. Register `SubmissionFinalizationRequested` with the existing durable outbox
   composition and fixed-service authority. Claim a separately fenced accepted
   continuation in a short transaction. Recognize and validate an already finalized
   operation before requiring a pending TASK pointer or a new lease.
2. Extend the existing typed ART provider interface and adapters with
   `observe_sealed_source(source, operation_evidence=...)`, taking only the exact
   committed `SealedSubmissionSource`. Return a frozen metadata observation of
   location, provider generation and byte count, or absence; raise an integrity
   error on mismatched ownership/generation/size. This is distinct from uncertain
   upload completion recovery, which currently rehashes the ZIP. S3 must issue
   version-pinned HEAD and validate VersionId, ContentLength and existing ownership
   metadata. Local must use the existing directory lock, persisted seal and
   no-follow descriptor, checking private regular-file permissions, device/inode
   generation and size without reading the body. Do not use unversioned `head()`
   or `observe_source_upload()` as this proof. Observe outside TASK locks, then
   compare every observation field to immutable accepted custody again under the
   T5 TASK/operation locks and current continuation fence. Combine observation with
   committed ingress and exact PRE hash/manifest evidence; metadata alone cannot
   authorize adopting an arbitrary object or prove its hash. Do not upload/copy/read
   the ZIP again merely to create a retained identity; register the exact already
   stored object. Retained reads must remain pinned to that same generation.
3. Under TASK → operation owner locks, consume narrow service continuation
   authority over immutable acceptance and the current continuation fence. Do not
   call ordinary contributor creation with an `evaluation_pending` exception or
   recheck the original bearer token, grant, revision cap/deadline or foreground
   lease. Preserve accepted initial/revision status as historical dispatch evidence.
4. Reuse logical ART content only for exact SHA/count identity, record a replica
   for the actual source key/generation with trusted verification provenance, and
   bind it to the actual newly allocated Submission. Reuse existing ART owners and
   binding rules. Required schema extensions must distinguish source custody from
   retained prepared receipts without fake put, prepared-generation or verifier IDs.
5. Reuse `build_submission`, existing policy snapshots, global version allocation,
   assignment revision-round accounting, selected POST request construction and
   outbox append. One transaction commits formal Submission, exact ART binding,
   evaluation/dispatch/reservation, POST event, finalized operation association and
   pointer release. Retries return that immutable association; no duplicate version,
   binding, revision round, dispatch or event is permitted.
6. Keep the source retained/protected through failure, retry, lease loss and provider
   uncertainty. Only separately authorized cleanup may later delete eligible data.
   Do not invent administrative cancellation or silently reopen/reassign accepted
   work on later grant changes.

Allowed scope: ART intake/source/API/models/repository and retained material/binding
owners, `app/interfaces/artifacts.py` and existing Local/S3 provider adapters; TASK Submission API/composition/participants/replay/dispatch and affected
lineage readers; AUTH closed continuation/binding contracts and adapters/catalogue;
existing CHECKERS POST content/reservation adapters; outbox handler registration;
new forward migration 0074 and affected schema fingerprint; tests/CI selection and
direct contracts/this record. Inspect shared consumers before changing retained
admission/verification fields. Retained rows remain readable; new execution must
use accepted source custody. Public raw-ZIP/API/CLI/MCP replacement remains required
in this same PR after a real finalization handler is available.

Prohibited: fresh human submission authorization in T5, renewed PRE or a second PRE
VM, host ZIP inspection/spooling, whole-source re-upload/copy to a new key, arbitrary
locator/hash adoption, fake legacy identifiers, parallel provider factories,
replacing POST routing/review/contribution owners, source cleanup before retained
custody, defaulting unqualified C-values, deployment or merge.

Risk: L0/L1 authority, workflow and immutable evidence. Required review: ARCH/SEC
for plan/continuation and storage closure, QA for transaction/race/public-journey
proof, DOCS for exact exposure and qualification claims. Human merge review should
focus on accepted authority lifetime, source-to-retained provenance, replay before
currentness, revision accounting, and removal of superseded public producers.

Verification: real PostgreSQL plus actual Local/MinIO source ownership where the
provider behavior is claimed; actual ZIP and worker proof with explicitly simulated
runtime observations until native qualification is available. Exercise accepted
T4 → finalization → reserved POST and existing POST completion/routing, then create
a real governed revision source and exercise T4/T5 again. Test rollback between
participants, duplicate deliveries and claims, lease fencing, lost commit response,
broker/observation failure and retry, exact finalized replay after TASK advances,
and successful continuation after original foreground/revision windows and grants
expire. Probe SQL association/provenance substitution and source deletion refusal.
Run affected retained-reader and POST policy branches, including default human
review and configured automatic final acceptance/contribution evidence. Finish the
public API/CLI/MCP drill and A01–A35/C01–C07 audit before overall completion; internal
T4/T5 tests alone cannot close the goal.

T5 storage verification must reject an absent recorded version, a response naming
another version, and replacement of the local inode. A newer S3 version at the same
key must never be silently adopted: the recorded old version may still be observed
if present; if absent, fail closed. Assert that observation makes no body-read or
upload/copy calls. This observation is availability/provenance evidence combined
with committed ingress/PRE, not a new content hash attestation or native provider
qualification claim.

Review repairs after f07ddcbd0: T4-QA-01 adds direct database assertions for zero
Submission ART bindings, POST checker reservations, dispatches and request events
at acceptance. T5-PLAN-01 is resolved in the plan above by explicitly extending the
existing provider port for exact sealed-version metadata observation. Revision,
whole-command heartbeat and substitution proof remain open; these repairs do not
claim the complete T4/T5 or public journey.

### Exact sealed-source observation implementation

The existing ArtifactStore now exposes `observe_sealed_source`, returning a frozen
location/generation/size/upload-fence observation or absence. S3 uses version-pinned
HEAD with the existing ownership response validator. Local uses the existing
operation directory lock, persisted seal and no-follow descriptor; it verifies
private sealed permissions, inode generation and size without reading ZIP bytes.
This is metadata evidence only, combined later with committed ingress and PRE;
it is not a hash attestation, arbitrary adoption capability or provider qualification.

Focused tests use real Local files and MinIO: same-size inode replacement is
rejected, missing recorded objects/versions return absence, a newer same-key S3
version cannot replace the recorded old version, and substituted response version,
size or ownership metadata is rejected. The S3 test proxy exposes HEAD only; the
Local test forbids body `pread`. Provider protocol and architecture guards include
only this additional operation, without extending foreground upload authority.

T4-QA-01's focused PostgreSQL regression passed (1 passed, 26 deselected;
`/tmp/t4-review-repair.log`, metadata `/tmp/t4-review-repair.json`). This is scoped
worktree evidence, not a complete T4 or exact frozen-head suite. The observation
implementation still needs its test result and focused review; it has no T5 caller
until accepted continuation, retained registration and atomic Submission/POST
composition are implemented. Full original acceptance requirements remain open.

Observation verification: `/tmp/t5-source-observation.log` completed with 51 passed
and 12 failed. All five new actual Local/MinIO observation cases passed; the failures
were the source-PRE grant absent from the exact provider-owner inventory and two
removed PRE consumers still listed as POST materialization importers (the latter
also failed ten inventory mutation probes). Repairs name only the exact source
reader/path and `open_source`, and remove only those obsolete POST imports; no
broad provider allowance is added. The full affected command is being replayed.

Focused architecture/security review found no new observation defect. QA identified
that the Local test trapped only `pread`, and the frozen observation lacked runtime
shape validation. Repairs add a descriptor-aware `read` trap while permitting seal
metadata reads, strict generation/count/fence/location validation with malformed
value cases, and explicit registration in the existing MinIO-enabled test lane.
T5 integration remains open; this provider checkpoint does not complete finalization.

The repaired observation/architecture/conformance command completed with **72
passed** (`/tmp/t5-observation-repair.log`); CI lane checks completed with **17
passed** (`/tmp/t5-observation-lanes.log`). Structure validation, Commitrail and
Markdown-link checks passed. Scoped ARCH/SEC and QA reviews passed at clean
`1f328b545777751f63f984528626f112f6bc723e`. QA independently inserted an in-memory
`os.read(bundle_fd, 1)` mutation and the targeted Local test failed specifically at
its body-read trap; no repository mutation remained. An earlier unconfigured
probe failed during MinIO setup and is excluded from evidence. The shared tests
began on the corresponding worktree before freeze; do not attribute them as a new
exact-commit full-suite execution. The next required change is accepted continuation
and atomic retained registration/Submission/POST composition, not additional
observation scaffolding. This checkpoint leaves the end-to-end goal incomplete.

### Accepted continuation and retained registration implementation

T5 now has a fixed-service `artifact.submission.finalize` action, an exact accepted
operation/context/source/receipt capability, and separate claim and commit decisions.
The continuation lease is committed before metadata observation outside TASK locks.
The final transaction registers the same sealed source as ART content/replica and a
source-backed admission, then invokes the shared TASK Submission/binding/POST dispatch
writer. It retains the original acceptance decision for creation provenance and a
separate service decision for continuation. Finalized replay reads retained closure
before any new lease or provider observation. No fabricated put or verification
receipt substitutes for accepted ingress/PRE evidence.

Migration 0074 extends the closed audit action/permission pair, discriminates source
admissions from retained put/verification admissions, and enforces acceptance,
continuation authority, finalized Submission/dispatch closure, and immutable source
ownership. The AUTH kernel's action classifications move to the existing domain
classification module; this removes its oversized-file debt without adding debt.

Verification on the implementation worktree: five focused real-PostgreSQL AUTH
cases passed (claim/commit exact consumption plus missing/wrong/revoked service).
The first composed T5 run advanced through registration and shared Submission/POST
creation to commit, then failed because a shared deferred trigger referenced intake
fields on a replica row. The repair isolates intake-specific checks in nested table
and operation branches. Known database failures now propagate directly rather than
being mislabeled uncertain commit acknowledgement. This is diagnostic progress,
not a passing T5 or POST execution claim. The composed test also checks replay,
original acceptance receipt stability, one Submission/dispatch/POST reservation,
same source key, retained charge, absent fabricated receipts, and rejected removal
of replica source ownership. Its repaired result remains required.

Still required: integrated T5 failure/retry/concurrency proofs, the finalization
outbox handler and composition, POST reads from exact retained source generation,
revision and public API/CLI/MCP journey, and the complete acceptance/deployment audit.
The single PR remains the delivery unit; this implementation does not complete it.

The repaired composed PostgreSQL T5 test passed (**1 passed, 27 deselected**,
`/tmp/t5-composed-repaired.log`, isolation metadata `/tmp/t5-composed-repaired.json`,
cleanup complete). It includes exact finalized replay, original acceptance replay,
all registration/dispatch assertions, and the source-link removal rejection.
Catalogue tests passed (**7 passed**, `/tmp/t5-catalogue-final.log`); changed Python
files pass Ruff; Markdown links and structure validation passed. A subsequent
unused-import removal shifts the unchanged kernel debt function by one line, with
the ledger coordinates adjusted accordingly. These are worktree-scoped results,
not full-suite or exact frozen-commit provenance. T5 crash/concurrency and POST
execution/public integration remain open; focused implementation review follows
this reproducible milestone.

### POST source custody continuation

The next bounded extension follows the frozen T5 review: repair content/adapter
immutability with direct SQL probes; bound continuation leases by the existing
OUTBOX one-hour structural ceiling (no deployment default or C05 approval implied).
Extend the existing POST selector/materializer and CHECKERS material contracts to
carry exact accepted-operation custody without provider coordinates. Preserve
retained verification-backed evidence and its canonical digests; new source-backed
material carries operation, accepted-source and acceptance-receipt hashes instead
of fabricated verification IDs. Both current and predecessor material use the same
selector and version-pinned `open_source` capability. Update external checker SDK
and service validation together. Do not widen generic object-key parsing.

Allowed scope is ART selection/materialization, CHECKERS material facts and retained
input custody, the external checker contract validators, focused tests and this
record. Prohibited changes include weakening AUTH/currentness, exposing provider
locators, copying/reuploading source bytes, and claiming production provider
qualification. Acceptance requires real T5-to-POST material execution, exact source
version substitution controls, and retained-evidence roundtrip tests. Risk is high;
ARCH/SEC reviews custody and QA reviews execution/failure proof before readiness.

Review repairs: source-linked content SHA/size/media changes now fail under a
narrow content trigger, with source admission validation holding a content share
lock through commit. Replica adapter must match its namespace. Direct SQL digest,
size, media and adapter substitutions are rejected in the composed test. The
continuation constructor and SQL claim transition reject durations above the
existing OUTBOX one-hour structural ceiling; deployment must still supply an
explicit measured duration. Three constructor bound cases pass; expired-claim
recovery proof remains required.

POST selection now resolves source-backed admissions from their finalized operation
and uses exact sealed-generation `open_source`. CHECKERS facts, ART's aggregate grant,
and the Rust SDK/service validators admit one complete source witness or one retained
verification witness. Python contract tests pass (38); Rust SDK tests pass (9), and
both targeted service grant tests pass. Artifact architecture tests pass (48).
The integrated run passed the T5 SQL mutation probes and reached selected POST
execution, exposing an additional closed field list in ART's grant builder; that
list is now updated without importing CHECKERS internals. The rerun is pending.
Historical revision-input SQL still requires extension for a source-backed
predecessor, and actual MinIO POST version-substitution proof remains required.

Migration 0075 extends both the current-input authorization digest reconstruction
and the historical predecessor custody predicate for source-backed material. Its
verification-backed branch preserves existing keys, values and optional revision
context encoding. The composed test originally reached POST terminal publication
and was correctly rejected by the old SQL receipt reconstruction; 0075 repairs
that actual failure rather than bypassing the receipt guard.

Integrated verification now passes: **5 passed, 27 deselected** in
`/tmp/post-source-composed4.log` (metadata `/tmp/post-source-composed4.json`). Both
normal T5 and worker death after a committed claim proceed through actual owner
POST selection/materialization, controlled selected evaluation, terminal commit,
and replay. The expired-claim case proves a live competitor is refused and a later
independent transaction reclaims generation 2 without duplicate Submission/POST.
The storage wrapper forbids generic unversioned reads and requires the exact
sealed source; replay does not read it again. The three lease constructor bounds
also pass. This uses real PostgreSQL and Local storage with explicit in-process
intake/checker fixtures; it is not native Smol or hosted provider qualification.

Runtime/contract verification passed **74 tests**; a further predecessor witness
roundtrip brings the focused contract file to **39 passed**. The earlier scratch
lifetime test incorrectly injected the retired `prepared_generation_id` into the
current PRE wire identity; it now keeps that ID only in private ART scratch facts.
Its shared scratch lifetime assertions remain. Rust SDK tests pass **9**, targeted
Rust service grant tests pass **2**, artifact architecture passes **48**, structure,
changed-file Ruff, and Markdown links pass. These are scoped worktree results.
Fetched current `origin/main` remains `94334ccf4`, with no missing base commits.

Remaining before end-to-end completion: MinIO source-version substitution during
actual POST; real source-backed revision routing/preparation/POST; rollback/lost
acknowledgement/concurrency expansions; durable finalization outbox/Celery wiring
and operational stall projection; public API/CLI/MCP cutover and the complete
A01–A35/C01–C07 audit. No merge or overall readiness is claimed by this checkpoint.

Scoped ARCH/SEC and QA review passed for committed `15c8945f0`, including the
content/adapter repairs, exact source POST path, lease ceiling and generation-2
recovery. Reviewers inspected the frozen commit; later parent-authored MinIO test
edits did not enter that verdict. No native or complete-goal qualification follows.

The provider integration extension reuses the same T1/PRE/T5/POST owners with a
versioned real MinIO namespace. After T5 it writes different invalid ZIP bytes to
the same key. The positive case must GET the recorded VersionId and complete POST;
the negative removes that recorded version and must retain infrastructure failure
without invoking the checker or falling back to the newer version. Both must replay
without another read. The test is registered in the existing MinIO-enabled lane.
The first local launch collided with that lane's fixed bucket before tests started;
read-only health/credential probes established a healthy provider and existing
bucket. The rerun uses the runner's unique-bucket mode rather than deleting shared
storage. This setup failure is excluded from behavioral evidence.

The MinIO rerun passed both scenarios (**2 passed**, `/tmp/post-source-minio2.log`;
metadata `/tmp/post-source-minio2.json` records database and bucket cleanup).
The positive path executed POST against the original version after replacement;
the missing-original path persisted infrastructure failure with zero checker
invocations. Each made exactly one version-qualified GET; POST and finalization
replay added no reads. This proves real MinIO storage behavior with controlled
checker execution, not native Smol or AWS qualification. CI lane/catalogue checks
pass **76 tests** after correcting a pre-existing stale shared-family fingerprint.
The new MinIO module belongs only to `omnicore_sdk`; it did not change shared-family
membership. Scoped QA and CI integrity review of `06fe9027e` found no blocking
defect and confirmed both cases are collected; removing the module from the lane
triggers `missing_lane_modules`. The provider run is worktree evidence based on
`15c8945f0`, not an exact-head rerun of `06fe9027e`.

The next implementation boundary is durable delivery of the already committed
`SubmissionFinalizationRequested` event. Allowed scope: ART finalization and its
delivery adapter, existing OUTBOX composition/worker routing, focused integration
tests and this record. Preserve the single T5 operation and existing delivery
owner; prohibit provider-body I/O in finalization, contributor-token reuse,
publication-only acknowledgement and fabricated deployment defaults. Acceptance
requires committed invocation observation, exact event/evidence matching, a
transactional invocation fence on claim and effect, bounded continuation custody,
and replay after committed T5 without another provider observation. Worker routing
and stalled progress must subsequently be proved through the durable owners.
This is high-risk workflow/authorization work requiring architecture/security and
QA review, with human review focused on lock order, expiry and acknowledgement.

The delivery implementation now registers the accepted event with the existing
production OUTBOX owner. Its handler requires an independently committed current
invocation. Every finalization claim, effect and unknown-commit recovery locks
TASK/operation, authorizes the fixed service, validates the exact accepted event
and acquires the existing OUTBOX invocation fence in that transaction. Continuation
expiry cannot exceed the delivery claim. Finalized replay validates retained
associations before provider access; the worker adapter initializes storage lazily
only for source metadata observation. UNKNOWN delivery uses OUTBOX's existing
explicit replay-safe registration and bounded retry machinery.

The composition reuses the existing `DeliveryOptions` convention (300-second lease,
240-second handler timeout, five attempts, 5-second exponential retry base capped
at 300 seconds) for this bounded metadata/SQL operation. These values are not a
new measured deployment qualification. Separate finalization capacity, visible
operation stalls and operator retry authority remain required under C04/C05.
The focused PostgreSQL test exercises the same adapter through actual OUTBOX
claim/invoke/finalize, simulates failure after T5 commits, and requires a second
delivery to acknowledge without another provider observation.

The first integrated run reached committed T5 but SQL refused retry of UNKNOWN
for this event: Python registration alone did not satisfy the database's closed
feature list. Migration 0076 extends that exact list only for version-1 submission
finalization. The public schema fingerprint was updated from the actual migrated
database; no schema guard was bypassed.

The repaired real PostgreSQL run passed **2 tests** (`/tmp/t5-delivery2.log`, metadata
`/tmp/t5-delivery2.json`). Loss after T5 commits replays the same Submission with one
provider observation. Loss during observation fences the first finalizer before
T5, retains pending custody, and allows generation-2 recovery after lease expiry.
Both acknowledge only the replacement invocation; stale invocation replay is
rejected. Production candidate discovery includes the accepted event. The existing
generic-event SQL refusal test also passed (`/tmp/t5-delivery-negative.log`, matching
metadata JSON), proving UNKNOWN retry remains closed for unregistered events.
Earlier ordinary/expired-claim T5 cases passed in `/tmp/t5-delivery1.log`; its new
delivery case failed before the migration and is not counted as a success.
Architecture/outbox contracts/topology passed **117 tests**; changed-file Ruff,
structure and Markdown-link checks passed. These are scoped worktree results,
not complete durable-worker or public-journey qualification.

Scoped architecture/security review passed clean `3fdbc820a`. QA/test-delta found
no production defect but requested explicit downstream row counts in each lost
invocation branch. Both recovery cases now assert exactly one Submission,
SubmissionDispatch, checker run and initial POST event. The strengthened run
passed **2 tests** (`/tmp/t5-delivery3.log`, metadata `/tmp/t5-delivery3.json`), with
database cleanup confirmed. This remains controlled-store handler proof through
real OUTBOX; production composition is exercised for discovery, not native Celery
execution or lazy provider startup. No scope expansion follows from the review.

### Finalization worker capacity boundary

Route accepted finalization selectors to a separate static Celery task/queue while
retaining the same OUTBOX claim/invoke/finalize owner. Discovery carries event type
only as a routing hint; worker composition independently limits registered handlers
to its assigned event group. A finalization consumer must be prefork and must not
consume other queues. Existing general workers explicitly select their current
queues, so adding the finalization queue cannot silently share their capacity.
No deployment concurrency default is introduced: enabling the separate consumer
and qualifying its resource allocation remains C04 work before public cutover.

Allowed changes are OUTBOX candidate projection/composition, Celery routes and thin
entrypoints/topology, affected Compose queue selectors and existing worker tests.
No new lifecycle/retry owner, broad retry authority or broker-owned business truth.
Acceptance requires routing tests, real worker topology rejection, wrong-group
delivery refusal and retained scan/publication recovery behavior. Workflow risk
requires architecture/security and QA review; human focus is actual queue/pool
selection and preservation of the database dispatch barrier.

The queue split uses `workstream.submission_finalization` and a thin bounded
`workstream.outbox.finalize_submission` entrypoint. Discovery selects its queue by
stored event type; delivery rechecks the immutable stored type against the worker's
filtered registry before even recovering an expired claim. The same OUTBOX owner
still owns all receipts and backoff. Finalization workers reject mixed queues;
general and finalization entrypoints reject the opposite worker group. The existing
300-second lease is shared through ART's public contract with a 360-second process
bound; no direct OUTBOX import was added to topology code.

Local Compose has an opt-in consumer profile with required positive concurrency;
no value is chosen by the implementation. A rendered-config check caught `extends`
merging the general backend profile into that consumer; explicit YAML mapping
inheritance now keeps the consumer out of ordinary backend startup. General hosted
workers also select their queues explicitly, and hosted preflight permits only
that exact selection. Hosted finalization consumer provisioning through the release
wrapper, measured capacity/saturation proof and operational recovery remain work.

Verification: **30 PostgreSQL worker/recovery tests passed**
(`/tmp/t5-queues-pg.log`, metadata `/tmp/t5-queues-pg.json`, cleanup confirmed),
including wrong-group refusal for pending and expired POST work and the existing
real prefork cancellation-resistant process bound. Static topology/contracts/
observability checks passed **81 tests**, with the existing real-Redis observability
test skipped because no test broker was supplied (`/tmp/t5-queues-static2.log`).
Local Compose tests passed **6**, hosted configuration tests passed **2**, and the
expanded short-queue-option refusal passed a further focused rerun. These prove
configuration/owner boundaries, not finalization saturation or live broker delivery.
Changed-file Ruff and Markdown links passed; structure validation is recorded with
the candidate checks. All test receipts are worktree evidence based on `cc38dc34f`.

Architecture/security and documentation review passed clean `263393c34`; QA passed
the queue split and identified a provider-startup dependency in the existing global
Celery child initialization hook. A validated exclusive finalization child now
defers that hook; unfinalized work still initializes the canonical provider on
demand, while finalized replay can reach SQL without provider startup. General
workers retain their original initialization. Two discriminating startup cases
prove provider unavailability prevents general startup but is not consulted by the
finalization child. The combined static rerun passed **83 tests**, with the same
existing no-broker observability skip (`/tmp/t5-queues-startup.log`). This repairs
the identified hook dependency without claiming a live broker/provider replay drill.

### Owner-backed finalization stall observation

Expose exact delivery progress from the existing OUTBOX append/custody participant,
requiring the same immutable event facts as `require_existing`. Extend ART's
authorized own-operation read with finalization progress. A pending accepted
operation is stalled only when its exact durable event is dead-lettered; age and
lease expiry alone do not imply a stall. Finalized operation facts take precedence
over delayed transport acknowledgement. Reads do not release source charges,
change task/operation state, invoke storage, or grant retry authority.

Allowed scope: OUTBOX public observation value/port and its existing service;
ART finalization progress value/reader and the existing foreground read owner;
focused real PostgreSQL/auth and custody tests. Preserve exact event binding,
current contributor read authorization and sanitized errors. Verify pending,
claimed, exhausted and finalized states, substitution refusal and no read effects.
This is an internal read boundary for the pending public cutover, not the full
API progress contract. The existing `operations.submission_gate.repair` action is
registered but planned/unavailable; its applicability to finalization recovery
needs assessment before activation. C05 requires a concrete authority decision
before inventing a new business/admin capability. Risk remains authorization/workflow;
architecture/security and QA review are required.

The exact exhausted/finalized progress cases passed on real PostgreSQL
(`/tmp/t5-progress2.log`: **2 passed**, isolated database/role cleanup confirmed).
Exact OUTBOX identity substitution and pending/claimed/acknowledged observation
passed separately (`/tmp/t5-progress-custody.log`: **1 passed**). Related OUTBOX
contracts and ART architecture checks passed (`/tmp/t5-progress-static.log`:
**94 passed**). Evidence is for the working tree based on `cb09fd84c`; it does
not prove public operation reads or operator retry. Ruff passed for all changed
Python files.

Scoped architecture/security and QA/test-delta reviews passed on clean
`82452d5f314d163b44c43fa6063ac44a6f60b033`, against `cb09fd84c`. Reviewers checked
current authorization before observer construction, exact immutable event custody,
finalized precedence, refusal of inconsistent terminal delivery, and absence of
provider/retry effects. Structure, Commitrail and Markdown-link checks also passed.
A fresh fetch found no missing `origin/main` commits.

Recovery follow-up must reuse the registered, currently planned
`operations.submission_gate.repair` action only for its narrow recovery purpose.
Current AUTH specifications require a system Operator grant, exact resource,
reason and append-only evidence. Existing POST delivery reconciliation is a
reference for retaining the original terminal attempt and authorizing a bounded
child; its current UNKNOWN-only contract cannot simply be relabelled as general
finalization recovery. Any implementation must qualify exact accepted operation,
source, event and current retry ownership, preserve original outcomes, and reuse
T5 rather than create another Submission path. In particular, finalizer lease
expiry currently uses the original envelope: a recovery child must supply its
verified live lease bound while retaining the original accepted event identity.
No recovery action has been activated by this checkpoint.

### Accepted-finalization operator recovery

Close C05's recovery gap using existing `operations.submission_gate.repair` and
OUTBOX finalized-UNKNOWN reconciliation custody. The first recovery uses the
existing one-child-per-original convention: a failed child remains visibly held;
there is no implicit new contributor command or unlimited retry loop. The original
accepted event and completed attempts remain immutable. Recovery must invoke the
same T5, retain its current service authority, and bind its lease to the live
child rather than the expired original.

Allowed scope: ART recovery values, owner and existing finalizer/handler; AUTH
resource/action activation and audit verification; existing OUTBOX reconciliation
ports; composition, worker routing, narrow SQL custody migration, corresponding
real PostgreSQL tests and current recovery documentation. No broadening of
Operator authority, QC override, source rewrite, new Submission writer, retained
data deletion or deployment defaults. Risk is authorization/workflow (L0).

Acceptance evidence: authorized exact retry and replay after revoked grant;
concurrent commands produce one child; reason/key/source substitutions fail;
failed authority rolls back child creation; worker verifies retained decision and
live child fence; successful recovery creates exactly one Submission/dispatch;
expired or substituted child cannot act; exhausted child is visible and keeps
source protection. Required reviews: architecture/security and QA/test delta,
plus documentation for public exposure claims. Human review focus is the exact
recovery authority and preservation of accepted evidence. This scope remains
unexposed until its composed behavior and custody checks pass.

The broader intake regression run completed: `/tmp/t5-progress-full.log` reports
**36 passed in 705.07s**; metadata records launch head `82452d5f3` and successful
database/role cleanup. Recovery development overlapped the tail of this run, so
this is regression evidence for the progress work, not a frozen recovery proof.

Recovery implementation is in progress. The first focused run caught the closed
active-action catalogue boundary; the second reached the command but caught the
missing authorization-decision resource literal. Both were repaired without
weakening either registry. Migration execution caught a multi-statement prepared
query; function and trigger creation now use separate statements. No successful
recovery end-to-end claim is made until the composed PostgreSQL test passes.

The composed recovery run `/tmp/t5-recovery4.log` passed **4 PostgreSQL tests**
(92.90s; isolated database/role cleanup confirmed). It covers current Operator
authority, concurrent requests producing one child, exact replay, reason conflict,
direct-SQL forged reason/decision refusal, revoked-grant denial, live recovery
progress, one Submission and POST event, and production worker registration and
group isolation. The original delivery remains dead-lettered and immutable.

Related static checks passed **84 tests**; the sole stale active/planned-count
assertion was updated from 168/25 to 169/24 for activation of the existing action,
and its focused rerun passed (`/tmp/t5-recovery-catalogue.log`). No action or
permission was added. OUTBOX rejected the initial `request_key` payload field
under its existing privacy guard; recovery now names its persisted command
identity `request_id`, with no guard exception or compatibility alias.

Migration 0077 adds one unique recovery-parent index, one custody function and
one insert trigger, and extends only the existing exact UNKNOWN-retry allowlist.
The PostgreSQL-observed schema fingerprint is
`1d0060750a195d348606ae5eaf9ae9a47462e1cf6062f278c9f2b408b707f8b2`
(`/tmp/t5-recovery-schema3.log`); the subsequent passing run validated it. The
structure ledger updates only the two-line source offset for unchanged
`AuthorizationService._require_prelocked`; its size and hash are preserved and
structure validation passed. No new debt or exception was introduced.

Additional regression in progress explicitly waits for the original delivery
lease to expire before successful recovery and rejects a stale child invocation
after acknowledgement. This must complete before claiming the recovery checkpoint
verified. The one-child limit follows existing reconciliation: exhaustion remains
held, not an automatic contributor retry. Public operator discovery/command
routes and the full public operation progress contract remain outstanding.

### Recovery review repair

The additional original-expiry/stale-child run completed successfully:
`/tmp/t5-recovery5.log` reports **3 passed**, with database/role cleanup confirmed.
Frozen review of `a32a870f8` nevertheless found direct-SQL custody gaps; typed
command success was not sufficient proof of those guards. Architecture/security
required exact retained system Operator grant, actor/link and target binding,
canonical child payload digest parity, and reason-whitespace parity with the typed
command. QA also requested a rehashed source substitution and a final authorized
progress read after child acknowledgement. Documentation identified the adjacent
stale checker-retry availability label; CI integrity found no guard weakening.

The repair adds those SQL predicates and historical cause checks in AUTH. SQL
creation checks current active actor/grant/link; worker cause validation preserves
the accepted decision after later human grant revocation, while still requiring
its immutable system Operator/actor/link/target associations. Reason trimming uses
the explicit Python whitespace set and C0/DEL control exclusion rather than a
locale-dependent SQL character class. The observed repaired schema fingerprint is
`98e8a90037368efa975e8807d2191da466756e46421f89f114424c6a0d3694cf`
(`/tmp/t5-recovery-schema4.log`).

The composed test's existing raw SQL reason/nonexistent-decision probes move to
`test_recovery_sql_requires_exact_source_and_real_operator_cause`, alongside
source, payload-digest, absent/wrong grant, identity-link, target and Unicode-edge
reason forgeries. For relevant cases the test first inserts a self-consistent
forged allow-audit row with recomputed resource digest and proves that row exists
before attempting the forbidden child; a valid child is the positive control.
The original journey retains its denial/race/replay/revocation, single Submission
and dispatch, expired-original and stale-child assertions; it now loses the
child acknowledgement after T5 and verifies replay plus final contributor progress.
A shared real setup fixture keeps both tests cohesive, without adding test debt.
The repaired journey and both progress tests passed in `/tmp/t5-recovery6.log`
(**3 passed**); its SQL test first failed because the forged fixture copied the
old audit `entity_id`, so generic audit shape rejected it before the new guard.
The fixture now gives the forged audit its own matching id/entity id, without
changing any guard. The focused `/tmp/t5-recovery7.log` run passed (**1 passed**,
41.18s), exercising all nine SQL forgeries plus valid-child positive control;
isolated database/role cleanup completed for both runs. Ruff, structure and link
checks passed. Frozen repair review remains pending.

Frozen repair review on clean `852fbf326c25e828d9d408185e55fa994c122eee` passed
architecture/security, QA/test-delta, documentation and CI integrity. Reviewers
confirmed the three SQL findings and both QA proof gaps were closed; architecture
independently compared the explicit SQL whitespace set with Python's 29 whitespace
code points. Evidence remains the declared worktree runs, not an exact-head native
or public-API drill. Public operator routes, cleanup and single-request API/client
cutover remain required for the full goal.

## Checker image qualification caller repair

Current-head hosted run 43326850205 builds the PRE image but fails before its
first sample executes. Inspection found the sample request builder still emits
`prepared_generation_id`, superseded by the operation/source/lease PRE contract.
This shared consumer must migrate with the source-first contract; no compatibility
alias or production validator relaxation is allowed.

Bounded scope: `backend/scripts/checker_image_samples.py`, existing
`backend/tests/test_checker_image.py` proof, and this record. Acceptance: both PRE
and POST dry-run qualification construct valid canonical requests; PRE material
matches operation/source/lease and attempt identity; existing publication and
cleanup failure protections remain effective. Risk: architecture/contract caller
repair, no new authority or product state. Verification: reproduce the existing
two-phase regression before repair, run the complete checker-image suite, then
run the actual Terminal Systems PRE image. Required review: architecture and
QA/test delta, with human focus on synthetic identities versus real custody and
unchanged production validation. Cleanup implementation remains the next feature
boundary; this discovered integrated proof failure is repaired first.

The existing two-phase dry-run regression reproduced the exact failure before
repair (PRE failed, POST passed). After replacing the retired synthetic field
with matching operation/source/lease identities, the full existing
`tests/test_checker_image.py` suite passed: 25 tests in 14.25 seconds, captured in
`/tmp/submission-checker-image-repair.log`. Ruff and diff whitespace checks pass.
No test assertions, production validators, CI selection or permissions changed.
The actual image drill is separate evidence and must finish before qualification
is claimed. Latest fetch confirms zero commits missing from origin/main.

Architecture and QA/test-delta independently passed the clean caller repair at
4c101c6e7. Architecture also confirmed that mismatched material operation and the
retired identity field remain rejected. Commitrail validation passed.

Actual Docker qualification remains unproven: the first local attempt timed out
executing its first sample. A diagnostic rerun instrumenting command durations
(without changing repository code, deadlines, or sandbox settings) passed six
samples, then exhausted the 30-second budget during creation of the seventh.
Logs: `/tmp/submission-pre-image-repair.log` and
`/tmp/submission-pre-image-timing.log`. The second run also exposed a late-create
cleanup gap: despite immediate removal and absence observation, the Docker create
subsequently left owned container `workstream-image-test-41d80d4bd7e4485599d986bbc87da211`.
Its exact image/name were inspected and it was explicitly removed. This is an
unresolved image-runner cleanup obligation, not evidence of successful complete
qualification; it must be addressed without weakening deadlines. No AWS/native
runtime qualification or full current-head CI success is claimed.

## Image runner uncertain-create custody

Bounded scope: `backend/scripts/checker_image.py`, its existing test module, and
this record. Before a Docker create, persist the exact owned container name and
image in the existing private receipt. Keep create uncertainty distinct from a
confirmed created container; a failed create followed by empty LIST cannot close
that obligation. Persist confirmation only after acknowledged creation and scoped
removal/absence. This closes lost cleanup identity, not the Docker daemon's ability
to finish an outstanding request. Uncertain receipts require reconciliation of
the named container and remain failed; no automatic retry/publication is allowed.

Acceptance: the on-disk receipt exists before create; simulated late create after
an empty cleanup observation retains its exact name and unresolved state; a
successful sample ends with confirmed cleanup; cleanup failure retains an open
obligation. Existing deadlines, output bounds, isolation and publication guards
remain unchanged. Risk: runtime resource custody. Verification: existing full
image-runner suite plus focused late-create regression and actual image drill.
Reviewers: architecture and QA/test delta. Human focus: whether retained receipt
truthfully distinguishes request settlement from point-in-time absence. Do not
claim an automatic daemon reaper or native runtime qualification from this repair.

Verification: the final existing suite plus custody regression passed 26 tests
in 8.25 seconds (`/tmp/image-cleanup-custody-tests-final.log`). Loading the previous
script implementation in memory and running the new regression failed with the
missing `sample_cleanup` receipt (`/tmp/image-cleanup-prefixed-regression.log`);
no worktree replacement or test weakening was used. Ruff and diff checks pass.
The actual unchanged Terminal Systems PRE image passed all seven configured
positive/negative samples, with confirmed cleanup in receipt
`.checker-images/bd8859524a454b358ef56dd02586ce25/receipt.json`; full output is
`/tmp/image-cleanup-live.log`. This is local Docker compatibility evidence only,
not AWS/native Smol qualification or a complete public submission journey.

Review repair IMAGE-CLEANUP-DURABILITY-01: sync the receipt directory after its
atomic rename and sync output-directory ancestry before external calls. Added
injected directory-fsync failure cases at output creation and receipt publication;
both must prevent Docker create. Do not narrow durability to process visibility.

Adjacent hosted Agent Gates failure 43328703870 identifies unqualified technical
worker wording at developer-setup.md:153–154. Extend editorial scope only to those
two references, identifying them as Celery workers; retain the vocabulary gate
unchanged and rerun it. Documentation review covers this wording correction.

The directory-sync repair's first suite run had 24 passes and four sample-budget
failures: synchronous real filesystem fsync exceeded the fake Docker fixture's
one-second sample budget. The fixture now uses a 30-second sample deadline;
production limits are unchanged, injected timeout refusal and real process
0.2-second deadline tests remain. The repaired suite passes all 28 tests in
12.10 seconds (`/tmp/image-cleanup-sync-tests2.log`). Both directory-sync failure
boundaries forbid Docker creation. Ruff, stale authorization documentation and
Markdown link checks pass. Actual-image and structure rechecks are tracked
separately; the earlier seven-sample result does not attest these later edits.

Final repair evidence: architecture, QA/test-delta and documentation passed clean
e31200fc4. IMAGE-CLEANUP-DURABILITY-01 is closed. QA additionally disabled
`sync_directory` in memory and both injected-failure tests failed, confirming
they discriminate missing synchronization. No actual power-cut drill is claimed.
The post-sync actual Docker run passed all seven samples with confirmed cleanup
(`/tmp/image-cleanup-sync-live.log`, receipt
`.checker-images/5250510b3df74e588192121327ae6c3f/receipt.json`). Structure validation
passed (`/tmp/image-cleanup-sync-structure.log`), and Commitrail passed. An
unacknowledged daemon create remains an explicit unresolved receipt obligation;
this engineering command still does not supply an automatic daemon reaper.

## Source cleanup observation prerequisite

Existing adapters can request abort, but cannot confirm the exact multipart
handle's absence. Add a read-only `source_upload_parts_absent` capability to the
ArtifactStore interface, Local helper/adapter and S3 adapter; update existing
adapter conformance declarations and source tests. This observation is a necessary
input to the durable cleanup owner, never charge-release authority: it says
nothing about outstanding calls or an object produced by completion. Only exact
NoSuchUpload may confirm S3 handle absence; an empty successful ListParts keeps a
live handle unresolved, and bucket/access/transport errors fail closed. Local
abort currently retains bundle bytes, so it cannot be called reclaimed.

Allowed scope: those interface/adapters, existing Local/S3/conformance test
modules, and this record. No deletion, quota release, IAM broadening or public
route is introduced in this prerequisite. Acceptance: live empty and populated
handles remain unresolved; exact aborted handle confirms absence on real MinIO;
other handle remains untouched; malformed/foreign/provider failures never count
as absence; Local abort with retained bundle remains unresolved. Verification:
focused Local/MinIO behavior, existing conformance coverage, Ruff and structure.
Risk: storage cleanup proof boundary. Reviewers: architecture/security and
QA/test delta. Human focus: distinction between absence of multipart parts and
settlement of all writes/completed objects. The full cleanup owner, tombstones,
exact deletion and charge release remain required immediately after this port.

Place provider failure/namespace probes in existing selected
`backend/tests/artifacts/test_sealed_source_observation.py` alongside the current
exact-source observation proofs. This avoids growing the near-limit S3 test
module or introducing a new test lane; its existing MinIO selection is retained.

Extend the existing architecture proof's exact provider-method set for the new
observation and permit `ListParts` only inside that typed source method. Keep
all deletion/copy/global-list prohibitions and cross-owner call restrictions.
This requires the existing `backend/tests/test_artifact_architecture.py` file;
review includes CI integrity for this exact allowlist extension.

First isolated integration run: 89 passed, one Local fixture failure; database
and MinIO cleanup both completed (`/tmp/source-cleanup-observation.json`). Lost
initiation was injected after metadata publication but before staging-file
creation, so uploading into that fixture was invalid. Corrected it to assert
confirmed absent parts after abort; a separate successful-initiation test writes
real staging bytes and proves abort does not reclaim them. A direct focused run
passed the corrected initiation case but the other module's MinIO autouse fixture
used the wrong default port (9000), so that run is excluded from green evidence.
The full corrected run uses the isolated runner and explicit59043 endpoint.

Architecture tests passed48 cases (`/tmp/source-cleanup-architecture.log`);
structure validation and Ruff passed before the final small Local test repair.
The initial fixture edits overlapped the first integration run, so that receipt
is not frozen-head proof. The corrected run and final review establish the
candidate evidence separately; no cleanup or charge-release readiness is claimed.

Corrected observation run passed91 tests in31.71seconds with PostgreSQL and MinIO
cleanup complete (`/tmp/source-cleanup-observation2.log/json`). It launched at
base da3ff9dc1 with all final product edits present; committing8d5780f66 mid-run
changed no product files. This is worktree evidence, not exact-head launch proof.
Architecture/security, QA/test-delta and docs/CI-integrity passed clean8d5780f66.
Final structure validation passed (`/tmp/source-cleanup-structure-final.log`).

Hosted Agent Gates run43329967178 exposed an adjacent test-selector bug:
`test_backend_uv_cache_keeps_fresh_frozen_installs_and_exact_inputs` splits the
preflight job through `lanes`, accidentally including the newer independent
external-checker-runtime job and counting its installer twice. Extend scope to
that existing test's extraction delimiter only, ending at the actual next job.
Keep all exact installer/cache assertions and workflow files unchanged. Verify
all108 lightweight/stale-review tests; CI-integrity reviewer checks this repair.

The first targeted gate rerun (35 tests) exposed the same stale assumption in
workflow-wide totals after fixing job extraction. Include the actual fourth
installer/lock-check and third agents frozen sync in those exact totals, and
add explicit one-each/order assertions for the independent runtime job. The
three cached jobs' exact cache/install assertions remain unchanged. This is a
complete test-model correction for the existing fourth job, not permission to
skip or loosen installs. Run the workflow's complete six-module108-test command.

The complete gate run exposed the final outdated global assertion: `.venv` was
forbidden anywhere in the workflow, including the runtime job's legitimate
frozen interpreter path. Restrict that prohibition to every cache restore/save
step (the behavior this cache test owns), preserving the ban on cached virtual
environments. Correct the remaining preflight/save extraction boundaries too.
No workflow or production command changes. Earlier failed35/108-test runs remain
failed evidence; only the final rerun can establish the repair.

Final CI test repair: all 108 workflow-selected lightweight regression tests pass
(`/tmp/source-cleanup-agent-gates3.log`, 5.747 seconds). CI-integrity review passed
clean b41501f6c; an independent in-memory `.venv` cache-path injection still fails
the exact guard. No workflow file changed. Commitrail, stale authorization docs
and Markdown links passed. Hosted results for the next push remain unverified.
The next product boundary is the durable source cleanup claim/tombstone and
exact eligible deletion, followed by confirmed charge release; the observation
port by itself intentionally grants none of those operations.

## Durable sealed-source cleanup custody

Implement the next cleanup boundary in existing ART intake ownership: a retained
claim/tombstone for an exact sealed terminal source, generation-fenced retries,
and atomic confirmed charge release. Claim under existing TASK/operation locks;
require at least two hours since terminal/seal activity and reject every accepted,
retained, active or ambiguous source. Provider deletion will consume this exact
claim outside transactions; confirmation must compare the current generation.
Unsealed/uncertain upload reconciliation remains conservative until its outstanding
write obligations are resolved, and cannot use this sealed-source path.

Allowed scope: intake models/repository/capacity and cohesive cleanup owner/API,
next migration0078, canonical model/identifier/reset registries, existing custody
fixtures plus a selected cleanup test module, provider adapter integration and
architecture guards, this record. No accepted-evidence deletion, generic key-only
admin deletion, schema guard bypass in production, invented business/admin retry
capability or quota release on abort ACK. Risk L0: retention, resource accounting
and concurrency. Required reviews architecture/security, QA/test delta, and CI
integrity/docs for affected guards/evidence. Human review focus: exact target,
current ownership, retained-reference barriers, late writes, once-only release.
Acceptance: positive eligible cleanup plus recent/live/accepted/retained denial,
SQL forgery/immutability, stale claim and concurrent replay, uncertain delete
retains charge, confirmed absence releases once. Verify with real PostgreSQL and
Local/MinIO; any historical timestamp fixture is setup only, never a disabled
cleanup guard. Public cleanup scheduling/authority and orphan reconciliation
remain required for full feature completion.

Initial custody candidate: migration 0078 adds one operation-owned cleanup table,
its pending index, three cleanup functions/three triggers, extends the two existing
charge/accounting guards and three charge constraints. No retained rows are
rewritten. The fresh PostgreSQL migration completed; the observed schema fingerprint
is `8dd976d22e0ea2e8c65a0ee47f0bc418a6315ddb67786876b16afbf92eecad5e`.
The canonical expectation and model/reset/identifier registries are updated for
that intended delta; model parity is part of the real database test run.

The flush-only cleanup owner remains private and uncomposed. Its confirmation
inputs must come from the forthcoming trusted provider coordinator; they are not
public client assertions or a deletion capability. No scheduler, AUTH service
boundary, provider deletion or unsealed reclamation is claimed by this candidate.
Historical fixture aging is restricted to the isolated `workstream_test_` database
and restores the foreground immutability trigger in the same setup transaction;
cleanup/charge guards are never disabled. Positive owner accounting tests therefore
prove database custody, not external deletion. Add the stalled accepted denial
probe to the existing admission module that already owns its real AUTH/T4 fixture.

Ruff, initial structure, migration application and whitespace checks passed.
The first custody run began before two additional cleanup tests were added;
its collection/output and the final focused rerun will be reported distinctly.
Do not use that initial launch as frozen final test evidence.

Review repair batch: CLEANUP-LEASE-01 bounds cleanup leases to the existing
300-second durable delivery upper bound in Python and SQL; callers still supply
an explicit duration. QA's retained-reference gap led to a reachable generic
replica conflict test (same namespace/key, no source-operation pointer). Add a
retention-side guard for replicas/admissions, locking TASK/operation and refusing
new references once a cleanup claim exists; checking only at claim/confirm would
leave a deletion race. All matching operation identities are checked, including
ambiguous pointer/key combinations. These add one function and two triggers.
The repaired migration fingerprint observed on fresh PostgreSQL is
`9f3d2ac2ea97b956a262561e272aeb41ff7fdf03c9e0e265ad76da63ca3946eb`.

CI-CLEANUP-01 updates only shared semantic-family count274→275 and its exact
verified digest for the new cleanup module; independent fingerprint enforcement
remains. Initial static run:106 passed/1 failed, not a green run.
Initial database run:56 passed/2 failed in669.51seconds, cleanup complete. Both
new tests failed before cleanup claims because the isolated runner deliberately
removes server-admin credentials. Historical fixture setup now uses the restricted
role that owns only its asserted `workstream_test_` database, and drains deferred
checks before restoring the immutable-history trigger. No runner permissions or
credential exposure changes. The focused final run includes all new cleanup
cases, model parity, stalled accepted protection and existing T5 finalization.

Focused repair run:9 passed/1 failed in225.63seconds, database cleanup complete
(`/tmp/source-cleanup-custody2.log/json`). Stalled acceptance, both existing T5
cases, serial retention barriers and the other cleanup paths passed. The failure
occurred on a valid300-second claim: owner clock sample00:08:32.832117 preceded
a trigger sample00:08:32.354489, so resetting only claimed_at made the duration
appear overlong. Rebase both timestamps from one trigger sample while preserving
the requested interval; the SQL300-second constraint still rejects long spans.
A raw shifted-timestamp regression proves this correction. The new actual schema
fingerprint is `ea88b39d4ba01e345a6ea036184cda3194d1aa95f303555bad005243acde50ca`.

Add two-session races for both claim-first and retention-first, waiting for actual
`pg_blocking_pids` evidence before committing the winner and asserting rejection
of the loser. Lease-expiry tests likewise observe database time before takeover.
The separate admission-pointer trigger remains code-inspected rather than directly
race-tested; source acceptance/finalization protection is covered independently.
No full admission-retention or provider-cleanup qualification claim follows.

Final custody repair proof: all nine focused PostgreSQL tests passed in120.01
seconds (`/tmp/source-cleanup-custody3.log/json`), with database cleanup complete
and schema0078. This covers the shifted-timestamp regression, bounded leases,
exact target, atomic release/replay, live/unsealed refusal, retained key barrier,
both blocked two-session race orders and model parity. Launch metadata records
59783a1a5 with final worktree content; it is not exact-head launch evidence.
Architecture/security and QA/test-delta passed clean5cbb19c90; CI integrity passed.
The final passing result closes DOC-CLEANUP-CLOCK-01's premature wording concern.
Final structure and Commitrail checks passed. Earlier partial/red runs remain
separately recorded and are not relabeled green. Provider deletion, current cleanup
service authority, scheduling, unsealed reconciliation and direct admission-pointer
race proof remain required; the full goal is not complete.

## Cleanup service authority integration scope

The remaining concrete gap is that private cleanup custody cannot yet authorize
provider deletion. Extend the existing prepared ART service authorization with a
dedicated fixed cleanup identity/action/permission and exact operation, project,
task, source digest, claim ID/generation and claim/confirm phase facts. Then bind
claim and confirmation custody to those audited decisions before composing any
provider deletion. Allowed files are ACTORS service identity vocabulary, AUTH
catalogue/context/prepared/audit owners, ART API/authorization/cleanup owners,
required migrations and their focused tests/catalogues, plus this record.
Provider capability/adapters and composition may follow under this same scope
only with committed-claim validation and exact-generation retention protection.
No general delete-by-key route, human cleanup grant, retained-source deletion,
quota release from an acknowledgement, or AWS qualification claim is permitted.

Risk is L0 (authorization and deletion). Acceptance requires wrong/missing/revoked
service denial, exact fact/phase/generation binding, one-use transaction-bound
handles, audit target/digest proof, database enforcement of matching decisions,
and uncertainty retaining the charge. Run focused AUTH and cleanup PostgreSQL
proof, catalogue/boundary/lint/docs checks; review the frozen candidate through
architecture/security, QA/test-delta and affected docs/CI tracks. Human review
focus is authority-to-durable-claim continuity and retained-object exclusion.
This scope remains incomplete until the authority and provider composition are
proved; adding an action alone does not enable cleanup.

### Cleanup authority implementation checkpoint (not composed)

The dedicated cleanup service now has one exact action/permission, a strict
phase-bound resource context and an ART prepared-authorization adapter. Existing
binding and scheduler principals receive no cleanup membership. Audit targets
remain the submission operation/project and bind every cleanup fact by digest.
Migration 0079 extends only the actor service-identity constraint and the two
closed audit permission/action constraints; no retained row is rewritten.
The measured migrated schema fingerprint is
`c7cb5c74bf2ff569927f804af635572743c76b3cc2dd9ae376d348c72d3ae423`.
The kernel/prepared resource maps moved into the existing fixed-service guard
owner, sharing the common entries without changing the prepared subset. This
keeps both files within structural limits; the debt ledger only relocates the
unchanged 105-line kernel function, with its content hash preserved.

Evidence: `/tmp/source-cleanup-authority.log` had 7 passing and 3 failing tests
because the initial implementation lacked the database service-identity change.
`/tmp/source-cleanup-authority-schema2.log` measured the expected new fingerprint;
its runner metadata confirms database cleanup and Alembic 0079. An earlier schema
attempt launched before the migration file existed and ended with a head
mismatch; it is not positive evidence. After the migration and exact catalogue
count repairs, `/tmp/source-cleanup-authority2.log` passed all 17 selected tests
in 17.03 seconds, with database cleanup confirmed. The tests cover both phases,
all seven changed fact selectors, single consumption, exact audit digest and
missing/binding-only/revoked service denial, alongside existing finalization
proof. That run precedes the resource-map refactor; the refactor replay is
recorded separately when finished. Ruff, catalogue, Commitrail, stale AUTH docs
and Markdown link checks passed at their recorded worktree states.

This checkpoint does not yet require these decisions in cleanup claims or
confirmations, expose provider deletion, or provision a cleanup principal.
Database decision binding and provider composition remain required work under
the active full objective; no cleanup end-to-end completion is claimed.

The post-refactor replay `/tmp/source-cleanup-authority3.log` passed all 17 tests
in 28.71 seconds, with Alembic0079 and database cleanup confirmed in its JSON.
It launched at e66dd6457 with final worktree content and is scope-compatible,
not an exact-head launch receipt. Structure validation
`/tmp/source-cleanup-authority-structure2.log` exited zero. After fetching origin,
`git rev-list --count HEAD..origin/main` returned zero.
At frozen clean 482062fd5, architecture/security and QA/test-delta passed this
preparatory authority scope; CI integrity passed. Review independently compared
all seven existing resource mappings and the four-action prepared subset with
their predecessors, and the unchanged 105-line debt function. Documentation
found DOC-CLEANUP-AUTH-01: a current operations page had obsolete service counts.
The repair states the actual 22 identities, 21 action-bearing identities,
44 memberships and eight ART identities, names cleanup's sole action and keeps
uncomposed custody/provider work explicit. Review replay remains scoped to that
repair; the full objective remains active and incomplete.

Documentation replay closed DOC-CLEANUP-AUTH-01 at clean 5fe3443a5, independently
confirming the registry counts and incomplete cleanup-composition boundary.
No scoped review finding remains for the authority prerequisite. Durable claim
and confirmation decision enforcement is the next implementation step.

### Durable cleanup decision binding

Continue the declared L0 cleanup scope by requiring current fixed-service
resolution before locked custody/replay and consuming exact phase facts before
claim/takeover/confirmation mutations. Persist separate claim/confirmation audit
IDs; extend the database guard to validate action, principal, target and full
context digest. Existing retained claims are not rewritten: unaudited pending
claims must expire and be taken over with fresh authority; historical confirmed
tombstones remain immutable. Update the existing cleanup/custody tests and the
accepted-stall protection test to use real cleanup authorization. Prove denied
and substituted decisions cannot acquire cleanup custody or release charges,
while successful confirmation/replay, rollback, retention and lease protections
remain intact. Provider I/O remains the following required composition step.

The identifier inventory check exposed a stale classification from the earlier
checker-image PRE sample repair: its removed prepared-generation expression was
still listed while the new synthetic operation/lease expressions were not.
Repair only those exact entries in
`backend/scripts/identifier_generation_classifications.json`, preserving the
existing synthetic-protocol-fixture category and all production classifications.
The sample helper explicitly creates isolated wire envelopes, not product rows.
This is a branch regression repair, not permission to relax the identifier gate.

Durable cleanup authority evidence: migration0080 adds two nullable audit FKs
without backfilling authority, one exact audit validation function and a narrowly
extended existing cleanup trigger. The measured canonical schema is
`847165363b1b89c72011b450992ab83512f5984faa6def5e751eb019423b7370`
(`/tmp/source-cleanup-decisions-schema2.log/json`, migrated0080, cleanup true).
An earlier invocation ran from the repository root and failed importing the
migration helper; it supplies no schema evidence. Owner mutations obtain the
audit decision before dirtying the claim, so audit flushing cannot prematurely
publish an unaudited target. Live replay checks current service and the persisted
claim decision; preexisting unaudited pending claims require expiry/takeover.
Confirmed historical tombstones remain unchanged and protected.

`/tmp/source-cleanup-decisions.log` passed all 20 selected PostgreSQL tests in
332.14 seconds: cleanup authority substitutions (missing, phase, claim ID,
generation, source digest and task), revoked service at claim/confirmation/replay,
audit+claim/charge rollback, existing leases and both retention race orders,
model/schema parity and stalled accepted-source protection. Existing raw-SQL
charge release, source substitution and atomic confirmation proof remain: the
atomicity probe now supplies valid confirmation authority before intentionally
omitting charge release. Ruff and structure validation passed. Identifier
inventory initially failed on the three stale sample classifications noted above;
the precise repair passed (`/tmp/source-cleanup-decisions-inventory2.log`, 18.80s).
This worktree proof precedes its frozen review commit, not exact-head launch
proof. Provider deletion, settlement evidence and scheduling are still required.

Review at frozen2407d522b found CLEANUP-AUTH-RACE-01: unlocked service preflight
could become stale while replay waited for TASK custody. The new two-session
regression waits until the exact TASK holder blocks replay, commits identity-link
revocation, then releases custody. Both existing-claim and confirmed replay
failed before the fix (`/tmp/source-cleanup-replay-red.log`: 2 failed, 50.79s),
reproducing receipt return after revocation. The repair revalidates and locks
fresh actor/link facts after TASK/operation locks, matching prepared consumption
lock order and retaining those locks until the root transaction ends.
QA also requested wrong non-null confirmation decisions with a complete attempted
charge-release transaction. Added phase, generation and source-digest probes;
all must leave confirmation empty and charge unchanged. Replay proof is pending
for this repair; the prior 20-pass result does not prove the new race guard.

The repaired full cleanup module passed 23 tests in 336.82 seconds
(`/tmp/source-cleanup-decisions2.log/json`, Alembic0080, database cleanup true).
The receipt launched at2407d522b with final worktree content; it is not an
exact-head launch. Architecture/security and QA/test-delta replay passed frozen
clean4fa19c88b and closed the replay race and confirmation-proof findings.
Docs/CI replay found no gate or scope-claim defect. Structure validation2 and
shared Ruff/Commitrail/stale AUTH docs/Markdown checks passed. Provider deletion,
late-write/part settlement and scheduling remain unimplemented.

Hosted CI inspection of the previous pushed735f165b4 (PR merge execution
b083aa86e92a9b36ce306d27003a8d4202a6887d, Backend run43338819788) is NOT green:
- AUTH preflight fails the reflection gate at `vars(draft)` in foreground
  acceptance; replace it with explicit acceptance-field publication, not a gate
  exemption. Evidence `/tmp/submission-ci-auth-preflight.log`.
- Checker runtime stops at rustfmt differences in `src/smol/pre.rs` and
  `src/smol/pre/tests.rs`; no native runtime qualification result follows that
  failure. Evidence `/tmp/submission-ci-runtime.log`.
- CLI API contract run has 10 failures/15 passes: its permission catalogue still
  expects94 instead of95, and remaining old PRE callers use removed preparation
  facts or the removed `materialization` constructor argument. Evidence
  `/tmp/submission-ci-cli-api.log`.
- Task lifecycle C artifact has47 failures/259 passes, likewise identifying old
  PRE/retained-fixture consumers that require coordinated source-first cutover.
  Evidence `/tmp/submission-task-c-pytest.log`, downloaded exact lane artifact
  13999330936. Do not restore a parallel obsolete PRE implementation to hide them.
Repair bounded count/format/reflection regressions, then continue provider cleanup
and the already-required public/client/downstream cutover. No full-suite readiness
or merge request is implied by the focused cleanup proof.

### Bounded CI regression repair

Repair the observed preflight/runtime/catalogue failures before further cleanup
composition. Allowed changes: explicit accepted-evidence field publication in
ART foreground admission; CLI permission response validation and its HTTP/API
fixtures; MCP catalogue fixtures; the independent external API drill permission
oracle and tests; rustfmt on the two changed PRE Rust files; this record.
Preserve the full accepted decision/event/receipt transaction and all input
identity fields. Keep the closed permission count exact at95 and add only the
new cleanup permission to the drill oracle. Do not relax response validation,
module-boundary gates, tests or lanes, or restore the obsolete PRE flow.
Risk is L0 for acceptance atomicity and L1 for client catalogue/format fixes.
Verify boundary/structure checks, real PostgreSQL T4 acceptance and rollback,
CLI HTTP and real API catalogue behavior, MCP catalogue behavior, drill oracle
unit proof and cargo fmt. Review architecture/security and QA for acceptance,
docs/CI for unchanged gate and proof scope. Human review focus is the explicit
publication field set and unchanged authorization/OUTBOX atomicity. Native Smol
qualification and remaining old PRE consumers are outside this repair's proof.

Once reflection is removed, preflight reports two added private AUTH edges:
ART's authorization adapter imports the cleanup and finalization resource fact
models from AUTH's domain package. These are strict, immutable selector-only
models that the caller must construct; relocate their definitions into AUTH's
public API, update all internal and external consumers, and remove the superseded
domain files. This exposes the actual typed fact contract rather than adding a
private-module re-export or ledger exception. The same models, validation,
audit digests and authority checks remain; no executable capability is granted
by constructing values. Include the two moves and consumer imports in this
scope's architecture/security review and replay existing exact-authority tests.

Further gate inspection finds four private ART imports in the new finalization
adapter submodule. Move that actual composition into the canonical ART adapter
root, update OUTBOX and test callers, and remove the superseded submodule. This
uses the repository's existing owner-composition boundary and adds no ledger
entry. Include original/recovery finalizer composition tests in verification.
MCP's permission schema snapshot also still fixes94 and its closed enum omits
cleanup; regenerate that one transitive fragment from current backend OpenAPI,
retain the snapshot digest check, and verify the installed contract behavior.

The public API leak gate additionally identifies manifest validation importing
private ART implementations. Move the actual canonical manifest value, builder
and reported-manifest validator into `artifacts/api/submission_manifest.py`, and
pure path/inventory rules into the existing archive API. Keep ZIP I/O and change
policy private; update all affected consumers without compatibility re-exports.
Extract the existing digest-format validator into `core/hashing.py` and update
its consumers so public values do not depend on private source capabilities.
This scope includes those files and their existing tests. Preserve closed shape,
digest, normalization, collision, ancestry and resource-limit rejection behavior;
verify existing archive/manifest/change-gate and selected PRE contract tests,
plus the full boundary gate. Include this relocation in architecture/QA review.

The concrete manifest relocation clears the public-private leak stage. The full
boundary run now reaches `cyclic_public_dependency` (boundaries4 log). A direct
edge inventory identifies CHECKERS -> ART in `checkers/api/selected_pre_submit.py`
(source values, archive limits and manifest validation) and
`checkers/selected_pre_submit_coordination.py` (source custody port), against the
existing ART -> CHECKERS dependency. This requires a real consumer-port design
repair; the relocation alone does not establish a passing boundary gate.
Archive/manifest/change-gate regression run: 76 passed, 5 failed in 121.63s.
All five failures are preparation-deadline errors before inspection in the
scratch-backed archive tests; preserve the deadline and diagnose independently.
Evidence: `/tmp/submission-ci-repair-manifest.log`. No passing-suite claim.

The regenerated MCP permission snapshot and updated fixtures passed all 21
selected permission-list cases (210 deselected, 215.33s), including the three
previously failing schema/wire/revocation cases. Evidence:
`/tmp/submission-ci-repair-mcp-permissions.log`. This proves source-package
permission behavior only; installed-wheel API integration remains separate.

The unchanged single scratch-preparation case also fails independently with
`ArtifactPreparationDeadlineError` (1 failed, 28.67s;
`/tmp/submission-ci-repair-archive-deadline-probe.log`). Thus parallel pytest
contention alone is not an adequate explanation. Next diagnose preparation I/O
and compare the same case before relocation, preserving its ten-second bound.

Scratch diagnosis continued without changing production behavior or limits.
Temporary timing instrumentation outside the repository reproduced successful
preparation in 5.02s: 64 ledger writes, 61 reserve-byte calls; ledger writes took
3.46s. The test buffer is two bytes and the sample ZIP is 122 bytes. The same
five failing cases then passed unchanged (5 passed, 38 deselected, 36.61s;
`/tmp/submission-ci-repair-archive-preparation-replay.log`). Together these show
variable preparation I/O latency, not a demonstrated manifest-validation defect;
retain the original timeout failures as evidence rather than claiming reliable
full-suite passage. Cargo fmt --check passed for the Rust service.

Further dirty-worktree verification after the public contract relocations:
- Exact finalization/cleanup authorization module: 10 passed in 56.17s,
  Alembic0080, isolated database cleanup true
  (`/tmp/submission-ci-repair-authority.log/json`).
- Selected PRE derived-manifest, completed-evidence and default-blocker cases:
  17 passed, 69 deselected in 15.91s
  (`/tmp/submission-ci-repair-derived-manifest.log`).
- Test structure boundary validation and Ruff on all changed backend Python
  files passed; git diff --check passed.
These receipts validate their affected scope, not the unresolved dependency
cycle, obsolete PRE callers or public end-to-end behavior.

Architecture consultation confirms two explicit CHECKERS consumer boundaries:
pure source-contract validation and session-bound live custody. Keep actual
source and limits values ART-owned; do not move them into core/interfaces or
add parallel models. Thread pure validation explicitly through constructors,
canonical decoding and nested invocation receipts; missing decoder context must
fail closed. This consultation is not frozen candidate approval.
First implement the independent custody boundary: add CHECKERS' source guard
protocol, move exact source/lease/context comparison into an ART-owned guard,
compose it through ART's adapter root, and update coordinator callers and
existing source-substitution tests. Keep TASK-before-ART-before-CHECKERS order,
all compared fields, and current refusal category. Allowed files include those
two owners, adapter roots and the existing coordination test module. Risk L0;
verify live-custody substitution cases and historical refusal, then include real
PostgreSQL acceptance/recovery coverage in final review. Pure decoding remains
an explicit remaining edge, not hidden by this first step.

The custody-port step passed the existing exact live-source substitution,
lease-cap and historical-refusal cases: 12 passed, 74 deselected in 3.05s
(`/tmp/submission-ci-repair-source-guard.log`). The tests now exercise ART's
real comparison guard with controlled custody facts; every original comparison
is preserved. CHECKERS' coordinator no longer imports ART. The selected-PRE API
still imports ART for pure source/limits/manifest validation; the full dependency
cycle therefore remains open. The next implementation step must explicitly
thread pure validation through constructor/decoder and nested receipt paths;
consumer inventory is `/tmp/submission-source-codec-consumers.txt`. Architecture
consultation completed without edits and is not final candidate approval.

Pure-contract repair scope: add a small CHECKERS API declaring read-only source
and archive-limit views plus strict parsing/validation methods. ART implements
those methods with its existing source, archive and manifest definitions; only
ART's canonical adapter root constructs the implementation. The port carries
no session, credentials or provider read capability. Add a canonical body method
to the existing archive-limits value for exact JSON preservation. Then replace
CHECKERS' concrete ART dependencies and thread the port through affected owner
services, adapters, constructors and decoders. Existing substitution, resource
limit and canonical-wire tests remain the proof; add only missing port-boundary
failure cases. Never store the port in persisted facts, use a global codec,
weaken strict source typing or permit context-free JSON decoding. Allowed files
include the two owners' APIs/implementations, their adapter roots and traced
callers/tests. Risk remains L0; frozen architecture/security and QA review is
required after the complete call-path cutover, not for an unused interface alone.

Pure validation port and ART implementation added, preserving concrete owner
values and delegating canonical manifest validation to the existing implementation.
The port tests passed 11 cases (137 deselected, 29.44s;
`/tmp/submission-source-contract-port.log`): reject forged/non-owner source
objects, missing/extra/coercive/overflow limits, omitted canonical source fields,
wrong manifest digest, stricter entry limits and malformed manifest fields.
Ruff and diff whitespace checks passed. This is boundary implementation evidence,
not completed runtime wiring or a passing module DAG. Production decoding still
uses the original concrete imports until the coordinated signature cutover.
Call-path inventory identifies coordinator replay, retained-run reader, ART
admission recovery, checker external-service response decoding, and nested
receipt decoding/validate_lease as required consumers. Do not wire only the
foreground constructor and leave historical or replay paths unvalidated.

The pure port is now explicitly threaded through CHECKERS source/execution
constructors (keyword-only InitVar, excluded from retained dataclass fields),
canonical decoders, derivation and nested receipt validation. Runtime-profile
JSON parsing requires an explicit owner context and preserves existing limits
serialization. Coordinator, retained reader, processor and socket transport get
the dependency through composition; ART callers use their owner implementation.
Pydantic also traverses these dataclasses inside AUTH resource values, requiring
explicit structural-view validation hooks; no arbitrary source decoding fallback
was added. Direct and fixture callers were updated together.
The first focused run after schema-hook repair passed87/failed1 because one
`dataclasses.replace` test omitted the required InitVar. After fixing that caller
and adding missing-context/non-retention tests, all90 selected cases passed
(34 deselected, 18.42s; `/tmp/submission-source-codec-wiring3.log`). The earlier
full module-boundary run passed (`/tmp/submission-ci-repair-boundaries5.log`),
and a repeat after complete wiring is underway. PostgreSQL T4, structure and
OpenAPI verification remain pending; no final frozen review or commit yet.

Complete call-path inspection also includes the separate trusted guest entry
point and portable guest/service drills under `external_checkers/`. Update their
manifest imports and explicit pure-validator construction with the backend
callers. The guest already composes the private ZIP inspector and default checker;
it constructs ART's pure validator at that application boundary without pulling
API/session adapter roots into execution. Include these paths in architecture
review; a backend-only import scan does not prove the guest is wired.
The first T4 replay stopped during collection on the missed guest manifest import;
that import and the guest's decoder/derivation calls are repaired. No T4 pass is
claimed for that run. A direct old-HEAD/new-profile wire comparison then exposed
integer versus float inspection-second serialization. Preserve Pydantic's prior
float output in the existing limits canonical projection; the corrected comparison
passes for integer, fractional and default seconds
(`/tmp/submission-profile-wire-compare.log`). Added a focused wire-representation
regression. Current repeated full module-boundary and structure gates passed;
OpenAPI generation succeeded (822091-byte document). T4 and portable worker
verification are still running, and candidate review remains pending.

Portable guest PRE proof passed19 cases (27 deselected, 18.68s;
`/tmp/submission-source-codec-worker.log`). The combined source/receipt/port/wire
regression selection passed105 cases (168 deselected, 25.32s;
`/tmp/submission-source-codec-final-pure.log`). This includes the owner-context
requirement, omission of the InitVar from retained request fields and the prior
float serialization representation. The original failed T4 collection run did
clean its isolated database; its metadata is not a pass receipt. The repaired
T4 replay remains in progress under `/tmp/submission-source-codec-t4-replay.*`.

The CI-repair implementation is being frozen as a review candidate after passing
module-boundary, structure, Ruff, OpenAPI and documentation checks, 105 focused
source/receipt cases and 19 portable PRE-worker cases. Latest fetched main is
94334ccf4 with zero missing upstream commits. PostgreSQL T4 replay is still live;
original/recovery finalizer composition tests and frozen architecture/security,
QA/test-delta and docs/CI reviews remain required before pushing this repair.
This candidate commit does not mark the full submission initiative complete or
the single draft PR ready. The public API/client/downstream/cleanup/provider
work listed in the implementation snapshot remains in scope.

### CI repair proof closure

Frozen implementation8f7e5eae3 has these completed receipts:
- Source/receipt/manifest/port/wire selection:105 passed,168 deselected,54.22s;
  `/tmp/submission-source-codec-frozen-pure.log` and `.head` bind the exact commit.
- Atomic acceptance/rollback/concurrent replay:12 passed,27 deselected,580.68s;
  `/tmp/submission-source-codec-frozen-t4.log/json` binds that commit, Alembic0080
  and completed isolated database cleanup.
- Original finalization and Operator/lost-ack recovery:5 passed,34 deselected,
  460.51s; `/tmp/submission-source-codec-finalization.log/json` has the same
  exact-commit/database custody. This proves retained Submission/POST dispatch
  composition, not the entire governed contribution journey.
- Installed MCP wheel/public-API access-read parity on Python3.12.13:1 passed,
  100.39s; `/tmp/submission-mcp-wheel-py312.log/json` binds the exact commit and
  database cleanup. `/tmp/submission-mcp-py312-provenance.json` records the
  isolated site-packages path and wheel SHA256
  35f1574d1649e2d72d8c329613f8d1a95552b37b3e54d9c9cc830ee44981afe0.

Pure selection command (backend cwd): pytest
`tests/checkers/external/test_selected_pre_submit_coordination.py`
`tests/checkers/external/test_pre_invocation.py`
`tests/artifacts/test_submission_intake_contracts.py`
`tests/test_submission_manifest.py`, with `-k 'source_first or historical_pre_values or receipt or invocation or completed_worker or source_validation_dependency or source_profile_preserves or checker_source_contracts or checker_manifest_port' -q --tb=short`.
T4/T5 used `scripts/run_isolated_tests.py` on
`tests/artifacts/test_submission_intake_admission.py`, respectively `-k t4` and
`-k 't5_finalizes or operator_recovers_same or finalization_outbox_recovers'`.
The wheel proof used the same isolated runner with MCP's test interpreter on
`mcp_server/tests/integration/test_access_reads.py` and the separately installed
wheel executable. A temporary diagnostic plugin only enabled API faulthandler
and copied subprocess logs before fixture cleanup; assertions were unchanged.

The initial wheel attempt failed before API readiness with backend process
SIGSEGV; its temporary logs had already been removed. A diagnostic replay passed,
but its accidentally selected Python3.14 wheel environment is excluded from the
supported-runtime claim. The explicit Python3.12 replay above passed. The first
startup crash is unreproduced and unroot-caused, not silently declared fixed.
Keep its `/tmp/submission-mcp-wheel-parity.log/json` failure and later captured
subprocess diagnostics as an outstanding stability observation for full CI.

ARCH/SEC and QA/test-delta reviewers independently closed PASS on clean8f7e5eae3
once exact-commit T4/T5/pure receipts were available. Both inspected the relevant
unchanged owners; adversarial probes rejected forged source facts and detected
restoring the integer-seconds serialization defect. Documentation/CI review
passed with no gate suppression or snapshot mismatch. No code changes followed
those reviews. The earlier19-case portable worker proof does not qualify native
Smol or AWS. Main was fetched at94334ccf4 with zero missing commits.

This closes only the bounded CI-repair implementation. Full hosted CI, existing
obsolete PRE consumers, provider cleanup/qualification, public API/client cutover,
revision/contribution journeys and the specification acceptance audit remain.
Keep the single PR draft; no merge or complete-initiative claim is authorized.

## Exact-generation provider cleanup implementation scope

The remaining concrete gap is physical removal after the existing audited,
committed cleanup claim. Implement exact Local and S3 generation removal and
compose it with claim/confirmation outside database transactions. Preserve the
separate cleanup capability/credentials requirement; never expose a general
administrative delete-by-key path or treat provider acknowledgement as settlement.

Allowed files: existing ART source adapters and their composition root, typed
artifact provider/cleanup contracts, ART cleanup owner/coordinator, required
configuration and provider qualification owners, existing source/cleanup tests
and their lane registration if needed, and this record. Begin with the private
Local primitive and its regression proof; it grants no authority and is not a
public deletion endpoint. The coordinator must validate a committed audited claim
before invoking any deletion capability.

Prohibited: retained/accepted generation deletion, upload-role deletion authority,
charge release on timeout/abort acknowledgement, broad bucket deletion, provider
qualification claims without live proof, gate weakening and unrelated cleanup.
Acceptance: exact source generation only; durable tombstone before unlink; replay
and crash recovery preserve ownership; changed inode/source refuses deletion;
provider I/O outside database locks; current audited claim and confirmation;
separate credentials; uncertain object/part/writer outcomes retain charges.
Risk: L0. Verify Local failure/replay/substitution cases, real MinIO VersionId
isolation, PostgreSQL claim/confirmation and accepted-retention races, applicable
boundary/lint/docs gates, then architecture/security, QA/test-delta and docs/CI
review of the frozen candidate. Human review focus is deletion authority,
retention barriers, late writes and conservative accounting. Full public cutover,
worker deployment and complete acceptance audit remain part of the same PR.

Local primitive worktree evidence (base f0d40a199): full existing Local storage
suite plus five cleanup cases passed, 64 tests in 19.93s
(`/tmp/submission-local-cleanup.log`). Cases exercise normal/repeated cleanup,
interruption before and after unlink, retained provenance/reinitialization,
late begin/part refusal and missing/replaced-generation rejection. Initial new
test execution failed three cases due to a missing exception import; fixed the
import before the full run. Ruff for both changed Python files and diff whitespace
checks passed. This is private primitive proof only: no composed authority,
provider settlement, S3 deletion or end-to-end cleanup claim is made. Candidate
review remains pending until the bounded cleanup integration is assembled.

Cleanup coordinator worktree progress: the owner now recovers the immutable upload
under a live exact audited claim; root composition commits before invoking the
separate provider capability and confirms only an exact-source observation with
all three settlement facts. A confirmed replay performs no provider call.
Local cleanup validates the upload before deletion and observes the retained
source tombstone for part settlement. No deletion method was added to the upload
ArtifactStore interface.

Verification: four isolated PostgreSQL coordinator cases passed in46.74s
(`/tmp/submission-cleanup-execution-replay.log/json`, Alembic0080, database cleanup
complete). A separate connection obtains TASK/operation locks during provider I/O
and reads the committed claim. Unsettled writes, substituted source and provider
exception retain the charge; exact settled replay invokes the provider once.
The initial four-case run failed on an incorrect test SQL table name (`tasks`);
corrected to the inspected `workstream_tasks`. The test charge oracle was also
corrected to the existing state/accounted_bytes columns before replay. Local full
suite passed65 tests in37.26s (`/tmp/submission-local-cleanup-full.log`); six focused
cleanup cases passed in4.60s. Ruff passed for all current Python changes. These
are dirty-worktree results, not frozen-candidate review. S3 scoped deletion,
separate credentials, scheduler and unsealed/uncertain reconciliation remain open.

Combined PostgreSQL/Local proof passed: one test in34.26s
(`/tmp/submission-cleanup-local-db.log/json`,0080, database cleanup complete).
The test writes actual Local bytes through durable initiation/EOF/seal custody,
terminalizes, ages only fixture history (preserving the actual provider upload
deadline), invokes audited cleanup, observes removal and retained tombstone,
verifies zero accounted bytes and replays the confirmed operation. This proves
the internal Local cleanup composition, not public submission or S3 deployment.
Current module-boundary gate also passed
(`/tmp/submission-cleanup-boundaries-current.log`).

S3 deletion primitive progress: private cleanup capability checks the exact sealed
upload handle, refuses unresolved multipart handles, deletes only the supplied
VersionId and separately observes absence. HEAD's generic404 requires a successful
bucket observation; missing bucket/denied access is not confirmed absence. After
deletion, any remaining version/delete marker keeps writes unsettled and therefore
retains the charge. The source capability AWS qualification guard remains intact.
The constructor currently requires a cleanup store by contract; production
construction and proof of separate credentials are still unimplemented. Tests use
administrative MinIO credentials and do not qualify role isolation or AWS.

Real MinIO protocol proof: five version-isolation/lost-delete-acknowledgement/
unresolved-upload cases passed in21.45s
(`/tmp/submission-s3-cleanup-versions.log`). Includes no-newer-version settlement,
newer-version preservation with conservative charge outcome, and replay after a
successful deletion whose response timed out. Four denied/missing-bucket HEAD
counterprobes passed in8.41s (`/tmp/submission-s3-cleanup-absence.log`). The initial
three protocol cases passed before review identified the remaining-version
settlement gap; current five cases supersede that narrower claim. Ruff and diff
whitespace checks passed. These results belong to the uncommitted worktree;
frozen-candidate reviews remain pending for the complete cleanup integration.

Cleanup provider construction now follows the typed ExternalServiceAdapterFactory
contract with explicit Local/S3 registration. It constructs its own store from
the cleanup worker's redacted Settings and requires the existing exact namespace
claim. MinIO construction rejects the upload access-key identity; native AWS
construction fails closed pending source-cleanup role qualification. The upload
process receives no new deletion method or cleanup credential setting. Separate
worker startup/scheduling still needs composition.

Restricted MinIO principal investigation: the first live STS-session test passed
upload and negative-role checks but failed version deletion with only
DeleteObjectVersion. The server's DeleteObject handler checks DeleteObject as
well (upstream source: https://github.com/minio/minio/blob/master/cmd/auth-handler.go).
A discriminating replay added a VersionId condition, but this build rejected that
condition as invalid during STS issuance. The current test therefore uses a
prefix-scoped MinIO DeleteObject grant, retains upload-deletion and cleanup-upload
denials, and checks out-of-prefix deletion denial. This is principal/prefix proof,
not IAM-level version-only deletion proof. Exact-version calls remain enforced by
the adapter and verified by the existing call-capture tests; retained-source
protection remains the audited ART gate as required by specification17.5. Do not
transfer this MinIO policy assumption to AWS qualification. Both failed evidence
logs are retained at `/tmp/submission-s3-cleanup-principals.log` and
`/tmp/submission-s3-cleanup-principals-replay.log`.

Restricted-principal proof now passes (1 test,14.86s;
`/tmp/submission-s3-cleanup-principals-final.log`). Distinct short-lived MinIO STS
sessions have separate upload versus cleanup policies. Real upload succeeds;
upload-principal version deletion, cleanup-principal upload and out-of-prefix
cleanup deletion are denied. The exact-version cleanup succeeds. Factory reuse of
the upload principal and a mismatched namespace claim are rejected. A test oracle
initially expected ArtifactConfigurationError for the latter, but the shared
factory intentionally wraps constructor failures in ExternalServiceConfigurationError;
the corrected oracle preserves that existing error contract.

The combined prior S3 run reported9 passed/1 failed and then exited139
(`/tmp/submission-s3-cleanup-all.log`). The process-level crash remains unexplained;
the focused replay with PYTHONFAULTHANDLER=1 exited0. Do not represent that replay
as a root-cause fix for process stability. Current lint, whitespace and module
boundary checks pass (`/tmp/submission-cleanup-factory-boundaries.log`). The full
PostgreSQL cleanup suite is still under verification; no frozen-candidate or full
initiative completion claim is made.

Current-head hosted CI correction scope: f0d40a199's image-proof job exposes a
missed manifest-owner import in experiments/pilot04_external_checker_runtime/run_probe.py.
Auth preflight reports behavior_ownership_error:partition_target_mismatch; local
inventory identifies22 missing tracked targets and no stale targets. Allow the
probe's canonical import correction, additive partition registration for delivered
owners/new cleanup files and existing behavior-ownership verification. Do not
change protected ownership, drop assertions or relax gates. External runtime also
has five obsolete prepared-PRE fixture failures (main.rs:3350); retain as pending
source-first caller cutover, never restore the obsolete implementation to pass.
Artifacts: `/tmp/submission-f0-ci-image.log`, `-preflight.log`, `-runtime.log` and
`-shared-a.log`. Full hosted CI remains failing; sampled database constraint log
messages alone are not classified as defects because many are expected negative
assertions. Lane-bundle pytest reports still need inspection.
The additive ownership repair also updates the explicit SUBMISSION_INTAKE_TARGETS
set in backend/scripts/behavior_ownership.py and its existing exact-set test in
backend/tests/test_behavior_ownership.py. Register24 concrete paths (22 previously
missing plus the new cleanup capability/coordinator). Preserve existing assignments,
protected base, digest validation and rejection of removed or unrelated targets.

Hosted-CI corrective verification: the canonical import repair passed all17
scripts.test_public_hosted_attachment tests in40.388s
(`/tmp/submission-probe-import-repair.log`). Additive ownership registration passed
all170 test_behavior_ownership tests in7.89s
(`/tmp/submission-cleanup-ownership-tests.log`), validated690 targets against
origin/main and passed Ruff. Existing assignments and protected base are unchanged;
only the24 named missing additions and canonical digest were added. This closes
the reproduced import/partition defects locally, not the other hosted CI failures.

Full cleanup suite result:28 tests passed,1 teardown error in439.87s
(`/tmp/submission-cleanup-full-db.log/json`,0080, runner database cleanup complete).
The error followed test_confirmation_rejects_wrong_decision_even_with_atomic_release[source]
in clean_postgres_database -> _verify_test_database_schema -> canonical schema
inventory: asyncpg text decoding raised UnicodeDecodeError (byte0x90 at position145).
The test assertions passed; this is not a passing full-suite result. The original
isolated database was removed, so do not claim its wire bytes were recovered.
An exact-case replay with PYTHONFAULTHANDLER=1 and PYTHONMALLOC=debug is the next
native-runtime diagnostic; no fixture/gate/assertion was weakened. Process139
observations remain independently unresolved. Full behavior_ownership validate
also passed after additive partition correction.

The exact teardown case replay passed in17.60s with both native diagnostics enabled
(`/tmp/submission-cleanup-teardown-diagnostic.log/json`,0080, database cleanup
complete). The earlier UnicodeDecodeError is unreproduced, not root-caused or
fixed. Review must preserve that limitation rather than combine these runs into a
fabricated clean full-suite receipt. All28 original test assertions passed in the
full run; its independent teardown gate did not. Sealed cleanup is ready for
bounded code review; the complete initiative, full hosted CI, unsealed cleanup,
scheduling and public cutover remain unfinished.

## Frozen sealed-cleanup proof and review closure

Implementation target:4de63467b272b8915427f447daff13f949241969, base and merge base
f0d40a1998b38df5cbdbb48eb69e7e36b05e80ee. All14 paths were frozen clean throughout
these executions and review snapshots. origin/main was fetched again; this branch
has zero missing main commits. No merge readiness is claimed.

All three frozen commands used backend/.venv Python3.12.13 with
PYTHONFAULTHANDLER=1 and PYTHONMALLOC=debug. PostgreSQL used the restricted isolated
runner against the owned local test server; S3 used the owned local MinIO endpoint.

- Full PostgreSQL cleanup suite:28 passed in340.97s, exit0. Command from backend:
  `.venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/submission-cleanup-frozen-db.json -- .venv/bin/python -m pytest tests/artifacts/test_submission_source_cleanup.py -q --tb=short`.
  `/tmp/submission-cleanup-frozen-db.log/json/head` records exact4de, Alembic0080
  and completed database cleanup, including teardown.
- Full Local store suite:65 passed in42.81s, exit0. Command:
  `.venv/bin/python -m pytest tests/test_local_artifact_store.py -q --tb=short`.
  Artifact: `/tmp/submission-cleanup-frozen-local.log`.
- S3 cleanup suite:10 passed,47 deselected in42.84s, exit0. Command:
  `.venv/bin/python -m pytest tests/test_s3_artifact_store.py -k source_cleanup -q --tb=short`.
  Artifact: `/tmp/submission-cleanup-frozen-s3.log`.
- `/tmp/submission-cleanup-frozen-provenance.json` records the clean implementation
  head, Python interpreter, diagnostic settings and MinIO image digest
  sha256:1033251d858d3f89f14d9e095e8dd0c8ada3360124ab33cca994655e579fdbf6.

Required bounded reviews closed on that unchanged target:

- Architecture/security:PASS, including authority before provider I/O, exact
  generation/tombstone custody and atomic audited confirmation.
- QA/test_delta:PASS WITH LOW RISKS, no findings or repairs. Exact frozen receipts
  close previously provisional runtime rows. The in-memory omitted-tombstone
  mutant fails the intended before-unlink assertion; repository stays unchanged.
- Documentation/CI integrity:PASS. Independent partition comparison preserves all666
  prior assignments/protected base and adds only24 exact paths. Recomputed-digest
  mutants that remove/reassign prior targets, add unrelated targets or alter the
  protected base are rejected. Actual CI selection remains full suite/all lanes.

The earlier exit139 and UTF-8 schema-inventory teardown error remain unexplained.
This clean frozen replay does not erase those failures or claim a root-cause fix.
MinIO principal/prefix separation and adapter VersionId enforcement do not qualify
AWS or IAM-level version-only deletion. Worker startup/scheduling, unsealed and
uncertain reconciliation, public API/CLI/MCP cutover, downstream journeys, remaining
hosted-CI failures, deployment values and complete A01–A35 proof remain required in
this same PR before readiness. The full thread goal stays active and incomplete.

## Coordinated public submission cutover scope

The next gap is the public journey: internal T1/upload/PRE/T4 owners exist, while
API/CLI/MCP still expose preparation followed by admission-consuming creation.
Reuse those owners and replace that obsolete public contract together. Begin with
strict request parsing, then compose foreground execution, authorized operation
reads and clients. Do not expose a second supported mutation or restore obsolete
prepared-PRE interfaces merely to satisfy old fixtures.

Allowed: backend/app/api/submission_intake.py and existing artifact/task routes;
ART public intake/command contracts and private foreground orchestration; canonical
ART/TASK/CHECKERS adapter roots and narrow read/continuation owner ports; required
Settings transport/resource profiles; existing backend submission/API/fixture tests;
cli/internal/api/submission*.go, cli/internal/command/submission.go and affected CLI
tests; mcp_server/workstream_mcp task-execution schemas/tools/gateway, corresponding
contracts/tests; affected OpenAPI/catalogue/docs and exact CI ownership registration.
The Rust/guest obsolete PRE consumers and fixtures are within the same source-first
cutover scope where required by real execution. Each repair retains its named
behavior proof; no policy or assertion is discarded just to make CI pass.

Prohibited: unaudited handoff, database locks across provider I/O, renamed legacy
aliases, client-supplied authority/checksums, implicit background PRE, fabricated
Submission IDs before T5, changed review/revision policy, default deployment values
for unresolved C01–C07, new paid provider selection or retained-data deletion.
Acceptance: exactly one raw-ZIP submission mutation, strict duplicate/framing/
packet validation before body consumption, actor-key replay, stable post-T4 receipt,
correct cancellation/unknown-outcome handling, owner-backed progress, coordinated
CLI/MCP upload/replay/revision behavior and removal of superseded public paths.
Risk:L0. Verify header refusal without reading body, real PostgreSQL/Local and
MinIO command/acceptance paths, public HTTP and CLI/MCP contract journeys, durable
continuation and all governed downstream branches, plus full relevant CI gates.
Required reviews:architecture/security, QA/test_delta and documentation/CI integrity;
human focus is authority, exact identity, transport limits, retained lineage and
truthful client progress. Full unsealed cleanup/scheduling/provider qualification
and the complete acceptance/deployment audit remain required before PR readiness.

### Public request parsing worktree proof

Added strict HTTP parsing in backend/app/api/submission_intake.py and proof in
existing backend/tests/test_api_controls.py. Reject duplicate packet/selector and
framing headers, conflicting length/transfer framing, unsupported media/encoding,
invalid UUID/packet/revision values and excessive declared length before consuming
the body. Preserve exact packet text, empty omission semantics, valid revision
acknowledgements and the permitted declared-byte boundary using canonical ART
metadata validation.

The complete API-controls module passed:43 tests in40.10s, run from backend with
`.venv/bin/python -m pytest tests/test_api_controls.py -q --tb=short`.
Ruff passed for both changed Python files. This is uncommitted worktree evidence,
not frozen-commit or public journey proof. The parser remains unwired; command and
route composition, clients, ownership registration and reviews remain pending.
Inspection confirms obsolete preparation orchestration still calls replaced PRE
builder signatures; remove that path during coordinated cutover rather than
restore superseded signatures. The full goal remains active and incomplete.

### Public command owner composition progress

ForegroundIntakeAdmission now owns reserve_pre: lock the original operation and
lease, recheck contributor authority and locked context, bind exact sealed source
and retained predecessor facts, and commit CHECKERS reservation before execution.
The shared acceptance fixture now uses this owner instead of privately rebuilding
T3. Actor/key replay now includes the stable accepted receipt only after its
existing authorization and database evidence validation; matching replay bytes
remain required before returning that result to the command caller.

Worktree verification on the unchanged Python implementation: six PostgreSQL tests
passed in142.03s, covering T4 receipt replay, three source/owner substitutions and
both revocation orders. Command from backend used PYTHONFAULTHANDLER=1,
PYTHONMALLOC=debug and the owned PostgreSQL55440 isolated runner:
`.venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/submission-public-t3-db.json -- .venv/bin/python -m pytest tests/artifacts/test_submission_intake_admission.py -k 't3_reservation or t4_accepts_exact_source_and_replays_one_receipt or t4_revocation_blocks' -q --tb=short`.
Log:/tmp/submission-public-t3-db.log; metadata confirms0080 and complete database
cleanup. These are worktree receipts; tree_sha identifies the parent commit and
must not be represented as a clean committed candidate. Earlier actor/key replay
selection also passed2 tests. Ruff and module-boundary validation passed.

Registered exactly backend/app/api/submission_intake.py in the existing explicit
CI addition set and partition. Preserved all690 previous assignments and protected
base; new total691. Exact-addition regression passed and full ownership validation
passed. No CI lane was narrowed. The complete API-controls proof remains43passed.

Public command orchestration, lifecycle failure terminalization, HTTP wiring,
client cutover, revision-path integration and full acceptance proof remain pending.
This intermediate commit is part of the same PR, not a merge checkpoint. Focused
architecture/security, QA and docs/CI review remains required before claiming this
public cutover stage complete. The full goal stays active.

### Foreground command composition implementation

The coordinated cutover now composes existing admission/upload/lease/PRE/T4
owners in intake/foreground_command.py. Explicit transport/runtime values are
injected; no production defaults or provider qualification are introduced.
Accepted actor/key replays discard/hash bytes and return the original receipt.
Known failed foreground work is terminalized only after the lease runner drains
its child tasks. Accepted, expired or superseded ownership cannot be overwritten.
Unknown acceptance or terminalization commit outcomes remain unresolved for
same-key observation instead of inviting new work. Physical charges stay retained.

QC rejection replay uses CHECKERS' retained source-operation terminal evidence,
with fresh ART read authority, original packet/key/source comparison and existing
bounded public findings. This reuses immutable stored evidence rather than create
another findings copy. Read authorization commits before returning QC feedback.
The command remains private and unwired pending HTTP composition/client cutover.

Initial integration attempts found two test composition mistakes: missing TASK
context port, then a Local store root differing from the registered namespace.
Both were corrected without weakening custody checks. Logs remain at
/tmp/submission-foreground-command-db.log and
/tmp/submission-foreground-command-full-db.log. Neither run is passing evidence.
The corrected five-scenario run uses /tmp/submission-foreground-command-corrected-db.log/json;
its result is pending at this record entry. Scenarios are acceptance/replay,
infrastructure-failure replay, unsafe-ZIP QC rejection/replay, cancellation and
unknown accepted-response replay. Portable worker execution is not native Smol.

CI registration adds only intake/foreground_command.py, preserving all691 existing
assignments and protected base. Full ownership validation and exact-addition test
passed. Required specialist review, upload-timeout HTTP classification, deployment
configuration/readiness, public routes, clients and full end-to-end proof remain.

The corrected command selection passed5 tests in83.45s with database cleanup
complete. Test-structure validation then identified admission-suite growth above
1200 lines. Moved the three new command test functions and the committed T3
substitution function into tests/artifacts/test_submission_foreground_command.py.
The T3 function AST, including decorators and every assertion, is identical to
87d8cbafb; this is relocation, not weakened/decomposed behavior. The relocated
module passed all8 parameterized cases in188.95s, isolated PostgreSQL0080 cleanup
complete (/tmp/submission-foreground-final-db.log/json). Runtime implementation
was unchanged for those eight scenarios; a later added upload-timeout classification
has its own supplemental regression, currently pending.

Upload/replay deadline expiration now has a distinct typed streaming exception,
normalized by the command to submission_upload_timeout. Existing deadline/drain
assertions now require that type. The complete intake-contract suite passed113
in9.02s (/tmp/submission-foreground-contracts.log). The dedicated database timeout
case uses /tmp/submission-foreground-timeout-db.log/json and remains pending here.

Structure validation passes after relocation. The new module remains in the
shared-foundations family; independent hashing confirmed exactly the previous275
members plus the new module before updating the276-member fingerprint. All59 CI
lane catalogue tests passed in6.59s. Ownership validation/exact-addition proof,
module boundaries, Ruff, Commitrail records, markdown links and diff checks passed.
These are scoped worktree receipts, not full CI or public end-to-end readiness.

### Frozen command proof and mixed-case header review repair

Frozen implementation b2d7dd325ff41643dd0f898f53f80596b0da480f remained clean
through the required review snapshots and final root suites. PostgreSQL command
module:9passed186.81s, exit0, exacthead/Alembic0080/database cleanup complete
(/tmp/submission-foreground-frozen-db.log/json). Combined intake contracts and
API-controls:156passed71.30s, exit0 (/tmp/submission-foreground-frozen-pure.log).
Both used backend/.venv Python with PYTHONFAULTHANDLER=1 and PYTHONMALLOC=debug.
The earlier supplemental timeout case passed1 in39.07s with cleanup complete.
Origin/main was fetched again and this branch has zero missing main commits.

Documentation/CI integrity review passed the250d8af70..b2d7dd325 delta, including
independent partition/lane preservation, AST relocation and adversarial mutations
(/tmp/submission-foreground-docs-ci-adversarial.json). Architecture/security and
QA/test_delta identified one shared Medium finding: Starlette getlist did not
count differently cased raw ASGI header names. They found no second material
command/retained-read defect; local duplication of retained decode validation
was assessed as optional simplification, not a bypass. QA's lowercase-guard
mutant failed the expected assertion; controlled retained-terminal substitutions
were rejected. Those controlled probes are not PostgreSQL custody proof.

Repair counts and selects from one raw-name-lowercased Headers collection,
preserving exact value bytes. Twelve new regression cases first failed against
b2d7dd325 (/tmp/submission-header-casefold-before.log): eleven valid-control
mixed-case duplicates were accepted and a single uppercase-name packet was
incorrectly rejected. Full API-controls after repair:55passed23.73s, exit0
(/tmp/submission-header-casefold-after.log); Ruff/diff checks passed. This parser
repair changes no command/runtime/DB owner. Affected review replay remains pending
at this entry; the original blocked finding is not yet declared closed.

The public route, explicit deployment composition/readiness, coordinated clients,
remaining cleanup/deployment/provider qualification, full CI and complete goal
remain unfinished. No merge readiness is requested.

### Foreground composition review closure

All required bounded reviews closed on clean58cfcc8c6748fb587b8b455bcc1636cf9b5cae48,
with implementation parentb2d7dd325ff41643dd0f898f53f80596b0da480f unchanged:
architecture/security PASS, QA/test_delta PASS AFTER FIXES, documentation/CI
integrity PASS. The shared mixed-case finding is closed. Architecture independently
rejected same-value and conflicting mixed-case duplicates. QA independently ran
all12 exact regression bodies on58cfcc8c6; all passed
(/tmp/submission-header-casefold-qa-frozen-replay.log). No other material finding
remains in this private-command/parser delta. The exactb2 PostgreSQL9 and pure156
receipts remain applicable to unchanged command/runtime owners; parser55 proof
and independent frozen regression replay cover the repair. Record/link/diff checks
also passed after repair. This evidence closure changes no implementation.

The full goal remains active: public HTTP/configuration/progress/client cutover,
remaining cleanup/worker/provider qualification, downstream journeys and full CI
are still required in PR708 before readiness. No merge request or new PR is made.

### Public raw-ZIP composition and CLI cutover worktree evidence

The public POST now composes the foreground command through the canonical ART
adapter root and returns the closed nine-field T4 acceptance snapshot. Removed
the preparation POST and the old TASK JSON/admission mutation. An explicit
submission execution profile supplies capacity, runtime and timing limits;
missing/invalid configuration fails before provider work. No deployment values
or provider qualification are inferred from test configuration. The new public
command contract is registered without reassigning prior ownership targets.

Real signed-HTTP tests exercise source upload and PRE with real owner/DB custody
and a portable worker: rejected replay passed in the initial two-case run; accepted
replay passed separately in `/tmp/submission-public-accepted-db.log/json` (1 pass,
Alembic0080, isolated database cleanup complete). The initial accepted case failed
in registry fixture setup: Docker logs establish a PostgreSQL backend signal11 at
2026-11-16 12:16:28 UTC, before the submission request. Evidence is retained in
`/tmp/submission-public-postgres-crash.log`. Recovery and a passing replay do not
resolve that infrastructure defect or replace a clean combined run.

CLI submit now streams the ZIP with the same caller key and exact packet/revision
headers, validates the stable202 receipt and bounded PRE feedback, and distinguishes
acceptance for evaluation from a final Submission. Removed the prepare command and
admission-consuming mutation. Migrated the hostile-peer process tests to the new
single mutation: preserve exact bytes/headers on explicit replay, revision pairing,
local source bounds/change detection, unknown outcomes, no retry after HTTP2 GOAWAY,
closed response identities, safe feedback and response size limits. The old JSON
creation assertions are superseded by raw-ZIP acceptance assertions; immutable
history/findings tests remain intact. Their shared fixtures remain consumed by
TUI, contributor and management read tests.

`go test ./internal/api ./internal/command` passed from cli/. The first attempted
Go command from repository root did not run tests and is not validation. Initial
migrated process suite:14 passed,1 failed in36.39s
(`/tmp/submission-cli-http-cutover.log`): human rendering included a null feedback
field before the readable findings. Fix omits that nil field during human
serialization; raw API receipt validation still requires nonnull feedback. Final
replay evidence follows when available. These local changes remain in progress;
MCP, real public CLI journeys, progress exposure, full API controls and coordinated
cutover review must close before treating this as a finished checkpoint.

Corrected worktree replay: Go API/command packages passed and rebuilt executable
passed all15 hostile-HTTP submission process tests in42.70s
(`/tmp/submission-cli-http-cutover-fixed.log`). Full backend API-controls module
passed57 in135.06s (`/tmp/submission-public-controls-rerun.log`), including the
single raw-ZIP OpenAPI contract and ambiguous-header refusal before body/command
execution. No files under either completed suite changed during that replay.
A fresh origin/main fetch reported zero commits missing from this branch.
These receipts close the local display and API-control test failures only;
coordinated MCP/public journey migration and final scoped reviews remain open.

### MCP single-mutation cutover worktree evidence

Replaced the MCP admission JSON mutation with raw-ZIP submission acceptance.
`submission_create` now accepts the caller assignment/key, bounded Base64 ZIP and
exact packet/revision fields; the gateway sends one202 POST to submissions and
binds response task/assignment identities. Removed preparation_create from input
schemas, tool catalogue, fixed gateway operations, packaged contracts and wheel
inclusions. Existing preparation reads remain until their retained-reader/public
progress migration is complete. No second supported mutation or compatibility
alias was added. The16 remaining execution tools preserve their prior read and
management routes. Refreshed submission_create's snapshot from actual backend
OpenAPI and updated MCP documentation.

Retained upload/header, safe checker failure and fixed-route tests now exercise
submission_create. Added acceptance substitutions/malformed-snapshot and revision
pairing cases. Initial run42passed2skipped (backend comparison command absent),
`/tmp/submission-mcp-cutover.log`; this does not establish OpenAPI drift closure.
Ruff and diff checks passed. A configured backend comparison plus adversarial
cases and package/catalogue checks are running; final receipts follow.

Expanded configured MCP run:53passed1failed in54.22s
(`/tmp/submission-mcp-cutover-verified.log`). Failure was the backend OpenAPI
subprocess dying withSIGSEGV, not a reported contract difference. Exact failed
test replay with PYTHONFAULTHANDLER=1/PYTHONMALLOC=debug passed1 in56.28s
(`/tmp/submission-mcp-openapi-diagnostic.log`). The live backend OpenAPI matches
all16 execution snapshots on replay; no root-cause fix is claimed. The retained
first-run crash is additional native instability evidence.

Catalogue/package command passed3 with1skip because no clean-wheel interpreter
was configured. Built the wheel using the canonical isolated uv build (the earlier
no-isolation attempt lacked hatchling and did not build), installed it into a
fresh /tmp environment and started the configured independence proof. This removes
the obsolete preparation contract from wheel inputs without requiring backend
sources at runtime. Final package/type receipts follow when terminal.

Configured clean-wheel independence proof passed1 in22.71s
(`/tmp/submission-mcp-wheel-proof.log`), and mypy passed all25 source files
(`/tmp/submission-mcp-types.log`). No MCP code changed during these final checks.
This closes the bounded MCP upload/acceptance transport migration, not the full
public journey: operation-progress API/client reads, bounded feedback parity,
remaining real public CLI/backend fixtures, coordinated reviews, deployment
qualification and the full acceptance audit remain required on the same PR.

### Operation progress: exact finalized TASK association

Within the coordinated public-read scope, extend TASK's existing immutable history
port/repository to resolve the operation's exact finalized Submission and dispatch.
Require project/task/assignment/contributor/admission identity together and equal
stored Submission/dispatch versions. Return only the exact attempt status and
original evaluation request identity; do not read the latest task Submission or
infer evaluation activity from TASK status. Missing/mismatched association is an
integrity-unavailable result, never fallback history. This is a read participant;
its caller must establish AUTH in the read transaction before exposing facts.

Allowed: existing TASK history API/repository and the existing real T5 integration
proof. Preserve canonical adapter composition and all immutable rows. No new route
or authorization grant is supplied by this participant. Verify real accepted T5
association, each substituted selector and stored outcome after actual POST.
Required coordinated ARCH/SEC, QA and DOCS review remains open for the complete
public read; this participant alone cannot close progress or end-to-end delivery.

Exact-association worktree verification: both real T5 cases (normal and expired
finalizer claim) passed2,37deselected in64.69s, with migrations through0080 and
isolated database cleanup complete (`/tmp/submission-progress-task-association.log/json`).
Each case rejects substitution of project/task/assignment/contributor/Submission/
admission and confirms that completed POST evidence without governed routing
leaves this exact attempt's outcome unchanged. The added reader neither queries
current task status nor selects a latest Submission. Ruff, diff and module-boundary
validation passed (`/tmp/submission-progress-boundaries.log`, exit0).

This is one required TASK read participant, not a publicly usable progress API.
CHECKERS current-attempt/stall observation, contributor/management AUTH composition,
current-task visibility and next-action eligibility, final closed response, route,
CLI/MCP reads and their real public journeys remain open. Tests ran on the current
worktree; metadata HEAD53d369b4c does not imply the uncommitted delta was frozen in
that commit. Coordinated review and proper implementation commits remain pending.

### Operation progress: current CHECKERS attempt evidence

Extend the existing evaluation coordination port/owner with an exact current
progress observation anchored to the original Submission dispatch request. Read
that Submission's current fence and run; validate original and current scope,
request/reservation, terminal result, and committed retry receipt for successors.
Return the current request/reservation, owner status, database-clock live-lease
fact, exact retry event (when applicable) and completion event. These are internal
facts for progress composition; no new execution authority or public diagnostics.
The caller owns the root transaction and TASK-first locking. Do not derive
running/stalled status from TASK status or rewrite fences/leases. OUTBOX stall
and reconciliation-child observation remains a separate required composition.

Allowed: existing CHECKERS execution API/coordinator and existing real T5/retry
integration tests. Retain exact historical Submission association and prior
request validation. Verify queued/completed states through real source T5/POST,
selector substitution and a real committed retry. Coordinated risk/reviewer
requirements from the public cutover apply unchanged.

Initial CHECKERS observation run passed the two source T5 cases but failed the
existing retry test before the new observation: its shared material_fixture still
calls retired bundle preparation and passes PreSubmitMaterializationPreparationFacts
to the now guide-only resource mapper (AttributeError:guide_source_item_id).
`/tmp/submission-progress-checker-observation.log/json`:2passed1failed,97.82s;
isolated database cleanup complete. Do not restore the obsolete API or treat that
fixture as proof of current intake. Its original assertions remain unchanged and
its migration remains a full-suite requirement.

Moved new retry-progress proof into the actual source T5 test: a controlled exact
source-read outage produces retained infrastructure failure, then the real Operator
retry owner commits a successor and the read follows its audited event. Successful
POST cases additionally observe the actual running lease from an independent root
session during the controlled worker call. No execution, authorization or retry
owner is mocked. The controlled runtime/provider outage is not native qualification.
Expanded source replay is running. Module-boundary validation passed before this
test-only refinement; production CHECKERS files are unchanged since that check.

Expanded source-first progress proof passed3,37deselected in98.68s
(`/tmp/submission-progress-checker-source-retry.log/json`), Alembic0080 and database
cleanup complete. It proves queued and completed exact-request observations,
substituted-selector refusal, actual live-worker observation through an independent
session, infrastructure failure, and current-fence transition to an authorized
retry successor/event. The worker observation returned during execution; it did
not wait for completion. No native-runtime or AWS qualification is inferred.

One Pydantic serialization warning occurs on the real retry path: existing
checker_retry builds request_fields with nested dicts, then
make_selected_post_submit_request uses model_construct before serialized hashing
and final model_validate. The final request and new read validate successfully;
this warning does not originate from the progress read. It remains recorded and
is not silenced. The earlier obsolete-fixture failure remains outstanding.

CHECKERS runtime progress is now available internally through its existing port.
Public progress still requires exact OUTBOX delivery/recovery-child observation,
reader AUTH/current-task concealment and next-action eligibility, closed projection,
HTTP/CLI/MCP reads, and end-to-end verification. These are uncommitted worktree
receipts, not a reviewed/frozen implementation checkpoint or overall completion.

### Operation progress: exact delivery observation

Reuse publisher event construction for initial dispatch, completion and authorized
reconciliation child. Extend the existing internal TASK/CHECKERS progress facts
with their exact event expectations. ART's existing progress module will observe
OUTBOX against those expectations and follow only a child bound to the same
original event, claim generation/digest and current evaluation identity. Never
expose event payloads/private coordinates in the public projection. A finalized
UNKNOWN original with a pending authorized child is not itself proof of a current
stall. Missing/mismatched custody fails closed.

Allowed: existing TASK history API/repository, CHECKERS execution API/results/
coordinator/publisher and reconciliation API/service, ART progress module and the
existing source T5/contract tests. Preserve emitted event bytes, existing authority
and original terminal evidence; no retries, publishes or claims from a read.
Verify real stored initial/completion/retry event comparison and focused child
association/refusal cases. Full public-route/read AUTH and final review remain
required; this change only closes the durable delivery observation prerequisite.

Delivery observation proof: real source T5 suite passed3 in92.12s with0080 and
isolated database cleanup complete (`/tmp/submission-progress-delivery-db.log/json`).
It compares stored initial, completion and retry events through OUTBOX's exact
observation owner. Reconciliation contract module passed34 in5.39s; initial child
association checks passed8 in1.94s. Module-boundary and all changed backend Python
Ruff checks passed.

An additional controlled retained-digest substitution reproduced a missing guard:
parent read and child agreed with each other on a digest different from the
owner's expected event. Before repair the new test failed DID NOT RAISE
(`/tmp/submission-progress-delivery-digest-before.log`). Compare the retained claim
to canonical_json_hash(event.payload) before following a child. All9 child identity
cases now pass in2.39s (`/tmp/submission-progress-delivery-digest-after.log`). This
repair adds no event publication or authority and changes only that read guard.

Freeze the accumulated raw-ZIP API/CLI/MCP mutation cutover and internal progress
participants as a proper implementation commit on the existing PR branch. The
commit is an incomplete-goal checkpoint: public operation GET and client reads,
MCP feedback parity, obsolete fixture/shared producer migration, complete downstream
journeys, cleanup/runtime/provider/deployment qualification and full CI remain open.
No PR readiness or merge request is made. Scoped internal reviews will assess this
implemented delta with those omissions explicit, rather than certify goal completion.

### Frozen public-cutover review and batched repairs

Frozen666be589370c15fe6be15b3ed96bcf97974912bb stayed clean through shared
verification and review snapshots. Combined pure/API/reconciliation suite221passed
in127.34s (`/tmp/submission-cutover-frozen-pure.log`). Combined foreground/public
HTTP/T5 suite14passed in376.40s with exact666 metadata,0080 and database cleanup
complete (`/tmp/submission-cutover-frozen-db.log/json`). Commitrail record check
passed. The existing retry-builder serialization warning remains disclosed.

ARCH/SEC and QA identified the same Medium transport defect: request.stream()
can yield a valid ZIP in a frame exceeding ART's1MiB internal chunk bound; the
route forwarded that frame unchanged. Their independent split/one-frame probes
confirmed identical legal bytes accepted when segmented and rejected whole. Add
public initial/replay tests for both segmentations, expose the existing chunk
bound through ART's public intake contract, and split only at the HTTP adapter.
Keep internal size/EOF/deadline checks and bounded backpressure. This repair adds
no whole-body spool or second ingress policy.

DOCS/CI findingCI-CATALOGUE-001: actual MCP catalogue131 but six exact-count
consumers still expected132. Allowed repair additionally includes the affected
existing .github/workflows/mcp.yml, scripts/test_hosted_mcp_container.py and
deploy/hosted/compose.mcp.yml assertions/summary, MCP drift test and README. Change
only the intentional count removal; preserve exactness, tool-name/route assertions,
health behavior, lane selection and deployment controls. This is catalogue repair,
not deployment authorization. Reviewer independently preserved all692 prior
ownership assignments/protected base with exactly693 total and full CI selection.

QA's independent retained-digest test-of-test passed on666 and failed at the intended
rejection assertion under its controlled guard-removal simulation
(`/tmp/submission-progress-qa-digest-mutant.log`). No other concrete implementation
finding was reported; the two shared repairs remain open until frozen replay.

Both new real HTTP framing regressions reproduced the defect before repair:
large-single initial failed413; large-split initial reached202 but same-key
single-frame replay failed413 (`/tmp/submission-asgi-frame-before.log/json`,2failed,
55.52s, database cleanup complete). The HTTP helper now yields bounded slices of
each supplied frame without reading ahead; ART imports the same public1MiB bound
and retains its guard. Four transport backpressure/boundary cases and the full
API-controls module passed61 in95.25s (`/tmp/submission-asgi-controls-after.log`).
Module-boundary validation and targeted Ruff/diff checks passed.

First repaired four-case database run passed one case then the Python process
segfaulted while garbage-collecting during FastAPI/Pydantic fixture schema creation
(`/tmp/submission-asgi-frame-after.log/json`, exit245, cleanup complete). This is
not an assertion failure or a root-cause fix for prior native instability. The
unchanged four cases are being replayed; retain both outcomes.

The exact131 catalogue repair passed its count assertion, then exposed one older
snapshot drift: ServiceIdentity lacks workstream.artifact.source_cleanup added by
this PR's sealed-cleanup owner. Independent comparison of all task-operation
snapshots found exactly that one enum difference. Refresh only
mcp_server/contracts/service_actor_create.json and its canonical digest/provenance;
do not weaken comparison. Initial command27passed1failed,34.50s
(`/tmp/submission-catalogue-count-repair.log`). Configured comparison rerun and a
local hosted-compose smoke against the rebuilt MCP image are in progress. This
smoke uses isolated fixture containers and is not deployment or AWS qualification.

Unchanged repaired public HTTP replay passed all4 cases in123.46s
(`/tmp/submission-asgi-frame-replay.log/json`),0080 and isolated database cleanup
complete. Both large-ZIP initial/replay segmentations now return stable202 with
one PRE; small acceptance and QC rejection remain covered. The earlier native
SIGSEGV remains unexplained and is not erased by this pass.

Configured MCP catalogue/task-operation OpenAPI checks passed28 in40.38s
(`/tmp/submission-catalogue-count-contract-after.log`). Local hosted-compose smoke
passed on image sha256:06bcaa810b65d2515db1ea44bcbefb8fe32d2402ffd4fc12385795bea16f423e,
with131tools, restart, replacement and stale-namespace counterexample all passed
(`/tmp/submission-mcp-hosted-smoke.log`, exit0). This exercised repaired health and
smoke counts against the actual rebuilt package and removed fixture containers.
It is local protocol/lifecycle proof, not deployment/provider qualification.

Freeze the batched transport/catalogue repairs for affected reviewer replay.
The unchanged666 owner/foreground14 and pure221 receipts remain bounded baseline
evidence; the new transport cases require the repair's exact-head replay. The
full goal and public progress wiring remain unfinished on PR708.


## Public operation progress contract and authorization composition

Repair121f8dfbb71ea24b2ffb75ee1ac735fffe64ffff exact-head large-ZIP
replay passed2 in53.62s with migration0080 and isolated cleanup complete
(`/tmp/submission-asgi-frame-frozen.log/json`). ARCH/SEC, QA and DOCS/CI
closed the scoped framing/catalogue findings. Commitrail validation passed.
Native crashes remain unexplained; these receipts do not establish full readiness.

The next change closes specification5.5: an authorized read of one operation,
never the latest submission. Existing TASK/CHECKERS/OUTBOX observations are reused.
The first implementation step defines the closed public response and exactly-one
selector in existing ART submission_command contract; it grants no read authority.
Allowed files: that contract, existing intake contract tests, ART intake progress
and repository/composition, canonical ART/AUTH adapters, existing AUTH intake
contracts/evaluator, TASK read contracts/owners, public submission route and its
existing tests, affected CLI/MCP contracts/consumers and this record. Broaden this
list explicitly before unrelated changes. Prohibited: provider coordinates in
responses, current-task status as historical outcome, ID possession as authority,
new compatibility readers, data deletion, or weakened tests/CI.

Acceptance: exactly one UUID selector; key lookup scoped to current actor;
required nullable fields retained; existing TASK status reused; exact operation
association; current contributor/management authorization; reassignment conceals
current status; next action derives from current TASK eligibility and original
assignment/revision; owner-backed stalls. Tests must cover closed shape, selectors,
authorization substitution, historical revision independence and corruption.
Risk: authorization/workflow. Required reviews: ARCH/SEC and QA, with DOCS/CI
for generated contracts and client exposure. Human focus: management access,
historical concealment and distinction between accepted handoff and governed result.
The public route and full journey remain unfinished until composed and exercised.

Initial public progress schema/selector checks passed7 (130 deselected) in3.57s;
targeted Ruff and git diff --check passed. Nullable fields remain required and
current_task_status reuses TASK TaskStatus. This is contract-only evidence, not
authorization or public route proof. Response PRE feedback retains the existing
projection shape pending bounded-feedback reconciliation. No endpoint is exposed
by this step; contributor/management composition remains the next required work.


Authorization extension reuses the existing historical-read evaluator, whose
contributor branch requires current exact-project Submitter authority and whose
management branch requires Project Manager authority. Allowed AUTH paths also
include catalogue.py, action_definitions.py, domain/contributor_reads.py,
domain/submission_history.py and existing task_authority/test_intake_authority.py.
Move the existing operation read out of generic own-work dispatch, retain its
original action/permission, and add its management action using the existing
project.task.manage permission. A distinct closed operation resource is necessary:
pre-handoff operations have no Submission ID, so a fabricated history target is
forbidden. Both paths bind the real operation/task/project/contributor and current
reader. An explicit internal management selection is an authorization request,
not a grant; the kernel must independently validate it. Existing replay callers
continue to request the contributor path. No public management route is added.

The exact AUTH catalogue count increases194 to195 for the management operation
read action; permissions remain95. Allowed tests include the existing
authorization/test_catalogue.py exact inventory check. No count check is relaxed.

Audit constraints require a forward migration0081_operation_read_authority;
allowed paths include that migration, existing catalogue_fixtures.py and
test_alembic.py. Preserve every existing action/permission pair and all retained
rows; change only the exact management read pair. Initial catalogue run caught
the missing independent expected row (6pass1fail), which must be added explicitly.
The first DB run was deliberately interrupted before collecting proof when this
missing constraint extension was identified; cleanup metadata confirms complete.

First0081 authority run applied migration but refused reset against the old
exact schema fingerprint:35 setup errors;20 pure checks passed and one catalogue
active-count assertion correctly required170 to171. Update the existing
tests/conftest.py exact fingerprint for the new audit constraint, keeping reset
validation enabled; migration manifest comparison must prove no unrelated change.
Separate migration process segfaulted during pytest assertion rewriting/GC before
test execution (exit245, cleanup complete); unchanged collection-only diagnostic
passed1 selected/68 deselected in0.93s. This is another retained native failure,
not proof of migration behavior or a root-cause resolution.

Progress authorization candidate is held unchanged for live v3 authority and
migration replay processes. Logs/metadata: /tmp/submission-progress-authority-v3
and /tmp/submission-progress-migration-replay (.log/.json). No pass is credited
until terminal results are inspected. Latest shared checks: targeted Ruff, module
boundaries, Commitrail and diff checks passed. All these changes remain uncommitted
worktree work pending proof/review, not a delivered public progress endpoint.

Migration replay completed1failed/68deselected in161.42s: existing
alembic/env.py still hard-codes current head0071 and does not admit0080 as an
upgrade starting revision. This is a forward-upgrade defect masked by fresh
installs. Allowed repair includes alembic/env.py: enumerate the real intervening
revisions and name0081 as current, preserving unknown-revision rejection. Apply
after the frozen authority-v3 process finishes, then replay the manifest proof.
Authority-v3 remains live (session19779); do not restart while running.

Authority-v3 finished47passed9failed in240.34s, cleanup complete. Eight
failures expose missing OperationReadResourceContext audit projection (resource_id
was null); one new Operator negative-control fixture used an invalid project
scope. Allowed repair includes domain/audit_targets.py and runtime.py closed
resource union. Replace the obsolete generic operation-resource audit branch
with the new exact type; preserve operation IDs in allow and denial evidence.
Use a valid system Operator grant for the negative control, retaining denial.

Repaired AUTH read matrix passed13 (22deselected) in101.52s on worktree
parent121, migration0081, with complete isolated cleanup
(`/tmp/submission-progress-authority-fixed.log/json`). Catalogue/audit contracts
passed21 in1.53s (`/tmp/submission-progress-catalogue-fixed.log`). Lint and diff
checks pass. Fetch confirms no missing origin/main commits.

First preflight-repair migration run failed during unchanged0053 with a reported
PostgresSyntaxError before reaching0081 (`/tmp/submission-progress-migration-fixed.log`).
The exact46708-byte reported SQL has balanced parentheses and succeeded against
a temporary table inside BEGIN/ROLLBACK on the same PostgreSQL server
(`/tmp/submission-progress-migration-sql-probe.log`). Do not change0053 or claim
the native/transport cause resolved from this diagnostic. The unchanged forward
upgrade proof is replaying under /tmp/submission-progress-migration-fixed-replay.

Preflight-repair replay successfully upgraded0080 to0081 and confirmed only
the intended constraint changed; its final exact-string assertion failed because
build_manifest uses PostgreSQL pretty constraint definitions without redundant
parentheses. Correct the independent expected addition to that actual format;
retain exact two occurrences and exact equality after removing only the new pair.
Run ended1failed/68deselected in127.49s with cleanup complete. No production or
preflight change is needed for this assertion-format repair.

Final upgrade preservation replay passed1 (68deselected) in119.25s,0081
with complete isolated cleanup (/tmp/submission-progress-migration-preservation.log/json).
Exact comparison proves only the action-evidence constraint changes and removal
of its two new manager-action/permission terms recovers the previous definition.
Independent AST/script inventory confirms preflight recognizes all81 actual
revisions and names the actual0081 head. Configured backend OpenAPI/MCP task
contract drift passed25 in35.41s (/tmp/submission-progress-mcp-drift.log).
Module-boundary validation, Commitrail validation and diff checks passed.

Freeze this contract/authorization checkpoint for required ARCH/SEC and QA review.
These are worktree receipts on parent121, not an exact committed-head full suite.
Public route composition, TASK eligibility/concealment, client progress wiring,
full journeys/CI and native instability remain open. Keep the one PR708 draft.


### Public reader authority selection

Continue in temporary worktree /tmp/workstream-submission-progress-read while the
primary checkout remains frozen atc11 for its exact-head proof. This is a local
implementation branch feeding the same PR708, not a second PR or replacement goal.
The prior allowed public-reader scope and ARCH/SEC/QA review requirements apply.
First close AUTH selection: the route cannot choose by actor ownership alone,
because the stored contributor may now have only Project Manager authority.
Extend the existing intake authority with a composition method selecting its
existing read decision from current locked grants; never probe access by staging
an intentional failed decision. Reuse authorize_read for the one actual decision.
Return separate management visibility and same-owner Submitter-grant facts:
a dual-role actor must not lose authorized management visibility or be treated as
management-only for next-action eligibility. These facts do not grant submission;
TASK must still validate original active assignment, predecessor/revision and
operation guard. Prefer the manager read when its grant exists, and preserve the
separately locked contributor fact for subsequent TASK eligibility. Replay callers
retain the existing explicit contributor path. No client role selector is added.
Allowed files for this step: AUTH api/submission_intake.py, submission_intake.py,
existing task_authority/test_intake_authority.py, and this record. Tests exercise
own Submitter, own Manager, dual-role, other-contributor Manager, wrong contributor,
foreign Manager and absent grants using real decisions/audit rows. No provider,
TASK mutation, route exposure or migration changes are part of this selection step.


### TASK operation-read visibility and candidate context

Extend the existing IntakeTaskCustodyPort and owner (api/intake_custody.py and
intake_custody.py) with a read of the operation's exact original assignment.
Allowed proof extends existing artifacts/test_submission_intake_custody.py.
This does not change the frozen primary checkout or AUTH selection source under
test. The reader receives authenticated projection facts from AUTH, checks exact
TASK/project/assignment/contributor association under TASK-first locks, and exposes
current status only to management or the active original contributor. A candidate
new-intake context is returned only for an authorized same-owner Submitter with
an active original assignment, matching current predecessor and no operation guard.
Reuse the canonical Submission context service, not a second revision resolver.
The candidate is not final eligibility: composition must apply the existing locked
PROJECT revision-capacity and explicit acknowledgement checks before recommending
a new submission. Missing original ownership is an integrity error. Current
ineligibility yields no candidate without changing historical operation outcome.
Acceptance/proof: initial active context, active-operation guard, cleared terminal
guard, hidden status for non-active/unauthorized contributor projection, manager
visibility, exact selector substitution refusal; existing AUTH tests supply the
separate permission proof. No TASK writes or new submission transition are added.

Frozen primary c11 replay passed14 in214.43s with exact c11 metadata,0081 and
cleanup complete (/tmp/submission-progress-frozen-c11.log/json). ARCH/SEC, QA
and DOCS/CI scoped reviews now closed with no required repairs.
Isolated public automatic-authority selection passed7 in45.42s with0081 and
cleanup complete (/tmp/submission-progress-auto-authority.log/json); these are
worktree receipts on c11, not committed public-reader delivery. TASK-only additions
were independent of that AUTH test scope. Closed/reassigned assignment public
concealment and complete next-action policy checks still require composition proof.

Reviewed commits666be5893,121f8dfbb,c11ed9101 were pushed together to existing
PR708 branch after all three scoped reviews closed. The public-reader continuation
remains uncommitted in the temporary worktree; primary checkout stays clean atc11.
TASK context proof is live under /tmp/submission-progress-task-context-v2.log/json
(session21862); inspect terminal result before rerunning or claiming proof.


### Owner-backed progress read composition

Compose the actual read in existing ART intake/progress.py, existing public
submission_command.py, canonical adapters/artifacts/__init__.py and public
api/routes/artifact_submissions.py. Extend existing public/intake tests rather
than creating another reader subsystem. AUTH selects live read mode after exact
TASK-first operation locking; key lookup is scoped to the current actor. Validate
accepted custody with the existing database acceptance verifier, which checks
retained PRE/receipt/AUTH/event evidence independently of the current reader.
Read exact TASK finalized association and CHECKERS current attempt; follow the
existing OUTBOX delivery/reconciliation observer. Governed attempt status outranks
pending delivery, never current task status. Infrastructure-failed current CHECKERS
attempt and dead-letter current delivery supply explicit operational stall facts;
no expired clock alone is a stall. Live worker lease is required for running.
TASK current status is contextual only; new-key advice requires its candidate plus
shared locked PROJECT revision capacity and original acknowledgement validation.
Errors are concealed/sanitized; no storage provider or execution profile is needed
for a read. Commit the read audit before returning; restage canonical denials after
rollback. Acceptance: public selectors, actor-scoped key, initial/PRE/accepted/
finalized state progression, management/own authority, retained-attempt isolation,
closed/reassigned concealment and bounded failures. Required ARCH/SEC and QA apply.

Allowed API proof includes existing tests/test_api_controls.py exact route/action
inventory addition and artifacts/test_submission_foreground_command.py public
acceptance/QC read assertions. TASK context test hit PostgreSQL internal node61440
during existing guide fixture setup (43.64s), before new assertions; cleanup
complete. Saved server log /tmp/submission-progress-postgres-before-restart.log,
confirmed no client backends, and restarted only the owned test PostgreSQL container.
No native root cause is claimed. Replay the unchanged TASK proof on fresh server.


Public accepted/QC progress reads and TASK context proof passed3 (67deselected)
in203.47s with0081 and cleanup complete (/tmp/submission-progress-public-read.log/json).
This is scoped portable/local proof after the owned server restart, not resolution
of native failures. API controls found the intentional new GET needs count134,
protected132; retain prior inventory hashes by explicitly classifying that new
route in public_entry_actions, not refreshing unrelated hashes.

CI on pushedc11 found two real public-contract boundary violations introduced in
prior owner observations: TASK and CHECKERS API contracts import OUTBOX types.
Do not relax architecture tests. Allowed repair extends tasks/api/submission_history.py,
tasks/submission_history.py, checkers/api/execution.py, checkers/execution_coordination.py,
checkers/api/delivery_reconciliation.py, checkers/delivery_reconciliation.py and
existing intake-admission proof callers. Carry immutable serialized event facts
across those public boundaries; reconstruct OutboxAppendInput only in private
composers/observers. Preserve single shared event builders, exact envelopes,
canonical payload digests and stored-event comparison. Rename the replaced fields
and helper, update every consumer, and remove the prohibited imports entirely.
No parallel old/new field or producer is retained. Run the actual architecture
unit tests as well as module-boundary validation; generic validator alone missed
these narrower dependency invariants. Other CI lane failures still need artifact
inspection; /tmp/submission-c11-ci-task-lane.log alone has no terminal diagnosis.

Extend the existing real T5/PRE/POST proof with actual public progress reads
for finalized queued, worker-live running, completed awaiting governed routing,
explicit infrastructure stall, and Operator successor retry. Retain all original
owner association/substitution, retained-data and dispatch assertions. The revised
API fields carry serialized event envelopes and observers revalidate via OUTBOX
before exact comparison; public HTTP exposes neither those envelopes nor providers.

### Removed-route test migration

The raw CI task-lane log confirms collection errors in three modules rooted in
recovery tests importing the removed preparation handler. Migrate the HTTP tests
in tests/test_submission_bundle_preparation_recovery.py and the binary OpenAPI
assertion in tests/test_submission_bundle_admission.py to the sole raw-ZIP submit
contract. Preserve ordered bounded feedback, sanitized error categories, unexpected
failure propagation and optional packet-text warning semantics. Keep the shared
_feedback_facts and internal preparation tests until their remaining consumers are
replaced; no compatibility route or production alias is permitted. This is test
contract repair with QA review in the existing checkpoint, not a new product path.
Verify collection of all three affected modules, targeted HTTP assertions and
existing internal command assertions. Human review focus is preservation of error
boundaries despite replacement error codes and response schema.

Finalized public progress proof passed all3 cases in165.85s with0081 and isolated
cleanup complete (/tmp/submission-progress-finalized-public.log/json). One Pydantic
serializer warning in the existing forged-context case remains visible. This is
uncommitted worktree proof, not full CI qualification.

The three modules now collect: first execution reached61 cases,29passed/32failed.
Failures expose the shared feedback fixture still constructing the removed
zero-project-PRE facts shape (seven missing source evidence fields), plus the
unexpected-error assertion now encountering mounted middleware's500 conversion.
Use the existing structural source-completed fixture and required one-project
member, retaining no-member default rejection; test unexpected propagation at the
handler boundary as before. Do not relax production evidence validation.

Additional CI repairs allowed: format cli/tests/integration/test_submission_http.py
using the configured Ruff formatter; reconcile only the missing manager operation
read ActionId in MCP contract snapshots containing that schema and recompute their
canonical hashes. Verify full MCP OpenAPI comparison, not only task contracts.
No unrelated schema refresh is authorized by this repair. Rust runtime log shows
five unwrap failures in old PRE fixture helpers; investigation remains separate.

Corrected route/fixture replay passed61 in36.52s across all three previously
uncollectable modules (/tmp/submission-route-migration-v2.log/json), with0081 and
isolated cleanup complete. The scoped CLI formatter check passes. MCP full drift
probe still reports an ActionId schema mismatch; inspect exact normalized diff
before refreshing anything else. The initial local MCP invocation incorrectly
used PYTHONPATH=src although this package lives at its root; it collected78 tests
rather than CI's144, so its scope is not accepted as complete MCP qualification.

Exact normalized MCP diagnosis also finds the previously committed source-cleanup
action, permission and service identity missing in authorization_context_get,
admin_roles_list and actor_get snapshots. Extend snapshot repair only to these
three existing enums from canonical authorization catalogue; prohibit removal or
any other added enum member. This closes existing cleanup contract drift rather
than changing authorization behavior.

The fail-closed enum updater additionally identifies the already implemented
artifact.submission.finalize action absent from the authorization-context snapshot
(no removed actions). Include that exact canonical action in the repair scope.
The intermediate MCP replay started before this last omission was repaired; its
result cannot qualify the final snapshots.

Scope correction: inspection of .github/workflows/mcp.yml shows CI's144 cases
span four drift files; test_contract_drift.py alone has78 cases even with the
correct package path. The count difference was not evidence of an import failure.
Run the remaining three files too before claiming equivalence to that CI step.

Final main MCP drift file passed78 in35.75s against configured current backend
OpenAPI (/tmp/submission-mcp-full-drift-v3.log). Remaining three CI drift files
are running under /tmp/submission-mcp-remaining-drift.log (session41274).
Backend-wide collect-only verification is running under
/tmp/submission-backend-collection.log (session77217). Preserve these live handles;
do not restart based on observation timeout. All changed Python files passed Ruff
and git diff --check. Current work remains uncommitted in the temporary worktree.

Remaining MCP drift run passed64 and failed only the exact public route count:
new operation progress GET makes132, not131. Extend allowed test scope to
mcp_server/tests/test_task_operation_contract_drift.py: assert the exact GET path,
security and contributor/management action metadata, then count132. This records
backend exposure; CLI/MCP progress tool wiring remains required and is not implied
by this inventory repair. Backend collect-only remains live (session77217).

### Governed completion in public progress proof

Extend only existing artifacts/test_submission_intake_admission.py T5 drill to
actually deliver the retained POST completion through OUTBOX with fixed dispatcher
and router authority. After acknowledgement assert public progress reflects the
persisted governed submission outcome and inspect-governed-outcome next action,
while preserving all pending/running/stall/retry checks. No direct outcome SQL
mutation or fabricated acceptance is allowed. This closes the gap between completed
checker evidence and governed progress. Existing ARCH/SEC and QA review applies.

Backend collection reached12174 tests but8 modules require missing httpx2. This
is a local environment mismatch: pyproject's agents extra pins httpx2==2.12.0.
A separate /tmp/workstream-submission-agents-env is being provisioned using
uv sync --frozen --extra agents, preserving the shared current environment.
The MCP task-operation inventory replay passed25 in30.46s; combined with78 main
and the other40 passing drift cases, all four CI drift files have scoped passing
coverage after the intended inventory repair (not an entire MCP lifecycle suite).

Correct locked agents+dev environment collects all12486 backend tests successfully
in111.30s (/tmp/submission-backend-agents-collection.log). This closes collection
only, not execution. Generic module-boundary validation also passed. The new
real governed-completion drill remains live at /tmp/submission-progress-governed.log
(session69102); do not claim its outcome yet. Rust investigation shows the failing
fixture's prepared_generation_id belongs to the superseded PRE material-grant
path; the corresponding production branch still exists. Its removal and transfer
of output/cleanup/security proof to supported execution requires a focused owner
cleanup, not insertion of old fields into the new source-bound request fixture.

Governed drill ended2failed/1passed in171.48s, followed by a Python GC shutdown
SIGSEGV; isolated cleanup completed. Both non-infrastructure cases dead-lettered.
Inspection shows ART's seed_started_task_for_artifact_test deliberately arranges
an ART-only active assignment without accepted_at, while TASK routing requires
accepted work. Complete that prerequisite in this fixture's initial setup before
any intake (not after routing), retaining production routing guards. This still
is not public claim authority proof. Include full delivery outcome on assertion
failure to distinguish any remaining cause. Replay one successful branch first.

Focused governed replay uses the clean locked agents+dev environment and is live
under /tmp/submission-progress-governed-v2.log/json (session84882). Fixture-local
sqlalchemy.text import was corrected before test execution; Ruff/diff pass. Read
its terminal result before further changes or qualification claims. Public progress
and CI repairs remain local/uncommitted; required review and same-PR push remain
outstanding, alongside full goal requirements.

Focused governed replay passed1 in81.80s on the corrected initial assignment,
with0081 and complete isolated cleanup (/tmp/submission-progress-governed-v2.log/json).
Real OUTBOX completion delivery acknowledges, TASK persists review_pending and the
public reader returns inspect_governed_outcome for that original submission.
This proves the default human-review admission branch, not human terminal review
or automatic final acceptance. No native crash occurred in this run; its cause
is still unresolved. Freeze the current public reader plus scoped CI repairs for
required ARCH/SEC, QA/test-delta and DOCS/CI review, with exact committed-head
regression to cover all three T5 cases after the fixture correction. CLI/MCP
progress commands, other governed outcomes, historical/new-revision concealment,
old runtime removal and full acceptance/qualification remain open.

### Frozen public-reader review closure

Code checkpoint0e45c371eb24f8909e7e88aaa05d8af6d6a54af7 has exact-head proof:
- /tmp/submission-progress-frozen-0e45.log/json:11passed231.52s (threeT5,
  sevenlive-authority selections, oneTASK visibility/context),0081,cleanuptrue.
- /tmp/submission-public-frozen-0e45.log/json:2passed61.32s (small accepted and
  QC-rejected public ZIP/progress flows),0081,cleanuptrue.
- /tmp/submission-progress-architecture-full.log:92passed245.83s.
Ruff, diff, module-boundary and Commitrail checks passed. Remote fetch confirms
no missing origin/main commits. PR708 remains the only draft PR.

ARCH/SEC code review, QA/test-delta and DOCS/CI reviews closed with no required
repairs on clean0e45. QA independently proved the mounted error test detects a
503-to409 mutation and that PRE feedback rejects metadata/actor/key/task/assignment/
source substitutions (/tmp/submission-progress-read-qa-error-mutant.log and
/tmp/submission-progress-read-qa-feedback-probe.log). DOCS/CI inventory mutants
reject absent GET/security, wrong manager action and an extra public route
(/tmp/submission-progress-read-docs-ci-adversarial.json). These are scoped review
verdicts; earlier native failures and remaining full-goal requirements persist.
This evidence-only follow-up does not change the reviewed production/test code.
Next work: client progress commands and pending task/work-context projection,
real historical/reassignment/new-revision and remaining governed outcome proof,
obsolete runtime/consumer cleanup, full CI and A01-A35/C01-C07 qualification.

### Client operation inspection

Extend existing CLI submission API/command and MCP task-execution adapter with
one read-only operation lookup using exactly one operation UUID or actor-scoped
idempotency UUID. No resubmit, poll loop, provider field or client-owned lifecycle
inference. Preserve required nullable fields, original task/selector binding,
closed stage/action enums and bounded feedback through existing safe output paths.
Allowed: cli/internal/api/submission_progress.go and focused tests, existing
cli/internal/command/submission.go and command/HTTP tests; MCP existing schemas,
http_gateway, task_execution tools, catalogue tests/packaging and a snapshot for
the new read; CLI/MCP README and this record. Keep governed revision preparation.
MCP key lookup must remain a query parameter, never the mutation-only header or
filtered out by common submit-field exclusion. Response binding must validate
task and the supplied selector, including manager ID lookup versus own key lookup.
Risk: public adapter/security contracts; require ARCH/SEC and QA/test-delta review,
DOCS/CI for snapshot/catalogue changes. Acceptance: each selector emits one GET,
invalid/ambiguous selectors make no request, foreign/malformed/extra-field output
is refused, and accepted/rejected/stalled/governed responses preserve server advice.
Verify focused Go/CLI HTTP tests, MCP input/output/gateway and actual OpenAPI drift.
The task/work-context pending projection remains a separate required owner change.

Client worktree evidence: Go API/command packages pass; existing CLI HTTP15cases
pass, and corrected explicit-json progress cases pass2 in1.79s (initial test
invocations accidentally requested default text). MCP focused run60passed/2backend
probes skipped; configured backend drift replay20passed48.81s closes those probes.
Additional response-negative tests initially omitted authentication and therefore
failed their one-upstream-request assertion; corrected authentication is required
also for invalid-selector tests so absence of dispatch cannot pass vacuously.

CI on pushed686 independently confirms92 architecture tests pass, then rejects
new structural debt: intake_admission.py1330lines and its T5 function220lines.
Do not refresh the debt ledger to bless growth. Extract cohesive existing proof
into focused tests/helpers with unchanged assertions and collect/lane membership.
CLI real-API failures still use removed PRE materialization constructor/fields;
these require shared consumer migration, alongside the known Rust obsolete grant
path. Logs /tmp/submission-686-ci-133380152032.log and
/tmp/submission-686-ci-133382036484.log. Neither is fixed by client progress work.

Client progress negative replay passed10 in56.98s with authenticated calls:
/tmp/submission-progress-mcp-negative-v2.log. Both selector GETs, no mutation header,
wrong selector/task refusal, extra/private field, missing nullable, unknown stage
and invalid input/no-dispatch cases exercised. Built CLI inspection replay passed2
in2.27s including JSON and safe text paths (/tmp/submission-progress-cli-http-v3.log).
MCP wheel built successfully and contains the exact new contract bytes
(/tmp/submission-progress-mcp-dist/workstream_mcp_server-0.1.0-py3-none-any.whl).
These are local worktree receipts on parent686, not reviewed/pushed client delivery.
Current client implementation is ready for scoped review after the required test
structure repair; same PR708 and all remaining goal requirements still apply.

### Preserve T5 proof without structural debt

Move the existing three-parameter T5 proof from test_submission_intake_admission.py
to focused tests/artifacts/test_submission_intake_progress.py. Extract its existing
contiguous retained-custody/association assertions into one local helper, return
only the owner observations needed by the remaining progression assertions, and
move imports to module scope. Preserve every assertion, parameter, real HTTP call,
source substitution and real OUTBOX outcome. No skips, new abstractions, debt ledger
refresh or limit increase. Add the new module beside admission in the existing
shared-foundation lane catalogue; verify collection and actual lane membership.
Allowed files are those two tests, scripts/test_lane_catalogue.py and any exact
catalogue expectation proven stale by this move, plus this record. QA/test-delta
and CI integrity review must inspect preservation and selection on the frozen
client/proof checkpoint. Run the three moved cases and structure validation.

Extraction replay passed3 in152.57s,0081,cleanupcomplete
(/tmp/submission-progress-extracted.log/json), retaining the existing intentional
forged-context serializer warning. Mechanical AST comparison preserved all42
assertions and original3-case parametrization. Main test117lines and custody
helper75lines are below the120line function limit; source admission file shrank
below1200. Structure validator passes with unchanged debt ledger. Lane/catalogue
replay passed76 in19.89s; removing only the new progress-module path reproduces the
prior shared-family fingerprint exactly. Behavior-ownership validation passes.
Freeze client progress plus proof extraction for ARCH/SEC, QA/test-delta and
DOCS/CI review. All receipts above are worktree receipts on parent686; no full CI
or historical/terminal branch qualification is implied.

### Client review repairs

Frozen ddf proof passed3DB153.91s (0081/cleanuptrue),66configuredMCP238.40s,
17CLIHTTP37.68s and GoAPI/command packages. QA/test-delta passes, with independent
binding mutant detection and exact42assertion/four-raises preservation. ARCH/SEC
found no runtime defect, but the newly tracked test has an extra empty EOF line;
precommit diff --check had not inspected untracked files. DOCS/CI requires132-tool
counts in .github/workflows/mcp.yml, scripts/test_hosted_mcp_container.py and
deploy/hosted/compose.mcp.yml, plus CLI's stale prepare/admission walkthrough and
MCP's Seventeen family summary. Extend repair scope to these three exact hosted
consumers; retain uniqueness and fixed-name checks and explicitly require the new
progress tool where names are already inspected. Remove only the EOF blank line,
reconcile the current submission walkthrough/unknown-outcome/revision advice,
and remove duplicate appended progress prose. No client/runtime behavior change.
Verify committed diff whitespace, document scans and actual assertion probes;
replay affected reviews against the repair commit before pushing samePR708.

Repair verification: actual application tools/list returns132 tools and passes the
exact workflow Python assertion, hosted smoke count/name assertions and Compose
healthcheck Python with substituted HTTP responses. Workflow counterprobes reject
missing, extra, duplicate and missing-progress-tool catalogues. Artifact:
/tmp/submission-catalogue-repair-probe.log. This proves catalogue assertions, not
hosted deployment. Commitrail validation and worktree whitespace checks pass.

### Real CLI raw-ZIP journey migration

The pushed client repair is closed by affected ARCH/SEC and DOCS/CI reviewers at
4346f80e9. Current main is contained. The real CLI submission drill still calls
removed preparation routes and fails inside old materialization authorization
before exercising the CLI. Replace that drill with the signed admission fixture,
real socket/raw-ZIP command, portable source-bound PRE and actual T5 finalizer.
Allowed: cli/tests/integration/test_submission_public_api.py and its narrowly
scoped support, additive ownership registration if needed, and this record.
Preserve exact replay, changed-packet refusal, immutable bytes/one Submission and
POST dispatch, history/detail/findings/own-work reads, same-project/foreign-project
concealment, suspension and grant-revocation checks. Replace obsolete preparation
reads with operation-ID/key progress and unknown-operation refusal. Do not restore
legacy constructors, mutate production authorization, narrow CI or claim native
runtime/distributed scheduling. Approved-policy/task fixture setup is not public
setup proof. Risk is integration/proof fidelity. Verify built CLI against signed
HTTP/PostgreSQL and real Local storage; review QA/test-delta and ARCH/SEC with
explicit before/after behavior mapping. Human review focus is retained authority
and exact source custody. Shared legacy materialization fixtures remain a separate
consumer migration, not fixed by this drill.

Worktree drill evidence: initial collection needed explicit pytest-asyncio wrappers
for imported backend fixtures, matching adjacent CLI proofs. The historical GET
preparation routes remain intentional; only the obsolete POST is asserted absent.
The v3/v4 runs now reach accepted raw-ZIP replay, pending progress, production
OUTBOX finalization, finalized history/own-work reads, one-PRE custody, foreign
concealment and suspended-actor denials. They fail when the reactivated actor's
submitter grant is revoked: progress still succeeds while submit/history/findings
fail. v4 reports stored actor active/grant revoked. Retain this regression;
no authority relaxation or production change has been made. Investigate the exact
read audit/selected grant before repairing. Logs: /tmp/submission-cli-source-journey-v3.log
and /tmp/submission-cli-source-journey-v4.log. Structural validation, Ruff,
Commitrail and whitespace pass; these are not a passing journey result.

Diagnosis supersedes the suspected authorization defect: v5 audit shows the
revoked submitter decision denied, followed by a valid management decision.
seed_started_task_for_artifact_test grants the task actor a project manager role
for screen/release and retains it. This is not a submitter-only fixture. Revoke
that setup-only management grant through signed admin API before the CLI journey,
assert no active management grants remain, then keep the original contributor
revocation refusal. No production AUTH repair is justified. v6 is the explicit
counterprobe asserting that the unadjusted fixture is submitter-only.

The v6 counterprobe fails before upload with exactly one active project_manager
grant on the task actor. The repaired drill revokes that grant via the signed
admin API, retains its row/audit history, and asserts zero active management grants
before and after the journey. Temporary verbose audit diagnostics are removed.
The v7 run is the first execution of that repaired contributor-only setup.

Repaired contributor-only journey passes1 in71.96s, exit0, migrations0081 and
isolated database/role cleanup complete (/tmp/submission-cli-source-journey-v7.log/json).
This is worktree evidence based on4346f80e9; only this record changes after that
execution. The full assertion path includes accepted replay before/after T5,
changed-packet409, both progress selectors, zero-before/one-after Submission,
retained raw digest/size, history/findings/own-work, same/foreign project404 and
suspension/revocation404. Production OUTBOX handler performs T5; actual broker,
POST execution and native/provider qualification are not claimed by this drill.

ARCH/SEC and QA/test-delta close the fae1d4dce drill with no required repairs;
QA independently confirms the zero/one manager guard and unchanged socket helper.
Both preserve the worktree evidence provenance and broader goal limits.
CI4346 preflight now passes structure but finds one unused dataclasses.asdict
import in backend/tests/test_authorization.py, left by removed-route migration.
Extend the repair scope to removing only that unused import; no test behavior or
production code changes. Verify the full backend Ruff gate before the same-PR push.

### Remove superseded runtime prepared-PRE grants

The source-bound execute_pre path is separate from execute/POST grant handling.
The service still parses the removed prepared_generation PRE material grant, and
five runtime tests panic when their helper looks for prepared_generation_id in
the current source request. This is an affected obsolete implementation, not a
reason to add legacy fields back to the source contract. Next bounded scope is
external_checkers/workstream-checker-service/src/main.rs and this record only.
Remove PRE_GRANT_PROTOCOL/GrantManifest/GrantIdentity, old matching and its unused
semantic wrapper. Keep shared POST semantic hashing and all POST retained/source
custody validation. General wire/output/uncertain-cleanup tests use a valid parsed
POST request and exact published POST grant. Keep explicit current PRE model-grant
refusal without manufacturing prepared material. Replace old positive prepared-PRE
lineage test with binding-valid old protocol refusal at verify_grant. Prohibited:
new compatibility path, relaxed request/grant/custody checks, test skips or reduced
execution/cleanup assertions. Risk: runtime architecture/security and proof fidelity.
Verify pinned Rust1.84 service tests and workspace tests; ARCH/SEC and QA/test-delta
review before samePR push. This closes obsolete runtime acceptance and its failing
consumer proofs; shared backend fixtures, native deployment and full goal remain.

Extend scope to external_checkers/README.md's affected grant paragraph: POST owns
verified aggregate workspace grants; PRE owns the sealed-source single session.
Remove the stale statement that PRE retains a distinct prepared material grant.
Initial service run:132passed/3failed. Two fixture repairs preserve assertions:
match the POST fixture's image digest in test cache and release the POST materials
directory for teardown. An unchanged Smol launch-bound test also hit its500ms
execution deadline; its unchanged second-run case passes, not a root-cause fix.
No deadline or production execution bound has been relaxed.

Service v2 passes135 unit cases and11/26/16 integration cases. Full workspace
then passes guest/SDK suites but fails one unchanged PRE transport permitted-log
case (134servicepass/1fail). Its is_ok assertion hides the actual error. Extend
scope solely to a diagnostic assertion in smol/pre/transport/tests.rs; retain the
same is_ok predicate and every deadline/bound. Run that exact case to expose the
cause before claiming workspace success. Log:/tmp/submission-runtime-workspace.log.

The diagnostic log-limit case passes once under cargo and three direct repeats
with the same bounds; no hidden error reproduced. Artifacts:
/tmp/submission-runtime-log-diagnostic.log and /tmp/submission-runtime-log-repeats.log.
Do not infer that the earlier transient transport failures are fixed. Keep the
improved error assertion and replay the workspace with it; no production timing,
log limit, cleanup assertion or test selection has changed.

Workspace replay with diagnostic assertion passes the permitted-log case but
fails the unchanged launch-bound positive with deadline_exceeded (134service
pass/1fail); /tmp/submission-runtime-workspace-v2.log. Guest/SDK suites12/40/9pass.
Do not call the workspace green. No further repeat-until-pass attempts: keep
these timing failures open for dedicated transport diagnosis/native qualification.
The grant-cutover service v2 proof passed135unit+11/26/16integration before the
error-only diagnostic edit, with no grant implementation changes afterward.
Rustfmt, Commitrail, Markdown link and whitespace checks pass. Freeze this
bounded removal for ARCH/SEC, QA/test-delta and affected documentation review;
full goal still requires the failed gate and all other lifecycle work to close.

All three bounded runtime reviews close on b67d02a12 without required repairs.
QA independently runs the retired-protocol refusal test in an isolated copy and
confirms a permissive-v1 mutant fails its precise protocol assertion. The initial
compiler SIGSEGV remains unexplained; single-job/larger compiler stack diagnostic
completes. This does not close the recorded full-workspace transport failures.

### Structural ledger reconciliation after import repair

CI8989 preflight fails exact structural-debt parity. Inventory isolates one change:
backend/tests/test_authorization.py has the same10709 lines but its hash changed
when8989 removed unused asdict from the existing import. Protected main has10754
lines; the earlier route-test migration already shrank this item. Allowed scope:
this record and that single content_sha256 in TEST_STRUCTURE_DEBT.json. No source,
assertions, policy, exceptions, limits or other ledger entries change. Acceptance:
exact current inventory parity and full trusted-transition/assertion-map validation.
Risk is CI evidence consistency; focused CI reviewer inspects the one-entry delta.
Human review focus is confirming the digest corresponds to the already-reviewed
import-only edit, without accepting new or growing structural debt.

Full structural validator passes exit0 with the reconciled digest, including
trusted-main transition and assertion-map checks; log:
/tmp/submission-structure-reconciliation.log. No test or policy edit was needed.

Focused CI review closes the digest repair without findings. Latest CLI HTTP job
133428292508 stops before HTTP tests: Ruff check passes, formatter rejects only
cli/tests/integration/test_submission_public_api.py. Extend repair scope to pinned
Ruff formatting of that already-reviewed drill. Require identical Python AST,
full CLI lint/format gates, and unchanged structural inventory; no behavior edits.

Formatting repair preserves the complete Python AST. Move the existing E402
annotation to the formatter-expanded import's opening line so Ruff still applies
it. All98 CLI test files pass lint and format checks; full structural validation
again passes exit0 (/tmp/submission-format-structure.log). Both latest CLI jobs
stop at this same formatting gate before integration execution. No new journey
execution evidence is claimed. Latest fetched main is already contained in HEAD.

### Shared retained-history producer cutover: caller audit

CI8989 task_lifecycle_a artifact14244099338 supplies the failing test log at
/tmp/submission-8989-task-a-tests.log. It exposes two superseded producer paths:
retained_material_fixtures._runtime_factory passes removed materialization to
SelectedPreSubmitExecutionService; tasks.submission_lineage_support prepares old
material facts for the current guide-source authority. Neither warrants restoring
old constructors or weakening AUTH. Current retained_admission has two callers:
submission_fixtures.seed_retained_submission and dispatch/test_concurrency's
second-ready-admission race. The latter assumes two independent ready admissions
before TASK creation; current T1 task exclusion and T4/T5 handoff require a new
race trigger, preserving single committed Submission/dispatch/checker/event proof.
MemoryStore also serves checksum-bound migration rows and POST storage proofs;
its retained-object read/write semantics must survive. Migration snapshots remain
immutable and are not a substitute for a current submission producer.

Next bounded implementation scope: retained_material_fixtures.py,
submission_fixtures.py, checkers/execution/storage_fixture.py and directly affected
submission_dispatch fixture/race consumers, plus a focused current-source fixture
helper if required for cohesion. Replace preparation/verification/hidden-current
creation with real source T1/upload/PRE/T4 and production OUTBOX T5. Keep portable
external PRE as explicit controlled runtime evidence for the one selected image.
New producers must explicitly approve exactly one PRE and one POST before task
release; empty-policy historical reads remain valid, not new execution inputs. Preserve private retained packet fields only at the existing
fixture injection boundary around the canonical T5 writer. Retain exact source
bytes for subsequent POST and separate historical archive reads. Prohibited:
compatibility constructors, fabricated eligible PRE, SQL bypass of custody,
disabled triggers, weakened race assertions, changing snapshot data, or calling
this provider/native/broker qualification. Acceptance is the affected retained
history/read/storage suite plus concrete initial/revision and duplicate-finalizer
proof, followed by the original failing lane. Risks: lineage/authorization,
fixture proof fidelity and test structure. ARCH/SEC and QA must review the caller
mapping and frozen implementation; CI review applies if assertion maps/lane
selection need reconciliation. Human focus is preserved original proof and exact
T4/T5 source lineage. Shared post_submit_materialization_helpers and other old
lineage callers remain tracked follow-on consumers, not silently accepted green.

ARCH/SEC plan review confirms the existing ready-admission race cannot be carried
forward literally: T1 already owns exclusion, and duplicate T5 must prove exactly
one durable continuation. It also confirms private packet injection belongs only
around production T5's existing build_submission boundary. Source provider fixture
must bind operation/fence/generation and bytes while preserving historical reads.

Concrete prerequisite found during caller audit: ExternalCheckerPolicyCompileRequest
and GuideProposalApprovalInput still allow0..200 images per phase, whereas spec
D08/A34 and T1 require exactly1 each. Do not manufacture a selected image when
migrating retained policies. Tighten NEW approval/compiler input and CLI/MCP input
contracts together, leaving LockedExternal* retained decoders unchanged (spec20.2).
This requirement precedes creating valid current retained-history producers.
Allowed prerequisite paths: checkers/api/external_policy.py (compile input only),
projects/api/guide_proposals.py (approval input), cli/internal/api/guide_approval.go,
MCP generated approval contract and affected schema generation/tests, focused
policy/approval/client tests, and current selection docs. Prohibited: rewriting
locked policy bodies, changing historical decoder cardinality, silently picking a
first image or supplying defaults, relaxing admission, or removing retained replay
proof. Verification must cover missing/zero/two selections in either phase, exact
one-per-phase success with real registry resolution, rejection before registry or
HTTP side effects, schema parity, and historical empty/multiple-policy decoding.
ARCH/SEC and QA review apply; client contract/docs review applies on frozen target.
Broader caller migration remains required after this boundary is enforced.

Cardinality worktree regression: four zero/two-per-phase cases fail before input
bounds change; exact-one registry resolution passes. Tightened compiler and public
approval request fields to1..1, without changing retained decoders. Updated phase
configuration/model/forge tests to supply an explicit valid counterpart selection,
so their original failure boundaries remain reachable. Old duplicate/unsorted
multi-selection input proof now checks categorical cardinality refusal. Retained
multi-PRE aggregate runtime-budget guard is tested at stored decoding; historical
zero/two phase bodies retain exact JSON/hash. Full policy module passes35 in4.21s
(/tmp/submission-cardinality-policy-v2.log). Two saved-POST compiler tests now use
explicit one-per-phase inputs; their exact projection/hash assertions remain.

CLI input validator and MCP snapshot enforce the same cardinality. Their boundary
fixtures now explicitly select both images; zero/two selections must fail without
HTTP. Initial CLI replay launched before its new binary existed and failed fixture
setup; this is no product evidence. Replay begins only after binary existence is
observed. Client tests, backend schema parity, remaining approval fixture migration,
full shared checks and frozen review are still outstanding. These edits are not yet
committed/pushed; latest PR head remainsfac8ea511.

Current client evidence: Go API/command packages pass; rebuilt CLI approval HTTP
module passes6 in55.39s (/tmp/submission-cardinality-cli-v2.log), including the
new zero/two no-request cases. MCP lifecycle and configured full backend OpenAPI
snapshot checks remain live at this checkpoint; no result is inferred from partial
progress output. The latest full policy run remains35pass; saved-POST fixture
updates made afterward still need their focused execution.

Extend affected fixture scope to projects/guide_activation/source_fixtures.py,
projects/unified_policy_fixtures.py, selected_policy_fixtures.py and proposal
pg_support/test_postgresql/test_public_api. Ordinary fixture defaults deliberately
select the existing controlled PRE/POST specs before approval. Explicit None
continues to mean no registration for tests proving later image registration;
it cannot be approved by the new contract. proposal_case must register its exact
selected images through the existing real Operator owner, returning those values
for typed/public approvals. Tests must forward those exact values rather than
manufacture new identity/configuration. Preserve all authority/rollback/replay
assertions. Intentional historical multi-policy and T1-incompatible-policy tests
require retained fixture treatment, not silently changing their expected facts.

QA plan review independently confirms model-scope and PRE-budget tests detect
specific simulated defects. Add matching-hash retained duplicate/order negatives
for both phases because new-input cardinality now rejects earlier. Pure public
input/saved-POST projection tests pass10 in4.33s; configured MCP snapshot/backend
OpenAPI comparison passes78 in237.76s. MCP lifecycle remains running.

Caller trace extends the same fixture migration to guide_activation/pg_support,
post_submit_materialization_helpers, tasks/test_submission_lineage and the
projects policy_bundle/submission_policy fixtures; they explicitly forward their
own absent defaults. Authorization guide_proposals approval tests also consume the
same proposal_case choices. Preserve explicit absence for historical/late-register
scenarios. Focused database run initially refused the admin URL's plain postgres
scheme before provisioning; corrected to required postgresql+asyncpg for owned
loopback test database. No production database or guard changed.

Expanded pure replay passes85 in22.91s (/tmp/submission-cardinality-pure-v3.log):
policy cardinality/historical identity/order/budget, trial and evaluation-context
selection, approval replacement/attachment inputs and saved POST projection.
Evaluation-context no-write negative now additionally proves both actual registry
reads occurred, preventing an early cardinality denial from falsely satisfying it.
Proposal-case normal setup registers exact real images; explicit None remains an
unregistered setup opt-out for the later-publication test, which now rejects empty
approval and registers both images before its existing replay/conflict assertions.
The selected5 PostgreSQL/public approval cases are running against isolated0081;
MCP lifecycle process is live and progressing, neither yet counted as passed.

Still required in this cardinality change: complete shared policy_bundle and
submission_policy fixture migration, successor and remaining CLI/API/auth approval
callers, historical incompatible T1/multi-POST proof preservation, actual database
results, structural inventory/affected gates/docs and frozen ARCH/SEC/QA/client
review. No push or readiness claim at this checkpoint.

Focused5 real PostgreSQL/public approval cases pass in124.70s at0081;
/tmp/submission-cardinality-approval-db-v2.log/json records exit0 and complete
isolated database/role cleanup. Worktree evidence is based onfac8ea511; subsequent
fixture edits are not covered by that result. Shared policy-bundle approval now
registers explicit controlled fixture selections through the real Operator owner;
explicit empty inputs remain rejected. Extend directly affected scope to activation
successor/late-registration and locked_policy_custody tests. Successor selects real
registered images; locked-context refusal reuses exact original stored approval
choices; late-registration explicitly opts out of fixture registration until its
own publication step. Original lifecycle/hash/replay/denial assertions remain.
Broader affected approval/activation database replay is now running as v3.

Additional SQL boundary audit:0066's guide_approval_attachments_valid accepts
coherent zero/multiple selection arrays and protects retained evidence; tightening
it globally would invalidate historical approvals, including non-null request_json
rows from0066 through0081. ARCH/SEC confirms the correct extension is a new0082
migration replacing only require_current_guide_proposal_approval, already attached
BEFORE INSERT. Preserve its current request/schema checks; require safe JSON array
types and exact length1 in both request phases and locked plan phases. Do not alter
the deferred validator or old rows. Scope includes the new migration and focused
SQL insertion/preservation tests. Verify coherent zero/two new inserts fail at the
specific new guard, current1/1 owner approval succeeds, and retained null/non-null
old-cardinality rows remain readable under unchanged custody. Wait for running v3
schema proof to terminate before editing migration head.

Historical T1 review rejects a project-only fake as equivalent old-row proof: TASK's
frozen PRE hash would not match the zero-PRE projection. Preserve a genuinely
coherent retained TASK/PROJECT fixture for no_pre/no_post; fault-injection tests
may supplement but cannot replace that claim. The historical multi-POST visibility
proof likewise remains pending retained-custody migration.

MCP lifecycle replay finishes60pass in1244.70s; the prior process was slow but live,
not stalled or restarted. Structural validator exits0 with no ledger adjustment
(/tmp/submission-cardinality-structure-v1.log). Full backend Ruff, all98 CLI test
format checks, Markdown links and whitespace pass at this worktree checkpoint.
Broad database v3 remains live; do not infer its result from heartbeat output.
New schema guard and coherent historical fixtures are still incomplete, so no
frozen implementation review, commit or push is claimed for cardinality yet.

Historical fixture capture plan: use detachedfac8ea511 (before cardinality edits)
in an isolated0081 database to run the existing real no_pre/no_post approved TASK
fixtures. Capture exact nonempty public table rows plus actor/task/assignment and
namespace selectors, with fixed source commit and checksum. These are synthetic
test data only. Restore via the existing owned-database snapshot loader before
upgrading to0082; validate retained TASK/PROJECT context and original T1 zero-write
refusal after upgrade. This preserves the former integration assertion instead
of forging a mismatched port response. Allowed additions are a checksum-bound
historical policy fixture archive, concise loader/provenance and affected tests;
no executable old approval path in production, no locked row rewriting, no data
from user/provider environments. Capture scripts run only in detached temporary
worktree and isolated runner; main branch production changes remain separate.

Historical capture v2 passes2 in148.32s with0081 and full database/role cleanup.
Only the capture test was appended in the detachedfac8ea511 checkout; all original
source bytes match the commit. Archive policy_cardinality_history.json.gz binds
52nonempty tables/308rows per scenario, including actual non-null approval requests
with0/1 and1/0 phases. SHA256:
0b7cb10abc1c23864fac6c3be2b898caf297760192cc423e2f6f2c1e1862911c.
The checked-in capture text/provenance makes source and expected proof explicit.
Original T1 zero-operation/task-link/audit assertions now consume restored exact
TASK/PROJECT data through the same extracted intake_admission composition. Live
fixture setup always approves valid1/1; no fake historical context is introduced.
The existing snapshot loader checks ownership, exact rows/FKs and reinstated guards.
Restoration baseline and direct SQL negative are running before the0082draft is
installed; SQL negative is expected to fail until its new guard exists. Do not
count baseline as passing until terminal evidence is inspected. All new helper
lint/link/whitespace checks pass. Broader approval v3 remains live at0081.

Approval database v3 finished84pass in1174.75s at0081 with complete owned
database/role cleanup. Historical baseline finished2pass; SQL insertion regression
failed at the old uniqueness guard instead of the required cardinality guard,
confirming the new boundary was absent. Installed0082 only after both runs ended;
separate owned runs now verify upgraded historical refusal and current insertion.
Extend fixture scope to test_tasks and tasks/post_submit_routing/support: ordinary
new approvals must register a POST image by default instead of forwarding None.
Explicit None remains explicit; no production compatibility path is added.

0082 SQL replay initially stops at fixture schema fingerprint before test bodies.
The migration replaces only the existing BEFORE INSERT function; reset fingerprints
include function definitions. Extend allowed scope to tests/conftest.py pinned
EXPECTED_PUBLIC_SCHEMA_SHA256, updating0081 646811e5… to observed0082 35cf33c4…;
retain exact equality guard. Failed setup run cleaned its database/role completely.
Approval authority input replay passes19 in3.83s.

Historical upgraded0082 T1 cases pass2 in151.79s (37 unrelated tests deselected);
original zero-operation/task-pointer/audit assertions remain intact. Backend Ruff
passes for app/tests/new migration. MCP README now states the same exact1/1
approval input requirement as its checked contract and CLI instructions.

0082 SQL replay v2 passes2 in35.42s: real current approval/replay succeeds and
rehashed zero/two phase inserts fail at the named cardinality guard, leaving the
original approval unchanged. Reset/task replay passes6 in37.26s, including exact
schema preservation, schema-drift rejection and draft task creation with current
approval defaults. Structural validator v2 exits0 without ledger edits; Markdown
links pass15 changed files. Expanded SQL replay v3 independently varies request,
locked plan and both, with zero/two entries and null/object array-type violations.
This final expansion is running, not yet claimed passed. No cardinality commit
or full-goal completion is claimed; historical multi-POST and downstream current
producer migration remain required.

Expanded SQL replay v3 finishes2pass in25.07s at0082, complete database/role
cleanup. It checks24 invalid request/plan combinations plus current approval and
replay, and exact unchanged original approval row. Fresh origin/main fetch remains
94334ccf4085c26c7bfaa054465fc05cfbdad1fc; current branch is0commits behind.
All processes started for this migration checkpoint are terminal. Full goal remains
active, with no readiness or full-suite success claim.

Historical multi-POST preservation: capture the unchanged per-binding revision
journey at pinned main94334ccf4085c26c7bfaa054465fc05cfbdad1fc (schema0068),
where its original prepared-admission producer is still authoritative. A temporary
detached checkout adds only an observer test: snapshot accepted successor custody
and synthetic MinIO objects immediately before POST, then allow the original
test to complete all grant/visibility/replay/immutability assertions. Capture all
three role combinations. Only successful original journeys qualify as fixtures.
Allowed scope: captured synthetic archive/provenance/loader and existing revision
materialization test, with no production compatibility path or locked-row edits.
Current-head replay must drain retained accepted POST and preserve every distinct
visibility assertion. Native/AWS qualification remains separate.

QA provisional multi-POST plan review confirms endpoint-bound namespace cannot
be rewritten for CI. Use captured bytes only for current owner/grant isolation;
retain separate current real-MinIO single-image revision coverage as a required
proof. Capture observer preserves original test bytes and writes only after all
original assertions pass. First available archive is predecessor_submission_archive:
71tables/388rows,2objects, SHA256 cf6d55f9ed34334b86697961af192233a94097368ca777fc20e33527f0746fc2.
Both objects match exact retained replica/content hashes and sizes. Other role
cases are still running under owned runner handle38676, metadata/log
/tmp/submission-multipost-capture-v1.{json,log}; no whole-run success claim.
Portable restoration fixture drafted at /tmp/submission-multipost-fixture.py,
not installed: checksum/provenance/role validation, bounded read-only exact-ref
store, coordinator reread after upgrade, real current materialization. QA requires
original grant/context/SQL/replay/foreign-request/cleanup assertions unchanged.

Capture v1 is terminal:2pass/1fail in391.68s, all database/role/MinIO cleanup
complete. Archive-only and findings+archive original journeys passed; findings-only
was cancelled at ArtifactScratchManager.reserve_bytes/run_blocking_cancellation_resistant.
No timeout/guard changes made. Replay only that unchanged failed role in isolated
/tmp/submission-multipost-capture-findings-v2.log/json to distinguish a repeated
behavior from the first run cancellation. Do not count findings-only as captured.

Installed an explicitly incomplete two-variant multi_post_history archive to
exercise current upgrade while the missing-role recapture runs; not committed or
published. Current restore v1 selects only captured roles1/roles2. Replaced original
test setup with historical_revision_material; AST comparison confirms every
statement from successor materialization through visibility/SQL/cleanup/replay/
foreign-assignment assertions is identical. Actual original producer/helper source
is preserved by pinned capture provenance, not retained as an executable current
approval path. Full3-case replay and capture provenance remain pending.

Findings-only unchanged recapture v2 passes1 in202.15s, complete owned DB/role/
MinIO cleanup. All3original role journeys now have successful captures; first-run
cancellation remains recorded, with no timing/budget changes. Each snapshot has
71nonempty tables/388rows and2objects. Do not replace the partial archive while
restore v1 handle92448 is still live; its imported checksum must stay consistent.
After that run terminates, consolidate all3snapshots and replay the missing role.

Historical multi-POST current replay completes: roles1/roles2 pass2 in184.14s;
roles0 passes1 in55.85s. Both runs finish at0082 and clean owned database/role.
All original successor assertions retain identical AST; the fixture additionally
rereads the exact request through current coordinator after upgrade. Final3-role
archive SHA256 acde3375a3e96603868480fff9ffbb4492fe62ef3a89f9348e2ac9caddaae552,
146399bytes; existing two snapshots are byte-semantically unchanged after adding
the third. Ruff app/tests/new migration passes; structural validator v3 exits0
without ledger changes; Markdown links pass16 changed files. All processes started
for this checkpoint are terminal; QA plan review completed, implementation review
is still pending. Current real-MinIO single-image revision and shared producer
cutover remain required; no cardinality commit, full CI or full-goal claim.

Current producer cutover prerequisite: retained_material_fixtures still constructs
SelectedPreSubmitExecutionService(materialization=), and submission_fixtures then
uses the retired hidden prepared-admission creation operation. Replace this shared
producer with raw ZIP T1/upload/source PRE/T4 and production outbox T5. Preserve
fixture-private packet fields only around build_submission during T5; do not fake
source/PRE/acceptance rows or skip AUTH. Allowed files: retained_material_fixtures,
submission_fixtures, checkers/execution/storage_fixture and directly affected
tasks/submission_dispatch/test_concurrency (its competing ready-admission premise
is replaced by competing T1/finalizer proof). Keep actual old object bytes for
historical migration consumers, and share complete source state by factory and
namespace. Tests use existing current-task, revision/history/acceptance consumers;
architecture/security/QA review remains required. No production compatibility path.

Retained source replay v1 reaches real T1 and rejects the old symbolic provider
profile "test" created by committed_guide_fixtures. Extend allowed fixture scope
to that default namespace constructor: use canonical local-v2 descriptor/hash
through ArtifactStoreNamespaceIdentity/artifact_store_namespace_material from
the start of new guide setup. This remains an explicitly scripted byte provider,
not a filesystem/deployment proof. Existing retained rows and real provider
namespace overrides are unchanged. No production qualification guard is relaxed.

Retained source v2: initial owner/SQL lineage test passes; revision-history test
reaches accepted T4 then leaves T5 unfinalized (1pass/1fail,94.85s). Added an
observing wrapper around the unchanged production finalization handler so the
next exact-case replay exposes the underlying exception that OUTBOX classifies
as uncertain; no retry/guard bypass. /tmp/submission-retained-revision-v3.log/json
is running. Current concurrency replacement passes2 in60.09s: pause exact source
observation during a real OUTBOX T5 claim, refuse duplicate delivery or a new-key
T1, then assert one operation/Submission/dispatch/checker and one event per phase.
All completed runs cleaned owned database/role. ARCH/SEC in-progress review finds
no blocking fixture composition issue; scoped proof excludes provider/VM and
private-packet/source equality. Remaining role-race/rollback/material producers
still need current acceptance-path migration; no compatibility alias retained.

Verified production revision defect: retained revision replay v3 fails125.19s
at T5 admission INSERT with SQL CheckViolation "revision admission context
unavailable" from0043 guard_revision_admission_context. The trigger still reads
a prepared durable intent and requires needs_revision/current deadline, despite
source T4 having accepted custody and moved TASK to evaluation_pending.0074
updated the verified-lineage guard but omitted this revision guard. Scope extends
to new0083 migration and pinned test schema fingerprint, plus focused accepted
revision SQL substitution tests. Proposed change delegates source rows to existing
require_source_submission_admission (complete acceptance/PRE/actor/task/assignment/
revision-id/hash/predecessor/remediation validation); preserve old trigger body
exactly for non-source rows. A11 requires accepted work to survive delayed workers
without renewed contributor/deadline eligibility. No old row rewriting or guard
disabling. ARCH/SEC plan review requested before installing migration.

Revision continuation plan correction after ARCH/SEC inspection: 0043 also guards
Submission insertion and deferred revision deadline. 0083 must adapt all three
source paths, binding the exact accepted operation, source admission, immutable
revision preparation/lineage and continuation authority. Preserve non-source
branches. At T4 add preparation target/current TASK lineage and current routing
fence checks to require_submission_acceptance_current; these are eligibility
checks and must not recur after acceptance. Risk: high authorization/atomicity.
Acceptance: actual failing revision journey succeeds; invalid source/revision
bindings fail; acceptance refuses stale target/fence; delayed accepted work does
not recheck contributor deadline. Allowed files remain 0083, schema fingerprint,
focused existing intake/revision tests and this record. No retained row rewriting,
new public API, provider qualification claims or compatibility producers. Human
review focus is exact T4/T5 authority boundary; ARCH/SEC and QA review required.

0083 candidate installed: T4 adds exact revision project/target lineage/current
routing fence checks. All three old revision guards delegate accepted source
custody to the existing admission validator and a new exact Submission bridge;
the BEFORE bridge uses TASK active operation and the deferred bridge uses finalized
Submission identity plus consumed admission and commit authority. Non-source
branches remain unchanged. ARCH/SEC code-scope provisional PASS; no full proof
claim. Schema upgrades successfully; first run stops at expected fingerprint
mismatch 4f2fa4c887c1fe29c555b4af534227535c7b28b2ddccc53013c1e62eba8625a5,
now pinned. v2 /tmp/submission-revision-0083-v2.log/json runs actual revision
history with five finalized-record substitution probes plus reset tests. Ruff
and structural validator pass (structure log /tmp/submission-revision-0083-structure.log).
QA identifies outstanding direct preinsert and T4 stale target/fence cases and
expired-after-T4 replay. Existing expiry fixtures disable immutable triggers or
rewrite pre-preparation history; they are not no-bypass current-source evidence.
Use retained_intake/finalize_retained_intake split for new current boundary tests.
No commit/push or full-goal completion claim at this checkpoint.

0083 v2 terminal result: 32passed in236.32s; migration head0083; owned database
and role cleanup complete. This includes the previously failing real source
revision T4→OUTBOX T5/history journey, five finalized-record forged lineage
refusals, and database reset suite. Current blocker is repaired for this concrete
journey; acceptance/preinsert/deadline proof gaps above remain open. All local
processes started for this checkpoint are terminal. No full CI/provider claim.

0083 next proof increment: extend allowed test scope with
backend/tests/tasks/submission_dispatch/accepted_revision_probes.py and the existing
retained revision history case. Observe real T5 immediately before repository
Submission insertion; require a valid committed=false control and reject forged
revision lineage and source admission/preparation/predecessor/remediation records
inside savepoints, then invoke the unchanged repository insertion. No provider,
authority, SQL trigger, clock, or durable owner mutation bypass. Keep these
preinsert probes distinct from committed=true history probes. QA review will
assess actual boundary coverage; expiry and T4 stale-current evidence stay open.

T4 stale-fence proof design: stage real acceptance with unchanged owner, reserve
a legitimate generation2 predecessor checker evaluation inside the same root
transaction, then let deferred SQL validate commit. Expect named revision
acceptance refusal and complete rollback of receipt/event/Submission/admission.
This tests the new database fence check after Python context preflight; no raw
fence update, trigger disabling, or mocked eligibility. Add one existing task
client test and a scoped observing helper in accepted_revision_probes.py.

Expiry proof scope: add explicit long-running
backend/tests/artifacts/revision_deadline_drill.py (run by direct pytest path;
not ordinary test_ collection) and expose revision_deadline_hours on existing
create_active_project/create_policy_bundle_for_guide fixtures, default unchanged48.
Drill approves actual one-hour policy, creates genuine revision T4, observes
PostgreSQL time until its original deadline, then runs production OUTBOX T5.
No clock override, immutable-row edits or trigger bypass. This is scripted-store
owner/SQL timing proof, not provider/native qualification. Run with isolated
runner timeout4500; retain exact terminal result before claiming A11 evidence.

0083 v3 preinsert probes exposed test savepoint lifetime: SQLAlchemy ROLLBACK TO
left a PostgreSQL subtransaction active; later checker root pg_export_snapshot
correctly refused. No production relaxation. Probe helper now explicitly issues
SAVEPOINT, ROLLBACK TO, RELEASE for each rejected composite. v3 failed61.84s,
owned DB/role cleanup complete. v4 terminal: 2passed163.23s, cleanup complete;
real preinsert false-branch controls/source substitutions + original finalized
history probes + exact T4 stale-fence commit refusal all pass. One existing
storage_request generation2 Pydantic serializer warning remains visible.

Deadline drill v1 intentionally interrupted after QA found wrong POST event-name
oracle; cleanup complete. Corrected to canonical REQUEST_EVENT. v2 intentionally
interrupted before waiting an hour to batch final QA request: invoke production
finalizer twice within the same still-live OUTBOX invocation after deadline and
require identical full creation results. Cleanup complete. v3 now runs exact
final drill at /tmp/submission-revision-deadline-drill-v3.log/json, timeout4500;
do not restart merely for silence or elapsed observation. No expiry pass claim
until terminal evidence. QA code review confirms meaningful preinsert and
same-transaction T4 fence coverage; stale-target case remains open. No reviewer
is running, no full-goal claim, and only original PR708 remains authorized.

Shared material producer cutover scope: post_submit_materialization_helpers.py,
retained_material_fixtures.py, tasks/submission_dispatch/test_concurrency.py and
test_rollback.py, plus directly affected source-read assertions. Replace retired
_verified_admission/hidden create with actual raw ZIP source intake and OUTBOX T5
using real existing local/MinIO provider. Preserve exact archive mode bytes and
POST request reads. Custom producer hooks move to foreground submission so role
races test T4 authority; rollback cases move to accepted T5 and retain acceptance
receipt/event while refusing partial finalization. Do not add compatibility
aliases or a second producer. Retain creation_request projection only for existing
current downstream consumers, explicitly trace remaining old revision callers.
Risk high owner/AUTH/atomicity; focused real PG/local+MinIO execution, race/rollback
checks and required ARCH/SEC/QA review before commit. No provider qualification
claim from controlled portable project runtime. One-hour deadline v3 remains live.

Material source cutover implemented: exact archive bytes now traverse _foreground
and production OUTBOX T5; current dispatch result read from persisted owner row.
Removed prepared admission/hidden creation from this shared producer. Role race
hooks now pause T4 prepare_acceptance and prove already accepted work survives
later contributor revocation. T5 rollback tests preserve evaluation_pending,
acceptance receipt and finalization event, while requiring no source admission,
Submission, binding, CheckerRun or POST event after a failed participant. Current
selected POST fixture asserts one entry. CountedStore implements exact open_source;
real MinIO fixture enables bucket versioning. Remaining downstream old revision
helpers and composition/replay callers are traced, not treated as passed.

Material v1 terminal2fail81.32s: portable PRE lacked its directory and role race
never reached T4. Added mkdir with per-task unique source-runtime directory.
Material v2 terminated at collection because test imported ArtifactAuthorityDeniedError
from wrong module; corrected to artifacts.schemas. Both owned DB/role cleanups
complete. Structural validator v1 exited0, no debt ledger change. v3 now runs
local+MinIO execution/replay, T4 revocation race and seven T5 rollback cases,
/tmp/submission-material-source-v3.log/json. Deadline drill v3 remains active;
confirmed real accepted revision in workstream_test_906ae3a89dbc and original
PostgreSQL deadline2026-11-16T19:25:25.361833Z. No deadline result yet.

Shared producer ARCH/SEC code review complete: no further concrete bypass found;
portable-runtime versus real-provider proof scope retained. v3 remains live with
runner-owned MinIO bucket workstream-ci-isolated-4b500b25f9c9 and database
workstream_test_4b500b25f9c9. Seven rollback cases collect successfully. Latest
Ruff/diff checks pass. Fresh origin/main fetch remains94334ccf4; HEAD167ahead/0behind.
No merge/rebase needed at this checkpoint. No results inferred from live run.

Material v3 terminal: 8passed/2failed289.58s; owned DB/role/MinIO cleanup complete.
Passed local source POST/replay, T4 role revocation race, five staged participant
rollbacks and unmanaged-savepoint refusal. MinIO POST returned infrastructure_failed;
add materialization exception diagnostics before rerunning that exact case. Revoked
binding denies via PreparedAuthorizationUnsupported at fixed-service resolution,
not ArtifactAuthorityDeniedError; corrected exact assertion, no runtime change.
v4 /tmp/submission-material-source-v4.log/json runs only the two failed cases.

Next traced shared consumer within cutover: tasks/post_submit_routing/support.py
_create_submission still prepares/verifies and calls hidden create for sibling and
revision successors. Extend allowed scope to that producer. Extract the already
implemented current archive->source->T5 composition as create_source_submission
in post_submit_materialization_helpers.py and reuse it from both initial and
routing producers. Keep exact metadata revision acknowledgment from locked TASK,
whole real underlying store and persisted dispatch.result; no compatibility
producer. Use unique runtime directory per invocation so revision of the same
TASK cannot collide. Verify existing sibling, successor/routing and previous
version denial cases; current live-MinIO revision qualification still separate.

Material v4 terminal1passed/1failed80.50s, owned DB/role/MinIO cleanup complete.
Revoked binding test now passes exact fixed-service denial. MinIO diagnostic shows
ArtifactPreparationDeadlineError, followed by async-generator aclose-already-running
teardown errors. Fixture inherited 2-byte provider buffers from adapter vectors;
normal material execution will use bounded64KiB, matching existing source POST
fixture, without increasing any deadline. The cleanup symptom exposes a production
gap: PostSubmissionMaterializationService passes open_source directly to prepare
without closing that closable generator if preparation fails while suspended at a
yield. Extend bounded scope to post_submit_materialization.py and existing
materialization tests. Register exact-source generator closure in AsyncExitStack
with cancellation-resistant await; retained non-source iterator contract unchanged.
Regression must open real local/MinIO source, fail scratch write after first chunk,
and prove provider generator closed before failure returns, no consumer entry,
no active scratch. ARCH/SEC/QA review required before commit; no workaround by
relaxing timeouts or silently discarding the observed cleanup defect.

Routing source v1 terminal3passed103.52s: sibling mixed-lineage denial, old-version
routing refusal after real successor, and superseded-checker reserve/replay denial.
All use current archive source/T4/T5 composition; owned DB/role cleanup complete.
New cleanup regression added to test_post_submit_materialization.py: wrap real
provider open_source; fail scratch write after first chunk; require generator
finally completed before error return and zero scratch/consumer entry. Running
local baseline against unchanged production owner at
/tmp/submission-source-close-before-v1.log/json before installing closure fix.

Source close baseline fails exactly: first553-byte chunk written, closed count0,
30.64s, cleanup complete. Source close after-v1 passes4 in90.82s: real local/MinIO
first-write failure cleanup plus both normal execution/replay journeys; owned
DB/role/bucket cleanup complete. Production source generators now register on the
existing AsyncExitStack before scratch preparation. Final callback creates one
close task, shields/drains it despite repeated cancellation, preserves caller
cancellation only after successful closure, and maps ordinary or self-cancelled
close failures to ArtifactScratchIntegrityError (not a normal terminal material
failure). This follows ARCH/SEC review; generic preserving-cancellation helper
would suppress close errors during cancellation, so the callback explicitly lets
cleanup uncertainty win.

Keep the new cohesive regressions in backend/tests/artifacts/test_post_source_cleanup.py
instead of enlarging the existing materialization suite. Added real local/MinIO
repeated-cancellation draining and pure ordinary/self-cancelled close-failure
controls. after-v2 /tmp/submission-source-close-after-v2.log/json now verifies all
six cleanup cases plus local/MinIO normal execution against final callback. Ruff
and diff checks pass; no final result yet. Deadline v3 remains the same live run.

Final source-close structural check exits0, no debt-ledger edits. QA scoped code
review finds no additional defect; independently verified compound cancellation
then late-close-error probe exits0 and preserves original cause/integrity failure
(/tmp/submission-post-source-close-qa-compound.log). Final eight-case v2 still live
handle43563; deadline v3 same handle59321. No reviewers remain running. No final
execution/goal/signoff claim before terminal receipts; no commit/push yet.

Final cleanup v2 terminal7passed/1setup error150.91s, owned DB/role/MinIO cleanup
complete. Asyncpg raised UnicodeDecodeError while decoding canonical schema
inventory before the local first-write case executed; no owner assertion failed.
Keep this environment failure open, do not mask/skip it. Exact unchanged local
case replay runs /tmp/submission-source-close-after-v3-local.log/json. The seven
completed cases include MinIO ordinary cleanup, both repeated-cancellation paths,
both unconfirmed-close errors and both normal provider execution/replays.

Continue existing test_post_submit_materialization.py consumer cutover: use
actual selected POST processor with controlled registered-image adapter and exact
execution lease instead of synthesizing empty-policy results. Adapt existing
provider fault/lock hooks to open_source (closable generator), and protect source
reads as well as object reads in binding-consumption proof. Preserve foreign-result
refusal by rehashing a completed actual result with mismatched generation. Existing
manifest-corruption behavior will be checked, not weakened speculatively. Scope
is directly affected tests, no new runtime compatibility path or policy relaxation.

Unchanged local source-close replay v3 passes1 in27.04s; owned DB/role cleanup
complete. All eight targeted final-callback cases now have passing evidence
across v2+local replay, but prior asyncpg schema-decoding setup error is retained
as unresolved environment evidence, not claimed repaired. Existing whole POST
materialization owner suite now uses actual selected processor/lease and source
read hooks; running /tmp/submission-materialization-owner-v1.log/json and scoped
structure validation. No current-owner suite pass claim yet. Source cleanup
production/code review is complete; broader acceptance and native qualification
requirements remain active.

Next bounded proof cutover: test_evaluation_revision.py must create its consumed
revision using create_source_submission, actual raw ZIP PRE/T4 and OUTBOX T5.
Allowed files are that test and this record; preserve every revision-read,
rebase, substitution, replay and no-mutation assertion. No production changes,
historical-data rewriting, guard relaxation or compatibility helper. Risk is
test fidelity; verification is the entire four-case owner file on isolated
PostgreSQL plus Ruff and structural validation. QA/test-delta review should
compare the old assertions and current producer custody. Human focus is whether
the revision selector is exercised against the same actual source-backed
submission the public intake now creates.

Structural diagnosis: frozen Python diagnostic run exits0, system Python exits139
in garbage collection during ast.parse in coverage_policy.py. This is unresolved
interpreter/environment evidence, not proof of a validator defect or its repair.
Both materialization-owner and real deadline integration runs remain live.

QA-EVAL-001 found an affected shared producer in test_revision_exhaustion.py:
_submit_initial_after_reclaim still invokes the removed preparation endpoint.
Expand allowed test scope to this helper and its direct callers. Preserve HTTP
claim and submission boundaries, inject the real foreground owner with controlled
runtime through the configured command, then run production finalization. Keep
all caller assertions. Verify reclaimed-contributor isolation and existing
exhaustion/reclaim callers; do not claim an unrun caller passes.

Environment evidence at 2026-11-16 19:07 UTC: owned PostgreSQL log records backend
PID2068 killed by signal9 while updating project_setup_runs.documents_ready_at;
server terminated other connections and recovered. Before death host process
235582 used35.4 percent of16GB RAM. This is not a diagnosed application or
hardware root cause. Preserve affected run receipts. Evaluation v1 had loaded
the superseded reclaim helper; deliberately SIGINT that test process only after
repair, terminal exit2 with1passed404.65s and runner cleanup_complete=true.
New six-case current candidate run is /tmp/submission-evaluation-revision-source-v2.log/json,
including full evaluation-revision file and both zero-cap reclaim modes, failfast.
Ruff/diff checks pass. Structural /tmp/submission-evaluation-revision-structure-v1.log
is pending. Main materialization and deadline runs were not restarted.

Materialization owner v1 terminal3failed/14passed948.09s, cleanup_complete=true.
Quota case failed during setup at the exact PostgreSQL UPDATE killed19:07UTC;
consumer-deadline case hit outer10s while revalidating audit custody, not during
consumer waiting. Replay those two unchanged before any timeout/production change.
Stored-manifest corruption now fails earlier in require_source_submission_admission
with23514 before provider I/O; the old expected late manifest error is obsolete
for this source-backed fixture. Bound test repair to test_post_submit_materialization.py
and new cohesive artifacts/test_post_source_manifest.py: retain corrupt-database
rejection with exact SQLSTATE/provenance and zero provider/consumer calls; separately
inject changed executable semantics from the controlled inspector over exact source
bytes and require independent manifest mismatch before consumer/export. Preserve
cleanup assertions. No production guard changes. QA/test-delta review must verify
both distinct boundaries and a discriminating mismatch-check removal probe.

QA/test-delta confirms reclaim helper preserves HTTP/authenticated identity and
returns stored dispatch fields required by all traced callers. Its extracted
helper control and actor/metadata substitution probes pass
(/tmp/submission-reclaim-qa-auth-probe-bounded.log); these are not database proof.
QA independently ran exact new semantic-manifest test against exact materialize
method with controlled DB selection and real scratch/inspection: baseline passes,
removing only the semantic digest comparison fails at forbidden export
(/tmp/submission-source-manifest-qa-probe.log). Both boundary assertions remain.
Removed obsolete pre_submit_evidence_sets mutation from stored-corruption test
(source admissions do not link that table); replay final exact case after v2.
Frozen current test candidate; Ruff/diff pass. Revision structural run exits0;
new manifest structural run /tmp/submission-post-manifest-structure-v1.log pending.
Fresh origin/main fetch has167ahead/0behind; sole draft PR708 still points fac8ea511.
No native/provider/full-goal completion or new commit claimed.


Checkpoint verification: materialization owner focused replay passes4 in345.70s;
revision/reclaim passes6 in710.46s; real one-hour revision deadline drill passes1
in3680.50s. All three isolated runner receipts confirm cleanup complete. Source
cleanup, historical replay and policy-cardinality evidence remain as recorded
above. Python lint, Markdown links and structural validation pass. Native/provider
qualification, broader full-suite proof and full-spec acceptance remain unfinished.
This checkpoint does not mark PR708 ready or the active goal complete.

Bounded implementation: spec5.5 pending operation in TASK detail/work-context.
ARCH/SEC design review recommends TASK-owned typed port, ART bridge on exact
request session/context, reuse existing authorized operation reader and stage
derivation. Allowed files: TASK pending-operation API, detail DTOs, authorized
commands, TASK/ART composition, request dependency, focused task/operation tests,
affected wire contracts/docs and this record. No schema migration, provider
bootstrap, second root transaction, alternate stage logic or relaxed authority.
Expose operation ID/stage only to assigned contributors with operation-read
authority and authorized managers. Other visible TASK reads retain null. Only
genuine AUTH-denied reads may suppress the projection with staged denial retained;
missing/corrupt pointer or unavailable composition must fail closed. Embed field
in detail so work-context shares it. Preserve predecessor as historical evidence.
Risk: authorization and cross-owner transaction visibility. Required ARCH/SEC
implementation review plus QA proof: own/manager/non-owner/revoked authority,
active stages, revision pending, T5 clear, corrupt pointers, no provider I/O and
OpenAPI/JSON nullability; existing detail/work-context regression checks. Human
focus: no pending-operation identity leakage through broader task visibility.

Terminal evidence: materialization owner v2 passes4 in345.70s, cleanup complete;
revision/reclaim v2 passes6 in710.46s, cleanup complete. Real one-hour deadline
v3 passes1 in3680.50s, cleanup complete: original deadline remained unchanged,
accepted revision finalized after it and exact replay produced one Submission
and POST dispatch. Manifest structural check exits0. Environment root cause
from prior killed PostgreSQL/native Python failures remains unresolved.

Pending-progress implementation scoped ARCH/SEC code review finds no defect;
execution proof remains separate. Initial v1 fails after successful owner/manager
pending reads because test incorrectly expected non-owner assigned-task visibility.
Actual current TASK authority conceals it with404. Preserve existing visibility,
repair that expectation without broadening product access. V1 cleanup complete.
V2 tests initial/revision, receiving/PRE, revocation, missing/cross-task selector,
missing reader, OpenAPI and final stored-manifest corruption; pending.
Extend affected client scope to the four CLI task/detail-context decoders and
their HTTP tests, plus four transitive MCP contract snapshots. Go API package
tests pass; build /tmp/workstream-pending-progress-cli succeeds. Native CLI and
MCP OpenAPI drift checks running. Operator manual documents the nullable field;
roadmap reconciliation remains required before full PR readiness.

Boundary validation found new ART adapter importing private AUTH runtime to
classify denied operation reads. Do not expand the frozen import ledger. Extend
allowed AUTH API/service scope with a typed IntakeOperationReadDenied subtype,
raised only around AUTH's operation-read kernel denial; ART consumes that public
type and never inspects private AuthorizationDenied. Existing base-error callers
retain identical denial behavior. Replay ARCH/SEC and module-boundary validation.

Module inventory also exposed one new private ART repository edge from the new
adapter file. Move PendingSubmissionReader beside the existing configured reader
in adapters/artifacts/__init__.py; remove the new file and update imports. Exact
private-edge sets now match: module-boundaries v3 exits0, no ledger changes.
ARCH/SEC narrow replay passes code scope, including typed denial staging behavior.
CLI HTTP v1 had18pass/1failure: prior fixture lacked the new nullable field in
complete text projection. Update shared detail fixture and add visible pending
identity/stage to contributor/manager text detail. Rebuilt CLI v2 passes19 in108.40s.
MCP live OpenAPI/transitive-snapshot checks pass78 in45.16s.

Pending PG v2 completes5pass/3fail403.57s, cleanup complete. Failures are test
oracles: initial Submission history is concealed until a Submission exists;
revoked sole Submitter loses task detail/work-context before ART read. Preserve
these404 boundaries, assert initial stored Submission count0, and check TASK
denial audits. QA additionally identified seeded manager fallback and weak
cross-task negative: remove fixture manager grants through real API before own
authority tests; add two real tasks/operations with valid controls then swap
selectors. Add actual stalled-OUTBOX fixture and manager post-T5 null checks.
PG v3 running. Reviewer-retained owner detail is a distinct legitimate200/null
case: issue Reviewer, revoke Submitter, require committed ART denial audit while
work-context remains404. Its dedicated run is
/tmp/submission-task-reviewer-progress-v1.log/json. Full existing work-context
regression and final structural checks now running. No full-readiness claim.

Pending-progress checkpoint verification: PostgreSQL v3 passes 8 in 451.05s;
Reviewer-retained visibility passes 1 in 76.46s; complete existing work-context
regression passes 24 in 370.81s. All three isolated runner receipts confirm
cleanup_complete=true. CLI HTTP passes 19; MCP contract checks pass 78; Go API,
module boundaries, test structure, changed Python Ruff, and Markdown links pass.
Receipts record the pre-commit HEAD because these tests ran against the working
changes; they are not clean-commit CI attestations. ARCH/SEC and QA code reviews
found no remaining scoped defect; final clean-candidate review is still required.
Downstream completion tests remain running, and full specification qualification,
roadmap reconciliation, provider qualification and complete CI remain unfinished.

Downstream current-source run completes 3 passed/2 failed in 263.13s, cleanup
complete. Both production-registry cases still assume an empty POST policy and
remove execution configuration; current selected policy correctly produces an
infrastructure failure. Bounded repair scope: test_completion.py and this record.
Use the existing ControlledSelectedExecution at the configured external port,
assert one selected execution/member, retain actual production OUTBOX registration,
AUTH, materialization, completion, atomic acceptance/awards and replay assertions.
No production owner, policy bypass, new fake acceptance, or provider qualification
claim. Risk: test validity; QA review and both production-registry cases required.

Frozen pending review found CLI omission accepted as null although the field is
required by the intended CLI projection contract. The generated OpenAPI DTO
schema permits omission because the backend field defaults to None. Repair scope: contributor_tasks.go, task_context.go,
tasks.go shared management detail decoder, and test_task_pending_http.py. Require
key presence while retaining explicit null; prove omission rejection and null
success in all four readers. No backend authority or schema change. Replay Go
API and four HTTP readers; ARCH/SEC closure required on the final clean commit.

Corrected production-registry cases pass 2 in 185.64s with cleanup complete
(/tmp/submission-current-source-outcome-v2.log/json). CLI omission regression
fails against prior v2 binary as intended; corrected Go API passes. Expanded CLI
run passes 24 and fails 1 because the existing manager minimal-response fixture
omits the newly required nullable field. Extend repair scope to that fixture in
test_task_http_boundary.py: retain explicit null in its required-key projection.
Focused unchanged-behavior replay follows; no decoder weakening.

Final manager minimal-response replay passes 1 in 5.20s. The expanded CLI run's
other 24 cases remain passing, including all four omitted-key/explicit-null
regressions. Changed Python Ruff and diff whitespace checks pass. Final clean
review replay remains required; no full-spec readiness claim.

Head62c138605 hosted preflight fails behavior_ownership partition_target_mismatch
(job133573919169); prior module/AUTH/structure checks and 92 architecture tests
pass. Exact inventory diff shows only missing
backend/app/modules/tasks/api/pending_submission.py, no stale targets. Bounded
repair scope: behavior_ownership.py existing SUBMISSION_INTAKE_TARGETS exact set,
partition.v1.json, existing exact-addition test, and this record. Preserve original
protected base, all retained assignments, group rules and unrelated-path rejection.
No new wildcard, bypass, reviewed behavior claim, or catalogue population. CI
integrity/QA review required; verify partition/catalogue plus validator tests.

Partition repair verification: complete behavior-ownership validator suite passes
170 in 8.77s (one unknown asyncio config warning with plugin autoload disabled).
Catalogue validation exits0 with existing unresolved population listed, not
claimed reviewed. Exact diff adds only the pending TASK API lifecycle assignment
and its digest; protected base and retained assignments remain unchanged. Ruff
and whitespace checks pass. Hosted rerun and scoped CI review remain pending.

Further hosted diagnostics before pushing the repair: every sampled backend lane
stops at missing_lane_modules for the four new cleanup/manifest/pending tests;
CLI API and HTTP jobs stop at Ruff format for test_task_pending_http.py. Extend
bounded CI repair scope to test_lane_catalogue.py and that CLI formatting only.
Assign both artifact tests alongside existing POST materialization and both TASK
progress tests alongside work-context; preserve completeness/error propagation,
SDK selection, infrastructure requirements and timeouts. No excluded/skipped test
or workflow weakening. Run lane validator tests and full CLI lint/format gates;
CI integrity review required on clean combined candidate.
Separately, current economic facts proof passes all three unpaid/one-award/two-award
cases in136.19s, cleanup complete (/tmp/submission-current-economic-facts-v1).
It verifies exact FinalAcceptance, ContributionRecord and award facts/replay with
no fabricated human Review; this remains controlled execution owner proof.

Lane validator first run:201pass/3fail20.11s. Failures are independent exact
membership assertions for the intended four additions, not runtime failures.
Extend scope to test_ci_lane_catalogue.py: add the two POST modules to expected
delivery membership, update project256→258/task94→96 canonical family hashes,
and project ownership hash. Preserve exact comparisons and negative controls.

Final lane catalogue/evidence/runner tests pass204; repository discovery now
covers all collected modules with exact ownership and unchanged rejection gates.
Full CLI Ruff check and format check pass99files; AST comparison confirms the
pending HTTP formatting changes no behavior. Scoped combined CI review and hosted
rerun remain required. No full-suite or provider qualification claim.

A12 target-change proof scope: test_tasks.py and accepted_revision_probes.py.
ARCH/SEC review establishes legitimate PM repair cannot commit a changed target
while active intake protects its locked snapshot (0069 deferred custody guard);
after T4, evaluation_pending also makes repair ineligible. Test completed real
revision PRE before opening T4, activate a genuine successor guide, call authorized
PM repair, require named custody rejection and rollback of TASK/preparation/audit/
outbox effects, then complete original T4/T5 under unchanged lineage. No trigger
bypass, fabricated acceptance, clock mutation or independent SQL target-check
claim. Keep existing stale-fence proof separate. QA/ARCH review and focused real
PostgreSQL execution required. This closes legitimate target-change interleaving
proof, not all A12 scenarios or provider/native qualification.

Current request-delivery local/MinIO baseline fails2 in96.58s, cleanup complete
including owned MinIO bucket. Real selected POST is unconfigured in the shared
old empty-policy fixture, yielding infrastructure_failed. Bounded fixture repair:
evaluation_delivery/support.py and test_delivery.py. Bind existing controlled
selected execution only while composing the test handler (captured constructor
port), preserve production registry/authority/materialization, and assert exact
one selected result/request. No product fallback, provider qualification claim or
runtime bypass. QA proof: full delivery file including lostack, revocation and
eligibility, real local/MinIO storage, then affected delivery consumers as needed.

Affected delivery-consumer trace finds old open(reference) hooks in custody and
worker materialization tests; current POST reads open_source(exact source).
Extend scope to those two tests: move pauses/missing-object injection to the
current port with kwargs forwarded, retain cancellation/unknown/cleanup guards.
Do not add a production alias. ARCH/SEC A12 code review requests explicit changed
v2-versus-locked-guide assertion; added. Final execution must include it.

Hosted86a preflight now reaches existing docstr gate and fails78.8% against80.
Scope documentation-only repair to new submission code: checker API source_contracts;
local_submission_source/source_cleanup adapters; ART intake acceptance/finalization/
finalization_delivery; ART API submission_recovery/submission_command/submission_cleanup/
submission_finalization; AUTH API submission_intake; TASK API pending_submission.
Document source identity, bounds, custody, cleanup and authority contracts after
reading implementations. Do not alter logic, annotations, interfaces, coverage
configuration or unrelated old files. Verify normalized AST equality excluding
docstrings, Ruff and unchanged docstr gate; docs review for accuracy required.

Final A12 target/fence replay passes2 in121.84s (existing serializer warning),
cleanup complete. Local/MinIO delivery passes5 in141.14s, database and bucket
cleanup complete. Two cancellation custody tests pass; three worker cases first
error because the runner omitted MinIO endpoint (no product failure), then fail
on obsolete Consumer(files) signature and one-event count. Pass the actual
material execution to Consumer and assert the two real T4/T5 request events;
retain all source cancellation and missing-object assertions. Replay entire
worker materialization file. Documentation review corrects removal wording:
provider deletes bytes, not custody; all MCP selected fragments remain unchanged.
Hosted CLI API collection exposes ambiguous historical fixture import from
conftest resolving CLI conftest. Extend scope to historical_submission_fixtures.py:
use existing tests.conftest qualified owner import, preserve database ownership
assertion unchanged. Verify collection of all four affected public modules.

Shared Consumer trace also finds obsolete one-argument consumers in authorization
post_submit test_principals/test_atomicity/test_live_authority/test_receipt_custody
and test_post_submit_selection. Extend scope to supply each existing real execution
lease, constructing consumers only for materialize phases. Preserve denial,
rollback and positive-control assertions; no optional/compatibility constructor.
QA also requires paused source wrappers to close their inner iterator in finally;
add explicit aclose forwarding in custody/worker tests, preserving cancellation.

Checkpoint evidence: final A12 pair2pass121.84s; local/MinIO delivery5pass141.14s;
signed CLI raw-ZIP progress/replay/history/suspension1pass129.46s. All receipts
confirm owned database cleanup and delivery MinIO bucket cleanup. Structural
validator v2 exits0. CLI four-module collection5nodes succeeds (existing custom
marker warnings). Source cleanup wording corrected per DOC-CLEANUP-001; QA-HOOK-001
addressed with deterministic inner iterator closure. All12 documented production
files retain identical executable AST excluding docstrings. Existing docstr gate
passes6957/8692=80.0%; all selected MCP fragments match actual generated OpenAPI,
so no snapshot regeneration is needed. Ruff and whitespace checks pass.
Full worker-materialization run and affected authorization/material consumer run
are still active; the final close-forwarding hooks require their focused replay.
Do not treat this checkpoint as full CI/provider/spec readiness. Hosted preflight
and CLI collection fixes still require rerun on the final pushed head.

Hosted transport replay repair scope: tests/checkers/external/test_runtime.py.
The single PRE transport matrix fails before exercising transport because
dataclasses.replace requires the reservation's explicit source_contracts InitVar.
Supply the existing ART composition dependency while replacing source facts;
preserve every tampering, deadline, transport and runtime assertion. No production
contract default or compatibility path. Low-risk fixture repair; verify the full
existing transport matrix and Ruff. Broader hosted failures in retired PRE and
replacement producers remain separate required migration work.

Transport replay first reaches11passing cases and exposes the slow-decode hook's
old signature. Forward the real source_contracts keyword through that hook;
preserve its300ms delay and deadline_exceeded assertion. Final transport matrix
passes12 in3.38s; Ruff and Commitrail checks pass. Final worker/custody hook replay
passes4 in111.54s on99d, with database and MinIO cleanup complete. This replays the
previous consumer timeout without extending its20s bound; it does not establish
the original timeout's root cause. Documentation review passes; QA code review
closes inner-stream cleanup finding, while full AUTH execution remains pending.
Hosted86a artifacts contain146 failing cases across completed lanes, including
42 obsolete preparation-fact callers and multiple retired PRE constructors.
Artifacts: /tmp/submission-ci-43947584976; failure index:
/tmp/submission-hosted-failures-86a.txt. Full CI remains incomplete and failing.

Review-history successor producer migration scope: reviews/decision/support.py.
Replace obsolete prepare/verify/hidden-create setup in _admit_successor with
existing create_source_submission, using the same actor, locked revision context,
exact predecessor, summary and corrected ZIP. Preserve all storage review,
finding carry-forward and predecessor assertions; no compatibility alias, direct
Submission insert or authority bypass. Medium risk shared lifecycle fixture;
verify its three consuming storage tests on isolated PostgreSQL, Ruff and test
structure checks. QA review must confirm the current producer does not weaken
the history guards. Existing review fixtures remain storage proofs, not public
human-decision authority claims.

Adjacent retry-fixture scope: checkers/execution/test_checker_retry.py.
Its missing-object injection still patches open, while current selected POST
reads open_source. Move the exact controlled provider failure to open_source and
accept its keyword arguments. Preserve material_unavailable, Operator receipt,
rollback and retry assertions. Verify local/MinIO recovery first, then affected
retry/authority consumers; QA review of this shared injection is required. No
production changes or weakening of expected infrastructure failure classification.

Local/MinIO retry pair now reaches actual Operator successor creation; both fail
on obsolete total-event count2 versus3 (T4 finalization plus two POST requests).
Update this file's exact total counts for the one retained finalization event,
explicitly assert that finalization event in the shared source fixture, and move
the independent concurrency fixture's identical old open hook to open_source.
Preserve all rollback/replay and exact retry receipt checks; no event filtering
that could hide duplicates. Replay provider pair and full affected retry file.

Successor verification: all3 existing predecessor-chain, finding carry-forward
and first-review-after-correction cases pass273.83s; owned database and MinIO
cleanup complete (/tmp/submission-review-successor-v1). Existing serializer
warnings remain. QA finds no code defect: same actor/revision custody, unchanged
history/finding assertions; all11 retry event totals increase exactly1 for retained
T4 and the new source assertion requires exactly1 finalization event. Ruff,
whitespace, Commitrail and initial structure validation pass. Full retry replay
(/tmp/submission-current-retry-v2) and prior AUTH replay remain live; this checkpoint
does not claim their success or whole-spec readiness.

PRE coordination fixture migration scope: test_selected_pre_submit_coordination.py
read-current replay, expired-lease read, execution capability and authority digest
proofs, plus their shared queued-row fixture. Use the existing _source_reservation
and real SelectedPreSubmitSourceCustody adapter; retain exact task/source locking,
changed-source replay rejection, lease identity and one-use/digest assertions.
Populate current source row fields without invented manifest/default inputs.
No production compatibility, retired admission capability repair or new alias.
Medium authority-test risk: run the four affected proofs and entire module to
separate remaining retired-contract failures; focused QA review required.

ARCH/SEC separates retained historical jobs from obsolete new preparation flow:
do not revive PRE facts via guide-source AUTH fallback. Bounded parent-lock scope:
test_submission_lineage.py, extract existing current task/assignment setup from
_prepared_packet, use it directly for owner-substitution and NOWAIT parent locks.
Replace verifier positive control in substitution test with exact canonical
parent-lock success. Preserve all four substituted owners, both held locks and
both released-lock assertions. Leave historical migration replay unchanged and
explicitly defer obsolete verifier/new-creation tests to subsequent conversion.
No extra product writer, authority bypass or duplicated lifecycle implementation.
Run the five parent cases on real PostgreSQL; QA review required.

Full affected AUTH/material replay terminates39pass1fail1342.16s. The sole
principals.finalize failure counts real setup materialization from final_facts as
denied-operation I/O. Extend scope to test_principals.py: snapshot source opens
after valid setup and require unchanged opens across denied operation, retaining
database snapshot, scratch/consumer and restored-authority positive control.
Do not clear observations or skip phases. Replay all three phase cases; QA check
must distinguish setup I/O from unauthorized I/O. No product authority change.

Coordination final targeted replay passes4 in1.58s. Initial full module85pass4fail
included three untouched retired-contract cases and the missing explicit invocation
receipt now repaired; those three old cases remain required work. QA finds no
scoped defect in TASK fixture split, current source coordination or principal I/O
baseline. Independent exact-test probes detect reusable capabilities and
outcome-insensitive finalization digests (/tmp/submission-coordination-qa-mutation.log).
Unrelated verifier/history test ASTs remain unchanged. Ruff, whitespace and record
checks pass; parent5/principal3/fullretry and structure validation remain pending
at this checkpoint. Do not infer full readiness from these focused proofs.

Public malformed-ZIP migration scope: artifacts/test_submission_foreground_command.py
and tasks/test_public_submission_intake.py. Extract the existing signed raw-ZIP
HTTP setup for reuse; preserve its four framing/replay tests. Replace obsolete
prepare-route malformed test with current submissions route: sealed upload precedes
real guest default inspection, bounded QC rejection preserves task/assignment and
creates no Submission/POST/finalization event, failed source remains cleanup-owned,
and corrected bytes with a new key accept. Keep response privacy assertions.
Do not restore removed preparation endpoints, suppress provider I/O, fabricate
PRE results or bypass task authority. Medium public-contract risk; run migrated
case plus existing four framing cases and QA review of changed outcome oracle.

Public first replay4pass1fail131.98s: rejection checks pass, corrected-key control
hits500. QA identifies reused simulated-worker pre-tree directory; corrected
invocation must use a fresh child root, without clearing retained source/charge.
Restore exact malformed default failure/no project result and zero admission
assertions per QA-MALFORMED-001/002. Check simulated-runtime errors before the
positive HTTP assertion to retain diagnostic cause; no response/production change.
Earlier pending receipts now terminal: parent locks5pass145.79s, structure pass;
full retry26pass813.55s with cleanup complete. Principal three-phase replay2pass
and one10s scratch deadline in restored materializer positive control; unchanged
limit single-case replay passes1 in29.81s, cleanup complete. Do not claim the
transient deadline root cause resolved or all-provider qualification.

Final malformed rejection/corrected-key proof passes1 in34.08s with owned database
and MinIO cleanup complete (/tmp/submission-public-malformed-v3). The unchanged
four framing/replay cases passed in v1. QA closes all three findings by inspection;
fresh worker root resolves the positive-control fixture failure. Ruff, whitespace,
record and structure checks pass. Current27531 hosted CLI API failure is now
concrete: three old _prepared_packet consumers and one registry409 fixture conflict;
they remain required migration work. Same draft PR708; no full-suite readiness claim.

CLI current producer scope: integration/test_manager_task_evidence_public_api.py,
test_tui_public_api.py, test_checker_operations_public_api.py; shared signed HTTP
setup in artifacts/test_submission_foreground_command.py and its malformed caller.
Manager retains actual CLI submission using file/key, accepts202 then drives exact
OUTBOX T5 before history checks. TUI setup uses current TASK fixture and real source
submission where needed; claim-only case needs no admission. Shared HTTP setup
takes explicit factory/client, provisions fixed principals idempotently without
resetting lifecycle. Preserve all fresh-revocation, concealment, history and CLI
wire assertions. Registry probes use distinct versions from two locked fixture
images and assert exact total4 after two CLI registrations. No compatibility flags,
authority bypass, skipped test or changed production API. Medium risk client/owner
integration: run all four affected CLI cases with built binary, existing HTTP
helper consumers, CLI Ruff/format, structural checks and focused QA review.
Use the existing signed raw-ZIP journey's90s subprocess allowance only for task
submit; keep20s for reads. This accommodates the foreground upload/PRE command
instead of the removed short admission call; no product deadline changes.

CLI current-producer replay passes4 in185.90s (existing marker/serializer warnings),
including actual manager CLI ZIP submission, signed TUI read/claim and revocation,
Operator registry/retry. Shared HTTP helper consumers pass5 in169.90s. Both isolated
receipts confirm database and MinIO cleanup complete. QA finds no scoped defect;
all prior manager/TUI assertions and registry replay/concealment/revocation guards
remain. Full CLI Ruff/format99files, structural validator, record and whitespace
checks pass. Fresh origin/main fetch has no commits absent from this branch.
These focused proofs close the four observed27531 CLI API failures locally;
hosted rerun and remaining full-spec/current producer migrations remain required.

Optional public packet migration scope: tasks/test_public_submission_intake.py.
Replace removed nullable admission-JSON contract with raw header metadata:
omitted/empty ASCII text hashes equally, bounds remain enforced, retained packet
UTF-8 byte bound remains independently protected. Real signed ZIP accepts with
warning-only empty text, explicit empty replay keeps one PRE/source, changed
metadata conflicts before extra work. Drive production OUTBOX T5 then repeat
replay and inspect exact empty stored packet/consumed admission and one Submission.
No nullable-header compatibility, fabricated ready admission, skipped guard or
changed product API. Medium contract/replay risk: targeted pure+PostgreSQL tests,
Ruff/structure/record checks and focused QA review required.

Public nonblocking-feedback migration extends scope to the existing source runtime
fixture in artifacts/test_submission_pre_source.py and configure_source_http helper.
Permit explicit controlled project findings through the worker's existing project
reply hook, deriving the result digest with the canonical constructor. Guest still
derives source inspection/defaults and binds request/lease. Convert removed prepare
endpoint test to signed raw ZIP accepted receipt, exact coverage-incomplete finding,
no PRE replay, T5 evaluation_pending and existing0049 incompatible-finding refusal.
No caller-supplied manifest/default or product/runtime changes. Verify converted
case and unchanged-default optional packet consumer; QA shared-helper review.

Optional packet/bounds first replay passes2 in32.86s with cleanup complete.
Feedback first pair1pass1fail62.17s: strict constructor correctly rejects JSON UUID
strings in simulated project reply. QA-FEEDBACK-001 repairs fixture normalization:
decode original ExternalCheckerExecutionResult, use typed fields, replace findings
and derive fresh digest. Exact-hook probe preserves request/registry/lease and
detects lost coverage findings. Final feedback+optional pair passes2 in62.18s,
including T5 and retained0049 check; database/MinIO cleanup complete. QA finds no
remaining scoped code issue. Ruff, whitespace, record and structure checks pass.
Hosted8bfd gates/images pass but Backend was pending behind superseded27531 run;
requested cancellation of that old same-PR run, retaining its artifacts. No full
CI/spec/provider readiness claim; remaining old public producers still need migration.

Initial public replay migration scope: tasks/test_public_submission_intake.py only.
Replace obsolete prepare/admission JSON test with signed raw ZIP T1/PRE/T4 and
real OUTBOX T5. Preserve duplicate-header refusal, authorized foreign contributor
concealment, uncaused predecessor refusal, rejection of caller-owned JSON URI,
exact replay without a second provider upload/PRE, immutable metadata, history,
fresh suspension and exact one-source/admission/Submission/PRE/POST counts.
No production changes, compatibility route or weakened authority oracle. Medium
contract risk; isolated PostgreSQL test, Ruff/structure and focused QA review.
Human review focus: obsolete response semantics replaced by accepted receipt plus
finalized history without dropping replay ownership or packet integrity checks.

Initial replay first run reached all HTTP/T5/suspension checks then failed on test
model attribute submission_version (stored model uses version); corrected assertion.
Final isolated replay passes1 in34.43s (/tmp/submission-initial-replay-v2), database
and MinIO cleanup complete. QA finds no scoped findings; unrelated function ASTs
unchanged, independent assertion probes detect second PRE and lost replay feedback.
Ruff, structural boundary, record and whitespace checks pass. This closes current
initial replay proof only; remediation/deadline and other remaining spec work stay
open. Hosted953 backend lanes now running; no final full-CI qualification claim.

Public deadline migration scope: tasks/test_public_submission_intake.py and shared
artifacts/test_submission_pre_source.py runtime fixture. Replace retired processor
TimeoutError/prepare route with current signed ZIP and a simulated provider deadline
receipt after exact source read/drain. This proves current receipt persistence,
public infrastructure classification, stable replay, retained source cleanup charge,
unchanged task/assignment and no admission/Submission/POST. It does not qualify
real elapsed runtime enforcement; that remains separate A25 provider evidence.
Keep existing capacity-failure fixture behavior unchanged. Medium lifecycle/contract
risk: isolated target and existing receipt-source consumer, Ruff/structure, focused
QA review. No production timers, compatibility interfaces or fabricated defaults.

Deadline v1 selected an invalid parameterized node and ran no tests. Collected
actual IDs and corrected selection; v2 public deadline + existing received-capacity
source consumer pass2 in45.17s, database/MinIO cleanup complete. QA reports no
scoped code findings; actual shared-branch probe proves exact source drain/close
and typed pending receipt, and named public assertion detects capacity-for-deadline
substitution (/tmp/submission-deadline-qa-probe.log). Ruff, structural boundaries,
record and whitespace checks pass. Removed now-unused _prepared_packet import;
remaining remediation consumer still uses old preparation and requires migration.
Real timer/provider qualification remains open; no full-spec readiness claim.

Public remediation migration scope: tasks/test_public_submission_intake.py only.
Use existing real source-backed predecessor and routed failed POST; submit revised
raw ZIP over HTTP with exact predecessor and revision preparation acknowledgement,
reject wrong predecessor before PRE, accept/replay immutable receipt, then real
OUTBOX T5 produces version2 bound to consumed admission and predecessor. Assert
exact two Submission/PRE/POST runs across initial+revision, one successor and history.
No production changes or fabricated predecessor/default manifest. Retain shared
_client/_payload because revision-expiry and CLI consumers still import them.
Medium lifecycle risk: isolated target, whole public module, lint/structure and QA
review; human review focus is preserved lineage plus current asynchronous receipt.

Remediation QA001 repaired: CountedStore lacks observe_sealed_source, so T5 uses
its initialized underlying provider. QA002 repaired: consumed admission now binds
independently to receipt.operation_id and observed PRE run, not merely successor's
own admission selector. Independent mutation probes reject either substitution.
Full module first run7pass1fail284.17s; remediation failed T1 because predecessor
fixture locks16MiB namespace capacity while HTTP helper supplies4MiB. Preserve
production mismatch guard; explicitly use predecessor's16MiB test profile for
this revision only. QA verifies rest of profile unchanged and no shared change.
Diagnostic v3 loaded repaired code and passes1 in181.35s; explicit final v4 passes1
in152.66s. Both database/MinIO cleanup complete. Together with unchanged seven
cases from full run, every public module case has passing evidence. Ruff, structure,
record and whitespace pass. Shared _payload remains for revision_expiry consumer;
no removed preparation call remains in this module's tests. This is local proof,
not full CI/native/provider or full-spec completion.

PRE coordination cleanup scope: modules/checkers/selected_pre_submit_coordination.py
and tests/checkers/external/test_selected_pre_submit_coordination.py. Repo-wide
consumer trace finds no caller/issuer of SelectedPreSubmitAdmissionCapability
outside its obsolete unit test; current finalize always returns capability=None.
Remove dead class/member/export, retaining execution capability and all historical
readers/data. Replace obsolete capability test with exact current acceptance lock
refusal/positive controls; migrate TASK guard and packet/lineage tests to source
reservation without caller-derived manifests. Remove unused old reservation helper.
Medium authority risk: full coordination/receipt tests, Ruff/structure and QA+ARCH
review. No compatibility alias, relaxed authority, schema or retained-data changes.
Human focus: dead issuance removal must not weaken exact T4 evidence consumption.

Coordination initial full run136pass15.09s. QA-COORD001 identified coupled predecessor
ID/version negative could survive removal of either guard. Added typed current
revision positive control and separate ID-only/version-only substitutions alongside
initial case. Final full coordination+receipt run137pass9.98s; no retiredconstructor
failures remain in this module. Ruff, structure and whitespace pass. ARCH confirms
no live issuer or historical reader depends on deleted class; current T4 checks
persisted evidence independently. New mocked acceptance matrix proves immediate
conditions only; real database/source acceptance proofs remain separate. Old ART
admission-authority protocol/consumer cleanup remains traced residual work, not
removed blindly in this scope. QA mutation closure pending at this checkpoint.

QA-COORD001 closed: exact revision test detects independent removal of predecessor
ID and version guards, and acceptance test detects receipt-guard removal. In-memory
probes leave source unchanged (/tmp/submission-coordination-qa-repair.log). No
remaining scoped QA/ARCH findings;137pass final suite evidence inspected. Same
single draft PR708, with remaining full-spec/provider/CI work still open.

Model-call preservation scope: tests/checkers_model_calls/test_composed_execution.py.
Hosted953 run43960175985 actual stack shows output storage execute_committed_put
fails fixed ART service context. Source-based material fixture no longer incidentally
provisions old put pipeline; model-generated outputs still legitimately require
ARTIFACT_PUT_RESOLVER and ARTIFACT_VERIFIER per checker_output_storage composition.
Provision those exact identities alongside ARTIFACT_CHECKER_OUTPUT locally, using
idempotent helper that never resets lifecycle. No shared broad grants, product
AUTH changes or removed assertions. Medium downstream authority risk: full eight
composed cases incl MinIO/provider uncertainty/concurrency/recovery, lint/structure
and focused QA review. Human focus is explicit required fixture authority without
weakening model budget/charge/replay or output binding evidence.

Hosted953 evidence refreshed:15 downloaded backend-lane artifacts,152 failure
entries in /tmp/submission-hosted-failures-953.txt. This is an older head and includes
now-fixed public/coordination cases; do not call it current-head remaining count.
QA model-fixture probe confirms added identities exactly match production output
composition, all existing assertions unchanged, and suspended existing principals
are preserved by helper without reset/recreation. No scoped findings. Full8case
run /tmp/submission-model-composed-v1.log is active (session42607); do not claim
runtime success or commit completion before its terminal receipt. Ruff/record pass.

Independent bounded fixture repair while model integration runs: allowed file
backend/tests/test_checker_materialization.py. Hosted953 source-read tests stop
before exercising guards because dataclass replace omits explicit source_contracts
InitVar. Supply existing production contract dependency at the fixture copy;
no source-validator bypass or test assertion change. Low implementation risk,
authority test relevance: run full pre_source selection, Ruff and scoped QA.
Existing commit-before-read/lifetime/expiry/cancellation guards must all execute.

Source grant final selection12pass12deselected12.36s; existing assertions and all
other AST nodes unchanged. QA confirms canonical contract dependency validates
source only and conveys no storage authority; no scoped findings. Ruff/whitespace
pass, shared structure validation passed. Model8case integration remains separately
active42607; its fixture change is not included in this source-grant commit.

Retry-authority counter scope: tests/checkers/execution/test_checker_retry_authority.py.
Hosted953 six failures show exact outbox totals missing the source T4 finalization
event. Shared _failed_source already asserts exactly1 SubmissionFinalizationRequested.
Increase only affected absolute event totals by1, retain all counts (no filtering),
NOWAIT/observed blocking, revocation, audit rollback and replay/no-effects checks.
Public audit-failure assertion currently interrupts before test-owned trigger cleanup;
correct expected total permits existing cleanup and resolves downstream schema
fingerprint symptom if no separate defect exists. Medium authority-test relevance;
run six affected cases and QA review, lint/structure. No production changes.

Retry-authority QA confirms entire module AST changes only six integer expectations
by+1; every caller uses exact-one-finalization fixture. Baseline2 is T4+initialPOST;
retry3 adds successorPOST. Authority/lock/revocation/receipt/fence/audit/cleanup
assertions unchanged (/tmp/submission-retry-authority-qa-probe.log). No findings;
run77589 /tmp/submission-retry-authority-v1.log still active, so runtime and schema
cleanup consequence remain unproven. Separate modelrun42607 also remains active.

Execution integrity scope: tests/checkers/execution/test_execution.py only. Current
material fixture retains operation source ZIP, so old SHA-object damage test fails
before exercising integrity. Recover source operation from exact created admission,
assert stored original bytes, then unlink/corrupt exact local source bundle. Retain
no-checker-before-verification, finalize revocation, cleanup and immutable replay
assertions. Both damaged/nonrecordable tests must compare all exact baseline outbox
IDs (T4+initialPOST) and require that pair's exact types; no filtering/loose totals.
Medium source/authority proof risk: seven affected DB cases, lint/structure/QA.
No production storage, authorization, timers or retained historical fixtures change.

Execution integrity QA no findings: exact local source layout and admission-bound
operation confirmed; all non-outbox assertions and unrelated test ASTs unchanged.
Corrected independent exact-postexecution snapshot probe detects added, removed,
and type-swapped events (/tmp/submission-execution-integrity-qa-events-v2.log).
Sevencase28715 /tmp/submission-material-failures-v1.log active; model42607 and
retry77589 also active. No runtime completion claim. Ruff/record/whitespace pass;
shared structure check terminal0 before this two-test edit, final validation needed.

Model composed run terminal0:8passed635.57s,6 existing serializer warnings;
/tmp/submission-model-composed-v1.json confirms database/MinIO cleanup complete.
Coverage includes local+MinIO, paid-effect retry, concurrentcallbacksinglecharge,
operator no-effect/settledfailure recovery and offline OpenRouter completed/ambiguous
transport. QA no findings; exact required principal provision preserved all existing
assertions. Ruff/record/structure pass. This closes the eight hosted953 model-output
authority failures locally, not live paid-provider or full-CI qualification.
Retry77589 and material28715 remain separate active verification; only model fixture
is included in this implementation commit alongside accumulated scoped records.

Binding unit scope: tests/test_artifact_bindings.py. Hosted953 eight failures stop
on fake admission lacking source_operation_id. Migrate ready-consumption fixture to
explicit current accepted_operation_id and same source_operation_id (not silentNone
historical fallback). Positive binding asserts SQL source-custody check invoked for
exactadmission; negative absent/foreign acceptedoperation rejects before SQL/content
or binding writes. Preserve existing packet/manifest/authority/replay assertions.
Medium authority test risk, no production changes. Run whole unit module plus QA.
Mock SQL participation tests do not qualify database source-custody implementation;
real T5/public revision proofs remain separate evidence.

Retry-authority terminal0:6passed3deselected371.41s with5existing serializer warnings.
Database+MinIO cleanup complete; public audit-failure trigger cleanup now completes
and schema fingerprint teardown passes. Exact lock/revocation/rollback/replay
proofs retained; QA no findings. Ruff/record/whitespace pass, shared structure prior
run passed. This commit includes only retry-authority implementation; material
integrity and binding unit followups remain in progress separately.

Material integrity run terminal0:7passed8deselected242.68s, database+MinIO cleanup
complete (/tmp/submission-material-failures-v1.json). Actual source missing/corrupt
cases and all5 nonrecordable cases preserve finalize authority, no checker access,
recoverability, scratch cleanup and exact unchanged T4+POST event set. QA no scoped
findings; final structural validator terminal0, Ruff/record/whitespace pass. This
commit includes material tests only; bindingunit strengthening remains separate.

Binding first run18pass1fail: manually rebuilt wrongversion replay omitted accepted
operation, so it stopped at operation guard; use replace(original,submission_version=2)
to isolate intended version denial (QA-BINDING001). QA-BINDING002 strengthens new
negative fixture with full valid downstream readsequence, so removing operationguard
causes DIDNOTRAISE rather than exhaustedmock. Exact probes now detect missingSQL
participation and foreign/missingoperation invalidacceptance; all existing assertions
retained including historical read. Final19pass1.52s, no remaining QA findings;
Ruff/whitespace pass. Final structure session22457 stillactive at this checkpoint.

Final binding structural validator terminal0. Scoped tests/review/record checks
complete; commit current accepted-operation fixture and guards without claiming
live database source validation or full-spec readiness. No local test run remains
active from model/retry/material/binding batch.

Current PRE builder scope: tests/checkers/external/test_selected_pre_submit.py,
only revision acknowledgement request digest and current policy/predecessor binding
tests. Replace retired prepared archive fixture with sealed source reservation,
metadata and explicit contract dependency; preserve ack completeness/digest, exact
predecessor/rules/packet and revision lineage assertions. Derived manifest supplied
only after reservation through guest-default derivation, never admission metadata.
Retained publisher tests/helpers remain untouched pending checksum-bound historical
fixture migration. Medium lineage proof risk: targeted tests, Ruff/structure and QA.
No production path/schema changes, fake authority grant or compatibility alias.

Builder v1 targeted2pass1fail: current default input has no change_gate property.
Repair uses actual bind_submission_change over typed derived commitment/manifest;
assert intrinsic unchanged outcome. Supplemental pure current default gate confirms
changedrules allow and samerules refuse identicalarchive; no secret/byteproof claim.
Final targeted3pass11deselected0.75s; v2comparison-only also3pass1.69s. Ruff/structure/
record/whitespace pass. Historical publisher/old processor consumers remain explicitly
unmigrated; this is not a whole-module/full-spec completion claim. QA closure pending.

QA-BUILDER001 closed: exact tests detect ignored acknowledgement fields, removed
changedrules exception and unconditional unchanged acceptance; other test/helper
ASTs unchanged (/tmp/submission-current-builders-qa-probe.log). No scoped findings.
Fresh origin/main fetch has0missing main commits (190ahead beforethiscommit).
Same draftPR708; no broad CI or retained publisher completion claim.

Source PRE cutover scope: 0071_source_first_pre.py and focused migration proofs.
The migration currently installs a read-only guard on all v1 PRE rows without
refusing queued/running rows, stranding existing execution owners. Require an
exclusive table lock and refuse those rows before schema mutation. Preserve
terminal history byte-for-byte; never auto-complete, delete, or reinterpret it.
Allowed follow-up files are predecessor migration fixtures and their targeted
tests. Prohibited: restoring the retired admission publisher, changing current
submission authority, or claiming this check drains old put attempts/admissions.
High lifecycle/migration risk; architecture and QA review required. Acceptance:
real PostgreSQL queued/running refusal with rollback, completed historical-row
preservation, and serialization against concurrent old writes. Human review
focus: cutover refusal happens before historical execution becomes read-only.
Architecture agrees this is independently valid but not full spec20.2 cutover.
Archive inventory found completed selected PRE rows only; refusal fixtures still
need a genuine predecessor writer capture, not rewritten completed evidence.

Cutover preflight draft: syntax, whitespace and Commitrail validation pass.
Fresh isolated PostgreSQL migration through0083 and current PRE source custody
smoke pass (1test23.11s; /tmp/submission-pre-cutover-smoke-v1.json). This verifies
empty-database upgrade and current custody only, not queued/running refusal,
historical preservation or lock concurrency. Those acceptance checks and QA
remain pending; the migration change is not yet committed or qualified.

Historical refusal proof uses a detached e2b926288 owner checkout and captures
the same real run before execute, after committed claim, and after finalize.
Capture code only observes committed rows through a separate connection; it does
not replace owner decisions or rewrite terminal evidence. First capture passed
but omitted Alembic metadata; corrected capture rerun pending. Test files:
tests/migrations/test_source_pre_cutover.py and checksum-bound fixture/recipe
under tests/fixtures; register the test in scripts/test_lane_catalogue.py so CI
executes it. No gate weakening or current old-writer implementation is allowed.

Capture v2 passed1test56.11s with complete cleanup; archive SHA256
49156dd714478ba5d9b446440842b6b40d8372c4f05dcd38e7edb3b6e59f4b59.
The unchanged predecessor owns issuance at0065; current migrations carry each
restored snapshot to0070 before testing the cutover. No snapshot rows rewritten.
CI registration also requires tests/test_ci_lane_catalogue.py fingerprint update:
independently compared old/new sets, exactly one module added and none removed.
First catalogue run58pass1fail detects stale pinned count; exact fingerprint repair
rerun pending. Structural validator and Ruff pass. Migration run remains live.

Cutover migration proof terminal0:3passed421.85s, database/MinIO cleanup complete
(/tmp/submission-pre-cutover-migration-v1.json). Queued/running refusal preserves
rows/schema/guard/version; queued case observes blocked exclusive lock behind an
old writer; completed evidence upgrades to0083 byte-identically apart from the
new null source column and historical terminal digest still validates. ARCH/SEC
scoped PASS. Catalogue fingerprint repair59passed6.57s. QA omission probes pending.
This evidence is for the dirty candidate based on d5b809bb9, not full-spec CI.

QA omission proofs: removing only the refusal block makes the exact running case
fail DID NOT RAISE DBAPIError (133.36s); removing only the explicit lock makes the
exact queued case fail "cutover checked rows before excluding old writers"
(124.53s), with observed early drain exception, not an unrelated setup error.
Both isolated probes cleaned database and MinIO completely; current files were
unchanged. Historical reader probe accepts the captured completed row and rejects
an indexed request-digest substitution. Fresh main fetch:191ahead/0missing before
this commit. Full old put/admission cutover and publisher retirement remain open.

Current binding cutover scope: app/modules/artifacts/submission_bindings.py and
tests/test_artifact_bindings.py. Current consume compares nullable operation IDs;
two absent IDs pass, allowing an old ready admission into the current writer.
Require a nonnull accepted source operation before any content/binding mutation.
Preserve the separate read_consumed authority/receipt path for historical data.
Acceptance: valid old ready lineage with both IDs absent rejects before SQL/content
or writes; current T5 binding remains valid; consumed historical evidence replays
without new writes. Prohibited: old ready auto-acceptance, deletion, historical
reader changes, authority shortcuts. High lifecycle/authority risk; ARCH and QA
review, targeted unit regression and real public initial submit/T5/replay proof.
Human review focus: retained data is readable but cannot become a new accepted
submission without the current operation owner. Full old writer retirement remains
separate; this closes a live consumption boundary rather than reviving that path.

Binding regression reproduced before production repair: historical_ready with
both operation IDs absent reached consumption (DID NOT RAISE,3.03s). Require exact
UUID accepted ID/matching source and unconditional SQL source validation; remove
tautological source-nonnull OR revision branches from consume-only lineage helper.
Historical read_consumed is unchanged. Final units21passed5.61s; Ruff, structure,
record and whitespace pass. QA independently verifies AUTH-before-disclosure,
UUID-string rejection, no downstream mutation, old-guard regression detection and
historical read preservation. ARCH agrees removed branches were unreachable.
Public initial/T5/replay v1 passed104.89s but may have imported before dead-code
cleanup; frozen final v2 pending. TASK create replay-only and SQL old ready-to-
consumed barrier remain required follow-ups; no full old-writer closure claim.

Frozen binding public v2 terminal0:1passed75.71s, database/MinIO cleanup complete
(/tmp/submission-binding-cutover-public-v2.json). Current signed raw ZIP acceptance,
durable T5, retained history and accepted replay remain valid with the final guard
and dead-branch cleanup. No code changes after this run; final reviewer closure
requested on these results. Same single draft PR708; full goal remains active.

Database consumption cutover scope: new0084 migration, focused migration test and
checksum-bound ready/consumed predecessor fixtures with observation-only capture
recipe, current schema fingerprint and exact test-lane registration if needed.
The ART application guard alone does not prevent an old ready admission from a
direct database ready-to-consumed transition. Add a guarded SQL refusal for rows
without source_operation_id; preserve consumed historical rows and ready-to-stale
owner transitions. No automatic submissions, row deletion, receipt rewrites or
generic producer changes. High lifecycle/schema risk, ARCH/QA required. Proof:
capture real old ready and consumed states through pinned owners, upgrade both
without changing retained evidence, reject old consumption with exact guard error,
allow staling, and retain current public source T5. Verify schema fingerprint
delta and CI registration without weakening either gate. TASK old API removal is
being traced independently; this database change is not full cutover completion.

QA-SQL-BIND002: real split0083->0084 upgrade refused by stale env.py supported
revision list (still0081), before exercising newguard. Expand scope to env.py:
admit exact0081/0082/0083 predecessors and0084head, preserving unknown stamps.
Migration proof will traverse0082->0083->0084 and repeathead upgrade; rerun existing
unknown-stamp refusal. Do not infer schema fingerprint from preflight refusal.
QA-SQL-BIND001: raw ready update alone may lack later Submission/FK receipts.
It proves exactnewguard/order only; stronger pinned-old-writer control is running
at0083(success) and0084(exactrefusal/all-table rollback) in isolatedoldcode process.

Fresh0084 schema measurement (separate isolated read-only diagnostic, not the
failedupgrade) yields e028a3b353a8112bddd77309722cd0dd69e6fe0c871dfa00c50f6da88651a90b.
Update tests/conftest.py exactexpected fingerprint; retain its full assertion.
The migration suite must still prove only the intended public function changed
and no captured rows changed. V2 adds explicit0082->0083->0084 and current-head
no-op upgrade plus existing unknown0030 stamp refusal. These runs are pending.

Pinned old-writer control terminal0:2passed233.74s with complete cleanup
(/tmp/submission-source-binding-old-writer-v1.json). Production owner code is
e2b926288; only current0066..0084 migration files were copied into its isolated
checkout. The observed test recipe is retained as pre_cutover_writer_proof.py.txt,
not installed as a current compatibility writer. Each case creates genuine0065
ready custody, upgrades schema, then calls the unchanged old composed command:
0083 commits one Submission and consumed admission;0084 raises the exact new
source-custody guard error and preserves every public table row. This supplies
the otherwise-valid transaction control missing from the raw UPDATE assertion.
Current migration-v2 and public0084T5 tests remain live; no readiness claim yet.

Migration v2 terminal0:3passed321.59s with complete cleanup. Captured ready/consumed
graphs survive unchanged; only guard_submission_bundle_admission_lineage changes.
Split0082/0083/0084 and repeatedhead upgrades succeed; unknown0030 stamp remains
rejected without mutation, closing QA-SQL-BIND002. Current public0084 T5/replay
passed59.25s and full cleanup; canonical schema assertion remains enabled.
QA-SQL-BIND001 closed by the genuine old-writer control, not the raw SQL probe.
QA-SQL-BIND003 adds actual writer serialization to ready case: hold ROW EXCLUSIVE,
observe waiting ACCESS EXCLUSIVE, then release and require completed upgrade.
Final ready-case run and independent omitted-lock mutation remain pending.

Final0084 ready lock case passed248.03s with complete cleanup. The independent
copy with only0084 LOCK removed fails exactly "source binding cutover did not
wait for the old writer" (238.93s), also with complete cleanup. No current files
were changed by the probe. Structural validator, Ruff, record and whitespace
checks pass; ARCH/SEC scoped PASS. QA-SQL-BIND001/002/003 evidence now complete.
This closes the A33 admission-transition portion, not physical-provider/history
qualification or full operational cutover. TASK old command, ART old publisher
and preparation retirement remain next; keep full A01-A35/C01-C07 goal active.

Dispatch proof migration scope: update tests/tasks/submission_dispatch/test_composition.py
from the obsolete hidden creation command to accepted T5 and retained dispatch reads.
Preserve exact dispatch/POST custody, reject mismatched receipt identifiers without
participant writes, and force the deferred SQL missing-dispatch failure through
real OUTBOX finalization. Rollback must preserve accepted T4/source custody while
removing all T5 writes. Internal retained reads are not fresh human authorization
proof; public intake replay and lost-ack outbox tests retain those distinct proofs.
No production behavior or compatibility helper is added. This removes one test
consumer blocking old TASK command deletion, not the complete deletion itself.
QA/test-delta review and focused isolated PostgreSQL tests required.

Dispatch migration v1: 3 failures in97.07s, cleanup complete. Two new assertions
used nonexistent OutboxEvent.id; correct to native UUID event_id. The injected
missing dispatch correctly reaches SQL23514 at the current accepted-operation
closure guard (0074), before the older dispatch-required guard. Assert that exact
current error and preserve the no-dispatch injection and staged-write checks.
Also assert accepted receipt, sealed nonzero source charge, and active TASK pointer
survive T5 rollback. Structural and record validators passed; rerun after repairs.

Dispatch migration v2 terminal0: 3passed63.85s, database and MinIO cleanup complete
(/tmp/submission-dispatch-current-v2.json and .log). Frozen test blob
232a026b0ef5934398d4aa68333adf0ead354f99. Current composed accepted owner returns
exact retained dispatch; each mismatched receipt key fails without POST creation;
real deferred missing-dispatch failure rolls back T5 while retaining T4 acceptance,
sealed charged source, active TASK pointer and exact finalization event. Tests ran
on these modified bytes with precommit HEAD e52a215c3, not a clean commit execution.
Existing T1 changed-metadata/revocation/post-body reauthorization and real OUTBOX
lost-ack tests retain distinct public/worker replay obligations. Scoped QA found no
actionable issue: selector coverage and current T4/T5 rollback semantics agree
with their owners. QA inspected shared execution evidence; no independent PG
rerun or mutation is claimed. Old TASK command removal and full end-to-end
qualification remain open.

Dispatch authority proof migration scope: test_storage.py still intercepts the
obsolete PreparedSubmissionCreationAuthorization, while its fixture now accepts
through source T4. Move the unrelated-allow substitution to current
SubmissionIntakeAuthorization.consume_acceptance. Preserve a genuine unrelated
persisted authority event, real preparation/consume, exact SQL rejection, and
assert no accepted handoff or Submission/POST is persisted. Foreground failure
must retain sealed source obligations for cleanup. Run all three storage tests
including independent SQL member substitution and immutability controls. This
removes another old AUTH test consumer; it does not claim old path retirement.
Required QA/security review limited to the changed attack and its owner mapping.

Storage authority migration v1 terminal0:3passed115.98s at schema0084 with database
and MinIO cleanup complete (/tmp/submission-dispatch-authority-v1.json and .log).
Exact frozen test blob57dd8707b80ba6587848acf28d2b2a17e5708549; execution used modified
bytes over473c32677, not a clean postcommit execution. Unchanged independent SQL
substitution/immutability controls pass. Current T4 wrong-action allow reaches the
exact accepted-authority SQL refusal; genuine consume audit rolls back, unrelated
allow persists, no accepted/T5 writes survive, and sealed cleanup charge remains.
QA/security inspection found no actionable issue and confirmed unchanged control
ASTs. Verdict is limited to wrong-action/provenance substitution; no exhaustive
authority or provider qualification and no independent rerun/mutation is claimed.
Ruff, structural validator, Commitrail and whitespace checks passed.

Retained replay test migration scope: replace test_replay.py's obsolete hidden
creation command with composed TASK read_finalized for retained generation,
foreign receipt selectors and unavailable/invalid SQL custody. Old request-field
mutations map to T1 metadata/actor controls and SQL independent foreign-member
validation, not invented fields on the new internal read. Move actor suspension
checks to configured contributor operation read and binding-service suspension to
the actual PreparedSubmissionFinalizationAuthorization gate. This latter component
check is not an end-to-end outbox replay claim; existing lost-ack outbox proof owns
that composition. Preserve valid controls, exact persisted event identities, no
creation participant entry and no repair. Old individual Python-owner missing-read
mocks are obsolete: current TASK reads one SQL-valid dispatch; actual SQL member
substitution/immutability proofs remain in test_storage.py (3pass previous scope).
QA/security review required for coverage mapping and precise evidence limitations.

Replay migration v1 terminal0:4passed203.03s, complete database/MinIO cleanup
(/tmp/submission-retained-replay-v1.json/.log). QA-REPLAY001 confirms human denial
must assert code submission_unavailable, not any SubmissionIntakeFailure (which
also includes infrastructure errors). Add that exact code assertion; retain real
suspension and positive controls. No other scoped finding. Rerun changed security
case on final bytes; other three tests are unchanged. One Pydantic serialization
warning from the existing generation2 fixture is not suppressed or claimed fixed.

Final replay security v2 terminal0:1passed32.20s, all cleanup complete
(/tmp/submission-retained-replay-security-v2.json/.log). QA-REPLAY001 closed by exact
submission_unavailable refusal with positive controls. Final test blob
1953d6286901b2061831447125cfc48af114dc8d; the other three v1 tests remain unchanged.
Scoped QA/security inspection found no remaining issues. Evidence is shared
executions on frozen modified bytes over b388401ba, not an independent rerun or
clean postcommit execution. Broader old-command removal and final qualification
remain open. Same draft PR708 only.

Predecessor receipt proof migration scope: replace the old verified-ready admission
and hidden TASK creation in test_predecessor_receipt.py with current source T1/PRE/
T4 and production OUTBOX T5. Use genuine local and foreign routed failures. Change
only the new dispatch remediation manifest. Force its deferred constraint after
T5 has staged finalized operation custody, not prematurely inside create_accepted.
Add matching valid revision control to exclude incomplete-finalization false proof.
Require exact23514 replacement-cause guard, no T5 owner effects after rollback,
and preserved accepted operation/source/event/task pointer. QA/security review and
isolated PostgreSQL positive/negative cases required. Old producer retirement is
still incomplete; this ports another required negative test before deletion.

Accepted predecessor v1 terminal0:2passed120.19s, complete cleanup
(/tmp/submission-predecessor-receipt-v1.json/.log). The matching valid revision
commits; changing only its dispatch manifest reaches exact23514 replacement
currentness refusal after complete T5 staging. Strengthen negative rollback with
explicit absent candidate Submission/CheckerRun/POST event and retained exact T4
event. Rerun only changed foreign case; valid control remains unchanged.

Final foreign predecessor case v2 terminal0:1passed58.76s, complete database/MinIO
cleanup (/tmp/submission-predecessor-receipt-v2.json/.log). Final test blob
e0b0633363349f61867dda1809b0a5b0219baabc; valid v1 control unchanged. QA/security
inspection found no actionable issue. This explicitly forced deferred-constraint
check proves cause validation after complete staging and rollback, not native
COMMIT constraint ordering. Retained T4 event is checked by its persisted ID,
type and operation association, not full payload byte equality. Shared executed
content over b2e621581 is the evidence; no independent or clean-commit rerun claim.
Ruff, structure, record and whitespace checks passed. Full retirement remains open.

Revision POST-insert rollback/retry migration scope: port the late outbox failure
case in test_replacement_creation.py from old ready admission/create to real source
acceptance and OUTBOX T5. Keep actual SQL insert-trigger failure with nontransactional
sequence witness. Compare retained product/binding/checker/creation-audit snapshots,
retain accepted source/task/event custody, then remove fault and retry the same
finalization event after actual recorded retry/continuation deadlines. No clock
patches or fabricated ready state. Assert one version2 successor with exact local
cause and one new POST event. Remaining stale-cause/race tests are separate pending
consumers; this change does not claim their coverage or production retirement.
QA/security review and isolated PostgreSQL execution required.

POST rollback v1:1failed50.17s, cleanup complete. Actual handler returned the
expected OutboxPersistenceError, but the test wrongly expected its SQL cause to
be exposed. OUTBOX's payload-free error frame deliberately removes that cause.
Assert exact stable error and absent cause, retaining the nontransactional sequence
witness of the unconditional SQL fault. Do not expose diagnostics or weaken owner
error handling for the test. Retry/post-rollback assertions were not yet reached.

POST rollback v2 terminal0:1passed121.89s, complete cleanup. QA-ROLLBACK001 tightens
stable error to equality (substring allowed leaked suffix). QA-ROLLBACK002 adds
existing ART snapshot at accepted baseline and after failure: source registration
now creates artifact_contents/artifact_replicas inside T5, unlike old ready/create,
so preserved binding/admission rows alone would miss orphaned registered rows.
Retain that helper's content/replica counts plus other ART owner counts, and keep
existing projected product snapshot (four mutable Submission status/time fields
excluded by its preexisting definition). No claim of byte-identical every-row
state. Both repairs will run together on final bytes, including real retry.

Final POST rollback/retry v3 terminal0:1passed125.71s, schema0084 and complete
DB/MinIO cleanup (/tmp/submission-revision-post-rollback-v3.json/.log). Frozen test
blob facd01d41abba1933ac3a36c9de1f5484b11acd9. Exact sanitized error/SQL witness,
ART registration counts, retained projected product state and same-event real
retry all pass. QA-ROLLBACK001/002 code findings closed with final executed
repairs; scoped QA/security reports no further finding. Other two tests/helpers
in module AST-unchanged and still pending migration. Shared modified-content
execution over a091cb7d6 only; no independent or clean-commit rerun claim. Final
Ruff/structure/record/whitespace checks passed. Full retirement and goal open.

Remaining revision admission proof migration scope: port stale-cause and competing
ready-admission tests to current source owners, then remove their obsolete local
preparation/hidden-create helpers/imports. Stale cause: execute genuine eligible
PRE, reserve a newer predecessor evaluation before T4, require refused acceptance
and retained failed-source cleanup custody without new Submission/POST. Competition:
two real commands with distinct keys, observe actual blocked PostgreSQL TASK lock,
hold winner body until loser exits so refusal occurs against receiving custody,
require loser never reads bytes, winner accepted once, finalize via production
OUTBOX and replay same immutable receipt without new product writes. Preserve prior
POST rollback test unchanged and run all three module cases. QA/security review
required; does not claim removal of other modules' obsolete consumers.

Revision admission v1 terminal0:3passed151.09s/allcleanuptrue. Dependency search
found indirect old-helper consumers in test_alembic, revision_capacity,
revision_exhaustion_recovery, checker_retry_history_replay and related modules.
Restore existing shared helpers/imports unchanged; no compatibility alias or new
old writer. AST comparison confirms all five prior helpers and previous rollback
case unchanged. Those dependents remain explicit retirement work. Scope removes
old-path calls only from this module's two test bodies, not the shared helper API.
QA-REVISION001 requires exact context-invalid refusal and current-checker cause;
QA-REVISION002 adds unchanged OUTBOX rows at the post-PRE/pre-T4 baseline, since
no delivery mutation is legitimate here. Run repaired stale case and collection
of shared consumers; current race/rollback v1 bodies remain unchanged. Existing
Pydantic generation-fixture serialization warning is retained, not suppressed.

Final stale-cause v2 terminal0:1passed54.72s/schema0084/allcleanuptrue
(/tmp/submission-revision-admission-v2.json/.log). Exact context-invalid and checker
cause plus unchanged OUTBOX snapshot pass, addressing QA-REVISION001/002. Final
blob862eb2621b00a54fe32a07ed96560639406cadcc; race and prior POST rollback ASTs
unchanged from v1 three-pass run. Six shared-helper consumer modules collect
92tests19.12s; collection is not runtime qualification. All five shared helper
ASTs restored unchanged; broader old-path dependencies remain. Ruff/structure/
record/whitespace checks passed. Evidence is shared execution of modified content
over559617e9f, not clean-commit execution or independent rerun. Full goal open.

Checker retry history migration scope: replace test_checker_retry_history_replay's
old ready-admission/hidden-create helpers with current source T1/PRE/T4/OUTBOX T5
for the later revision. Preserve real prior failed execution, authorized retry,
selected checker completion and governed needs_revision cause. Keep exact durable
state snapshot for same-key historical replay and refusal of new-key old-source
retry after a later Submission. Extend provider traps from old open() to current
open_source()/observe_sealed_source() without changing retry production code.
This removes one indirect shared-helper consumer; QA/security review and focused
isolated PostgreSQL test required, not full history/provider qualification.

History v1 failed43.07s before later-submission creation at unchanged selected
execution request count (0). QA-HISTORY001 diagnosis: delivery_fixture captures its
own ControlledSelectedExecution through configured_post_submit_external_execution;
the test's older lower-factory monkeypatch observes an unused port. Use explicit
returned delivery.selected, assert it was not invoked by the initial missing-source
failure, set its verdict to failed before retry, and retain all actual execution/
completion/needs_revision assertions. No product runtime or routing policy change.
No downstream history qualification was reached in the failed run.

History v2 terminal0:1passed44.57s/schema0084/allcleanuptrue
(/tmp/submission-checker-history-current-v2.json/.log). Finalblob
e0c7018e5e77bbc182c42db1b2be9a8c90a714a7. QA-HISTORY001 resolved: actual captured
checker port executes once and produces governed remediation; later accepted
revision finalizes through real OUTBOX/T5 before historical replay assertions.
All22 original Assert ASTs retained; new empty-port/v2 controls added. Same-key
receipt/full retained-state equality and new-key refusal pass with old/current
source-read traps. QA/security inspection has no remaining finding. Existing
Pydantic fixture warning retained. Shared modified-content execution overf9d1b2529,
not independent or clean-commit rerun; no provider/native runtime qualification.
This removes one old shared-helper consumer; full retirement remains open.

Two-revision public cap proof scope: migrate test_two_revisions_then_public_and_sql_refusal
in test_revision_capacity.py from old preparation+JSON admission to raw ZIP202
acceptance and real finalization OUTBOX. Retain two governed checker failure rounds,
unchanged policy window duration, terminal exhaustion, historical accepted replay,
and rawSQL excess/invalid-version refusal with exact lineage. Configure the existing
controlled PRE transport on the already-claimed16MiB test namespace. Require one
PRE per accepted revision, exact source-backed finalized dispatch, and no additional
intake on exhausted-assignment refusal. Other capacity tests/shared helpers remain
unchanged and unqualified by this run. QA/security review and targeted PG/public
journey required; no real guest/provider or final specification qualification claim.

Public cap v1 failed105.62s during the rawZIP revision loop with response500
(sanitized middleware), before cap refusal assertions. Teardown also logged an async connection
cross-loop close error; do not assume it is the request's cause. Use an untracked
test-only diagnostic plugin to rethrow the active sanitized middleware exception;
no production disclosure change or qualification from that diagnostic run.
Structural validator also found test function130lines vs120limit. Extract exact
raw-ZIP header construction into a cohesive local helper; leave policy/ledger
unchanged and rerun validator. Both are open until discriminating evidence arrives.

Diagnostic v2 failed94.49s: actual request cause is FileExistsError for pre-tree.
Repeated configure_source_http calls share its test-runtime scratch root; second
PRE collides even though durable namespace should remain identical. Expand bounded
scope to that helper: allocate unique runtime-only scratch subdirectory per
configuration while _settings(tmp_path) retains the same durable namespace/profile.
No product storage/configuration change. Prior first-revision attribution corrected;
teardown loop-close logs are not this cause. Remove redundant saved-header/response
initialization (the fixed two-round loop assigns both) to stay within120lines.
Run normal cap journey and existing one-revision public control without diagnostic
plugin; rerun structural validator with no policy/ledger relaxation.

Normal cap/control v3 terminal0:2passed128.15s/schema0084/allcleanuptrue
(/tmp/submission-public-revision-cap-v3.json/.log), without diagnostic plugin.
Two accepted source revisions finalize, exact window/terminal exhaustion and
fresh-intake refusal/historical replay pass, with unchanged SQL excess/invalid
version attacks. Existing one-revision public control also passes after runtime
scratch isolation. Structural validator now passes with policy/ledger unchanged;
Ruff/record/whitespace pass. Final blobs: capacity114921339529fe0d5542d4b37f5148faa9fb828e,
foreground96751781c3aeffb398b4bdf677539ba0101835e8. Scoped QA/security reports no
remaining actionable finding. Shared modified-content execution over11e7c36c7,
not independent or clean-commit rerun. Other capacity cases and full old-producer/
provider/specification qualification remain open; same single draft PR708.

Zero-cap and rebase public proof scope: migrate coverage-return and policy-rebase
cases in test_revision_capacity.py to rawZIP202 acceptance/OUTBOX T5. Preserve
zero-round coverage semantics, actual terminal exhaustion/status timestamps and
backfill parity. Rebase must replay original accepted source using its persisted
key/metadata despite new guide, reject wrong acknowledgement before PRE, finalize
one v2 under exact acknowledgement, and preserve old Submission/checker evidence
and preparation immutability. Extract shared test runtime/profile composition for
these and existing two-revision cap case; preserve16MiB already-claimed namespace.
Run all three public journeys. Other capacity/recovery helpers remain unchanged;
QA/security review required, no provider or full specification claim.

Zero-cap/rebase/cap control v1 terminal0:3passed171.12s/schema0084/allcleanuptrue
(/tmp/submission-zero-cap-rebase-v1.json/.log). Frozenblob
7e89f998d9d4b3553ce0b643275142087913faaa. Zero-cap coverage preserves round0 and
exact terminal status/time/backfill semantics; rebase replays initial accepted
source without PRE, refuses wrong acknowledgement before PRE, then finalizes v2
without changing original Submission/checker custody. Existing two-round cap
control passes after shared runtime extraction. Ruff/structure/record/whitespace
pass. Scoped QA/security inspection found no actionable gap. Shared modified
content over0c801dc84, not independent or clean-commit rerun. Remaining capacity/
recovery consumers, producer retirement and full specification qualification open.

Reclaimed-assignment public source scope: migrate only
 test_expiry_allows_new_assignment_initial_at_next_global_version in
backend/tests/tasks/submission_dispatch/test_revision_capacity.py from obsolete
prepared admission/JSON creation to raw ZIP acceptance and real OUTBOX T5.
Preserve genuine expiry delivery with lost ACK, public reclaim, global version2
with no predecessor, new assignment round1 policy window and old-event replay
isolation. Require exact accepted replay and one PRE. Existing retained-expiry
fixture stays unchanged; this is not historical migration qualification.
Allowed files are this record and that test module; no production/SQL policy,
shared expiry helper or historical fixture changes. Lifecycle proof risk requires
QA/test-delta/security review. Verify the isolated PG journey, cleanup, Ruff,
structural/record/whitespace gates. Human review focus: assignment lineage and
old-expiry replay cannot affect the new assignment or reset its window.

Reclaim source v1 terminal0:1passed78.24s/schema0084/allcleanuptrue
(/tmp/submission-reclaim-source-v1.json/.log). First launch from repository root
failed module discovery before executing tests; corrected backend launch above.
Finalblob e316d39842e02fa76053667e5f8406ffa077eade. Exact accepted replay performs
no second PRE; real finalization creates globalv2/newassignment/no predecessor.
Actual checker failure opens fresh round1; recovered old lost-ACK expiry leaves
new window, task, assignment and expiration count unchanged. Ruff/structure/
record/whitespace pass; scoped QA/security inspection found no actionable gap.
Evidence is shared modified-content execution over25fb117f9, not independent or
clean-commit rerun. Existing synthetic retained-expiry setup is unchanged and
not historical migration proof. Fetched main has0 missing commits. Old producer
retirement, deployment/provider qualification and full specification remain open.

PM recovered-revision source scope: migrate only
 test_pm_recovers_retained_source_and_repairs_without_resetting_window in
backend/tests/tasks/submission_dispatch/test_revision_capacity.py to raw ZIP202
and real OUTBOX T5; remove now-unused old preparation/payload imports from this
module. Preserve root PM recovery/replay, child rebase/exact parent/stale refusal,
original deadline/limit, post-finalization blocked replay and immutable parent
lineage. Require exact source manifest/v2 and one PRE. Allowed files: this record
and test module. No production, shared helper, historical fixture, policy or
SQL guard changes. Existing synthetic retained setup does not qualify historical
migration. QA/test-delta/security review and isolated changed journey plus PM
superseded-source negative control; Ruff/structure/record/diff gates required.
Human focus: recovered permission must not reset policy windows or old evidence.

PM source v1 terminal0:2passed151.59s/schema0084/allcleanuptrue
(/tmp/submission-pm-source-v1.json/.log). Frozenblob
716aa0b9c5c610cbb550479a522f706d96ade335. Recovery/rebase retains original
window, exact source and parent lineage through real T5; superseded-source
negative control passes. Existing Pydantic fixture serialization warning remains.
Ruff/structure/record/whitespace pass; scoped reviewer inspection no actionable
finding. Shared modified-content execution overe2ee4ada1, not independent or
clean-commit rerun. Synthetic retained setup unchanged, no historical migration
qualification. One old preparation endpoint test remains in this module; full
producer retirement/provider/specification readiness remain open.

Expired-window public refusal scope: replace the last obsolete preparation
endpoint in test_revision_capacity.py with current raw ZIP submission. Preserve
PM blocked recovery/replay, exact original anchor/deadline, exact409 expiry code,
unchanged creation snapshot and needs_revision state. Configure controlled PRE
and assert no invocation; malformed body ensures expiry precedes ZIP validation.
Allowed files: this record and that test module. No production, historical
fixture or SQL guard edits. Existing synthetic retained setup remains limited to
runtime recovery, not historical migration proof. Lifecycle/authority test risk
requires QA/test-delta/security inspection; run changed test plus live two-round
cap control, Ruff/structure/record/diff gates. Human focus: timely refusal before
PRE without extending the original revision window or creating product facts.

Expired-window v1 terminal0:2passed191.42s/schema0084/allcleanuptrue
(/tmp/submission-expired-window-v1.json/.log). Frozenblob
7f7f4a94eda3e20918bc035104c8b1f15ef3f4ae reverified unchanged after user pause.
Exact409 revision_deadline_expired precedes malformed ZIP validation with no PRE;
all10 prior assertions retained. Two-round public cap control also passes.
Ruff/structural/record/whitespace checks passed before pause. Shared modified
content execution over40baa0f15, not independent or clean-commit rerun. Existing
synthetic retained setup does not qualify historical migrations. This removes
last obsolete preparation endpoint from capacity module; expiry-race consumers,
production retirement and full goal qualification remain open.

Current-main integration scope: integrate origin/main a2154e8a4 (33 commits since
previous base) into the same submission branch/PR. Preserve main's Keycloak/native
login and shared external-services package relocation together with branch source
custody/PRE contracts and submission tests. Merge preview identifies9conflicts in
behavior ownership inventory/tests, MCP workflow/hosted tests, PRE interfaces/
model adapter/selected execution, retained fixtures and trusted-intake tests.
Allowed: merge incoming main changes and resolve overlapping files, regenerate
owned inventory only through canonical tooling where necessary; this record.
Prohibited: removing security checks, restoring obsolete PRE paths, losing source
expiry/receipt fields or weakening CI to make merge pass. Review architecture,
QA/security and CI affected intersections; verify syntax/imports, ownership/gates,
focused merged contract tests then current submission public regression. Human
review focus: preserve both current authentication and exact source execution.

Integration resolutions preserve branch source PRE and incoming canonical shared
external-services imports; nine additional branch-only import sites migrated.
The old module and incoming package source are byte-identical; no compatibility
module restored. MCP keeps incoming authenticated fixture and both catalogue
assertions instead of the removed unauthenticated smoke. Combined partition
retains both parents' targets except exact approved relocation; canonical digest
recomputed, both ownership regression tests retained. Review inspection found no
actionable architecture/security or CI/test-delta issue. Initial test collection
failed because the existing venv lacked the new package and has no pip; installed
via uv pip --python and reran:233passed151.31s in ownership/adapter/trusted-intake
modules (/tmp/submission-main-contracts-v2.log). A pytest invocation of the hosted
MCP executable collected0 tests and is not validation evidence. No hosted Docker
runtime claim. Public PG source journey still pending; merge not yet qualified.

Merged public source v1 terminal0:1passed477.66s/schema0084/allcleanuptrue
(/tmp/submission-main-public-v1.json/.log). Actual two-revision cap journey passes
raw ZIP/PRE/T4/OUTBOX T5, exhaustion refusal, retained replay and SQL controls on
combined main/submission code. Metadata tree_sha f33a8440a is premerge HEAD;
evidence executes staged merge content, not clean-commit rerun. Slow run inspected
without restart: no PG lock blockers, two finalized operations then third PRE
confirmed forward progress. Required scoped architecture/security/CI reviews found
no actionable issue. Ruff/record/whitespace pass. Full CI, hosted container/native
provider qualification and remaining spec scenarios are still open.

Late coverage/accepted deadline scope: migrate
 test_late_coverage_return_inherits_the_expired_window_and_expires_once in
backend/tests/tasks/submission_dispatch/test_revision_expiry.py to raw ZIP T4 and
real OUTBOX T5. Wait across the actual original PG deadline after acceptance and
before finalization to verify accepted custody survives it. Preserve zero-round
coverage semantics, inherited anchor/deadline, stale first expiry no-effect and
exact single second-source expiration/statuses/taskrelease. Add accepted-before/
finalized-after deadline assertions and one PRE. Allowed files are that test and
this record; no product/SQL/shared helper changes or historical qualification.
Use existing controlled runtime and source finalizer, retain75second window unless
measured evidence requires test scheduling allowance. Required QA/security/test
review, isolated PG journey plus Ruff/structure/record/diff gates. Review focus:
T4 owns deadline eligibility; T5 cannot invalidate accepted work after deadline.

Late coverage v1 failed155.17s after actual T5: test assumed nonexistent
Submission.created_at. Correct assertion uses owner-persisted intake.finalized_at
and exact finalized_submission_id. Acceptance beat unchanged75second deadline;
no timing allowance needed. Cleanuptrue. Teardown cross-loop log is secondary to
explicit AttributeError. No product change or downstream expiry qualification
from v1; rerun full targeted journey with the corrected owner timestamp.

Late coverage v2 failed359.67s in unchanged completed_evidence fixture before
entering changed journey: initial POST routing_recommendation mismatch; actual
status/source were absent from assertion. Cleanuptrue. Host load was high, but
no timeout root cause is established. Expand allowed test-only scope to
backend/tests/checkers/execution/completion_fixture.py assertion diagnostics:
retain exact comparison, report status/outcome_source/routing_recommendation on
failure. No deadlines or policy changes. This distinguishes infrastructure or
lease outcome from a policy-routing mismatch on next run; a pass alone will not
claim v2 root cause resolved.

Late coverage v3 terminal0:1passed261.72s/schema0084/allcleanuptrue
(/tmp/submission-late-coverage-v3.json/.log). Testblob
70b4abce4b885a32ebae091427fca139f0c65d1c; diagnosticfixtureblob
2430d602328e062520eb7ce912d880f9f7aafd9c. Real acceptance precedes unchanged75s
window, owner-recorded finalization follows it, inherited coverage round0/window
and exactly one second-source expiration/status/task release pass. V2 initial
fixture mismatch remains unexplained; successful v3 is not root-cause proof.
Ruff/record/whitespace passed; structural v2 passed before diagnostic-only two-line
fixture assertion change. Scoped reviewer found no weakening or owner mismatch.
Shared modified-content execution overa326bec95, not independent/cleancommit
rerun or full policy-duration/native-provider qualification. Old expiry-race
creation consumers and full A01-A35/C01-C07 goal remain open.

Expiry-wins T4 race scope: migrate only
 test_due_expiry_and_ready_final_submission_wait_for_task_lock in
backend/tests/tasks/submission_dispatch/test_revision_expiry.py. Complete real
rawZIP PRE then pause before T4; cross original PG deadline and queue expiry
before T4 on real TASK lock, observing both database waits. Preserve expiry
receipt, rejected predecessor/released assignment/taskready/no economic effects.
Replace obsolete ready-admission assertion with failed intake/no acceptance or
finalization event and retained sealed charge. Compare product snapshot after
PRE so legitimate PRE evidence is not mistaken for new product creation.
Allowed files: testmodule and this record; add cohesive test-only outcome helper.
No production/clock/SQL guard changes, no historical migration claim. Required
QA/security/testdelta inspection, isolated race, Ruff/structural/record/diff gates.
Existing creation-boundary tests/shared helpers remain until separately migrated.

Expiry T4 race v1 failed173.81s beforelockrace: reused15second creation-stage
observer expired while newrequest still performs upload/PRE. Initial attempt to
add timeout selector had failed wrongcwd before run; v1executed unchanged helper.
Add optional test-observation timeout(default15 preserved), select60 for full
foreground journey only; no product/policy/lease/window changes. QA-EXPIRY001
requires sealed/exactpositive sourcecharge; QA-EXPIRY002 compares finalization
and POST eventrows against afterPREbaseline. Independent reviewer counterprobes
showed releasedcharge/orphanfinalization would evade v1assertions; batch both
repairs before v2. No production failure inferred from these oracle gaps.

Expiry T4 race v2 failed220.58s with actual23514 'intake task custody mismatch'
at expirycommit, allcleanuptrue: expiry tries to release assignment/TASK while
live prechecking source still owns locked context. Expand scope to
backend/app/modules/tasks/revision/expiry.py: after authorized/fenced/current
source checks, return explicit safe RETRY while TASK has an active source owner.
Foreground T4 still fails original expired deadline and its own finish clears
pointer; same expiry event redelivers and releases once. Accepted pending task
remains stale ACK, not expiry eligible. No ART imports, forced terminalization,
lease theft, SQL relaxation or new capability. Architecture/security review
required alongside QA. Test asserts first explicit retry/no expiration/economic
facts, then waits actual next_attempt_at and delivers sameevent for exacteffect.
Current race plus accepted-afterdeadline/coverage control verify both branches.

Architecture review confirms safe guard placement after authority/fence/currentness
and before expiration writes. Important open liveness gap: default OUTBOX5attempts
with5/10/20/40second backoff may exhaust before a long foreground PRE hard deadline
(up to4h) and its reaper. Explicit same-event test redelivery proves ordering, not
production eventual expiry. C05/recovery envelope must be resolved for fullgoal;
no readiness claim or invented deployment defaults. v3 initial root-cwd launch
failed module discovery before tests; corrected backend launch uses same candidate.

Expiry T4 race v3 terminal0:2passed276.06s/schema0084/allcleanuptrue
(/tmp/submission-expiry-t4-race-v3.json/.log). Productblob
39925240bf85b3db65329bb022706ff81742352b; testblob
9ff0d893420e4a1c9f2f58ac780b3e42732ba417. Race proves real PRE, both TASK lock
waits, known RETRY_REQUESTED (not unknown23514), originaldeadline refusal,
foreground-owned pointer release, actual sameeventgeneration+1 redelivery,
exactoneexpiration/sealedpositivecharge/noorphanT5orPOST. Accepted-afterdeadline
coverage control also passes. AUTH attempted-action decisions may persist on
RETRY; no-product-expiry effect does not mean no audit. Ruff/structure/record/
whitespace pass. Review QA-EXPIRY001/002 closed with independent assertion probes.
Shared modified-content execution overa420f3e3c, not cleancommit/independent rerun.
C05 finite retry-envelope liveness remains unresolved and blocks full readiness;
no automatic eventual expiry, native provider or whole-spec qualification claim.

User correction supersedes fb80e635e's foreground-deferral policy: expiry must
ACK without release once TASK is evaluation_pending, but may expire a current
needs_revision assignment even while upload/PRE is active. It must atomically
invalidate that intake before ready/reclaim; late PRE cannot accept or affect a
new assignment. Replace RETRY-behind-PRE rather than extend retry budgets. The
C05 concern caused by that deferral is superseded for this race. Whether T4 may
accept after clock deadline when T1 started earlier remains a pending user
clarification; do not implement the assistant's proposed relaxation by assumption.

Bounded correction scope: TASK expiry operation/API and composition adapter;
ART-owned intake invalidation via a narrow injected port using current root
transaction, exact task/assignment/actor/predecessor and consumed expiry authority;
foreground terminal-error projection if needed; focused race/security tests and
this record/current specification explanation. Preserve SQL ownership closure,
generation fencing, source receipts/bytecharges and accepted work. No runtime
wait inside expiry, storage deletion, cross-owner private model access, new
service identity or relaxed authorization. Test both lock winners, receiving/PRE
invalidation, late callback/refusal, exact reclaim isolation, rollback and sealed
charge retention. Architecture/security and QA review required before closure;
focused PG and structural/record/owner checks, then single PR708 commit. Human
review focus: one atomic state winner and truthful reclaim guidance.

Atomic expiry correction implements the existing TASK expiry root with an injected
ART participant. It checks exact task/assignment/actor/predecessor and fences only
receiving/PRE generations before clearing the task pointer; source charges remain.
Foreground exception resolution uses fresh own-operation read authority and exact
original lease/generation, actor/key/metadata. Receiving expiry with no committed
EOF is a terminal observation without reading/resuming the body; sealed replay
still checks hash/count. HTTP and operation-status reads preserve the expiry code.
The current T4 deadline cutoff is unchanged. No new worker, timeout policy or
contributor claim-expiry feature is added.

Review QA-ATOMIC001/002 require reclaim-before-late-PRE and rollback with active
intake; the added focused control exercises both with actual HTTP PRE, a committed
expiry invocation, late injected failure, public reclaim and the old callback.
The new assignment has no new active intake; this is assignment-isolation proof,
not a claim to have exercised replacement of a newer non-null intake pointer.
Architecture review found no authority/atomicity bypass. A lease crossing between
clock samples can still cause the authoritative SQL guard to roll back expiry;
normal delivery recovery retries it. No single-attempt availability claim or SQL
relaxation is made. This corrects an already scoped capability, without changing
roadmap delivery/readiness claims or qualifying providers/full-goal completion.

Atomic correction proof: initial PRE race plus inherited late coverage control
passed 2 tests in190.34s, schema0084, complete database/MinIO cleanup
(/tmp/submission-expiry-atomic-v1.log/.json). The active-intake rollback and
late-PRE-after-public-reclaim control passed1 in101.85s with complete cleanup
(/tmp/submission-expiry-atomic-custody-v1.log/.json), including the operation-read
expiry-code assertion. Its pytest child started12:10:29 after the final functional
progress/test edits12:10:28; subsequent admission edit only clarified a docstring.
Shared worktree evidence overfb80e635e, not clean-commit execution. QA design
findings001/002 are covered by that executed control. Ruff, Commitrail, whitespace,
test-structure and changed Markdown-link gates pass.

Expanded atomic expiry run passed5 in346.38s/schema0084/all cleanup complete
(/tmp/submission-expiry-atomic-v2.log/.json): receiving and PRE lock-race winners,
same-key terminal replay, inherited expired-window routing, invalid service and
committed-resource substitution, and late outbox/audit rollback. Separate custody
control above proves active-intake rollback/reclaim isolation. Module/authorization
boundary suite passed92 in101.54s. These are bounded shared local proofs; full-suite
CI, provider qualification and remaining specification work are still required.

Next bounded cutover proof: replace the remaining JSON creation commit-boundary
race in test_revision_expiry.py with raw ZIP/PRE/T4 and actual T5 continuation.
The old test still calls the removed public JSON contract and patches the old
TaskSubmissionCreationService. Preserve both timing branches: committed timely
T4 protects pending work; a transaction held beyond its existing eligibility
cutoff rolls back acceptance and lets due expiry release the assignment. Do not
relax current deadlines or alter production behavior. Inspect/delete only the
now-unreferenced local old-path helper/imports; shared consumers remain intact.
Allowed files: that test and this record. QA/architecture review focuses on real
transaction locks, no orphan accepted event/product facts, exact retained source
charge, timely accepted continuation and unchanged historical source. Run both
PostgreSQL branches plus relevant static gates. Single PR708; no merge/readiness
claim. This advances A11/A12/A31/A35 and old-producer retirement without treating
fixture success as complete specification/provider qualification.

Commit-boundary v1: timely branch passed; late branch failed180.62s with expected
SQL23514 'revision acceptance is no longer eligible' at deferred commit, but API
returned503 submission_infrastructure_unavailable. Cleanup complete. This is a
conclusive acceptance rollback mislabeled by generic IntegrityError translation,
not unknown commit. Expand scope narrowly to foreground_admission.py: after that
rollback, fresh authorized exact-owner read plus canonical TASK context recheck
may classify a confirmed expired revision as revision_deadline_expired. Do not
infer expiry from SQL text or map other integrity errors to expiry. Preserve
unknown-commit handling and all deadline/SQL rules. Late-race terminal proof must
permit foreground to finish failed with the known expiry code before worker
invalidation, as well as worker cancelled/abandoned; both retain exact charge,
fence and no acceptance. QA/architecture review required for the added projection.
The structural gate found a133-line test; factor finalized-state assertions into
one named helper without weakening or relaxing the gate.

Review refinement: a post-rollback expired context alone cannot identify the cause
of an unrelated integrity error. Replace that broad classifier with a dedicated
constraint identifier on the revision-deadline SQL rejection. Add migration0085
which separates that predicate from other existing acceptance-currentness guards;
no eligibility relaxation or retained-row mutation. Only the named deadline
violation maps to409; all other integrity failures retain their original handling.
Add a real unrelated-integrity failure while the revision window is valid, as
QA-COMMIT001 requests. This expands allowed scope to that migration and the same
foreground translation/test paths, avoiding ambiguous cause inference.

0085 integration includes the canonical Alembic head pin (and retained0084
upgrade starting point) in alembic/env.py, plus tests/conftest.py's exact schema
fingerprint. Actual isolated PostgreSQL upgrade applied0085 successfully; v3
then refused all4 fixture setups at the intentional old fingerprint gate39.59s,
complete cleanup. Measured new canonical hash:
4dd5956392e13454b03eccbe6001ad4f8251a88934539465ea9bc0b049cd4844.
Only the acceptance-currentness function body changes in this migration; no
rows/tables/privileges are replaced. Pin that measured result, not a guessed hash.
Intermediate broad-classifier v2 passed2/232.18s and initial-lease control passed
1/62.39s on0084, but those results do not qualify the superseding named-error fix.

Final named-error candidate: v4 passed4 in283.03s/schema0085/all cleanup complete
(/tmp/submission-t4-commit-boundary-v4.log/.json). Timely T4 remains pending through
stale expiry then real T5 finalizes one dispatch; late deferred revision deadline
returns409 and exact replay without another PRE; unrelated real revision SQL
integrity failure returns503 with no accepted/expiry facts; initial lease-expiry
control remains a generic custody conflict. QA-COMMIT001 is covered. Schema parity
probe (/tmp/submission-0085-schema-parity.py/.log/.json) passed on separate owned
PG: reversing only this function change inside a rolled-back transaction restores
the exact full0084 catalog fingerprint, and rollback restores exact0085 fingerprint.
Cleanup complete. Ruff/structure/record/Markdown links/whitespace pass. Evidence
is shared modified-content execution over532984f33, not independent or cleancommit
execution. Fresh origin/main remainsa2154e8a4 and is already contained. This fixes
existing error semantics and retires this module's old JSON creation dependency;
remaining old producers, full-suite CI and provider/spec readiness remain open.

Next bounded retirement: replace test_dispatch_commit_requires_current_predecessor_checker_fence
in test_submission_predecessor_custody.py. The remaining test uses an old ready
admission and hidden create command; current acceptance must instead reject a
stale checker generation at T4 even if a deliberately frozen TASK context port
returns the earlier valid context. Use public raw ZIP and real PRE, advance the
real checker fence after PRE, retain real AUTH/ART/CHECKERS/SQL, and require no
accepted event/product facts plus retained sealed charge. Positive control uses
current context and real T5 to verify the routed predecessor dispatch. Allowed:
that test module and this record; remove its now-unused old creation-service
import only after checking callers. Shared historical fixtures and other old
consumers remain untouched. No production behavior/SQL/authorization changes.
Risk: lineage/currentness proof; QA and architecture/security review required.
Run both real PostgreSQL branches, static/structure/record gates, then commit to
single PR708. A12/A24/A31/A35 evidence advances; full old-producer retirement,
provider qualification and all-goal completion are not inferred from this test.

QA-FENCE001: generic503 plus rollback alone could credit an unrelated deferred
failure. Preserve cause proof by observing only the staged T4 session's real
commit, capturing and rethrowing its IntegrityError unchanged. Require23514 and
'revision acceptance is no longer eligible' for the stale case, and no commit
error for the valid case. This restores the old test's cause-specific assertion
at the new T4 boundary without exposing SQL diagnostics through the public API.

Fence v1 passed positive T4/T5 but failed stale-case stage observation126.43s:
CHECKERS lock_acceptance independently obtains the same canonical TASK context
through selected_pre_submit_task_guard and refuses the advanced fence before
staging. This is an earlier valid guard, not a product bypass. To retain the
intended independent SQL guard proof, freeze the TASK context factory for that
T4 consumer too, after first proving the genuine canonical port rejects. Keep
CHECKERS validation/source locking and all writers real. Existing broad TASK
factory replacement was also the old test's fault injection; no production
change or additional owner authority is introduced. v2 includes QA's exact
commit-cause observation plus both port instances of that one stale TASK reader.

Fence v2 passed2 in61.85s/schema0085/all database+MinIO cleanup complete
(/tmp/submission-current-predecessor-fence-v2.log/.json). One existing Pydantic
serialization warning comes from the synthetic next-request fixture; no warning
is suppressed. The stale case stages real T4, then observes exact23514 currentness
refusal and full rollback/charged-source custody; valid context reaches real T5
and a valid version2 routed dispatch. QA-FENCE001 counterprobe independently
rejects unrelated23514, wrong SQLSTATE and missing error
(/tmp/submission-predecessor-fence-qa-cause-probe.json). Existing
 test_stale_routed_cause_denies_acceptance_after_successful_pre separately covers
normal context denial; this new boundary is intentionally SQL-backstop proof.
Shared modified-content execution overb9a26bd60, not clean-commit or independent
runtime execution. This removes the old creation-service dependency from this
test, not all remaining hidden old producers or broader qualification work.
Ruff, test-structure, Commitrail record and whitespace gates pass on final content.

Next bounded predecessor cutover batch: move the successful replacement/replay
matrix (human-review true/false) and dispatch SQL cause/receipt substitution test
to public raw ZIP, T4 receipt replay before and after actual T5, and finalized
source-backed admissions. Preserve one physical upload/one PRE, changed raw and
semantic content, exact predecessor/cause lineage, prior immutable history,
consumed admission and valid dispatch, all four SQL substitution refusals and no
economic effects. Allowed: test_submission_predecessor_custody.py, existing test
fixture helper only if required for the file boundary, and this record. Inventory
shared helpers before edits; parameterize only the existing provider-write trace
with unchanged defaults for remaining consumers. No production/migration/authority
changes or hidden old-create calls added. Required QA/architecture review, three
real PostgreSQL cases, Ruff/structure/record/whitespace gates, single PR708 commit.
This removes two more old writer consumers while retaining A05/A22/A24/A31 proof;
full old-producer deletion and specification/provider qualification remain open.

Predecessor replay v1 passed3 in113.87s/schema0085/all cleanup complete
(/tmp/submission-predecessor-replay-v1.log/.json). The full creation-snapshot
replay assertion was added at12:53 after the pytest child began12:52:41; do not
credit v1 with that added assertion. Freeze final content and run v2 including
that stronger no-extra-product/event oracle. Review found lineage/substitution
checks preserved and default trace consumers unchanged. No production gap found.

Frozen predecessor replay v2 passed3 in95.81s/schema0085/all database+MinIO
cleanup complete (/tmp/submission-predecessor-replay-v2.log/.json). Both review
policy branches prove stable replay before/after actual T5, unchanged preparation
and creation graphs, exact one traced physical upload and one PRE, intact prior
history and consumed source-backed lineage; the SQL test retains all four
substitution refusals. Ruff, test-structure, record and whitespace gates pass.
Shared worktree proof overa29886861, not clean-commit/independent execution. Scope
is test cutover, so roadmap capability/readiness claims do not change. Remaining
old preparation/creation consumers and full qualification remain explicit work.

Next bounded predecessor batch removes this module's last hidden creation-command
consumers: foreign predecessor denial and replacement-versus-successor locking.
Use public raw ZIP with a forbidden upload/body to prove foreign lineage rejects
before ART effects, then valid T4/T5 for the retained foreign-cause SQL refusal.
Move the lock race to a real staged T4 root: a successor evaluation of the old
Submission must wait on TASK, then be refused once the new intake is accepted
and pending T5; afterwards T5 must create one valid consumed dispatch. Preserve
all original cross-task/assignment/actor/predecessor denials, exact blocker PID,
old checker-fence/run/routing immutability and final counts. Allowed: this test
module, an existing fixture helper if needed, and this record. No production or
SQL changes assumed; diagnose any concrete reproduced gap before expanding scope.
QA and architecture/security review required; both PG cases and static gates,
same PR708. Shared old preparation helpers remain until their consumers migrate.

Custody v1 passed foreign denial and failed the real post-T4 successor race
(1pass1fail75.83s/schema0085/cleanup complete): the old-source reservation did
not raise. This reproduces A13, not a test timeout. Expand scope to TASK's
post_submit_routing/evaluation_guard.py and migration0086 with normal Alembic
head/fingerprint integration. While TASK is evaluation_pending with an active
intake pointer, a non-evaluation_pending latest attempt is historical and cannot
start a new evaluation. Return False after exact scope validation to preserve
stored replay. Receiving/PRE remains needs_revision and can still observe fence
changes; T5 inserts its new evaluation_pending attempt before its own reservation.
0049 requires that initial attempt state and forbids needs_revision resurrection.
Mirror the predicate in the existing checker INSERT trigger under TASK lock; no
cross-owner private read, new state, service authority or timeout. Add exact replay
and forced-stale TASK reader SQL-denial controls, plus prior fence immutability.
Existing staged T4/T5 race is the regression, with prior PRE stale-fence case as
control. QA/architecture review must verify the initial T5 path stays allowed.

0086 schema probe passed with complete database/MinIO cleanup. Reversing only
the new function predicate restored the exact full 0085 catalog fingerprint;
transaction rollback restored the measured 0086 fingerprint
`b04738514ef38518dc476645c9a9b381d8d893387090b6f8479a1802cc61e3a9`.
Evidence: /tmp/submission-0086-schema-parity.log/.json. Pin this measured catalog
before the focused custody race, historical replay and PRE fence controls.

Custody v2: 3 passed, 1 failed in 229.56s. The real successor race now refuses
correctly and historical replay passes. The SQL negative control expected a raw
IntegrityError, but the existing CHECKERS coordinator translates it to
CheckerRequestConflict. Correct the test to inspect its retained exception
context for the exact SQLSTATE/constraint; no production change. Rerun only this
failed case; the other three controls passed on unchanged product/schema content.
Module/authorization boundaries passed 92 checks; test-structure and Ruff pass.

Custody v3 passed the corrected race case in 45.03s on schema0086 with complete
database/MinIO cleanup (/tmp/submission-predecessor-custody-v3.log/.json). It proves
TASK lock serialization, old-source successor refusal, exact historical replay,
named SQL refusal under a stale application reader, unchanged predecessor facts
and real T5 success. The other three unchanged controls passed in v2; do not
describe all four as rerun after the assertion repair. The existing synthetic
next_request Pydantic warning remains visible. Shared precommit worktree proof
over9b9467653, not an independent or clean-commit execution. QA and ARCH/SEC
inspected the exception translation assertion and found no weakening. This is
A13 handoff protection only; full acceptance/provider/CI qualification remains
open, with the same single draft PR708 and no merge-readiness claim.

Next bounded migration proof: replace the post-upgrade hidden creation call in
`test_revision_upgrade_retains_policy_source_and_running_window` with public
raw ZIP, real PRE/T4 and durable OUTBOX/T5. Preserve genuine guarded 0047 source
creation, whole retained-row equality across upgrade, unchanged policy/window
and historical routing evidence afterward. Assert accepted operation, one PRE,
consumed source-backed admission and valid v2 dispatch. Allowed files: this
record and backend/tests/test_alembic.py; existing fixture correction only if
a concrete mismatch is diagnosed. No product/schema changes or disabling guards.
Risk: migration/lineage proof; QA/test-delta and architecture/security reviewers.
Run this PostgreSQL migration case plus Ruff/structure/record gates. Human focus
is historical evidence preserved while only new work uses current submission.
The older 0047 cap fixture still uses shared preparation helpers before upgrade;
do not delete those helpers until that historical fixture has a retained-data
replacement. Same draft PR708; full qualification remains open.

Retained-window v1 reached the new public call after successful 0047-to-0086
upgrade/history checks but returned infrastructure503 (137.58s). No private
diagnostic appeared in the public envelope. Add failure-only PRE terminal code
and controlled runtime diagnostics to the test before rerunning; do not change
production behavior or replace this historical lineage with a fresh fixture.

The v2 diagnostic shows no runtime call and no new PRE terminal; the archived
0047 policy has `compiled_bundle.entries=[]`. Specification section 20.2 (line1135)
explicitly requires an incompatible locked task to remain blocked pending a
governed rebase/re-release, never silently relocked. Therefore successful new
submission is an obsolete expectation of this particular historical fixture,
not a product defect to bypass. Correct the bounded proof to preserve its
window/history checks and require exact cardinality denial through public HTTP
before body/provider/PRE, with no intake or creation effects. Compatible new
revision acceptance/T5 remains covered by the prior raw-ZIP revision tests.
No policy mutation, historical evidence deletion, or production exception.

V3 confirms exact `IntakeCustodyConflict('intake_requires_one_pre_and_post_checker')`
before runtime, rather than an unknown infrastructure fault (183.69s; cleanup
complete). V4 executes the corrected refusal proof with exact before/after
intake, source-charge, historical PRE, audit and full creation snapshots; body
and source-upload callbacks must not execute. Public503 remains the existing
generic mapping, not an actionable rebase-message claim. No successful migration
T5 claim applies to this zero-PRE fixture. QA and ARCH/SEC independently verified
its pinned archive and specification20.2 before approving the expectation change.

Reviewers found a snapshot SQL defect: source charges use operation_id, not id.
Use explicit table/key pairs for deterministic before/after comparison. This
changes only the snapshot query; no product behavior or refusal assertion. V4
was already running the earlier query; final proof must use corrected V5.

Stopped the confirmed-live V4 pytest child with SIGTERM after the reviewer
identified its invalid snapshot query, saving an unnecessary full historical
rebuild. The isolated runner completed cleanup. V4 is interrupted, not passing
evidence or a timeout. Launch V5 only after that authoritative termination.

Final retained-window V5 passed1 in138.42s at schema0086; database and MinIO
cleanup complete (/tmp/submission-retained-window-v5.log/.json). Genuine0047
window creation and upgrade/history equality remain proved; current public
intake refuses the incompatible zero-PRE lock with the exact cardinality cause,
without reading body, uploading, invoking PRE or changing intake/charge/PRE/
audit/creation facts. Ruff, structure, record and whitespace gates pass. Shared
frozen-worktree evidence overb6c3452c1, not clean-head or native-provider proof.
This removes the post-upgrade hidden-create consumer from test_alembic; the
before-upgrade cap fixture still needs its historical writer replacement.
No capability/readiness claim changed; full cleanup/provider/CI and acceptance
audit remain open under the same goal and draft PR708.

Next bounded change migrates assignment-invalidation race proof from hidden
creation to public source intake at T4. Both lock winners must preserve authority:
accepted pending work cannot be released; invalidation-first cannot accept. Run
real PRE before the race, observe exact TASK blocker PID, actual invalidation
handler and actual T5 for accepted winner. Preserve assignment/audit uniqueness,
source custody and no premature Submission. Allowed: test_assignment_invalidation_
races.py, its sole-use prepare_submission helper in invalidation_support.py, and
this record. Trace helper consumers before removing old preparation imports.
No product or migration change assumed; expand only on reproduced defect. Risk
is authority/workflow/concurrency; QA/test-delta and ARCH/SEC review required.
Verification: both PG race cases, affected shared fixture tests as needed, Ruff,
structure, record and whitespace. Human focus: exact acceptance cutover versus
committed revocation cause, no authority bypass, same PR708 and full goal active.

Race review found an invalid fixture hook: TASK context reads also use the
repository method patched for the invalidation winner. Restrict that hook to
the uniquely named invalidation coroutine; foreground and heartbeat locks stay
unchanged. Stop V1 known-invalid child and let its runner clean up, then run V2.
Strengthen refusal to exact404/submission_unavailable and no accepted/event facts;
assert sealed bytes stay charged, and bind accepted response to observed intake.
Baseline Ruff fixture-import shadowing is removed by importing the fixture module
and exposing the same fixture objects, with no wrapper or changed fixture scope.

V2 reproduced production gap: acceptance winner passed, invalidation winner
failed its root commit with23514 `intake task custody mismatch` (1pass1fail
152.41s). Expand allowed scope to TASK assignment-invalidation API/operation,
TASK/ART composition, ART intake repository and foreground terminal/read mapping,
and the direct-constructor test in test_assignment_invalidation.py. Add a required
TASK-owned ART cancellation participant after exact consumed service authority
and event fence, before release. Validate project/task/assignment/actor, initial
in_progress status and unaccepted state; cancel/abandon by DB lease time, bump
generation, clear pointer, preserve charge in the same root. Reuse existing
submission_unavailable error and current-read authorization for late foreground
and replay. Preserve revision expiry mapping. No migration or new authority.
Add rollback after real intake terminalization before release, exact terminal
code/generation and replay/no extra release assertions. Verify both lock winners,
existing invalidation behavior and focused revision-expiry control.

Rename ART composition to submission_intake_assignment_release_port for both
existing expiry and invalidation participants; update traced expiry-security
test consumer too, with no alias. Add it to allowed files. Expiry still calls
its distinct expire_revision contract; only common terminal read now returns
the exact stored release failure after matching owner/key/metadata/generation.

QA requested one distinct receiving/no-raw control for the new known-failure
replay branch. Add a real HTTP body gate after upload ownership, invalidate via
existing handler, require404 without receipt or PRE/Submission, retain reserved
bytes, and replay with a forbidden body. Own GET must preserve the known code.
This covers the changed no-raw and progress allowlists separately from sealed
PRE/T4 races. Existing V3 cases remain unchanged; execute added case separately.

Final focused evidence: invalidation V3 passed4 in512.33s; receiving V1 passed1
in100.17s. Both schema0086 receipts have complete database/MinIO cleanup
(/tmp/submission-invalidation-race-v3.log/.json and
/tmp/submission-invalidation-receiving-v1.log/.json). V3 proves both exact TASK
lock winners, actual accepted T5, forced post-cancellation rollback, late known
denial/sealed replay, original root/prior-receipt guard and revision-expiry
rollback/late-PRE-after-reclaim. Added receiving case independently proves no-raw
known denial, forbidden replay body, reserved charge and own progress code.
92 module/authorization boundary checks passed in504.63s. Runtime was slower in
the shared busy environment; all runs terminated normally, no timeout credited.
Ruff/record/whitespace pass. Shared precommit proof overd627bfffc, not independent
or clean-head execution. Test-only fixture alias cleanup preserves the same
objects/scopes; it does not change the product evidence. Full goal qualification
and remaining hidden/preparation consumers remain open, same draft PR708.

Next bounded lineage cutover replaces the remaining hidden-create consumer in
backend/tests/tasks/test_submission_lineage.py. Public ZIP/PRE/T4 establishes the
accepted packet; one real service claim/observation drives production T5 roots.
Retain missing-admission substitution and both packet-field consumption refusals after staged
Submission, both immediate packet SQL guard attacks after real finalization AUTH,
full rollback, concurrent identical finalization, exact contribution/assignment/
binding/content lineage, and all existing post-bind immutability attacks. Deliver
the existing durable event after T5 to prove exact completed replay; this latter
step is delivery replay, not initial T5-through-worker proof (covered elsewhere).
Allowed: this test module and record; no product/schema changes assumed. Keep
shared preparation helpers until traced consumers migrate. QA/test-delta and
ARCH/SEC review for custody-test change; run focused PG case, Ruff/structure/
record/whitespace. Human focus: preserve independent packet-guard and rollback
oracles rather than replace them with happy-path assertions. Same PR708.

Lineage V1 reached the real staged Submission/ART missing-admission guard but
failed on the expected exception wrapper (52.59s; cleanup complete). The removed
hidden transaction command alone translated ART failure to TASK failure; current
T5 exposes SubmissionAdmissionConsumptionError directly to its durable owner.
Assert that exact ART exception and unchanged code, retaining every snapshot
rollback check. No product change. Later packet/concurrency checks were not
executed by V1; V2 reruns the entire focused case. Refreshed main remainsa2154e8a4
fully contained by this branch (HEAD..origin/main count0).

Lineage V2 passed1 in41.93s; receipt records schema0086 and complete database/
MinIO cleanup (/tmp/submission-lineage-t5-v2.log/.json). All three exact ART
refusals, both independent immediate SQL packet guards and complete rollback
snapshots passed, followed by concurrent identical T5, completed durable replay,
exact source/assignment/contribution-policy lineage and bound-packet immutability.
Proof uses controlled PRE and local store, direct production T5 and later worker
replay; it is shared precommit evidence over8a854f7a6, not clean-head/provider
qualification. No product/schema change; full goal remains active on draft PR708.

Scoped QA and ARCH/SEC inspection found no remaining actionable finding after
V2; QA-LINEAGE001 resolved by exact direct ART exception oracle. Ruff, record
and whitespace pass; structure validation passed, subsequent oracle correction
only removed lines. Reviewed test blob30964b2a432124d548d430124743a0314cd73e72.

Next bounded change migrates locked-policy refusal tests from hidden creation
to public raw-ZIP T1. Allowed: backend/tests/authorization/task_authority/
test_submission_policy.py and this record initially. Preserve detached corrupt
effective/compiled policy, malformed TASK lock and crossed POST sidecar cases;
assert exact owner error plus public envelope and no body/PRE/intake/charge/
Submission writes. Retain SQL lock mutation guard and rollback, remove only
unreachable creation after failing flush. No policy relaxation, schema or
historical-data changes. Risk: authorization/custody proof cutover; QA and
ARCH/SEC review, focused isolated PG module, Ruff/structure/record checks.
Human focus: precise refusal must precede unrelated cardinality/provider errors.

Policy HTTP V1 reproduced exact PROJECT custody refusal followed by generic500
internal_error instead of existing503 submission_infrastructure_unavailable;
3 SQL guards passed, first public case failed (205.10s), schema0086 and cleanup
complete (/tmp/submission-policy-http-v1.log/.json). Expand allowed scope only
to backend/app/adapters/artifacts/__init__.py: include the existing PROJECT
owner exception in ConfiguredSubmissionCommand.submit translation. Preserve
private diagnostics and all existing error semantics; no new public code.
Rerun all7 cases and module/authorization boundaries. Structure scanner first
exited139 without output; diagnostic rerun active, no pass claimed for first.

Current product fix passed92 module/authorization boundaries in386.93s
(/tmp/submission-policy-boundaries.log). Unchanged full structure checker
passed under system Python3.12.3. UV Python3.12.13 crashed twice with139;
faulthandler points to validate_assertion_maps call at line736. No checker or
policy bypass/edit; /tmp/submission-policy-structure-v2.log retains crash and
/tmp/submission-policy-structure-system.log is the successful system run.
Scoped ARCH/SEC and QA code inspection found no actionable issue; integration
closure remains subject to terminal V2 evidence. No provider qualification.

Policy HTTP V2 passed all7 in289.97s; schema0086 and all database/MinIO cleanup
complete (/tmp/submission-policy-http-v2.log/.json). Three SQL lock mutation
guards and four public refusal cases preserve rollback and exact owner errors.
PROJECT faults now yield existing503; malformed TASK context remains404.
Forbidden body, no PRE, and full selected custody/audit/outbox snapshots pass.
Evidence is shared precommit over168e5268f, not independent frozen-head or
provider qualification. Product blob1474a120c3b8167034369496abef3153b1d30f03;
test blobba939131bd87423af06ce32f268d9bce62c3e411. Full goal remains active.

Remaining traced old writer dependencies are composition authorization tests,
the isolated ART final-denial composition test, named old commit-race tests,
and a real0047 cap-source fixture using replacement creation. Retire shared
writer only with those contracts preserved, including historical-row proof;
current create_accepted remains production T5. No new PR or merge request.

Next bounded retirement removes live hidden-writer dependency from the retained
0047 cap recovery fixture. Capture its genuine guarded v2 cap-blocked rows once
at d31a45773, after null-only projections are removed and before current upgrade;
retain checksum/provenance and capture source as non-executable documentation.
Current test will restore exact predecessor rows, check guards and retained-row
invariance through real upgrade, then exercise current recovery/replay/authority.
Allowed: migration_revision_fixtures.py, test_revision_exhaustion_recovery.py,
test_replacement_creation.py (only traced unused historical helpers), new
checksum-bound cap archive/capture provenance under backend/tests/fixtures and
this record; temporary capture test removed after run. No runtime, migration,
policy or data deletion changes. Risk: retained history/security proof; required
QA/test-delta and ARCH/SEC review, isolated cap recovery and neighboring upgrade
control, Ruff/structure/record checks. Human focus: data snapshot is setup, not
a fabricated current writer or a claim that rawZIP existed in0047. Preserve
replay and revocation proof; incompatible retained policy must remain blocked
under spec20.2 rather than silently relocked for a new successful submission.

Capture V1 failed before producing rows: current ORM reads source_operation_id
on genuine0047 admissions, where the column does not exist (204.29s; allcleanup).
Use detached pre-cutover e2b926288899bcd9b05e1a560ec19b6bca8cfcfc owners for
the one-time capture instead of extending current compatibility projections.
Keep explicit historical0047 adaptations documented. No output from V1 credited.
Captured invocation leases also cannot authorize future replay: restore uses
current authorized delivery continuation rather than extending archived clocks.

Extend allowed scope to test_alembic.py existing incompatible-policy helper:
accept explicit initial-submission headers so cap reclaim reuses the same
exact private-cardinality/HTTP/no-body/no-upload/rollback proof without copying
it. Capture completes the known historical routing invocation with authorized
RETRY before its lease expires (explicit test-only600s lease/1s backoff). Restore
will claim the same event afresh through existing dispatcher authority; no
archived lease extension, unsafe unknown replay or production registry change.

Pinned capture V2 passed1 in134.47s, sourcee2b926288, schema0065 final receipt
and complete cleanup (/tmp/submission-cap-capture-v2.log/.json). Archived rows
are genuine0047 before upgrade,71nonempty tables/twoSubmissions, canonical v2
ZIP hash/length verified and both object bytes retained. Source completion is
retryable with RETRY_REQUESTED from actual authority. Archive SHA256
62f9ae1c767182e3c91dd705a0e282133b44e882921634f7fbc4a41ad3decbde.
Capture/provenance files retained under fixtures; no temporary current test.

User requested correction of fragmented goal tracking. Replace the stale overview
and duplicated implementation snapshot with one current completion checklist.
This expands allowed documentation scope to OVERVIEW.md. Current source trace
shows submission_source_cleanup_execution and its provider factory exist but
have no production worker caller; close that runtime integration before further
optional test migration. Preserve full A01–A35 and C01–C07 requirements.

Current restore V1:2controls passed, cap fixture failed before recovery at strict
UUID decoding of archived routing outcome (575.27s, schema0086, completecleanup).
Use JSON-mode validation consistent with other archived Pydantic values. No
migration/product defect or cap recovery pass claimed. Rerun only the failed
cap case; unchanged assignment-backfill and retained-window controls remain valid.

Cap V2 runner exited migration_failed before pytest, without migration output
or metadata (metadata is written only after migration). No pass or receipt
claimed. The runner reached normal cleanup without reporting a cleanup failure.
Use isolated systemPython3.12.3 environment with the same existing dependency
packages and faulthandler enabled for V3; the unchanged structure checker already
passed on that interpreter after UV3.12.13 native crashes. No product/gate changes
and no root-cause claim for the V2 setup failure. JSON-mode archive parsing also
passed directly against the exact v2 Submission selector before the rerun.

Cap restore V3 passed1 in123.38s under systemPython3.12.3, schema0086 and
complete database/MinIO cleanup (/tmp/submission-cap-restore-v3.log/.json).
Exact0047 restore/real upgrade/history invariance, recovery denial/rollback,
one release, new assignment with incompatible-policy refusal, live invocation
replay and revoked-service denial all executed. The two unchanged neighboring
upgrade controls passed in V1. These are shared precommit proofs over d31a45773,
not an independent final-head/native-provider/full-suite qualification.
SystemPython full structure validation passed; Ruff, record, link and whitespace
checks passed. Overview now checks this fixture cutover complete and puts the
missing production source-cleanup integration first. Full goal remains active.

Production cleanup integration scope: connect the existing sealed-source owner
to an exclusive prefork cleanup queue and a12-hour scheduled bounded sweep.
Require an explicit cleanup profile (page, run and lease bounds, upload-principal
identifier for separately credentialed S3 cleanup); no deployment values invented.
Discover only aged terminal sealed operations in the configured retained namespace,
under current cleanup-service authority. Exclude accepted/retained/released/live
claims, then recheck existing custody and consume exact authority on every claim.
Provider I/O remains outside roots; confirmed absence/settlement alone releases
charge. Repeated or concurrent sweeps and process loss recover through existing
claim generations. Fair ordering moves attempted unresolved work behind older
unattempted eligible work. Explicitly leave unsealed/uncertain-begin/completion
and genuine-orphan reconciliation open until separately implemented and proved.
Allowed: cleanup API/profile and owner, ART worker composition, dedicated worker
module/topology, existing Celery wiring/Settings, intake model+0087candidate-index
migration+Alembic predecessor gate+measured test schema fingerprint; focused
worker/real-PG+Local provider tests, deployment example documentation, overview
and record. No new public/admin deletion surface, retention relaxation, provider
qualification or API upload credential expansion. Risk: security/workflow; QA and
ARCH/SEC reviews required. Proof: registered schedule and bounded/exclusive worker,
real owner+provider sweep, replay/concurrent/uncertain retries, namespace/service
denial and protected accepted custody; migrations/current/predecessor and boundary
checks. Human focus: an indexed candidate is never deletion authority.

User deployment correction: API/application infrastructure and microVM execution
must be separate. The reported t3.large application instance is not required to
provide nested virtualization or local KVM. Dedicated execution infrastructure
and future paid sandbox adapters share the provider-independent core contract;
one PRE session does not mean one shared API/runner host. Inspect and remove
shared-host assumptions within execution integration. Native proof belongs on
the selected runner; do not treat missing API-host KVM as a deployment blocker.
Cleanup test scope also includes the existing stalled-accepted protection test
and registration of the two new test modules in the existing CI lane catalogue;
no lane exclusions or gate weakening are authorized.

Cleanup verification in progress: measured0087 schema fingerprint is
094801f2d9fab469983e8b49ca3a0b260ded61dacd7e823380626637e440be25.
The isolated probe restored the exact0086 fingerprint by dropping only the new
index, then executed the actual0086-to0087 upgrade and recovered the new exact
fingerprint; database/MinIO cleanup completed. First worker run passed the real
reclamation/live-PRE/repeated-sweep case and failed three tests: one test's
one-second lease timed out before committing its intended uncertain claim, and
two denial cases imported their exception from the wrong module. Corrected to
an explicit30-second test lease and the actual exception owner; rerun includes
concurrent sweeps and stalled accepted-source protection. No production profile
value was inferred from those test values. Boundary discovery exposed private
ART imports in the worker adapter; moved candidate composition into the existing
ART root and reused configured namespace composition. Startup validation now
runs before fork, outside Celery's short child-init window, and disposes resources
before return. A failed startup cannot mark the parent validated.

Required reviews of clean1f9ddef55 found CLEANUP-WORKER-ISOLATION-01:
exclusive queue selection does not reject foreign registered task names delivered
to that queue. Accepted repair: use the existing Celery application's task
execution boundary to reject every non-cleanup task in a validated cleanup child,
before task code can initialize ordinary ART capabilities from cleanup settings.
A Celery signal exception is insufficient because signal dispatch can suppress
receiver errors. Add an actual registered-task trace negative and ordinary-worker
positive; retain the existing queue and process guards. No second Celery app or
submission workflow is introduced. Also clarify that successful confirmation
observations include already-confirmed replay; concurrent sweeps may both observe
confirmation, while the database proves exactly one charge release. The test
must assert the durable single-release fact without assuming a particular race
schedule.

Shared cleanup verification closure: V2 passed five selected integration cases in
148.86s, with one namespace fixture error; V3 passed the corrected namespace
case in19.73s. Both isolated receipts report0087 and complete database/MinIO
cleanup. The first boundary/topology run passed104 and failed the new private
edge; the repaired repository boundary passed in28.35s. Structure, scoped Ruff,
record and link checks passed before the review repair. These are modified-tree
runs over884a, not a clean-head full-system or native-provider qualification.

CLEANUP-WORKER-ISOLATION-01 regression executed through the registered
resolve_put_attempt Celery task. Before repair, the cleanup-child negative failed
with DID NOT RAISE RuntimeError while the ordinary-worker positive passed
(/tmp/submission-cleanup-isolation-before.log). The existing application's task
base now rejects foreign task names in before_start; this is a task execution
hook, not a signal receiver. After repair all15 cleanup topology cases passed
in7.82s (/tmp/submission-cleanup-isolation-after.log). The charge concurrency
assertion now allows either one or two successful confirmation observations,
while preserving its exact single durable claim and zero-charge checks.
The source owner/provider semantics are unchanged by this repair.

Repair verification/review closure at clean8928f39244f90402ce796fddac0d8a938a672bce:
ARCH/SEC scoped PASS; QA/test-delta PASS WITH LOW RISKS. QA independently removed
the execution hook in memory and the registered-task negative failed; restoring
the hook passed (/tmp/submission-cleanup-isolation-qa-probe.json). No other
blocking scoped finding remains. System-Python structure validation passed after
the repair. Existing worker regression run passed35; six API startup tests failed
because the --noconftest command omitted the standard test pagination HMAC secret.
Supplying that exact test-only conftest setting passed all six in21.52s; no product
change or gate weakening was made. Record/link/Ruff/whitespace checks passed.
The two implementation commits close sealed-source worker integration only.
Next runtime work is expired foreground abandonment plus unsealed/uncertain and
orphan reconciliation, followed by separate-runner integration and final goal
qualification. No broker-crash, native AWS, production deployment or full-goal
completion claim is made. One draft PR708 remains the delivery vehicle.

Next runtime scope: recover expired receiving/PRE owners through the existing
source-cleanup worker and existing abandon_expired primitive, then extend the
same cleanup ownership to interrupted/unsealed provider obligations. No alternate
submission lifecycle, PRE worker, accepted-work expiration or source charge
release from mere lease expiry. First recovery step uses the existing indexed
expiry candidates, exact configured namespace and current cleanup service;
each operation gets its own TASK-first root and an after-lock authority recheck.
State/lease are rechecked by the current primitive, which fences the old owner
and releases only its task pointer. Source bytes remain charged. The existing
12-hour sweep is the periodic caller; this step does not claim prompt runtime
reaping or change revision expiry. Allowed files: existing ART intake cleanup,
repository/capacity and their SQL guards as required for later unsealed custody;
ART composition, cleanup provider/worker/API, focused integration tests and
required migration/head/fingerprint files; current runbook and this checklist.
Prohibited: weakening accepted-source retention, synthesizing a sealed source to
release partial-upload charges, using absence or an abort acknowledgement as
settlement, broad provider deletion, introducing deployment defaults. Risk:
security/workflow. Required QA and architecture/security review. First proof:
expired receiving/PRE clears only its exact task guard and rejects late owners;
live and accepted operations survive; revoked service/foreign namespace cannot
mutate custody; source charges remain until separately confirmed cleanup.
Unsealed reconciliation is not considered implemented by this first step.

Expired-foreground first-step evidence: V1 passed eight PostgreSQL cases in
255.14s, including the existing cleanup/retry/accepted-protection cases and both
receiving/PRE abandonment cases. Before finalizing the change, recovery attempts
were individually bounded using the existing explicit profile lease interval,
and the expiry query was changed to bind a database-clock value so the existing
expiry index can supply candidates. V2 passed seven affected cases in164.77s:
both foreground phases, real TASK-lock timeout followed by successful next-sweep
recovery, and service/namespace denial against both sealed and expired targets.
Both isolated runs used schema0087 and report complete resource cleanup.
Logs/receipts: /tmp/submission-expired-foreground-v1.log/.json and
/tmp/submission-expired-foreground-v2.log/.json. The exact module boundary passed
in44.39s; structure, Ruff, record/link and whitespace checks passed. No schema
change, new worker queue, PRE retry or source-charge release was introduced.
These proofs do not implement or qualify unsealed-byte reclamation. The periodic
caller is explicitly the existing12-hour sweep; prompt runtime reaping remains
separate. Required focused review follows against the clean candidate.

Review of9d0e56f30 found a liveness issue: a blocked expired operation can consume
the whole run envelope before sealed work starts. Repair reserves half the
existing run envelope for foreground recovery, leaving sealed processing time;
no new deployment setting or queue. The held-lock test now includes an unrelated
aged sealed source and equal operation/run limits. QA-EXPIRED-001 also requests
a discriminating real PostgreSQL race: authorize discovery, block mutation on
TASK, revoke cleanup service, release TASK, and prove operation/generation/charge
and task pointer unchanged. Both findings are accepted and repaired together.

Unsealed-path inspection, for continuation: current charge_shape requires
sealed_at even for released charges, so partial-source release needs an explicit
SQL/owner extension, never a fabricated seal. Reuse the existing cleanup claim
and authority mechanism with a typed unsealed target. An absent initiation
receipt, checked under operation custody, proves foreground never obtained write
permission; a receipt with uncertain
begin requires scoped handle discovery and settlement; committed EOF permits
exact completion observation. An observed completed version must become a durable
exact cleanup target before deletion, with fresh age protection for late writes.
Local can settle partial writers under its existing operation lock and retained
abort tombstone. S3 abort acknowledgement or one empty observation is insufficient
for writes_settled. Preserve conservative charge for unresolved remote outcomes.
This is implementation guidance, not completed reconciliation or provider proof.

Repair proof: the held-TASK/unrelated-sealed regression failed against9d0e56f30
with confirmed0 rather than1 in58.98s. With half-envelope recovery isolation,
both foreground phase controls and the contention regression passed in the
four-case repair run. Its revocation case reached the correct authorization
denial but expected the wrong exception class; fixed the test to expect the
actual PreparedAuthorizationUnsupported boundary. Exact revocation replay passed
in24.31s and checked unchanged operation/generation/charge/audit state plus the
original task pointer. Logs: /tmp/submission-expired-starvation-before.log/.json,
/tmp/submission-expired-repair.log/.json (3 pass,1 expected-error mismatch), and
/tmp/submission-expired-revocation.log/.json (1 pass). All isolated receipts report
schema0087 and completed cleanup. System-Python structure validation passed after
the repair; Ruff, record/link and whitespace checks passed. No production denial
was suppressed or broadened to satisfy the test. Clean review replay follows.

Clean81d69a20745b1a8f6870c6b0af652d11e48520b8 review closure: scoped ARCH/SEC
PASS and QA/test-delta PASS WITH LOW RISKS. Independent exact-case mutation
removed only after-lock revalidation; the PostgreSQL revocation test failed on
unchanged-state equality because abandonment incorrectly committed, even though
later discovery still raised the expected authorization denial. Evidence:
/tmp/submission-expired-qa-mutant.log/.json, expected1failure19.08s, schema0087,
complete cleanup. Both scoped findings are closed. No unsealed/provider/full-goal
qualification is claimed. Refresh this initiative overview and its INDEX.md
navigation row to remove the obsolete no-production-caller/preparation-only
summary; full capability-ledger/export reconciliation remains in final delivery
scope. The next implementation boundary is interrupted/unsealed and genuine
orphan reconciliation using existing cleanup ownership, followed by the remaining
writer retirement, remote execution and acceptance/configuration qualification.

Unsealed implementation boundary: generalize the existing cleanup claim target
with an explicit unsealed source value bound to operation location, initiation
fence/handle and committed EOF identity. Preserve existing sealed target bytes
and digest domain; no alias or second cleanup subsystem. Carry exact initiation,
handle and completion facts through the same owner/claim/confirmation execution.
Extend SQL target validation/audit digest and permit a reserved charge to become
released only through the same confirmed cleanup tombstone. No-initiation cleanup
uses locked durable absence of write permission. Local partial cleanup uses its
existing operation lock plus an immutable abort tombstone; a discovered completed
source is retained until exact-version custody and fresh age are recorded.
Unknown remote begin/completion remains charged until provider settlement is
proved. Scope includes existing cleanup API, owner/execution/capacity/model,
provider adapters and their source primitives, worker/composition and callers,
0088 migration/head/fingerprint plus focused Local/MinIO/PG retained-data controls.
Do not mark all unsealed reconciliation complete while late completion or remote
settlement is unresolved. Required reviews remain QA and architecture/security.

Unsealed recovery verification on the uncommitted 0088 candidate: the initial
observation run passed nine cases and failed its historical timestamp fixture
because deferred PostgreSQL trigger events prevented restoring the guard. Flush
constraints before restoring that guard, as the existing age fixture does; do
not weaken production triggers. The exact late-completion replay then passed
in 21.88s (`/tmp/submission-unsealed-v3.log/.json`, schema0088, isolated resources
cleaned). It proves observation retains the ZIP and charge, invalidates the old
target decision, and requires an aged fresh exact-version claim before removal.
Add direct SQL substitution probes for operation/hash/fence and old-claim release.
Rename the existing sweep to `sweep_submission_sources` with all callers updated;
there is one sweep, not parallel sealed/unsealed workers. Replace the superseded
test forbidding all terminal unsealed claims with recent-age denial and aged
unsealed eligibility, retaining live-input and competing-claim protection.
Scoped Ruff, module-boundary, structure, link and record checks passed before the
combined rerun. Remote unsealed settlement, orphan reconciliation, retained-row
migration proof and focused review remain required; these local results do not
qualify them.

The combined 0088 Local/PostgreSQL rerun passed all 11 cases in 204.10s
(`/tmp/submission-unsealed-v4.log/.json`): five unfinished-upload phases, recent
partial/completed retention, late-completion age and fresh-version authority,
direct SQL source-substitution rejection, existing sealed-source/live-PRE cleanup,
and stalled accepted-source protection. This run includes the sweep rename.
The full existing cleanup-owner suite and two real-MinIO unsealed adapter cases
are separate verification runs; do not infer their results from these 11 cases.

The two MinIO adapter cases passed in 18.11s
(`/tmp/submission-unsealed-minio-v1.log/.json`, schema0088, isolated cleanup
complete): completed-but-unrecorded bytes are observed and preserved, while
unfinished multipart abort confirms handle absence without falsely reporting
complete write settlement. The Local/PostgreSQL combined-run receipt also
confirms isolated cleanup complete. Native AWS and complete remote settlement
remain unqualified.

The complete existing cleanup-owner module passed all 28 cases in 554.87s
(`/tmp/submission-cleanup-owner-v4.log/.json`, schema0088, isolated cleanup
complete). This covers retained-source barriers, service revocation, decision
substitution, competing claims, stale takeover, transaction rollback and charge
release, including the updated terminal-unsealed age rule. Add a focused actual
0087-to-0088 retained-row test: create outstanding and confirmed sealed claims
using predecessor SQL guards and real authorization decisions, compare source,
charge, upload, operation and audit facts across upgrade, then replay through
the current owner. This uses no fabricated seal or disabled cleanup guard.

The first retained-migration probe stopped in predecessor setup: two volatile
clock reads made its five-minute lease exceed the maximum by microseconds.
Use the same statement timestamp for both endpoints, preserving the production
bound. The direct source-substitution probe now uses a well-formed alternative
SHA-256 identity, so its negative assertion cannot rely on malformed input.

Retained-migration replay passed in 177.84s
(`/tmp/submission-unsealed-migration-v2.log/.json`), and the well-formed source
substitution replay passed in 46.31s
(`/tmp/submission-unsealed-substitution-v2.log/.json`). Both receipts report
schema0088 and complete isolated cleanup. Scoped reviews at clean `e6844b38c`
found no production defect, but QA-UNSEALED-001 identified a distinct omitted
case: a committed initiation intent before provider begin. QA's independent
real-Local probe showed that omitting only abort-tombstone publication permits
late begin despite reported settlement
(`/tmp/submission-unsealed-intent-only-qa-probe.json`). Extend the existing phase
matrix with `intent_only`, require charge release without a seal, inspect the
exact tombstone and absence of upload.json, and require late begin refusal while
the original upload deadline is still valid. Architecture/security agreed this
must discriminate tombstone protection from expiry. No production change is
needed for the finding; the focused test closes its missing regression proof.

The intent-only case passed in 21.11s
(`/tmp/submission-unsealed-intent-only-v1.log/.json`, schema0088, complete
isolated cleanup). Scoped Ruff and whitespace checks passed on the repair.

Clean `89ed11f584909265301a4afc91d149f8d275a173` review closure:
architecture/security PASS and QA/test-delta PASS WITH LOW RISKS.
QA-UNSEALED-001 is resolved. Both reviewers inspected the exact test/record
repair; production code remains the reviewed `e6844b38c` implementation.
Start/end review snapshots matched. Test receipts identify their precommit
worktrees; clean commits were inspected, not falsely presented as exact-head
suite reruns. Remote write settlement, orphan reconciliation, native AWS and the
separate-runner integration remain open under the full goal.

Remote settlement boundary: remove SDK-managed duplicate storage attempts before
adding reconciliation authority. The data-plane S3 client currently configures
`max_attempts=1`, which permits one retry after the original request. Multipart
initiation is not idempotent, so this can create an unrecorded second handle.
Use one total SDK attempt; existing durable owners retain their explicit
observe/retry behavior. Scope: S3 adapter data-plane configuration, focused SDK
wire-level failure tests and neighboring source/cleanup controls, plus this
record. Do not change STS credential acquisition, widen deletion authority,
fabricate settlement for retained ambiguous uploads, add a new retry workflow,
or declare remote reconciliation complete. Acceptance: a retryable multipart
start failure sends exactly one HTTP creation request and surfaces uncertainty;
normal upload/observation and lost-ack cleanup controls remain valid. Risk:
provider transport behavior; required review is QA and architecture/security.
Human focus: distinguish eliminating new duplicate attempts from proving old
uncertain writes settled. Botocore's official Config reference defines
`total_max_attempts=1` as one request including the initial attempt.

The real SDK/HTTP regression failed before repair in 6.57s: one
`begin_source_upload` call sent two POST creation requests after a retryable503
response (`/tmp/submission-source-sdk-retry-before.log/.json`). The endpoint
supplies normal bucket-versioning metadata, so failure reaches actual multipart
initiation. `AWS_MAX_ATTEMPTS=9` is set to verify the explicit adapter bound wins
over environment retry policy. Change only the data-plane AioConfig to
`total_max_attempts=1`; STS configuration remains unchanged. The
[official Config reference](https://docs.aws.amazon.com/botocore/latest/reference/config.html)
defines this distinction. This repair prevents new hidden retries; it does not
retroactively settle a retained unknown handle or authorize charge release.

After repair, the SDK HTTP regression and neighboring real-MinIO source,
lost-begin/lost-completion, exact-version deletion/lost-delete acknowledgment,
uncertain SHA-object put and unsealed observation controls passed:14 passed,
46 explicitly deselected in33.51s
(`/tmp/submission-source-sdk-retry-after.log/.json`). These selections exercise
the changed data-plane retry behavior and preserve explicit recovery; they are
not a whole-suite result. Ruff, structure and whitespace checks passed.

Clean `49e280d0542fa212745fc833c9157bd8e372818b` scoped review closure:
architecture/security PASS and QA/test-delta PASS WITH LOW RISKS, no findings.
QA independently replayed the exact wire test successfully and restored the old
retry configuration in memory; that mutation failed the same request-count
assertion (`/tmp/submission-source-sdk-retry-qa-probe.json`). Both clean review
snapshots matched. Shared suite receipts identify the precommit worktree, not an
exact-head launch. This closes the SDK duplicate-attempt defect only; existing
unknown upload settlement and orphan reconciliation remain open.

Known-handle remote settlement scope: reuse the existing cleanup claim and
confirmation operation to release a recorded unfinished upload only after scoped
abort, authoritative NoSuchUpload/parts absence, fresh handle discovery and
absence of every object version/delete marker at its managed key. Re-observe
committed EOF after abort so a racing completion becomes the existing durable
exact-version observation, never deletion under a partial claim. Factor the
existing sealed-cleanup version-absence check for both paths. Allowed files:
source cleanup adapter and existing provider/owner tests plus record. Prohibited:
new lifecycle/schema, broad deletion, release on abort acknowledgment alone,
inferred settlement of missing-handle initiation, AWS qualification claims or
changed retained-object policy. Acceptance: real MinIO known partial upload and
lost-abort replay settle; racing completion, surviving parts/versions and unknown
initiation remain protected; late part/complete against the aborted handle fail.
Risk: storage reclamation; QA and architecture/security reviews required.

The affected test scope includes `tests/artifacts/test_source_cleanup_minio.py`
and its existing shared-foundation lane registration: use the current T1 owner,
real PostgreSQL and MinIO, then the existing cleanup execution composition to
prove lost-abort uncertainty retains the reservation and a confirmed replay
releases it once without fabricating sealed custody. Provider-level phase cases
cover completion-before-abort and completion-during-abort, not merely mocked
absence booleans. Surviving parts, unexplained versions/delete markers and
missing-handle initiation remain negative controls. Fresh `origin/main` is fully
contained in the working branch; no integration merge was needed.

Provider selection passed18 cases in95.55s (48 explicitly deselected,
`/tmp/submission-known-upload-settlement-v1.log/.json`). The integrated charge
probe initially failed before provider work because the existing MinIO fixture's
claimed reopenable factory reused one bootstrap/adapter for two simultaneous
clients. Repair that test helper to create a fresh bootstrap per invocation,
retaining the exact same namespace, and include the existing pinned-version POST
test in its rerun. No production bootstrap contract is weakened.

CI on prior head also exposed stale vocabulary in the cleanup operations guide
(`agent-gates`, run45215714126). Reconcile that affected guide with the current
sealed/unsealed behavior and explicitly name Celery processes; do not exempt
the text or weaken the documentation checker. These fixture and ordinary-doc
repairs are within the affected cleanup integration, not a broader migration.

The combined PostgreSQL/MinIO charge test and existing retained-version POST
control passed2 cases in80.86s
(`/tmp/submission-known-upload-charge-v2.log/.json`, schema0088, complete
isolated cleanup). Lost abort acknowledgment left the1024-byte reservation and
unconfirmed claim intact; exact replay released it to zero once without a seal
or fabricated provider generation. Provider results18passed and this integrated
pair are bounded proofs, not native AWS qualification. Ruff, structure,
protected-module boundary, record/link, stale-authorization-doc and whitespace
checks passed. The overview now distinguishes recorded-handle settlement from
the still-open missing-handle and genuine-orphan paths.

Clean31f59daf4 review: architecture/security/documentation scoped PASS; QA found
QA-KNOWN-001, a masked delete-marker negative. Its fixture retained both a data
version and marker, so MaxKeys1/truncation or the version guard could still deny
settlement when the marker guard was omitted. QA's isolated omission mutant
passed that exact test in21.38s
(`/tmp/submission-known-marker-qa-mutant.log/.json`,0088, complete cleanup),
demonstrating the coverage gap rather than a production defect. Repair only the
fixture: after making the marker, remove the exact admin-seeded data version;
assert zero versions and one marker. Keep the separate version-only control.
No production guard or ownership rule changes for this finding.

The repaired marker-only and retained-version controls passed together
(`/tmp/submission-known-marker-only-v1.log/.json`, schema0088, complete
isolated cleanup). Ruff and whitespace checks passed on this test-only repair.

Clean `96c91c718bc39c627caf31bc439f726d437ad271` review closure:
architecture/security/documentation PASS and QA/test-delta PASS WITH LOW RISKS.
QA-KNOWN-001 is resolved. The same independent marker-guard omission now fails
the repaired exact case at `writes_settled is False`, because the mutant returns
true (`/tmp/submission-known-marker-qa-mutant-repair.log/.json`, expected failure
in7.91s,0088, complete cleanup). Review snapshots match; production code remains
the reviewed31f59daf4 change. Supplied suite receipts identify precommit
worktrees rather than exact-head launches. Missing-handle initiation, genuine
orphans, native AWS and full-goal qualification remain open.

Missing-handle recovery boundary: persist a bounded, canonical set of discovered
multipart handle IDs on the existing cleanup claim before aborting those handles.
Bind that set into the next exact cleanup authorization; recording or enlarging
the set invalidates the previous decision. Preserve original upload receipts and
source identities. A lost abort response can then replay all recorded handles
even when LIST no longer returns them. Empty discovery remains unresolved; do
not infer that an unacknowledged begin never happened. Reuse the existing sweep,
claim lease and confirmation/charge release, with no new submission state.
Allowed scope: cleanup API/model/owner/execution/provider, migration0089 and
head/fingerprint, focused Local/MinIO/PostgreSQL and retained-migration controls,
lane selection and affected cleanup documentation. No broad inventory deletion,
retained-data rewrite, new caller authority or native-AWS qualification claim.
Acceptance: discovered handles are durably audited before abort; old or altered
observations cannot authorize removal; lost-abort replay releases once after all
known handles/versions settle; unresolved/no-handle discovery stays charged;
existing sealed and observed-version claims survive upgrade unchanged. Risk:
authorization and storage reclamation; QA and architecture/security review.

0089 implementation evidence: focused real PostgreSQL/MinIO proofs passed for
known/missing handle charge settlement (2 cases, 49.72s), observation growth
before any abort (1 case, 68.96s), empty/unknown initiation controls (2 cases,
18.77s), and the bounded inventory failure (1 case, 31.37s). Logs and isolated
metadata are `/tmp/submission-observed-upload-v2`,
`/tmp/submission-observed-upload-growth-v1`,
`/tmp/submission-observed-upload-empty-v1`, and
`/tmp/submission-observed-upload-bound-v1` (`.log/.json` each). Metadata confirms
0089 and complete resource cleanup. These runs used an uncommitted candidate
based on a46c317a2, not an exact committed-head launch.

The actual 0088 predecessor upgrade passed in 179.95s
(`/tmp/submission-observed-upload-migration-v1.log/.json`), preserving outstanding,
confirmed and observed-version claims and their prior audit identities. This
run covers the 0088 parameter; the 0087 parameter was not rerun for this change.
The measured 0089 schema fingerprint is
`fb82d1094faebbf8c2ae35a71987772af7cd2519944423b5ab91a6902e3c3580`.
Scoped Ruff passed. Native AWS, genuine orphan reconciliation and full-system
qualification are not established by these focused proofs.

Clean 09701e433 scoped review: architecture/security/docs PASS and QA/test-delta
PASS WITH LOW RISKS. Independent early-abort mutation failed the exact
missing-handle test because the cross-session durable handle set was NULL
(`/tmp/submission-observed-before-abort-qa-mutant.log/.json`, expected failure
51.67s, 0089, complete cleanup). Structure, record, links and stale-doc gates
passed. This closes the bounded implementation review, not the full goal.

CI repair scope: a46c317a2 hosted preflight fails partition_target_mismatch;
full collection fails on identical artifact/migration test basenames. Reproduced
locally in `/tmp/submission-cleanup-partition-before.log` and
`/tmp/submission-cleanup-collection-before.log`. Rename only the migration test
and update its lane selector; add exactly the three existing cleanup modules to
the current submission partition allowance and canonical partition, preserving
its protected base and every prior target. Update the existing exact-additions
negative test. Allowed files: that migration test, lane catalogue,
behavior_ownership.py, partition.v1.json, test_behavior_ownership.py and this
record. No workflow, skip, threshold or assertion weakening. Acceptance: full
collection succeeds, partition validates against origin/main, arbitrary neighbor
additions still fail and existing migration tests retain selection. Risk:
CI selection; focused CI-integrity and QA/test-delta review required.

Affected CI scope also includes test_ci_lane_catalogue.py: the existing family
fingerprint predates five intentionally added shared cleanup test modules (four
artifact controls and the cleanup migration). Reconcile its exact count/hash,
without moving any existing test between families. Preserve negative controls.

CI repair verification: exact partition and lane catalogue controls passed
61 tests in 14.26s (`/tmp/submission-cleanup-ci-repair-tests-v2.log`), including
refusal of unapproved additions/removals. Behavior ownership validation passed
against origin/main (`/tmp/submission-cleanup-partition-after-v2.log`). The
initial system-Python validation's secondary stale_catalogue_test error came
from local plugin imports; no catalogue record was changed to suppress it.
Ruff, Commitrail and whitespace checks passed. Full collection is checked
separately; collection success is not execution of the full backend suite.

Clean e858c5e82 CI-integrity/QA/test-delta PASS WITH LOW RISKS. Independent
allowance-expansion mutation is rejected by the existing exact-set test. The
migration rename is byte-identical; exactly five shared test additions account
for the fingerprint delta, with no family moves. Affected pair collection passed
12 tests in 18.82s (`/tmp/submission-cleanup-paired-collection-after.log`, exit 0).

Full local collection is NOT passed: one run printed 12,597 collected tests but
exited 139; a diagnostic run reproduced SIGSEGV in pytest fixture ordering
(`/tmp/submission-cleanup-collection-after-v2.log` and
`/tmp/submission-cleanup-collection-diagnostic.log`, Python 3.12.3). The cause is
not established. Do not substitute the paired collection or focused execution
for full-head qualification. Hosted CI must run on the repaired pushed head.

Main integration and separate-runner scope (user-directed): integrate d713594eb
before further implementation, preserving its direct S3 credentials and app-only
hosting, and all submission custody work. Resolve merge conflicts and affected
callers/tests/docs; remove retired expiring-proof arguments from new source
paths, rather than restoring the deleted subsystem. Preserve both deployed
migration histories using a merge revision. Verification: one Alembic head,
fresh and retained upgrade paths, source upload/cleanup controls, app-host
configuration and import checks. Security/architecture and QA review apply.
Separate runner provisioning lives in worktree workstream_runner on branch
codex/external-runner-provisioning, initially based on current main; integrate
its commits into the existing PR708 rather than opening another PR. The local
AWS profile failed authentication and the user explicitly instructed us not to
use it; await replacement access before any AWS action. Runtime qualification
must use the separate runner and existing app server, with PRE and POST linked
through an authenticated provider capability and no shared filesystem.

Integration verification: fresh PostgreSQL migration through both parents to
0090 passed with measured fingerprint
`1ab3f95836accf52887d6e006d0f37ddfd60bf1269bd945255a46c529ac384a2`
(`/tmp/submission-0090-schema.log/.json`, complete cleanup). The merged graph
and exact lane-family fingerprint checks passed. Source/cleanup integration
passed 61 selected tests in 143.36s, with 146 explicitly deselected
(`/tmp/submission-main-source-integration.log/.json`). These are focused
MinIO/PostgreSQL proofs, not native AWS qualification. Direct AWS cleanup now
compares configured IAM user ARNs; unidentified workload identities remain
refused. Four factory separation/selection controls passed.

Hosted configuration/image checks passed 101 cases plus 319 subtests; two
secret-loader subcases initially failed because the local backend virtualenv
lacked the repository external-services package. Installing that local package
without dependency changes repaired the actual subprocess environment; the
exact test passed with both subcases (`/tmp/submission-main-hosted-loader-v3.log`).
No test assertion or deployment process was weakened for that environment issue.

Merge review found OUTBOX-MERGE-01 (High): app-profile POST exclusions were
passed to the finalization-only registry, so construction raised before T5.
Both reviewers reproduced the same composition failure. Repair intersects the
exclusions with the already selected registry and extends the existing real
PostgreSQL finalization-worker isolation test across app/single-host profiles.
Retain the existing app-host POST deferral/completion test as the general-worker
control. Allowed repair: outbox composition, that worker test and this record;
no delivery guard relaxation or new registry path.

OUTBOX-MERGE-01 repair passed all five real PostgreSQL controls in 27.63s
(`/tmp/submission-main-app-finalization.log/.json`): the finalization worker
rejects both pending and already-claimed POST events under both app and
single-host profiles; the existing app general-worker case retains POST work
while allowing completion delivery. Constructor exclusion validation is intact.
The two retained-upgrade nodes passed in 231.72s:
`tests/test_alembic.py::test_retiring_provider_proof_drops_only_its_tables_and_preserves_artifacts`
and `tests/migrations/test_unsealed_source_cleanup_migration.py::test_upgrade_preserves_sealed_claims_charges_and_audit_decisions[0088_unsealed_source_cleanup]`.
Metadata confirms 0090 and complete isolated resource cleanup. Structure,
protected module boundary, record/link, stale-artifact-contract and Ruff gates
passed on the merge candidate. The repair changes only the exclusion selector
and extends the existing integration test.

Clean fb041d35c review closure: ARCH/SEC PASS and QA/test-delta PASS WITH LOW
RISKS; OUTBOX-MERGE-01 resolved. Both reviewers verified matching clean targets,
registry intersection and the expanded real PostgreSQL cases. Prior scoped
main-integration review stands. This integrates origin/main d713594eb; it does
not establish separate-runner or full-system readiness. The user's explicitly
requested runner worktree now owns infrastructure plus authenticated remote
PRE/POST execution and removal of shared-host material assumptions. The lead
retains submission lifecycle/cleanup and final integration in PR708.


### Retire admission-only TASK submission entry

Intent: make accepted intake custody the sole TASK Submission creation entry;
remove the unused admission-only command and HTTP composition. Risk: high
(authorization and transaction sequencing). Allowed files: TASK composition,
participants, replay helper and adapter; authorization HTTP dependency wiring;
affected composition/binding/revision tests; exact module ownership inventory
and this record. Prohibited: retained rows/schema/audit parsers, ART binding
concurrency behavior, accepted-custody guards, runner-owned files, deployment.
Acceptance: no callable admission-only writer; accepted T5 still atomically
creates one Submission, binding and POST dispatch and replays exactly.
Preserve accepted authority closure and invalid ART-result refusal with focused
replacement tests. Old human-entry denial tests are superseded by T1 revoked
admission/replay and T4 revocation tests; finalization uses service custody.
The old DB final-denial test refused before any write; retain real binding
rollback/concurrency proof and exercise current T5 transactional proof instead.
Remove only old-entry revision mapping tests; retain repair/ART mapping and T4
expiry winner-order coverage. Retained SUBMISSION_CREATE audit parsers stay.
Verification: focused composition, binding, revision, T1/T4/T5 PostgreSQL tests,
Ruff and affected ownership/structure checks. Reviewers: scoped ARCH/SEC and QA
on clean candidate. Human review focus: no bypass of accepted custody or loss
of rollback/replay proof. Same PR708 per explicit user instruction.

The exact inventory check exposed pre-existing duplicate entries at 43ab89385:
s3_compatible.py and interfaces/artifacts.py each appeared three times with
identical groups. Deduplicate those exact entries and refresh the digest;
retain duplicate rejection and all ownership checks. The removed TASK replay
module is permitted only while all accepted-finalization owners remain.

Retirement candidate: 24 focused composition/parser/revision checks passed
(12.55s), including replacement accepted-service authority denial, policy
failure closure, and invalid ART result refusal before dispatch. Test-structure
validation and scoped Ruff passed. Ownership suite: 171 cases passed initially;
exact inventory then passed after removing duplicate entries, sorting and
staging the deleted module (inventory intentionally reads the Git index).
The new accepted-owner-required retirement control passed. PostgreSQL receipt
`/tmp/submission-retire-writer.log/.json` is still running at candidate freeze;
no integration success is claimed yet. No schema or retained-data changes.

QA-RETIRE-001: retained ART concurrency fixture reconstructed a request without
accepted_operation_id, so it would reject before reaching concurrency. Preserve
that exact identity with dataclasses.replace. This isolated ART schema proves
binding concurrency/rollback only; real accepted-source SQL custody remains
covered by the full-schema T5 cases, not this narrow fixture.

Writer-retirement review closure at clean 91116d97b: ARCH/SEC PASS and QA
PASS WITH LOW RISKS; QA-RETIRE-001 resolved. Original PostgreSQL receipt finished
8 passed/1 failed in 306.10s; only the obsolete binding fixture failed. Exact
repaired fixture passed in 3.55s at 91116d97b. Both metadata receipts show schema
0090 and complete cleanup. These are eight precommit integration passes plus
one exact-head repair pass, not a full-suite final-head result. QA independently
omitted authority closure and the replacement denial test failed as intended.
Commitrail, changed Markdown links, stale artifact contracts and diff checks
passed. This closes the admission-only TASK writer retirement; genuine-orphan
cleanup, remote execution/AWS qualification, operational crash evidence and
full end-to-end acceptance remain open under the unchanged goal.


### Process-loss finalization qualification

Intent: close the exception-only worker-loss proof gap with actual SIGKILL
before source observation and after committed T5. Allowed: a focused ART
integration test, exact lane registration and this record. Prohibited:
production behavior/leases/schema/provider changes, runner files, broker or
full-system qualification claims. Risk: medium verification change across
transaction custody; use existing scoped QA/ARCH reviewers. Acceptance: a child
process dies by SIGKILL at each boundary; persisted claim remains unresolved;
after real lease expiry the existing recovery/delivery owners finalize exactly
one Submission/binding/POST dispatch, preserving accepted source identity.
Finalized replay must not reread the provider. Verify real PostgreSQL, child
cleanup, existing structure/lane checks. Human focus: real process death and
committed-state assertions, without fabricated expired timestamps. This does
not replace the distinct lost-ACK tests or prove broker outage behavior.

Initial crash receipt: both processes reached SIGKILL; after-commit passed,
before-observation recovery returned not-ready after a client-clock sleep.
Use a bounded PostgreSQL-clock expiry wait rather than a fixed 50ms margin,
without retrying or weakening the recovery assertion. Switch fork to spawn so
the child cannot inherit pytest threads. Rerun both cases for these harness
changes; no production timing changes.

Spawn rerun failed both startup bounds before reaching either crash boundary;
therefore it supplies no crash/recovery proof. Restore the repository's existing
prefork test approach (matching durable worker topology), whose first run
reached both SIGKILL boundaries. Keep the database-clock gate and fresh child
engine. Record the fork/thread warning as a harness limitation, not production
qualification. No extra retries or enlarged startup bound.

V3: before-observation SIGKILL/recovery passed; after-commit child returned
normally instead of reaching SIGKILL (test correctly failed). Host observed
4 CPUs/load16.23; the harness's 14-second handler deadline can terminate the
real T5 transaction before the kill hook under this load. Use bounded 60-second
custody/55-second handler window (production unchanged), 90-second process
supervision and 75-second DB-clock wait. An unexpected child delivery return
now fails with its delivery receipt for diagnosis. Run the two cases again;
do not credit the failed after-commit run or retry it inside the test.


### AWS source policy preparation

Intent: extend the existing direct-user policy generator for the managed
submission-source prefix and a distinct cleanup principal. The current sha256
only policy cannot support the source adapter. Allowed: aws_direct_user_config,
its focused tests, operations_aws_s3_credentials.md and this record. Risk: high
(storage authority/retention). Prohibited: applying IAM/bucket policies or
reading credentials in this change, app deployment, enabling the AWS intake
gate before actual qualification, deleting retained sources, generic policy
frameworks or expiring activation. Acceptance: runtime has conditional source
writes/exact-version reads but no delete/abort; cleanup has exact-version delete
and multipart abort only inside managed source namespace, no writes or retained
sha256 artifact access; foreign principals and insecure transport denied.
Multipart initiation/parts must be exempt from conditional-header enforcement,
while PutObject and completion still require If-None-Match (AWS official
conditional-writes-enforce documentation). Preserve existing artifact runtime
access. Both principal ARNs must be distinct exact IAM users in the same account
and partition. Verify focused policy controls; ARCH/SEC and QA review before
any actual AWS policy application. Static tests do not establish deployed IAM
behavior; actual AWS qualification remains separately required.

AWS policy candidate checks: 15 focused policy boundary tests passed in 0.83s;
Ruff and diff checks passed. Official AWS action reference confirms multipart
LIST has no s3:prefix condition key: bucket metadata listing is explicit, while
object reads/abort/deletion are source-scoped and version listing is prefix
restricted. No policies applied or source qualification claimed.

Process-loss evidence update: V4 targeted after-commit test passed in 172.42s
at 221f14e85, schema0090, complete cleanup. V3 before-observation case passed
separately at the shorter fixture timing. These results prove local direct
worker process loss, not real broker/native execution or production timing.
The final test file has not been run as an aggregate at one final head. Keep
fork/thread warning and all failed preliminary receipts explicit. Later work
in this candidate only changes AWS policy generation/docs; crash-test code is
unchanged from the exact-head V4 launch.

Review closure: crash scope ARCH/SEC PASS and QA PASS WITH LOW RISKS pinned to
221f14e85 with separate V3/V4 receipts and stated limits. AWS policy scope
ARCH/SEC PASS and QA PASS WITH LOW RISKS at clean 88100a030; no findings.
Independent QA mutations adding runtime abort or removing multipart exception
were rejected by focused tests. No live policy application was performed.
Read-only AWS preflight through the intended workstream-provisioner confirmed
bucket versioning Enabled and retained the existing bucket policy (SHA256
201a11a52f1f9984962190e3a71fceb89b896db9a16a3846928103a1aa191fae).
IAM ListUserPolicies on workstream-storage returned AccessDenied. Prepared
non-secret exact runtime/cleanup/bucket policy files and a two-user-scoped IAM
setup grant under local aws-source-qualification-20261124; requested admin
access/application. No alternate/default AWS credentials used. Runner owner
confirmed no concurrent bucket/IAM work; app configuration remains untouched.
AWS gate and live provider qualification remain open pending access and proof.


### Prepare live source adapter qualification

Allowed: local non-secret qualification script in
aws-source-qualification-20261124 and this record. Risk: high when executed
(provider writes/exact-version deletion); preparation is side-effect free.
Use existing production source/cleanup adapters and private direct-user files,
new UUIDv7 synthetic operation keys only, durable local target journal before
provider creation, and exact upload/version cleanup only for those targets.
Never touch product rows or retained product keys. Refuse ambient AWS settings
and require explicit runtime/cleanup principals. Check conditional multipart,
exact readback, runtime delete/abort denial, lost begin/completion/delete ACK,
and retained independent source survival. Return non-secret results and keep
uncertain targets in the journal. No execution before access is supplied and
bounded ARCH/SEC review of the script hash. This qualifies provider behavior,
not SQL ownership, broker execution, native PRE/POST or the complete journey.

LIVE-AWS-DRILL-01 pre-execution finding: lost-response checks must compare the
reconciled handle/version with the exact successful provider response retained
by the fault injector. The local drill now retains those identifiers in memory
and its fsynced journal, refuses a different discovered upload before abort,
and requires the recovered/deleted VersionId to match. No drill execution or
AWS mutation has occurred; re-review the new script hash before use.

Qualification preparation closure: ARCH/SEC PASS for script SHA256
 a94f860a2efc01f6ac5612c47e5d12fae43bf9aae5b7b56b812ae5ed44aa5ff9.
Compile, Ruff, help/import and optimized-mode rejection before provider/report
I/O passed. No credential contents read or AWS drill executed. Retain an
identical copy as scripts/qualify_submission_source.py in this same PR, with
pilot-specific invocation/limits in operations_aws_s3_credentials.md; these two
paths extend this preparation scope for reproducibility. IAM admin action is
still pending. Runtime file permissions were inspected only and are already0400.


### Join source-preserving finalization to automatic acceptance proof

Concrete gap: source T5/POST integration currently ends at review_pending;
automatic acceptance/award tests use a separate routing source fixture. Extend
the existing source integration with one approved human_review_required=false
policy and money/project_points definitions, using real Operator lifecycle
transitions. Allowed: intake admission fixture, source progress integration test
and this record. Prohibited: production/schema changes, changing default-true
policy behavior, test timestamps/fences, real payments, native/AWS/public-ZIP
qualification claims. Acceptance: the exact source-backed Submission reaches
shared FinalAcceptance, one accepted_submission ContributionRecord with exact
contributor/assignment/source hash/policy, exact configured award definitions,
no Review/reviewer contribution; finalized replay does not duplicate effects.
Verify the added real-PostgreSQL case and default-true control, structure/Ruff;
scoped QA/ARCH review. This joins an owner path, not the pending deployed
public-API/runner proof. Keep other required work in the unchanged goal.

Verification closure at 521898c4f: the automatic-acceptance case and default
human-review control passed together (2 passed in 90.00s); isolated receipt
/tmp/submission-source-autoaccept.json confirms schema0090 and complete database
and MinIO cleanup. The launcher recorded precommit631ece311 with the final test
worktree, so this is compatible evidence, not an exact-head launch. Structure,
scoped Ruff and diff checks passed. ARCH/SEC PASS and QA PASS WITH LOW RISKS
reported no findings; independent QA probes rejected substituted source hash
and award quantity. This proves the source-backed owner path and public progress
read, not public ZIP/native/AWS execution or the aggregate four-case matrix.

Recovery controls at f3e83e200 also passed: expired finalization ownership and
POST infrastructure failure/retry (2 passed in53.58s). Receipt
/tmp/submission-source-recovery-controls.json confirms schema0090 and complete
database/MinIO cleanup. One existing Pydantic serialization warning remains in
the retry fixture. Together with the prior two-case run this covers all four
parameters, across separate runs rather than a single final-head aggregate.
Reconcile the overview/index to these completed boundaries; remaining native,
AWS, broker, preparation-writer and orphan requirements stay open. This is an
evidence update, not a deployed-capability claim or goal completion.

### Preserve retained verifier setup before preparation-writer retirement

The retained-verification tests still manufacture historical SHA admissions
through the superseded preparation command. Capture its pending-verification
rows and exact bytes once, then replace that test setup with checksum-bound
restore using the existing isolated snapshot validator. Allowed: lineage test
fixtures, a bounded historical archive/provenance, and this record. Preserve
the actual verifier, parent locks, rollback, and contributor-lifecycle tests;
do not claim restore executes the old writer. No production, migration, runner,
or retained-data deletion changes. First capture must verify enabled database
guards and exact schema in a read-only consistent transaction. Subsequent
restore must verify row/column/FK custody before running the unchanged verifier
contracts. Risk: medium test-custody change; scoped ARCH/QA review required
before retiring the old fixture. This removes a concrete test dependency, not
the shared preparation service used by guide/import/POST consumers.

Current-head capture diagnosed the stale dependency rather than producing an
archive: old PreSubmitMaterializationPreparationFacts no longer matches current
source-read authorization (AttributeError before pending verification). Receipt
/tmp/submission-pending-capture.json confirms complete cleanup. Do not repair
the obsolete production authorization path to manufacture test setup. Capture
instead from clean detached e2b926288, schema0065, in the separate local
worktree /tmp/workstream-pending-verifier-capture; preserve source provenance
and then exercise real upgrades before current verifier assertions. The failed
capture produced no retained fixture and is not acceptance evidence.

Historical capture V3 passed on clean writer e2b926288/schema0065 (36.76s,
isolated cleanup complete): 55 tables and exactly the pending job's replica
bytes. Archive SHA2561305eaa9de3083d2ca4188f3cdba40a42fa912f211fc90c99ea36989d45e3e38;
capture source retained as tests/fixtures/retained_pending_capture.py.txt.
The initial historical run refused invalid terminal timing; the diagnostic
rerun preserved the timing validator and reached pending verification, then
revealed synthetic guide references cannot be read through the real local
provider. V3 captures only the actual pending job's object; all DB rows remain
literal. No timestamp or authority guards were changed. Retained setup now
restores exact schema0065 rows through the existing validator, performs the real
upgrade, and checks object hash before yielding current verifier tests. Removed
the old _prepared_packet producer from test_submission_lineage.py; preserve its
four lifecycle/rollback/locking cases and mark their actual schema operations.
This does not yet retire other callers of the old preparation command.

The four-case verifier run completed with3fail/1pass (492.26s, cleanup complete).
The unchanged missing-TASK rollback test passed. Actual retained verification
exposed two production defects: publisher decodes archived v1 PRE using the new
source-bound request type, and publication conflict mutates an already-inserted
immutable verification receipt. Extend this bounded scope to the retained
publisher in submission_admission.py and verification completion in service.py.
Use the existing read-only historical PRE decoder, never a new live v1 path.
On publication failure, roll back the verified transaction and retry the exact
job fence under fresh authority with one immutable conflict receipt. Preserve
trigger immutability, bytes and retained parent locks; add a focused publication
failure regression. ARCH/SEC and QA review remain required; the red run is not
successful historical-continuation evidence.

Repair verification at0f80e0135: profile suspension + forced late publication
failure passed2/2 in170.70s (/tmp/submission-retained-verifier-repair.json;
precommit launcher c982e19ee with final repair bytes). Identity-link revocation
and original lock ordering passed2/2 in184.04s at exact0f80e0135
(/tmp/submission-retained-verifier-remaining.json). Both receipts confirm
schema0090 and complete database/MinIO cleanup. Missing-TASK rollback passed in
the earlier four-case run. Structure, authorization boundary, Ruff and diff
checks passed. ARCH/SEC PASS at clean0f80e0135; no guard weakening or live v1
execution restored. QA inspected unchanged original assertion bodies, archive
checksum/byte identity, and the unrelated-integrity-error propagation control.
These separate runs close the retained verifier regression scope, not a single
aggregate final-head run. Spec20.2 still requires deployed old unsubmitted work
to be drained or explicitly stale before cutover; restored historical test
inputs do not authorize deploying with pending old submissions.

### Move revision rejection controls to the raw-ZIP command

Allowed: the unchanged-archive/semantic-manifest and secret-rejection cases in
test_submission_predecessor_custody.py, their selected_predecessor_fixtures
assertions, the existing revision HTTP runtime helper, and this record. Replace
their old prepare/ready-admission calls with public raw-ZIP requests and current
operation receipts. Preserve exact rejection codes, no project execution after
default failure, persisted terminal/authority/source binding, unchanged retained
artifact/Submission/POST facts, needs_revision task state, missing-attestation
warning and a corrected fresh-key acceptance. New source uploads are expected
and remain charged/cleanup-owned; no SHA-artifact put is permitted. No production,
schema, runner or broader test deletion. Risk: medium workflow-test migration;
run both cases on PostgreSQL, structure/Ruff, then scoped QA/ARCH review.

Both migrated cases passed initially (112.31s). QA-REVISION-REJECTION-001 found
that expected HTTP feedback was not compared with the persisted typed terminal.
Added exact public projection equality; the repeated pair passed in106.66s at
abe88c0d2, schema0090, complete database/MinIO cleanup
(/tmp/submission-public-revision-feedback.json). QA's bounded mutation probe
rejects substituted persisted failure code, warning code and finding count.
Structure, Ruff, diff and Commitrail checks passed; scoped ARCH/SEC reported no
finding. These are real HTTP/SQL with controlled guest transport, not native
provider or full deployed journey qualification. Other obsolete preparation
callers remain outside this two-case retirement.

The two-case QA/test-delta review closed PASS WITH LOW RISKS at clean59abae501;
QA-REVISION-REJECTION-001 is resolved. Runner commitdc7fe4b4a was integrated as
179395685 without conflicts. Import-only application/worker checks passed with
an explicit memory broker URL (not broker delivery qualification). The runner
owner reports real mTLS health, native POST and streamed ZIP PRE with exact
bindings and empty workspaces afterward; expected checker failures in those
smokes are not successful governed acceptance.

Frozen runner ARCH/SEC review requires three repairs before app deployment:
REMOTE-MODEL-01 binds callbacks to the issuing connection instead of a global
replaceable app bridge; REMOTE-PROXY-02 drains copy tasks and closes the native
socket on cancellation/timeout; REMOTE-STAGE-03 reconciles or safely quarantines
staged files left by process death before admitting work. The runner owner owns
the batch repair and regression tests. No app configuration or restart occurred.
These are concrete runtime findings; no native production-ready claim is made.

Next test-only retirement replaces the remaining no-routed-cause preparation
case with raw-ZIP HTTP. Allowed: that case in test_submission_predecessor_custody
and this record. Preserve refusal before body/upload/PRE/reservation, unchanged
ART facts, and successful fresh-key acceptance/finalization after the real
routing owner creates revision context, with exact remediation lineage. No
production or runner edits. Verify the one real PostgreSQL case, Ruff/diff,
and focused QA review; existing authority checks remain unchanged.

The public no-route control and routed positive continuation passed together
in30.30s on the integrated runner code; isolated metadata
/tmp/submission-public-unrouted-revision.json confirms schema0090 and complete
cleanup. The launcher recorded9defe33b2 with the final test worktree before
commit2b318e914. The positive path reaches consumed admission through T5 with
the exact routing manifest, not an old ready-only preparation. Ruff/diff and
Commitrail checks passed. This remains controlled runtime evidence, not live
AWS/native public acceptance.

Retire the implementation-only _load_predecessor probe in the same predecessor
test module. Its five-call count belongs to the removed preparation workflow;
raw/semantic refusal and secret/warning behavior are retained in the reviewed
public cases above, and acceptance/replay/consumed lineage in
test_real_replacement_compares_consumed_predecessor_and_replays_exactly. Move
the exact predecessor ID/version/raw hash/semantic hash assertions into that
public case's persisted PRE context before deleting the private probe/import.
Allowed: this test module and record only. No production/retained data changes.
Verify both review-policy parameters of the retained public replacement test,
Ruff/diff, and QA assertion-preservation review. Other old writer callers remain.

Both retained public replacement/replay policy cases passed in57.17s with the
explicit predecessor context assertions. Receipt
/tmp/submission-public-predecessor-context.json records schema0090 and complete
PostgreSQL/MinIO cleanup; its launcher HEAD was9836bfcd5 with these test edits.
This removes only the duplicated private-method probe; the remaining old SQL
reservation/admission fixtures still require migration before writer retirement.

Next bounded test migration: the infrastructure-failed/allow-review POST cases
must still refuse a replacement before reading bytes. Allowed files: predecessor
custody test and this record. Replace their obsolete preparation call with public
raw-ZIP HTTP; retain real POST outcomes, exact public refusal, unchanged ART and
intake counts, no source upload or PRE execution. No production, schema or runner
changes. Medium workflow-test risk; run both parameters on isolated PostgreSQL,
Ruff/diff and focused QA review. Human focus is authority before body consumption.

QA closed the preceding private-probe retirement PASS WITH LOW RISKS at02920f9ff:
all four predecessor-field substitutions fail the new public assertion.
The nonremediation pair first exposed a stale fixture: failing ArtifactStore.open
no longer fails POST because current retained inputs use open_source. Moved the
injected failure to that port and asserted it was reached. Both public refusal
cases then passed in45.39s; /tmp/submission-public-nonremediation-repair.json
records schema0090 and complete database/MinIO cleanup (launcher02920f9ff with
final test edits). Structure, Ruff and diff checks passed. This is controlled
storage failure plus real HTTP/SQL authority proof, not live provider acceptance.

QA closed b976a7d2d PASS WITH LOW RISKS; no lost refusal/infrastructure assertions.
Next bounded retirement migrates the upload-time superseded revision cause test
onto public raw-ZIP intake. Allowed: predecessor custody test and this record.
Preserve real checker-fence advancement during body consumption, refusal before
PRE/admission/Submission, and current-context denial. Unlike obsolete scratch
preparation, the new source upload has durable cleanup custody: assert sealed
charged source survives failed intake without acceptance/finalization. Remove
only now-unused local preparation helper/imports. No production/schema changes.
Medium workflow-test risk; isolated PostgreSQL race test, Ruff/structure and
focused QA review. Human focus: no late acceptance or false quota release.

The upload-fence race passed in42.64s with schema0090 and full PostgreSQL/MinIO
cleanup (/tmp/submission-public-upload-fence-sized.json; launcher8fa9ae12c with
final test edits). The first request hit429 before the race because an unknown
stream length reserved the configured maximum; supplying the exact content
length exercises the intended race without weakening quota. Actual body read
advances the checker fence; fresh context refuses before any PRE reservation,
operation ends failed and its sealed source stays fully charged for cleanup.
One existing POST fixture Pydantic serialization warning was emitted. Ruff/diff
passed. Removed the now-unused local preparation helper and its dependencies.

Runner repair a64729edc integrated as8fa9ae12c. Scoped ARCH/SEC replay passed:
callback connection ownership, proxy cancellation and known workspace residue
reconciliation findings closed. The initially suspected missing worker model
socket was retracted after checking the selected inference Compose overlay.
Agent reports112 focused tests; real provider callbacks and complete public
acceptance remain unqualified. No app deployment or restart occurred.

QA closed upload-fence c8a6cc9da PASS WITH LOW RISKS. Next transfer the last
private predecessor-rule tests to current public intake. Allowed: predecessor
custody test, obsolete artifacts/test_selected_predecessor_rules.py and record.
The positive persisted PRE context must select the consumed admission's rules,
not its different policy-context hash. Four public negative cases substitute
only that read result (absent admission/run/rules or contradictory evidence),
leaving database rows/guards unchanged, and must fail before PRE/acceptance while
retaining charged source custody. Existing initial public source tests prove no
predecessor required. Then retire the old private-method harness. Medium test
migration risk; real PostgreSQL cases, Ruff/structure and scoped QA review.
The same retirement also removes that obsolete module's explicit entry from
backend/scripts/test_lane_catalogue.py; current public replacement tests retain
their existing integration lane. No lane policy or other module ownership changes.
The catalogue's independent shared-family count/digest in
tests/test_ci_lane_catalogue.py is updated solely for this one module deletion;
recursive inventory coverage passed before that expected fingerprint update.
The same inventory check exposed an earlier runner integration omission: the
project-family fingerprint lacked exactly tests/checkers/external/test_remote_node.py.
Removing only that module reproduces the previous digest. Update the expected
project count/digest for that already-owned module; no membership change.

All four public predecessor-custody fault cases and both positive review-policy
replay cases passed in165.79s, schema0090 with complete cleanup
(/tmp/submission-public-predecessor-rules.json). Launcher wasc8a6cc9da with final
test bytes; hosted integration afterward did not alter these tests. No retained
row/guard was changed by fault injection. Structure/Ruff/diff passed. The old
private predecessor-rule harness is now replaced by this current public proof.
Hosted follow-up97750e9c8 integrated092986b8a; ARCH/SEC passed its exact delta.
Runner-only repaired service qualification is coordinated; API remains unchanged.

QA closed predecessor-rule transfer a0856e8fb PASS WITH LOW RISKS. Current remote
PRE cancellation source/execution cases integrated asf9fb0a090 (runner c12fd6cce,
reported113 focused passing cases). Next remove two preparation-only modules:
test_pre_submit_evidence_relock.py and external/test_selected_preparation_command.py.
Allowed files: those modules, test_lane_catalogue.py, test_ci_lane_catalogue.py,
and this record. No production or schema changes. Medium test-retirement risk.
The relock behavior is now the reviewed public upload-fence race c8a6cc9da.
Old selected-before-durable/prepared-size ordering is obsolete: current public
raw-ZIP/replay and source custody tests require sealed exact source before PRE,
then T4/T5. Current no-route/nonremediation public tests refuse bytes before
execution; foreground upload timeout/failure retains charge; expired PRE lease
refuses source/runtime opening. Source/execution cancellation closes readers,
remote transport and staged workspace; upload cancellation retains durable
cleanup custody. Current received-failure and unknown-acceptance tests preserve
recoverable outcomes. All mounted HTTP/shared ART tests remain. Verify exact
lane inventory/fingerprints, current runtime cancellation/expired-lease controls,
Ruff/diff/structure and QA deletion mapping. Remaining old SQL fixtures and
command references still prevent production writer retirement.
Extend the same test-only batch to preparation-command-only cases/fixtures in
 test_submission_bundle_admission.py and test_submission_bundle_preparation_recovery.py.
Retain all mounted/public HTTP tests, public feedback fixture, shared scratch,
limits/bootstrap, and still-existing authorization-class tests. Remove old hidden
factory/endpoint/private lock-order/replay/status projection tests and obsolete
pre/post preparation archive wrappers. Their current public authority, replay,
source failure and cancellation proofs are mapped above and in the QA retirement
review; no old public endpoint or ready-admission contract remains required.
Run both retained modules in addition to focused cancellation/inventory checks.

Retained module checks passed26/26 in19.19s. Current remote PRE cancellation
(source/execution), expired-lease and exact inventory/fingerprint/partition
checks passed6/6 in7.56s. Unused private fixture helpers/imports were removed
afterward; executable retained test bodies are unchanged. Ruff/diff passed.
No production factory or retained-data reader has been removed in this batch.

QA approved c4873cc36 test retirement. Next replace the old superseded-cause SQL
fixture with current public source intake, valid/superseded controls. Allowed:
predecessor custody test and this record only. During upload advance the real
checker fence; freeze only application TASK context/selected-scope reads to the
previous allowed facts so the actual selected PRE INSERT guard is exercised.
Keep all native SQL guards and writes real. Require exact23514 routed-cause
failure, no PRE execution/admission/Submission, retained sealed source charge;
positive control must insert/run PRE and accept202. Medium authority-test risk;
isolated PostgreSQL pair, Ruff/structure and focused QA/ARCH review. No production,
schema or retained-data edits. Foreign-cause SQL fixture remains next.

The valid control passed in the first pair run. Its negative parameter and an
isolated retry failed earlier in fixture creation at the unchanged selected PRE
timestamp ordering guard, before the tested upload. Added exception-only clock
value notes (no timestamp/guard substitution); the targeted negative then passed
in31.11s with exact23514 routed-cause error, zero PRE calls and charged failed
source. Receipts: /tmp/submission-current-pre-sql-fence.json (mixed result),
/tmp/submission-current-pre-sql-fence-retry.json (fixture failure), and
/tmp/submission-pre-clock-diagnostic.json (negative pass); all cleanup complete,
schema0090. Positive and negative evidence is from separate runs, not one clean
aggregate. The intermittent fixture timing cause remains unresolved; a100000
sample database-clock probe observed no backwards samples and does not establish
that no clock adjustment occurred. Retain diagnostic notes for recurrence.
Structure passed before exception-note-only addition; Ruff/diff checked final.

QA/ARCH approved565704c3a within its split-run evidence limits. Final old SQL
fixture migration covers foreign cause at native PRE INSERT, immutable PRE
request, and foreign cause/run at native source-admission INSERT during real T5.
Allowed: predecessor custody test, exclusively unused predecessor/lineage fixture
helpers and this record. Use real local/foreign routed histories; mutate only new
INSERT values. Admission negative probes use transaction savepoints then valid
registration in the same T5 root; retained rows and triggers remain unchanged.
Assert exact SQLSTATE/messages, rollback counts, current source charge, one valid
consumed successor, unchanged foreign history and no economics. Medium workflow/
authority-test risk; isolated PostgreSQL case, Ruff/structure plus QA/ARCH review.
Preserve historical verifier helper and any other shared consumers. No production
writer deletion until this final old fixture dependency is removed and reviewed.
The first new run correctly stopped at namespace validation: HTTP used parent
scratch/root instead of the local fixture's exact root. Corrected that test setup.
The next run reached all SQL probes but T5 then refused PostgreSQL subtransaction
state from the probe savepoints. Keep the real T5 root free of savepoints: first
finalize normally, then probe invalid admission INSERT copies in independent
rolled-back transactions using the actual current source-bound admission. This
preserves exact foreign provenance/lineage guard proof without weakening root
transaction enforcement. No production change or retained-row mutation.

Final foreign-cause case passed in54.97s with full schema0090 database/MinIO
cleanup (/tmp/submission-current-foreign-sql-roots-valid.json; launcher565704c3a
with final test/helper edits). It reaches exact foreign PRE23514, immutable
request55000, and both current source-admission23514 guards, plus valid T5 and
unchanged foreign history. Prior failed setup/savepoint runs remain recorded;
one launcher typo used a shortened MinIO host and was rejected before provisioning.
Structure, Ruff and diff passed. No testcaller of the obsolete preparation
factory/command remains. Historical _verify_put_attempt and its real retained
publisher tests remain; exclusively unused old preparation helpers were removed.

QA/ARCH closed2bb68b49e PASS. Remove the uncalled high-level preparation writer
now: adapter get_submission_bundle_preparation_command; ART durable-put request/
result/service, current_submission_bundle_admission_id, preparation runtime and
command. Allowed files: adapters/artifacts/__init__.py, submission_admission.py,
this record, and affected exact architecture inventory if required. Preserve
historical publisher/error byte-for-byte, packet validation still tested, and
shared ART producers/current foreground source execution. Medium architecture
risk; import app/outbox with explicit test broker, focused retained publisher
contracts, structure/import boundaries, Ruff/diff and ARCH/QA review. Remaining
old low-level ArtifactAdmissionService branch, authorization/request and old
materialization classes are the next coherent deletion, not declared retired yet.
No database migration, retained data deletion, app deployment or new fallback.
Focused publisher checks exposed pre-existing stale pure fixtures constructing
v1 fields through the live v2 type. Add test_selected_pre_submit.py to scope only
for retained publisher fixtures: decode the committed v1 completed capture with
the read-only historical decoder and use its actual terminal shape, preserving
publisher assertions and current live types. Old live materialization tests in
that module remain for the next deletion batch. App import also identified the
shared ArtifactInternalAuthority adapter export; retained it explicitly for
current project routes. No compatibility writer or historical fixture rewrite.

High-level writer retirement verification: app/outbox imports pass with explicit
memory broker (imports only, not broker qualification);5 focused retained-publisher
cases pass9.57s after historical fixture repair; real retained publication-failure
rollback case passes82.65s, schema0090/fullcleanup
(/tmp/submission-writer-retirement-retained.json; launcherf9db6febb with final
production deletion). Publisher/error class ASTs are identical to baseline.
Structure and authorization boundaries, scoped Ruff/diff passed. Fresh origin/main
remainsd713594eb and has0 commits absent from this branch. Low-level old admission
branch/authorization/materialization remain explicitly pending; no complete
writer-retirement or full-suite qualification claim is made yet.

Next delete the now-uncalled low-level prepared-submission writer: the
SubmissionBundleArtifactAdmissionRequest schema/union arm, ArtifactAdmissionService
submission kwargs/branch/intent creation and three private submission-facts/replay
methods, and exclusive submission_custody.py. Allowed: service.py, schemas.py,
submission_custody.py, old DTO-only coordination test, exact architecture inventory,
and this record. Preserve verifier/publisher, ORM/history, shared guide/import/
model/trial producers, current source intake and their authority guards. Remove
only the obsolete DTO-shape test; current source reservation/admission SQL proofs
replace its lineage invariant. Medium architecture/security risk; imports,
architecture/current source contract tests, shared artifact admission tests,
structure/auth boundaries and scoped ARCH/QA. No schema/data/deployment changes.
Architecture tests surfaced stale pre-cutover expectations already in the
current branch: preparation POST (now read-only), two rather than three ART
capability factories (cleanup is separate), and retired Unix transport names.
Update these exact inventories to current public raw-ZIP/read-only history and
remote-TLS constructors. Preserve aliased-constructor mutation controls and
closed composition-root counts; no relaxed wildcard or skipped assertion.

Low-level writer deletion verification passed: shared committed put/independent
verification PostgreSQL case1/1 in32.01s, schema0090/fullcleanup
(/tmp/submission-lowlevel-retirement.json);53 architecture cases42.81s after
current inventory repair (/tmp/submission-retired-writer-architecture.log);
57 current source-first/historical decoder coordination cases13.03s
(/tmp/submission-retired-writer-coordination.log). App/outbox import, structure,
authorization boundaries and Ruff/diff passed. AST comparison confirms verifier/
orchestrator and every surviving admission method except admit/request-boundary
are unchanged. Removed DTO/custody names are now forbidden by the existing retired
intake architecture check. Old authorization and materialization-only code still
needs cleanup; no full-suite/deployment completion claim.

Next remove exclusively old preparation authorization: ART
PreparedSubmissionBundlePreparationAuthorization, its two adapter dependencies
(actor/get-authority), submission_authorization.py protocols/deny types, obsolete
adapter/deny tests and unused prepared_submitter_authority fixture. Allowed:
ART authorization.py, adapter __init__, submission_authorization.py, corresponding
test_submission_preparation_adapter.py/test_submission_bundle_admission.py,
submission_preparation_auth_helpers.py, catalogue/fingerprint and this record.
Keep install_submitter_grant and historical AUTH parsers/binding validation;
keep current source-read issuer PreparedPreSubmitMaterializationAuthorization
and current intake authority. API DTO/old materialization cleanup remains next.
Medium authorization risk; retained shared tests, current intake AUTH tests,
imports/structure/auth boundary and scoped ARCH/QA review. No schema/data/deploy.

Authorization retirement checks passed:8 retained shared/catalogue checks22.22s
(/tmp/submission-auth-retirement-pure.log); current intake exact audit/rollback/
single-use PostgreSQL case1/1 in5.02s, schema0090/fullcleanup
(/tmp/submission-auth-retirement.json). Imports, structure, AUTH boundary,
Ruff/diff passed. Fresh designated-provisioner IAM read still returns AccessDenied
for ListUserPolicies; no policy mutation or credential change was attempted.
Runner owner is preparing the app connection/deployment delta read-only while
root finishes remaining API/materialization retirement. Hosted qualification
still requires the prepared administrative IAM grant/policies.

Hosted connection verification now proves app-host private mTLS to the separate
runner (receipt f7a777a30); API/worker activation remains unproved. Read-only
deployed inventory at 2026-11-24 13:18:50 UTC found schema
0069_remove_artifact_proof, zero contributor admissions/PRE/checker runs/formal
Submissions, and one guide object_confirmed put with one retained replica. A
second read found no workstream_tasks or checker_policies rows. Repeat under
actual cutover drain; preserve guide custody. Receipt:
/tmp/workstream-deployed-cutover-inventory-20261124.txt. Public API module8/8
and CLI submission HTTP/public API18/18 passed with controlled PRE transport;
these are not deployed journey evidence.

Bounded verification repair: update only the independent project ownership
fingerprint in backend/tests/test_ci_lane_catalogue.py and this record. The
runner test addition8fa9ae12c and retired preparation-command test removal
c4873cc36 left the count258 unchanged but changed the exact module mapping.
Replacing current test_remote_node.py with retired
test_selected_preparation_command.py in memory restores the old expected
f2581105 digest exactly; current mapping hashes to2d323a55. No lane ownership,
selector, count or assertion changes. Low risk; verify complete catalogue
module and diff/record checks. Human review focus: independent fixed digest
continues to reject unreviewed ownership changes.

Independent catalogue repair verified:59 tests passed in15.63s
(/tmp/submission-catalogue-current.log); Commitrail and diff checks passed.
The warning reflects running this pure module without the asyncio plugin,
not a skipped asynchronous case.

### Qualify finalization publication recovery through real Redis/prefork

Allowed: the existing test_submission_finalization_worker_loss.py module and
this record. Add one bounded integration proof: signed public raw-ZIP acceptance
through real PRE/T4 owners using the existing controlled guest transport; actual
production scanner publication fails at a closed test-only TCP endpoint while
accepted custody remains intact; restore that endpoint as a transparent Redis
forwarder, run the same scanner and deliver duplicate production finalization
tasks through the exclusive non-eager prefork worker. Preserve real registry,
AUTH, outbox claim/invocation/finalization and provider observation. Observe task
completion without replacing handlers; require one durable Submission, binding
and POST event, stable receipt/replay and retained source charge.

Risk: medium test-process/network custody. Use one isolated PostgreSQL/MinIO
launcher and a unique Redis key prefix; terminate only the owned worker process
group, drain owned proxy connections and remove only prefixed Redis keys. The
shared Redis container must remain running. No production/schema/provider changes
or new queue. Verify focused test, Ruff/structure and scoped review. This does
not qualify Beat scheduling, SIGKILL broker redelivery, native guest execution,
AWS, deployment or the complete public governed-acceptance journey. Existing
SIGKILL owner tests remain separate. User authorized parallel end-to-end proof;
all edits are isolated from the primary checkout.

Initial isolated V1 stopped after public acceptance but before discovery: the
fixture exported local artifact configuration without environment=test, so the
unchanged Settings validator refused local production storage. Receipt
/tmp/submission-finalizer-real-broker-v1.json confirms schema0090 and complete
cleanup; it is not successful broker evidence. Match the existing fixture's test
environment explicitly and isolate/close this proof's Celery connection pools
so later tests do not inherit the temporary broker endpoint.

Final V2 passed1 in109.24s under system Python3.12.3 with real Redis7.4.12.
/tmp/submission-finalizer-real-broker-v2.{log,json} records launcher08066c81a,
schema0090 and complete PostgreSQL/MinIO cleanup; executable test bytes were
728682ecb2092fddbf20d04d7e760964772469fc before execution and remain unchanged. The actual
scanner reports selected1/published0 during connection refusal, then
selected1/published1 after restoration. Original plus two duplicate production
tasks returned SUCCESS from the exclusive prefork child; one recorded delivery
and two unavailable duplicate deliveries leave one completed outbox attempt,
Submission, binding and POST event. Accepted receipt and one PRE invocation are
stable through public same-key replay. Source remains sealed and fully charged;
only T5 clears the task pointer.

The test removes only its unique Redis prefix and owned worker/proxy resources.
A post-run read confirmed shared Redis still responds and no finalizer-proof-*
keys remain. One Python fork-with-threads DeprecationWarning is retained (the
existing repository real-broker prefork pattern); passing does not establish
thread-free process startup or broker-crash redelivery. Production scanner logic
is invoked directly to simulate its next scheduled pass; Beat itself is outside
this proof. The task, registry, delivery/authority and source provider are real;
only PRE guest transport uses the existing controlled fixture.

Ruff and diff checks pass; test-structure validation exits0
(/tmp/submission-finalizer-broker-structure.log). Commitrail gate exits0 before
this evidence append and is repeated for the final record. Original SIGKILL test
and helper ASTs are unchanged. No new module/lane registration or production edit.
This is a single focused precommit execution, not a final-head/full-suite/native
or deployed governed-outcome qualification. V1's setup failure remains above.

Next retire the obsolete ART submission preparation writer API and its exclusive
prepared-bundle materialization module. Remove Request/Result/Command and
writer-only exceptions, header/revision wrappers and stale capacity fixtures;
retain read DTOs/status, historical AUTH/ORM readers, publisher byte behavior,
current source grants and shared scratch cleanup. Migrate revision
acknowledgement, packet-header and cleanup assertions to current owners before
removing obsolete tests. Allowed: ART API/submission admission/materialization,
their direct tests and architecture inventories, catalogue only if selection
changes, and this record. No schema/data/deployment changes. Medium API and
test-coverage risk. Verify current intake contracts, retained publisher and
historical reads, shared scratch cleanup, imports, architecture, structure,
ownership, Ruff and diff; seek scoped architecture and QA review.

Retirement implementation removes the writer Request/Result/Command,
writer-only exceptions, obsolete header/revision wrappers, exclusive prepared
materialization module and its unused capacity fixture. The selected PRE test
module now retains current source-first revision binding, direct TASK revision
acknowledgement and four historical publisher controls; the intake lifecycle
module retains three shared scratch/cancellation cleanup tests. Current
SubmissionIntakeMetadata packet validation replaces the removed header helper
test. ART read DTO/status, historical AUTH parsers and retained publisher stay;
AST comparison confirms the publisher class, publication error, PRE feedback
projections and read DTOs are unchanged. Protected behavior ownership partition
removes exactly this module plus submission_custody.py and
submission_authorization.py, which earlier retirement commits had already
deleted but left listed in the manifest.

Staged-tree verification: selected PRE/coordination/shared cleanup 119 passed;
current intake, admission and packet contract tests 153 passed; artifact and
module-boundary architecture 90 passed; behavior ownership tests 172 passed.
Structure and module-boundary validators, behavior partition validator,
Commitrail record check, Ruff and diff check passed. No PostgreSQL/storage or
native PRE qualification is claimed from this retirement-only verification.
An attempted whole-backend collection using the base backend virtual environment
collected 12080 cases but ended with eight unrelated optional-agent import
errors because that environment lacks `httpx2`; it is not counted as a pass.
The repository-wide Markdown-link checker also fails unchanged on two links to
the missing `deploy/hosted/SINGLE_HOST.md` in untouched documents.

### Qualify actual broker redelivery after finalization child death

Allowed: existing test_submission_finalization_worker_loss.py and this record.
Reuse its owned Redis endpoint/public ZIP setup and process cleanup for two
production exclusive-prefork cases. A test-only one-shot hook sends SIGKILL to
the actual Celery child immediately before source observation or after the real
T5 run commits and before handler acknowledgement. Never replace finalizer
results, registry, authority, SQL guards or provider observations. Fsync an owned
crash marker and record Celery task-prerun delivery metadata so actual broker
redelivery must preserve the task ID, set redelivered and run in a replacement
child. No manual duplicate publication may satisfy this criterion.

Preserve the real300s ownership lease and database clock. Immediate broker
redelivery must not steal live custody. After PostgreSQL observes expiry, the
production scanner/worker must recover the uncertain invocation, respect its
actual backoff and finalize under a new claim. Require one exact retained graph,
source charge and accepted receipt, generation2 only when T5 had not committed;
committed T5 must replay its original submission without another provider read.
Existing direct SIGKILL tests remain unchanged. Risk: medium test-process/broker
proof; final isolated run covers prior outage plus both crash cases, with exact
worker/proxy/prefix cleanup and scoped review. No production, schema, remote or
shared-container changes. Beat scheduling and deployed/native execution remain
outside qualification.

The first combined death-proof run passed3/3 in838.60s (two unchanged direct
SIGKILL cases deselected). /tmp/submission-finalizer-broker-death-v1.{log,json}
records launcheraaee53f6c, schema0090 and complete PostgreSQL/MinIO cleanup.
Executable test blob8d299d5e52a940b610b5dfc364300a3d5459c0f1 stayed unchanged during
execution; the final evidence append changes only this record. The prior
publication-outage case also passed after factoring its setup/cleanup.

Both actual Celery child kills produced automatic Redis redelivery of the same
task ID with redelivered=True in a different prefork child. Immediate redelivery
returned unavailable while the original300s owner lease remained live. After
PostgreSQL time passed that original deadline, the production scanner and task
recorded INVOKE_OUTCOME_UNKNOWN with the real5s backoff; the next scanner pass
claimed generation2 and acknowledged. Each trace has flags
[False,True,False,False]: original, broker redelivery, owner recovery and final
claim. The before-observation case advances continuation to2; after-commit keeps
continuation1 and the exact original Submission. Both finish with one graph,
one POST event, exactly two completed outbox attempts, sealed charged source,
stable accepted receipt and no second PRE. The committed case performs only its
original provider observation; replay does not reopen source metadata.

/tmp/submission-finalizer-broker-death-observations.json retains the fsynced
boundary/PID and real Celery delivery metadata beside the terminal receipt. All
observed child PIDs are dead afterward; test finally blocks stop their owned
worker groups, drain proxy connections and delete only the unique Redis prefixes.
The Python fork-with-threads warning remains unsuppressed for each case. This
qualifies child loss with a surviving consumer parent and broker, not parent
loss/Redis visibility-timeout reclamation, Beat scheduling, native PRE or AWS.
Ruff/structure/diff pass (structure log
/tmp/submission-finalizer-broker-death-structure.log); final Commitrail check
runs after this append. No production or lane changes, no remote mutation.

### Genuine-orphan scope clarification

Read-only ARCH/SEC assessment at08fd205d0 confirms that spec17.4 makes
managed-prefix inventory for genuinely absent operation records optional.
Earlier notes listing that scanner as required remaining work are superseded
by this clarification. D05 and A14–A17 still require durable ownership before
bytes, exact indexed cleanup, accepted/retained protection and reconciliation
of uncertain known-operation writes, including conservative charges.
Only operations-guide wording changes; no owner, deletion authority, test or
provider gate changes. No orphan discovery/deletion or backlog metric is claimed.
The persistent local checklist now excludes this optional expansion.

The AWS credential guide also names the dedicated Celery process explicitly
and links the canonical source-key specification instead of duplicating its
versioned key example. This resolves stale-vocabulary scan false positives
without changing the scanner, IAM policy, runtime behavior or key format.

### Refresh pending-operation MCP schema descriptions

Configured backend OpenAPI comparison atc853743b6 passed142 and failed2
in150.95s. Recursive comparison isolates the entire drift to the existing
PendingSubmissionOperation description missing from task_get,
task_work_context_get, management_task_work_context_get and management_task_get
snapshots. Allowed change: those four descriptions, canonical hashes and source
SHA provenance, plus this evidence. No schema properties, routes, validation,
authorization or product behavior changes. Low-risk contract metadata refresh;
root review and existing configured drift/tamper-evidence checks verify exact
backend equality. Human review focus: only description/hash/provenance differs.
The current full MCP run remains untouched until terminal. Clean wheel startup
passed1/15.91s with isolated installed wheels and no backend import availability
(/tmp/submission-mcp-wheel-current.log); this is package independence only.

The native journey V3 stopped before PRE because its local runtime omitted the
existing isolated guide parser, and its cleanup profile had no distinct upload
principal. Its isolated PostgreSQL/MinIO cleanup completed. Root started the
existing parser image39fda85bf137cac056f0e04b1f59bb5ce908135ffb3899f568fd518b5c3be706
with network disabled, read-only root, bounded RAM/CPU/process/tmp resources and
only KILL/SETGID/SETUID capabilities. Parser source is unchanged since609f59ed7.
An exact local client ACL permits host UID1000 access; socket10002:10001/0660
and parent10002:10001/0750 remain enforced. A canonical client read of a
source-bound Markdown document passed; receipts are
/tmp/submission-guide-parser-{runtime,proof}.json. This local dependency repair
is not hosted activation or public submission acceptance evidence.

Full non-integration MCP suite completed before the snapshot edit:955passed,
6environment-selected skips,1dependency deprecation warning in3563.09s
(/tmp/submission-mcp-current.log). Separately configured OpenAPI checks exposed
the two failures above; all other configured checks passed. After the exact
four-snapshot refresh, both affected modules passed45/34.62s, including live
backend OpenAPI equality, canonical hashes and current claim HTTP validation
(/tmp/submission-mcp-snapshot-repair.log). Together with the clean-wheel check,
these exercise the six environment-selected checks. Root compared parsed JSON
before/after: only the description, canonical hash and repository SHA differ.
No integration/deployed acceptance claim. Markdown links, Commitrail and diff
checks pass.

Next bounded change: modernize the existing connected public CLI journey in
`cli/tests/journey` and its current `cli/README.md` instructions. The present
script still calls removed `task prepare` and `task submit --admission`, runs a
local native checker socket, and registers Harnessy proof declarations that
need unavailable forge facts. Replace those steps with current raw ZIP
`task submit` and `task submission-operation` reads, the deterministic
`pilots/terminal_systems/mvp` correct/incorrect/pre-missing ZIPs and matching
PRE/POST registry entries, an explicitly configured remote TLS runner, and
the existing real API/Redis/MinIO/PostgreSQL worker path. Keep public setup,
claim, retained submission, governed outcome, contribution, replay, Operator
custody and exact award checks in the same journey. Run a separate default
human-review branch through public review commands if the current contracts
support it. No mocked checker, model, authority, provider or synthetic
Submission/Review/Contribution. No production, schema, deployment or external
service changes; runner image installation is a separate owned prerequisite.

Allowed files: existing `cli/tests/journey/*.py`, the pilot's bounded
`pilots/terminal_systems/mvp/registry.py` input generator, its
connected-journey documentation in `cli/README.md`, and this record. Required inputs are
explicit runner TLS host/port/server name/CA/client certificate/key, exact
intake image/config digests, measured submission execution and cleanup
profiles, PRE/POST registry JSON and pinned image; missing inputs fail before
API or worker start. Worker queues must include exclusive finalization and
source cleanup consumers. Preserve resource ownership/cleanup of this
isolated local drill. Risk: high integration and process custody; require
focused pure tests, static/lint/structure checks, exact real PG/MinIO/Redis
and runner execution with cleanup metadata, then scoped review. Partial setup
or source acceptance cannot be reported as full governed-acceptance proof.

Current scope resolution: the user keeps live human review deferred. The
public default-review branch must stop at `review_pending` and prove it did
not fabricate a Review or Contribution; the main locked-false branch must
reach real automatic acceptance. No human-review API or CLI operation is
added here.

The first isolated run failed before its first CLI call because the evidence
directory parent was not created; both isolated database and MinIO cleanup
completed. After fixing that setup defect, the second run passed public
identity, authority and Project creation. It then exposed a stale CLI-local
service-identity allowlist: the backend accepts
`workstream.artifact.source_cleanup`, but `admin service-actor provision`
rejected it as `invalid_arguments` before issuing HTTP. The bounded change
therefore also allows the exact identity in
`cli/internal/api/admin_inspection.go` and its existing admin HTTP contract
module. The rebuilt CLI passed all 25 focused admin mutation contracts,
including the new positive provisioning case and existing unknown-identity
negative. That second run also cleaned its isolated database and MinIO bucket;
neither diagnostic run reached the external checker.

The third isolated run passed service provisioning and public Project setup,
then its guide compilation stayed queued and timed out. The real guide
compiler requires the hardened fixed-parser socket; this launcher had not
supplied one. The dedicated cleanup child also exited at startup: the
test cleanup profile's null `upload_principal` and shared upload credential
violated its separate-provider-principal guard. The root-owned local parser
now serves a source-bound Markdown read under its fixed UID/GID/socket modes.
The journey uses an independently owned local MinIO instance with a distinct
read/write cleanup IAM user, a private secret file and an explicit profile
naming the actual foreground upload principal. Only the exclusive cleanup
worker receives the second credential. Parser identity, credential separation
and all named files are checked before API startup; a worker process exiting
during startup now fails early. The third run's isolated database and bucket
were removed; it did not reach PRE or POST. These are local drill prerequisites,
not hosted credential or parser qualification.

With those prerequisites, the fourth isolated run reached the real parser and
finished guide compilation as `compilation_invalid_terminal/unsafe_text`.
The sole offending authored prose was a slash-joined count phrase in one
POST check step. It was rewritten as plain prose; the unchanged production
untrusted-result model now validates the authored fixture before API startup.
An in-memory restoration of the slash phrase fails that preflight at the
exact check-step field. No checker runner call occurred in this fourth run;
database and bucket cleanup both completed.

The connected drill now checks the accepted Contribution's original ZIP hash
directly. A separate read-only query in the isolated database compares each
finalized operation, sealed physical charge, source admission, replica and
content to the public operation/submission and exact uploaded ZIP; it also
counts Submission, dispatch, POST run, acceptance, Review, Contribution and
award rows for each auto-acceptance, failed-POST and review-pending Task. The
audit performs no state transitions. Its SQL graph parsed and ran against a
fresh migrated isolated database; the deliberately absent operation yielded
the expected missing-graph assertion, and that database was cleaned. A
successful live graph is still pending the next end-to-end run.


### Retire qualification-script preparation callers

Release image guards exposed an import of removed preparation composition from
run_selected_end_to_end_probe.py. Its only live imports are the locked registry
specification and secret-fixture builders; preserve those exact functions in
public_probe_support.py and retire the obsolete hidden-owner drill. Port the
shared current public/model qualification path from preparation/admission plus
JSON201 to raw-ZIP202, immutable acceptance replay, public operation observation
and actual dedicated T5 worker. Preserve input hashes, model/forge/paid-effect
custody, native verdict and governed-outcome assertions. No old-writer alias,
compatibility route, injected verifier/finalizer or skipped test.

Allowed first scope: run_selected_end_to_end_probe.py, run_public_journey_probe.py,
public_probe_support.py, public_hosted_attachment.py, public_hosted_model_post.py,
their two scripts/test_public_hosted_* guard modules and this record. Require
exclusive finalization worker startup/inspection, and preserve POST fault timing
by pausing only the general worker across T4/T5 before enabling the injected POST
failure. Medium qualification-tool risk: run the36 release guards plus new
current source-flow assertions, imports, Ruff/structure/diff/record checks and
scoped review. No production, remote, IAM, paid call or deployment mutation.

The independently separable local public_intake_trials/public_runtime_trials
remain mandatory follow-up: zero/multi PRE and VM-before-seal vectors are
superseded; transfer current resource/cancellation/deadline safety claims and
use distinct tasks for multiple accepted sources. Do not call those vectors
qualified by this guard repair. Root owns operations wording and current native
journey work; this change does not claim a complete native/model qualification.

Common-flow repair replaces only the obsolete command, not model/forge evidence.
The two helper builders moved unchanged; the hidden-owner drill is deleted after
tracing its live imports. Current _submit sends raw ZIP once, replays its exact
key/body, observes public operation progress with all four selectors bound and
checks real finalized admission/PRE hashes and acknowledged finalization custody.
No preparation/verifier task injection remains. Model replay retains the original
revision acknowledgement instead of asking current work-context to fabricate one.
The local launcher adds an exclusive production finalization consumer and pauses
only its general consumer until the POST fault is installed after PRE/T5. It
uses explicit remote-TLS/source-profile settings and an existing canonical parser
socket; no retired Unix/proof argument or second parser launcher is introduced.
Hosted inspection now requires the already-defined finalization service.

Initial guard replay resolved all9 import failures and exposed one remaining
obsolete stalled-verifier test (35pass/1error). Ported that safety assertion to
current stalled source finalization: only GET is allowed and no finalizer task
may be injected. All40 guards passed20.81s in
/tmp/submission-qualification-guards-v2.log (original36 plus4 current contracts).
New controls cover raw bytes/exact replay, each foreign progress selector with
a valid control, exclusive worker composition and the existing parser socket.
This is local guard/contract evidence, not native or paid execution.

The current CLI/native journey owner confirmed upload/PRE source/execution
cancellation, original deadline expiry, launch/controller loss and POST outage
recovery are not covered by its happy/failure journey. They remain mandatory in
the following local trial-vector migration; this common-flow commit does not
silently remove or qualify them. The old selected-drill README paragraph needs
root's coordinated wording update after deletion. No remote mutation occurred.

Final live-caller trace also found model qualification explicitly requiring an
empty PRE approval, and shared task setup calling removed start/requirements
routes. Port these within the same allowed files: one non-model baseline PRE
plus exactly one paid model POST retains all rubric/profile/budget guards;
claim must prove in_progress/started_at and read current work-context. This is
required current cardinality/lifecycle alignment, not paid execution or a
qualification shortcut. Local zero/multi resource vectors remain separate.

Root's common-flow review required preserving the canonical supplied runner
window instead of an old hardcoded90s override. The launcher now validates the
explicit typed source profile with its owner-selected source-contract context
and refuses any request window shorter than its aggregate deadline; it does
not alter product defaults or shorten a model POST window. A new positive/short
window guard first exposed omitted validation context (40pass/1error), then the
canonical context helper was supplied. The model guide explicitly discloses its
required non-model PRE; all model POST rubric/profile/accounting guards remain.

Final common-flow guards passed41/41 in44.464s at the frozen candidate
(/tmp/submission-qualification-guards-frozen.log). A final DTO trace corrected
task setup to public accepted_at rather than internal started_at; its focused
positive/refusal guard passed1/1 in48.466s
(/tmp/submission-qualification-claim-final.log). These are split local guard
receipts, not one42-case aggregate or actual native/paid qualification.
The bounded in-memory selector mutant removes only task_id comparison; the
named guard fails with RuntimeError-not-raised while the valid control passes
(/tmp/submission-qualification-selector-mutant.json). No source or production
file was mutated by that probe. Root requested the affected README paragraph
update; it now points at current public raw-ZIP flow and labels old drill
receipts as history, retaining the mandatory local-vector gap.
Structure and Ruff/diff pass; final record/link checks follow this append.
No remote action, deployment or paid request occurred.

### Reconcile current delivery scope and capability claims

Allowed scope: affected submission statements in roadmap_status.md, this
initiative overview/index and local one-sheet XLSX/CSV exports. The ledger still
describes the removed two-step writer, empty phase selections and unimplemented
T4/T5; replace those with current owners and distinguish implementation from
unqualified deployment. Preserve default review_pending and user-deferred live
human review, historical receipts, mandatory known-operation cleanup and all
remaining runtime/provider/resource evidence. Do not mark the initiative complete
or imply AWS/native public acceptance from component tests. Verification: compare
claims to current routes/guards and named receipts, Markdown/stale-wording checks,
and exactly one WorkStream RoadMap export sheet with current definition.

Reconciled executive submission summary, lifecycle scoreboard, dependency map,
release gates and current initiative/index boundary against the current raw-ZIP
route, exactly-one phase guards, indexed cleanup and recorded broker/native
transport proofs. Older named hosted receipts remain historical. The initiative
stays Planned; no complete native public or AWS qualification is claimed.
Local ignored sheets/workstream_roadmap.xlsx and CSV export the25 lifecycle
scoreboard rows plus current README definition. Verified identical cell data,
exactly one sheet named WorkStream RoadMap and gitignore exclusion. Markdown
links, stale authorization/review scans and diff checks pass. Full Go CLI
suite also passed on4652f39bd (/tmp/submission-cli-go-current.log); later changes
touch qualification scripts/docs only. Latest main fetch found0missing commits.

The next isolated public drill exposed a guide dispatch transport uncertainty:
the CLI's ordinary 12-second HTTP deadline returned `service_unavailable` with
`outcome_unknown=true` after the request entered the API. The journey now
reads the public setup before dispatch, observes the same setup after such an
unknown response, and replays only the identical compile command and
idempotency key within three bounded attempts. It refuses changed setup
identity, generation or source, failed setup, conclusive errors, and a receipt
that names another setup. Eight focused regressions cover the recovered and
refused cases. This is a journey caller repair; it does not extend the CLI
deadline or claim a completed PRE/POST run. The diagnostic run's isolated
database and bucket cleanup completed.

### A19 public upload resource measurement

Intent: measure the remaining maximum-size public upload resource boundary in
one isolated local qualification, while retaining the existing contract,
deadline, and small real-MinIO tests as separate evidence. This is a test-only
probe, not a new upload path or production setting.

Allowed files: this record and one opt-in qualification script at
`backend/tests/artifacts/qualify_submission_a19.py`. Its non-test basename keeps it outside the regular test
lane so the 500 MiB drill is never selected in ordinary CI. Prohibited changes:
production API/ART/provider
owners, deployment defaults, CLI/MCP journeys, shared service configuration,
and unscoped object deletion. Use a runner-owned temporary PostgreSQL database
and versioned MinIO namespace; launch the existing public route through the
repository's pinned Caddy configuration on loopback. Generate a valid ZIP near
the 500 MiB compressed limit incrementally without an archive-sized file or
Python buffer. The public request uses a test-only dev token mapped to the
fixture's real active identity and must traverse real T1/T2 custody and
the S3 multipart adapter; the PRE result is outside this resource probe.

Acceptance: record raw bytes and part count, Caddy/API peak RSS and temporary
disk, and a timeline showing a held provider part prevents unbounded request
read-ahead. A slow client and a finite provider stall/failure must terminate within
the explicit measured upload envelope, with no accepted receipt, no PRE
session, and retained charged ownership until ordinary cleanup. Verify the
owned bucket/database are cleaned by the isolated runner. Risk is high for
resource use and test-harness interference; verification starts with a small
smoke, then one near-limit run, with other heavy local journeys coordinated.
Architecture/security review focus: no fixture shortcuts around the public
route or source custody, no whole-body spool, no shared namespace deletion,
and resource claims limited to measured processes/provider.
Review tracks: architecture and security inspect public-route ownership,
provider stall/custody and memory evidence; CI integrity inspects opt-in
selection and the isolated runner receipt. Human review should check that
these local measurements support A19 without implying AWS or hosted capacity.

The first public smoke reached both provider holds. Holding the final part
until the hard upload deadline produced an outcome-unknown response because
the foreground lease also expired at that deadline; that run is diagnostic,
not a conclusive terminalization or cleanup proof. The bounded measurement
now returns a controlled provider failure after an eight-second hold, before
the hard deadline, so it can verify the committed failed state and retained
charge. Existing deadline tests remain the hard-deadline evidence.

The finite-stall 6 MiB smoke passed through the pinned Caddy public route,
real API and isolated MinIO source. One 5 MiB part completed; holding the
final part for eight seconds then returning a provider error yielded an exact
503 `submission_infrastructure_unavailable`, a committed failed operation,
no acceptance, and the reserved 500 MiB charge. The client emitted 6,291,618
bytes, read-ahead during the first two-second part hold was zero, API peak RSS
was 248,877,056 bytes (201,003,008 at first sample), Caddy peak RSS was
47,927,296 bytes, and API scratch peak was 143 bytes. Evidence:
`/tmp/submission-a19-smoke5.log`, `/tmp/submission-a19-smoke5.json`, and the
timeline path printed in that log. Isolated database and bucket cleanup were
confirmed. This small smoke does not establish near-limit memory behavior.

One near-limit run then passed from the same isolated worktree at
`814f596fc75d83c0e337e6ff3e136707a2d2efe9`: a generated 496 MiB
ZIP (520,094,278 wire bytes) traversed the pinned Caddy ingress and public
API. The adapter completed 31 real 16 MiB MinIO parts; the final 582-byte
part was held for eight seconds and failed before provider I/O. The exact
response was 503 `submission_infrastructure_unavailable`; DB custody was
committed failed with no acceptance and its 500 MiB charge remained reserved.
During the two-second first-part hold, the client emitted only 7 MiB more.
Across 484 samples over 113.67 seconds, API RSS peaked at 283,742,208 bytes
(200,982,528 at the first sample); the peak before 100 MiB and after 396 MiB
was essentially flat (283,742,208 and 283,525,120 bytes). Caddy peaked at
47,251,456 bytes; API scratch peaked at 143 bytes. Caddy XDG state was
scoped to the test directory. The explicit test profile used a 300-second
upload deadline, 30-second idle deadline, 60-second foreground lease and
16 MiB parts, without changing hosted defaults. Evidence:
`/tmp/submission-a19-max.log`, `/tmp/submission-a19-max.json`, and
`/tmp/pytest-of-abiorh/pytest-6701/test_public_a19_near_limit_upl0/a19-timeline.json`.
The isolated database and versioned bucket were removed by the runner.
This is local MinIO/Caddy resource evidence for a deliberately failed upload,
not native AWS, PRE or accepted-submission qualification.

### Port local native failure vectors to current source intake

Allowed next scope: public_intake_trials.py, public_runtime_trials.py,
public_guide_setup.py, guide_worker.py, run_public_journey_probe.py,
public_hosted_attachment.py, scripts/test_public_hosted_attachment.py and this
record. Preserve actual native launch retries, controller death/restart, original
lease epoch/deadline, exact deletion/foreign-resource control, failure replay,
fresh recovery and authorized POST retry. Use one PRE and separate tasks for
independent accepted vectors; no zero/multi approval or VM-before-EOF claim.
Upload cancellation/timeout must retain reserved source charge and no PRE/T4/T5,
and valid source upload must allocate native processing only after EOF.

Pause only the general worker after each fixture project's guide setup while
measuring PRE resources; the dedicated finalizer stays real. Resume and observe
queued POST execution before the next fixture so it cannot pollute PRE counts.
Read source operations/charges and public progress rather than old admission
status. Keep exact native deadline safety in its current execution-stage guard.
Remove the local worker's scripted parser override but keep explicitly recorded
inference; consume the already-supplied canonical parser service. Local policy
approval must select the exact registered one-PRE/one-POST fixture entries.

Risk: medium qualification control code. Run affected guard contracts, omission
probes, imports, Ruff/structure/record/link/diff and scoped review. Real native
resource/controller vectors require a separately authorized qualified execution;
local contract tests cannot close them. No remote fault commands, deployment or
paid requests will be issued in this repair worktree.

Include the affected README status paragraph in this local-vector scope so
implemented caller migration remains distinct from unexecuted native proof.

Implementation of this bounded port:

- public_intake_trials now sends public raw ZIP with exact declared length;
  cancellation and timeout precede EOF/native allocation and require terminal
  operation, no acceptance/finalization selectors, released Task pointer and
  exact positive reserved charge. The source-upload timeout keeps its original
  stored upload deadline. Default-secret rejection blocks the single external
  image; project rejection retains its exact finding/request/native receipt.
  A deliberately incomplete valid body cannot allocate a VM; after releasing
  its final bytes the accepted source must finalize through public progress and
  the actual dedicated T5 worker.
- public_runtime_trials uses four separate tasks for one-attempt launch
  refusals, controller death and selected-image timeout. POST separately retains
  automatic launch retry/exhaustion; actual aggregate native expiry is pending. It keeps exact native
  create/start/exec/delete counts, shared deadline/epoch, foreign-resource
  survival, failed terminal replay without another VM, and fresh-key recovery.
  The pre-existing public Operator POST outage/retry function is AST unchanged.
  General workers stop only after guide setup and restart before observing each
  queued POST result; T5 is never patched or manually injected.
- Local approvals read exact immutable registered fixture identities inside a
  root transaction, selecting exactly one PRE and POST. Stale approval uses
  otherwise-valid attachments. Hosted approval rejects zero/multiple PRE input.
  The local API now starts app.main:app; the old optional observer module stays
  solely because its shared adapter-transparency test still consumes it. No
  obsolete prepare observer or tracing environment is installed by this flow.
  guide_worker retains recorded inference and production ART source receipts,
  but no longer overrides the real parser. Existing canonical parser socket,
  explicit TLS runner and source profile remain required. Local HTTP request
  timeout derives from upload/runner envelopes, replacing the obsolete90s cap.

Executed contract evidence: affected HostedAttachment/ModelPOST unittest suites
passed45 in224.097s (/tmp/submission-local-vectors-guards-v1.log). The subsequently
added final local registry selection/root-transaction guard passed1 in45.359s
(/tmp/submission-local-approval-guard-v1.log). These are split receipts, not an
aggregate final-head46-case run. Named current PRE and source-failure guards
use controlled typed-shaped facts to check exact selected image/default stop,
charge preservation, no accepted handoff and pointer release; they do not prove
those PostgreSQL/native boundaries end to end. The current native expiry guard
has a valid control plus early deletion, reset deadline and changed epoch
refusals. An in-memory omission of only deletion-at-original-expiry caused its
named guard to fail RuntimeError-not-raised, without editing source files
(/tmp/submission-local-native-expiry-mutant.json and .log).

Ruff, whitespace, record and links passed; structure validation is pending at
this append. No actual native fault, remote service mutation, deployment or paid
model/forge call was performed. Required qualification remains actual connected
upload cancellation/timeout, launch retry/exhaustion, controller death/restart,
original native expiry and POST recovery on an owned node. Native PRE source and
execution cancellation are distinct remaining vectors; provider-stage upload
cancellation does not qualify them. Recorded setup inference does not certify
real model inference. This change ports affected callers, not full-system or
native/AWS qualification.

Root review caught two protocol-shape distinctions before freeze. The actual
smol/pre/admission.rs selects the locked registry's image cache, and pre.rs
passes it to prepare_with_connection: one VM runs both trusted defaults and
optional project execution. Thus the existing image-based `project` trace flag
classifies the whole source PRE VM, not the guest project phase. Default-secret
rejection now requires exactly one native VM and zero external members, never
zero VM. create_pre explicitly has one create attempt; source launch failures
now require one failed launch, no retry and fresh-key recovery. Native automatic
2/3 launch retry/exhaustion is preserved in bounded POST cases: valid source
PRE/T4/T5 precedes fault installation while the general worker is paused, then
real POST consumes the fault. Exhaustion uses unchanged public Operator retry
and a fresh successful POST machine; no finalizer or custody patch.

The selected-image marker timeout also differs from aggregate PRE VM expiry.
The PRE trial requires an unchanged aggregate lease plus its exact retained
failure, not deletion-after-aggregate-expiry. Actual aggregate expiry remains
unqualified. The separate pure original-expiry guard still protects that future
receipt contract; it is not invoked by or credited as the inner-timeout vector.
Controller kill observes native VM execution/controller identity, not proof of
entry into the guest project phase.

Topology limit: public_node_faults reads the runner's lease/cgroup/Smol state
and exchanges operator-local private command/trace files. Current TLS source
execution does not supply authenticated remote fault control or evidence
transport. The requested separate app/runner deployment must not share these
paths or move KVM onto the API host. This operator-local harness is not ready to
qualify that topology; remote fault transport and actual native aggregate
expiry/source/execution cancellation are concrete remaining prerequisites.
No new production control framework or remote action was introduced.

Final current-shape guard result: the two added PRE/POST vector composition
contracts passed2 in91.897s (/tmp/submission-current-runtime-vector-guards-v2.log).
They observe separate tasks, exactly one source PRE creation attempt, native
POST2/3 launch retries, fault installation after accepted T5 and before worker
resume, and the unchanged Operator recovery route. Their first run reported
only two mock argument-index errors, corrected in the final guard source; no
production defect or native execution was inferred. The two-case receipt is
separate from the earlier45 and local-registry1 receipts. No aggregate final-head
suite, remote transport, aggregate-expiry or actual native fault pass is claimed.
Root requested a contention hold; no further guard/probe was launched after it.

The selected wait case is named project_wait_failure. Static tracing through
pre.rs::run_project_phase and guest::run_project shows that its inner timeout
may exit the bootstrap and become implementation_unavailable at the host, before
the aggregate VM deadline. It now requires that exact current classification,
exec-to-delete elapsed time at least the locked selected deadline, and unchanged
aggregate VM epoch/deadline. It does not label generic failure as a proven typed
inner-deadline result or aggregate expiry. A new pure guard has a valid cleanup
before aggregate expiry control plus early-selected-cleanup, reset-lease and
wrong-classification refusals; execution is pending the shared A19 memory-run
slot. Actual receiving cancellation here uses an incomplete one-byte HTTP body;
it does not claim completed remote part upload or native PRE cancellation.

After the A19 runner and its cleanup became terminal, the held selected-wait
pure guard passed1 in30.742s (/tmp/submission-selected-wait-guard-final.log).
No new native or remote run occurred. Full structure validation exited0
(/tmp/submission-local-vectors-structure-final.log) before the final23-line pure
guard addition; protected backend files and ledgers remain untouched. Final
Ruff, Markdown links and whitespace checks passed. Final record gate follows
this evidence append. Executed contract custody is45+1+2+1 separate guards,
not an aggregate49-case or clean-commit runtime run. The native-expiry omission
probe is controlled in-memory evidence only. Actual two-host fault transport,
aggregate VM expiry, native PRE source/execution cancellation and real native
fault execution remain mandatory open qualification, without API-side KVM or
shared runner paths.

A later diagnostic run passed guide activation and reached the first public
raw-ZIP submission, then failed before a source upload was begun. A bounded
exception-class/line probe located `ArtifactConfigurationError` at the
production S3 adapter's required bucket-versioning check; the public operation
reported failed infrastructure. The canonical isolation launcher creates a
fresh bucket without versioning because other test lanes configure it in
their own fixtures. The CLI journey now validates that its runner-owned bucket
and prefix match, enables versioning on only that bucket, and reads the state
back before starting the API or workers. Four focused tests cover the exact
bucket call, foreign bucket/prefix denial and failed readback. The production
versioning guard is unchanged. The diagnostic run's database and bucket
cleanup completed; it did not reach native PRE or POST. Temporary probe code
was removed before the next qualification attempt.

### Align retained migration and task-read test expectations

CI at5c29 exposed stale expectations in task detail, locked policy display and
retained checker-evidence migration tests. Allowed scope: tests/tasks/test_task_detail.py,
tests/tasks/test_project_display.py, tests/test_tasks.py and
tests/test_checker_evidence_migrations.py under backend, plus this record.
Preserve exact audience fields, locked successor isolation and byte-identical
historical columns; acknowledge the explicit nullable source_operation_id added
to historical replicas and assert that it remains null. Use distinct valid
single-image policies for the successor comparison rather than empty selection.
No product, migration, authorization or data changes. Low-risk test-only repair;
verify exact failed cases through the isolated PostgreSQL runner after the live
journey releases the heavy slot, plus Ruff/diff. Root reviews against actual
DTOs/migration and named CI failures; human review focus is preservation of the
original historical/audience assertions rather than broader ignored snapshots.

The same additive-column mismatch also affects
backend/tests/tasks/submission_dispatch/test_migration.py; include that named
retained-data test in scope, asserting source_operation_id is null alongside
its existing exact old-column preservation.

The isolated PostgreSQL replay passed all6 database cases in the seven-case
run, including both historical migrations, both audience projections, guide
successor lock preservation and worker/manager context. The remaining pure
contract assertion expected the generic error for the new pending-operation
field; its exact field-specific message is now checked. The focused pure rerun
passed1/1 in18.57s. Combined-run log /tmp/submission-task-read-migration.log
(6pass/1initialfailure,369.60s); final pure log
/tmp/submission-task-detail-contract.log. Isolated schema0090 database cleanup
is confirmed in /tmp/submission-task-read-migration.json. Pinned Ruff0.15.22
and diff checks pass. No production behavior or retained row changed.

The first clean run with that bucket setup passed the real pre-submit
negative: the missing-summary ZIP produced `pre_submission_checker_failed`,
the public operation was rejected, and no Submission appeared. The correct
ZIP then received T4 acceptance and exact command replay. Its subsequent
public progress reads crossed the T5 commit: the key selector read
`finalization_pending`, while the operation-ID selector read
`finalized/evaluation_pending`. Both named the same durable operation. The
journey had incorrectly required the entire two responses to be equal. It now
compares immutable operation, task, assignment, key, acceptance time and PRE
feedback, refuses state regression and any changed populated Submission
identity, and permits the forward commit between separate reads. Eight focused
tests cover that observed transition and identity substitutions. The run's
isolated database and bucket were cleaned; the automatic POST outcome was not
yet observed in this run.

### Repair shared current-source test constructors after the single-flow cutover

Intent: restore the current POST grant and PRE projection test fixtures without reintroducing prepared-bundle PRE APIs. This is a test and catalogue change only; production source custody, AUTH, SQL, runtime, and CI gate policy stay unchanged. The superseded `test_selected_pre_submit_service.py` invokes a removed materialization constructor and `recover_expired` method. Its claim/commit/finalize behavior is covered by the source-backed real PostgreSQL cases in `test_submission_pre_source.py`; expired lease no-I/O and cancellation drainage are covered by `test_runtime.py`, and TASK-first expired-lease custody by `test_selected_pre_submit_coordination.py`.

Allowed files: `backend/tests/checkers/external/test_selected_post_submit.py`, `backend/tests/contributor_reads/test_projection.py`, the obsolete PRE service test module and, if needed, those named current-source proof modules; `backend/scripts/test_lane_catalogue.py`, `backend/tests/test_ci_lane_catalogue.py`, and this record. Remove the obsolete test and its exact catalogue membership; update the independent fingerprint from the resulting catalogue. No compatibility constructor, relaxed grant source, skipped test, altered production contract, new default, or lowered test gate is allowed.

Acceptance: POST mock execution receives an explicit typed source capability without reading project bytes; contributor projection uses structurally valid source-first PRE results and retains eligible and blocked findings and every custody-state assertion; current-source claim/finalize, expiry no-I/O, and cancellation proofs remain selected. Verify focused pure tests and catalogue/inventory contracts, then run only affected real cases when the shared resource slot is free. Risk: a fixture could become vacuous or the deleted PRE tests could leave an interruption or expiry gap. CI integrity and architecture/security reviews should compare those precise assertions. Human review focus is the evidence map for the deleted tests and the independent catalogue count/hash; this does not claim full CI or native qualification.

Exact retained proof map: `tests/artifacts/test_submission_pre_source.py::test_source_pre_execution_uses_committed_authorized_local_read` owns real source claim, short committed AUTH roots, finalization and failure retention. `tests/checkers/external/test_runtime.py::test_single_pre_expired_lease_does_not_open_source_or_runtime` rejects source/runtime access after lease expiry, and `test_single_pre_cancellation_closes_source_and_transport` owns interruption drainage. `tests/checkers/external/test_selected_pre_submit_coordination.py::test_selected_pre_expired_lease_read_keeps_task_first_custody` owns expired-lease TASK lock order; the adjacent authority-digest test binds the distinct deadline outcome. `tests/artifacts/test_submission_intake_custody.py::test_expiry_can_only_abandon_and_cannot_resume` owns the current required operation-level fence, charge retention, and fresh-key recovery; `test_submission_intake_admission.py::test_t4_and_expiry_serialize_both_winner_orders` owns accepted handoff versus abandonment. Spec section 16 requires the operation to terminalize/fence and forbids PRE worker continuation; it does not require an orphaned selected-run row itself to gain a synthetic deadline terminal. Those are existing current-source tests, not newly executed PostgreSQL/native proof in this commit. The removed test module's synthetic `recover_expired` method did not exist on the current service, so retaining it would create false API coverage. A selected run left `running` after a crashed foreground is a retained observation, not an adopted recovery path or a claim of selected-run terminalization.

Focused final pure execution: 111 passed and two unrelated real-PostgreSQL POST cases deselected in 14.01 seconds, exit 0. Initial run had 52 passed, two PostgreSQL setup errors because no isolated database URL was provided, and the independent project fingerprint failed before its count/hash update; it was not credited as a pass. The two deselected cases use `material_fixture` and `live_executor`, not the edited fake source-grant constructors. The current catalogue has 257 project modules with independently recomputed family and lane ownership hashes. This is affected pure test custody, not a full backend CI pass.

### Restore remote POST delivery in the app-only topology

CI's production POST/reconciliation calls return no claim because the app-only
profile exclusion still removes those event types. Settings now permit only
hosted_profile=app; native execution moved to the authenticated runner, so this
old local-runtime exclusion blocks the required current path. Allowed scope:
backend/app/adapters/outbox/__init__.py, existing production delivery tests if
needed, and this record. Remove only profile-based exclusion/get_settings import;
retain exact handler registration, exclusive finalization worker filtering,
finite leases, authorization and configured remote adapter failures. No deployment,
provider default, local KVM fallback or authority changes. Medium workflow risk;
QA reviews the composition against remote wiring. Verification uses existing
production request/completion tests for both policy branches and real public
reconciliation/custody tests, plus the native journey. Human review focus: app
workers can dispatch remote POST while finalization workers remain exclusive.

Use the actual general-worker composition (finalization_worker=False) in
the existing request→completion regression for both policy branches. The
existing finalization-worker isolation test retains pending/expired cases
under the sole supported app profile; remove its obsolete single-host variant.
These tests directly exercise the two worker groups affected by this fix.

### Repair retained Terminal Systems Smol qualification callers

Bounded intent over83ee3bacb: terminal_systems_smol_composition.py and recovery
reuse the production RemoteTls adapters through existing remote_adapter_endpoint,
without restoring removed Unix adapters. Extend that existing test endpoint only
with explicit finite session/material/callback socket parameters; ordinary10s
callers keep their current envelope. The native Rust service must see the edge's
runner callback socket while the adapter routes callbacks to actual application
model/trial proxies. Preserve exact ART material roots and cleanup inventories.

Split author and runtime POST approval into independent one-image pytest cases,
with separate fixture roots, two model effects and one retained trial receipt per
case. Preserve the original combined four effects/two receipts, all17 trial-slot
outcomes, replay and full binding/economic checks in aggregate qualification
admission; recovery explicitly selects the runtime case. Update existing native
wrapper/evidence guards to require both cases, refusing missing/duplicate/skipped
branches instead of lowering the total. Allowed files: composition, recovery,
existing test_remote_node endpoint helper, native qualifier and its existing guard
module, and this record. No product code or schema changes planned.

Use scoped imports/collection and actual loopback production-TLS helper guards,
plus native evidence-admission negatives and source checks. No live native,
service, runner configuration or deployment mutation while the connected journey
uses the remote node; local guards/collection do not qualify native composition.

Implemented the bounded harness cutover. Both POST cases are explicit pytest
parameters, each approving exactly one registered image/configuration. Recovery
calls the same runtime-case helper directly. Each case gets an independent
composition root and short child-HOME leaf, refusing reuse; the configured child
HOME parent must therefore fit <=16 bytes so each existing native leaf bound
stays <=18. Each result requires two completed model effects with UUIDv7 request/
response bindings, one retained trial evidence binding/content/put/verification
join and its exact receipt digest. Native qualifier admission requires both exact
JUnit case IDs and both one-image summaries; flattened totals must equal those
summaries and remain the original four model effects/two receipts. Per-case
raw summary hashes are retained alongside the aggregate, with separate authority
manifest digests rather than pretending authority is shared.

Both adapters use the production RemoteTls implementations and canonical
selected_pre_submit_source_contracts(). The existing loopback test edge now
accepts explicit finite720s sessions and independently pinned material/callback
roots, keeping default10s behavior unchanged. Application post-scratch stays
separate from runner-materials to prevent extract-ID collisions. Rust callbacks
target the runner edge socket; the adapter routes the owning connection back to
actual application model/trial proxies in native qualification. The helper
cleans its socket root even if explicit-root validation fails. No Unix adapter
or compatibility layer was restored.

Executed scoped evidence (modified content over83ee3bacb): exact hosted CI
collection command collected author, runtime and recovery (three nodes) in4.09s
at /tmp/submission-ts-harness-collection-v1.log, exit0; its pre-existing unknown
postgres_schema_contract mark warning is retained. Native evidence-admission
and inventory guards passed14 in0.543s at
/tmp/submission-ts-qualification-guards-v1.log. Actual loopback production-TLS
endpoint guards plus the existing model-selector control passed3 in5.31s at
/tmp/submission-ts-tls-helper-final.log. Those native peer replies and model/
trial-labelled callback frames are controlled plumbing facts, not real Smol,
SQL model/trial custody, paid inference or deployed two-host qualification.

The first TLS plumbing guard failed due to its fake native peer using the wrong
wire key material_grant instead of grant; a wrong-cwd edit did not apply before
the second run, which honestly repeated that fixture failure. Final bytes fixed
that field; assertions were retained. No product failure was inferred. A pure
in-memory mutant retained count2 and fatal-result checks but omitted exact JUnit
image-case identities: the named duplicate-author/missing-runtime test failed
ValueError-not-raised after its valid control, with no source mutation
(/tmp/submission-ts-case-omission-probe.json and .log).

AST comparison confirms _provider_output, _manifest,
_runtime_configuration_digest, _assert_idle_trial_roots and
_retained_trial_summary unchanged, plus original17-slot cardinality/all11
explicit slot assertions unchanged (/tmp/submission-ts-preservation.json).
Ruff/whitespace pass. Record/link checks follow this append. Actual native
composition/recovery remains unexecuted: no live runner, service, configuration,
deployment or paid-provider mutation occurred while the connected journey ran.

QA-REMOTE-POST-001 identified the old app-hides-POST regression. Replaced
that obsolete expectation with exact general-worker pagination, POST claim
and expired uninvoked reconciliation recovery under the sole app profile.
The test preserves generation/owner/state checks and proves discovery/recovery
does not invoke synthetic payloads; real request execution stays covered by
the separate production request→completion tests.

The clean public journey at `a51f1acd0` passed the native PRE missing-summary
rejection, accepted and replayed the correct source, and finalized T5 to one
Submission. A read-only isolated database observation showed the original
finalization event acknowledged on its first attempt, while
`PostSubmissionEvaluationRequested` remained pending, unclaimed and at zero
attempts; the POST run was queued. A second observation still found the same
pending event. This matches the profile-based exclusion removed above. The
canonical isolation runner was signalled only after those observations and
reported both database and MinIO cleanup complete. That stopped run did not
observe automatic acceptance, the incorrect POST branch or review-pending
branch. The repaired production worker composition still needs its focused
PostgreSQL replay and then a fresh full public journey.

The repaired composition's10 scoped real-PostgreSQL cases passed at0449ed4c9
in317.77s (/tmp/submission-remote-post-delivery.log and .json), schema0090 and
owned database cleanup confirmed. Cases cover actual general-worker POST
request→completion under both review-policy branches, committed reconciliation
without repeated effects, four substituted child/operator-cause refusals,
app-worker pagination/claim/expired-uninvoked recovery, and pending/expired POST
isolation from the finalizer group. No MinIO was provisioned by this run.
QA-REMOTE-POST-001 is resolved; scoped QA PASS at the exact clean candidate.
Independent composition control restores the old exclusion and rejects it,
while retaining finalizer-only registration/options and missing-TLS refusal.
These are local SQL/controlled execution proofs, not native/AWS qualification.

Read-only live API credential inspection confirms mounted dedicated AWS access
keys through the canonical direct-user provider, not inline MinIO fields.
GetBucketVersioning and ListObjectVersions under the actual
workstream/artifacts/submission-source/v1 prefix return AccessDenied. The
provisioning identity can read the bucket policy and versioning: versioning is
already Enabled, while the current policy explicitly confines object access
to the old sha256 namespace and denies all deletion. Its IAM GetUser/ListUserPolicies
calls are denied; those are administration limits, not a runtime need for IAM
administration. Existing API credentials stay on the app side; no keys belong
in the microVM. Prepared source permissions must preserve retained SHA objects
and qualify the separate cleanup authority. No bucket/object/config mutation
was performed by these probes. Actual AWS source qualification remains open.

### Preserve SHA put guards while enabling source multipart uploads

Read-only live policy comparison shows the existing SHA namespace denies every
PutObject operation without If-None-Match. Restrict the multipart API exemption
to the new submission-source bundle keys rather than broadening legacy SHA
behavior. Allowed files: backend/scripts/aws_direct_user_config.py and its
existing test_aws_direct_user_config.py, this record and regenerated local
permission handoff JSON. No live AWS mutation or credential handling change.
Medium storage-policy risk; ARCH/SEC reviewed prepared policy against the live
five-statement snapshot and found no blocker, subject to exact generator parity
and actual later AWS positive/negative qualification. Retain metadata-listing
scope limitation in the handoff; no object read/delete authority outside exact
sources is added. Verify existing focused policy tests and generated JSON equality.
AWS conditional multipart reference:
https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html

All15 existing policy guards passed2.02s, including separate runtime/cleanup
rights, retained SHA protection, conditional completion/part rules and refusal
of foreign/unbounded identities (/tmp/submission-aws-policy-scope.log).
All three prepared JSON files compare exactly to canonical generator output
for the actual bucket, namespace and same-account IAM users. ARCH/SEC review
found no blocker to administrator application; metadata-list scope is explicit
in administrator-handoff.txt. Live policy application, credentials provisioning
and actual AWS source qualification remain unperformed. Pinned Ruff/diff pass.

The first clean run with the repaired POST dispatcher (`f14a19179`) passed
public setup, real native PRE rejection for the missing-summary ZIP, correct
ZIP T4/T5 and automatic POST acceptance, exact accepted Contribution/export,
the source/effect read-only audit, incorrect-count ZIP POST failure with no
acceptance, and Operator custody. It stopped while creating the separate
review-required project: that fixture skipped `set-review-policy` entirely,
leaving the public activation context without a selected review policy. The
backend and built CLI both require such a selection. The journey now calls
the ordinary public `set-review-policy` with only required window and lease
fields in this branch, letting the backend apply its documented default
`human_review_required=true`; the automatic branch continues to pass explicit
`false`. It checks the selected response. A focused test pins omission versus
explicit false. This is a fixture correction, not a human acceptance route.
The stopped run's isolated PostgreSQL database and MinIO bucket were cleaned;
`review_pending` remains unobserved in that run.


### Existing AWS runtime permissions rechecked after administrator update

On 2026-11-24, the running API container's canonical isolated AWS credential
provider returned HTTP 200 for GetBucketVersioning (Enabled) and
ListObjectVersions under a fresh submission-source/v1 operation prefix. The
existing API key remains in its private mount; no credential was exposed or
provided to the runner. Receipt: `/tmp/submission-aws-permission-recheck-20261124.json`.

A separate read of the actual bucket policy still returned the old five
statements: source keys remain outside DenyOutsideArtifactNamespace's allowed
SHA namespace and DenyArtifactDeletion still covers all objects. The reviewed
source bucket guard update is therefore not yet applied. Receipt:
`source-policy-applied-read-aed80ad765474a2eb0d7b7c2999a048f.json` in the private
AWS setup directory. The separate cleanup credential file location is pending.
These two successful reads close the previous read-permission failures only;
actual multipart, exact-version, restricted cleanup and lost-acknowledgement
AWS qualification remain unproved. No service, policy or deployment was changed
by these checks.

### Prepare attach-only operator SSH fault bridge

Bounded intent over5f3599d73: extend existing public_node_faults/private control
owner with run-ID-bound command/query/snapshot input and bounded trace reads;
add one thin public_runner_faults operator client using the approved pinned SSH
argv pattern, never a production endpoint. Allowed files: public_node_faults.py,
public_fault_files.py, new public_runner_faults.py, existing public fixture guard
module, the experiment README and this record. No CLI journey overlap.

Commands retain one stable ID/action and query that same ID after lost ACK;
unknown transport never means safe to resend under a new ID. Snapshots bind exact
run/custody and bounded trace prefix. Reject wrong run/custody, mutable or aliased
private files, arbitrary actions, oversized/truncated output and malformed IDs.
SSH must use -F /dev/null, explicit identity, no agent, BatchMode and strict pinned
known-host checking. Keys stay operator-side and are never read/printed or passed
to API/workers. Application TLS source execution remains unchanged.

Supervisor preparation must be finite and handle HUP/TERM through existing
restore/foreign-resource cleanup; independent operator-owned finite lifetime is
a prerequisite for future SSH disconnect qualification. The bridge attaches to
an already prepared verified run and does not start or deploy a remote service.
No remote connection, service/configuration mutation, native fault or paid call
will run while the connected journey owns the runner. The next live vector and
caller wiring remain separately qualified; no shared runner filesystem, API-side
KVM, cross-host monotonic comparison or aggregate-expiry inference is permitted.

Read-only tracing identified that hardcoded fixture repository selection would
block the actual pinned runner cache. Within the same bridge files, require an
explicit locked image digest at supervisor startup and in every operator
request/response, resolve exactly one cache entry and bind it into the private
run metadata. Preserve original node-binding bytes/custody; no cache population,
image replacement, app caller or production configuration change is introduced.

Implemented the attach-only bridge in the allowed six files. Every request
requires exact run ID, canonical node-binding SHA and explicit cached image
digest before command dispatch. Cached image selection is exact/unique and no
longer depends on the retired fixture repository name. The client reuses the
approved pinned SSH argument pattern and additionally disables global host-key
fallback and automatic pin updates. It never reads key bytes, starts a remote
supervisor or forwards credentials to API/workers. Requests/results and SSH
stdout/stderr have finite byte/time limits, and a dead local SSH PID during
cleanup cannot lose the original command ID. Unknown ACKs only query that same
ID; no automatic resend/new-ID path exists.

Snapshots bind an append-only trace prefix and include a same-run/image/custody
cleanup receipt when present. Invalid IDs/pins, mutable private modes, symlinked
or incomplete traces, oversized output, rewound traces and incomplete cleanup
are refused. Cleanup observation requires empty typed resource lists and exact
foreign cleanup flags; the caller still compares the original config hash with
its independent preparation custody. The supervisor accepts a finite <=1800s
run budget, checks it before queued commands, uses bounded command subprocesses,
and preserves existing config/foreign cleanup under controlled HUP/TERM. This
is a bounded run loop plus restoration, not a host reboot/SIGKILL guarantee.
Actual launch must use an independently finite operator-owned supervisor/unit.

Root review identified that O_NONBLOCK does not bound flock. Repaired new trace
reads to LOCK_SH|LOCK_NB; a held writer now means unavailable observation with
no polling. The named guard runs real local reader children under a five-second
failure bound: available control, held writer returns unavailable, available
again after release. Native/service operations remain mocked in the lifecycle
guard. Final bridge class passed9 in2.347s at
/tmp/submission-runner-bridge-guards-lock.log. Earlier lifecycle fixture errors
were a missing dummy socket_path; an intermediate request fixture accidentally
included response-only cleanup metadata and was correctly rejected. Neither
was a product/native failure or reason to relax the protocol.

A bounded in-memory omission of only the before-dispatch custody/image check
makes the named stable-command/refusal guard fail after its valid control
(/tmp/submission-runner-bridge-custody-probe.json and
/tmp/submission-runner-bridge-custody-probe-current.log). No source file, SSH or
native state was mutated by the probe. AST checks show validate_node,
write_node_config, ForeignControl, runtime, owned_resources and
runtime_control_root unchanged (/tmp/submission-runner-bridge-owner-preservation.json).
Ruff/whitespace pass; final record/link checks follow this append.

No live SSH connection, native fault, service/configuration/deployment change or
paid request occurred. Physical node custody checks and actual foreign VM
preservation are not proved by mocked lifecycle tests. Existing filesystem-based
trial callers are not yet wired to this bridge, no two-host fault drill has run,
and independent supervisor disconnect/restoration, API/runner separation,
aggregate native expiry and source/execution cancellation remain required.


### AWS source qualification scratch prerequisite

The first live attempt at439de11ff verified both exact IAM users but stopped
before source intent creation or provider writes: enabled storage Settings
requires artifact_scratch_root, which the drill omitted. Journal
live-620b55b065974b6f9e99db3dc8948560.jsonl contains only started and ValidationError.
The bounded repair supplies an owned temporary scratch directory to the two
existing production adapter constructors and removes it on exit. Only the
qualification script and this evidence record change; no product validation,
credential policy, source ownership, retention or cleanup rule changes.
Verification uses the real AWS drill after the prerequisite repair. The bucket
policy now exactly matches the reviewed guard; the cleanup credential is
installed on the API host with0400 ownership10001 and its exact IAM ARN verified.


The workstation correctly rejects ambient ~/.aws files; the failed second
attempt's two exact keys were independently confirmed to have no versions or
multipart uploads. A clean isolated container using the production dependencies,
read-only current source and two private selected keys reached real multipart
upload, conditional completion and exact source readback, then AssertionError
before the permission/cleanup checkpoint. Its journal is
live-d0dad07781b744538b4a46b1fce9802c.jsonl; synthetic targets remain explicitly
owned for reconciliation. The drill now records traceback locations (no locals
or SDK messages) and its own static AssertionError text to diagnose the exact
failure. This is diagnostic-only; no acceptance assertion is removed or widened.


### Conclusive retained-artifact permission control

The diagnostic replay isolated the failure to the cleanup GET of an invented
all-zero SHA key. AWS returned NoSuchKey/404, not a conclusive permission denial.
ARCH/SEC reviewed a narrow correction: require an operator-selected existing
canonical SHA key, prove its existence with runtime HEAD, then require cleanup
HEAD to fail with403/AccessDenied. HEAD exercises GetObject permission without
reading retained user bytes. Run this control before synthetic source creation.
Keep all source multipart/overwrite/deletion/abort and lost-ack checks unchanged;
never accept404 as permission-denial proof and never create an undeletable SHA
fixture. Allowed changes are the operator drill, its operations instructions and
this record. Real AWS replay provides verification; no product policy changes.

### Keep historical preparation reads separate from current source progress

Intent: the retained preparation GET must show pre-cutover v1 history only. The current source-v2 PRE run has a separate operation-progress API. Reading it through the historical ART projection currently reports `passed/storing` after real T5 because that projection joins only pre-cutover durable intents and admissions; reporting this false intermediate state is a read defect. The CHECKERS run reader has only ART preparation-read consumers, so restrict its contributor and project selectors to v1 rows with null `source_operation_id`. Do not alter current source execution, operation progress, retained decoding, or authorization. The existing authorized task/project route still gates the historical reader.

Allowed files: `backend/app/modules/checkers/selected_pre_submit_reads.py`, affected contributor/project preparation tests and scale fixture, `backend/tests/migrations/test_source_pre_cutover.py` for a genuine captured consumed-history projection after upgrade, contributor/project preparation GET route and dependency docstrings, their generated MCP description snapshots after canonical refresh, and this record. Prohibited: schema/trigger relaxation, fabricated accepted source state, separate current-progress implementation on the old route, new public route, removed tests or smaller performance dataset, bypassed foreign keys, or changed AUTH selectors. Acceptance: current v2 is omitted on both historical routes while its operation remains visible through the already tested current progress API; the unchanged checksum-bound captured v1 consumed snapshot projects its exact submitted admission and findings; corrupt completed retained facts still fail closed; 10,000 tasks, 20,000 submissions and 30 preparation-history rows keep the read budget test. Build scale-only rows from canonical retained v1 values with row identities and digests matched by the retained decoder, retaining FK enforcement. Risk: filtering by schema label alone could expose a forged v1 body on a source row, and synthetic benchmark rows could bypass decoder/ownership semantics. Architecture/security and CI integrity review should inspect both predicates, archived custody, page sizes and actor filtering. Human review focus is the archived v1 proof and the scale fixture's exact row integrity. Execute pure checks first; defer PostgreSQL setup until the shared native journey slot is free.

The implementation filters the historical reader by `source_operation_id IS NULL`; its existing closed decoder then requires the indexed request/terminal values to match. Actual archived v1 `consumed` rows are read after a real upgrade in the existing migration test, including contributor and project projections and a foreign-actor empty result. The performance fixture remains synthetic bulk restore: it borrows the one real run's execute/finalize audit foreign-key references solely to satisfy the closed table shape, while deriving each v1 request/terminal body and digest from the retained canonical decoder. It does not prove those 30 or 10,000 benchmark runs were independently authorized or executed. The exact old public cursor filter/limit denial assertions moved to the project scale test so dropping the current-source rows does not discard them. Pure retained-decoder/projection tests passed 17/17; all 40 affected test nodes collected; Ruff and whitespace checks passed. PostgreSQL route, archive and scale execution is pending the shared slot, so no implementation pass is yet claimed here.

The first isolated PostgreSQL pass at schema 0090 ran six selected cases: four passed, including the current-source public selector controls and contributor scale. The archived consumed-history case stopped before the added read assertions because its older 0083-to-current function-set equality now spans the merged main and later cleanup migrations. The test now compares exact function definitions only across 0083-to-0084, where the admission guard is the intended sole change, then separately requires all captured rows to survive through current schema before reading archived history. Project scale reached the historical preparation page within its unchanged one-second budget (0.707 and 0.499 seconds), but an unrelated submission continuation took 1.008 seconds and failed the same inherited budget. No budget was widened or performance result credited. The first runner's database cleanup completed; the two affected cases await a focused replay.

Focused replay at schema 0090 passed the archived consumed-v1 read after the corrected exact migration comparison. The project scale case remained red on the unchanged one-second gate: submissions filtered took 1.905 seconds, assignments 1.316 seconds, and preparation pages 1.889/1.129 seconds under the shared host's load. Those broad overruns do not isolate a preparation-query regression, and this commit does not claim the scale gate passed. The two-case run had one pass and one failure in 462.90 seconds, with full isolated database cleanup. A later controlled performance measurement remains necessary before crediting the one-second project scale requirement.


### Live AWS source qualification passed

At clean script candidate074cade5e, the pilot bucket and both independently
STS-verified runtime/cleanup IAM users passed the complete operator source drill.
Private journal: aws-source-qualification-20261124/live-612605b1732644d189ad0c5257328c5c.jsonl.
Actual checks: runtime HEAD confirms an existing retained artifact and cleanup
HEAD is403; two-part conditional source completion and pinned-version byte/hash
readback; conflicting overwrite refusal; runtime DeleteObjectVersion/Abort
refusal; cleanup Put refusal; cleanup abort and exact NoSuchUpload; lost delete
ACK reconciliation while an independent equal-byte retained source survives;
lost begin ACK exact-handle discovery/abort; lost complete ACK exact-version
recovery and substituted hash refusal. Four new owned operation keys were used:
three completed sources removed with confirmed absence, one unsealed multipart
handle discovered and aborted with confirmed absence. Final event completed/passed.
No user artifact body was read by the retained-object permission control.

The two earlier synthetic runs each had two source keys. Exact recorded versions
and upload handles were reconciled with the cleanup principal, and independent
exact-key listings confirmed no versions, delete markers or multipart uploads.
Their adjacent .cleanup.json receipts are retained. No product SQL rows, current
API/worker configuration or existing retained keys were mutated. Temporary local
credential files and isolated drill container were removed on process exit.
This qualifies the actual native AWS source adapter/policies for this pilot;
it does not prove deployed worker wiring, public hosted journey or C01–C07 limits.
The hard-coded native-AWS admission exclusion can now be replaced with the
qualified profile, followed by its focused T1 test and actual hosted activation.

### Wire the first remote PRE launch-failure trial

Intent: connect only the existing first project_fail_once public PRE vector to
RunnerFaults. Allowed files are the existing runtime trial, native trace assertion
owner, fixture guard module, this record and experiment documentation. The caller
must supply an already approved/claimed current task, exact assignment/actor and
actual locked-image-compatible ZIP. Reuse real public raw-ZIP intake, SQL custody
reads and durable OUTBOX T5; do not create another setup or product fault endpoint.

Acceptance: one failed operation with sealed exact charge/no accepted handoff,
one native create/start/delete and no exec, same-key replay with unchanged terminal
custody and no new remote trace events, then a fresh key accepted202 and real T5.
Use acknowledged remote snapshots/cursors only; never compare local and runner
monotonic values. Unknown SSH command/transport stops the trial without resend or
fresh submission. Preserve actual lease and exact foreign-resource assertions.

Risk: operator qualification code mutates an owned runner only when explicitly
launched later. Prepare pinned runner-only source staging/start/restore commands
for owner review. No SSH, service/configuration mutation, native run or paid call
is authorized during the current V14 runner window. Verification here is focused
caller/trace guard testing, static gates and root review, not live qualification.
No roadmap capability is completed by this wiring. Other runtime vectors,
remote disconnect restoration and original aggregate expiry remain unqualified.

Implemented the isolated first-vector caller in public_runtime_trials. It accepts
only a fresh existing task plus its exact assignment/token/compatible ZIP and the
reviewed RunnerFaults profile; it does not repeat project setup or select a new
image. The general POST consumer must be paused by its existing launcher owner,
with the exclusive production finalizer still running. Existing local trial loops
and CLI bootstrap are unchanged; the latter exposes worker startup only and is
not silently treated as a fault launcher.

The caller records acknowledged remote cursor snapshots around failure, replay
and recovery, binds the persisted failed/fresh PRE to the exact profile image,
requires the known infrastructure failure, sealed exact positive charge and one
failed operation, then unchanged terminal replay with no trace growth. Only after
conclusive failure and acknowledged clear does it submit a fresh key and delegate
to existing real OUTBOX T5 observation. It rechecks failed custody after replay
and requires exactly the failed and accepted operation IDs afterward. Unknown
command ACKs propagate with the retained ID and no fresh source submission.

Extracted the existing native launch/lease/deletion assertions into a pure trace
assertion used unchanged by both filesystem and snapshot callers. AST comparison
confirmed all original assertion statements unchanged after the input filter.
The new guard valid control delegates the existing T5 observer and preserves exact
503/503/202 selectors; independent missing-delete, replay-allocation and wrong-image
controls fail their intended exact messages. An uncertain command retains its ID
and prevents submission. These are mocked HTTP/SQL/SSH caller guards, not live
fault/provider evidence. Final2guards passed33.404s at
/tmp/submission-remote-pre-caller-v2.log (initial2passed78.049s before final
replay-custody recheck and precise negative-message assertions).

REMOTE_PRE_LAUNCH.md contains the runner-only reviewed source bundle/staging,
independent manifest fields, exact current image/unit/config candidates, finite
systemd supervisor and TERM restoration commands. The saved setup config has old
cache pins and is explicitly insufficient current custody. No owner manifest or
live source staging root was invented, and no permissions/cache are changed to
fit a test. Missing independent custody blocks the live run. Roadmap scope is
unchanged: this prepares qualification, not a new delivered product capability.
No SSH connection, runner/app service mutation, native VM, paid request or live
fault occurred. Actual remote launch failure/restoration remain unqualified.

Root required explicit worker lifecycle ownership before live scheduling. The
entry now requires the existing isolated fixture stop_worker/start_worker
callbacks and restores that general worker in finally, including partial pause
failure and unknown fault-command outcome. It never stops arbitrary deployed
services. The final3caller guards passed26.830s at
/tmp/submission-remote-pre-caller-final.log with these exact executable bytes;
valid/negative vector controls and the owned-worker restoration paths ran.
Structure validation exited0 (/tmp/submission-remote-pre-structure.log); after the
small callback/test addition, a bounded AST check confirmed all added functions
remain below120lines and the guard module remains below1200 without ledger edits.
Ruff, links and whitespace pass. Commitrail is checked against the bridge base.

### Complete connected native journey and current read contracts

V14 passed all six stages and 573 CLI invocations at clean85ce76e17, schema 0090.
Public PRE rejection leaves no Submission; correct input reaches one passing
registered POST, FinalAcceptance, Submission and Contribution with exact original
ZIP hash in Contribution/CSV export, no Review and no awards for this policy.
Incorrect input passes PRE then reaches failed POST/needs_revision without
acceptance effects. Default-required review reaches review_pending with zero
Review/Contribution/FinalAcceptance. Read-only source/effect audits and Operator
custody checks passed. Metadata confirms owned database and MinIO cleanup;
journey-owned provider container/secret were removed. Evidence:
`/tmp/submission-public-journey-live-v14.log` and matching.json; private timing
snapshot `/tmp/submission-public-journey-v14-pre-intervals.json`.

Topology was disposable local API/PostgreSQL/MinIO/Redis and the real dedicated
AWS Smol runner, not the deployed API release. DB-recorded PRE intervals were
86.422219, 85.504909, 83.267697, 80.466899 seconds under the test 120-second / 2 CPU /
2 GiB / 8 GiB / 64-process profile. These are not HTTP or execution-only timings.
The approximately 60-second target is not met; C01 hard-limit approval was
requested with these measurements and remains pending. Do not fabricate defaults.

Historical preparation route descriptions were refreshed in exactly three MCP
snapshots using current exported OpenAPI and the canonical fragment/hash helpers;
only descriptions, hashes and source provenance changed. No schema or permission
changed. Five focused configured checks passed 1.35s, including both current
OpenAPI comparisons (`/tmp/submission-historical-mcp-contracts-final.log`).
The initial selector command selected two nodes from the wrong module and ran
no tests; corrected selection uses the existing task-execution contract module.
Roadmap, initiative overview/index and local sheet exports are reconciled to
these scoped results while keeping hosted activation and final qualification open.

### Admit the qualified AWS source profile into T1 and source PRE

Intent: the actual pilot AWS source drill passed with conditional multipart completion, exact version reads, retained-version survival, scoped deletion and abort, denied runtime deletion, and lost begin/complete/delete acknowledgement recovery. The provider identity `aws-s3-v1` can now enter the same source-first T1 and PRE custody as qualified local/MinIO; this is an explicit profile addition, not a dynamic proof registry or an AWS runtime default. The live drill used the dedicated runtime and cleanup IAM users and a private fsynced journal; it did not execute a public T1/PRE transaction or native guest. The administrator-applied policies and pilot bucket are deployment evidence, not a new database authority source.

Allowed files: `backend/app/modules/artifacts/intake/foreground_admission.py`, `backend/app/modules/artifacts/selected_pre_submit_admission.py`, a new narrow `backend/alembic/versions/0091_qualified_aws_source.py`, Alembic current-head and expected-schema fingerprint fixtures, `backend/tests/artifacts/test_submission_intake_admission.py`, `backend/tests/artifacts/test_submission_pre_source.py`, exact migration graph tests if needed, and this record. The migration must replace only the existing selected PRE source-profile/scheme predicate, with predecessor-shape checks and no historical row rewrite. Preserve all locked source, packet, policy, fence, deadline, and task checks.

Acceptance: a real PostgreSQL T1 under a pinned AWS namespace commits one receiving operation, reserved source charge, exact TASK pointer and AUTH allow before any provider/body I/O; replay returns the same operation. A database-only sealed AWS source (explicitly not a provider qualification) builds `storage_scheme=s3` and passes the current SQL source guard, while a rehashed foreign profile/scheme is refused. An unknown profile cannot form the canonical namespace identity, and the PRE builder continues to refuse an unknown source profile. Verify the exact 0090-to-0091 SQL function delta, current schema fingerprint, focused positive/negative cases and retained existing local/MinIO controls. No broad SDK, native VM, public flow, config default, or cleanup authority change. Risk: admitting T1 without both PRE builder and SQL guard would leave a committed unusable operation; broadening the SQL predicate or accepting a forged scheme would weaken source custody. Human review focus is the three coordinated gates, immutable function delta, AWS namespace binding, and the separate limits of the live adapter versus database-only tests. PostgreSQL execution waits until the shared V14 journey releases its isolated test slot.

After V14 released the shared PostgreSQL slot, the first focused five-case run at schema 0091 passed four cases: AWS T1 exact receiving operation, reserved charge, TASK pointer, AUTH allow and same-key replay; existing local admission/source control; and an actual 0090-to-0091 full-function comparison that found only the two expected profile/scheme edits. The fifth case stopped at a test-only strict UUID decoder call before its SQL assertion. The fixture was corrected to decode the persisted JSON through the model's JSON validator; the single affected PostgreSQL replay then passed, including the AWS `s3` source guard positive and rehashed foreign profile/scheme refusals. Receipts: `/tmp/submission-qualified-aws-admission-v2.log/.json` (4 passed, 1 test-fixture failure, 241.84 seconds) and `/tmp/submission-qualified-aws-pre-source-v3.log/.json` (1 passed, 41.18 seconds). Both isolated databases report cleanup complete and Alembic 0091. The measured current public-schema fingerprint is `7ad79f8771b732cbabdc956cdffae50905b757990b1e5336f44990054967f31b`; Ruff, whitespace and Commitrail checks pass. These tests exercise database custody with a synthetic provider generation; the separate actual AWS adapter drill is the provider evidence. No public AWS submission or native guest journey is claimed by this change.


Independent QA scoped review passed for bc4c37acd versus919cb0b92. Runtime AST
comparison preserved every existing source/packet/policy/lease/deadline/namespace
and AUTH predicate after removing only the additive AWS profile entries. The
unknown-profile fail-open control was detected; migration control changed exactly
two predicates and rejected absent/duplicated predecessor fragments. Author18750
and integratedbc4 executable paths match the shared five successful PostgreSQL
cases across two runs; these are not claimed as full-head executions. Actual AWS
adapter qualification was independently checked through the safe journal envelope
and exact074 script hash. Evidence `/tmp/submission-aws-gates-qa-probe.json`.
No deployed AWS public journey or full-CI pass is claimed.


### Contributor scale control and interrupted-fixture process cleanup

The contributor scale node passed at clean bc4c37acd / schema0091 in30.76s,
with complete isolated database cleanup. Slowest-of-three request measurements:
assignments0.209s/continued0.305s, submissions0.202s/continued0.232s,
summary0.223s, preparations0.165s, project tasks0.243s; all below the existing1s
budget. The agent initially mislabeled this as the project scale test; root
checked the printed endpoint set against both test owners and rejected that
scope claim. Project scale remains pending its exact named node. Evidence
`/tmp/submission-project-scale-quiet.log` and matching.json;
host samples `/tmp/submission-project-scale-quiet-host.txt`. No threshold widened.

Before this measurement, root identified still-running private Celery groups
from the terminated V11/V13 fixtures by exact process group, executable/cwd,
stdio paths and database names matching their terminal metadata. Root sent TERM
only to those two owned groups and verified all members exited. This occurred
during the scale runner's startup and was recorded in the host context; no test
restart occurred. The earlier database/bucket cleanup receipts remain true, but
they did not establish process teardown. The existing journey runtime teardown
is being repaired and tested before the next fault drill. PRE intervals from V14
remain actual observed stages under that host context, not quiet-host benchmarks.

Reviewed b23b9be28 fault source and the independently compared root-private
custody manifest were staged on the dedicated runner with exact bundle/file hash
checks. Source is clean at the pinned commit. This is staging only; no fault
supervisor or service restart occurred. Archive nlink2 was resolved as the
existing immutable native-cache hardlink with exact bytes and0400 owner10001;
post-V14 leases/workspaces were empty. Local proposal/transfer evidence remains
in `/tmp/submission-runner-b23b9be28-stage.log` and associated comparison files.


The corrected exact project node `tests/project_reads/test_work_scale.py::test_project_pages_and_summary_meet_budget_at_scale` passed at bc4c37acd, schema0091, in47.62s. The actual `project read timings` output includes filtered submissions, import batches and10,000 preparation history rows; slowest endpoint0.414s against the unchanged1s budget. `/tmp/submission-project-work-scale-v1.log` and `.json` show one pass and full isolated database cleanup. This closes the focused project performance replay; the earlier contributor control is not its evidence.

### Focused remote PRE launch-failure fixture

Intent: run only the existing `public_pre_launch_failure` vector after the
connected CLI journey's public guide, task creation and claim. This bounded
fixture may change `cli/tests/journey/bootstrap.py`, `runtime.py`, add its
single adapter module and focused cleanup tests, plus this record. It must
reuse the actual incident-summary ZIP, isolated database and bucket, exact
runner profile and owned general-worker callbacks. The dedicated finalizer
remains live. No product route, provider policy, runner configuration or
human-review behavior changes are allowed. The lead owns reviewed runner
staging, supervisor start and restoration; this fixture cannot perform them.

Acceptance is a real public 503 with one failed source/PRE and no accepted
handoff, one remote create/start/delete without execution, unchanged same-key
failure replay without new allocation, then fresh-key 202 and durable T5.
The runner cleanup receipt must bind the original config and show no owned
resources after the supervisor stops. Unknown remote command outcomes retain
their original ID and stop the sequence. Verification uses a private isolated
launcher and focused process-group regression; the complete V14 journey is not
repeated. Risk is high because the fault supervisor temporarily changes the
owned remote runner and interrupted local workers must be reaped.

The fixture now selects this one branch only after existing public setup. A
private runner profile is validated before local API startup, with exact image
pin and no credentials in output. It pauses only the fixture-owned general
worker and restores it in `finally`; the finalizer continues T5. A new exact
process-group shutdown helper observes every live group member rather than
waiting solely for the Celery leader. Cancellation sends TERM to all owned
separate sessions and kills survivors within the isolation runner's two-second
grace. Real leader plus TERM-resistant child controls passed both normal and
cancellation paths (2 cases); an in-memory predecessor leader-only stop failed
the regression. Focused bucket/cleanup checks: 6 passed; Ruff and diff check
passed. These are fixture checks, not a live runner-fault result.

Root review found three teardown edges before integration. Exact group signals
now accept a group exiting between observation and `killpg`; shutdown attempts
every owned group and retains its first failure through log capture; a stopped
general worker is removed from the active ownership list before restart so a
stale process-group ID is never signalled later. Added focused race and
attempt-all controls. Eight local fixture checks pass, including the two real
process-group cases; the remote supervisor is still unstarted.

### Validate hosted config custody under its root-owned directory

Intent: actual read-only staged validate_node failed before any supervisor start
because the shared private-control path check required the config parent to be
owned by runtime UID10001/mode0700. The approved hosted configuration is instead
UID/GID10001/mode0400 under root-owned nonwritable /etc/workstream. Repair only
that configuration-file validation; never chmod/move the deployed config to fit
the operator fixture. Allowed files are public_node_faults.py, the existing
public fixture guard module, its affected experiment docs and this record.

Acceptance: root-owned nonwritable hosted config ancestry is allowed while its
file stays exact UID/GID10001,0400,regular,single-link,canonical and inode-bound.
Writable or foreign-owned ancestry, symlink aliases, wrong file mode/owner and
extra links refuse. Keep local config and every private control/runtime directory
on their existing strict private checks. Add a discriminating root-parent control
and denials, retain the same-fd read and exact-inode write checks, then run focused
guards/static gates. Local tests may model root ownership because the host user
has no sudo; actual runner read-only validation follows reviewed incremental
source staging. No runner file writes, restart or supervisor start in this task.

Read-only parent audit confirmed /etc/workstream, /etc and / are UID/GID0 mode0755;
config inode303569 remains UID/GID10001 mode0400 with one link. Evidence is
/tmp/submission-runner-config-parents.json. No runner permissions, files or
services changed. The config-only helper now accepts that root-owned ancestry
without group/other write, retaining the existing runtime-private0700 hosted
layout and local config branch through unchanged private_path checks. Mutable
private controls were not generalized.

Final bridge class passed10 in0.494s at
/tmp/submission-runner-config-parent-final.log. The new named guard uses modeled
root/runtime stat identities with a real FD read and a real foreign-inode denial;
local sudo is unavailable, so it is not a physical root-ownership drill. It
includes both valid config-anchor layouts plus writable/foreign ancestry,
file UID/GID/mode/link, symlink, canonical-alias and inode denials; root0755 is
still refused as a mutable private control directory. The same named guard
fails against the pre-repair read at the actual private-anchor error and kills
an in-memory omission of the new ancestry checks:
/tmp/submission-runner-config-parent-probe-final.json and matching.log. The first
probe replay reached its existing O_EXCL evidence filename; the unique final
artifact rerun completed. No source was mutated by either probe.

AST/byte comparison confirms validate_node, ForeignControl, native resource
custody, private_path/PrivateControlDirectory and all same-FD/exact-inode I/O
checks unchanged. New helper/test stay below120lines, and the guard module is
1197lines without ledger changes. Ruff, local links and whitespace pass;
Commitrail is checked against bc4c37acd. Actual hosted validate_node remains a
separate read-only check after review and incremental source staging. No
supervisor start or native fault proof is claimed here; roadmap scope unchanged.

Integrated runner config validation and focused PRE fixture at5c3be023d: combined worker-group cleanup and hosted-attachment suite passed41 tests plus73 subtests in26.57s. Ruff passed all six affected Python paths, whitespace passed and Commitrail passed. This verifies the combined local test tooling, not execution of the remote fault. Staging/read-only validation of the new runner-pinned source remains the next deployment action.

### Repair busy-node fixture for the finite runner supervisor

Intent: release-image CI at877c06c81 found the existing busy-node control still calls serve without required run_id, maximum_seconds and image_digest, failing before its refusal assertion. Bounded change: scripts/test_public_smol_proof.py and this record only; supply explicit finite test pins and a matching cache entry so the existing busy-resource refusal is reached. No production changes, weakened assertions or skipped checks. Low-risk fixture repair; verify the complete existing script suite, including optimized Python refusal, and Ruff. Root reviews exact diff; human review focus is preserving no-control/no-config mutation for all four resource classes.

Fixture repair verification: all13 scripts.test_public_smol_proof unittest cases passed in3.026s, including the optimized-Python subprocess and all four busy-resource subcases. Ruff and whitespace checks passed. Exact review confirms only matching test config and the three required bounded supervisor arguments changed; all refusal and no-mutation assertions remain.

Actual runner source61dbcdd55 passed read-only validate_node on the hosted node; `/tmp/submission-runner-61dbcdd55-validation.json` binds exact source, unchanged original config and PID8263. The root then started the finite supervisor run3a85b8a2-eafa-4b33-a13c-86c05844c62e once; systemd acknowledged invocation493fafa63a0147d5ae3d89796b8c1f63, and a separate observation confirmed PID11525 active/running with supervisor-ready present. Focused public failure/replay/recovery drill pre1 is using integrated5c3be023d, with source0091 and the matching private profile. This entry records launch only, not a passing fault result or completed restoration.

CLI contract CI stopped at the existing formatter check for the four new/edited journey fixture files (lint passed). Apply pinned Ruff formatting only to those four paths; preserve ASTs and all assertions, then run whole cli/tests lint/format checks. This is formatting repair of the same bounded fixture, with no runtime change.

Focused remote pre1 finished exit1: public setup and claimed task succeeded; the failure submission returned expected503, then native trace launch-count assertion failed before replay/recovery. This is not a passing fault qualification. Isolated metadata confirms schema0091 and database/MinIO cleanup complete. Root sent TERM once to the exact finite supervisor; same-run restoration receipt `/tmp/submission-runner-pre1-restoration.json` confirms original config SHA c3f8fb85ab2cc3b27ddf8da6db1e483aae9880b23918822c241d6864322a3dcd, empty disks/leases/machines/cgroups, and exact foreign test machine/disk/cgroup/process removal. Trace diagnosis precedes any rerun.

Post-restoration independent SSH verified checker PID11966 active/running and exact original config hash. Read-only snapshot has zero trace events, so pre1 did not reach the intended native launch fault. Root reproduced a concrete harness path defect: `/var/lib/workstream-operator` is root:root0700, while its runtime child is10001:10001/0700; `sudo -u '#10001' test -x` on the wrapper fails. Runtime-only files must live beneath an accessible service-owned anchor; operator controls must remain private. Do not relax launch-count assertions or shared parent permissions.

The exact six-module release configuration unittest command that failed in CI was rerun atd67eddfd6 after the busy-node fixture repair:119 tests passed in49.978s (`/tmp/submission-release-config-repair.log`). Whole cli/tests lint and all105 formatting checks also pass; AST comparison confirmed the four formatted files preserve behavior. These local repairs do not claim the final CI or native fault qualification passed.

### Restore the structural gate by relocating AWS source tests

Intent: hosted auth preflight877c06c81 passed92boundary guards, then correctly
failed structural_debt_mismatch. Exact inventory comparison found only one new
item: backend/tests/artifacts/test_submission_intake_admission.py at1249lines
against hard1200; all33 frozen entries and policy digest remain identical.
Do not regenerate or relax the debt ledger. The added AWS profile contract tests
belong in a small cohesive artifact module using their unchanged shared fixture.

Allowed files: the original admission test module, new
backend/tests/artifacts/test_submission_aws_source.py, existing test lane catalogue
and independent family fingerprint test, and this record. Relocate the three AWS
profile tests byte/AST-identically, retain their signed AUTH/namespace fixture
closure and real-SQL assertions, and assign the new module to the same shared
family without moving/deleting existing modules. No production, workflow, policy,
ledger, skip, threshold or runtime deadline changes. Verification: exact inventory
parity, complete structural validation, old/new test and fixture identity checks,
focused collection and catalogue negatives. Reuse prior executed PG proof only
for identical test bodies/context; do not claim a fresh PG or deployed AWS run.

Implemented the relocation without changing policy or ledger: original admission
module is1120lines and new AWS source module145. All three decorated function ASTs
and exact function source segments match877c06c81, and every remaining original
module AST is unchanged (/tmp/submission-structural-877-preservation.py). The new
module imports the identical signed AUTH/admission fixtures and helpers; focused
collection passed39nodes in7.33s, including all three relocated nodes, complete
fixture closure and exact identity of13fixture/global bindings
(/tmp/submission-structural-877-collection.log/.json). Collection executes no
PostgreSQL setup. Existing PG component proof remains pre-relocation custody;
no new transaction/provider/native execution is claimed.

Full unchanged structural validation exits0 at
/tmp/submission-structural-877-after.log. Its exact repository guard passes on
current source and rejects the original1249line source restored only in memory
with structural_debt_mismatch. Omitting only the new AWS module makes the exact
independent family test fail; no source files were mutated by these probes
(/tmp/submission-structural-877-discriminator.log/.json). The shared family adds
exactly one module, retaining all previous modules/order and lane topology;
removing only that addition reproduces the prior276-module fingerprint. The
new277-module fingerprint is7d5683912037886633519322314c8fdc3c89855dc2408b2ffc629c842e3ad8fc.
All59catalogue tests pass7.54s (/tmp/submission-structural-877-catalogue.log), with
only the documented plugin-disabled asyncio-mode warning. Ruff, whitespace and
Markdown links pass. No workflow, debt baseline, limits, assertion-map, skip or
product capability changed; roadmap scope is unchanged. Hosted lane reruns remain
root-owned rather than inferred from these local checks.

The smallest repair leaves the existing exact sibling resolver and root-private
controls unchanged. A fresh control root `/var/lib/workstream-pre-launch-$RUN_ID`
is root-owned0700 directly under the existing root-owned0755 `/var/lib` parent;
the supervisor-created sibling runtime remains checker-owned0700 and UID10001
can traverse the parent. The independent custody manifest stays inside the
existing root-private `/var/lib/workstream-operator` directory. No parent mode,
service configuration or production binary is changed to make the fixture pass.
Before config rewrite, the supervisor now runs the reviewed wrapper `--version`
as UID/GID10001 with empty supplemental groups and requires the real pinned
Smol response, proving path traversal, wrapper settings read and original-binary
exec. A portable real-subprocess old-parent denial/new-sibling success test and
the unchanged exact sibling-binding control pass. Pinned read-only runner checks
also showed UID10001 can traverse `/var/lib` and execute original Smol. The new
run path and preflight remain to be staged and exercised; pre1 is still failed
evidence, not an injected-launch proof.

### Active-guide exact selected POST assertion

Cloud project_lifecycle_g at merge5bc9a104 (PR877c06c81) ran525 cases:524 passed, one active-guide test expected an empty required POST list although its approved canonical bundle now selects acme.safe_archive under mandatory single-image cardinality. Isolated schema0091 database/MinIO cleanup completed. Bounded low-risk fixture correction: backend/tests/test_projects.py plus this record; require the exact selected POST checker supplied by the approved canonical bundle, retaining every other response/authority assertion. No production/cardinality/fixture mutation. Root review; one real PostgreSQL case after native pre2 releases the shared slot. Do not credit that replay before execution.

### Second native fault run and exact PRE refusal diagnosis

Pre2 at integrated9e8ab8130 used direct /var/lib private sibling roots; actual checker UID wrapper --version preflight passed and supervisor PID13136 reached ready. Its public request returned503 before native creation; exact trace has zero events. Isolated database/MinIO cleanup completed. Root restored the exact supervisor18e8adc0-48ae-406e-8f7e-edcb80e345bc once. `/tmp/submission-runner-pre2-restoration.json` confirms original config hash, empty owned machine/lease/disk/cgroup sets and foreign fixture removal. This is not passing failure/recovery evidence.

Read-only service journal at18:10:44 reports `PRE request rejected: PRE configured identity differs` (`/tmp/submission-pre2-runner-journal.log`). Rust PRE admission compares its configured Smol digest with runtime.binary_sha256. The temporary fault harness replaces the runtime digest with the verified wrapper digest but leaves the PRE copy at the original executable. Repair the temporary config pins consistently, retain the production identity guard, and restore exact original bytes. The earlier traversal defect was real but was not the sole pre-launch blocker. A discriminating config-consistency check and focused review must precede another native attempt.

### Retire impossible duplicate revision-fence probe

TASK E cloud failure occurs because the obsolete test reserves a new checker generation after T4 has already staged finalization_pending. The current TASK owner correctly refuses it. Scoped ARCH/SEC review identifies two existing stronger real-PostgreSQL tests in test_submission_predecessor_custody.py: test_dispatch_commit_requires_current_predecessor_checker_fence advances the fence before T4 and verifies real deferred23514/rollback plus positiveT5; test_replacement_holds_task_custody_against_successor_generation verifies acceptedT4 denies a waiting successor while retaining predecessor fence. Retire only the impossible duplicate test in test_tasks.py and its sole-use stale_fence_before_acceptance_commit helper; no replacement behavior or product change. Preserve both named current tests and replay them after the shared slot is free. Refresh only mechanically affected shrinking structural debt metadata with reviewed diff; no gate/policy change. Human review focus is that both distinct race orderings remain covered by real owners and SQL.

### Cloud project lifecycle C fixture repair

The cloud `project_lifecycle_c` lane at the integrated submission head reported
four failures. Three trial custody journeys reach ART materialization without
the `ARTIFACT_PUT_RESOLVER` and `ARTIFACT_VERIFIER` fixed service actors used
by the existing checker-output storage owner, so authorization stops before
trial publication. The public operator reconciliation request test
creates its child production handler with the default remote checker adapter
while its fixture has no runner endpoint, so acknowledged delivery records an
`infrastructure_failed` checker run. This bounded change may adjust only the
three trial setup calls and that operator test's selected execution factory.
It must retain the real ART, CHECKERS, AUTH, OUTBOX and SQL owner operations,
the trial/model behavior, and the public operator reconciliation authority.
The selected POST adapter may be controlled only for the child delivery, as
the existing `delivery_fixture` controls the original request. No production,
schema, runtime profile, or test expectation may be relaxed. Focused
PostgreSQL cases were deferred until the concurrent native PRE proof released
the local heavy test slot. The first isolated four-case replay reached the
next missing `ARTIFACT_VERIFIER` identity in all three trial cases, while the
operator child completed; its PostgreSQL and MinIO cleanup both completed
(`/tmp/submission-project-lifecycle-c-fixture.log/.json`). After provisioning
the exact two identities composed by `checker_output_storage`, the two trial
publication race variants, trial byte custody and trial/model receipt custody
all passed (4 in 107.48 seconds, schema 0091, PostgreSQL and MinIO cleanup
true; `/tmp/submission-project-lifecycle-trials-v2.log/.json`). These are
isolated worktree receipts whose metadata names the pre-commit base, not a
claim of exact committed-head execution. They retain the real publication,
verification, binding, model proxy and selected POST owner paths; no native
runner qualification follows from the controlled selected response in the
operator reconciliation case.

### Match the selected POST materialization oracle to current approval

Intent: project_lifecycle_d artifact14949234050 from the same PR run records
1failure/480passes, schema0091 and complete cleanup. Only
 test_selected_post_materializes_actual_submission_and_replays fails: the current
material fixture has one required registered POST, while the oracle expects no
external members. Correct that assertion only in test_selected_post_submit.py
and this record. Require the exact one-member order/requirement, pinned locked
registry ID/digest and completed/passed phase, preserving original result identity,
replay equality and exactly-one provider read assertions. No production, fixture,
policy, timer or file-line growth. Pure exact-oracle discrimination and static
gates now; root owns B/D/G PostgreSQL batch after C/F and native ownership finish.

The replacement binds exactly order0/project.post_evidence to the locked request's
registry ID/digest and post_submit/completed/passed result. The old empty oracle
fails on the real registry_entry fixture; the new assertion accepts that control
and rejects9member-count/order/identity/result substitutions
(/tmp/submission-project-d-oracle-probe.log/.json). Every other AST and all1084
file lines are unchanged; replay equality and provider read count remain intact.
Ruff/diff/Commitrail pass. The combined structural check separately exposes the
B/G edits' stale frozen test_projects file hash; this D module introduces no
structural change. That debt must shrink through honest behavior relocation,
not a hash-only rebaseline. Actual D PostgreSQL replay remains root-batched.

Retained revision-race replay passed all3 cases in96.24s at a3d6178dc, schema0091: both variants of test_dispatch_commit_requires_current_predecessor_checker_fence plus test_replacement_holds_task_custody_against_successor_generation. `/tmp/submission-retained-revision-races.log` and `.json` confirm complete isolated database cleanup. This verifies the preserved stronger SQL/race coverage after retiring the impossible duplicate. No constraints, product guards or time budgets changed.

The next isolated pre2 trial used clean `9e8ab8130a73a1c86566908c09f8528bc2ed645d`
and the staged `18e8adc0-48ae-406e-8f7e-edcb80e345bc` supervisor. The real
checker-UID wrapper preflight and public guide/task claim passed, but the public
request returned infrastructure 503 before any native create. The unchanged
launch-count assertion failed; the read-only runner snapshot recorded zero
runtime events and drained owned resources. The isolated database and MinIO
bucket cleaned successfully. The runner journal identified the exact refusal:
PRE configured binary identity differed because the temporary fault config
changed `smol.binary_sha256` to the wrapper digest but retained the original
`pre.smol_binary_sha256`. This is failed fixture evidence, not the required
injected native launch proof.

The narrow fixture repair requires an existing PRE binary pin to match the
original Smol pin, then sets both temporary pins to the exact wrapper digest.
That original-pin check runs before creating fault controls or foreign node
resources, and a negative fixture confirms rejection leaves both absent.
The original config bytes remain available for the existing restore. A config
without PRE retains its older POST-only fault path. A focused test checks both
new pins, old-pin mismatch refusal, unchanged unrelated fields and the legacy
path. The next attempt also stores the first public failure and selected PRE
terminal in a private local receipt before the native count assertion, so an
early refusal cannot disappear with isolated database cleanup. The evidence
directory is made owner-private before this write. The existing busy-node
fixture now includes a valid Smol pin so it still reaches the busy-resource
guard. Focused supervisor and hosted attachment tests pass
`54 passed, 77 subtests passed`; changed-file Ruff
and `git diff --check` pass. A real third trial and supervisor restoration are
still required before any native launch-failure qualification claim.

### Shrink policy-read file debt while correcting B/G selected-policy oracles

Intent: B/G exact one-checker oracle repairs touch frozen test_projects.py file
debt. Equal line count still changes its frozen hash, so a hash-only refresh is
invalid. Move both whole primary tests into a cohesive PostgreSQL policy-read
module, preserving every body/assertion except the reviewed B/G empty-checker
corrections. Reuse existing API client/settings/grant fixtures; no decomposition,
new resolver, compatibility alias or production change. Allowed files are the
legacy test module, new project policy-read test module, exact catalogue and
independent family fingerprint, measured debt ledger and this record. Remove
only imports made unused by the move. Update only the genuinely shrunk FILE debt
and any unchanged-function span shifts caused by removed imports; preserve every
limit, scope, debt owner/removal chunk, policy, validator and assertion map.

Acceptance: exact decorated/body preservation, identical fixture/global closure,
same total collected tests, exact project-family addition with no module moves,
full unchanged structural validation and adversarial stale/unshrunk checks.
Root owns actual B/D/G PostgreSQL replay after the native/C/F jobs; no duplicate
heavy database run. This combined closure supersedes standalone B94bfd3d48;
G527e7ab5a remains the reviewed current POST policy oracle.

Both complete tests now live in tests/projects/test_policy_read_postgresql.py
(197lines), with exact decorated/body identity to the reviewed B94/G527 fixes.
The retained legacy module differs only by whole-node removal and its now-unused
validator import; it shrinks5492->5321. Actual inventory changes exactly the FILE
digest/span/count plus two unchanged-function start/end offsets of-1 from that
import removal. Their hashes, sizes, limits, owners and removal chunks are intact;
all other debt entries are untouched. No policy, validator or map changed.

Focused collection passed248nodes in11.21s, equal to the original CI canonical
project-node count. New paths are test_policy_read_postgresql.py::
 test_submission_artifact_policy_approval_persists_effective_policy_hash and
 test_active_guide_retrieval_returns_exact_policy_bundle. Exact19fixture/global
bindings and complete fixture dependency closure were checked without PG setup
(/tmp/submission-policy-read-collection.log/.json); full-body/source comparison is
/tmp/submission-policy-read-preservation.py. New project-family membership is an
exact+1; removing that one module reproduces both prior family and lane-ownership
fingerprints. Existing modules/assignments are unchanged. The initial catalogue
run correctly rejected its unrefreshed independent ownership count; the exact
addition refresh then passed all59tests in2.45s
(/tmp/submission-policy-read-catalogue-final.log).

Unchanged full structural validation exits0
(/tmp/submission-policy-read-structure.log). A valid shrink passes the existing
transition check, while simulated hash-only unshrunk metadata fails with
structural_debt_changed_without_shrink. Both exact independent family/ownership
tests reject omission of the new module (/tmp/submission-policy-read-guard-probe
.log/.json). Ruff, whitespace and links pass; Commitrail checked against527.
This is whole-node relocation and real debt reduction; prior PG proof is retained
as inspected custody, with current-path B/D/G replay owned by root. No runtime,
provider, public capability or roadmap completion claim changes.

Pre3 at9c489adbe reached the intended native launch fault: first-response receipt reports3trace events (create/start/delete), exact infrastructure_failed/implementation_unavailable PRE, expected public503, and failed-source assertions passed (sealed physical charge, no acceptance/Submission, task eligible). It then stopped before replay/recovery on an incorrect fixture expectation that failed intake carries acceptance-only selected_pre_submit_run_id. Production stage_acceptance alone fills that field; the real failed binding is SelectedPreSubmitRun.source_operation_id with its unique FK. Correct the fixture to require the failed operation pointerNULL, the exact reverse binding, and the same singleton operation set; do not change production custody.

The run is not a passing full fault/recovery result. Isolated DB/MinIO cleanup completed; root restored exact run09ebccf4-d1d2-49c3-8804-32d647e43d17 once. `/tmp/submission-runner-pre3-restoration.json` confirms original config hash, all four owned resource lists empty, and exact foreign fixture removal. The first response remains private in `/tmp/submission-pre-launch-evidence-pre3/remote-pre-launch-first-response.json`. Next attempt can reuse unchanged staged9c supervisor source with fresh run identity; only the local caller assertion changes.

The third isolated run used clean `9c489adbed12387fc4cc9b5101ab4176094abceb`
with one finite supervisor and the corrected temporary PRE/Smol binary pins.
Public guide activation and task claim passed. The first public submission
returned the expected infrastructure 503 and retained a finalized failed PRE
terminal with `implementation_unavailable`. The private first-response receipt
and independent runner snapshot show exactly one project machine create, start
and delete, no exec, and drained owned resources. The run then failed a later
trial assertion before replay/recovery: it expected a failed intake operation's
`selected_pre_submit_run_id` to equal that PRE. That field belongs only to an
accepted operation and must be NULL on failure. Isolated database and MinIO
cleanup both completed; the operator restored the original checker config and
empty resources. This is real first-failure native evidence, not the full
same-key/fresh-key recovery qualification.

The trial now requires the failed operation's acceptance pointer to be NULL
and binds the exact failed PRE through its durable `source_operation_id`,
canonical request and terminal source location operation ID, and the singleton
task operation set. Fresh recovery also requires its PRE source-operation ID to
equal the public accepted receipt operation. Controlled tests model the real
NULL field and reject a foreign source binding; the entire affected hosted
attachment module passes `39 passed, 74 subtests passed`. The retained native
trace-count assertion remains unchanged. A fourth connected run is still
required to prove same-key replay, fresh-key accepted T5 and full cleanup.

Integrated B/D/G repair replay atc897ad192 passed all3 exact PostgreSQL cases in89.42s, schema0091, complete isolated database cleanup (`/tmp/submission-policy-and-post-repairs.log` and `.json`). These cover persisted required PRE selection, public active-guide POST selection, and selected POST materialization/replay with the exact locked member. The unchanged structural validator and Commitrail check passed on integrated source before this replay.

### Shared CI capacity and immediate failure diagnostics (2026-11-24)

Intent: three shared-foundation jobs from run45451579222 exhausted the unchanged
1500-second budget. The exact receipts retain A1301/2319, B881/2184 and C1394/2214
completed nodes, no skips/deselections, and successful cleanup. Buffered progress
dots cannot identify failed node IDs soundly; no inferred failure mapping is used.

Allowed scope: existing shared-family shard tuple, independent exact inventory
controls and hosted aggregation/validator counts, existing lane report hook and
focused runner tests, affected operations guide, this record. Increase only shared a..c to a..i using the
existing node hash; preserve every family member, project/task assignment,
timeout, status, isolation, coverage, interruption and exact-once custody gate.
No product change, skip, new evidence schema, framework or budget increase.
Immediate failed reports must print node/phase and bounded existing traceback,
redact configured secrets, and flush before a subsequent hang or interruption.

Acceptance: historical6717-node shared inventory has exactly one new owner per
node; other5679 ownerships unchanged; independent family fingerprints unchanged.
Actual subprocess regression must retain a failure before final pytest summary
when a later node is interrupted. Missing shards/duplicates still fail existing
evidence controls. Existing1500-second budget and hosted status dependency remain
unchanged. Root selected9 shared shards for headroom beyond the smallest8
(799..868nodes versus slowest observed881 completions); node counts do not prove
timing. CI-integrity/QA review and fresh hosted replay remain required. Risk is
CI selection/diagnostic custody; human focus is complete inventory and unchanged
blocking gates. Roadmap capability claims are unaffected.

The historical12396-node canonical manifest is preserved byte-for-byte per row
except shared lane selection. Shared6717 redistributes to a..i counts
809/751/767/738/688/738/772/745/709; all5679 other nodes keep their exact owners.
All shared/project/task module tuples, old lane definitions and independent
family membership fingerprints are unchanged. Six new shared shards are the
only added lanes. Hosted coverage/aggregation and independent validator now
require exactly23 distinct complete lanes rather than17; workflow changes only
those two exact-count checks. Existing1500-second budgets and blocking status
logic are untouched. /tmp/submission-shared-capacity-preservation.json records
the original manifest digest and exact counts; this is inspected redistribution,
not fresh hosted runtime qualification.

Existing report hook now flushes failed node/phase plus at most65536characters
of redacted existing traceback, with explicit truncation. No report file/schema
or new collection behavior. Ordinary/admin output owners still apply their
existing outer redaction and buffering; child report bytes survive timeout
before pytest can print its final summary. Actual subprocess proof creates
setup/call/teardown failures then a hanging node, uses the production isolated
process timeout path, and requires all three exact reports without final summary.
It removes all four outer custody-path environments and checks unchanged parent
sentinels, preventing synthetic nodes from polluting hosted lane evidence.

First narrow red run exposed missing reports; two5-second branches did not
reach the hang under load, so those are harness failures, not discriminator
proof. The consolidated20-second test reaches every failure phase in one child.
First full focused run252pass/1fail caught the unchanged17-row timing fixture;
its exact23-row sum now includes all new lanes and retains missing/extra/invalid
timing refusal. Final five-module pure suite passed273 in50.75s
(/tmp/submission-shared-capacity-tests-v2.log), including new-i missing/foreign
bundle, latest-failed/no-fallback, partial/duplicate/skip custody controls.
The final parent-custody test-only tightening was separately replayed successfully
(/tmp/submission-lane-custody-regression.log). No database run was started.

An isolated omission mutant reached the hanging node and actual timeout124,
then failed specifically because exact setup report bytes were absent; no final
summary existed (/tmp/submission-lane-report-omission-mutant-v2.log). Initial
mutant setup lacked app/HEAD prerequisites and is excluded from behavioral proof.
Configured-secret redaction, finite output, passed-report silence and unchanged
skip recording are tested directly. Full unchanged structural validation exited0
(/tmp/submission-shared-capacity-structure.log) before the final test-only child
custody assertion addition; no policy, debt ledger or runtime assertion changed.
Ruff and whitespace pass. CI-integrity review and fresh hosted completion remain
required; this change neither identifies old buffered failure IDs nor claims
all current tests pass or the full submission goal is complete.

The affected operations guide now names nine shared shards and immediate bounded
failure diagnostics. Its bucket wording follows current isolation owner: shared
lanes create/probe/remove their distinct buckets; only omnicore_sdk retains the
fixed workstream-artifacts traffic-proof bucket. Historical17-lane receipts in
reports/roadmap remain historical and unchanged.

The fourth isolated public fault run used clean
`4b6c42807b7ce25a57573b10d06839dcbb958b92` and one fresh finite
supervisor. Guide/task setup passed; the first public submission returned the
expected infrastructure 503, with a finalized failed PRE and exact native
create/start/delete. The failed source-to-PRE custody assertion now passed.
The same-key replay returned infrastructure 503, but the trial stopped at a
compound equality assertion comparing the entire first and replay error
bodies. That comparison included request-scoped `error.correlation_id`, which
the API creates for each HTTP request. The independent post-terminal trace
still has only the original three events, so replay did not allocate another
native machine. The other equality terms were not individually observed by
this failed assertion. Isolated database and MinIO cleanup completed; the
operator restored the original config and verified all owned resource lists
empty with the exact foreign control removed.

The trial now compares the five closed public error fields while validating
both correlation IDs as canonical UUID strings, and checks selected PRE ID
and digest, native trace cursor and singleton source operation separately.
The fake public replay uses distinct valid correlation IDs; changed stable
message and malformed correlation cases fail. The entire affected hosted
attachment module passes `39 passed, 76 subtests passed`; Ruff lint and diff
checks pass. A fifth connected run is still needed for same-key custody,
fresh-key accepted T5 and complete end-to-end cleanup proof.

The fifth isolated run used clean `df766fe63b043cae686586373421ba153c735ac7`.
The initial public 503 and exact failed PRE/source binding passed. The same-key
public 503 preserved stable error fields, selected PRE ID/digest, the singleton
source operation and the native trace cursor. A fresh key then returned public
202 and a second native VM ran through project execution: the independent
snapshot has two create/start/delete sequences, one `prepare_completed` and
one `exec`. The trial stopped before accepted T5 because its shared PRE helper
expected the synthetic `project.pre_submit` requirement, while this locked
incident-summary policy selects `terminal.pre.incident_summary_layout`. The
fresh result was not retained before isolated DB teardown, so the precise
failed helper conjunct is inferred from code and requires replay. Database and
MinIO cleanup completed; the operator restoration receipt confirms original
checker config, empty owned resources and exact foreign process removal.

The helper now derives its expected requirement, registry ID/digest and native
image digest from the independently locked selected request policy. It still
requires eligible defaults, one ordered project member, the expected verdict,
request digest and Smol isolation. A private 0600 diagnostic stores only fresh
selection, policy and outcome identifiers before that assertion, so a future
failure is observable without retaining source bytes or credentials. An
incident-summary requirement positive and foreign selection/image negatives
pass; the full affected hosted attachment module passes
`40 passed, 78 subtests passed`, with Ruff lint and diff checks. A sixth
connected run must still prove fresh-key T5 and final cleanup.


### Identifier metadata contract reconciliation

Intent: repair the two exact identifier-metadata failures from shared shard H
without changing persisted identities or owner-local Python representations.
Allowed files: `backend/tests/test_identifier_schema.py` and this record.
No product/model/migration changes or removal of UUIDv7 guards are authorized
by this bounded change. Cleanup claims reuse the intake operation foreign key
as their primary key; they do not generate a second identity. The sole current
foreign-key representation difference is intake.finalization_event_id (string)
to outbox.event_id (UUID), both native PostgreSQL UUID. AGENTS.md explicitly
preserves owner-local string/UUID boundaries.
Acceptance: classify the exact cleanup-claim natural key and compare relational
PostgreSQL UUID types, retaining every generated-key version/variant assertion.
Verification: complete identifier metadata module, current metadata inventory,
diff check and scoped architecture review; existing real T4/T5 proofs cover the
unchanged runtime conversion boundary. Risk is test-contract interpretation;
review focuses on preserving native types and distinguishing generated from
referenced identities. No new deployment or full-suite claim follows.

Scoped ARCH review independently confirmed the cleanup key is already classified
in `backend/scripts/identifier_inventory.py`, migration 0073 uses native UUID,
and the acceptance owner deliberately stores `str(outbox.append(...).event_id)`.
Apply only the exact ART-to-OUTBOX representation exception and assert its
False/True Python mapping plus identical PostgreSQL UUID types; retain generic
representation equality for every other relationship.

Verification: all five identifier metadata tests passed in 0.61 seconds; pinned
Ruff and diff checks passed. ARCH inspected the final exact exception and found
no further scoped issue. Metadata inventory confirms this is the sole current
representation difference and cleanup claims the sole omitted referenced key.

### First fresh shared-lane CI fixture corrections (2026-11-24)

Intent: run45465160851 for PRhead65a176a69 executes mergeac81fefb7987569ba15414bb8130bf1433a52a1a.
Its shared_foundations_i artifact14953584341 reports3failed/706passed in410.89s,
709/709 completed, zero skips/deselections, schema0091 and complete DB/MinIO
cleanup. New immediate failure blocks expose exact causes. Allowed scope only
the broker finalizer fixture, exact active-action test inventory, client packet
refusal oracle, and this record. No production/config defaults, authorization
policy, timeout, skip, selection or completeness gate changes.

The real broker helper imports the production Celery app before configuring its
explicit test broker; cold CI has no production broker setting. Bind the existing
required WORKSTREAM_TEST_BROKER_URL before import, clear settings cache, retain
real isolated endpoint/prefix/prefork worker and all outage/duplicate assertions.
Exact catalogue expectation must include the four activated source cleanup,
accepted finalization, PM operation-read and gate-repair actions. The empty JSON
packet reaches current ART input refusal submission_packet_invalid, while full
and forged old packets retain invalid_request; preserve status, complete state
snapshot and foreign/concealment assertions.

Acceptance: focused exact catalogue check and actual four PG cases (real broker
plus all three packet variants), cold broker configuration with no ambient
production URL, no public/runtime change, Ruff/structure/record/diff checks. Risk
is test-fixture/contract custody; QA/CI review checks meaningful exact refusal
and retained durable graph assertions. Human focus is unchanged production
guards and exact approved inventory. Full CI remains running; no full-head or
provider/native completion claim. Roadmap capability claims unchanged.

Scope extension from the next exact CI failure: shared_d completed1failed/739passed
in523.97s. Its pre_submit/test_contracts.py shared reservation still constructs
retired prepared fields before reaching decision/audit/parser assertions. Port
only that fixture to the existing current _source_reservation and supply required
source contracts to dataclass replacement; all assertions and substitutions stay.
No production compatibility or new source fixture. Exercise the complete pure
contract module so failures in other shards from the same cause are covered.

The full pure PRE contract module also requires explicit invocation_receipt=None
for its existing no-runtime infrastructure finalization; no synthetic provider
receipt is introduced. All parser/digest/phase/audit assertions remain. Next
shared_f failure is exact admin permission surface94 versus current95. Extend
allowed scope to that one cardinality oracle after canonical catalogue inspection;
retain HTTP200, exact total/items equality and every role/grant isolation check.

Fresh A/E reports confirm the same packet refusal for all three JSON variants;
use exact submission_packet_invalid throughout, retaining all no-mutation and
concealment assertions. A second admin permission oracle has the same94->95
canonical correction. Extend scoped files to that existing parameter value.
ART custody documentation test needs only the two current action/permission
rows missing from spec_authorization_service.md; both independent custody
tables and their historical counts already pass and remain unchanged.

The setup-finalization reachability test fails on unrelated accepted-submission
worker topology symbols sharing the word finalization, not an authority path.
Extend only that test file: allow exact topology constant/module/process-role
symbols on exact outbox/celery_app/outbox_topology paths. Preserve the generic
rejection of every other finalization import/call, exact project_setup authority
exception, and no direct finalize invocation. Extend existing four aliased setup
authority mutations across all four affected worker paths; no whole-file bypass.

Shared_g exposes a second PRE test from the same repaired fixture and an obsolete
public201 assertion. Extend only task_authority/test_public_surface.py: require
current202 and exact sole application/zip content; preserve authentication/action
metadata, forbidden self-activation/start routes, required body and all claim
key/UUID/closed-DTO limits. No mounted route or schema change.

Final scoped evidence: exact pure batch33passed in41.60s
(/tmp/submission-fresh-ci-pure-batch-v2.log): current PRE source/phase/digest/audit
contracts, exact active action inventory, both ART custody documents, exact
worker-path topology exceptions with sixteen aliased authority mutants, and
public202/soleZIP schema. The initial pure fixture replay exposed missing required
invocation_receipt; explicitNone fixed the no-runtime branch. No original
assertion was removed. Canonical permission IDs are exactly95.

Cold composition probe removes ambient production broker configuration. Omitting
only before-import binding reproduces exact CeleryConfigurationError; final
fixture reaches the public acceptance boundary then intentionally stops, cleaning
its owned endpoint/queue/Redis connection (/tmp/submission-cold-broker-before-v2
.log and -after-v2.log). An initial standalone probe missed pytest's test import
path and is excluded from behavior proof. This proves import configuration, not
new worker/broker recovery behavior; existing integration remains required and
is coordinated with the separate scanner isolation repair. No expensive child
death cases were repeated.

Five actual PG cases passed102.36s: all three client packet JSON refusals, admin
permission catalogue, and auditor permission read. Each retains its snapshot,
identity, confidentiality, audit and exact total/item assertions. Receipt
/tmp/submission-fresh-ci-packet-admin.json records launcher65a176a69 with final
modified test bytes, schema0091 and all database/MinIO cleanup true; this is
precommit execution, not clean-commit or complete-head qualification.

Full unchanged structural validator exits0
(/tmp/submission-fresh-ci-structure.log); Ruff and whitespace pass. No production
file, policy, ledger, provider guard, workflow or test budget changed. The two
identifier-schema failures from shared_h are separately routed to root/ARCH and
are not claimed fixed here. Remaining lanes are still being observed. Historical
shared receipts prove completed tests/cleanup and newly retained failure details;
they do not turn failing CI green or qualify the full submission goal.


### A30 completed managed-style adapter substitution (2026-11-24)

Intent: pure managed PRE receipt/processor failure tests do not prove completed
source-bound facts survive real public intake, SQL terminal custody, T4 and T5.
SQL0072 already validates managed runtime/deployment/provider-cleanup facts with
exact source/request/lease/profile/config binding; no provider/schema change is
needed. The guest PreSubmitWorker constructor intentionally accepts native
isolation only, so do not relabel a native result or weaken that worker.

Allowed files exactly five: new tests/artifacts/test_submission_managed_execution.py;
existing tests/artifacts/test_submission_foreground_command.py test-only optional
typed external_execution injection; scripts/test_lane_catalogue.py exact shared
module addition; tests/test_ci_lane_catalogue.py independent shared fingerprint;
and this record. Reuse canonical inspector/manifest/default-input/derived-request
functions used by the trusted worker and its material reader, exact live source
grant drain/close, managed evidence from construction onward, existing signed
HTTP fixture and production OUTBOX/T5 helper. No product adapter, provider
registration, model, migration, native worker branch or compatibility path.

Acceptance: public rawZIP202 with one managed PRE, exact persisted source/result
and public feedback binding; matched managed deployment/config/provider cleanup
receipt with no native binary/guest/journal/UID/path fields; no Submission at T4;
real T5 consumes exact source admission and creates one graph; replay before and
after T5 preserves accepted receipt without another PRE. Exact source bytes/hash
and canonical manifest/default semantics remain real. Existing default runtime
helper behavior unchanged. One focused PG case plus exact lane/structure/Ruff
checks; bounded forged managed deployment or source/result must be rejected.
Risk is test-adapter/SQL custody composition; QA/security review inspects those
bindings. Human focus is proof limits: controlled managed-style computation, not
a deployed managed provider, native isolation, full public journey or goal-ready
qualification. Current CI failure repair is already frozen25f81de8d; new work is
separate and does not alter its executed evidence.

Evidence frozen on2026-11-26 from the executed2026-11-24 candidate, before the
separate submitter-journey delta. The single managed public case passed27.51s
(/tmp/submission-managed-public-v1.log). Its JSON receipt records launcher
25f81de8da24a3edcb2a9fbbb475b25906e720ea, schema0091 and complete database/MinIO
cleanup. Actual modified test bytes were present for that execution; this is
precommit evidence, not a clean-commit, current full-head or later-contract run.
No runtime was restarted after the pause. The saved structure session79926
returned exit0; /tmp/submission-managed-structure.log is intentionally empty on
success, and no missing live-session outcome was inferred.

The managed adapter uses the exact canonical archive inspector, semantic manifest,
default derivation/evaluator and project request constructors used by the trusted
worker. It constructs managed isolation/deployment and provider cleanup receipt
from outset, checks exact source bytes/hash, closes the actual grant and removes
its owned private temporary processing tree. The public test compares persisted
terminal/digest/receipt and every feedback result, rejects independently forged
managed deployment and source observations, proves T4 has no Submission, then
consumes the exact source admission through production OUTBOX/T5 owners. Exact
one Submission/dispatch/checker run/binding/POST event and stable pre/post-T5
accepted-key replay remain asserted.

The T5 helper invokes the real OUTBOX delivery and finalization owners; it is not
a live broker-consumer proof. Existing broker/child-loss qualification remains
separate. Existing [managed receipt and processor controls](../../../backend/tests/checkers/external/test_pre_invocation.py)
retain test_completed_worker_is_bound_to_provider_receipt, wrong selected factory,
wrong runtime family, received failure/cancellation and malformed/bounded receipt
refusal. This controlled provider fixture does not register a paid or deployed
managed provider, prove provider cleanup in a remote environment, or qualify
native isolation. No SQL/provider authorization check was relaxed.

All59 catalogue tests passed4.68s (/tmp/submission-managed-catalogue.log). Exact
shared membership is277->278; removing only the managed module reproduces the
previous fingerprint. An isolated omission of that module is rejected by the
existing independent family guard. No existing module or lane owner moved.
Ruff/whitespace checks and unchanged structure passed. Root inspected the bounded
draft with no scoped code blocker; final clean content binding follows this
evidence-only append. Full goal/hosted CI qualification remains outside scope.

### Dedicated worker queues and durable outbox publication

PRE6 proved the public native launch failure, same-key failed replay, and fresh
accepted PRE source, then timed out before T5. A read-only isolated database
observation found the accepted operation still `finalization_pending` and its
`SubmissionFinalizationRequested` event `pending` with zero delivery attempts.
The general worker had been stopped for the trial; Beat scheduled the outbox
scan on its default `celery` queue, which that same worker consumed. Hosted
general workers also shared guide work and POST effects at concurrency one,
so a long effect could delay publication. The PRE6 isolated database/MinIO
cleanup and runner restoration completed; this is a partial diagnostic, not
a completed public journey.

The bounded repair assigns all fifteen registered application tasks to seven
fixed workload queues: guide compilation, project control, artifact work,
outbox scanning, generic POST effects, submission finalization, and source
cleanup. Each queue has one dedicated prefork service in hosted and local
composition and the public journey launcher. Outbox scanning uses its own
DB-and-broker hosted worker and a sixty-second hard limit for each one-hundred
candidate page. Existing sixty-second Beat scheduling reselects still-pending
events after a failed or killed publication; generic effects remain on the
outbox delivery queue and finalization remains exclusive. A closed route map
refuses unknown task names; the worker start and task boundary refuse mixed
queues or delivery to a foreign role before owner work. The model proxy socket
follows POST delivery to its new worker. No provider, authorization, schema,
public contract, or native runner behavior changes are in this repair. Existing
cloned local/hosted worker mounts retain their prior permissions; queue
isolation is a scheduling and execution claim, not a new least-privilege claim.
The hosted scanner receives only database and broker secrets; the local opt-in
scanner still inherits the local MinIO root environment. Retained OpenAI guide
runtime cleanup remains governed by its existing provider-mode credential
availability and is not qualified by moving it to project control.

Allowed files are the existing Celery worker topology/task files, the hosted
and local Compose/preflight and inference overlays, the public journey worker
launcher, affected topology/broker/Compose tests, and their immediate docs.
The risk is high because publication can stall accepted operations; architecture,
security, QA/test-delta and CI topology review apply. Acceptance requires an
independent exact task-route inventory, wrong-queue task refusal, actual Redis
prefork scan-to-finalizer delivery with no general consumer, hosted/local
singleton queue checks, and cleanup of owned test resources. This proof does
not qualify native fault recovery or the complete public journey by itself.
The focused real Redis/prefork test passed with one scanner and one finalizer,
no general consumer, an actual foreign registered-task rejection before DB
effects, exact T5 finalization and public replay; its isolated PostgreSQL and
MinIO resources cleaned (`/tmp/workstream-queue-scanner-real2.log` and `.json`).
The first run exposed Celery's requirement for a declared sender default even
with explicit routes; the corrected closed fallback router still refuses an
unknown task. The launch receipt names the base commit because the working tree
held this patch, so it is scope-compatible dirty-tree evidence, not clean-head
qualification. Focused topology, rendered hosted/local configuration, Ruff,
structure, Commitrail and changed Markdown links are checked separately.


### Remaining full-suite schema execution boundary

Backend run 45465160851 at PR head 65a176a69 completed with all project/task
lanes passing. The nine shared shards executed all 6717 assigned nodes with
no skips/deselections; their concrete contract/fixture failures are addressed
by the reviewed local repairs. This is not a final-head CI pass.
The schema lane exhausted its unchanged 1500-second budget: artifact 14957896305
records 237 of 584 nodes complete, including all 56 isolated-runner admin cases
and 65 of 70 Alembic cases, without a reported assertion failure. Root's bounded
remaining-five-case probe at 3334fa566 also reached its 180-second bound after
three completed cases; this is incomplete execution, not a pass or proof of a
specific hanging test. Its receipt confirms schema 0091 and complete owned
database/MinIO cleanup. Private evidence: `/tmp/submission-schema-65a.zip`,
`/tmp/submission-schema-tail-65a.log`, `/tmp/submission-schema-tail-65a.json`.
Full schema execution still needs bounded capacity diagnosis/partition and a
complete run; do not skip cases or treat the timeout as an assertion repair.

Queue isolation is integrated at db4f0a92c after scoped ARCH review and real
scanner/finalizer proof. The native public-journey caller still needs its owned
worker lifecycle updated before the combined live drill. The submitter handoff
core remains in a separate reviewed candidate pending historical-upgrade and
public read tests. All changes remain in PR 708; PR 709 is not our workstream.


### Bounded schema lane capacity partition (2026-11-26)

Intent: Backend45465160851 schema artifact14957896305 has584canonical nodes
(528ordinary,56admin),237completed (181ordinary,56admin), zero skip/deselection
and1502.273seconds before unchanged1500-second interruption.65/70Alembic cases
completed. Root remaining-five-case probe also reached180seconds after three
completions with completecleanup; sortedmetadata/progress does not identify a
hanging node. No assertion repair or skipped case follows from these timeouts.

Scope exactly ten paths: existing test_lane_catalogue.py, independent
validate_test_lane_evidence.py, Backendworkflow, test_ci_lane_catalogue.py,
test_ci_scope_selection.py, test_ci_test_lanes.py, test_test_lane_evidence.py,
test_merge_test_lane_evidence.py, operations_backend_testing.md and this record.
Use the existing hash to partition the entire current schema family across
schema_contracts_a, schema_contracts_b and schema_contracts_c. Preserve all module
membership, current A30 inventory, otherfamily ownership, every node and runtime
kind. Admin runner self-tests still execute in separate admin units; ordinary
children retain isolated credential/database custody. All three schema jobs and
the aggregate remain disk-backed. Total required lanes23->25 with exact distinct
coverage/fan-in/validator inventory. Keep1500seconds, all blocking gates and all
cleanup/skip/deselection/duplicate/partial-execution checks unchanged.

Existinghash on the historical584nodes gives191/207/186total,175/178/175ordinary,
16/29/11admin and29/26/15Alembic across three shards. Two shards leave259/269
ordinary and35/35Alembic; three is the smallest placing every ordinary group
below the181observed ordinary completions, with expensive Alembic groups reduced
from70to atmost29. Counts guide capacity, not timingqualification or a diagnosis
of an individual slow/hanging case. Existingnodehash and runtime are unchanged.

Acceptance: exact old-to-new canonical row preservation except schema owner,
no foreignfamily changes, deterministic/order-independent and head-independent
one-owner partition, unchangedadmin classification/credentials, all3disk-backed
workflow selection, missing/duplicate/new-shard evidence rejection and existing
purelane suites. Risk is CI capacity/custody; root+ARCH review exact gates and
admin isolation before push. No heavy PostgreSQL run, cancellation, rerun, product
change, newframework, timeoutincrease or PR709 work. Fresh hosted completion
remains required. Runtime roadmap capabilities do not change.

Candidate uses consistent schema_contracts_a/b/c names; the ambiguous old
unsuffixed lane is retired from active callers. The existing schema module tuple
is moved unchanged into SCHEMA_CONTRACT_MODULES, registered as one more existing
partition group. No new runner or hash path. All three schema jobs explicitly
select disk storage both in PostgreSQL container options and the independent
mount/write-settings expectation. Exact hosted fan-in/coverage and independent
validator require25lanes. Every1500-second execution budget is unchanged.

The saved12423-node manifest comparison preserves all node IDs, module names and
execution kinds; only584schema owner fields change, with11839other owners
unchanged (/tmp/submission-schema-capacity-preservation.json). The current A30
shared module membership/fingerprint and all other family definitions are
unchanged. This historical redistribution is not a current full collection or
actual execution result.

Focused existing five-module CI suite passed335tests in100.20s
(/tmp/submission-schema-capacity-pure-v1.log), including deterministic reversed
input/head independence, every schema module partitioned once, ordinary/admin
kind preservation, exact three-shard scope selection, strict25-row timings and
fan-in/independent custody failures on all three schema names. Existing missing,
foreign, partial/duplicate/skipped and latest-invalid/no-fallback controls remain
blocking. Tests still require separate ordinary coverage even when admin coverage
is empty. The plugin-disabled pure run has its existing asyncio_mode warning;
no async or database test was silently skipped.

An isolated source-only workflow probe kills omission of one schema disk member,
reversal of the storage guard expectation, and an increased execution budget. No
shared file was mutated by these probes. The regular pure suite also checks exact
three-name membership in both disk rules and unchanged45-minute job allowance.
Ruff and whitespace pass; full unchanged structural validation is recorded at
completion separately. No PostgreSQL, native runner, deployment, CI rerun,
cancellation or push was started. Hosted timing/completeness must still be
qualified on the combined candidate; no individual timeout/hang is declared fixed.

Final unchanged structural validator exits0
(/tmp/submission-schema-capacity-structure.log). Source binding confirms the
old schema module tuple is identical, every non-schema lane definition is
unchanged, A30 membership remains present, and run_test_lanes.py has no diff
(/tmp/submission-schema-capacity-source-binding.json). Pure tests executed these
modified candidate files over clean basef40071744 before commit; subsequent
changes were documentation/evidence only. This is bounded precommit verification,
not a clean-head hosted run. Ruff, links, Commitrail and whitespace pass. Root
inspected the scoped diff with no blocker; independent ARCH review and combined
25-lane hosted completion remain pending. No schema test was executed or skipped
locally for this partition change, and no other workstream/PR was touched.

The existing native public journey launcher also needs this topology. Its
former guide worker selected both `celery` and `workstream.outbox`, which the
singleton guard now rejects. The launcher starts one owned prefork process
for each of the seven exact workload queues, using recorded guide composition
only for project setup and the production app for the other roles. Fault
callbacks pause and restart only POST/outbox delivery; the scanner and T5
finalizer remain live so accepted-source publication can continue. Every
source-cleanup child receives the separately supplied private deletion
credential and explicit bounded profile; the upload/API credential remains
with the other workers. The profile must identify that upload principal, and
the deletion key must differ. Every
started process is registered before readiness is awaited, and final cleanup
attempts every owned process group even after a prior stop failure. A real
exited-leader/remaining-child regression checks that group cleanup does not
leave a worker behind. Focused command tests pin the complete role/queue/app
map. This is caller closure for a future combined native journey; no new
native trial or deployed worker qualification is claimed by these tests.
The affected hosted-attachment test module passed all 44 cases and 87 subtests;
the focused four-case worker custody subset passed separately. Replacing the
group stop in memory with the previous leader-only return made the real
exited-leader child regression fail, and its `finally` removed that owned
child. Ruff, whitespace and changed Markdown links passed. The two Python
files predate this change with Ruff-format differences, so the edit did not
claim a file-wide format pass.
## Submitter journey reconciliation

The public ZIP command takes task, assignment, file and caller idempotency key,
with optional exact project feedback. TASK chooses and retains the current
predecessor and revision preparation under lock. Recheck that selection before
PRE and acceptance. T5 consumes accepted evidence. Preserve historical packets
and hashes and keep optional project feedback outside checker eligibility.

Allowed files for the contract stage are ART's intake API, repository,
foreground admission, progress, registration and finalization, its selected PRE
binding and HTTP route and error adapter. TASK may update its submission context,
intake custody, creation, dispatch, requirements and models. CHECKERS may extend
the packet evidence decoder where required for exact old and new custody. A
forward Alembic migration may update the native guards and add feedback storage.
Directly affected contracts, owner tests, public API fixtures, CLI and MCP inputs
and docs are in scope. The guide and exact assignment read stage extends the
current PROJECTS, ART, AUTH, TASK, CHECKERS and contribution read compositions and
their client contracts and tests. Preserve the T4 status transition and existing
authorization, source custody, terminal outcome and AWARD ownership. Exclude
queue topology, Finance fulfillment, review implementation and email.

Risk class L0. Architecture, security, QA and test delta review the immutable
inputs, native guards, authorization and replay. Documentation and product
operations review the contributor journey and retained transport limits. Human
review should verify revised selection, closed-assignment isolation and the
difference between a granted award and fulfilled payment. Verification uses
real PostgreSQL and source storage in focused integration cases, plus the
connected CLI/MCP journey against the combined candidate.

The earlier two-source PostgreSQL drill started from `3334fa566` on Alembic
`0091_qualified_aws_source` and advanced to the `9efd2c017` implementation of
`0092_submission_feedback`. It refused upgrade while a receiving operation
was live. After it settled, the approved old attempt replayed its original
receipt, retained the two historical packet fields and digests, and finalized
once using existing OUTBOX/T5 owners. A separate nonempty legacy command
conflicted with the new minimal replay. The isolated database cleanup receipt
was complete. The reproducible two-checkout drill now lives with the
[submission qualification experiments](../../../experiments/pilot04_external_checker_runtime/submission_feedback_upgrade_drill.py).
Run its test explicitly from a detached `0091` checkout with
`WORKSTREAM_SUBMISSION_FEEDBACK_CANDIDATE` identifying the candidate backend,
using the owned isolated PostgreSQL runner. It also checks the exact audit
constraint delta and row identity across the migration.
The expanded drill passed in 248.27 seconds using the predecessor
`3334fa566` and the `0092` schema from `a38dee4d1` and `eb5f93de4`, with
owned database cleanup complete.

At `eb5f93de4`, the combined isolated PostgreSQL/MinIO run reached eight
passing case markers for new intake, retained rejection, guide access and
concealment, revised terms, the managed adapter, migration graph and the
connected CLI. Its child reached the 540-second cap before a terminal pytest
summary and exited 124. The isolated database and MinIO cleanup receipts both
completed. The separate built-CLI HTTP suite passed 52 cases. The
precommit caller check for the `124695d5e` code passed 69 cases and 100
subtests in 68.03 seconds. The installed MCP wheel and built CLI are available to the
native proof. The probe records a connected-client receipt only when both are
used with the same API and worker processes and the governed checkpoints pass.

The November 26 infrastructure recheck verified the same running native
runner instance at `56.228.13.174` using its pinned original SSH host key via
`HostKeyAlias`. The configuration digest prefix `c3f8fb85`, executable,
cache and root pins were unchanged. Both runner services were active with
98.1 GB free. The existing API release still used image prefix `83744f1c16dd`,
reported healthy and had 93.2 GB free. This was a read-only recheck of the running
infrastructure. Combined candidate execution and deployment qualification
remain open.

### Installed 0092 migration preflight correction

CI's historical-schema lanes exposed a real migration preflight omission:
`alembic/env.py` admitted installed `0091` but refused the new installed `0092`
head before any migration could run. The closed list now names `0092`; its
earlier installed revisions and fresh-database guard remain intact. A current
database no-op upgrade regression checks the revision and public snapshot before
and after. This correction changes no migration body or retained rows.

###0092 caller integration: exact TASK peer DTO and CLI formatting (2026-11-26)

Intent: Backend45776768469 for pushed46858a75d (merge6e2761218) exposes
preflight TASK-self-only syntax assertion and CLI formatting failures before
contract execution. Canonical public API validation already accepts TASK's
intended reuse of PROJECTS ContributorGuideDocument from guide_reads; root
confirmed that single immutable public owner edge avoids duplicate schemas.

Allowed exactly seven files: tests/architecture/test_module_boundaries.py,
cli/tests/integration/test_submission_http.py, test_submission_public_api.py,
test_task_context_http.py, test_task_guide_http.py, test_task_guide_public_api.py,
and this record. Change only exact TASK guide_documents.py peer-symbol exception
while preserving canonical public/private/mutability checks and rejection of
private/unrelated foreign imports. Add valid-first negative controls at that
exact path/symbol boundary. Format only the five named CLI files; verify AST
identity before/after and run unchanged CLI Ruff lint/format gates.

Risk is architecture/CI assertion custody, not product behavior. Independent
ARCH review applies after freeze. No production source, registry, policy, debt
ledger, test budget, skip or broad foreign-API allowance. No PG/native run or
CI restart/cancel/push. Grouped historical0092 fixtures and public-contract
failures are separate bounded followups; do not weaken guards to clear them.
The existing draftPR708 remains the sole workstream; PR709 is untouched.

The exact peer exception applies only to TASK api/guide_documents.py importing
ContributorGuideDocument without aliases from PROJECTS api/guide_reads. The
canonical public API validator, frozen/closed model checks, nonempty import scan
and all other TASK-self-only dependencies remain enforced. Six valid-first
mutations reject private imports, another peer schema, mixed allowed/foreign
symbols, wildcard, bare module import and the allowed symbol relocated to another
TASK API file. The wildcard probe initially expected AssertionError, but the
unchanged canonical parser correctly raised its earlier wildcard_import error;
the oracle now asserts that exact existing rejection rather than weakening it.

Focused TASK/peer/private-reexport cases passed8 in4.97s before the final
nonempty-scan preservation tightening; final targeted replay records completion
separately. CLI Ruff0.15.22 lint and all105file format checks pass. The exactfive
formatted files have identical before/after ASTs
(/tmp/pr708-cli-format-preservation.json), so no assertions/fixture behavior changed.
No database or client runtime was rerun for formatting. Full structural validation
is being checked unchanged; independent ARCH review remains required. This
clears only these named early gates, not the other0092 callers or full CI.

Final narrow replay passed8 in1.45s
(/tmp/pr708-peer-boundary-repair-final.log); full unchanged structural validator
exits0 (/tmp/pr708-0092-gate-structure.log). Ruff, changed links, Commitrail and
whitespace pass. Exactly seven scoped files; all product/registry/policy/debt
files unchanged. The six attack controls first pass the intended actual edge,
so their refusals cannot be satisfied by a globally broken import checker.
This is precommit source verification over57c939a30, not hosted or public journey
qualification. Root supplied architecture disposition; independent ARCH review
of the frozen exception remains pending.


###0092 current caller and projection alignment (2026-11-26)

Intent: group the current-contract CI failures from45776768469 by owner, after
the separate exact peer-edge/CLI format repair. Allowed twelve files: this
record; artifacts/intake_recovery_support.py; test_submission_bundle_preparation_recovery.py;
test_artifact_architecture.py; authorization/task_authority/test_task_commands.py;
authorization/setup_finalization/test_catalogue.py; test_api_rate_controls.py;
checkers/execution/test_storage.py; authorization/submission_history/test_absence.py;
test_tasks.py; outbox/test_delivery_topology.py; and
artifacts/test_submission_finalization_worker_loss.py. No production source,
sharedconftest, historicalrestore/schema fixture, policy, skip, budget or new
compatibility alias. ARCH separately owns genuine retained private-attestation
witness and all historical schema/snapshot failures; preserve their assertions.

Reconstruct current recovery input from exact stored task/assignment/feedback,
not the enriched server command record as a caller DTO. Require exactly three
current input fields and retire only the two obsolete removed helper parameters
for required summary/attestation. Existing closed/bounded current coverage is
test_metadata_canonical_fixture_and_round_trip_preserve_exact_feedback,
test_feedback_rejects_unrepresentable_headers_without_normalization,
test_submit_metadata_rejects_retired_inputs and
test_frozen_values_revalidate_nested_instances_and_reject_unknown_command_fields
in test_submission_intake_contracts.py. All other malformed locked-policy cases
remain. Apply ledger change only if actual structural inventory demands it; no
blind baseline update.

Preserve mounted exact ordered/privacy-safe feedback and retained warning
projection, while optional current input is feedback, not removed summary or
attestation. Add exact new feedback history field, the approved two action IDs
and three read-rate routes; keep independent exact inventories and mutation
controls. Required guide documents now compare exact locked snapshot IDs,
fixture byte hash/count/media/order and task-bound read references; never just
nonempty. Stored checker finding message is verbatim with no invented fix.

Cold dedicated-worker negative fixture must bind its existing explicit eager
setting before importing Celery. After actual T5 commit, broker rescan legitimately
sees one original finalizer lease plus one pending POST. Require that exact extra
uninvoked POST and exacttwo counts only for after_commit; before_observation
stays exactone. Keep authority/lease/source/redelivery/graph/cleanup assertions.
Risk is fixture/projection/custody proof. QA/CI/ARCH review exact test preservation
and stale-producer retirement; root coordinates one focused PG/broker run after
native slotrelease. No new service or end-to-end completion claim; all work stays
in PR708, never709.

Focused current-contract pure cases passed42 in49.97s
(/tmp/pr708-0092-current-contract-pure-v1.log), including mounted exact feedback
and privacy bounds, current metadata canonical/bounded/retired-field guards,
exact activated action/rate/history schema and twelve remaining malformed locked
policy cases. The separate cold dedicated-worker test passed3 in17.05s
(/tmp/pr708-0092-cold-worker-boundary.log); explicit eager configuration now
precedes import, with no production default changed. Its plugin-disabled warning
is unchanged and no async test was skipped.

Guide-hint oracle binds exactly two locked originals (guide.pdf/rubric.pdf),
snapshot item IDs, canonical fixture hash/count, order/media and task-bound read
references. Finding history expects the actual retained diagnosis and no invented
fix; fallback messages remain tested elsewhere. Retained optional packet warning
projection remains a mounted-command response test, not a claim that new minimal
input produces deprecated summary/attestation warnings. Only feedback is optional
current input. All private path/storage fields remain forbidden.

Full unchanged structural validator exits0
(/tmp/pr708-0092-current-contract-structure.log). The two obsolete parameters
shrink test_tasks.py by ten lines; no ledger entry for that file requires refresh,
and no policy/debt file changed. Ruff and whitespace pass. Exactly twelve scoped
files; privacy test and seed helpers, historical migrations and conftest untouched.

Runtime evidence remains pending: the current accepted-recovery helper consumers,
real guide-hint/source metadata and stored finding history, and the changed
after_commit Redis/worker rescan assertions have not been executed on this
candidate. Root explicitly holds heavy PG/broker work while native journey has
priority. No source/provider/authorization owner was mocked or changed to make
their future run pass. This clean source checkpoint is for review and later
focused execution, not a complete QA/CI/deployed-journey verdict.

### Retained 0092 history fixture correction

The historical migration probes keep their predecessor schemas and rows intact.
Where current test owners construct an older cleanup or revision source, a
null-only `submissions.feedback` read projection is removed before the real
upgrade; the migration snapshots then require the actual 0092 column to be
null and preserve every preceding field. The current HTTP history privacy
fixture uses its still-stored private package URI as the nonleak witness. A
separate checksum-bound 0024 archive exercises the genuine old private
attestation after upgrade through the current fixed history projection.
These fixture changes do not relax runtime custody, authorization, or SQL
guards. The checksum-bound archived private-attestation projection passed in
the first two-case replay; that run also exposed a predecessor 0088 INSERT
using the new command metadata. A scoped fixture binder now writes the exact
historical v1 metadata body and digest before the old guarded INSERT. The
isolated 0088 replay passed in 131.62 seconds with schema 0092 and complete
database cleanup (`/tmp/submission-0092-0088-v1.log` and `.json`). Other
historical lane cases remain pending and are not represented by this receipt.

### Remaining current CI observability and fence fixtures (2026-11-26)

Intent: repair only the observed real-prefork diagnostics startup fixture and the
current predecessor-fence fault injection, and diagnose the OTLP timeout log
assertion independently. Scope is tests/test_celery_observability.py,
tests/test_submission_predecessor_custody.py, a possible focused OTLP test repair
only after causal evidence, and this record. Production queue declarations,
WorkerTaskBoundary, source custody, SQL guards, exporter deadlines and logging
ownership remain unchanged. No historical/privacy fixture overlap.

The Redis diagnostics probe must consume one declared dedicated queue using its
real registered identity with only a temporary synthetic probe body, restoring
the original task exactly; it qualifies diagnostics, not the scanner owner. The
stale-fence probe must accept only the two independently validated TASK selector
forms (public current predecessor selection and explicit CHECKERS lineage), then
retain real post-fence application refusal and staged T4/deferred SQL rejection.
All original correlation, context reset, failure/retry, privacy, source charge,
rollback and valid-control assertions remain required. No PG/broker/native run
while the parent-owned native/historical fixture slot is reserved. A permitted
lightweight local HTTP OTLP run is diagnostic evidence only.

Static-ready checkpoint: only the two named tests and this record changed. The
diagnostics test uses the existing scanner task/queue with the production task
base and closed route intact; its synthetic body proves diagnostics only. Original
registration identity is asserted on restoration and startup failure includes a
bounded tail of its private worker log. The fence test proves both reader forms
return the same exact genuine context before advancing the fence and requires
both genuine readers to refuse afterward; only those two selectors are frozen.
All staged-T4, exact23514, no-mutation, charge and positive T5 assertions remain.

The unchanged OTLP status/refusal/timeout matrix passed3 in7.10s with the system
Python3.12.3 interpreter and explicit asyncio plugin, no conftest/PG/broker/native
(/tmp/pr708-otlp-failure-baseline.log). This does not resolve the original CI
timeout case's empty log set: even its synchronous Celery labels were absent. No
logger ownership, deadline, expected event or exporter behavior was changed on
that evidence. OTLP's full-lane failure remains an unresolved qualification limit.

Ruff and whitespace pass; the unchanged full structure validator exits0
(/tmp/pr708-observability-fence-structure.log). Both test files already fail Ruff
format-check at the base, so this bounded fixture patch does not reformat those
whole modules. Native execution has priority; the repaired real Redis/prefork
probe and both PostgreSQL fence parameters have not run on this candidate. No
production behavior change or aggregate runtime-pass claim.

### Diagnostics startup failure disclosure correction (2026-11-26)

Intent and bounded scope: remove the newly added raw worker.log tail from the
real-prefork startup assertion in tests/test_celery_observability.py. Independent
security review identified that early worker logs can contain a broker URL with
credentials before safe logging is installed. Retain the original exit-code
assertion and all dedicated queue, registration restoration, context and privacy
guards. The private log remains available to the test's existing safe-content
assertions; it is not copied into the public failure diagnostic. No production
changes or PG/broker/native rerun is required for this diagnostic-only removal.


### Integrated host qualification checkpoint (2026-11-26)

Both backend SDK release images built from 1d28b567d and passed the existing
native-hosted image verifier on the API host. Receipt:
`/tmp/workstream-host-image-5fb26081a6c9/host-only-build-1d28.json`.
They are local candidate images, not published or deployed releases. The MCP
image built from the same source; its first container proof stopped at the
obsolete 132-tool expectation. Current authenticated catalogue and OpenAPI proof
passed 28 cases for 135 tools; the corrected existing container proof is pending.
The ignored CSV/XLSX contain no obsolete tool count; the workbook retains its
single WorkStream RoadMap sheet.

The first paired CLI/MCP native probe stopped before submission because the
health contract reports a cache count, not manifest identities. d8046ea23 fixes
that comparison, retaining independent exact configuration/binary/cache custody;
the positive and wrong-count controls passed. Original failed receipt remains at
`/tmp/workstream-paired-native-5k85wccw/cleanup.json`, with database and storage
cleanup complete. A fresh independently checked runner custody envelope binds
config 7ceb63e3 and the clean d8046ea23 rerun. The running journey has no success
claim yet. Runtime package source is unchanged by the subsequent test/doc repairs.

ARCH reviewed the historical fixture changes and QA selector/queue repairs.
The raw worker-log diagnostic finding was removed in 711c02b92. Exact historical
0088 replay passed with cleanup; remaining historical and broker cases still
need their terminal evidence. The unchanged local OTLP failure matrix passed
three cases but does not explain the earlier CI missing events. Main was fetched
with zero unseen commits. All work remains in PR 708, with production deployment,
final-head CI and acceptance/configuration reconciliation incomplete.


Host MCP transport proof is now terminal PASS using unchanged image source
1d28b567d and corrected verifier 565cc143a. Receipt
`/tmp/workstream-mcp-proof-565.json` binds image ad364ad8, 135 tools, signed caller
isolation, restart, replacement and stale-network-namespace counterexample.
This is the shipped container against the fixture provider, not deployed OAuth
or submission outcome proof. The d8046ea23 native rerun passed runner health but
stopped when the dedicated cleanup worker refused startup configuration; the
other workers started. Its database/storage cleanup is complete at
`/tmp/workstream-paired-native-n7e8wt8w/cleanup.json`. Diagnose that exact
configuration before another full rerun; no acceptance or PRE success is claimed.


Focused current-contract runtime closure: eight cases passed in 183.12 seconds
with real PostgreSQL/MinIO and the dedicated Redis consumer. Receipt
`/tmp/pr708-current-fixtures-runtime-v1.json` records 0096a744c, schema0092 and
complete database/storage cleanup. The launch observation db9dc975 differs only
in this record; all six executed test/helper modules match the reviewed fixture
commit. Covered three recovery consumers, exact guide/current-authority hints,
stored failure history, both SQL predecessor-fence parameters and the real
prefork observability probe on its declared queue. The existing synthetic-context
Pydantic warning remains visible. Broker-loss replay and the earlier CI OTLP
missing-events failure are not closed by these eight cases.

### Hosted API cutover inventory (2026-11-26)

Read-only inspection of the current API host and `deploy/hosted` composition
found the enabled `workstream-hosted.service` and healthy app-profile containers
still using release `013ffbac2291179c03ff6d832f52efee9382322d`; PostgreSQL is at
`0069_remove_artifact_proof`. The existing service unit points at that release
directory. The reviewed backend agents, omnicore, and MCP images built from
`1d28b567d` passed local hosted image verification (receipts
`/tmp/workstream-host-image-5fb26081a6c9/host-only-build-1d28.json` and
`/tmp/workstream-mcp-proof-565.json`), but have no published ECR digests and are
not deployed. Agents is the currently selected backend variant; the installed
model selection remains `openai_agents_sdk` / `openrouter` /
`openai/gpt-5.6-luna`. Neither guide nor artifact data was changed.

The existing release environment already selects the runtime AWS credential,
database and Redis secret files, app profile, model proxy, S3 bucket and region.
Separate cleanup credentials are installed at
`/etc/workstream/aws/source-cleanup.json` for
`arn:aws:iam::094032936130:user/workstream-source-cleanup`, distinct from the
runtime `workstream-storage` principal. Runner TLS files are installed at
`/etc/workstream/runner-tls/{ca.crt,app.crt,app.key}`. Twelve unique preflight
selectors remain absent: cleanup principal ARN and credential host-file path;
submission execution and source-cleanup profile JSON values; runner CA, certificate,
private-key paths, host, port, and server name; trusted-intake image and config
digests. Bind the runner address and server name to its installed endpoint and
certificate, and the intake digests to its qualified custody receipt rather
than template values. The verified runner capture is recorded separately at
`/tmp/workstream-paired-native-e38-custody.json`; it does not qualify the blocked
native journey.

The typed execution and cleanup JSON candidates under
`/tmp/workstream-hosted-submission-profile-candidate/` validate structurally.
Their PRE aggregate deadline is 120 seconds; **choosing 120 seconds for C01 is
an explicit production policy decision still outstanding**. The other candidate
capacity, quota, retry, sweep, and cleanup values need reconciliation against
measured hosted behavior; the local 496 MiB MinIO resource result does not by
itself qualify hosted AWS limits. This is evidence and configuration work, not
an additional approval gate for each field.

After the native blocker and configuration reconciliation, cutover uses the
existing `deploy/hosted/compose.py` pull/migrate/up and `preflight.py` flow:
publish the exact verified agents and MCP images to the existing
`workstream-backend` ECR repository and record actual repository digests; stage
a new exact-source release directory while retaining the old directory/unit;
back up PostgreSQL and source custody, drain old producers, migrate forward to
`0092`, run full preflight, then start the dedicated app workers and verify the
public and durable journey before repointing the enabled service unit. Existing
guide and source data stay intact. Migration is forward-only: restoring the old
`013ffbac` image against `0092` is not a safe rollback without independent
compatibility proof. Preserve the pre-migration backup and prior image for a
controlled restore or use a reviewed forward repair. No host mutation, image
publication, migration, service restart, or production cutover was performed in
this inventory.

### Current TUI submission fixture feedback (2026-11-26)

Intent and bounded scope: cli/tests/integration/test_tui_public_api.py and this
record only. New0096 Backend45784976520 job139790509318 has one failure and
24 passes: the signed TUI read/revocation test supplies retired summary and
contributor_attestation fields to the closed current SubmissionIntakeMetadata.
The actual local log is /tmp/pr708-0096-cli-api.log; the failure is before its
current source producer, not a TUI authorization failure.

Use the same nonempty text as current optional feedback; require its exact
retained public value and a null historical summary. The native TUI must render
that feedback before revocation and remove it after fresh real grant revocation.
Preserve actual source/T5 fixture, signed identity, foreign actor404, no dependency
overrides, exact read-only requests and product counts. No retired field alias,
production DTO change or privacy assertion removal. PostgreSQL execution stays
pending while the parent-owned native cold-start prerequisite holds the slot.

Static verification: evaluate the exact old and new constructor AST nodes against
the current production model. Old fails precisely on the two retired fields; new
retains exact task/assignment IDs and nonempty feedback. AST comparison preserves
all22 original assertions, changing only the approved privacy text selector, and
adds exact null-summary and retained-feedback assertions; all other module nodes
are identical. Ruff check/format and whitespace pass. No PG/native/TUI execution
on the repaired fixture yet; the original CI failed before that fixture setup
completed. Parent holds the slot for the native prerequisite and will obtain
runtime evidence in the coordinated run or new CI.
