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
