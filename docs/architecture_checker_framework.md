# Checker Framework

## Purpose

The checker framework protects reviewer time and enforces project rules before human review.

It does not replace reviewers. It blocks structurally broken work and gives reviewers reliable evidence.

## Stage And Execution Method Are Separate

**Pre-submission intake checks** ask whether a prepared package is fit to
submit, including packaging, completeness, integrity, and configured intake
quality. They execute before a Submission exists; blocking failures prevent
its creation. **Post-submission evaluation** asks whether the immutable submitted
work meets the locked task/project checks. It produces durable results for
review eligibility, not a final Review decision. Neither stage's evidence can
stand in for the other.

These stage names do not mean that every checker is deterministic. The current
intake primitives and trusted policy compilers are deterministic mechanisms.
Task-specific post-submit evaluation may use deterministic rules or a supported
model/agent evaluator, such as a quality judge, when its implementation and
policy binding exist. A deterministic compiled policy does not make a model's
judgment deterministic. Evidence must remain attributable to the evaluated
artifact and policy; reproducible inputs do not promise identical judgments.

This describes the distinction, not activation of a runtime agent judge. Only
supported registered checkers execute. Setup agents propose checker policies;
they are not called again as an implicit evaluator of contributor work.

## Checker Result Contract

`ExternalCheckerExecutionRequest` and `ExternalCheckerExecutionResult` are the
normalized versioned contract for the external-checker target. Every request
binds one immutable registry entry and entry digest, the exact configuration
and input hashes, bounded ART-verified read-only material identities, and one
phase-specific owner identity. Pre-submit identity uses the existing prepared
generation, attempt, attempt-request digest and effective-plan hash before a
Submission exists. Post-submit identity uses the immutable Submission,
evaluation request and reservation, plus the current execution lease and its
database expiry.

The normalized result echoes the exact request, registry and phase identity.
It is either `completed`, with closed findings and a passed/failed verdict, or
`infrastructure_failed`, with one of the existing capacity, deadline, material,
implementation or invalid-output codes. Missing images, crashes and malformed
or oversized output cannot become a silent pass. This contract and the
immutable registry are available to later owner operations; no external
launcher, routing path or execution factory is installed yet.

The following catalogue contracts remain the currently executing behavior
until the clean cutover replaces them. They are not alternate external wire
formats.

The following illustrative provenance envelope uses a pre-submission catalogue
`v1` definition; it is not a universal serialized result schema. The
[current post-submit contract](#current-post-submit-contract) uses
`PostSubmitMemberResult` with schema `post_submit_structural_result` and its
separate bounded fields.

Illustrative pre-submission provenance envelope:

```json
{
  "definition": {
    "dispatch_authority": "pre_submission_catalogue",
    "definition_id": "policy.submission_packet.validate",
    "definition_version": "v1",
    "public_name": "check_submission_packet",
    "source": "locked_project_policy"
  },
  "policy_trace": {
    "effective_plan_hash": "sha256:<64 lowercase hex>",
    "rule_instance_id": "sha256:<64 lowercase hex>",
    "locked_policy_hash": "sha256:<64 lowercase hex>"
  },
  "status": "passed",
  "severity": "info",
  "code": "submission_packet_complete",
  "message": "Submission packet is complete.",
  "suggested_fix": null,
  "evidence": [],
  "metadata": {}
}
```

`definition` and `policy_trace` are typed provenance, not arbitrary metadata.
The discriminating `dispatch_authority` gives `definition_id/version` exact
meaning: for `pre_submission_catalogue` they are the stable catalogue
definition ID/version, while the effective plan separately binds the top-level
catalogue ID/version and manifest hash; for `durable_checker_registry` they are
the registered durable checker ID/version.
For Workstream defaults, `source=workstream_default` and policy-only fields may
be null under the closed schema. Serialization preserves this exact nesting.
Persistence uses explicit authority-neutral columns or schema-validated typed
JSON fields for every member; none may be stored only inside open-ended
`metadata`.

Status:

- passed
- warning
- failed

Severity:

- info
- low
- medium
- high
- critical

## External Checker Registry And Current Catalogues

The immutable external registry publishes one capability/version/phase with an
exact OCI `sha256` digest, bounded configuration/input/output JSON Schemas and
CPU, memory, deadline and output ceilings. Publication requires fresh
system-scoped Operator authority over the complete request and entry digests.
Exact replay returns the original row; changed operation or logical-identity
replay fails. PostgreSQL closes the authorization receipt and recomputes every
schema, request and entry digest while denying update, delete and truncate.

Registry metadata grants no policy selection, activation, execution or routing
authority. Consumers read an exact registry ID and digest; there is no
"latest" lookup and no registry-driven Python plugin or callable discovery.
The registry supports both `pre_submit` and `post_submit`, but no external
execution is wired in this foundation.

Until the replacement proof and clean cutover, the single versioned
`PreSubmissionCheckerCatalogue` remains the pre-submit dispatch authority and
the current process-wide post-submit catalogue remains the post-submit dispatch
authority. They do not execute registry entries in parallel.

The current hidden catalogue implementation is process-wide and immutable.
Deployment configuration may name disabled stable definition IDs only at startup. Unknown
or duplicate IDs, invalid dependencies/order, unknown capabilities, and unsafe
disabled behavior fail startup validation. The pure effective-plan compiler
binds project, guide version, source snapshot, effective policy, pre-submit
policy, catalogue manifest, availability state, ordered definition/configuration
hashes, and deterministic rule-instance identities. It does not read artifacts
or invoke either pre-submit or durable checkers.

External registry fields include:

- capability ID and version;
- `pre_submit` or `post_submit` phase;
- exact OCI image digest;
- configuration, phase-input and normalized-result schema IDs, versions,
  documents and hashes;
- CPU, memory, deadline and maximum-output limits;
- complete entry and registration-request digests plus the exact authorization
  decision receipt.

Capability names must not drift between project guides, approved policy
bindings, registry entries and checker results. Later policy work must bind the
exact digest, configuration and schema identities; registration alone changes
no locked task.

## Current post-submit contract

CHECKERS owns one immutable initial-v0.1 catalogue, one implementation per
checker ID, and closed evaluation-request/result contracts. PROJECTS uses that
same catalogue to compile one canonical policy body. Active PROJECTS, TASKS and
CHECKERS consumers validate that body and its exact hash; persisted required,
warning and blocking summaries must agree with it. Unsupported development
bodies reject without translation or an alternate reader.

The eight mandatory structural defaults and the selectable
`check_acceptance_criteria_present` have conformance fixtures. Criteria presence
does not prove that work satisfies the criteria. Unsupported substantive
automation remains a capability gap; an explicitly approved `human_review`
disposition remains valid without a checker binding.

The single policy-context check compares actual Task and Submission locks:
guide version, source snapshot, effective artifact policy, pre-submit bundle,
post-submit policy, review policy and revision policy. It has no economic-policy
prerequisite. Compilation and ContributionPolicy task references are not yet
persisted and are not fabricated as checker inputs. Project ownership remains
checked by the owning services. Structural consistency grants no authorization.

The canonical `policy_hash` binds ordered entries, configuration and exact
catalogue/implementation identities. Domain project policy versions record
changes to project rules; they do not select obsolete software implementations.
ARCH-04C implements hidden phase execution; ARCH-04D2 supplies exact service authority. No public execution route or dispatcher is activated.
POL-04B connects unified guide setup; POL-05B and POL-06B expose separate
pre-submit and post-submit policy approvals.

## Durable execution custody

ARCH-04C extends the existing CheckerRun/CheckerResult aggregate. A caller-owned
coordination transaction reserves the exact request and advances one per-Submission
fence. Global request/phase and submission/phase/generation uniqueness prevent
split attempts. Replay returns the original identity; it cannot restore an old
request as current. Execution claims a PostgreSQL-timed execution lease and releases
all locks and prepared authority before materialization or evaluator work.

The existing in-process post-submit structural-handler registry evaluates exactly
the compiled entries against ART-verified material; it is distinct from the new
external-image metadata registry. Finalization consumes separate action-specific authority,
checks the current fence and unexpired lease, and commits complete ordered closed
members, terminal result and shared-outbox completion together. Expired-lease
recovery retains the attempt; terminal infrastructure failures never restart or
publish a routable result. No generated outputs or provider inference are enabled.
The current-result port checks the exact request inside the caller transaction.

ARCH-04D2 composes real fixed-service materialization, execution and finalization
authority. Each phase obtains fresh AUTH/PREP before feature locks. Materialization
checks the exact current execution lease and revalidates its original receipt after
I/O. Execute/finalize receipts are bound to the persisted phase facts by PostgreSQL;
terminal replay validates both original receipts without appending new evidence.
No new Celery task, delivery handler or public execution endpoint exists. ARCH-04E
must recheck currentness when consuming a completion event and apply the locked
ReviewPolicy; CHECKERS never accepts a contribution or mutates TASK state.
Migration 0008 refuses retained checker history before changing schema rather
than inventing request lineage or deleting data.

## Blocking Policy

The current catalogue behavior remains:

- critical- and high-severity `failed` results block human review
- medium-severity `failed` result creates reviewer warning
- low-severity `failed` result creates informational note

Approved machine policies can declare stricter blocking behavior. `SubmissionArtifactPolicy` and generated project `PreSubmitCheckerPolicy` govern pre-submit artifact rules. `PostSubmitCheckerPolicy` governs durable post-submit checker blocking.

Project policy cannot weaken Workstream default submission artifact rules. Workstream defaults are applied before project policy. A project policy that attempts to require a forbidden artifact, remove hash requirements, allow credential-bearing storage references, or downgrade blocking defaults is a project setup defect.

The clean-cutover target has one versioned Workstream default checker with
exactly four blocking behaviors:

1. safely open exactly one ZIP within platform size limits, rejecting
   encryption, symbolic links, special files and traversal paths;
2. compute the received SHA-256 in Workstream, verify stored bytes and build
   the file manifest;
3. reject high-confidence private keys, cloud credentials and API tokens; and
4. reject the same files as the preceding attempt unless the task rules changed
   since that attempt.

Missing summary or attestation produces warnings only. Required-file, project
size and forbidden-file rules belong to digest-pinned external project images.
The default checker, ART custody and project images must replace every required
outcome before either current catalogue is removed. Human reviewers continue
to own final quality judgment.

The clean-cutover intake order is fixed. ART receives the ZIP, computes its
SHA-256, verifies the stored bytes, safely opens it within platform limits and
builds the manifest before any external image can read material. The one
Workstream default checker implements all four defaults above; they are not
four independently selectable catalogue entries. Every required project
pre-submit checker then runs as an exact digest-pinned OCI image against a
bounded, private, read-only view of the verified files. Only after the default
checker and every required project checker pass may one caller-owned
transaction create the immutable Submission, persist `evaluation_pending` and
commit initial dispatch. Work findings return without creating a Submission
and leave the task `in_progress`. Infrastructure failure stays distinct and
recoverable and does not count as a contributor failed attempt. Required
post-submit images run only from the committed Submission/evaluation custody.
External image execution never occurs inside that database transaction. A
valid locked policy with no project pre-submit bindings is distinct from an
unavailable required image and may proceed after the default checker passes.

The target launcher and checker integration use the agreed Rust service and
SDK. Registered OCI images are not thereby required to be written in Rust;
their execution identity is the approved digest, schemas and resource limits.
The hidden runtime mechanism now supplies the strict Rust SDK and long-lived
service plus an unselected typed Python Unix-socket adapter. ART can issue one
opaque request-bound grant only inside the existing pre-admission prepared-ZIP
callback; the service independently verifies its sealed file/directory manifest
and exact private-root location before a read-only mount. The service accepts
only an administrator-cached OCI platform manifest whose repository, platform
and config image ID all match, and owns no-network, non-root, capability-free,
read-only sandbox launch, bounded output/deadline handling and cleanup. Hosted
readiness requires `runsc`; local `runc` is reported as `docker-dev`.

This hidden mechanism is not selected by either current catalogue and stores no
run state. Policy binding, caller-owned phase authority/currentness, durable
attempt and isolation receipts, the one default checker, project-image routing,
F-020 and public intake remain required before cutover.
The replacement must remove both current pre- and post-submit catalogues after
end-to-end replacement proof. It must not retain a legacy/new parallel path,
weaken caller-owned atomicity or bypass phase identity and currentness checks.

## Current Required Core Checkers Pending Removal

The names below describe the current catalogue pending replacement; they do
not expand the four future Workstream defaults.

### check_policy_context_present

Ensures the task has locked guide, checker, review, and revision policy context.
Award eligibility is locked on TaskAssignment for the attempt, stamped on the
immutable Submission, and copied from that Submission to ReviewLease. It is not
checker-policy context.

### check_submission_packet

Ensures submission has summary, output reference, and package/evidence where required.

### check_evidence_present

Ensures accepted work can be audited.

### check_evidence_integrity

Ensures the submission packet records content hashes for uploaded artifacts and that checker runs use those exact hashes.

### check_acceptance_criteria_present

Ensures a task has rubric or acceptance criteria.

### check_required_files

Validates required submission artifacts from the locked project pre-submit
checker policy.

### check_forbidden_files

Blocks known forbidden artifacts, secrets, private keys, copied internal data, or artifacts forbidden by the locked project pre-submit checker policy.

Default forbidden patterns include:

- private keys
- API tokens
- `.env`
- copied confidential client/source files
- generated low-quality helper artifacts banned by project submission artifact policy
- files not allowed in the submission packet

### check_confidentiality_attestation

Ensures the contributor explicitly attests that the submission does not contain prohibited client data, private source material, credentials, or copied platform artifacts.

### check_low_quality_generated_artifacts

Flags repeated low-quality generated patterns banned by project submission artifact policy, such as generic helper files, hidden-test leakage patterns, fabricated model files, placeholder evidence, or boilerplate reports that do not prove task-specific work.

This mandatory default emits a medium-severity warning for placeholder signals.
It cannot be removed or reclassified as a project-selected entry. Project
blocking severities govern whether that warning requires contributor revision;
only `check_acceptance_criteria_present` is selectable.

Revision closure, task lifecycle movement, task readiness, and pre-review routing are enforced as lifecycle guards in v0.1. They must not be configured as checker policy names until a registered checker exists for that contract.

The pre-review gate is a checker execution phase. The persisted task status during this phase is `evaluation_pending`.

## Gate Mapping

Project activation gate:

- `check_policy_context_present`
- project-specific guide completeness checks

Task screening gate:

- `check_policy_context_present`
- `check_acceptance_criteria_present`
- task lifecycle transition guards

Submission quality gate:

- `check_submission_packet`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

Pre-review gate phase:

- project-configured registered checkers run against the locked submission and policy context

## Submission Artifact Policy And Pre-Submit Generation

Pre-submit intake is generated from policy. It is not manually supplied by the contributor.

The deterministic chain is:

```text
ProjectGuide
-> GuideSourceSnapshot
-> GuideSufficiencyReport
-> SubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> trusted Workstream checker compiler
-> PreSubmitCheckerPolicy
-> pre-submit intake checks
-> Submission row only when blocking checks pass
```

`ProjectGuide` is open-ended human-facing project material. Workstream first
persists a `GuideSufficiencyReport`. Blocking guide gaps stop activation and
create clarification requests for the project owner. Warnings require
acknowledgement by an authorized covered Project Manager.

`SubmissionArtifactPolicy` is machine-readable, derived by Workstream from
project guide material after sufficiency passes or passes with warnings, and
approved by an authorized covered Project Manager after
any warnings are acknowledged.
The project owner does not approve this internal policy. Workstream combines
that policy with the non-bypassable Workstream default submission artifact
policy.

Workstream default submission artifact rules require:

- summary
- one outer ZIP whose exact identity and semantic manifest are generated by ART
- contributor attestation
- safe relative artifact paths
- production artifact hashes shaped as `sha256:<64 lowercase hex>`
- pre-cutover only: validated caller-supplied storage references and manifest;
  the superseded `WS-ART-001-05B` contract is implemented by
  `WS-ARCH-001-02I` for the broader Submission caller cutover, including its
  internal Submission guard and the caller-owned `package_uri`,
  `package_hash`, and `artifact_hash_manifest` fields together so checkers
  consume Workstream artifact bindings only; the transitional `artifact_hash`
  column is handled separately by a schema-removal migration after every
  reader uses exact binding/content identity. POL-07B removes the standalone
  caller-owned JSON precheck and connects the internal checker phase service
- no credentials, signed URLs, query strings, raw local filesystem paths, or token-bearing references
- narrowly high-confidence sensitive-file exclusions such as `.env`, `.git`,
  exact known credential/private-key files, `.pem`, and `.key`; broad
  `token*`, `secret*`, `credential*`, and dependency-directory matches are
  advisory or locked project-specific unless an exact generic custody risk is
  proven

The hidden pre-submit executor consumes one exact effective plan under ART
scratch custody. It validates the commitment, inspection, semantic manifest and
change-gate facts and returns bounded entry results. ART owns the immutable
pre-submit evidence; these results are separate from post-submit CheckerRuns.

POL-07B composes exactly two internal commands, `evaluate_pre_submission` and
`evaluate_post_submission`. Hidden preparation calls the pre command once after
reservation commits, including completed replay. The composition passes the
same opaque reservation to the same ART evidence owner; it clears the consumed
prepared authorization and opens no transaction before ART's existing executor
obtains fresh authority. Replay returns ART's canonical result unchanged.

The post command validates and delegates CHECKER's closed value contract.
Production composes the canonical executor with separate exact execute and
finalize authority through AUTH/PREP. ARCH-04C reserves the exact request, fences execution attempts and
atomically persists complete closed member results and a completion event; it
does not activate automatic request delivery. ARCH-04B supplies the hidden ART input port: exact consumed
Submission bytes, rebuilt manifest, async scoped file access and cleanup, followed
by a fresh material-selection check. ARCH-04D2 supplies fresh fixed-service materialization authority before and after I/O.
ARCH-04B2 now supplies hidden typed output storage, byte-free recovery and
flush-only verified binding. The CHECKERS reservation reader now verifies the
exact current request/run/lease and returns zero slots; ART authority remains
deny-only. Controlled nonempty slots prove ART mechanics only. ARCH-04C supports
that exact empty output set and owns durable execution. ARCH-04D2 supplies input,
execute and finalize authority; ARCH-04E routing remains pending. A returned evaluation value is not a stored
current result or acceptance.
Retained run and submission history now use canonical AUTH and separate fixed
contributor/manager projections. The alternate execution service and Celery worker are
removed; the facade neither wraps them nor adds another policy compiler.

POL-07A commits an ART attempt reservation after bounded ZIP inspection and
before invoking any checker. Only the original request can consume the winning
claim. The fixed materializer consumes fresh authorization for inspected custody
and obtains another transaction-bound authorization before execution. Evidence
and attempt completion commit together after a fresh locked-context check.
The context, reservation, execution, and completion transactions acquire TASK
locks, contributor profile/link locks, PROJECT context locks, then the submitter
role-grant lock. Where needed, fixed-materializer AUTH follows, then attempt/
evidence locks. This matches TASK command ordering and project-role issuance
and revocation. Role issuance locks eligible human targets before PROJECT;
non-human targets cannot take a service-principal lock through that operation. The ZIP inspection
and reservation transaction takes context and authority locks before inspecting
the archive, and records the reservation only after inspection. It follows the
same lock order as execution, so concurrent tasks in one project cannot invert
the shared materializer lock.
The evidence captures a separate hash of the packet actually passed to the winning
invocation; the database compares it with the attempt's requested packet.

An exact completed retry verifies its uploaded bytes and manifest, revalidates
contributor and fixed-service authority, and reconstructs the original result
from canonical evidence, including member metadata and definition order. It
invokes no checker and receives no new pass capability. An existing durable put
receipt may continue recovery; absent or corrupt evidence/continuation is an
infrastructure failure. A stale admission is reported stale, and a consumed
admission conflicts; neither returns an admission ID for reuse. A reservation
without committed completion remains unavailable under the same key, including
a crash after checker return. A new authorized attempt requires a new key.
Retained evidence is not rewritten or assigned invented attempt metadata.

Project policy adds required artifacts, evidence requirements, stricter forbidden artifacts, stricter packaging rules, and project-specific attestation requirements.

The generated project `PreSubmitCheckerPolicy` is persisted with a compiled
bundle hash and locked to the effective project submission artifact policy before tasks enter the
contributor pipeline. Tasks lock references to the shared project's compiled checker
bundle hash. It runs inside continuous submission-bundle preparation before
Workstream creates a submission. ART retains bounded status, eligibility and
pass/fail/warning results. The existing hidden route returns only the code
`pre_submission_checker_failed`; structured public intake feedback remains
pending. The standalone JSON precheck and its exclusive implementation are removed
by POL-07B. Broader
Submission caller migration remains WS-ARCH-001-02I; this result is not a review decision value.
Pre-submit results do not create durable `CheckerRun` records, do not move a
task to `review_pending`, and do not return review decision values: `accept`,
`needs_revision`, or `reject`.

The unified `ProjectGuideCompilationAgent` proposes the artifact-intake
contract alongside sufficiency and both checker-stage bindings in one result.
It does not produce unrestricted checker code. Workstream's trusted
checker compiler builds and validates the project checker specification during
setup, then persists deterministic project-level checker logic using approved
primitives such as:

- `validate_submission_packet`
- `enforce_storage_scheme`
- `require_manifest_field`
- `verify_hash`
- `require_file`
- `require_minimum_evidence`
- `forbid_artifact`
- `require_attestation`
- `limit_file_size`
- `limit_package_size`
- `limit_archive_size`
- `limit_archive_entries`
- `require_packaging`
- `warn_low_quality_generated_artifact`

`limit_package_size` evaluates total expanded bytes from ART's verified manifest,
not compressed upload size. `limit_archive_size` separately evaluates the entire
compressed ZIP's verified `ArtifactCommitment.byte_count`, including archive
metadata, not the sum of compressed member sizes. It is an optional strict
positive byte limit; null adds no project limit. `limit_archive_entries` evaluates that manifest's
normalized outer ZIP entry count, including explicit and implied parent
directories. Omitting a ZIP directory record cannot evade this limit. Nested archives count as
files; this rule does not recursively unpack them. Project count is an optional
strict positive integer; null adds no project limit. All three rules preserve ART's
independent platform safety ceilings and block intake through the existing
effective-plan result, without creating acceptance or exposing hidden routes.

`warn_low_quality_generated_artifact` is warning-only. The trusted compiler
rejects checker specifications that escalate that primitive to blocking.

Project-specific executable checker code is a future extension path, not the
default. That extension path must require static validation, generated tests,
sandboxed execution, no network, no shell, no secrets, no database access,
covered Project Manager approval of the exact code hash after those checks
pass, and a locked code hash.

Pre-submit checks are authoritative for intake. Post-submit runs supply the
current evaluation evidence for TASK's locked-policy routing, not acceptance
authority. TASK admits human review on true or invokes shared acceptance on
false after the required evidence and authority checks.

## Post-Submit Policy Projection

The unified compilation already contains the post-submit proposal before the
Project Manager approves the artifact/pre-submit chain. Approval creates the
effective intake policy and compiled pre-submit policy; a separate operation
then deterministically projects the same result's post-submit component. It
does not resume finalized setup or invoke `PostSubmitCheckerPolicyDerivationAgent`.

Bindings select only implemented definitions/configurations from the exact
CHECKERS-owned catalogue snapshot and trace to the guide's requirement inventory.
All pre/post capability gaps block under the current compilation schema.
Ordinary warnings may be acknowledged; unsupported automation cannot be silently
reclassified as human review. Explicit approved `human_review` requirements
remain valid and do not claim automated semantic coverage.
They require `human_review_required=true`: false guide activation and final
acceptance both reject any applicable approved `human_review` disposition.
Passing every executable check cannot discharge that separate requirement.

The unified output is a constrained proposal. Workstream's trusted compiler owns the
canonical `PostSubmitCheckerPolicy.policy_body`, hash, default checker list,
and execution order. Runtime checker execution loads the locked compiled
policy; it does not call the setup derivation agent to judge a contributor
submission. A model-based runtime evaluator would be a separate supported,
registered checker, not an automatic consequence of this setup flow.

The compiled project `PostSubmitCheckerPolicy` is persisted with exact setup
provenance: guide id, source snapshot id/hash, effective project policy id/hash,
and pre-submit checker policy id/hash. A corrected submission artifact policy
approval establishes the new upstream provenance. The subsequent post-submit
derive operation creates the compiled policy under that provenance and
supersedes any still-current prior policy while retaining its evidence; correction
may already have superseded it. Workstream must not reuse a policy or correction
request that only happens to match the same project id and guide version.

The first two gates replace external origin qualification and task ingestion for v0.1. Origin qualification and webhook drop notifications are future adapter concerns.

## Project-Specific Checkers

Each project can register specialized checkers.

Examples:

- code task package checker
- rubric formatting checker
- document citation checker
- data annotation completeness checker
- security artifact checker
- plagiarism or originality checker
- hidden-test packaging checker
- no-confidential-source-data checker
- reviewer-simulation checker for first-of-kind or high-value tasks
- reviewer simulation gate
- prior feedback checklist checker

## Post-Submit Compiler Boundary

`PostSubmitCheckerPolicy` is produced by Workstream's trusted post-submit
compiler from a constrained specification. The compiler owns the canonical
runtime body and hash. Setup agents may propose registered checker names and
routing classifications, but they do not produce executable runtime code and
they do not decide submission outcomes at runtime.

The compiler always includes the platform default durable checkers in
`default_checkers` and `execution_checkers`:

- `check_submission_packet`
- `check_policy_context_present`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

Default-only projects are valid. The single compiled body stores ordered
entries; default, required, warning and execution lists are derived from them.
Project selections cannot remove, rename, reorder or reclassify mandatory
defaults. Only registered selectable entries may be added. Unknown or
conflicting selections reject before persistence.

Platform blocking severities are `critical` and `high`. Project policy may add
stricter blocking severities, but it cannot remove those platform blocking
severities.

## Checker Run Flow — Target Contract

The following is the intended end-to-end lifecycle. Pre-submit intake and
retained-history reads are implemented. Hidden durable post-submit execution is
implemented with ARCH-04D2 exact service authority. ARCH-04E1B-B7 adds a hidden
request handler that verifies committed outbox invocation, recovers B6's exact
request and fences both execution and terminal replay/publication. It remains
unregistered; automatic delivery and result routing are unavailable. Known missing or corrupt input after ART authorization records a
terminal infrastructure failure only after cleanup and fresh finalization
authorization; it does not route the task. Exact replay does not reread storage.
Denied material access and unexpected failures remain nonterminal. ARCH-04F adds
contributor-correctable remediation and gates public intake and enabling the
false-policy acceptance path; the true `allow_review` route may ship before
ARCH-04F. ARCH-04B hidden input and ARCH-04B2 hidden output custody are delivered
with output-file authority unavailable; exact input authority is implemented. The flow below is not a claim
that those jobs or transitions are live.

```text
Draft packet
-> load locked task context
-> load locked EffectiveProjectSubmissionArtifactPolicy hash
-> load locked PreSubmitCheckerPolicy compiled bundle hash
-> run pre-submit intake checks
-> create Submission only when blocking pre-submit checks pass
-> automatically lock submission
-> queue automatic pre-review CheckerRun
-> validate locked PostSubmitCheckerPolicy id/version/hash/body
-> execute locked PostSubmitCheckerPolicy execution_checkers
-> store CheckerResult records
-> calculate blocking status
-> commit final CheckerRun result/recommendation, required verified output bindings and completion event
-> TASK consumes the current result: publish allow_review manifest/current pointer and review_pending atomically when eligible
-> TASK's later checker-remediation boundary projects contributor-fixable failures as needs_revision with outcome_source = auto_checker
-> project/setup faults remain internal task_setup_blocked, never contributor blame
-> if checker infrastructure fails: keep in checker retry handling
```

The checker run must bind to one immutable submission version. If the contributor uploads a replacement file, the platform creates a new submission version and reruns checks.

`evaluation_pending` is the persisted state while post-submit checker execution
or infrastructure retry is active. After checker results, immutable output/log
artifact bindings, and completion facts commit atomically, the TASK-owned
handler performs the routes above through its own transaction and authority:
passing work moves to `review_pending`, while
contributor-fixable blocking failures may move to `needs_revision` with
`outcome_source = auto_checker`. Artifact-storage cutover changes how exact
bytes and checker outputs are persisted; it does not redesign these routes.

ARCH-04C owns CHECKERS result/currentness and its completion event, not TASK
mutations. ARCH-04E owns the current `allow_review` manifest and TASK transition;
ARCH-04F owns contributor-readable non-allow remediation before public cutover.
The direct CHECKERS-to-TASK mutation, fabricated system actor and alternate
Celery gate are removed. Hidden durable execution and exact service authority are implemented; automatic
routing remains unregistered. ARCH-04E2-B supplies the hidden authorized
outcome operation; completion delivery and live composition remain pending.

`review_pending` marks readiness for the separately owned WS-REV lifecycle.
WS-REV alone creates `ReviewPacketManifest`, review queues, reviewer leases,
assignments, and review decisions. Checker completion facts and general
`ArtifactBinding` records are inputs to that later boundary, not review records.

Checker failures are not human review decisions. They do not `accept` or `reject` work. Contributor-fixable blocking failures can route the task to user-facing `needs_revision`, with `outcome_source = auto_checker` and no review decision id. Human review can also produce `needs_revision` later, but that records `outcome_source = human_review` and a review decision id.

If a checker crashes or cannot run because of platform infrastructure, the
checker run remains failed as an infrastructure failure and the task does not
move to human review. The planned retry contract requires Operator
`operations.checker.retry`, a reason, a new attempt/supersession record, and
append-only audit evidence. That action is currently unavailable; no public
retry or repair route survives the alternate execution removal.

This terminal retry is distinct from transport redelivery or recovery of an
unfinished provider call. In-flight recovery retains its logical attempt and
provider idempotency identity; it cannot turn a terminal failed run back into
an unfinished one. A new authorized terminal retry preserves prior evidence
and supersedes it through the coordinated currentness protocol, never by
replaying an old success or bypassing the Operator boundary.

If a checker finds missing locked guide or policy context, missing acceptance
criteria, or another task setup defect that is not contributor-fixable, the run uses
`task_setup_blocked`. That route is internal to covered Project Managers and
authorized Operators and must not be shown to contributors as a revision request.

## Readiness Proof — Target Contract

Canonical readiness publication is pending. Its required contract stores proof
on the current checker run when all blocking checks pass.

The checker run records:

- submission id
- post-submit checker policy id, version, hash, and internal locked body
  stamped from the locked submission context
- exact ArtifactBinding/ArtifactContent and server-generated manifest identity
- blocking failure count
- warning count
- completion timestamp

ARCH-04B input, ARCH-04B2 output custody and ARCH-04C result custody are
delivered, together with ARCH-04D2 exact service authority. Reviewers will receive
readiness proof after ARCH-04E routing integration. That proof must identify the same immutable binding
and manifest that passed automated checks; caller-owned manifest fields are not
authority.

[ARCH-04D1](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04D1.md)
adds canonical database custody through ART's scalar lineage contract. Every
terminal run retaining material must match the exact consumed admission,
Submission binding/content, verified replica and semantic manifest, including
infrastructure failures after materialization. Migration 0009 preserves valid
retained history and refuses unprovable rows without rewriting or deleting them.
Current replica health is separate from immutable evidence identity. ARCH-04D2
supplies exact service authority; migration 0010 binds execute/finalize receipts to
the exact run, request, lease, result and retained material. It refuses unprovable
retained receipts without rewriting or deleting evidence.

A separate `ReadinessCertificate` record may be added later if reviewer routing needs a dedicated signed handoff object. v0.1 does not require that extra record.

## Checker Output Visibility

Contributors see:

- failed checker name
- severity
- message
- suggested fix when safe

Contributor-facing checker-run responses do not expose `routing_recommendation`,
`outcome_source`, internal route tokens, post-submit policy provenance fields,
locked post-submit policy body, or hidden task setup details.

ARCH-04C retains closed, ordered post-submit checker identity and implementation
version, status, code, failure category, severity and the bounded counter fields
of `PostSubmitMemberResult`. It also retains exact request/result generation and
digests, locked policy lineage and verified material custody. Current structural
handlers emit empty counters. Explanations and suggested fixes in history are
derived deterministically from the closed code; raw handler messages and arbitrary
metadata are not retained.

This is retained proof, not a live reviewer projection. Current contributor and
Project Manager history reads expose only their fixed, permission-appropriate
DTO fields. Future REV packet/current-work presentation must expose an authorized
bounded subset after routing and review integration. The current contract does
not include per-file findings, per-check evidence references, full logs or generated
output artifacts. For example, a missing-required-file code identifies the failed
rule but does not retain which path was missing or a missing-file counter.

Reviewer file inspection belongs to the planned lease-scoped ART capability bound
to the exact `ReviewPacketManifest` and active `ReviewLease`; see
[reviewer packet access](spec_review_lifecycle.md#review-packet-and-artifact-boundary).
CHECKERS history does not grant artifact access. A reviewer uses the exact immutable
Submission and locked context, with checker results as bounded provenance.

A richer finding such as a path, location, excerpt, evidence reference or generated
output needs a typed capability-specific result/evidence schema, visibility rules,
immutable custody and regression tests before the reviewer contract may promise
it. This does not introduce a generic metadata store or another checker path.
Future Operator and Audit projections likewise require their own authorized fields;
ARCH-04C adds neither full-log reads nor retry/repair controls.

## Recovery, Not Checker Override

`operations.submission_gate.repair` and `operations.checker.retry` are planned,
unavailable actions. The following describes their required future authority
and evidence contract, not existing callable recovery routes.

Critical- and high-severity checker failures cannot be converted into review
readiness by an administrative grant. A covered Project Manager may repair task
setup under `project.task.manage`. Future Operator submission-gate repair and
checker retry must be limited to the registered recovery purpose once their
canonical owner implementation and AUTH activation are delivered.

Recovery requires:

- reason
- actor
- timestamp
- exact project/task/submission/checker resource
- matched grant and permission
- evidence

Recovery cannot delete checker results, mutate an immutable submission, create
a human review decision, or bypass a blocking content failure. It creates a new
audited repair/retry attempt while preserving prior evidence.

## Checker Quality Metrics

Track:

- false positive rate
- false negative rate
- most common failures
- checks that reviewers repeatedly ignore
- checks that predict rejection

Checker quality is reviewed using recorded outcomes. A repeated reviewer finding becomes one of:

- a new checker
- a stronger project guide rule
- a template update
- a reviewer training note
- a ProjectLesson record for operating review

## Checker Blind-Spot Review

Every week, compare accepted submissions, rejected submissions, and needs-revision findings against checker output.

Look for:

- reviewer findings that no checker predicted
- checker warnings reviewers always ignore
- repeated infrastructure retry/repair patterns or attempts to bypass blocking
  checker failures
- evidence that passed structurally but did not prove the claim
- generated or copied artifacts that evade forbidden-file rules

Each blind spot becomes a guide update, checker update, reviewer policy update,
revision policy update, contribution policy update, template update, or
reviewer-training change.

## First Implementation

The first checker runner can be simple:

- async-first execution
- authorized checker trigger that records a run before execution
- markdown/json output
- attached logs

The checker interface is async-first from the start so storage reads, external
checks, and later agent evaluation do not require a contract rewrite.

Background checker execution uses Celery. FastAPI background tasks are not the
Workstream product-job boundary. Request-bound pre-submit evaluation can remain
fast and deterministic because it runs before submission creation, but any
long-running setup or post-submit checker work must go through the durable
worker boundary.

### Saved guide proposal to post-submit policy

POL-06A projects validated bindings from the saved unified guide result through
this canonical compiler. Shared identical bindings emit one required checker;
all requirement references remain in the saved proposal. Platform defaults are
inserted once. The complete policy body and its canonical hash are the reviewable
draft; separate operation receipts bind its source and approved upstream chain.
Approval cannot supply a replacement body. Correction creates the existing
unified successor, preserving the original result and policy evidence.

POL-06B exposes these operations under AUTH-12G: only the fixed setup
service derives, and exact-project managers read, approve or correct. Committed
pre-submission approval schedules derivation; an approval-ID recovery scan
republishes missing derivations in bounded pages. Derivation supersedes any
still-current prior policy. The proposal read identifies its exact derived
policy, whose complete body is separately reviewed and approved. Projection and approval neither
open guide documents nor invoke a model or runtime checker. Supported structural
checks do not establish substantive work quality, and capability suggestions do
not register implementations or bypass required gaps.


## Retained history reads

Application composition first resolves immutable Submission ownership through
TASK's typed public read port, then queries CHECKERS through its typed read port.
Detail routes include the parent Submission; CHECKERS selects fixed columns using
the exact run, Submission and task together. Contributor reads require current
Submitter authority for the original Submission contributor, not today's assignee.
Separate Project Manager reads expose internal result summaries and locked lineage,
without raw metadata, provider locations, token claims or obsolete payment fields.
Hidden result rows and internal-only routing results are never returned to contributors.
No manual execution endpoint accompanies these reads. See the
[TASK history contract](spec_chunk_4_task_queue_assignment.md#retained-submission-and-checker-history).


### Shared evaluation content capacity

ARCH-04E1B-B5 provides `PostSubmissionEvaluationContent` for both preparation and
later identified requests. It enforces the existing locked catalogue, policy
consistency and structural field limits, plus 1 MiB minus a 1,024-byte reserve
for the finite request identity envelope. The full request retains its 1 MiB
limit and canonical digest. Catalogue and policy identities are unchanged.

The typed adapter projects every verified file and only required evidence with
matching verified `evidence/{key}` files. Missing criteria remain empty text for
the existing post-submit checker. This check does not execute evaluators or
supply authority. See [the ART admission boundary](spec_artifact_storage_service.md#evaluation-content-capacity-before-durable-admission)
for timing and cleanup. ARCH-04E1B-B6 reuses this projection with actual record
identities and reserves generation one through the required TASK guard in the
Submission transaction. The same commit retains exact creation/binding AUTH
receipts and a bounded `PostSubmissionEvaluationRequested` outbox event.
Select-only creation replay checks the original request and event without
changing the current-generation fence. Request/completion handlers remain
unregistered; this stored intent alone does not invoke checker execution or accept work.
Preparation has no stored Submission to observe and never replaces the TASK
evaluation guard.
