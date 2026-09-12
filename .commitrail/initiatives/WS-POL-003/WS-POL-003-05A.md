# WS-POL-003-05A — Complete proposal review and pre-submission approval custody

- Initiative: WS-POL-003
- Durable disposition: Complete
- Intended merge outcome: One hidden PROJECTS operation family reviews an exact finalized unified proposal, records pre-submission approval, and requests a setup-wide correction without changing prior evidence.

## Intent

The project manager must see the complete agent result before deciding what to
approve or correct. Pre-submission intake policy and post-submission evaluation
proposals stay distinct. Approval runs the existing policy compiler and makes no
model call. Correction requests another generation through the unified setup
machinery; it does not edit or retry an uncertain provider result.

This implements the adopted [05A contract](planning/chunks/WS-POL-003-05A-hidden-pre-submit-approval.md).
Public authorization and exposure follow in AUTH-12F4 and POL-05B.

## Replaced behavior

Before this change, `guide_compilation/` owned immutable attempts, results, component
projections and setup finalization. `ProjectService.approve_submission_artifact_policy`
accepted manual lineage and rejected unified proposals. Its shared activation
consumers and downstream fixtures now use unified approval custody; the obsolete
manual HTTP approval route is removed.

## Bounded change

### Allowed

- `backend/app/modules/projects/`: complete review contracts, policy merge and
  approval owner, correction operation, canonical request/context integration,
  removal of superseded manual approval route/schema/implementation, and
  shared active-guide-read readiness custody for the replacement approval.
- `backend/app/modules/authorization/api/`: narrow unavailable-by-default typed
  review/approval/correction port; no activated evaluator or composition.
- AUTH catalogue and audit vocabulary may declare the two proposal actions as
  `planned` and register bounded evidence identifiers. Hidden PostgreSQL custody
  needs these identifiers; neither action becomes active or receives an evaluator.
- `backend/app/modules/checkers/api/policy_compilation.py`: public typed bundle-and-plan
  contract implemented by the canonical catalogue; the private compiler remains
  the sole implementation. The catalogue supplies both operations through the
  existing injected planner, without widening planning-only consumers. The dependency-free
  `checkers/api/artifact_paths.py` owns shared machine-field grammar; replace
  its private compiler/runtime consumers and PROJECTS path validation together.
- `backend/app/interfaces/project_agents.py` and affected runtime input shaping:
  bounded correction feedback bound into the existing canonical input hash,
  plus field-specific artifact-proposal path/pattern validation matching the
  existing compiler contract (nested relative paths are machine fields, not prose).
- PROJECTS database models and one successor Alembic migration for append-only
  operation custody, composite ownership and immutable evidence constraints.
- CHECKERS effective-plan lineage and its PROJECTS, ART and TASK consumers:
  preserve the existing opaque guide-version string without integer coercion,
  including the AUTH pre-submit materialization resource schema.
  Reconcile existing packet validation with the canonical policy’s required
  `artifact_hash_manifest`, supplied and identity-checked from inspected bytes;
  this adds no checker capability or execution activation.
- Affected tests and shared fixtures, the standalone API contract drill and its
  scripted guide runtime, API/schema inventories, ownership records,
  structural inventory, current specifications and POL navigation/roadmap.

### Not allowed

- Public action activation, public live approval/correction, provider invocation,
  post-policy approval/projection, new checker execution activation, public guide activation operations/routes/state transitions,
  unrelated AUTH/ART audit cleanup, alternate compilers or compatibility routes.
- Changing finalized setup rows or receipts, weakening tests/gates, deleting
  retained data or embedding private guide material in repository evidence.

## Design and decisions

External-review repair within this boundary: approval must reconcile every
selected pre-submit capability/version with the canonical plan compiled from
the actual merged policy. A valid catalogue binding alone does not prove that
its policy configuration emits a check. Reject an absent selection before
consuming authority or writing approval outputs; preserve unselected platform
defaults. Test the real validator/compiler with empty and configured evidence
and artifact requirements, and prove persisted approval or no-write rejection
in PostgreSQL. Align migration 0019's review-package audit permission and current
README/manual wording with `project.guide.manage` and Project-Manager-only
proposal access. Probe duplicate approved chains through direct SQL with valid
custody; add a narrowly scoped database guard only if the probe demonstrates
the missing invariant. This remains L1 authorization/policy work, with security,
architecture, QA/test-delta, CI-integrity and documentation replay before readiness.
Human focus is selected-check enforcement and consistent database authority;
public exposure and unrelated cleanup remain excluded.

The database probe confirmed that suppressing only the current-approval lookup
allowed two fully authorized approved roots for one guide. Add a partial unique
index on immutable approval operations' `guide_id` where their predecessor is
null, with matching SQLAlchemy metadata. Combined with existing predecessor
uniqueness, this permits one root and one successor per operation. Keep policy
lifecycle sequencing and retained superseded chains intact. Prove rejection with
complete new approval custody and a suppressed application lookup, plus normal
corrected-successor and concurrent-approval controls. Update the exact schema
fingerprint only for the reviewed audit-constraint and index changes.
The deferred approval guard must also require a linked predecessor's artifact,
effective and pre-submit policies to be superseded with equal non-null
timestamps. Root/predecessor uniqueness establishes one chain; this lifecycle
check establishes one current approval even if application supersession is
omitted. Prove that omission independently of the duplicate-root case and keep
normal replacement valid. Register new tests in the explicit project lane
catalogue and verify full collection before hosted execution.
The lifecycle invariant is bidirectional: an approval with an immutable
successor must remain superseded. Reject direct-SQL reactivation of all three
predecessor policy rows even when their original approval custody is intact;
the successor must remain the sole current approval after rollback.

1. Expose a bounded exact-compilation package containing validated findings,
   artifact policy, requirements, separate pre/post bindings, suggestions and
   safe notes, with all component/source/catalogue/finalization identities.
2. Reuse the existing PROJECTS policy merge, CHECKERS canonical bundle compiler,
   and CHECKERS `EffectivePreSubmissionPlanningPort` for the ordered effective
   execution plan. Bind both compiled outputs and the exact catalogue to the
   approval operation. ART owns original-document custody, not either compiler.
   Extract shared merge behavior if needed; remove the superseded manual
   approval operation.
3. Record approval separately from setup finalization, atomically with canonical
   artifact/effective/pre-policy lifecycle writes and authorization evidence.
   Bind operation replay to the exact displayed target and fresh authority.
   `SubmissionPolicyMutationIdempotencyRecord` remains the existing reservation
   and replay owner; the immutable approval operation is its committed product
   provenance, not a second idempotency protocol. Effective/pre-policy custody
   must require both that reservation and the exact immutable approval operation.
   Retain manual draft creation custody only for still-supported create/update.
   Approval-aware finalization replay must prove the original draft projection
   digest and the exact authorized lifecycle transition using this provenance;
   coercing arbitrary policy state to draft is not sufficient evidence.
4. Record correction separately, with normalized bounded feedback and one
   successor setup generation. Integrate feedback into the canonical request
   context and hash. Preserve the previous finalized generation byte for byte.
   The successor starts in `correction_requested`, outside automatic upload
   recovery. This distinct state is necessary because every existing queued or
   awaiting-documents state can trigger automatic source consent, which belongs
   only to the initial upload. The existing human compilation-request operation
   later admits this successor, changes it to the canonical queued shape and
   reserves its attempt atomically. Hidden tests supply request authority; live
   dispatch composition remains POL-05B. No automatic-origin alias is added.
5. Default authorization is unavailable. Tests exercise supplied purpose-specific
   authority handles; this does not claim AUTH-12F4 or public GET is live.

## Acceptance criteria

- [x] Complete result is reviewable by exact identity with no provider payload,
  raw guide, storage credentials or replayable document references disclosed.
- [x] Stale/mixed source, generation, result, component, catalogue and policy
  identities fail; every capability gap blocks approval; warnings require exact
  acknowledgment where applicable.
- [x] Mandatory platform checks cannot be weakened, repeated, selected or
  reordered; effective policy and pre-plan match the canonical compiler.
- [x] Default authority denies reads and writes; authorized operation/replay
  remains inside the supplied session/root transaction with no hidden commit.
- [x] PostgreSQL proves atomic approval/provenance, immutable finalization,
  composite ownership, rollback and exact replay.
  `test_unified_approval_postgresql_requires_reservation_and_operation` must
  independently remove each relation from an otherwise valid transaction and
  prove rejection, alongside a successful complete control.
- [x] Correction produces one successor on replay, binds bounded feedback, and
  cannot restart uncertain provider work or mutate previous evidence.
- [x] Removed manual approval callers/tests are replaced with required behavior
  coverage; current API inventory and docs describe the resulting exposure.

## Risk and review routing

- Risk class: L1 (policy lifecycle, authorization seam and immutable evidence).
- Required reviewers: architecture, security, QA, product_ops, reuse_dedup,
  test_delta, documentation; ci_integrity for affected evidence inventories.
- Human review focus: full proposal visibility, clear pre/post distinction,
  correction lineage, no inference during approval, no obsolete approval path.

## Evidence

Focused tests use real PostgreSQL transactions and the canonical compiler.
Named controls cover each independently missing reservation/approval relation,
opaque guide versions, exact warning acknowledgement, immutable projection and
finalization, correction and approval replay, current manager authority, foreign
project grants, full nonempty proposal sections and active-guide exclusion.
Migration tests cover empty roundtrip and refusal with retained approval evidence.
Hosted CI supplies full-suite and coverage evidence; current command results,
review targets and external checks belong to the PR trust summary.

## Reconciliation

- Current-source reconciliation: starts after merged #396 and preserves #397's
  canonical project-role task authorization; the unrelated submission denial
  audit gap remains outside this change.
- Next usable boundary: AUTH-12F4, then POL-05B.
- Remaining dependencies: AUTH-12F4 supplies live exact manager authority;
  POL-05B exposes review/approval/correction and manual dispatch. Post-submit
  policy approval and guide activation retain their separate adopted boundaries.

## Plan review disposition

ARC-POL05A-001: retain the existing reservation/replay owner and require a
separate immutable product provenance relation on all approval outputs, as
specified above. This resolves the ambiguity without another replay subsystem.
The other reviewed corrections assign both compilation stages to CHECKERS,
require approval-aware finalization validation and isolate correction successors
from automatic source consent. Evidence references in the review package must
be display-only source labels/locations; runtime document handles are excluded.
Correction feedback is optional input data, not a new implementation version;
its canonical encoding omits an absent feedback field and binds a present one.
This keeps unchanged semantic inputs unchanged without an old/new runtime path.

## Affected-consumer reconciliation

Shared active-guide reads previously required manual-policy lineage. They now
reuse the exact unified approval and original finalization proof under the
existing guide lock, binding approval/reservation identity into their resource
digest. This changes no activation command, public action or lifecycle authority.
Warning acknowledgments live in the immutable approval receipt; finalized
sufficiency reports are never edited to acknowledge them.

The removed HTTP approval tests are replaced by actual hidden PostgreSQL
operation tests: exact approval/replay, each independently missing custody row,
immutable projected/approved content, same-content corrected-generation
supersession, required predecessor identity, concurrent approvals and current
manager authority. Packaging merge and identical-default deduplication retain
focused tests of their existing canonical owner. The removed route has an
absence assertion; unknown fields remain rejected by current public schemas
and the new strict commands. Invalid artifact fields are now rejected at result
validation with independent defensive projection checks, without old-version
fixtures or a permissive compatibility constructor.

The compilation input resolver is renamed to reflect its shared automatic and
human request responsibility. Its exact ownership partition replacement and
new bounded proposal targets are declared without widening eligibility or
limits. The catalogue contract moves intact to its focused test module and
adds the two planned actions; permission inventory and active actions do not
grow. Model metadata stays in the existing compilation model owner.

The coherent diff spans these shared callers and their tests because removing
manual approval while retaining its fixtures/read assumptions would leave a
broken product path. This is one approval/correction boundary, not an additional
authorization or post-policy implementation chunk.

## Implementation review corrections

- Preserve opaque guide versions in the one effective-plan contract and every
  affected PROJECTS, ART and TASK caller. PostgreSQL approval controls include
  `v0.1` and a nonnumeric version.
- Replace remaining TASK and ART hand-built manual approval prerequisites with
  canonical unified compilation, finalization and approval fixture custody.
- Current exact-project managers may admit a correction created by another
  manager through the existing human request authority. Retain the original
  correction creator's provenance separately from the admitting request.
- Exact approval retries validate retained custody before currentness gates,
  including after correction allocation or supersession; no new outputs or
  authorization events are written by replay.
- Complete proposal prose is guide-derived content, not a DLP-filtered public
  diagnostic. The planned package-read action uses existing Project Manager
  `project.guide.manage` authority. Raw document payloads, runtime/provider
  details, storage handles and replayable references remain excluded. Public
  AUTH-12F4 must enforce current exact-project manager/content authority.
- Extend the existing 90 percent compilation coverage surface to its proposal
  API contracts. Preserve all existing CI thresholds, inventory and isolation
  guards; repair stale migration and route inventories rather than bypassing them.
- Manual draft replacement remains a governed draft operation. It cannot create
  approval evidence; the original reservation guard still proves its successor.

The removed persisted-invalid-path projection case is replaced by the existing
result-boundary invalid-machine-field cases and defensive projection validation
in `test_projection_policy.py`; the blocked-result service case remains. Active
read corruption tests now prove the database rejects altered approved content
or a return to pending, then verify the unchanged active-guide read. Locked
historical-policy tests create actual corrected approvals before activation
instead of hand-writing superseded rows or a parallel effective policy.

Downstream authority prerequisites now reuse canonical bootstrap/grant database
custody, allowing real grant revocation rather than seeding impossible bootstrap
manager rows. Only source-creation and not-yet-live activation prerequisites use
the explicitly bounded existing test fixture; proposal/approval constraints stay
enabled. The active-guide approval guard test stages activation drift in a
rollback-only transaction and forces that exact deferred constraint.

Shared artifact fixtures finish canonical guide setup before minting short-lived
checker-output bytes; existing source leases and retry limits remain unchanged.
Corrected-result fixtures cite every document in the exact manifest, including
multi-document guides. Operator inspection selects the checker output’s exact
originating put attempt rather than the earlier guide-upload record.

The canonical evidence integration exposed a second stale assumption: packet
validation did not recognize the platform-required `artifact_hash_manifest`.
The existing processor already validates that manifest against inspected bytes
before dispatch. Its packet-field mapping must recognize that derived field;
unknown fields still fail closed and manifest-drift tests retain their guards.

The ART evidence integration now uses actual unified approval and selected
review/revision policy mutations at opaque guide version `v0.1`. It no longer
hand-builds manual artifact/effective/pre-policy rows or disables their custody
triggers. Its submitter-grant fixture reuses canonical bootstrap custody.
Existing not-yet-live guide activation remains an explicitly bounded test
prerequisite. Oversized ART test setup is reduced through shared provider
construction, isolated conflicting-row setup and deduplicated binding creation;
assertions, structural limits and coverage floors are preserved.

Shared compilation fixtures now calculate their snapshot digest from the actual
task-example manifest. The evidence repository independently rehashes that
manifest; an arbitrary placeholder could satisfy earlier setup fixtures while
failing the real locked-context consumer.

Downstream TASK submissions and requirements assertions use the canonical
projection's generated artifact/evidence keys, ZIP packaging, and omitted
optional descriptions. Corruption tests do not delete or
rewrite immutable approval outputs: database tests assert rejection, while
consumer tests inject detached invalid repository reads after valid canonical
setup. Hash-consistent consumer probes also supply matching detached task
pointers so an earlier digest mismatch cannot mask shape validation. Queue
repair tests restore the read fault rather than changing retained policy data.
The public OpenAPI inventory removes the obsolete manual approval route, and
migration fixtures use the shared manifest's actual digest.

The standalone API drill must also use full unified worker finalization and the
shared hidden approval fixture. Remove its separate partial sufficiency pipeline
and manual approval calls; reuse the existing post-policy fixture for the
not-yet-live downstream prerequisite. HTTP assertions continue to prove that
approval is not publicly exposed. Run the complete real HTTP drill locally and
in hosted CI; do not replace it with the passing lane suite.
