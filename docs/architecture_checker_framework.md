# Checker Framework

## Purpose

The checker framework protects reviewer time and enforces project rules before human review.

It does not replace reviewers. It blocks structurally broken work and gives reviewers reliable evidence.

## Stage And Execution Method Are Separate

**Pre-submission intake checks** run before a Submission exists; blocking
failures prevent its creation. Static inspection and other checks that can
reliably finish within 60 seconds belong here, including project-specific
package, completeness, integrity and bounded quality checks. PRE execution may
still use durable work and polling; the stage does not promise synchronous HTTP
completion. **Post-submission evaluation** runs after the immutable Submission
exists. Longer execution, repeated trials and model evaluation belong in this
background stage and produce durable evidence for review eligibility, not a
final Review decision. Automation alone does not make a check POST. Neither
stage's evidence can stand in for the other.

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

The normalized `external_checker_result.v1` echoes the exact request, registry
and phase identity. It is either `completed`, with closed findings and a
passed/failed verdict, or `infrastructure_failed`, with one of the existing
capacity, deadline, material, implementation or invalid-output codes. Each
finding names the `check_id` that produced it, a closed `code`, a level
(`info`, `warning`, `error` or `coverage_incomplete`), a message and an
optional `path` with an optional 1-based `line` inside that path. The verdict
is `failed` exactly when an `error` finding exists; `coverage_incomplete`
reports work the checker could not evaluate and never fails the verdict by
itself. Missing images, crashes and malformed
or oversized output cannot become a silent pass. This contract and the
immutable registry are consumed by selected hidden PRE/POST owners through an
explicit Rust service adapter. Production request/completion handlers are
registered; ARCH-02I-B exposes public contributor ZIP preparation and
admission-backed initial/checker-remediation Submission creation. The bounded
local public API and Celery service drill starts from public guide inputs with recorded inference.

Both executable catalogues, their runtime factories and their request/result
decoders are removed. Requests use the default-plus-external PRE contract and
external POST contract. Stored predecessor rows retain their original provenance
and business-version digests; they do not supply an alternate execution path.

## External Checker Registry And Selected Policies

The immutable external registry publishes one capability/version/phase with an
exact OCI `sha256` digest, bounded configuration/input/output JSON Schemas and
CPU, memory, deadline and output ceilings. Publication requires fresh
system-scoped Operator authority over the complete request and entry digests.
Exact replay returns the original row; changed operation or logical-identity
replay fails. PostgreSQL closes the authorization receipt and recomputes every
schema, request and entry digest while denying update, delete and truncate.

The supported bearer-authenticated Operator API accepts the canonical
specification and an `Idempotency-Key`, selects the registry UUIDv7 on the
server, and returns the complete immutable entry. Exact-ID readback requires a
fresh system Operator decision and discloses no row after grant or identity-link
revocation. Registration and readback do not expose REV lifecycle transitions
or activate the registered image.

Registry metadata grants no policy selection, activation, execution or routing
authority. Consumers read an exact registry ID and digest; there is no
"latest" lookup and no registry-driven Python plugin or callable discovery.
The registry supports both `pre_submit` and `post_submit`. Registration alone
grants no execution; selected owners execute only exact approved image bindings
with fresh phase authority and ART-verified material.

Guide setup classifies a check from its complete work and execution budget, not
from whether the guide says automated, PRE or POST. A newly proposed PRE binding
must fit the `bounded_pre_submit` mode, propose at most 60 seconds and select a
registry entry whose deadline does not exceed that boundary. Longer work uses
the background POST stage. A cheap automated structural check stays PRE.
Static means a deterministic predicate over explicit syntax or a guide-defined
grammar. Free-form completeness and consistency judgments belong to model-based
POST evaluation; setup must not invent document headings or keywords to force
them into PRE.

Setup checks aggregate capacity separately for PRE and POST, including the PRE
default or POST materialization and per-entry cleanup. A proposed policy that cannot
fit must expose an `execution_capacity` runtime gap with a `capacity_exceeded`
infrastructure outcome; supported bindings cannot exceed the actual aggregate
deadline. A stage that fits must not claim a capacity gap. This does not increase
runtime capacity. Ordinary checker-image isolation does not supply nested task
environments. A POST requirement may claim that support only when its exact
binding selects the typed generic isolated-trial profile described below and
every required material and runtime dependency is present.

The trusted compiler binds approved requirement identities to exact immutable
registry entries, image/configuration/schema digests and ordered PRE/POST
policies. PRE includes the single versioned Workstream default. No executable
pre-submit or post-submit catalogue remains, and no registry-driven Python
implementation discovery is allowed. Retained catalogue identities remain
immutable provenance for earlier records; they do not select new execution.

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
bindings, registry entries and checker results. Approved policies bind the
exact digest, configuration and schema identities; registration alone changes
no locked task or approved guide generation.

## Post-submit contract

POST requests carry the task's locked `LockedExternalPostSubmitPolicy` and the
exact immutable Submission/ART identity. One request/result contract drives
reservation, execution, completion and recovery. Every approved digest-pinned
image receives verified read-only material; its normalized findings and observed
isolation become immutable evidence for the existing routing owner.

Policies bind exact registry entries, image digests, configuration and schema
hashes. TASK and ART validate the locked guide, source, policy, assignment,
predecessor and material context before admission or evaluation. Checker results
supply work evidence and do not grant acceptance authority. Passing required
POST checks routes through the existing human-review or shared final-acceptance
branch selected by the locked ReviewPolicy.

A POST binding can explicitly select revision context using the flat approved
configuration pair `workstream_evaluation_context_version: "v1"` and
`workstream_evaluation_context_roles`. The latter is a sorted, unique list drawn
from `predecessor_findings` and `predecessor_submission_archive`. Both properties
must be declared by the immutable registry configuration schema; permissive
additional properties do not grant the capability. PRE cannot select it.
Absent selection means current Submission material only.

Selected images receive a typed `input.evaluation_context` with `kind`, `source`,
`predecessor` and `feedback`. An initial attempt has null source, predecessor and
feedback, even when its global Submission version exceeds one after reclaim.
A checker revision binds the preparation actually consumed by that Submission,
the exact previous Submission from the same assignment/contributor, and the
immutable checker completion that requested the revision. It never follows a
latest preparation or today's policy. Kept and rebased contexts use the same
owner read; neither alters old attempts. Feedback is complete normalized member
evidence, bounded at 512 KiB; excess or inconsistent evidence fails closed.
Contributor identities and provider locations are not included in image context.

ART reads these facts under current materialization authority, verifies each
selected archive's bytes and semantic manifest, and projects the files once into
one quota-owned private workspace. Each binding receives its own temporary
request-bound v2 grant. The current role mounts read-only at `/work/input`; an
explicitly selected predecessor role mounts read-only at
`/work/context/predecessor`. A current-only binding in the same aggregate cannot
see that prior role. Publishing or revoking a grant does not move the files, so
later selected bindings reuse the verified trees. Combined expanded bytes and
entries remain subject to the existing ceilings; adding a prior archive does
not double them. All views and grants close before replay validation or result
publication.

Context-enabled member results retain the configuration hash, actual input hash,
context hash and visible material identities. Current-only results omit this
unselected receipt, preserving immutable historical result hashes. This extends
the one selected execution contract; it creates no second executor or authority.
The parent run retains `input_context_custody`: the exact context and any selected
predecessor verification chain. PostgreSQL reconstructs its consumed preparation,
same-assignment predecessor and normalized historical findings, and includes the
extension in materialization and finalization authority digests. Missing or
substituted custody cannot commit. The current archive's existing custody shape
and retained current-only receipt digests remain unchanged.

There is no catalogue request/result decoder, generic rule planner, alternate
phase service or old execution path. Removing those implementations does not
rewrite or delete stored records. Unsupported stored envelopes fail closed;
stored historical facts cannot select a checker implementation.

## Durable execution custody

ARCH-04C extends the existing CheckerRun/CheckerResult aggregate. A caller-owned
coordination transaction reserves the exact request and advances one per-Submission
fence. Global request/phase and submission/phase/generation uniqueness prevent
split attempts. Replay returns the original identity; it cannot restore an old
request as current. Execution claims a PostgreSQL-timed execution lease and releases
all locks and prepared authority before materialization or evaluator work.

Selected POST execution runs every approved digest-pinned image against
ART-verified immutable Submission material through the Rust service. Finalization consumes separate action-specific authority,
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
No new Celery task or public execution endpoint exists. ARCH-04E/B8 recheck
currentness when consuming a completion event and apply the locked ReviewPolicy;
their selected handlers are registered in production composition. CHECKERS never accepts a contribution
or mutates TASK state.
Migration 0008 refuses retained checker history before changing schema rather
than inventing request lineage or deleting data.

## Blocking Policy

Selected PRE requires the Workstream default and every required external image
to pass. Selected POST derives `needs_revision` from a failed required image and
`allow_review` from a complete passing set; TASK applies the locked review mode.
The old severity lists belong only to retained structural evidence.

Approved project images enforce their exact required checks. Artifact custody
cannot be weakened by project configuration, and a failed required image cannot
be reclassified into a pass through an administrative grant.

Project policy cannot weaken Workstream default submission artifact rules. Workstream defaults are applied before project policy. A project policy that attempts to require a forbidden artifact, remove hash requirements, allow credential-bearing storage references, or downgrade blocking defaults is a project setup defect.

The selected hidden flow has one versioned Workstream default checker with
exactly four blocking behaviors:

1. safely open exactly one ZIP within platform size limits, rejecting
   encryption, symbolic links, special files and traversal paths;
2. compute the received SHA-256 in Workstream, verify stored bytes and build
   the file manifest;
3. reject high-confidence private keys, cloud credentials and API tokens; and
4. reject the same files as the preceding attempt unless the task rules changed
   since that attempt.

Missing summary or attestation produces warnings only. Required-file, directory
layout, project metadata, project size and project-specific prohibited-content
rules belong to digest-pinned external project images.
The default checker, ART custody and approved project images replace the removed
executable catalogues. Human reviewers continue
to own final quality judgment.

The selected `workstream.default` v1 component implements this closed result
boundary. It consumes detached ART/TASK custody facts and reads verified bytes
only through the existing CHECKERS-owned callback-scoped material capability;
it receives no path or storage authority and introduces no CHECKERS-to-ART
dependency. It reports four ordered blocking slots and separate warning-only
summary/attestation absence; matched secret bytes and contributor text never
enter its result. Malformed or
unsafe contributor ZIPs are bounded work findings, while storage integrity,
inspection timeout, stale predecessor and mixed-custody failures remain
recoverable infrastructure outcomes. The unchanged-work check compares the
canonical predecessor only when its locked task-rules digest is still current.
The selected PRE owner calls this component before required project images;
both executable catalogues are removed.

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

Guide activation refuses an approved compilation with unresolved required
checker capabilities. After current manager authority and policy custody checks,
the canonical HTTP `error.details.missing_capabilities` lists only each
requirement ID, pre-submit or post-submit stage, and title. It contains no
rationale, evidence paths or provider coordinates. Registration alone cannot
clear a gap: a corrected compilation and approved binding are required.

The target launcher and checker integration use the agreed Rust service and
SDK. Registered OCI images are not thereby required to be written in Rust;
their execution identity is the approved digest, schemas and resource limits.
The hidden runtime mechanism now supplies the strict Rust SDK and long-lived
service plus an explicitly composed typed Python Unix-socket adapter. ART can issue one
opaque request-bound grant only inside the existing pre-admission prepared-ZIP
callback; the service independently verifies its sealed file/directory manifest
and exact private-root location before a read-only mount. The service accepts
only an administrator-cached OCI platform manifest whose repository, platform
and config image ID all match, and owns no-network, non-root, capability-free,
read-only sandbox launch, bounded output/deadline handling and cleanup. The
closed deployment pairs are `runsc/gvisor`, `runc/docker-dev`, and
`smolvm/smol-microvm`; project requests cannot select an engine. Smol uses a fresh
KVM VM, a static trusted bootstrap, workload and host resource limits, bounded
concurrency and independent exact-lease cleanup guardians. Its node requires
Linux amd64, KVM and delegated cgroup v2. The existing hosted Docker composition
still requires `runsc`; Smol deployment and guest ZIP/default integration are
separate boundaries. See the [node contract](../external_checkers/README.md#smol-microvm-engine).

Project-specific requirements are implemented by registered external images.
The shared service accepts the normalized result contract; it does not interpret
project-private continuation plans, task-ID allowlists or named build profiles.
Setup proposes bindings or missing capabilities from the guide and examples;
engineering implements gaps before corrected policy approval and activation.
The runner's existing sandbox contract does not by itself prove that arbitrary
submitted environments can be built and tested. Any such requirement must have
a supported, bounded image implementation before the project can activate.

### Invocation-local isolated trial tool

An approved POST image may use the existing service's typed generic trial tool
through one request-bound `/work/execution.sock`. This socket is an internal
capability of the already selected invocation; it is not a second runner,
provider, host socket or final-result variant. Six flat approved configuration
values select the exact profile and projection
by ID, version and digest. A trusted operator manifest resolves those immutable
values. The backend requires the paired
`WORKSTREAM_CHECKER_TRIAL_AUTHORITY_MANIFEST_PATH` and
`WORKSTREAM_CHECKER_TRIAL_AUTHORITY_MANIFEST_DIGEST`; the Rust service loads
the same canonical manifest and expected digest. Both refuse a missing, changed
or invalid selected profile. The private backend proxy socket carries the
closed trial reservation/publication protocol (4 MiB frames) and model sessions
(1 MiB frames); this host socket is never exposed inside an image.
The verified ART request binds their configuration to the registry entry,
checker image, material and current execution. The profile bounds offline
builder/base/cache and trusted-launcher identities, operations and aggregate resources; the
projection selects material roles, visibility and finite ordered step templates.
The image cannot select Docker flags, host paths, mounts, runtime,
network, devices, credentials or another image. Workload commands remain
untrusted argument arrays executed only inside the confined candidate image;
they are never appended as host launcher flags.

ART owns verified read-only inputs and canonical bounded scratch. The service
projects only profile-authorized build/runtime roles, uses a networkless
digest-pinned offline builder under the configured sandbox, loads exactly one
owned candidate image, and runs fresh non-root, capability-free trials with no
host socket or device. The digest-pinned launcher creates bounded filesystems
inside the sandbox, then drops mount/chroot authority before running submitted
commands. Builder code retains only its three required file capabilities;
trial commands run as nonroot with no capabilities. Neither can reach the
private bootstrap or host export directory. Exports belong to the nonroot
service so it can read and remove complete and partial output.
The candidate's numeric UID/GID must match that service identity so private
read-only role projections remain readable; mismatched configurations are
refused before launch. Each workload still runs in its own sandbox.

Each visible `state_overlay` uses one normal, top-level workspace name chosen
by its approved projection. Nested overlay destinations and collisions with
existing workspace entries are refused. The launcher creates that mountpoint,
mounts the protected role read-only, and removes the empty mountpoint after
stopping descendants and unmounting the role. No protected content or mount
placeholder enters retained state. Build-context and state-seed projections
still support safe nested relative paths.

CPU, memory/swap, PID and wall-time bounds include the whole container,
including the trusted launcher, build and export work. PID limits below two
are refused before launch. Projected files, retained images and workspaces,
temporary filesystems and export copies share one invocation byte/entry budget.
Missing prepared material, launch/cache failure, platform capacity exhaustion,
cancellation and uncertain cleanup are infrastructure outcomes. An observed
workload limit or an unsupported generated export is instead a completed
execution fact: receipts preserve the real child status and a separate
`export_outcome`. Forced stops never invent an exit code or unobserved signal.
Only successfully exported state with a profile-permitted work outcome can
feed another step. Host storage errors remain infrastructure failures even
when their operating-system error is disk-full. Project images interpret
these facts against approved requirements; shared runtime code does not grade
work or decide acceptance.

Completed observations are published only after owned nested resources and
scratch are settled. An opaque handle resolves to server-owned, request/material/
profile/plan/engine-bound facts in the same invocation. When a model assessment
depends on a trial, the model boundary injects the resolved canonical facts; an
image-authored copy cannot substitute. Every trial that starts must settle its observations and cleanup before
final result acceptance. A selected capability may remain unused when the
project check has no applicable trial, such as a revision-only check on the
initial submission; shared runtime code does not infer project semantics. CHECKERS allocates one stable trial slot for
the exact Submission and selected binding before execution. The plan and input
hashes are immutable at that address. ART stores and independently verifies
the canonical receipt, then binds it to `checker_trial_evidence`. Only that
verified receipt can produce a handle for model assessment.

A restart after reservation but before a receipt is pinned may execute the
same plan under fresh current authority; reservation provenance and the actual
executor remain distinct. After content is pinned, replay recovers those exact
bytes and issues a fresh local handle without rerunning the trial. A missing or
uncertain stored receipt fails as infrastructure; it never becomes fabricated
observations or a work failure. Model request hashing includes the resolved
canonical evidence, not the invocation-local handle.

This mechanism does not revive the removed output continuation. Shared Rust
contains no project filename, task identity, rubric, trial sequence or command
allowlist. Project logic and relative workload commands stay in the approved
image/profile. An outer `project_private_plan.v1` remains invalid output and
cannot request host work.

The service holds a nonblocking exclusive lock on the validated private socket
parent for the listener lifetime. It acquires that custody before Docker
validation or recovery, so a losing concurrent startup cannot inspect or clean
the live owner's resources. Startup preserves a live listener and every foreign
or linked path, but may remove a connection-refused socket only after its owned
inode remains unchanged. Clean shutdown removes only the listener inode it
created. A private persistent random owner ID in that locked directory scopes
container names and labels to one deployment. Startup filters by that owner and
removes a container only when the inspected full ID, owner, generated name and
attempt label agree. Other deployments and generic unowned containers remain
untouched. Preserve the owner file across restarts; loss requires operator-owned
orphan reconciliation, never generic adoption. Work commands share the request
deadline/output meter and poll cancellation. Emergency cleanup has its separate
bounded budget. Unsettled cleanup suppresses the result and prevents another
request from being admitted; restart reconciles owned resources while retaining
socket-parent custody. Project code cannot authorize additional host containers
or access to the host Docker socket by returning a private plan.

The Rust launcher owns sandbox execution; durable CHECKERS owners retain
approved policy binding, phase authority/currentness, attempts, results and
isolation receipts. F-020 requires corrected approved generation after missing
capability registration; registration alone never clears the old warning.
Production completion routes true-policy success to review_pending and eligible
locked false-policy success through shared acceptance. Complete supported false
guides can activate when the approved inventory contains no `human_review`
disposition. ARCH-02I-B exposes public ZIP preparation plus admission-backed
initial/checker-remediation Submission creation. Local
Rust/MinIO proof uses runc/docker-dev and makes no deployed or gVisor claim.

## Gate Mapping

- Project activation validates approved source/policy identities and exact
  registry digests; missing required capability coverage blocks activation.
- TASK screening and release retain their canonical locked-context and lifecycle
  guards; registry publication alone grants no Task transition authority.
- Selected PRE runs the four Workstream defaults and all required project images
  before caller-owned immutable Submission creation.
- Valid empty image bindings require no external-service configuration. The
  fixed Unix provider is resolved only when an image executes; missing required
  runtime configuration yields recoverable `implementation_unavailable` evidence.
- Selected POST consumes committed Submission custody and produces durable
  evidence. TASK's authorized completion operation alone changes lifecycle state
  or invokes shared acceptance.

Revision closure and task lifecycle movement remain owner guards, not generated
checker names. Complete supported false-policy guides can activate when their
approved inventory contains no `human_review` disposition, and public ZIP
preparation plus admission-backed Submission creation expose contributor intake.

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

- summary metadata, with absence warning-only
- one outer ZIP whose exact identity and semantic manifest are generated by ART
- contributor attestation metadata, with absence warning-only
- safe relative artifact paths
- production artifact hashes shaped as `sha256:<64 lowercase hex>`
- ARCH-02I-B public intake consumes verified ART admission and a server-generated
  manifest. The former caller-owned `package_uri`, `package_hash`, and
  `artifact_hash_manifest` inputs are removed; checkers consume Workstream
  artifact bindings. The transitional `artifact_hash` column is handled by a
  separate schema removal after readers use exact binding/content identity.
  POL-07B removes the standalone JSON precheck and connects the internal
  checker phase service
- no credentials, signed URLs, query strings, raw local filesystem paths, or token-bearing references
- narrowly high-confidence sensitive-file exclusions such as `.env`, `.git`,
  exact known credential/private-key files, `.pem`, and `.key`; broad
  `token*`, `secret*`, `credential*`, and dependency-directory matches are
  advisory or locked project-specific unless an exact generic custody risk is
  proven

The selected hidden PRE owner consumes one exact approved policy under ART
scratch custody. It validates commitment, inspection, semantic manifest and
change-gate facts and returns bounded default/external results. CHECKERS retains
immutable selected run/evidence custody; ART owns verified bytes and admission.
PRE results remain separate from post-submit CheckerRuns.

The earlier POL-07B phase facade composes two internal commands, `evaluate_pre_submission` and
`evaluate_post_submission`. Public ZIP preparation calls the internal pre command once after
reservation commits, including completed replay. The composition passes the
same opaque reservation through canonical selected custody; it clears the consumed
prepared authorization and opens no transaction before ART's existing executor
obtains fresh authority. Replay returns ART's canonical result unchanged.

The post command validates and delegates CHECKER's closed value contract.
Production composes the canonical executor with separate exact execute and
finalize authority through AUTH/PREP. ARCH-04C reserves the exact request, fences execution attempts and
atomically persists complete closed member results and a completion event; it
does not activate automatic request delivery. ARCH-04B supplies the hidden ART input port: exact consumed
Submission bytes, rebuilt manifest, async scoped file access and cleanup, followed
by a fresh material-selection check. ARCH-04D2 supplies fresh fixed-service materialization authority before and after I/O.
The existing ART output storage, byte-free recovery and flush-only verified
binding now retain private model-call request/response evidence. CHECKERS
reserves exactly those bounded slots against the stable paid attempt. Request
writes require current execution; response writes may complete an already-paid
effect after its original lease ends. Fresh current authority still gates image
access. The corresponding fixed ART writer/binding actions are active. This
private evidence is separate from the run's normalized member findings; ordinary
images do not acquire model-call authority. ARCH-04C owns durable execution.
ARCH-04D2 supplies input,
execute and finalize authority; ARCH-04E/B8 supply the hidden routing operation
and completion handler, and 04F2 supplies its remediation branch. Production
request/completion registration is supplied by PILOT-04. A returned evaluation value is not a stored current
result or acceptance.
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
pass/fail/warning results. The public authorized ZIP preparation route returns
`pre_submission_checker_failed` with those exact ordered bounded results in the
same request. ARCH-02I-B publishes it in OpenAPI with admission-backed
Submission creation. A passing ready admission can be consumed by the public
Submission operation. The bounded local public API and Celery service drill
starts from public guide inputs with recorded inference. POL-07B removes the standalone
JSON precheck and its exclusive
implementation. This result is not a review decision value.
Pre-submit results do not create durable `CheckerRun` records, do not move a
task to `review_pending`, and do not return review decision values: `accept`,
`needs_revision`, or `reject`.

The `ProjectGuideCompilationAgent` derives only PRE and POST checks. Artifact
requirements, guide sufficiency, exact default coverage and capability gaps support
that specification. The PM independently configures review mode, revision caps and
windows, deadlines, eligibility and compensation. The agent neither recommends nor
classifies those choices. New inference output rejects human-review, lifecycle and
informational requirement classifications; it has no free-form notes field.
Each check explains its classification in `classification_rationale` and carries
one `check_specification`. Exact default coverage and guide blockers are supporting
facts, with no checker specification. Retained results and explicitly manager-authored
rules preserve their existing read and authority contracts.

Both inference phases require one strict JSON object. Malformed JSON, duplicate
keys, extra fields and schema/canonical/context failures are rejected before the
candidate can proceed. Up to two corrections across the entire attempt receive
bounded field paths and closed error codes, never rejected values. Corrections share
the original timeout, model-turn/tool budgets and cleanup. Generic provider errors
are not treated as proof of invalid output or replay permission. The successful
review phase independently reopens the source originals before final admission.
The complete synthetic PRE/POST example is included in the immutable instruction
snapshot and hash. See [the setup contract](engineering/guide-checker-specification.md).

The typed specification is the implementation and test handoff. It records the
evaluation method, `bounded_pre_submit` or `background` execution mode, proposed
duration, stage rationale, exact input materials, ordered steps, pass conditions,
coded work findings, positive and negative cases, runtime dependencies and
infrastructure failures. File and directory inputs use canonical relative paths.
Capacity, deadline, unavailable material or implementation, and invalid output
remain infrastructure outcomes rather than contributor work findings. Model
evaluation requires a `model_service` dependency provisioned by the credential-
isolated `model_proxy`. An isolated execution check may declare the same dependency
for model-assisted planning or assessment. Nested builds and trials declare
`nested_sandbox` through `trial_proxy`, with exact profile and projection selectors
declared by the registered image's configuration schema. This capability is POST-only.
Its approved offline cache is `prepared_material` through the same trial tool,
with `material_unavailable` handling; it is not received package content. Other
external material and unavailable task/guide context remain explicit runtime gaps.
An unavailable cache or runtime is an infrastructure failure. The
ordinary image runner remains networkless. Model access is available only to a
registered POST image through its exact approved project model profile; a missing
image or profile remains an unbound capability suggestion that blocks activation.
The paid-call slot excludes retry generation and execution lease. Workstream
reserves the maximum configured charge before create, retains that reservation
on ambiguous delivery, and retrieves only a known provider ID during recovery.
The image owns prompt interpretation and verdict; the proxy cannot accept work
or spend a revision. Public Operator profile/budget controls and narrowly
authorized terminal-call recovery are described in
[model runtime operations](operations_checker_models.md).

The trusted compiler resolves each supported project check to an immutable
Operator-registered image, validates bounded typed configuration against that
entry's schema, and locks its exact digest and order. A missing implementation
produces a staged capability gap and engineering suggestion, rather than a human
fallback or a fabricated binding. Capability gaps permit a warning-ready draft
for manager review but continue to block activation. Only an actual guide blocker
or blocking finding stops draft policy projection. A presence check cannot stand
in for a substantive evaluator. The removed primitive catalogue is not an
alternate compiler or runtime path.

Project-specific file/count/size/evidence requirements belong to these approved
external checks. Workstream's independent ZIP/resource and credential safety
bounds remain mandatory regardless of project configuration. Generated checker
implementations remain later development work; registering an implemented image
is distinct from asking a setup agent to generate or run contributor evaluation.

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

Bindings select exact registered image/configuration/schema identities and trace
to the guide's requirement inventory. Both PRE and POST bindings carry only
configuration accepted by the selected immutable registry schema. Capability
gaps remain visible in a warning-ready draft and block activation until a later
corrected compilation selects the registered implementation. Ordinary warnings
may be acknowledged; unsupported automation cannot be silently reclassified as
human review. Explicit approved `human_review` requirements remain valid and do
not claim automated semantic coverage.
They require `human_review_required=true`: false guide activation and final
acceptance both reject any applicable approved `human_review` disposition.
Passing every executable check cannot discharge that separate requirement.

Retained compilation results keep their exact hashes and public representation.
The new `classification_rationale` and `check_specification` members are omitted
when absent from historical results; reads, approvals and recovery never invent
them. Newly compiled results must satisfy the complete typed contract before
acceptance, so retained evidence does not relax new-generation requirements.

The unified output is a constrained proposal. Workstream's trusted compiler owns the
canonical `PostSubmitCheckerPolicy.policy_body`, hash and ordered external
bindings. Workstream defaults belong to PRE, not a duplicated POST list. Runtime checker execution loads the locked compiled
policy; it does not call the setup derivation agent to judge a contributor
submission. Model-based runtime evaluation uses a separately registered checker
and approved model profile; setup inference alone grants no runtime access.

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

A system-scoped Operator registers specialized image implementations. Covered
Project Managers approve exact project bindings; a project grant alone grants
no registry publication authority.

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
compiler by projecting the exact approved external POST policy. The compiler owns the canonical
runtime body and hash. Setup agents may propose registered checker names and
PRE/POST classifications, but they do not produce executable runtime code and
they do not decide submission outcomes at runtime.

Stored pre-cutover bodies preserve their original ordered entries and hashes
as immutable provenance, without a runtime decoder or replay executor.

Those bodies are retained provenance only. New POST bodies contain the exact
approved external entries and `policy_sha256`; an empty approved POST binding
set is valid. Saved requirement, capability/version, stage and configuration
substitution rejects before projection. All required image results are consumed
by the selected outcome owner, without runtime catalogue lookup.

## Checker Run Flow — Target Contract

The following is the intended end-to-end lifecycle. Pre-submit intake and
bounded retained-history reads are implemented. Hidden durable post-submit
execution is implemented with ARCH-04D2 exact service authority.
ARCH-04E1B-B7 adds a hidden request handler that verifies committed outbox
invocation, recovers B6's exact request and fences both execution and terminal
replay/publication. B8 delivers the hidden completion handler, and ARCH-04F2
extends its existing TASK/AUTH outcome operation so an exact current
contributor-correctable result routes to `needs_revision` under either locked
ReviewPolicy mode. Selected request and completion handlers are registered in
production composition, with exact invocation authority and replay custody. Known missing or corrupt input after ART authorization records a
terminal infrastructure failure only after cleanup and fresh finalization
authorization; it does not route the task. Exact replay does not reread storage.
Denied material access and unexpected failures remain nonterminal. ARCH-04F adds
implemented hidden exact-cause replacement intake and reason-bound Operator
retry after the remediation handoff. The bounded local public durable-runtime
drill starts from public guide inputs with recorded inference; hosted operation
remains a separate readiness boundary.
ARCH-04B hidden input and ARCH-04B2 hidden output custody are delivered
with output-file authority unavailable; exact input authority is implemented.
The flow below is not a claim that the complete journey is live in production.

```text
Draft packet
-> load locked task context
-> safely inspect ZIP in bounded private ART scratch
-> run the four Workstream default checks with server-verified digest/manifest
-> execute every approved external PRE image against verified read-only files
-> create Submission only when blocking pre-submit checks pass
-> automatically lock submission
-> queue automatic pre-review CheckerRun
-> validate locked PostSubmitCheckerPolicy id/version/hash/body
-> execute every exact locked external POST image
-> store CheckerResult records
-> calculate blocking status
-> commit final CheckerRun result/recommendation, normalized JSON evidence and completion event
-> TASK consumes the current result: true -> review_pending; eligible locked false -> shared FinalAcceptance/TASK/CON/awards atomically
-> TASK projects an exact current contributor-fixable failure as needs_revision with the retained manifest recommendation and no Review
-> if checker infrastructure fails: keep in checker retry handling
```

Planned setup-fault handling is separate from this implemented routing: the
current completion classifier cannot emit `task_setup_blocked`. A manager-visible
hold for non-contributor-fixable project faults remains future safety work, as
recorded in the [capability ledger](roadmap_status.md).

The checker run must bind to one immutable submission version. If the contributor uploads a replacement file, the platform creates a new submission version and reruns checks.

`evaluation_pending` is the persisted state while post-submit checker execution
or infrastructure retry is active. After checker results, normalized JSON evidence and completion facts commit atomically, the TASK-owned
handler performs the routes above through its own transaction and authority:
passing work moves to `review_pending`, while
contributor-fixable blocking failures may move to `needs_revision`. The routing
manifest retains the exact checker recommendation and no Review is created.
Artifact-storage cutover changes how exact bytes and checker outputs are
persisted; it does not redesign these routes.

ARCH-04C owns CHECKERS result/currentness and its completion event, not TASK
mutations. ARCH-04E owns the current `allow_review` manifest and TASK transition;
ARCH-04F1 extends the existing `require_current_completion` port to all completed
recommendations and returns the exact retained typed result with its verified
material/receipt facts. It recomputes routing from the stored request/result and
rejects a mismatching caller recommendation. Infrastructure failures still have
no completed-result reference. This internal observation grants no routing or
artifact authority: TASK's success consumers still require `allow_review`.
ARCH-04F2 supplies the hidden TASK/AUTH handoff for exact current
`needs_revision` recommendations. It retains the active assignment and exact
Submission/result/manifest/receipt lineage, and creates no Review,
FinalAcceptance, ContributionRecord or award in either ReviewPolicy mode. Exact
replay returns the retained outcome without repeating effects. Contributors
continue to receive only the existing bounded checker-history projection; no new
public API is added. Exact-cause replacement and Operator retry are implemented
by their owners; manager-visible setup-fault hold remains future work.
ARCH-02I-B exposes public initial/checker-remediation ZIP preparation and
admission-backed Submission creation, and selected production composition is
implemented.
The direct CHECKERS-to-TASK mutation, fabricated system actor and alternate
Celery gate are removed. Hidden durable execution and exact service authority are implemented; selected automatic
request/completion delivery is registered. ARCH-04E2-B supplies the hidden authorized
outcome operation; B8 supplies completion delivery; ARCH-04F2 extends that
operation with remediation. The bounded local public durable-runtime drill
passed; manager-visible setup-fault hold remains pending.

`review_pending` marks readiness for the separately owned WS-REV lifecycle.
WS-REV alone creates `ReviewPacketManifest`, review queues, reviewer leases,
assignments, and review decisions. Checker completion facts and general
`ArtifactBinding` records are inputs to that later boundary, not review records.

Checker failures are not human review decisions. They do not `accept` or `reject`
work. Contributor-fixable blocking failures can route the task to user-facing
`needs_revision`; the exact routing manifest retains the checker recommendation
and there is no Review or review decision ID. Human review can also produce
`needs_revision` later, but that path is rooted in its exact Review decision.

If a checker crashes or cannot run because of platform infrastructure, the
checker run remains failed as an infrastructure failure and the task does not
move to human review. The implemented hidden retry contract requires Operator
`operations.checker.retry`, a reason, a new attempt/supersession record, and
append-only audit evidence. That action is available only through the canonical hidden recovery owner;
no public retry or repair route is added.

This terminal retry is distinct from transport redelivery or recovery of an
unfinished provider call. In-flight recovery retains its logical attempt and
provider idempotency identity; it cannot turn a terminal failed run back into
an unfinished one. A new authorized terminal retry preserves prior evidence
and supersedes it through the coordinated currentness protocol, never by
replaying an old success or bypassing the Operator boundary.

Planned setup-fault handling would retain non-contributor-fixable defects, such
as missing locked guide/policy context or missing guide-level acceptance
requirements, for authorized manager investigation rather than contributor
revision. The current completion classifier does not emit `task_setup_blocked`,
and that manager-visible hold is not implemented. Retained contracts or history
containing the token do not activate the route. Omitted or null optional
task-local `acceptance_criteria` alone is not a setup defect; guide-level
acceptance requirements remain mandatory.

A completed post-submit result with no failed member but at least one
`coverage_incomplete` finding never auto-accepts. Classification reads the
task's locked ReviewPolicy: when human review is required the result is
`allow_review`, so a reviewer judges the part the checker could not evaluate;
otherwise it is `needs_revision` and returns to the contributor. TASK records
that return as `needs_revision` with `status_reason`
`checker_coverage_incomplete`, and neither Python nor PostgreSQL counts it as a
revision round, so the next attempt keeps its current round. The normal revision
deadline still applies, and consecutive coverage returns keep the first
return's revision window instead of starting a new one, so a checker that keeps
reporting the same gap cannot return the work indefinitely. The deferred terminal-custody trigger recomputes the
same route from the stored result and locked policy. A genuine failure keeps
its normal accounting even when a coverage finding accompanies it: no coverage
reason, one revision round spent and the policy's normal window. Pre-submit
intake treats a coverage gap like any non-error finding: it does not block
admission, because intake never decides acceptance, and the bounded intake
results are returned on the successful preparation response and its exact
replay as well as on a blocked one. Run-level
`warning_count` and `blocking_count` remain member counts; per-finding counts
come from the stored findings, and contributors count only the findings their
checker history shows them.

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
digests, locked policy lineage and verified material custody. Retained structural
results have empty counters; selected image results use their closed JSON schema. Explanations and suggested fixes in history are
derived deterministically from the closed code; raw handler messages and arbitrary
metadata are not retained.

This is retained proof, not a live reviewer projection. Each selected-image
finding is also stored as an immutable `checker_result_findings` row that the
deferred terminal custody trigger compares with the stored result. Current
contributor and Project Manager history reads list one entry per stored finding
with its `check_id`, `path`, `line` and level-derived status (a member without
findings keeps one entry), plus fixed, permission-appropriate messages; raw
checker messages are not exposed. Future REV packet/current-work presentation must
expose an authorized bounded subset after routing and review integration. The
current contract does not include excerpts, per-check evidence references, full
logs or generated output artifacts.

Reviewer file inspection belongs to the planned lease-scoped ART capability bound
to the exact `ReviewPacketManifest` and active `ReviewLease`; see
[reviewer packet access](spec_review_lifecycle.md#review-packet-and-artifact-boundary).
CHECKERS history does not grant artifact access. A reviewer uses the exact immutable
Submission and locked context, with checker results as bounded provenance.

A richer finding such as an excerpt, evidence reference or generated
output needs a typed capability-specific result/evidence schema, visibility rules,
immutable custody and regression tests before the reviewer contract may promise
it. This does not introduce a generic metadata store or another checker path.
Future Operator and Audit projections likewise require their own authorized fields;
ARCH-04C adds neither full-log reads nor retry/repair controls.

## Recovery, Not Checker Override

`operations.checker.retry` has a hidden reason-bound Operator owner with fresh
authority and immutable attempt/audit custody. `operations.submission_gate.repair`
remains unavailable. Neither grants a public override or bypasses checker results.

Critical- and high-severity checker failures cannot be converted into review
readiness by an administrative grant. Covered Project Manager authority under
`project.task.manage` remains limited to existing lifecycle/context-repair
operations; it does not implement the future post-submit setup-fault hold.
Future Operator submission-gate repair and current hidden checker retry must
remain limited to their exact registered recovery purposes.

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
Workstream product-job boundary. PRE checks may also use durable execution and
polling, but their complete work must remain reliably bounded to 60 seconds.
Longer-running setup or post-submit checker work must go through the durable
worker boundary. Determinism and automation do not select the stage.

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

ART checks the canonical selected POST content against the request capacity
before durable admission. The content binds the exact approved external policy,
verified artifact/manifest, and checked packet; the removed catalogue content
type and preparation adapter are not retained as executable alternatives.
See [the ART admission boundary](spec_artifact_storage_service.md#evaluation-content-capacity-before-durable-admission).

The existing Submission transaction reserves generation one through the TASK
guard and retains exact creation/binding AUTH receipts and a bounded
`PostSubmissionEvaluationRequested` outbox event. Exact creation replay checks
the original request and event without changing the current-generation fence.
The selected request/completion handlers consume those facts. Stored intent
alone confers no execution or acceptance authority.
Preparation has no stored Submission to observe and never replaces the TASK
evaluation guard.

External PRE and POST bindings may carry the same bounded, flat typed parameters.
Approval validates their JSON values against the exact registered configuration
schema and retains both the values and configuration digest in the locked policy.
Empty PRE parameters remain absent from serialized bindings so reading historical
compilation evidence does not change its original hash. Array values serialize
as JSON arrays before schema validation and digest computation.
