# Workstream v0.1 Roadmap And Capability Status

This is the public, human-readable source for what Workstream can do on
`main`, what is implemented but intentionally hidden, what we are building
next, and what remains before v0.1 is ready. It uses capability milestones,
not calendar promises.

**v0.1 is Workstream's first usable release: the minimum complete product, not
an expansion beyond an already-working MVP.** Individual backend foundations
are implemented, but Workstream is not yet usable through its complete governed
work lifecycle. The remaining v0.1 release requirements establish that baseline;
they are not optional enhancements to a finished product.

Implementation claims require merged code, migrations, tests, and review
evidence. A plan or open pull request is not implemented behavior. Open pull
requests are the transient view of work currently under review.

Bounded contribution evidence reads expose existing immutable work and award
facts to the current human or authorized project exporter. These reads alone do
not activate recognition writers, establish the local contributor journey or assert payment.
The REST reads traverse short-lived fixed membership with fresh authority on
every page. The CLI follows JSON and exact CSV continuation internally, retains
its complete public output shape and publishes only a fully validated traversal.
Separate CLI task-audit commands consume the existing exact Audit Authority
locked-context and bounded evidence GETs; they do not broaden manager or
contributor disclosure, grant authority for later pages, or export full history.

External-checker registry preparation has a supported bearer-authenticated
system Operator API for immutable registration, lost-response replay and exact
readback. Workstream selects the UUIDv7 identity and retains exact AUTH and
digest closure in PostgreSQL. This capability does not select or activate a
checker, change an approved guide, or expose REV lifecycle controls.

The external checker node supports a self-hosted Smol microVM engine through the
existing typed Unix-socket execution adapter. Bounded node proof covers Python
and native PRE/POST images, resource enforcement and interrupted-work cleanup.
It does not establish upload-overlapped preparation, guest ZIP/default processing
or the public durable-worker contribution journey on Smol. Those remain the next
[WS-EXEC-001 boundaries](../.commitrail/initiatives/WS-EXEC-001/OVERVIEW.md).

The artifact diagnosis API uses exact,
current system-Operator AUTH decisions for its bounded reads and independent
verification retry. Signed local PostgreSQL tests cover the real routes and
atomic retry evidence. The CLI consumes all nine existing routes through
`operations artifact`, with explicit pagination and one-shot reasoned retry;
hosted S3 operation remains a separate proof boundary.
The [CLI distribution path](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-44.md)
prepares native four-platform GitHub Releases proof and a protected manual
publisher. No approved release tag or public binary has been published yet.

## Product Goal

Workstream turns governed work into trusted `ContributionRecord` facts:

```text
Project Guide
-> governed Task
-> artifact preparation and pre-submission intake checks
-> immutable Submission
-> post-submission evaluation against locked requirements
-> policy-governed acceptance: authorized human Review or automated decision
-> controlled Revision when required
-> Contribution Records
-> conditional Compensation Awards and Fulfillment
-> evidence for a future Reputation projection
```

The v0.1 release bar is one secured, observable, recoverable end-to-end path.
Authorization, locked project rules, exact artifact identity, attributable
policy-governed acceptance decisions, and durable contribution facts are necessary for that path to be
trustworthy. Integration and failure-recovery proof are part of making it
function correctly, not a later quality upgrade. This does not require every
future feature, an exhaustive cleanup of the codebase, or proof of unlimited
scale before first use; the release gates below define the bounded requirement.
Attributable human Review is required when the locked project mode requires it;
automated acceptance records its own authorized decision and evidence instead.

Marketplace expansion, blockchain settlement, external source adapters,
external task-routing systems, agent workspaces, and runtime reputation projection remain
outside v0.1.

A documented future research hypothesis considers a provider-neutral adapter
that proposes task dependencies and contributor candidates for multi-human and
multi-agent work. It is not Planned or implemented, adds no v0.1 milestone, and
can advance only through a separately approved initiative after the current
lifecycle is proven. See the
[Product Brief](product_brief.md#future-research-hypothesis-accountable-orchestration).

## Status Vocabulary

The public automated-acceptance journey passed its bounded connected local drill
from public guide inputs with recorded inference, local Flow-compatible auth and
real PostgreSQL, MinIO, Redis, prefork Celery and Beat. Both policy outcomes,
restart/replay, late authority revocation and cleanup passed; live-model and
hosted deployment proof remain separate. ARCH-04E3-B admits
complete false-policy guides with supported approved checks. Selected production
completion reached the governed outcome under a LIVE REV generation. The
existing versioned ReviewPolicy now
persists the setting: `human_review_required: bool = true`. True requires human
review after required checks pass; false leads to authorized FinalAcceptance
and submitter contribution without a reviewer contribution. It requires explicit locked project policy,
supported acceptance evidence, distinct service decision provenance and shared
atomic contribution effects; checker success alone is not acceptance. The
[canonical shared acceptance contract](spec_review_lifecycle.md#finalacceptance)
defines one FinalAcceptance/submitter-contribution operation with two triggers,
not a separate automated acceptance system. The human branch retains canonical
`allow_review`. Shared REV source persistence and hidden CON submitter
participation are delivered before ARCH-04E false/pass integration; human
queues/leases are not its prerequisites. REV-12A4A supplies the existing
controller’s internal Operator-authorized phase transitions and current-generation
participant gates. The controller refuses retained pre-authority acceptance
facts before entering live. ARCH-04E3-B's reviewed manifest describes selected
production routing; payment delivery remains unavailable, and
conditional award facts remain atomic, while obligation/root/cutoff machinery
belongs to later fulfillment activation.

The setting is configurable through the existing authorized policy writer;
creation defaults true and omitted replacements inherit the predecessor.
Versioned hashing preserves old policy hashes and locks. ARCH-04E3-B allows
false activation only for a complete approved requirement inventory with exact
supported checks and no `human_review` disposition; Python and PostgreSQL both
enforce that boundary. See the [setting record](../.commitrail/changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
and [activation record](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E3B.md).
New false/pass effects require an Operator-authorized LIVE REV generation whose
exact retained transition binds the current reviewed manifest. An old live
generation cannot authorize expanded scope after upgrade; renewal uses the
existing Operator transitions and leaves historical replay unchanged.
The separate `requires_second_review` field is [fixed to false](../.commitrail/changes/enforce-requires-second-review-false.md)
at typed input, immutable lineage and PostgreSQL boundaries. Retained true facts
refuse upgrade without rewrite; supported false-policy hashes remain unchanged.
The first complete contributor milestone is claim -> upload ZIP -> pre-submit
feedback or immutable Submission -> automatic post-submit checking -> outcome.
For an eligible project with locked `human_review_required=false`, success must
include shared FinalAcceptance, the submitter ContributionRecord and applicable
policy awards. Failure/remediation and public intake belong to that milestone;
reaching hidden checker success alone does not complete it. The bounded local
journey passed before live human review/revision. Independent review foundations may proceed in
a separate worktree, but cannot add a human-queue or review-lease dependency to
automated acceptance. Human review/revision still belongs to the complete v0.1 release. See the
[product-builder handoff](../.commitrail/changes/pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next).

| Status | Meaning |
| --- | --- |
| **Live foundation** | Merged behavior is available to its intended caller. It may still be only one part of a larger product flow. |
| **Hidden and proven** | Merged behavior exists and is tested, but no public production route exposes the complete flow yet. |
| **Next** | The next dependency-safe implementation boundary after current `main`. |
| **Planned** | The design direction is accepted, but its current skeleton must be refreshed into a bounded executable contract before coding. |
| **Deferred** | Deliberately outside the v0.1 runtime. |

## Executive Snapshot

Identity, authorization, guide ingestion, automatic unified compilation and
public manager proposal/approval operations and terminal guide activation are
implemented. Compilation uses bounded source read/search tools behind the chosen
runtime adapter. The OpenAI Agents SDK and OmniCoreAgent adapters are statically
selectable in mutually exclusive inference images; OpenRouter remains a separate
provider choice. Neither adapter requires provider-hosted files or containers.
The OpenAI Agents SDK and OmniCoreAgent paths each passed an original-guide public
API and durable Celery qualification using the real parser and MinIO. This proves
the bounded runtime swap for Project Guide compilation, not deployed Flow/AWS
operation or an independently interoperable protocol implementation. Compilation
runs either through inference or
through the provider-free `manager_authored` runtime, which converts a
manager-uploaded rules document with no inference. Managers discover exact activation selections through the authorized
draft post-policy read; Finance publication remains separate. Task policy
lineage, public ZIP preparation and admission-backed immutable Submission creation
are implemented for initial work and exact checker remediation. Their complete
public API and Celery service journey passed its bounded local drill under
public guide inputs and recorded inference. TASK
now reserves and replays exact post-submit routing requests internally. Hidden
AUTH binds those requests to exact source and branch consequences through
canonical PREP. The hidden authorized outcome operation commits source custody
and its governed effects atomically; B8 supplies hidden completion delivery.
04F1 supplies verified current failure evidence; 04F2 routes an exact current
contributor-correctable result through the existing TASK/AUTH operation to
`needs_revision` under either locked ReviewPolicy mode when another revision
remains. PILOT-08 uses the task's locked project policy: N=0 permits one attempt;
N=2 permits attempts 0, 1 and 2. Final-attempt failure immediately records
exhaustion and returns the task to ready, without another preparation or window.
With revisions remaining, failure freezes a complete kept/rebased/blocked
context. A setup block publishes durable PM attention and pauses the PostgreSQL
allowance; repair resumes only the remainder, or preserves a running deadline.
The CLI exposes that existing public manager repair as one explicit keyed
operation for an exact parent or retained missing-root routing source; it neither
decides eligibility nor renews the clock.
Only committed immutable resubmission ends a running opportunity. Contributor
reads expose exact acknowledgement and change summary; contributor/PM task detail
and Submission history distinguish exhaustion from timeout. Timeout also closes
the assignment and returns the task to ready. Any eligible claimant can start a
new assignment at round 0; no contributor-count limit or repeated-failure hold
is introduced. A coverage-only return under a false ReviewPolicy spends no
round and never exhausts, keeping the current round; consecutive coverage
returns keep the first return's window. Earlier evidence remains immutable. 04F3 supplies replacement intake through the canonical
ART/TASK writer, preserving predecessor evidence and checker provenance while
atomically creating the successor Submission and evaluation request. ARCH-04F4
owns reason-bound Operator retry for an exact current terminal
`infrastructure_failed` run through the existing CHECKERS coordinator and
request handler, with immutable source, AUTH/audit/outbox custody and
fresh-authorized historical replay. The supported system-Operator API now adds
project-scoped, bounded source discovery and invokes that same owner. Separate
Operator reconciliation classifies uncertain post-submit request/completion
deliveries and appends at most one child to verify committed effects or invoke
the existing owner after proving no effect. Unresolved sources and an UNKNOWN
child remain held. Full hosted interruption proof remains outstanding. PILOT-04 registers
selected request and completion handlers in production composition. ARCH-02I-B
publishes ZIP preparation and the canonical admission-backed Submission POST in
OpenAPI. Current completion classification has no `task_setup_blocked` path, so
a manager-visible setup-fault hold is future safety work rather than a
first-journey prerequisite.

Exact assignment-invalidation authority, atomic originating publication and
production delivery with enforced prefork topology are implemented. Manager task
create/screen/release now use exact project authority, atomic evidence and durable
replay. ARCH-03C4 adds the three exact-authorized public task queues. PILOT-14
adds locked
ContributionPolicyVersion compensation to ready rows and Contributor detail for
active exact-project Submitters or Reviewers, without Finance internals or claim
authority. ARCH-03C5 adds exact-authorized Contributor/Manager
detail and requirements. ARCH-03C6 adds
separate exact-authorized locked-context reads. ARCH-03C7 adds bounded public
Audit Authority history access. WS-CLI-001-34 adds explicit CLI consumption of
those two audit reads without changing their authority. WS-CLI-001-46 adds
`GET /api/v1/projects` and `workstream project list` for a minimal ID/name/status
page under current system Project Manager, Operator, Finance or Audit project-read
authority. It leaves exact-grant contributor discovery unchanged and supplies
no TUI runtime. PILOT-02A provides project-bound canonical JSON
source declaration, upload, status and verified download using ART custody and
current PM authority, with public-route PostgreSQL/MinIO custody, replay,
rollback and recovery proof. PILOT-02B adds public atomic JSON-to-DRAFT import
and native batch status, with immutable membership, fresh-authority exact-file
replay and a real 200-row PostgreSQL/MinIO proof. PILOT-02C adds separate atomic
batch screening/release and explicit CLI source/import/status commands, including
local CSV conversion. WS-CLI-001-31 adds a separate CLI verified-source
download through the existing public status/content reads, with private
no-overwrite output. Omitted/null task-local criteria remain optional through
SCREEN/RELEASE under exact guide locks. These public backend/CLI capabilities
do not imply deployment.
ARCH-03D connects hidden intake through durable intent to the activated historical
guide using canonical owner ports. ARCH-04B adds hidden verified Submission input
with scoped async access. ARCH-04B2 adds hidden typed checker-output storage,
byte-free recovery and flush-only verified binding over generic ART
put/verification. ARCH-04C supplies hidden durable evaluation, immutable ordered
results, database-timed execution leases and atomic completion events. ARCH-04D2 supplies exact fixed-service input, execute and finalize authority
and database-bound receipts; output-file authority remains unavailable. ARCH-04D1 enforces canonical
ART material lineage for all terminal results retaining material; ARCH-02I-B
subsequently exposes public intake. ARCH-04E1A adds one immutable route-neutral
TASK source table, detached source facts and source-neutral accepted-effects
contracts. Required success branches on the locked ReviewPolicy: the hidden
operation stages the TASK human-review handoff for true and shared authorized
acceptance without a human Review for false. These internal outcomes have
transaction and database proof; B8 supplies hidden completion delivery, and
ARCH-04E3-B admits complete supported false guides under exact Python/SQL custody.
ART-07A1 supplies metadata-only reviewer packet types, with no resolver or byte
authority. REV-03B packets and REV-04A immutable Review source storage are delivered; REV-04B shared acceptance storage, CON-03C contribution/award storage, REV-12A1 disabled controller/fence mechanics and CON-07 hidden source-neutral submitter participation with complete frozen award sets
are delivered. [REV-04C](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04C.md)
adds one hidden source-neutral participant that stages
FinalAcceptance, TASK accepted/completed effects and the complete CON outcome in
the caller's transaction. [ARCH-04E2-B](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E2B.md)
adds the hidden authorized outcome operation over those owners. It binds actual
Submission, materialization, checker and routing receipts to the retained source.
Locked true stages the TASK human-review handoff; locked false atomically stages
FinalAcceptance, accepted TASK/completed assignment, the submitter contribution,
applicable awards and shared audit/outbox evidence. Database closure rejects
partial outcomes; replay verifies the retained tuple with fresh authority.
B8 supplies hidden completion delivery. 04F2 extends the same operation and
actual receipt custody with `checker_remediation`: TASK moves from
`evaluation_pending` to `needs_revision` when revisions remain; PILOT-08 closes
a final failed assignment immediately and returns the task to ready. Both
create no Review, FinalAcceptance, ContributionRecord or award under either
ReviewPolicy mode. 04F3 admits a changed full ZIP from that exact current
authorized cause under either mode, with no failure economics or human Review.
04F4 supplies the hidden retry owner for known terminal infrastructure failure;
the supported Operator recovery change exposes project-scoped public discovery
and invokes that owner. Recovery creates no Review, acceptance, contribution or
award. Uncertain request/completion effects are not eligible for this retry.
Selected production request/completion composition and
supported false-guide activation are implemented. A known pre-effect non-live REV refusal returns bounded OUTBOX retry after rollback; exhaustion dead-letters without automatic reopen. A setup-fault hold is future safety work because no current selected production result emits `task_setup_blocked`. Human review/revision, conditional fulfillment, operations and
release proof remain later v0.1 work.

The [independent MCP package](../mcp_server/README.md) implements forty-seven
self-service, administrative access, actor/identity-lifecycle, project-shell,
project-participation, guide-metadata, draft-policy, contributor-workspace,
contribution-evidence and contribution-policy tools through WS-MCP-002-10. The
[Go CLI](../cli/README.md) provides caller-profile and exact-project authorization
reads plus human self-profile editing, exact-project inspection and manager
task queue/detail reads, contributor ready-work/instruction reads and public
claim/start commands with caller-supplied retry keys, plus governing work-context
and locked intake-requirement reads, assigned locked-original listing/download,
and distinct system-Operator task status/locked-reference reads and deliberate
reasoned start override through the already-public routes,
draft project creation, guide declaration
with illustrative tasks/document selectors, explicit draft-summary edits and
review/revision policy selection with caller-owned preconditions, and declared-original upload with
hash/size-bound storage receipts and a local-original recheck before success, using explicit
caller-owned retry keys, with
text/JSON output, plus latest guide-setup diagnostic inspection without polling
or local readiness decisions, and exact finalized-proposal inspection without
approval or implicit latest selection. Project inspection preserves
server-selected full/minimal fields. Exact pre-submission proposal approval uses
deliberate caller-prepared input and retry keys; its receipt does not establish
post-policy approval, post-policy job delivery or guide activation. Exact derived
post-policy inspection returns the canonical policy, upstream findings, activation
selectors and saved correction, including retained superseded policies; reading
does not make a decision or dispatch work. Separate exact post-policy approval
uses caller-prepared input and a retry key, validates the full returned target
and preserves backend-owned fresh replay authority; it does not activate a guide.
Exact post-policy correction submits the inspected target and manager feedback,
returning one saved unified successor without dispatch or activation.
Exact proposal correction and explicit saved-successor dispatch are also
available: dispatch preserves backend diagnostic status, including enqueue
failure, rather than claiming processing completion or activation.
Separate exact guide activation is available through the public manager POST,
with caller-selected approved policies, contribution-policy binding and immutable
receipt validation. The backend retains readiness and supersession authority.
Complete supported false-policy guides can activate only when their approved
inventory contains no `human_review` disposition; new false/pass effects still
require a live REV generation.
Separate manager task create/screen/release commands now bridge an active guide
to ready work through the public APIs, with explicit request keys and complete
management receipts. Backend owners retain policy locking, readiness and fresh
authority; there is no automatic create-and-release sequence. PILOT-02 supplies
separate explicit batch conversion, source custody and verified download,
atomic import/status and whole-batch screen/release commands in the same CLI.
The CLI also invokes the existing exact Project Manager revision-context repair
POST, returning its current paused/running clock and disposition without an
automatic read, rebase or retry.
Explicit CLI Submitter/Reviewer issuance and revocation use the existing public
AUTH writes with caller-supplied qualifications/reasons, exact receipt binding
and fresh-authorized manual replay. This is not AdminRole administration,
automatic eligibility or activation of unfinished human review.
The CLI also reads the existing privacy-safe, exact-project contributor-candidate
page for a covered Project Manager; discovery is not qualification or a grant.
CLI grant list/detail now expose the existing authorized qualification and
revocation history: one filtered count-free page with explicit continuation,
or one exact project/grant. Current authority remains backend-owned; no global
actor directory, role cache or automatic decisions are added.
CLI contribution-policy current/exact-version reads now expose the authorized
Finance policy graph, including empty drafts, published/open-draft selectors and
retained historical versions. Backend selection and current Finance authority
remain decisive; PM-only permission does not suffice. CLI draft creation, complete
rule replacement, publication and retirement now use the existing public Finance
operations with explicit retry keys and immutable receipts. Guide activation is
separate. CLI contribution-evidence commands now provide self and authorized
project reads, including exact server CSV downloads. Backend fixed-membership
pagination and the CLI's bounded internal traversal preserve complete selections
through 100,000 contributions without exposing cursor controls.
Explicit CLI ZIP preparation, admission-backed creation/replay, submission history
and contributor checker findings now consume the public APIs. PILOT-READ-1 adds
typed attempt status, `decided_at` and finding counts to history, and per-finding
`check_id`/`path`/`line` to checker results. The CLI also exposes the seven
existing manager task requirements/context,
exact task Submission history, exact Submission and checker-run evidence GETs
under Project Manager authority. These are distinct from contributor projections;
reads do not authorize later writes or make checker evidence acceptance.
PILOT-READ-2 adds the contributor's
own cross-project reads with their own AUTH actions: the projects where the
caller holds an exact grant, and, limited to projects where the caller holds a
current Submitter grant, claimed assignments with a server-computed next
action and the work-context revision context, attempts with finding counts,
intake preparations, and a summary with award totals; plus filtered manager
task lists; the CLI `me`,
`task preparations` and `project tasks` filter commands consume them.
PILOT-READ-3 adds the Project Manager's project-wide reads, each with its own
AUTH action: guide versions, one guide with its documents and selected
policies, a side-effect-free activation readiness dry run that reports the
unmet activation conditions it evaluates (a check whose inputs are missing is
not evaluated) with activation's own refusal code, verified
read-back of an uploaded guide original, every attempt and claim, a project
summary with award totals,
task import batches and ZIP preparations with finding counts; plus the Finance
list of every ContributionPolicy version. The CLI `project guide
list|show|readiness|document`, `project submissions|assignments|summary|import-batches`,
`project preparations` and `project contribution-policy list` commands consume
them. Preparation does
not create a Submission; readiness recovery is an explicit same-key POST replay,
not a polling GET. PILOT-08 exposes frozen revision-change summaries through
contributor task context and requires the exact preparation acknowledgement for
checker-remediation intake. CLI submission/history text distinguishes the absence
of that summary in historical responses from the separate current task-context
read; it never substitutes current context for historical submission evidence.
Individual CLI tests retain fixture-arranged prerequisites. The connected
[native CLI journey](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-43.md)
targets public manager-authored setup through real MinIO/Celery evaluation,
unpaid automated acceptance and matching JSON/CSV contribution evidence,
including rejected-intake recovery, replay and authority denials. The fresh
connected run passed those assertions and exact Operator artifact custody
inspection, with isolated PostgreSQL and MinIO cleanup confirmed. See the
linked evidence record for source/binary identity and earlier diagnosed failures.
It uses explicit local deployment bootstrap, not fixture-created product facts.
Hosted operation, external Flow verification and human-review/revision remain
separate proof boundaries; this is not general beta certification.
The CLI also exposes the seven existing administrative active-guide, exact-guide
sufficiency, retained artifact-policy, current effective-policy and pre-submit
policy GETs. Historical collections show the newest 100 rows without cursors;
exact IDs reach older retained evidence. Current-chain reads remain backend-
authorized and do not confer later-write authority or compute readiness locally.
Separate CLI POST commands record a human sufficiency diagnostic and explicitly
acknowledge eligible warnings under fresh Project Manager authority and caller-
owned replay keys. They do not produce an authoritative setup result, approve a
policy or activate a guide; the separate CLI manual artifact-policy writes only
append retained drafts after authoritative setup and never authorize activation.
The separate public `GET /api/v1/projects` and `workstream project list` return
only bounded ID/name/status pages for the four current system project-reader
roles. `GET /api/v1/actors/me/projects` still lists only the caller's exact-grant
projects; neither route discloses guide content by catalogue authority alone.
The CLI also exposes the eight existing administrative actor, identity-link,
fixed-service provision and grant POSTs as deliberate keyed commands under the
single `admin` root. Backend authorization and lifecycle guards remain decisive;
administrative reads are observations, not permission for later writes. This
client exposure is not a deployed-service or independent conformance claim.
CLI write uncertainty is explicit and never automatically
retried. The separate CLI release workflow builds read-only pull-request
previews for Linux amd64, Intel/Apple Silicon macOS and Windows amd64, then
permits only a manually approved exact-tag publication. Its presence is not
a published binary, deployed backend or complete proposed workflow catalogue.
The [Operator checker CLI](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-29.md)
adds explicit registry register/read and project-bound terminal retry-source
list/retry commands over the existing public API. Registry publication is not
checker enablement; source reads never grant a subsequent retry, and all writes
retain caller-owned exact replay and backend authority.
The separate [uncertain-delivery CLI](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-40.md)
consumes the two public Operator routes for one project-bound UNKNOWN-source
page and one explicit keyed event reconciliation. It makes no local delivery
classification or write-authority decision; an unknown POST outcome requires
manual unchanged-key replay. Its signed PostgreSQL/API proof starts from an
owner-produced source, not a hosted interruption or S3 drill.

Privacy-bounded API and prefork Celery diagnostics are implemented: structured
logs, sampled traces and bounded metrics through one typed export adapter.
Trusted-broker trace linkage depends on restricted broker publisher ACLs and
never supplies product authority. Collector deployment, diagnostic-store access
and finite-retention controls, and an operational end-to-end drill remain
release work; diagnostics do not establish lifecycle truth.

The first hosted release configuration now separates immutable API/Celery/Beat
and checker-service images from the development stack, requires real Flow
verification and AWS workload identity, and binds the existing checker service
to a dedicated Docker/runsc host with exact private material paths and cached
image identities. It carries the required release digest and exact AWS
role/policy/trust/bucket-policy identities into every long-running process
environment. The external-host credential integration uses AWS Roles Anywhere
with dedicated certificate identities, preserving the same S3 adapter and
activation guards; it does not require EC2 or interactive login. The integrated
canonical S3 Settings owner validates their format
and relationships at startup; image proof first exercises that owner directly.
Its preflight proves
local configuration and host prerequisites only. Real certificate-role diagnostics
have passed immutable upload/readback, bucket controls and access isolation.
Persisted activation proof jobs, deployment, representative resource limits,
diagnostic privacy/outage behavior, drain/restart and isolated backup/restore
remain environment evidence for #583 and the parent release drill.

Checker startup recovery is deployment-scoped through persistent owner custody
in the locked private socket directory, exact container labels/names and inspected
Docker IDs. It does not adopt another deployment's or unowned containers. See
[ownership and restart guidance](../external_checkers/README.md#container-recovery-ownership).
This repair does not establish a hosted or complete CLI journey.

The generic [checker image command](engineering/checker-images.md) builds a project-owned image, tests positive and negative samples, and optionally publishes that same image to private ECR. It verifies the platform manifest/configuration identity and emits registration and cache inputs. Dry-run compatibility evidence is explicitly `docker-dev` or `gvisor`; it is not live ART custody, project activation or deployed operation. Operator registration, execution-host provisioning and approved policy binding remain separate.

[ARCH-04E1B-B1](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB1.md)
adds required TASK-before-CHECKERS reservation/current-result locking, ordered
review admission INSERTs, exact terminal replay and mechanical race controls.
[ARCH-04E1B-B2](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB2.md)
adds exact hidden source preparation through existing owner ports, without
source publication or authority.
[ARCH-04E1B-B3](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB3.md)
retains verified ZIP member metadata for consumption without another storage read.
[ARCH-04E1B-B4](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB4.md)
binds Submission text to its checked intake packet at consumption and in storage.
[ARCH-04E1B-B5](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB5.md)
rejects unrepresentable evaluation content before durable admission.
[ARCH-04E1B-B6](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB6.md)
commits each new Submission, verified ART binding, exact creation/binding AUTH
receipts, generation-one reservation and shared outbox request together.
Fresh-authorized replay verifies retained owners without creating missing rows.
B7 delivers the hidden request handler with exact invocation fencing. 04E2-B delivers the hidden authorized success outcomes; B8 supplies hidden completion delivery; 04F2 supplies the hidden remediation handoff; 04F3 supplies exact-cause replacement; 04F4 supplies the hidden terminal infrastructure retry owner, and the supported Operator recovery change supplies its project-scoped public discovery and invocation. Uncertain delivery remains a separate recovery boundary. A manager-visible setup-fault hold remains future safety work, with no current `task_setup_blocked` production result.

## Pre-Submission And Post-Submission Checking

Both stages enforce quality, but answer different questions and produce
different outcomes. They are not one combined checker phase.

The phase is distinct from the execution method. Static inspection and other
checks that can reliably finish within 60 seconds belong before Submission
creation, even when they use durable execution and polling. Longer work,
repeated trials and model evaluation belong in background POST. Automation alone
does not make a check POST. Recording a model evaluator's inputs and result does
not promise identical judgments on rerun; it still needs an explicit
implementation, runtime dependency and policy binding.

| Stage | Purpose and examples | Policy and execution boundary | Outcome |
| --- | --- | --- | --- |
| Pre-submission intake checks | Is this bounded package check acceptable before creating a Submission? Check static structure, required/forbidden files, evidence integrity and other work that reliably completes within 60 seconds. | The locked selected PRE policy runs the single Workstream default followed by every required digest-pinned project image on ART-verified material. PRE may use durable execution and polling, but a proposed check and selected registry deadline must remain within the 60-second boundary. | Blocking failures return correction feedback and prevent Submission creation. Passing intake does not prove the task is accepted or ready for review. |
| Post-submission evaluation | Does the submitted work meet checks that need longer execution, repeated trials or model evaluation? Evaluate the exact immutable work and evidence under the locked requirements. | The Submission-stamped external POST policy drives approved digest-pinned images through the Rust service and durable `CheckerRun` ownership after immutable Submission creation. Only supported, registered checks execute. 04F1 verifies current completed failure evidence through the same CHECKERS port. The locked project revision policy requires an explicit integer cap `N >= 0` and positive deadline hours. | Persist current evidence. The hidden authorized operation publishes exact source custody. `allow_review` branches on locked ReviewPolicy: true moves TASK to `review_pending`; false invokes shared acceptance under TASK authority. Exact current `needs_revision` with another revision remaining moves TASK to contributor remediation under either mode, with a running or setup-paused PostgreSQL window and no REV/CON effects. Failure on the final permitted attempt immediately records rejection and exhaustion, closes the assignment as `revision_exhausted`, and returns TASK to `ready` without another preparation or window. CHECKERS never writes TASK state or acceptance itself. B8 supplies completion custody; PILOT-04 registers selected request/completion production delivery. |

The unified guide agent proposes both sets of policy bindings in one setup
result. Trusted compilation, validation, and the governing approval path turn
those proposals into separate locked policies; setup inference is not a second
agent run judging a contributor's submission. An agent-based evaluator or quality
judge would require its own supported checker implementation and policy binding;
it is not implied to be live by the unified setup agent or the roadmap.

Each newly compiled atomic requirement explains its classification. Supported
and missing PRE/POST checks carry one typed engineering specification covering
stage and budget, inputs, ordered checks, pass conditions, work findings,
positive/negative cases, dependencies and infrastructure failures. Missing
implementations remain capability gaps in a warning-ready draft and block
activation; only guide blockers or blocking findings stop draft projection.
Historical results remain readable and hash-identical with absent new fields.
The inference adapter drafts a candidate, then reviews source coverage in a fresh
model context within the same attempt and work budgets. Only its final reviewed
output reaches validation; failed review cannot publish the candidate.

Authorized reviewers still own `accept`, `needs_revision`, and `reject`.
Only an actual human Review stores those decisions; neither checker stage
impersonates one. With locked false policy, TASK invokes the shared acceptance
operation without a Review. Pre-submission feedback
cannot be reused as post-submission review-gate evidence. See the
[checker architecture](architecture_checker_framework.md) and
[pre-submit versus durable contract](spec_chunk_8_submission_artifact_policy_checkers.md#pre-submit-versus-durable-runs).

## End-To-End Lifecycle Scoreboard

| Lifecycle stage | Intended merged status | What is already proven | What remains before v0.1 |
| --- | --- | --- | --- |
| Identity and actor resolution | **Live foundation** | Flow-token verification; canonical ActorProfile and ActorIdentityLink; human/service separation; lifecycle controls; canonical `/actors/me` self-read with duplicate `/auth/me` removed; suspension denies both self-read and self-update; CLI privileged exact-actor/profile and identity-link reads and explicit separate profile/link lifecycle writes remain distinct from self-service and backend guards | Final end-to-end operational and conformance proof |
| Authorization kernel | **Live foundation** | Closed action/permission catalogues; deny-by-default evaluation; grants; exact-project, privacy-safe candidate read now consumed by the CLI; fixed services; rate controls; opaque transaction-bound PREP; atomic decision evidence; CLI scope-filtered administrative grant/catalogue reads and explicit keyed grant issue/revoke consume existing public APIs without local authority decisions | Activate only the remaining owner-proven TASK, checker, REV, and CON boundaries; remove obsolete authority after replacement paths are live |
| System project catalogue | **Bounded public API and CLI read** | WS-CLI-001-46 adds `GET /api/v1/projects` and `workstream project list` for current system Project Manager, Operator, Finance or Audit `project.read` grants; each signed page exposes only ID, name and status. `me projects` retains exact-grant membership semantics. | TUI runtime, deployed CLI and hosted conformance remain separate |
| Project Guide source custody | **Live foundation** | Guide creation declares documents and task examples; public document upload; immutable internal metadata snapshots; draft guide and review/revision policy writes with fresh-authorized exact replay of original receipts; exact run-scoped setup reads and assigned-task locked-original reads; S3-backed originals and isolated agent document inspection; exact document generation through separate manager approvals and public exact-authorized CP07 activation; Project Manager guide list, guide detail, activation readiness dry run and verified original read-back (PILOT-READ-3); the CLI exposes existing administrative active-chain and retained sufficiency/artifact-policy reads, keyed human sufficiency writes, and separate manual artifact-policy draft create/update with backend-owned policy decisions | Public original upload, task examples, Celery setup and separate approvals are connected locally with recorded inference; prove configured live inference and readers in the intended environment; manual drafts are not compiled activation proposals; deployed CLI remains separate |
| Unified Project Guide compilation | **Live setup and manager proposal operations** | Committed original-document readiness dispatches one immutable attempt through Celery; complete result and crash/recovery custody; distinct pre/post proposals; typed per-requirement classification and checker specifications; deterministic sufficiency and submission-artifact-policy projections; immutable authorized setup finalization; public exact manager review, pre-submit approval and manual correction dispatch; automatic deterministic post-policy derivation, public complete policy read, separate approval and shared correction custody. Neutral read/search tools support statically registered OpenAI Agents SDK and OmniCoreAgent adapters in mutually exclusive inference images, while provider-free `manager_authored` compiles a manager-uploaded rules document with no inference or provider resources ([runtime initiative](../.commitrail/initiatives/WS-AGENT-001/OVERVIEW.md), [manager-authored record](../.commitrail/changes/manager-authored-guide-runtime.md)). Capability gaps preserve a warning-ready review package but block activation; retained pre-specification results keep exact hashes and reads. Exact Omni SDK, mutually exclusive release-image, parser-isolation and real-MinIO proofs pass. Both inference adapters pass the same original-guide public API, durable Celery, real-parser and MinIO path; the Omni run stopped at a warning-ready manager draft with no bindings, approval or activation. The Terminal Systems handoff now has a project-owned image for its two PRE rules, with local rule and networkless-container proof. | Retain the exact external provider/account and selected-image AWS evidence; implement the eight Terminal Systems POST rules and their runtime dependencies; register the required images, obtain approved bindings and qualify the broader hosted Flow contribution journey. Original-guide qualification and local checker proof are not deployed operation or full guide-to-contribution proof. |
| Contribution policy administration | **Public Finance policy workflow; binding administration internal** | Internal Finance Authority adapter-binding lifecycle; public ContributionPolicy discovery/read/create/update/publish/retire with exact Finance Authority and recoverable draft selectors, and a Finance list of every version (PILOT-READ-3); immutable operation and event history; internal exact selected-version validation; CP07 binding with live exact-project manager authority of the selected published version to the active guide generation | The bounded local public drill passed; policy publication alone does not create a contribution, and hosted operation remains unproven |
| Task readiness and claim | **Foundation with grant-backed manager and contributor commands** | Task records, assignments and locked work context; guide-bound ContributionPolicyVersion locked before `READY` and copied to TaskAssignment; detached project/guide display; public project-scoped ready, management and operational queues with distinct current grant authority and signed bounded live pagination, with typed task status and manager filters by status, assignee, native import batch and update time (PILOT-READ-2); contributor cross-project own-assignment, attempt and summary reads under current Submitter grants (PILOT-READ-2); Project Manager project-wide attempt, claim, summary and import-batch reads (PILOT-READ-3); public contributor/management detail with exact project and assignment authority; separate current live work-context projections with exact receipt-selected review/revision/ContributionPolicy identities and no obsolete economic fields; explicit management/operational/audit locked-context projections using one historical resolver, with separate public manager, system-Operator and Audit Authority access; immutable contributor/management requirements using one historical translator, with public exact Contributor and Manager authority; the CLI exposes the three exact manager requirements/context reads separately from contributor commands (WS-CLI-001-27); bounded public Audit Authority lifecycle evidence with atomic project/task scoping and exact transition references; separate CLI audit commands consume those two existing Audit Authority GETs with explicit continuation; public manager create/screen/release use exact covered Project Manager authority, atomic audit and replay; claim/start/contributor context use exact-project Submitter grants; assigned context lists documents only and distinct `task.guide.read` verifies locked originals before delivery; separate manager context and system-Operator start; durable claim/start retry receipts with fresh authority and exact assignment checks; hidden exact-assignment invalidation with committed cause verification, delivery fencing, exact fixed-service authority and decision-bound immutable release evidence; atomic authority-loss publication and registered prefork delivery; PILOT-14 exposes both locked contribution types in ready rows and Contributor detail for active exact-project Submitters or Reviewers as unpaid or exact instrument/unit/quantity awards, without Finance binding facts; claim/start remain Submitter-only | The bounded local public durable-runtime journey passed; intended hosted operation remains unproven |
| Operator task CLI | **Existing public task operations consumed by the CLI** | WS-CLI-001-36 adds separate status-only project pages, exact-project locked-reference reads and explicit reasoned start override with caller-owned manual replay. Backend Operator authority, assignment consistency, locked lineage and audit remain decisive; contributor start has no fallback to override. | Native public-API proof is bounded to existing fixtures; hosted/deployed operation, other Operator workflows and published binary remain separate |
| CLI binary distribution | **Release path prepared; no public release** | WS-CLI-001-44 defines four native targets, `cli-v` exact-source versioning, deterministic archives and SHA-256 manifest, pull-request native installation/API/upgrade/rollback/removal smoke, and separately gated manual GitHub Releases publication | Confirm `cli-release` environment and immutable `cli-v*` tag ruleset; approve an annotated tag and first publication, then download and independently install all public assets. First-release smoke uses a same-source prior-version stand-in, not a previous published release; signing/notarization are absent |
| Operator artifact diagnosis | **Public API and CLI with exact Operator authority** | Eight bounded artifact GETs use current persisted system-Operator grants and exact AUTH decisions, with response-validated read commits and concealed denials. An independently guarded reasoned verification retry atomically records its decisions, recovery chain and audit; exact replay rechecks authority. The CLI consumes all nine routes, with malformed-lineage rejection and receipt-specific pagination. Signed PostgreSQL proof covers eligible retry, exact replay, wrong-resource refusal and revoked-Operator concealment. | Hosted S3 proof remains separate; diagnosis does not grant provider access or activate AWS |
| Bulk task import | **Public backend and CLI batch journey** | PILOT-02A supplies exact source custody; PILOT-02B imports 1..500 verified JSON rows under one immutable native batch, retains per-Task AUTH/TaskCreated facts, recovers exact original IDs with fresh authority and exposes batch status; actual 200-row, rollback, concurrent-wait and SQL-custody controls pass on PostgreSQL/MinIO. PILOT-02C adds atomic whole-batch screen/release with fresh per-Task authority, locked guide/policy custody and explicit CLI/CSV commands. WS-CLI-001-31 adds bounded, hash-checked CLI source download through public custody with no-overwrite local publication. Optional task-local criteria remain optional through single/bulk screening and release; required instructions and guide locks remain enforced. | No remaining PILOT-02 implementation gate; deployment and full contributor-lifecycle proof are separate |
| Contributor artifact preparation | **Public initial and checker-remediation entry** | One outer ZIP through the published preparation route; unreadable or structurally rejected ZIPs return sanitized non-retryable 422 feedback before PRE reservation or durable effects; bounded scratch inspection; canonical manifest; shared evaluation-content capacity and exact locked-policy checks before attempts or durable intent; platform and project prechecks; unchanged-work rejection; durable put intent; verification; capacity-charged ready admission; final handoff validates the exact activated historical guide through owner ports; same-key ready replay does not repeat checker or PUT. The preparing contributor reads back their own preparations with outcome, storage state, finding counts and intake findings (PILOT-READ-2); a Project Manager lists a project's preparations with finding counts only (PILOT-READ-3). CLI preparation, read-back, creation/replay and history consume these public owners | Bounded local API and native CLI journeys passed, including CLI rejected-intake recovery; hosted operation remains separate |
| Pre-submission intake checking | **Public selected entry with approved-guide lineage and bounded feedback** | One versioned Workstream default checker enforces safe ZIP/resource bounds, independently verified digest/manifest, high-confidence secret rejection and unchanged-work rejection. Missing summary/attestation produces warnings only. Successful preparation and its exact replay return the same bounded intake results as a blocked one (PILOT-READ-1), so nonblocking findings such as coverage gaps stay visible; CLI preparation prints them. Approved project PRE checks are immutable digest-pinned images run by the Rust service on verified read-only ART material. A supported system Operator API and explicit CLI commands register and read exact immutable external-checker entries with server-selected UUIDv7 identity, fresh authority and replay recovery. Durable selected custody takes TASK before CHECKERS; only a complete pass grants admission to the existing atomic Submission transaction. Both executable catalogues are removed. CLI preparation prints bounded contributor failure details. The same typed adapter also accepts the Smol node's fresh microVM execution receipts, with bounded concurrency and exact-lease recovery; upload-overlapped trusted intake remains separate. The hosted release configuration requires the existing service's gVisor/runsc profile and fixed private material paths on a dedicated runner host | Bounded local public Celery drill passed. Registry publication alone does not activate an image or repair an approved compilation. Work findings create no Submission and preserve in_progress; infrastructure failures retain recoverable outcomes. The release configuration is not deployed gVisor execution. Real-project setup must identify supported checks and missing capabilities before engineering, registration, approved-policy activation and production-limit selection; deployed hosted operation and public REV lifecycle controls remain separate |
| Immutable Submission creation | **Public admission-backed entry with explicit CLI consumption** | Canonical POST derives contributor identity and consumes a ready admission for initial work or exact checker remediation; durable pre-submit reservation and same-key ready recovery without rerunning checks or PUT; TASK-owned atomic creation with exact assignment ContributionPolicyVersion, locked policy lineage and service/database checked-packet custody; fixed-service artifact binding; exact replay, authority, concurrency and rollback proof. CLI creation/replay and bounded history use these public owners | Bounded local API and native CLI unpaid automated-acceptance journeys passed; live human-review revision and hosted operation remain separate |
| Post-submission evaluation and governed outcome | **Selected external execution and production completion routing** | Immutable approved image bindings, Rust service/SDK and typed ART callback grants; exact verified input custody, bounded normalized JSON results and phase authority. Project-owned digest-pinned images implement project requirements inside the generic service contract; the former named terminal-benchmark continuation is retired. The shared service does not interpret project-private build plans or provide a host-side continuation. Production outbox request/completion handlers run selected images and preserve exact restart/replay. True-policy success reaches review_pending; false-policy success invokes shared authorized FinalAcceptance and atomically creates the submitter ContributionRecord and complete frozen award set. Contributor-correctable failures retain exact remediation causes; a supported public system-Operator read and explicit CLI page list expose known finalized infrastructure failures; exact public/CLI retry invokes the existing owner with fresh authority and no spent contributor round. Supported uncertain request/completion reconciliation uses at most one immutable child to verify committed facts or invoke the existing owner after proving no effect; unresolved sources and an UNKNOWN child stay held. PILOT-READ-1 extends the single external result contract with findings carrying `check_id`, `path`, `line` and the `coverage_incomplete` level, and stores each finding immutably. A coverage gap without errors never auto-accepts: under a true ReviewPolicy it reaches review_pending, otherwise it returns to the contributor as `needs_revision` (`checker_coverage_incomplete`) without spending a revision round. Each Submission records its evidence-guarded attempt outcome and decision time. The bounded local public API/Celery drill passed both branches, prefork Celery process restart and late authority revocation | Live human review and human-triggered contributor revision remain separate #554 work. Unsupported or human-review-only approved requirements block false activation. New false/pass effects require LIVE REV bound to the current reviewed manifest; a known pre-effect refusal retries within the existing OUTBOX budget, then dead-letters if exhausted. The full hosted interruption drill for uncertain request/completion reconciliation remains outstanding. True handoff has no REV/CON prerequisite. Project-specific image correctness, registration, approved-policy activation and qualification on the intended runtime remain separate requirements. Former named-profile experiments are historical evidence. Hosted operation and deployment remain unproven |
| Operator uncertain-delivery CLI | **Existing public delivery routes consumed by explicit CLI commands** | WS-CLI-001-40 adds one project-bound page of finalized UNKNOWN deliveries and a deliberate reasoned, UUID-keyed reconciliation of one exact event. Fresh backend authority and classification remain decisive; a page never authorizes a later write. | Native signed PostgreSQL proof is scoped to an owner-produced source; a hosted interruption and deployed CLI remain unproven |
| Review queue and lease | **Hidden persistence foundation** | Queue/admission idempotency and ReviewLease/preference persistence; complete unavailable REV action/principal catalogue and typed AUTH contracts; ART-07A1 metadata-only packet contract and REV-03B immutable normalized packet persistence with live ingest custody; REV-04A Review/finding/resolution and completed request storage | Future resolver proof; canonical admission from `allow_review`; claim/lease/packet authority; lease copies the Submission-stamped policy version with no CON lookup |
| Review decision and revision | **Checker revision implemented; human decisions planned** | Review/revision policy identities and mutation authority, with `requires_second_review` fixed false through typed and database boundaries; REV-04A immutable Review storage; REV-04B source storage; REV-04C hidden source-neutral FinalAcceptance/TASK/CON participant; ARCH-04E2-B source AUTH and complete database/audit/outbox closure for hidden automated outcomes. PILOT-08 supplies required project-policy N>=0, assignment-scoped attempts, immediate exhaustion/release, atomic complete-context rebase and acknowledgement, setup-blocked clock pause/resume, PM attention/repair, and durable timeout rejection/reclaim. The CLI now makes the existing exact manager repair POST available with caller-owned key and source, preserving backend eligibility and replay authority | Genuine human decision authority/composition and revision integration remain #554 work under the same intended policy; hosted operation remains unproven |
| Contribution and compensation truth | **Hidden shared participant plus public policy administration** | ContributionPolicyVersion persistence; lifecycle-audit participant; adapter bindings and project-points units (internal Finance commands); public Finance policy administration; REV-04B shared acceptance source storage; CON-03C immutable ContributionRecord/CompensationAward storage; obsolete guide-keyed payment storage and task-local payment fields removed; CON-07 source-neutral submitter participant and complete frozen award sets; REV-04C composes it with FinalAcceptance/TASK effects in the caller transaction; 04F2 checker remediation and terminal infrastructure retry create no contribution or award. The bounded local public drill produced exactly one false-policy FinalAcceptance, submitter ContributionRecord and project-points award, with no Review | ARCH-04E2-B supplies exact routing authority/evidence, complete-set database closure and audit/outbox under REV-12A4A. Selected production request/completion delivery, 04F3 exact-cause replacement and the 04F4 owner with supported public terminal recovery are implemented; supported false-guide activation is implemented. Only actual Reviews create reviewer records. Obligation/root/ordinal custody remains deferred until fulfillment activation; no public recognition or fulfillment route is live |
| Contribution evidence reads | **Public fixed-membership REST and complete CLI export** | PILOT-10A exposes current human self-read and one-project JSON/CSV export for covering Project Managers or exact-project Finance Authorities. Each page has fresh authority and one repeatable-read response transaction; selections through 100,000 contributions retain page-one membership behind signed scope/filter/format/limit-bound cursors, with complete zero/one/two immutable awards, exact decimals, recorded-time filters and formula-neutralized CSV. The CLI follows JSON or CSV continuation internally with unchanged filters, validates cross-page order/identity, and publishes only the complete JSON result or one private no-overwrite CSV | No recognition mutation, fulfillment, payout, deployed-service or published-binary claim |
| Fulfillment, reconciliation, and audit | **Planned** | Shared audit foundations, provider-neutral adapter convention, AUTH-OUTBOX-02 live dispatcher authority, retained phase audit decisions, Celery delivery/recovery scans and CON-02B custody | Feature-specific handlers and authority, conditional award fulfillment, callbacks, idempotent recovery, reconciliation, bounded operational reads, and release controls |
| Runtime diagnostics | **Implemented foundation; release configuration prepared** | Closed structured logging, explicit API/Celery tracing, bounded metrics, safe correlation and optional typed OTLP export; hosted composition accepts only an optional HTTPS collector origin and keeps exporter outage outside product correctness | Restrict broker publishers; configure and secure collector/log access, egress, encryption and finite deletion; prove privacy, correlation and collector outage during the deployed release drill; no deployed monitoring claim |
| Frontend and pilot | **Local runtime foundation; release configuration prepared; project inputs prepared** | An original [Terminal Systems guide, example and five task briefs](../pilots/terminal_systems/README.md) provide inputs for fresh project onboarding. The fixed five-task sample, its checker, private runtime continuation and sample-only proof workflow are retired. Checkout-isolated Docker Compose API, prefork Celery, Beat, PostgreSQL, Redis and MinIO remain available, alongside digest-only hosted release composition and the generic external image service. The generic image command tests project samples and publishes a verified digest to ECR without registering or activating it. The opt-in [local agent-loop overlay](engineering/local-agent-loop.md) adds that service, a separately built networkless proof checker and operator scripts; Docker Desktop (Apple Silicon) proof covers registration, checker execution and lifecycle activation, not this project’s requirements. Setup supports inference and explicitly manager-authored rules through the same governed proposal path. Inference is limited to PRE/POST specifications, with strict JSON and bounded correction; PM policy choices remain separate. The retained real Terminal Systems proposal preserves null project limits on the unchanged guide; its independent review predates the PRE/POST-only scope, with ten explicit implementation/runtime gaps and no bindings in that retained proposal. The [project-owned PRE image](../pilots/terminal_systems/checkers/README.md) now implements layout and metadata intake with local rule and networkless container samples; it has no task-name allowlist or shared-runner project code. The independent offline gVisor feasibility spike remains historical mechanism evidence | Obtain a fresh PRE/POST-only correction of the retained proposal, then reconcile the implemented PRE image, implement the remaining POST checks and resolve their runtime/material gaps; register the required images, obtain corrected policy bindings and separate approvals, then activate, import, screen and release tasks. Then prove the real contribution journey, runtime limits and interruption recovery on the intended local/hosted stack. Guide assets, image builds and former sample results are not live-project evidence. Hosted identity/AWS configuration, isolation, diagnostics, backup/restore and broader macOS runtime proof remain; the agent-loop overlay still needs approved guide bindings, GitHub facts supplied to POST evaluation ([WS-GHPROOF-001](../.commitrail/initiatives/WS-GHPROOF-001/OVERVIEW.md)) and a persistent-stack FinalAcceptance drill |

## What Has Been Completed

### Security and platform foundations

- FastAPI, SQLAlchemy 2.x async, PostgreSQL, Alembic, Celery, and Redis form the
  locked backend execution stack.
- [Runtime diagnostics](engineering/observability.md) provide closed structured
  logging, sampled API/prefork Celery traces and bounded metrics through optional
  OTLP export. Public propagation cannot control sampling; sensitive payloads,
  credentials and exception text are excluded. Collector failures do not change
  product outcomes. Durable outbox recovery starts a new trace and retains only
  its existing diagnostic correlation, without new persisted trace fields.
- The schema has one fresh `0001_uuid7_v01` Alembic baseline. Generated record
  identities use UUIDv7 and native PostgreSQL UUID relationships; meaningful
  natural keys and external request tokens retain their semantics. Old stamped
  development databases require explicitly scoped recreation, not conversion or
  compatibility stamping. Local Compose uses a separate UUIDv7 database volume.
- The [local pilot stack](engineering/local-pilot.md) runs API, the existing
  prefork Celery topology, its recovery scheduler, PostgreSQL, Redis and MinIO
  under one explicit Compose project. Every published port is checkout-local;
  containers, network, retained data and bounded scratch are project-scoped.
  Its Flow-HMAC helper creates identity only, while the existing trust-root and
  grant operations remain the sole local authority path.
  The opt-in [local agent loop overlay](engineering/local-agent-loop.md) adds
  the existing checker service in `docker-dev` mode with a networkless
  proof checker that compares proofs with GitHub facts and fails closed until
  POST evaluation supplies them; selecting it into guide rules remains
  separate work.
- AWS S3 is the hosted artifact target, MinIO proves the storage protocol in
  development and CI, and all storage access stays behind `ArtifactStore`.
  Development/CI MinIO uses a shared pinned-source build; existing artifact
  volumes and real S3-protocol tests remain unchanged. Native AWS composition
  is guarded by immutable, exact three-probe activations bound to reviewed role
  trust-policy digests and distinct workload subjects at startup, each SDK call
  and provider-derived terminal commit. Certificate-based external hosting also
  binds the exact Roles Anywhere trust-anchor and profile state. The
  [setup guide](operations_aws_roles_anywhere.md) covers generated configuration,
  private certificate custody and renewal. Real AWS connection diagnostics passed
  immutable upload/readback and role/anonymous isolation; database activation and
  the public guide/Submission custody drill remain separate requirements.
  Proof clients use the configured region;
  settings reserve a fixed 120-second proof sequence, and ART/PostgreSQL reject
  overlong activation using database time. Lazy configuration outages remain
  recoverable instead of becoming false integrity conflicts. The
  [timing correction](../.commitrail/changes/aws-activation-failure-and-timing-corrections.md)
  preserves retained evidence; cadence and commit-latency margin still need live
  measurement. No hosted readiness claim exists
  until the intended environment runs those identity-separated live probes and
  the public guide/Submission custody drill.
- Private extraction scratch is bounded by `ArtifactScratchManager`; it is not
  durable artifact storage.
- Cross-module behavior is moving through explicit public ports under the
  modular-monolith boundary. New private edges are prohibited and touched debt
  is reduced incrementally.
- GitHub CI distributes the backend suite across semantic lanes, rejects
  skipped/deselected tests and requires behavior, boundary and real API proof.
  Coverage is diagnostic only, with no percentage gate or test-count target.
  Redundant coverage-only reruns are removed; their tests remain in full-suite lanes.
  Its 16-lane allocation uses seven project lanes, five task lanes, three
  shared-foundation lanes and one schema lane. Backend preflight, suite and
  aggregate commands use the checked, frozen dependency lock. Database resets
  batch trigger commands within the existing transaction while retaining full schema checks;
  authorization preflight runs alongside lanes and remains mandatory at fan-in.
  Ordinary CI databases use bounded private RAM-backed storage with write
  settings verified; schema-contract and aggregate databases stay disk-backed.
  Hosted runtime remains measured rather than guaranteed.

### Identity and authorization

- Workstream verifies external Flow identity tokens but owns no login,
  password, or primary authentication session.
- External subject identity resolves through ActorIdentityLink into a stable
  internal ActorProfile.
- Human roles and fixed-service authority remain separate and fail closed.
- Exact-project contributor grants support only `submitter` and `reviewer`.
  Unsupported `adjudicator` inputs are rejected; adjudication remains deferred.
- Project and administrative grants, resource guards, lifecycle revalidation,
  idempotency, rate controls, audit evidence, and opaque prepared authority are
  implemented. Draft-guide PATCH and review/revision-policy PUT historical
  receipts require the same actor/link and a fresh covered Project Manager grant
  before exact replay; they do not reselect a current policy or repeat the write.
  See the [bounded replay authorization repair](../.commitrail/changes/guide-policy-replay-authorization.md).
- A reusable [real-HTTP authorization drill](engineering/external-api-drill.md)
  exercises twenty human profiles, the actual local administrator bootstrap,
  all five administrative role definitions and applicable scope boundaries,
  submitter/reviewer grants, self-protection, replay and lifecycle revocation.
  Separate rollback-only probes exercise the four last-effective-administrator
  count guards on stored authority; isolated off-by-one mutants verify that the
  assertions detect those defects. These are local synthetic-Flow checks, not
  deployed identity-provider certification or exhaustive API-field coverage.
- The [five API drill defects](engineering/external-api-drill-findings.md) are
  repaired: project name/slug and guide version enforce existing storage limits,
  guide PATCH now excludes the superseded inline-content field, and
  unsupported project-role input is rejected before mutation. Both original
  drills passed again on merged main after that repair. The extended drill adds
  populated pagination/cursor checks, nested qualification boundary probes and
  separate value/predicate/shape/request evidence. The
  [fixed 29-operation matrix](engineering/external-api-drill.md#fixed-29-operation-acceptance-matrix)
  records the completed client-contract scope and its field/authority/replay
  checks for the MCP handoff, across the documented frozen executions. New
  provider-dependent operations require their own evidence;
  they do not repeatedly reopen this original selection. Route discovery alone
  is not readiness.
  The [MCP initiative](../.commitrail/initiatives/WS-MCP-002/OVERVIEW.md)
  now fixes the caller-token design: the adapter forwards each caller's Flow
  bearer unchanged and Workstream verifies it. The
  [local one-tool experiment](../experiments/mcp_caller_token/README.md) passed
  15 real-process checks and 24 focused tests, including first admission and
  caller isolation. Independent packaging and the three bounded self-service
  tools are delivered through WS-MCP-002-02: profile read, profile update and
  exact-project authorization context. WS-MCP-002-03 adds six administrative
  reads for permission/role definitions, grants and actor/identity projections;
  WS-MCP-002-04 adds issue/revoke grant mutations through current Workstream authority;
  WS-MCP-002-05 adds actor and identity-link lifecycle mutations; WS-MCP-002-06
  adds project creation and authority-selected project reads; WS-MCP-002-07 adds
  candidate discovery and project-role grant issue/list/read/revoke; WS-MCP-002-08
  adds guide declaration and summary-only draft editing; WS-MCP-002-09 adds
  review and revision policy selection and completes the original 27-tool catalogue;
  WS-MCP-002-10 adds 20 workspace/evidence/policy bindings. Four public-domain
  batches and assembled release proof remain. This is still a custom
  authentication adapter, not a public deployment or a certified release.
  The [CLI foundation](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-01.md)
  provides `whoami` and `project access PROJECT_ID` through those public REST
  contracts. [CLI profile editing](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-02.md)
  adds caller-owned display-field set/clear through public PATCH, with explicit
  uncertain-outcome reporting and no automatic retry.
  [CLI project inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-03.md)
  adds the existing public project read, preserving server-selected full/minimal
  fields and concealed foreign/revoked/suspended denials.
  [CLI system project catalogue](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-46.md)
  adds a separate bounded ID/name/status page for the four current system
  project-reader roles; exact-grant contributor discovery is unchanged.
  [CLI administrative inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-28.md)
  adds six explicit public privileged reads: exact actor/profile and one
  identity link, system/project-scoped grant pages, and permission/role
  catalogues. Self-service stays separate; each read uses current backend
  authority and does not authorize a later mutation.
  [CLI administrative mutations](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-39.md)
  expose eight existing public POSTs beneath that same command root: fixed
  service provision, separate actor/link lifecycle transitions, and exact
  administrative grant issue/revoke. Caller-owned keys and strict receipts
  do not move authorization, final-administrator protection or replay policy
  into the client.
  [PILOT-02A task-import source custody](../.commitrail/changes/pilot02-task-import-source-custody.md)
  provides public covered-PM declaration, exact JSON upload, status and verified
  download with immutable failed/abandoned-source retention and existing ART
  automatic recovery, proven through public routes on PostgreSQL and MinIO.
  [PILOT-02B atomic JSON import](../.commitrail/changes/pilot02-atomic-json-draft-import.md)
  adds public atomic DRAFT creation and native batch status with exact-file replay,
  verified source ancestry and per-row canonical AUTH/TaskCreated evidence. Its
  actual 200-row, rollback, lock-wait and immutable SQL controls pass on PostgreSQL
  and MinIO. PILOT-02C completes explicit batch screen/release and CLI conversion.
  The [PILOT-02C bulk/CLI implementation](../.commitrail/changes/pilot02-bulk-transitions-cli.md)
  implements caller-root canonical SCREEN/RELEASE composition and separate CLI
  source/import/status/screen/release commands with local CSV-to-JSON conversion.
  [CLI source download](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-31.md)
  adds verified retained-original read-back through the public source status and
  content endpoints without direct provider access.
  Historical exact-source PostgreSQL/MinIO proofs cover 200/500-member
  import-screen-release journeys, fresh replay, rollback, native waits, revocation
  and immutable custody, plus the built-CLI 200-row socket journey and equivalent
  CSV/JSON bytes and verified-source recovery. [PR #543](https://github.com/Flow-Research/workstream/pull/543)
  delivered the context-reuse repairs and final native/hosted verification.
  The [optional-criteria correction](../.commitrail/changes/pilot02-optional-screening-criteria.md)
  completes the remaining screening gap from
  [issue #489](https://github.com/Flow-Research/workstream/issues/489): omitted/null
  task-local criteria survive single and bulk SCREEN/RELEASE under exact guide
  locks, with supplied text preserved and required instructions still enforced.
  Correctness and completeness passed; the diagnostic CI timing target remains
  unmet. These results do not claim deployment or complete submission/review support.
  [CLI manager task browsing](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-04.md)
  adds one-page task discovery and exact task detail through existing manager
  reads, with server-owned live authority and opaque continuation.
  [CLI contributor discovery](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-05.md)
  adds ready-task pages and contributor instructions through public reads,
  preserving exact-project contributor scope and assignment visibility without
  claiming work. PILOT-14
  displays the task-locked ContributionPolicyVersion UUID and both unpaid or
  exact award terms in ready rows and task detail to a Submitter or Reviewer,
  while claim/start remain Submitter-only.
  [CLI contributor claim/start](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-06.md)
  adds the existing public writes with explicit retry keys, server-owned
  assignment/lineage, fresh-authority replay and uncertain-outcome handling.
  [CLI Operator task inspection and start](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-36.md)
  consumes the distinct status-only queue, exact locked references and reasoned
  start override. These reads do not authorize the later write; current system
  Operator authority, assignment and replay remain backend-owned.
  [CLI contributor context](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-07.md)
  adds the governing guide, exact policy selectors, server hints and locked
  intake requirements through public reads. Hints are not authority; no files
  are fetched and no policy is evaluated locally. This CLI command does not
  invoke the now-public Submission intake operations.
  [CLI project creation](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-08.md)
  creates a draft shell through the public POST, with exact 201 response,
  caller-owned replay custody and explicit uncertain outcomes. It does not upload,
  approve or activate a guide. Committed recovery follows the existing project's
  API contract, not task replay authorization semantics.
  [CLI guide declaration](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-09.md)
  creates draft guide metadata, required illustrative tasks and document targets
  through public POST. The API reauthorizes exact replay and setup waits for
  document upload; the declaration command does not upload, approve or activate
  the guide.
  [CLI guide configuration](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-26.md)
  exposes the public draft-guide PATCH and separate review/revision policy PUTs.
  Caller-owned keys and exact `If-Match` selectors preserve replay and stale
  precondition boundaries; backend authorization for new writes and exact
  replays, policy semantics and activation remain decisive. The backend
  [exact-replay authority correction](https://github.com/Flow-Research/workstream/pull/621)
  does not transfer authorization decisions to the CLI.
  [CLI guide original upload](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-10.md)
  sends one declared document through the public binary POST, with bounded
  streaming, explicit replay custody and SHA-256/size-bound storage receipts.
  Unconfirmed storage is an unknown outcome, not success. Upload does not imply
  setup completion, policy approval or guide activation.
  [CLI setup inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-11.md)
  reads the latest exact-guide setup and compilation lineage through the public
  diagnostic GET. Read success does not establish compilation success, policy
  approval or guide activation; no polling or setup execution is added.
  [CLI administrative guide inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-32.md)
  exposes seven existing public GETs for retained sufficiency/artifact evidence
  and the current active/effective/pre-submit chain. The two historical lists
  return only the newest 100; exact IDs permit older retained inspection.
  These reads neither approve a policy nor authorize a subsequent write.
  [CLI human sufficiency writes](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-38.md)
  record one diagnostic or eligible warning acknowledgement through existing
  public POSTs with fresh authority and exact caller-key replay. They do not
  replace owner-produced setup or create an approved artifact policy.
  [CLI manual artifact-policy drafts](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-41.md)
  consume the existing public POST/PATCH after authoritative finalized setup.
  Create binds the source snapshot; update selects an exact manual draft and
  expected hash. Fresh authority and exact replay remain backend-owned; neither
  operation approves an effective policy or activates a guide.
  [CLI proposal inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-12.md)
  reads one explicitly selected finalized proposal with its complete findings,
  inventory and intake/evaluation proposals. Blocked/historical results are
  observations, not automatic decisions.
  [CLI intake approval](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-13.md)
  submits the exact public pre-submission decision with explicit warning
  acknowledgments and caller retry custody. Its immutable receipt is not
  post-policy approval or post-policy job delivery.
  [CLI post-policy inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-14.md)
  reads an explicitly selected derived policy, unified findings, activation
  selectors and saved correction, preserving historical/non-current observations.
  [CLI evaluation approval](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-15.md)
  commits the separate exact-policy decision with caller-prepared input and retry
  custody, complete receipt validation and fresh backend authority on replay.
  [CLI evaluation correction](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-16.md)
  sends the inspected target and manager feedback to the existing public write;
  the receipt identifies one saved unified setup successor, not dispatch or
  activation. Exact replay retains backend authority and adds no successor.
  [CLI guide correction and dispatch](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-17.md)
  saves feedback for an exact finalized proposal and explicitly dispatches the
  saved unified successor. Complete response identity and manual-only recovery
  protect the journey; dispatch diagnostics are not completion or activation.
  [CLI guide activation](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-18.md)
  sends caller-prepared, separately approved selections once to the public
  manager activation operation and validates its complete immutable receipt.
  Readiness, contribution-policy publication, fresh replay authority and
  supersession remain backend-owned; supported false-guide activation follows
  the current backend readiness rules, not a client policy decision.
  [CLI manager preparation](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-19.md)
  adds separate public draft creation, policy-locking screening and deliberate
  release with full management receipts and current-authority manual replay.
  Bulk import and submission have separate explicit commands; the retained
  contributor journey proves the prepared ready task can be claimed and started.
  [CLI revision repair](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-35.md)
  exposes the already-public exact parent or missing-root manager repair POST.
  The backend still decides authority, current lineage, clock and disposition;
  this adds no human Review decision or automatic repair.
  [CLI contributor role decisions](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-20.md)
  issue/revoke exact-project Submitter/Reviewer grants through public AUTH POSTs,
  with explicit qualification evidence, full receipts and current-authority
  manual replay. The real contributor journey retains claim/start and revoked
  grant denial; Reviewer-only authority still cannot claim/start. AdminRole
  administration and automatic grants are not added.
  [CLI grant inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-21.md)
  reads one filtered public grant page or one exact grant with complete
  qualification/provenance and revocation facts. Cursors remain opaque,
  continuation is explicit and each request requires fresh backend authority.
  Observed history does not authorize subsequent writes.
  [CLI candidate discovery](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-33.md)
  consumes the existing two-field, exact-project public AUTH page for a covered
  Project Manager. Backend authority and cursor scope remain decisive; the CLI
  neither enumerates all actors nor qualifies or grants a candidate.
  [CLI contribution-policy inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-22.md)
  discovers current published/open-draft selectors and reads backend-selected or
  explicit retained versions with complete rules and exact award quantities.
  Real API proof covers unpaid policy history, current Finance authority,
  suspension/revocation and project/version isolation; compensated precision is
  process-boundary proof. Reads do not publish, activate, pay or infer readiness.
  [CLI Finance decisions](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-23.md)
  add explicit draft creation, complete rule replacement, publication and
  retirement, preserving exact selectors and caller retry keys. Original event
  replay requires current authority; publication remains separate from guide
  activation. The native unpaid journey verifies stored events and denied writes.
  [CLI contribution evidence](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-24.md)
  adds human self and authorized project reads with type/time filters, complete
  source/award projections and exact private CSV downloads. Earned award facts
  are not proof of external payment; reading records does not activate lifecycle writers.
  [CLI submission and findings](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-25.md)
  adds public ZIP preparation, separate admission-backed creation/replay and bounded
  history/checker reads. Findings are not acceptance. Full public setup integration,
  hosted operation remain separate. PILOT-08 supplies the public contributor
  revision-context summary, acknowledgement, paused clock, and exhaustion/timeout
  history projections.
  [CLI task audit reads](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-34.md)
  add separate exact-project/task Audit Authority locked-lineage and one-page
  lifecycle-evidence commands. Structured continuation requires fresh server
  authority; neither read includes manager policy summaries or full audit export.
  [CLI Operator checker operations](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-29.md)
  expose explicit immutable registry registration/read and project-bound
  known-terminal retry discovery/command. Backend AUTH and lifecycle custody
  remain decisive; registration is not execution enablement.
  [CLI manager task evidence](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-27.md)
  exposes existing exact project/task requirements and contexts, task Submission
  history, exact Submission and retained checker runs through separate manager
  reads. Each page reauthorizes; checker evidence remains distinct from acceptance.
  [PILOT-02 batch CLI](../.commitrail/changes/pilot02-bulk-transitions-cli.md)
  shares the binary and adds explicit source/import/status/screen/release with
  local CSV conversion. [WS-CLI-001-31](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-31.md)
  adds a separate verified-source download through public custody. Evidence export works independently of task origin;
  neither command family creates a dependency on the other.
  [PILOT-13 assigned-guide access](../.commitrail/changes/pilot13-assigned-task-guide-documents.md)
  lists exact locked originals in assigned contributor context and streams
  authorized, fully verified ART bytes. `task guide` lists or safely downloads
  them; setup examples remain private. Successor activation does not move a
  task's locks; a committed fixable failure prepares the next context and a
  contributor-visible change summary. Live human decision composition remains later work.
  Built-binary HTTP
  integration and isolated real-API proof accompany
  the package. [WS-CLI-001-46](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-46.md)
  adds minimal system project-reader discovery through one public API page and
  `project list`, without changing exact-grant `me projects`. Further public
  commands and the optional TUI remain planned; binary-release automation is
  prepared, while protected first publication remains outstanding. CLI reads
  do not complete unfinished product lifecycle work.
  The public-client drill targets currently usable APIs only; hidden and
  unfinished lifecycle routes are not completion targets. Draft-guide policy
  probes additionally cover optional fields, conditional headers and exact
  selected-lineage preservation after rejection, including preservation of the
  human-review mode when omitted during replacement.
  Endpoint-by-endpoint probes also check exact health output, full self-profile
  business-state preservation after rejected updates, and contributor context
  actions/revocation with real foreign-project concealment. These strengthen
  evidence within the selected 29 canonical operations, not obsolete routes or
  an exhaustive API-completion claim.
  Catalogue evidence compares every registered permission and the full five-role
  definition matrix. Administrative grant probes compare complete provenance,
  reason and timestamp fields across issue/revoke replay, retaining independent
  stored-state checks. Catalogue membership does not imply action activation.
  Contributor-discovery drill checks enforce the privacy-safe two-field row,
  cursor scope/limit binding and exact candidate membership across existing
  actor/link lifecycle transitions. These checks do not equate discovery with
  contributor authority or certify the entire public API surface.
  Project-role field probes bind issuance and qualification capture to the known
  manager grant and compare complete public state across issue/revoke replay
  and conflicts for both submitter and reviewer roles.
  Closure probes include exact persisted administrator-history fields, all
  lifecycle reason/key partitions and conflict codes, document declaration
  limits/order/labels/media types, service exclusion from human discovery,
  ineligible grant targets and stored cross-project grant substitution. Local
  bootstrap/count-guard evidence remains distinct from HTTP API observations.
  [API-DRILL-007](engineering/external-api-drill-findings.md#api-drill-007-embedded-nul-in-canonical-profile-fields-becomes-503)
  records the reproduced self-profile NUL defect and its repair: both editable
  fields reject the unsupported character at request validation with 422 rather
  than passing it to storage. The drill retains unchanged-business-state controls.
  [API-DRILL-008](engineering/external-api-drill-findings.md#api-drill-008-nul-project-selector-becomes-503)
  records the matching authorization-context selector repair: NUL is rejected
  with 422 while project-ID lookup and project concealment remain intact.
  [API-DRILL-009](engineering/external-api-drill-findings.md#api-drill-009-project-and-guide-text-nul-becomes-503)
  records the project/guide text repair: the original eight inputs rejected NUL
  at request validation instead of returning a storage failure; the guide
  document cutover removes inline-content inputs and retains validation on
  surviving fields. Dedicated
  regressions check selected stored-state preservation, same-key recovery and
  replay. This does not certify the unfinished all-field external-client handoff.
  API-DRILL-006 is repaired with a bounded project-role issuance envelope that
  accommodates the existing public qualification maxima; other authority
  mutations retain their original limit. Full-max parser/PostgreSQL regressions
  cover both roles, persistence, replay, conflict and unauthorized rollback.
  The resumed real guide-upload drill reproduced
  [API-DRILL-010](engineering/external-api-drill-findings.md#api-drill-010-successful-guide-document-replay-returns-stale):
  an exact retry of a successfully stored document returned `stale`. The repair
  returns the authorized terminal result without another provider operation.
  The related inactive-resolver denial now returns concealed 404 and retains
  its canonical audit rather than escaping as 500. Local real PostgreSQL/MinIO
  regression and genuine-document replay passed; this does not establish
  complete field-level client readiness.
  [API-DRILL-012](engineering/external-api-drill-findings.md#api-drill-012-administrative-grant-reasons-containing-nul-return-503)
  closes the same validation gap in administrative grant issue/revoke reasons:
  NUL rejects before storage, while valid Unicode and same-key recovery remain
  supported. This does not change authority or retained grant history.
  [API-DRILL-013](engineering/external-api-drill-findings.md#api-drill-013-service-provisioning-subject-containing-nul-returns-503)
  applies the same early rejection to service provisioning subjects, preserving
  exact Unicode identity and same-key recovery without changing service authority.
- Guide ingestion and exact document reads, artifact verification/recovery,
  contributor preparation, Submission consumption/binding, unified compilation
  request/execute, and deterministic projection authority are implemented at
  their current hidden or live boundaries.

### Project Guide and artifact pipeline

- Project Managers can authorize guide-source ingestion for projects they are
  permitted to manage.
- Guide originals remain immutable in ArtifactStore; PostgreSQL holds metadata,
  versions, custody and the required task-example list. Guide creation requires
  at least one nonblank example and the complete nonempty document list. The
  response supplies document IDs for the public binary upload route; no separate
  source-snapshot creation call remains. A starting idea is sufficient and optional
  example fields do not repeat requirements from the guide. Each snapshot/run
  binds the exact version's examples. Upload admission accepts PDF, DOCX, PPTX and byte-preserved UTF-8 Markdown (`.md`)
  and checks bounded format, digest and size.
  Committed originals do not bypass the separate verification required for
  submission ZIPs. Embedded document bodies and extractors are removed.
- Committed original-document readiness automatically runs one unified compilation
  through Celery. It persists sufficiency findings and separate pre-submit and
  post-submit proposals, then projects the sufficiency and artifact-policy
  components and atomically finalizes the setup at draft output. A blocked guide
  ends at sufficiency evidence, with no policy projection. Capability gaps alone
  preserve a warning-ready draft and continue blocking activation. Each new
  atomic requirement includes classification rationale; supported and missing
  PRE/POST checks include one typed specification with stage/budget, inputs,
  checks, outcomes, test cases and dependencies. Its canonical result retains
  exact registered digest-pinned image matches and one evidence-linked engineering
  suggestion for each required missing pre-submit or post-submit check. Fully
  covered projects need no suggestions. PRE covers static and other checks that
  reliably finish within 60 seconds before Submission, including durable/polled
  execution; longer and model work belongs to background POST. POL-05B exposes the complete POL-05A review package;
  AUTH-12F4 supplies exact manager authority; suggestions cannot register or activate a checker. Runtime, model/provider and instructions are independently
  configured and bound to the attempt. The agent reads assigned originals with bounded trusted read/search tools
  through the isolated parser and assesses them with every supplied task example;
  exact grants exclude other projects and runs. The provider-free
  `manager_authored` runtime instead converts one manager-uploaded rules
  document into the same untrusted result; it reads every original through the
  same grant, records those reads without provider resources, and stores
  provider, API and model `none` on the attempt. Known invalid inference output
  receives at most two value-free corrections across drafting and review within
  the original execution budget; exhaustion ends terminally. Exact replay never
  starts a second inference.
  The model-facing default capability names exactly four platform guarantees:
  bounded safe ZIP handling, received-byte/manifest identity, high-confidence
  secret detection and unchanged-work detection. Required project files, layout,
  metadata and content rules require project checks; artifact-policy metadata
  does not make the default enforce them. The existing package-size rule enforces
  verified expanded bytes, now explicit in the proposal schema.
  Setup leaves absent project file/package limits null, matching canonical policy;
  guides need not repeat platform ceilings. ART independently enforces configured
  upload/archive safety limits and storage admission, and explicit project limits
  add restrictions without relaxing those controls. The CLI proposal reader
  preserves these optional limits.
  The optional `maximum_archive_entries` policy adds a compiled, blocking normalized
  outer-ZIP tree entry limit, including implied parent directories, preserving tighter default
  limits and ART safety ceilings. This does not expose public submission intake.
  The separate optional `maximum_archive_size_bytes` rule enforces the entire
  compressed ZIP's verified byte count, including archive metadata, independently
  of expanded content size; the same default-floor and locked-plan controls apply.
  The [post-POL-05B genuine-guide replay](engineering/external-api-drill-findings.md#post-pol-05b-replay-nested-archive-capability-gap)
  exposed an unrequested nested-archive restriction in the assistant's drill
  guide. The human removed that fixture requirement: members may have any file
  type, including nested archives, subject to existing safety/resource checks.
  No nested-archive detector is required by this decision. The corrected guide's
  replay reached draft readiness with 34 expected HTTP checks and independently
  verified stored limits; the old failed run remains historical evidence.
  Transient pre-send retries use bounded backoff and a circuit breaker; the
  default request timeout is 300 seconds, separate from the whole-run timeout.
  POL-05B exposes review, pre-submission approval and correction successors
  using POL-05A custody. Approval requires selected pre-submit checks to appear
  in the plan compiled from the actual policy; complete-proposal access requires
  Project Manager guide-management authority. Public manager review and manual
  dispatch use AUTH-12F4 authority. Committed manager requests enter the same
  Celery execution pipeline with atomic queue intent and no second attempt.
  The authorized latest-setup read exposes saved correction/predecessor identifiers
  so a replacement manager can discover and explicitly dispatch a pending correction
  after the creator is revoked, without the original creation receipt.
  Superseded post-submit setup/approval/correction routes are removed. POL-06A
  implements hidden deterministic projection of the saved post-submit proposal,
  complete draft read, separate approval and correction through the existing
  unified successor. Immutable operation receipts replace role-string authority
  in affected readers. AUTH-12G supplies live fixed-service and exact-project manager adapters. POL-06B exposes the complete post-policy read, separate approval and correction, with automatic deterministic derivation and approval-driven recovery. Real Terra runs through API upload,
  MinIO, the Celery handler and PostgreSQL proved both blocked findings and ready
  draft policy outcomes, with exact replay and provider cleanup. Broker delivery
  was scripted in these drills; live Celery transport and broad semantic accuracy
  are not established by them. A later public-client diagnostic used an isolated
  Redis broker and actual Celery delivery with two original shareable PDFs;
  it reached a persisted `sufficiency_blocked` report and verified both stored
  originals. The subsequent clean `869a1d71` public-client run passed 36 cases,
  including repaired replay, findings-to-setup lineage, and inactive-resolver
  denial with unchanged setup and stored originals. Its real model identified
  unsupported archive/content intake checks and post-submit audit evaluation
  required by that project. This does not establish broad semantic accuracy,
  manager approval or active project policy.
  Earlier probes omitted task examples and establish
  execution mechanics only. A subsequent real Terra run with assigned private documents
  and two task examples proved exact example delivery, original access, persisted
  findings, cleanup and replay. It correctly stopped for absent project-wide
  file/archive size limits, without demanding one selected paper. This proves
  that bounded blocked-result flow; it does not establish a ready policy for
  those inputs or broad semantic accuracy. CP07 supplies complete-guide activation and immutable ContributionPolicy
  binding, exposed through AUTH-18 public manager activation. It requires both exact
  approvals and current complete review/revision inputs, supersedes the selected
  prior guide and promotes a draft Project atomically. Active-guide reads require
  the committed binding. AUTH-12H supplies live exact-project manager authority;
  CP08 locks and carries exact policy lineage through Task, TaskAssignment and
  Submission. ARCH-03D completes the hidden final intake handoff through exact
  historical TASK/PROJECTS ports; ARCH-02I-B exposes the public cutover.
- Contributor ZIP preparation uses one verified byte lineage from scratch
  inspection through durable admission and eventual Submission binding.

### Contribution and review foundations

- Finance Authority can manage compensation adapter bindings through the
  hidden, authorized boundary. CP07A aligns policy/binding mutations with AUTH
  by locking authority before product resources, and reconciles the database
  audit vocabulary for the existing binding actions. CP07 guide activation/binding, AUTH-12H live exact-project manager authority
  and AUTH-18 public manager activation are delivered.
- CP05A exposes ContributionPolicy discovery, read, draft update, publication
  and retirement through exact human Finance Authority, preserving immutable
  lifecycle history and default-denied uncomposed owners. Compensation-binding
  administration remains internal; public manager activation uses exact published
  selectors without granting Finance privileges.
- Finance Authority can create a project's `project_points` compensation unit
  through the internal `contribution.compensation_unit.create` command, so a
  published policy can award project points without direct database writes.
  Like binding administration it has no public route; the local operator
  script `backend/scripts/provision_project_points.py` composes it with the
  adapter actor and binding. Money-unit enablement and unit retirement remain
  unimplemented.
- CP06 supplies internal caller-transaction validation of the exact selected
  ContributionPolicy version and its complete graph/resources. New guide binding
  requires the active current published selector. Controlled revision validates
  the caller’s exact guide-bound version, not a newer global selector. Guide
  activation and checker revision preparation use that custody; genuine human
  Review revision integration remains #554 work.
- REV queue/admission and lease/preference persistence foundations are merged.
- The governing rule is fixed: one ContributionPolicyVersion contains both the
  `accepted_submission` and `completed_review` rules. It is bound before task
  readiness and carried as immutable attempt lineage.

## Current Work And Immediate Order

Only open pull requests describe transient work. Use the repository's
[open pull-request view](https://github.com/Flow-Research/workstream/pulls) to
see whether any item below is already under review.

[PILOT-15 / PR #514](https://github.com/Flow-Research/workstream/pull/514)
delivers byte-preserved UTF-8 Markdown (`.md`) guide admission, setup-agent reads
and task-locked contributor REST/CLI reads alongside PDF, DOCX and PPTX originals.
This guide-format capability is complete; it adds no downstream intake or
acceptance activation.

Delivered capabilities are summarized in the [scoreboard](#end-to-end-lifecycle-scoreboard);
their evidence is linked under [completed work](#what-has-been-completed).
The [dependency and ownership plan](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
owns implementation sequencing. The existing checker phase service supports
hidden pre-submit execution/replay and hidden durable post-submit execution.
Exact post-submit service authority and the hidden 04E2-B authorized outcome
operation are implemented. 04F2 adds the hidden policy-independent remediation handoff, 04F3 adds
hidden exact-cause replacement intake and 04F4 supplies the retry owner; the
supported public Operator discovery/retry path now invokes it. PILOT-04
registers selected request and completion delivery in production composition; passing
false-policy results use the shared atomic acceptance operation. ARCH-02I-B
publishes admission-backed initial and checker-remediation Submission entry.
Live setup does not wait for downstream task/checker execution.

The [first complete contributor milestone](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#first-complete-contributor-milestone)
records the delivered checked-input, capacity and atomic Submission/request
steps, public admission-backed entry, hidden authorized outcomes and B8
completion delivery. ARCH-04E3-B supplies supported false-guide activation and
REV manifest readiness; the bounded local public durable-runtime drill passed. A setup-fault hold is future safety work
because the current completion classifier has no `task_setup_blocked` outcome. Human review/revision
runtime follows that milestone. Initial public intake covers initial submissions
and checker remediation; the historical requirement to complete human-review
revisions before any public intake is not adopted. The delivered remediation path stays independent of an already-live false branch.

The broader v0.1 sequence below retains later scope:

1. **Integrate the delivered guide/task foundations.** CP08 lineage and
   ARCH-03B1–03B9 owner operations are delivered at the exposure boundaries
   listed above. ARCH-03C1 supplies exact reconciler authority and decision-bound
   receipts. ARCH-03C2 supplies atomic originating publication and production
   delivery with enforced prefork topology. ARCH-03C3 supplies exact-authorized
   manager task create/screen/release; ARCH-03C4 supplies the three public queues;
   ARCH-03C5 supplies exact-authorized detail and requirements; ARCH-03C6 supplies
   distinct locked-context reads; ARCH-03C7 supplies bounded public Audit Authority
   history access. AUTH-18 exposes manager activation context and the canonical
   guide activation POST. PILOT-02A delivers canonical JSON import-source custody
   with its linear migration and public-route PostgreSQL/MinIO proof;
   PILOT-02B adds atomic DRAFT import and native batch status under current PM
   authority. PILOT-02C adds the explicit atomic batch screen/release and CLI/CSV
   journey; WS-CLI-001-31 adds read-only CLI source download. Source/import does not acquire screen/release
   guide locks. Guide activation requires exact
   current compilation, sufficiency, separate pre/post approvals, review/revision
   inputs and an explicitly selected published ContributionPolicyVersion.
   Registered checker implementations and configuration are checked without a
   Task, Submission, completed checker run or live REV implementation.
   The operation replaces superseded economic readiness. Retained economic
   data and downstream TASK consumers remain until their scoped cutover;
   deleting retained data is not authorized by code cleanup.
2. **Produce current post-submit evidence and policy-governed routing.** ARCH-04B's
   hidden exact input materialization and ARCH-04B2's hidden output custody are
   delivered. ARCH-04C executes the locked structural plan internally, supports its
   empty output set and persists one current result with its completion event.
   ARCH-04D1 enforces canonical ART material lineage for every terminal result
   retaining material, with database rejection, rollback and safe-upgrade proof.
   ARCH-04D2 supplies exact input/execute/finalize service authority and durable
   receipt custody. ARCH-04E1A supplies one immutable route-neutral source table,
   detached facts and source-neutral accepted-effects types. CON-03C adds immutable contribution/award storage. REV-12A1 supplies disabled controller/fence mechanics with PostgreSQL-enforced root-transaction checks, including raw-SQL savepoint rejection. CON-07 supplies a hidden source-neutral submitter participant and complete frozen award-set staging/replay under that caller-root fence. REV-04C composes FinalAcceptance, TASK accepted/completed effects and that CON participant in one hidden caller-owned transaction for either source. It adds no AUTH receipt, handler, route, currentness guarantee, audit/outbox consequence, fulfillment root or reviewer participant.
   Both branches have delivered request reservation 04E1B-A, hidden AUTH
   preparation 04E2-A and complete authorized outcomes 04E2-B. B8 supplies hidden completion delivery;
   04E3A composes the existing ART Celery child provider lease and bounded scratch for
   hidden request execution. 04F1 supplies verified failure evidence and 04F2
   supplies the exact current TASK/AUTH remediation handoff under either policy
   mode. 04F3 adds hidden exact-cause replacement intake and 04F4 supplies the
   retry owner; the supported public Operator discovery/retry path now invokes
   it. PILOT-04 selected production registration and ARCH-02I-B
   public entry and ARCH-04E3-B supported false-guide activation are delivered;
   the bounded local public drill starts from public guide inputs with recorded inference.
   True routing may proceed after its own prerequisites to publish the exact TASK
   manifest and move `evaluation_pending -> review_pending` when no blocking
   failure exists; this does not write the REV queue. The delivered shared
   acceptance participant is an additional false-branch dependency; true
   admission has no CON prerequisite.
   CHECKERS owns durable execution/currentness; the shared facade does not
   create a second result store. Work evaluation may be deterministic or use
   an explicitly implemented model judge. A structural presence check cannot
   stand in for a required substantive quality evaluation. Unsupported required
   evaluators block the affected guide until implemented and included in a new
   approved image-bound generation. Infrastructure retries and project
   setup faults are not contributor failures; `allow_review` is not acceptance.
   **For the first false-policy acceptance path:** consume the delivered TASK
   04E1A source facts through the delivered REV-04B source FK; TASK request/source-identity reservation (04E1B-A) and the hidden
   `task.post_submit.route` preparation for `workstream.task.post_submit_router`
   (04E2-A) are delivered. They bind exact `TaskAcceptedEffectsRequest` values
   without a Review. CON-07 now uses the delivered REV-12A1 fence to stage or
   exactly replay the contribution and complete zero/one/two frozen award set;
   paid replay checks its correlation and unpaid replay retains none. REV-04C
   composes that result with FinalAcceptance and TASK effects. Delivered 04E2-B
   supplies the actual routing decision on the same strict acceptance input,
   validates its immutable AUTH event, and commits complete effects with shared
   audit/outbox evidence. PostgreSQL guards enforce complete outcomes and actual
   phase receipts; successor, lifecycle and replay tests exercise the authorized
   operation. Upgrade refuses pre-authority outcomes without rewriting retained data.
   B8 delivers hidden completion handling, acknowledging only after commit.
   04F1 supplies the verified failure-evidence input and 04F2 supplies the hidden
   `needs_revision` consequence without REV/CON effects. 04F3 supplies hidden
   exact-cause replacement; 04F4 supplies the terminal infrastructure retry
   owner and the supported public Operator route invokes it.
   ARCH-04E3-B supplies real manager-authorized false-guide activation under
   matching Python/PostgreSQL requirements custody and corrects the selected
   production REV manifest. New false/pass effects require LIVE REV bound to that
   current manifest; a known pre-effect refusal has bounded retry, with exhaustion
   dead-lettered. The bounded local public drill starts from public guide inputs with recorded inference, including prefork Celery process restart and late authority revocation. The milestone creates the
   submitter contribution and applicable awards without inventing a Review or
   reviewer contribution. Live human queues/leases/decisions remain later work.
3. **Bounded local public intake through durable workers is proven.**
   CP08 already locks the complete guide and policy context before `READY`.
   Claim copies it to TaskAssignment without selecting another ContributionPolicy;
   ARCH-02I-B's public admission-backed creation copies that exact lineage.
   ARCH-03D connects the final handoff to the approved unified-guide intake.
   The published preparation route returns correction feedback for blocking
   failures and a replayable ready admission after required checks; the canonical
   POST consumes it. The local drill exercised those APIs with selected durable
   PRE/POST Celery services, false-policy activation, remediation, bounded retry,
   prefork Celery process restart, late authority revocation and exact contribution evidence.
   It used public guide inputs and recorded inference, local Flow-compatible auth and
   development containers; hosted operation is the next boundary.
4. **Start the live REV path.** Reuse the packet, Review and FinalAcceptance
   storage completed before the automated path. Admit only canonical
   `allow_review`; claim a bounded lease and
   exact packet using the Submission-stamped ContributionPolicyVersion.
5. **Make human review decisions economically complete.** Before the first live
   Review commit, add the reviewer CON operation and reuse the shared acceptance
   operation already needed by the false branch. Every final decision records
   reviewer work; accept additionally records accepted submitter work. Do not
   duplicate the common persistence or submitter participant.
6. **Complete revision and operations.** Checker replacement enforces caps
   with initial round 0, fresh per-failure deadlines, complete-context rebase,
   exact contributor acknowledgement, PM repair with paused-clock conservation,
   immediate exhaustion and durable timeout release/reclaim. Each assignment has its own revision allowance. Connect genuine human Review
   decisions to the same locked-policy window and controlled revision boundary
   through #554; preserve
   prior attempts and reviewer economic evidence. Finish remaining recovery,
   fulfillment, reconciliation, audit, release controls, and legacy cleanup.
7. **Release proof.** The isolated seven-service local stack is available; use it
    to expose stable APIs and frontend surfaces, exercise the complete path
    through real database, durable-job, storage, security, failure, and recovery
    tests, then run the internal pilot. Compose health alone is not journey proof.

## Engineering Quality Alongside Product Work

The [behavior-first audit](../.commitrail/initiatives/WS-QUAL-003/OVERVIEW.md)
has delivered focused PROJECT proof repairs, fixture separation, real
rollback checks, a shared AUTH concurrency-observer repair, and a rebalance of
the hosted CI lanes. The audit also corrected concrete sufficiency and
submission-policy validation defects. These are delivered bounded repairs,
not a claim that every test or subsystem is fully audited.

The selected AUTH projection replay, actor-resolution, and authentication audit
and decomposition are also delivered, including stronger first-access race
proof. The selected bootstrap/admin-access audit also retains signed API
composition, strengthens exact PostgreSQL lock and staged rollback proof, and
maps the replaced mixed assertions to bounded owner tests. That does not complete
the remaining service-actor, profile/link and other AUTH families or the full
suite audit. Remaining work includes those AUTH families and the TASK, CHECKER,
ART, CON, REV, and tooling audit. The audit requires behavioral proof, not only
file splitting or coverage percentages. Real PostgreSQL, concurrency, storage,
and full hosted behavior/integration checks remain required. Product
implementation is already progressing alongside this audit with separate file
ownership.

Commitrail's contribution-path and reviewer-routing improvements are delivered.
They support this work; they do not complete a product capability or create a
second permission system.

Retained checker ownership is database-immutable; finished outcomes cannot change
or receive additional results. Result insertion serializes with completion.
Detail reads first resolve the authorized parent Submission, then query the exact
run/task/submission.
Retained submission/checker history now uses canonical AUTH with separate
contributor and Project Manager projections. The obsolete token-role dependency,
compatibility identity writer, manual checker execution, finalize repair and
fabricated-actor Celery gate are removed. Retained records are preserved;
ARCH-04C supplies hidden durable execution and unfinished-attempt recovery;
ARCH-04D2 supplies exact service authority; 04E/B8 supply hidden authorized
routing and completion delivery, 04F2 supplies the hidden remediation branch,
04F3 supplies exact-cause hidden replacement intake, and 04F4 supplies the
Operator retry owner for terminal infrastructure failure. The supported public
project-scoped discovery/retry path invokes that owner.
PILOT-04 registers the selected request and completion handlers in production composition; ARCH-02I-B separately exposes public intake.

ARCH-04B adds hidden exact Submission materialization through TASK's immutable
read port and ART's consumed admission. Local/MinIO input is independently reread,
verified and projected through canonical bounded scratch. ARCH-04D2 supplies exact leased input authority before and after I/O.
The public admission-backed Submission POST uses the same TASK-owned creation
and durable initial post-check dispatch.

ARCH-04B2 adds hidden typed checker-output `store` and byte-free
`recover(selector)` operations, per-slot preparation caps, generic put and
verification reuse, and flush-only immutable verified binding. Controlled
nonempty slots originally proved ART mechanics only. Selected external
images return bounded schema-validated JSON results; generated output-file
write/binding authority remains unavailable. ARCH-04C supplies CHECKERS reservation/currentness; ARCH-04D2 supplies
execute/finalize authority. ARCH-02I-B exposes public ZIP preparation and
admission-backed Submission creation; the complete public API and Celery
service drill starts from public guide inputs with recorded inference.

## Critical Dependency Map

```text
Delivered foundations (bounded local journey proven; no deployment claim)
  privacy-bounded API/Celery diagnostics (collector deployment still required)
  digest-only API/Celery/Beat/checker release configuration (hosted proof still required)
  WS-EXEC-001-01 Smol node + existing typed execution adapter + exact-lease recovery
    -> upload-overlapped trusted guest ZIP/default intake
    -> Smol public API/durable-worker proof (both review-policy branches)
  automatic unified setup + separate manager pre/post approvals
  public Finance ContributionPolicy administration + exact selected-version validation
  public manager activation context + exact guide activation/binding
  WS-CLI-001-38 keyed human guide sufficiency diagnostic + warning acknowledgement
  WS-CLI-001-41 keyed manual artifact-policy draft create + hash-guarded successor
  WS-CLI-001-46 current system project-reader catalogue -> CLI project list (TUI separate)
  WS-CLI-001-44 native CLI release proof + gated manual publisher (not yet published)
  task/assignment/Submission lineage + public ZIP intake/admission-backed creation
  ARCH-03D exact approved historical guide through durable intake handoff
  ARCH-04B hidden verified Submission input
  ARCH-04B2 hidden checker output store/recovery/binding (authority deny-only)
  ARCH-04C hidden durable execution/current results + atomic completion event
  shared dispatcher + exact-authorized hidden assignment invalidation
  ARCH-03C2 invalidation producer + first handler registration
  ARCH-03C3 exact manager task create/screen/release + replay
  ARCH-03C4 exact-authorized public task queues and ARCH-03C5 detail/requirements
  ARCH-03C6 distinct exact-authorized locked-context reads
  WS-CLI-001-36 explicit Operator task status/reference reads + start override
  AUTH-ART-02D-OPERATOR exact system-Operator artifact GETs + separate retry
    -> WS-CLI-001-43 consumes all nine public operations without new authority
  ARCH-03C7 bounded exact-authorized Audit Authority task history
  WS-CLI-001-34 CLI consumption of those two audit GETs (no new lifecycle owner)
  PILOT-13 assigned-task locked originals: document-only context + verified REST/CLI reads
  canonical contributor/manager Submission and checker history; obsolete gate removed
  ARCH-04D1 canonical ART material custody at terminal CHECKERS commit
  ARCH-04D2 exact input/execute/finalize authority + durable receipts
  ARCH-04E1A immutable route-neutral TASK source facts + type-only effects port
  ART-07A1 metadata-only packet membership types (no resolver/byte authority)
  REV-03B normalized immutable lease packets and live guide ingest custody
  REV-04A immutable Review/finding/resolution and completed request storage
    |
    v
  REV-04B immutable shared acceptance source storage (no AUTH custody or production writer)
  CON-03C immutable contribution records and fixed awards
  REV-12A1 disabled generation-zero controller and transaction fence (no authority)
  AUTH-19A exact source/receipt contracts and planned router (no execution or receipt storage)
  ARCH-04E1B-A immutable request and future source-ID reservation (no source publication)
  ARCH-04E2-A strict hidden preparation + nominal PREP adapter (action unavailable)
  CON-07 hidden source-neutral submitter participant + complete frozen award set
  REV-04C hidden FinalAcceptance + TASK effects + CON composition (no authority/route)
  ARCH-04E1B-B1 ordered reservation/current reads + admission INSERTs (no activation)
  ARCH-04E1B-B2 exact source proposal + B3 ZIP metadata + B4 checked packet custody + B5 bounded evaluation content
  ARCH-04E1B-B6 atomic Submission/dispatch + exact AUTH receipts + replay (no delivery/publication authority)
  ARCH-04E1B-B7 original hidden request-delivery foundation
  REV-12A4A scoped Operator transitions + immutable AUTH/history custody + current-generation gates
  PILOT-02A public canonical JSON source custody + authorized replay + PostgreSQL/MinIO recovery proof
  PILOT-02B public atomic JSON-to-DRAFT import + immutable native batch status + exact-file recovery
  PILOT-02C explicit atomic batch screen/release + CLI source/import/status + CSV conversion
  WS-CLI-001-31 public source status/content -> verified private CLI download (no Task change)

  ARCH-04E2-B hidden complete authorized outcomes + actual receipts + DB closure
    true: TASK review_pending handoff, no REV/CON prerequisite
    false: shared FinalAcceptance + TASK/CON/awards + audit/outbox, exact replay

  ARCH-04E1B-B8 hidden completion handler for both branches (commit before ACK)
  ARCH-04F1 verified current failure evidence
  ARCH-04F2 exact current checker remediation through TASK/AUTH under both policy modes
  ARCH-04F3 hidden exact-cause replacement through canonical ART/TASK intake and writer
  ARCH-04F4 reason-bound Operator retry through CHECKERS/AUTH + existing request handler
  supported public project-scoped Operator source discovery + exact retry invocation
  uncertain request/completion reconciliation -> one immutable child
    committed: verify retained effects; retry_safe: recheck then existing owner
    unresolved or child UNKNOWN: hold, no repeat
  ARCH-04E3A hidden ART Celery child lease + per-invocation scratch
  PILOT-04 selected default + exact external PRE/POST images; both catalogues removed
    production request/completion handlers -> true review_pending or hidden false acceptance
  ARCH-02I-B public initial/checker-remediation ZIP preparation and admitted Submission
  ARCH-04E3-B supported false-guide activation + reviewed selected-production REV manifest

  PILOT-10A public bounded evidence reads over existing immutable CON/awards
    active human self or covering PM / exact-project Finance -> JSON or CSV
    REST fixed membership -> signed JSON / CSV-header continuation, fresh AUTH per page
    CLI follows continuation internally -> complete JSON or atomic private CSV
    no recognition writer or fulfillment dependency

  WS-CLI-001-27 consumes existing manager task-context and history/checker GETs
    with exact project/resource selection; no new backend lifecycle or write dependency
  PILOT-READ-1 stored attempt outcomes + per-finding checker evidence
    -> PILOT-READ-2 contributor own-work reads A1-A6 + manager task filters B3
         exact grants -> projects; current Submitter grant -> assignments,
         attempts, preparations, summary; one REPEATABLE READ snapshot per response
         signed cursors bound to actor, filters, limit and order; read-only
    -> PILOT-READ-3 Project Manager reads C1-C9 + Finance policy list D1
         guides, activation readiness (same conditions as activation), project
         submissions/assignments/summary, import batches, failed preparations;
         summary award totals under the Project Manager grant; read-only

Proven bounded local first-layer drill (public guide inputs, recorded inference, local Flow-compatible auth)
  Original guide + examples -> recorded Celery setup -> separate PRE/POST approval
  + public review/revision settings + Finance publication -> exact guide activation
  -> public API + PostgreSQL/MinIO/Redis/prefork Celery/Beat contributor journey
  -> public triggers reached the selected completion outcomes
       |
       +-- final-attempt failure -> rejection + assignment release -> ready
       +-- fixable failure with revisions -> TASK needs_revision (no REV/CON)
       |                                    -> frozen context + acknowledgement
       |                                    -> setup block: pause + PM attention/repair
       |                                    -> exact-cause replacement intake
       |                                    -> expired window: rejection receipt + release -> ready
       |
       +-- locked true -> review_pending -> human Review (later runtime)
       |                                    | accept
       |                                    v
       +-- locked false -> authorized ----> shared FinalAcceptance
                           automated        + submitter ContributionRecord
                           trigger          + applicable awards (atomic)
                                               |
                                               v
                         fulfillment, reconciliation and release proof
```

Future genuine human `needs_revision` will use the same controlled revision
boundary through #554; `reject` will record a rejected outcome. Every final
human decision records reviewer work and any applicable
reviewer award atomically; the false branch creates neither. Both acceptance
triggers use the same operation. Shared acceptance persistence and hidden CON
participation are separate foundations before false/pass routing activation; human
queues and leases are not prerequisites for that branch. The diagram shows the
successful evaluation branches. The hidden failure handoff, exact-cause replacement intake
and public known-terminal Operator recovery are delivered. Separate uncertain
request/completion reconciliation preserves original UNKNOWN custody and permits
one child only after source-specific classification; ambiguous effects stay held.
Its full hosted interruption drill remains outstanding. The setup-fault hold is future safety work;
the current selected production classifier emits no `task_setup_blocked`.
Both branches passed the bounded local public API/Celery drill; hosted deployment
is not established by that evidence.

No claim-time policy selection exists. A normal task claim copies the version
already locked on the ready task. Review claim copies the version stamped on
the admitted Submission. During `needs_revision`, the continuing assignment
may rebase only after comparing and atomically preparing the complete active
governed context; earlier Submission, ReviewLease, Review, ContributionRecord,
and award history never changes.

## Remaining Release Gates

v0.1 is not ready until all of the following are true:

- Reproduce the connected guide-to-contribution journey with the intended
  hosted identity, inference provider and infrastructure. The bounded local
  drill now covers original upload, task examples, recorded async inference,
  public review/revision configuration, separate PRE/POST approvals, Finance
  publication, activation and both policy outcomes. It does not establish live
  model quality or deployment readiness. See the [connected proof](../.commitrail/changes/public-guide-to-contribution-proof.md).
  The provider-free `manager_authored` runtime removes the inference dependency
  from local and hosted setup and selects no provider credential. It proves
  nothing about model quality. Both inference runtimes now pass the bounded
  original-guide qualification. Exact OpenRouter account/plugin evidence, the
  selected-image hosted/AWS proof and the broader Flow contribution journey
  remain.
- Publish the reviewed backend and checker-service source builds, substitute
  their registry digests and the approved exact checker cache into the prepared
  release configuration, and rerun its full host preflight. Then prove actual
  Flow/AWS identities and the selected isolation engine with measured limits in
  the deployed environment; configuration rendering and local source-image builds are only
  prerequisites.
- Connect Smol preparation to the authorized upload request, replace production
  host ZIP/default processing with trusted guest intake, and prove public PRE,
  immutable admission, durable POST, recovery and both governed policy outcomes.
  Standalone node execution and failure injection do not meet that release gate.
- Prove artifact diagnosis/retry in the intended hosted S3 environment; local
  public API/CLI proof does not establish hosted provider operation.
- A task cannot enter `READY` without that complete locked context.
- A contributor can claim and prepare one ZIP under the locked pre-submit
  policy. Blocking intake failures return feedback and create no Submission;
  successful preparation produces ready admission after the required custody
  checks, without a parallel legacy path.
- TASK consumes that admission to create the immutable Submission with exact
  assignment/policy lineage. Pre-submit feedback is not post-submit proof.
- The immutable Submission automatically reaches exactly one current
  post-submit result. Locked true produces human `allow_review` when eligible;
  locked false with supported requirements invokes the shared atomic acceptance
  operation with no human Review/lease/reviewer contribution.
- An exact current contributor-correctable result routes to TASK
  `needs_revision` under either locked policy mode when another revision remains.
  Final-attempt failure instead closes the assignment and returns the task to
  ready. Neither creates a Review, acceptance, contribution or award. The contributor can submit a
  full replacement ZIP through the canonical admission writer with its exact
  current authorized cause. A supported public system-Operator read discovers
  known finalized infrastructure failures and exact retry invokes the existing
  owner. Supported uncertain request/completion reconciliation must demonstrate
  that committed effects are not repeated, safe recovery uses the existing
  owner, and unresolved sources or an UNKNOWN child remain held. The source
  implementation does not replace the hosted interruption drill. A
  future manager-visible hold must retain the Submission and locked rules
  without contributor penalty if a supported setup-fault result is added. The
  current classifier emits no `task_setup_blocked` production result; changing
  or re-screening submitted-task rules remains deferred.
- ARCH-04E2-B hardens the existing TASK source table with mandatory exact
  routing and owner-receipt custody and rejects retained pre-authority rows;
  no parallel manifest or permissive backfill is introduced.
- REV-12A4A supplies authorized lifecycle transitions and phase-gated atomic
  participants; ARCH-04E2-B binds genuine source receipts and complete authorized
  success consequences under that manifest. B8 completion delivery is
  implemented; 04F2 adds exact checker remediation with zero REV/CON effects.
  04F3 adds hidden exact-cause replacement intake; 04F4 supplies the exact retry
  owner and the supported public Operator recovery path invokes it.
  Selected production completion already invokes shared acceptance for eligible
  locked false-policy facts. Supported false-guide activation is implemented;
  the bounded local public durable-runtime drill passed. Setup-fault handling is future safety work.
  Conditional awards remain atomic. Fulfillment obligation/root/ordinal storage
  and real cutoff/drain proof are required when payment fulfillment is enabled,
  not before the first contribution path. No fabricated observation or
  permissive generation can replace a supported manifest.
- A reviewer can claim only that admitted version, access only its bounded
  packet, and record one immutable final decision.
- Genuine human `needs_revision` must join the implemented controlled-revision
  boundary through #554 with the same assignment rounds and locked-policy
  PostgreSQL window. Only immutable resubmission ends it; timeout retains
  rejection evidence, releases the exact assignment and returns to ready.
  Every earlier attempt stays immutable; `reject` and `accept` retain their
  distinct effects.
- Every final review atomically creates the reviewer ContributionRecord;
  `accept` additionally creates FinalAcceptance and the submitter record.
- The delivered REV-04C participant composes FinalAcceptance, TASK effects and
  CON-07's zero, one, or two frozen CompensationAwards in one caller transaction
  without controlling Workstream lifecycle truth; isolated hidden participation
  is not release proof.
- Fulfillment and recovery are idempotent, observable, reconcilable, and safe
  under durable-job, provider, transaction, and unknown-commit failures.
- Contribution evidence reads retain complete source/award identities with fresh
  self or project authority per page and fixed membership for selections through
  100,000 contributions. Signed cursors bind caller/scope/filters/format/limit;
  excess selection refuses without partial output. The CLI follows continuation
  internally, validates one complete traversal and publishes no partial JSON or
  CSV result. Exported award quantities are earned facts, not proof of external
  payment.
- Configure secured diagnostic collection with bounded retention and access,
  and prove API/Celery correlation, privacy and collector-outage behavior in
  the release drill. Implemented instrumentation alone is not deployed monitoring.
- Public APIs and frontend surfaces expose only the canonical paths, obsolete
  authority and legacy routes are removed, and the full security/operations
  drill plus internal pilot passes without weakening safeguards.

## Trace References

The [neutral runtime contract](../.commitrail/initiatives/WS-AGENT-001/WS-AGENT-001-01.md)
and [OmniCoreAgent companion](../.commitrail/initiatives/WS-AGENT-001/WS-AGENT-001-02.md)
define the shared document-tool/result boundary, mutually exclusive SDK images,
synthetic and original-guide qualifications, and the provider-account and hosted
evidence that remain outside repository-only proof.

The [observability foundation record](../.commitrail/changes/observability-foundation.md)
and [operator guide](engineering/observability.md) define diagnostic scope and
remaining deployment responsibilities.

The [local pilot stack record](../.commitrail/changes/pilot-local-stack.md) and
[runbook](engineering/local-pilot.md) define the checkout-isolated runtime,
authority bootstrap, retained-data boundary and remaining platform/journey
proof.

The [local agent loop record](../.commitrail/changes/local-agent-loop-profile.md)
and [runbook](engineering/local-agent-loop.md) define the checker overlay,
proof-checker trust limit, operator scripts and the unproven persistent-stack
FinalAcceptance path.

The [hosted release configuration record](../.commitrail/changes/mvp-hosted-release-configuration.md)
and [operator runbook](../deploy/hosted/README.md) define the digest-only process
topology, dedicated Docker/runsc trust boundary, private configuration and
runsc/cache checks repeated before every launch, and the live environment evidence that remains before deployment can be claimed.

The [Terminal Systems project inputs](../pilots/terminal_systems/README.md)
provide an original contributor guide, one illustrative task and five authoring
briefs. The guide now defines its project-local metadata and reproducibility
contract; each brief has readable source synchronized with the native import.
These are assignments to author complete tasks, not completed benchmark packages
or a fixed eligibility list. They deliberately contain no Workstream PRE/POST bindings or policy
defaults. The PM supplies those inputs to setup; its requirements, proposed
bindings and missing-capability suggestions drive engineering's external image
work. After registration, a Project Manager creates and dispatches a correction
successor or creates a new guide version; a finalized setup run is not rerun.
The fresh proposal needs separate approvals and complete activation before tasks
can be released.

The fixed five-task corpus, its project-specific checker and runtime exception,
and its dedicated proof workflow are retired. Earlier evidence remains historical
and is not proof of these broader project requirements. The generic external
checker service, material custody, normalized result contract and their safety
regressions remain. [#576](https://github.com/Flow-Research/workstream/issues/576)
owns input agreement; [#493](https://github.com/Flow-Research/workstream/issues/493)
must be reconciled with the actual setup-derived gaps, rather than treating one
remaining sample PID probe as sufficient project readiness.
[#555](https://github.com/Flow-Research/workstream/issues/555) owns the connected
public journey. The [live setup qualification](../.commitrail/changes/terminal-systems-live-setup.md)
includes real provider drafts from unchanged guide bytes with all project size/entry
limits null. Typed proposals expose engineering specifications; the final corrected
proposal has passed independent source-to-proposal review. Draft path and material-linkage
errors exposed a need for bounded output correction. Every draft, review and
correction now passes strict schema, canonical, context and source checks; only
the final review can become a proposal. Up to two value-free corrections share
the original attempt budgets. Each phase must initially read every assigned
original, including for blocked proposals; searches cannot substitute for those
reads. PM correction now
supplies the exact hash-verified predecessor as bounded, untrusted context rather
than only its identity and feedback. The final real correction successor was
independently qualified against the unchanged guide as a usable engineering handoff:
two PRE specifications, eight POST specifications and two lifecycle classifications.
That retained handoff predates the narrowed setup contract: newly inferred proposals
contain only PRE/POST check requirements and supporting default coverage/guide blockers.
The PM configures review/revision and other project policies separately. The historical
handoff needs a fresh correction before it is used as the current proposal.
Exact stored/public result and component hashes and CLI rendering passed; all 57
accumulated provider resources were deleted. Earlier proposals remain immutable
and unapproved. This qualification required explicit PM corrections and establishes
one reviewed handoff, not automatic completeness for arbitrary guides. Ten required
checks remain unbound suggestions in that immutable proposal. The project-owned
PRE image now implements both PRE specifications, is locally qualified, published
by digest and registered in the local rehearsal, but remains unbound. The eight POST checks and their model,
execution and authenticated-material dependencies remain to be implemented.
Registration, corrected policy binding and approval must precede activation;
no approved binding, activated guide or contribution outcome is established.

The [Smol node lifecycle](../.commitrail/initiatives/WS-EXEC-001/WS-EXEC-001-01.md)
adds production engine support through the existing typed adapter, independently
of the hosted Docker composition. Its node-level proof uses synthetic ART grants;
public upload/intake and durable-worker integration remain separate.

The [offline gVisor build spike](engineering/pilot00-gvisor-offline-build-spike.md)
selects a sealed-cache Kaniko builder plus a separate gVisor oracle sandbox for
PILOT-04/PILOT-06. PILOT-04 now has a normalized external request/result
contract, immutable authorized digest-pinned registry, selected Rust service/SDK
with a typed Unix-socket adapter and request-bound ART grant, and one versioned
Workstream default checker with exactly four blocking outcomes. Both executable
catalogues are removed. Verified ZIP/default checks precede approved external PRE
images; only a complete pass permits immutable Submission creation and durable
POST dispatch. Unresolved required capabilities block guide activation with bounded,
manager-authorized requirement IDs, stages and titles; registration alone does
not clear an approved compilation's gap. Corrected compilation and approval
must bind the registered image. Production completion routes true-policy success to review_pending
and false-policy success through shared atomic acceptance. Default failures prevent
Submission creation; infrastructure failures retain recoverable outcomes. Local
Rust/MinIO integration evidence uses runc/docker-dev, not gVisor. ARCH-02I-B
delivers public Submission entry; CLI25 consumes it through explicit preparation,
creation/replay and history/findings commands. The spike proves only the included small Linux fixture;
representative task sizing, hosted hardening and macOS fallback evidence
remain.

The [supported Operator registry record](../.commitrail/changes/mvp-operator-checker-registration.md)
defines the public registration/readback boundary, exact replay and denial
evidence. The remaining issue #580 boundary is public guarded REV lifecycle
control; registry publication supplies no lifecycle or execution authority.
The [ART Operator authority record](../.commitrail/initiatives/WS-AUTH-001/WS-AUTH-001-ART02DOPERATOR.md)
binds the eight existing artifact actions to exact system-Operator decisions
and distinguishes read response custody from atomic retry. It is a backend
prerequisite to the [artifact CLI and native journey](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-43.md).
The CLI consumes those public routes without adding authority or hosted proof.

Internal chunk identifiers are useful for implementation traceability, but a
reader does not need internal engineering records to understand the roadmap
above. The main
remaining trace sequence is:

- Unified guide: POL-04B1/04B/04B2, POL-05A/AUTH-12F4/POL-05B,
  POL-06A/AUTH-12G/POL-06B, POL-07A/07B, AUTH-12H and ARCH-03A are delivered.
  The complete internal guide context and `CP08` exact task/assignment/Submission
  contribution-policy stamps and ARCH-03B1 detached display are available; ARCH-03B2 ready and ARCH-03B3 management/operational queue facts and ARCH-03B4 hidden task detail and ARCH-03B5 current live work context and ARCH-03B6 locked-context and ARCH-03B7 requirements projections are delivered.
  ARCH-03B8 hidden task audit evidence and ARCH-03B9 hidden assignment invalidation
  are complete. ARCH-03C1 real feature authority and exact decision receipts are
  complete; ARCH-03C2 supplies atomic producer wiring and registration;
  [ARCH-03C3](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C3.md) supplies
  exact-authorized manager create/screen/release.
  [ARCH-03C4](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C4.md) exposes the
  three queues with distinct grants and signed pagination.
  [ARCH-03C5](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C5.md) exposes
  exact-authorized Contributor/Manager task detail and requirements.
  [ARCH-03C6](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C6.md) exposes
  distinct manager, system-Operator and Audit Authority locked-context reads.
  [ARCH-03C7](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C7.md) exposes
  bounded task history under covered Audit Authority. ARCH-04A supplies registered-capability
  contracts; activation does not require a Task, Submission or completed run.
- Contribution lineage: CP05 authorization, CP06 validation, `CP07` activation
  and `AUTH-12H` live manager authority are complete.
  [AUTH-18](../.commitrail/initiatives/WS-AUTH-001/WS-AUTH-001-18.md) exposes
  manager activation selections and the canonical public activation POST. `ARCH-03A` has completed
  the existing internal guide-context port. `CP08` delivers lineage fields
  and minimal Task/Assignment/Submission writers together without superseded economic
  readiness. Atomic assignment-invalidation publication and delivery are complete
  in `ARCH-03C2`, following real authority in `ARCH-03C1` and
  `ARCH-03B1` metadata and ARCH-03B2/03B3 hidden queues and ARCH-03B4 hidden detail and ARCH-03B5 current work context, ARCH-03B6 locked-context and ARCH-03B7 requirements and ARCH-03B8 hidden audit evidence and ARCH-03B9 hidden assignment invalidation, and authorization/public cutover in `ARCH-03C`. The [completed physical cleanup](../backend/alembic/versions/0023_remove_task_payment_policy.py)
  removes unused guide-keyed payment storage and TASK/Submission fields through
  migration 0023, with retained-data refusal. Historical CP09 sequencing is no
  longer a pending removal or an `allow_review` activation dependency.
  Shared dispatch authority is delivered by AUTH-OUTBOX-02. Live assignment
  invalidation has atomic producer fan-out and registered delivery in ARCH-03C2.
  Manager readiness commands are public with exact authority in ARCH-03C3;
  ARCH-03C4 exposes ready, management and Operator-status queues. PILOT-14
  adds contributor-safe
  locked compensation to ready/detail without restoring removed task payment
  fields or exposing Finance bindings. ARCH-03C5 exposes task detail and
  requirements; ARCH-03C6 exposes distinct
  locked-context reads; ARCH-03C7 exposes bounded Audit Authority history. Current authority is checked
  on every request.
- Hidden intake: [ARCH-03D](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03D.md)
  removes the private TASK/PROJECTS lookup at final durable handoff.
  [ARCH-02I-B public entry](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-02IB.md)
  subsequently exposes ZIP preparation and canonical admission-backed
  Submission creation for initial work and checker remediation.
- Post-submit admission: after delivered `POL-07B` and `ARCH-03C`, delivered hidden
  [ARCH-04B input materialization](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04B.md)
  and [ARCH-04B2 output custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04B2.md)
  and [ARCH-04C durable execution](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04C.md)
  and [ARCH-04D2 exact service authority](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04D2.md)
  lead to delivered
  [ARCH-04E1A source facts](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1A.md).
  [ARCH-04E1B-B2](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB2.md) adds exact source preparation without publication or authority.
  Delivered [ART-07A1 packet types](../.commitrail/initiatives/WS-ART-001/WS-ART-001-07A1.md), [REV-03B packet persistence](../.commitrail/initiatives/WS-REV-001/WS-REV-001-03B.md),
  [REV-04A Review source storage](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04A.md)
  and [REV-04B acceptance storage](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04B.md),
  followed by delivered [CON-03C contribution/award storage](../.commitrail/initiatives/WS-CON-001/WS-CON-001-03C.md),
  [REV-12A1 disabled controller/fence](../.commitrail/initiatives/WS-REV-001/WS-REV-001-12A1.md)
  and [CON-07 hidden participation](../.commitrail/initiatives/WS-CON-001/WS-CON-001-07.md),
  plus the REV-04C hidden FinalAcceptance/TASK/CON participant, support the
  additional false-path acceptance-source AUTH custody and activation prerequisites. Both branches have delivered request reservation `04E1B-A` and AUTH preparation `04E2-A`,
  followed by delivered authorized success outcomes `04E2-B` and hidden completion
  delivery `04E1B-B8`. PILOT-04 supplies selected production registration and Celery
  composition; true
  routing proceeds after its own prerequisites without shared acceptance. 04F1
  supplies verified failure evidence, 04F2 supplies the hidden remediation
  handoff, 04F3 supplies hidden exact-cause replacement intake, and 04F4 supplies
  the retry owner now invoked by supported public Operator recovery. A
  manager-visible setup-fault hold remains future safety work, with no current `task_setup_blocked` production result. The mandatory
  [04D1 canonical material custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04D1.md)
  closes the three-field ART database guarantee before authority activation.
  ARCH-04C retains immutable output-set custody; selected external image outputs
  use the same verified ART ownership rather than a structural catalogue.
  AUTH-OUTBOX-02 delivers shared live authority, phase audit custody and Celery
  delivery/recovery scans over CON-02B. Delivery termination is bounded by a
  fixed 3,660-second prefork process hard limit. Selected POST requests have
  a 3,520-second handler timeout and 3,600-second lease; completion/invalidation
  retain their 240-second handler timeout and 300-second lease. Exact task and
  message bounds prevent either truncating approved work or extending shutdown.
  ARCH-03C2 enforces a dedicated non-eager prefork delivery queue.
  ARCH-04E1A proves source storage and detached contracts only; its false scalar
  proof does not make false activation available. PILOT-04 separately installs
  selected request/completion production composition; public false-guide
  activation is delivered by ARCH-04E3-B for supported approved requirements.
  The true handoff does not require REV or fulfillment.
  TASK request/source-identity reservation `04E1B-A`, hidden AUTH preparation
  `04E2-A`, CON-07 participation and REV-04C hidden FinalAcceptance/TASK/CON
  composition are delivered. The hidden `04E2-B` operation now supplies mandatory authority/evidence
  closure and atomic success outcomes. B8 supplies hidden completion delivery;
  04F2 extends the same operation with exact checker remediation under both policy
  modes. 04F3 adds hidden replacement intake; 04F4 supplies the retry owner and
  supported public Operator recovery invokes it;
  ARCH-02I-B supplies public entry and ARCH-04E3-B supported false-guide
  activation; the bounded local public durable-runtime drill passed.
  A dispatcher cannot authorize TASK or CHECKERS mutations. A future supported
  setup-fault path must retain the Submission and locked rules without contributor
  penalty; it is not a public cutover prerequisite.
- [CON-03C contribution/award storage](../.commitrail/initiatives/WS-CON-001/WS-CON-001-03C.md)
  supplies immutable source/economic equality. [CON-07 hidden participation](../.commitrail/initiatives/WS-CON-001/WS-CON-001-07.md)
  supplies source replay and complete frozen award sets; REV-04C composes them
  with hidden FinalAcceptance and TASK effects, without live recognition,
  acceptance authority or fulfillment.
- Review/revision: REV packet/schema foundations may proceed independently,
  but live admission starts after `ARCH-04E`; the first live Review commit also
  requires the atomic CON decision participant on the delivered CON-03C storage.
- [PILOT-10A's bounded read/export record](../.commitrail/changes/pilot10-contribution-award-export.md)
  distinguishes public evidence reads from hidden recognition and deferred
  fulfillment. The [canonical read contract](spec_contribution_compensation.md#bounded-contribution-evidence-reads)
  defines fixed membership, scope, limits, cursor authority, exact quantities,
  time semantics and CSV safeguards. The current pagination outcome is recorded
  in [Stable Contribution Export Pagination](../.commitrail/changes/stable-contribution-export-pagination.md).
- [PILOT-READ-1 stored attempt outcomes](../.commitrail/changes/pilot-read-foundation.md)
  supplies typed attempt status, `decided_at`, finding counts and per-finding
  checker evidence. [PILOT-READ-2 contributor reads](../.commitrail/changes/pilot-read-contributor.md)
  records the A1–A6 own-work reads and B3 task filters: AUTH actions, Submitter
  scope, snapshot consistency, cursor binding and the evidence-stamp rule for
  incremental attempt reads.
  [PILOT-READ-3 project reads](../.commitrail/changes/pilot-read-project.md)
  records the C1–C9 Project Manager reads and the D1 Finance policy list,
  including the shared activation-readiness conditions and award-total scope.

For implementation ownership and exact contracts, contributors can follow
[Commitrail Engineering Index](../.commitrail/INDEX.md). For historical
decisions, use the [Historical Planning Index](historical_planning.md).

AUTH-19A source-contract boundary: [exact commitments and remaining custody](../.commitrail/initiatives/WS-AUTH-001/WS-AUTH-001-19A.md).

ARCH-04E1B-B3 proof: [verified ZIP metadata custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB3.md).

ARCH-04E1B-B6 proof: [atomic Submission, exact receipts and initial request custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB6.md).

ARCH-04E1B-B7 proof: [hidden request delivery and invocation custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB7.md). B8 supplied hidden completion routing; PILOT-04 adds selected production composition and ARCH-02I-B adds public intake.

REV-12A4A proof: [scoped lifecycle control and payment-delivery deferral](../.commitrail/initiatives/WS-REV-001/WS-REV-001-12A4A.md). ARCH-04E2-B supplies exact source receipts; B8 completion delivery, the 04F2 zero-REV/CON remediation handoff, 04F3 hidden replacement intake and the 04F4 retry owner are implemented. Supported public Operator recovery now invokes that owner for known terminal infrastructure failure. ARCH-02I-B supplies public entry and ARCH-04E3-B supported false-guide activation; the bounded local public durable-runtime drill starts from public guide inputs with recorded inference. Setup-fault handling is later safety work.

ARCH-04E2-B proof: [hidden authorized outcome custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E2B.md). B8 supplies hidden completion delivery; selected production composition is implemented, and ARCH-04E3-B supports false-guide activation under exact approved requirements custody.

ARCH-04E1B-B8 proof: [hidden completion delivery](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB8.md). Both policy branches commit before acknowledgment; closed UNKNOWN invocations never automatically repeat effects. PILOT-04 adds selected production request/completion composition; ARCH-02I-B separately exposes public intake.

ARCH-04F1 proof: [verified checker failure evidence](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04F1.md). The completion reader verifies retained contributor/setup failure facts. That historical read does not establish a selected production `task_setup_blocked` result; the chunk itself supplied no routing, replacement intake or recovery authority.

ARCH-04F2 delivered boundary: [authorized checker remediation handoff](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04F2.md). The existing hidden TASK/AUTH operation retains the exact current recommendation, manifest and actual decision receipt while moving TASK to `needs_revision` under either policy mode. It creates no Review, FinalAcceptance, contribution or award and adds no public API or production registration. 04F3 supplies hidden replacement intake and 04F4 supplies the retry owner now invoked by supported public Operator recovery. PILOT-04 later registers selected delivery; the bounded local public drill passed after those connections.

ARCH-04F3 intended merged boundary: [exact-cause checker-remediation replacement](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04F3.md). Existing hidden ART intake and TASK creation admit a changed full ZIP only from the exact current authorized remediation source under either policy mode. The successor Submission, binding, AUTH decisions and generation-one request commit atomically; old evidence stays immutable. Uncaused `revision` runtime/replay is removed, and migration `0034_checker_remediation_replacement` refuses retained unprovable revision rows without deleting them. 04F4 adds the terminal-failure Operator retry owner, now invoked by supported public discovery/retry; ARCH-02I-B adds public initial and remediation intake, and the bounded local public drill passed. Setup-fault handling is future safety work.

ARCH-04F4 intended merged boundary: [hidden Operator checker retry](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04F4.md). An active system Operator can request a reason-bound new CHECKERS generation only for the exact current terminal `infrastructure_failed` run. The existing coordinator and request handler retain a new immutable retry receipt, AUTH decision, audit and request event while preserving the failed run; fresh-authorized same-key replay validates historical ownership and the original closure without creating another run. This 04F4 chunk supplies no public route, selected production registration, setup-fault hold or contributor penalty; PILOT-04 later registers selected delivery.

Supported Operator checker recovery: [public known-terminal recovery](../.commitrail/changes/mvp-operator-checker-recovery.md). An active system Operator can list a bounded project page of finalized infrastructure-failed sources and invoke the existing 04F4 owner through a project-qualified public command. Discovery and replay revalidate current authority. Queued, running, completed, stale, foreign and uncertain-delivery sources do not become eligible.
The [CLI Operator commands](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-29.md)
consume that public list/retry pair; they add no backend recovery mode or
automatic retry.

Supported uncertain post-submit delivery recovery: [source-specific reconciliation](../.commitrail/changes/mvp-operator-uncertain-delivery-reconciliation.md). A separate active system-Operator surface classifies exact finalized UNKNOWN request/completion deliveries. One immutable child verifies committed effects or invokes the existing owner only after proving no effect; unresolved sources and an UNKNOWN child remain held. This does not broaden the known-terminal retry route. Hosted interruption proof remains under #581/#555.

ARCH-04E3A proof: [hidden invocation-scoped ART materialization](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E3A.md) leases the existing Celery child provider and closes bounded scratch for hidden request delivery. PILOT-04 adds selected production request/completion composition; ARCH-02I-B separately exposes public intake.

ARCH-04E3-B intended merged boundary: [supported false-guide activation](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E3B.md) verifies exact approved requirement coverage in Python and PostgreSQL, corrects the selected-production REV manifest and preserves the default-true branch. A known pre-effect non-live refusal retries within the existing OUTBOX attempt budget; exhaustion dead-letters without automatic reopen. The bounded local public durable-runtime drill passed at `d5703d9c6` under scripted approved-guide preconditions and local Flow-compatible auth; it does not establish hosted deployment, live model setup, human review or payment fulfillment.
