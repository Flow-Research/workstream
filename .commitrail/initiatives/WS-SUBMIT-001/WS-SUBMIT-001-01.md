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
