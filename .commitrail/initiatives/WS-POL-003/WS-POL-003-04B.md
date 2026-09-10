# POL-04B — Agent-driven unified guide setup

- Initiative: WS-POL-003
- Durable disposition: Planned
- Risk: L1
- Intended merge outcome: authorized document upload to private artifact storage
  starts one isolated agent investigation, ending at findings and separate draft
  pre/post policies. This replaces the earlier extraction-dependent, single-prompt
  implementation in the same unmerged change.

## Intent

The project manager uploads DOCX/PDF guide documents; PowerPoint is included only
through a tested reader (PPTX first, no unsupported binary PPT claim). Standalone
image/audio/spreadsheet/text-source expansion is outside this change. S3 stores
original immutable files; PostgreSQL stores metadata, versions, operation custody
and validated findings/policy proposals, not extracted document bodies.

After successful upload and metadata commit, one asynchronous setup job receives
the exact guide manifest. The agent chooses which granted documents to inspect,
uses document tools and an isolated workspace, keeps notes, manages context and
produces one complete proposal. One job may contain many model/tool calls.
Duplicate delivery must not start another agent run. Insufficient/unreadable
material ends with an explicit outcome. Ready proposals wait for manager review,
correction and approval. POL-05 owns manager surfaces and fresh manual reruns.

Every file access is restricted to an explicitly assigned source-item version
within the exact project/guide/snapshot/generation/run. Metadata or tool arguments
cannot widen that scope. No S3 credentials, bucket browsing, arbitrary keys,
provider URLs or access to another run's workspace reach the model.

The creator explicitly authorized replacing the old affected implementation in
this PR, including obsolete tests. No compatibility aliases, old/new runtime
variants, extraction fallback, or separate cleanup prerequisite is permitted.
Retained records are not authorized for deletion.

## Current-source findings

Base is `c69ff853`. ART currently stores originals through ArtifactStore, then
requires verification, binding, classification and extraction before setup.
`guide_sufficiency_material.py` loads canonical PostgreSQL text rows for all
sources; `projects/service.py` and `guide_compilation/context.py` flatten them
into a 12 MiB snapshot. The adapter sends that entire snapshot, has no tools and
limits execution to one model turn. These are the superseded paths.

The dependency extends into sufficiency projection provenance, submission-policy
mutation validation, setup continuation and authorization resource facts. Merely
changing the SDK adapter or placing tools over the PostgreSQL text aggregate
would leave the wrong design operational. Current source evidence references
extraction usage; the new contract must bind original document versions instead.

## Bounded change

### 1. Document upload and readiness

Reuse the existing authorized guide upload route, committed-source preparation,
ArtifactStore provider boundary and immutable source snapshot. New snapshot items use only `source_kind=document`,
`ingestion_adapter=upload` and required PDF/DOCX/PPTX media types. Keep ingress
permission, declared/observed size bounds and checksum computed during upload.
Reuse GuideFormatDetector and existing OOXML/ZIP safety against prepared bytes
before admission; require actual type to match the persisted declaration, reject
macro/binary-PPT substitutions, and never use request headers as format authority. Store the source once and record its exact committed
object identity. No mandatory post-upload download/classification/extraction.

A new setup run starts `awaiting_documents`. Guide `object_confirmed` has an
explicit `document_stored` receipt outcome and zero verification jobs. The final
exact upload atomically claims `dispatch_pending`; queued/eager worker handling
keeps the existing deterministic task identity. Concurrent, out-of-order and
replayed uploads must publish at most that one logical task. Late storage
completion for a stale snapshot may remain retained evidence, but cannot dispatch
or satisfy the latest run. This guide-specific exception updates ADR 0013 and
the ART specification in this change. It must not
mark a shared artifact replica verified or mint a fake verification receipt.
Submission/checker artifact verification remains unchanged, including when bytes
are shared with a guide. Readiness requires every assigned item in the manifest
to have a successful same-owner committed upload. Queue publication occurs only
after commit; existing bounded continuation scans recover missed publication.
Replace the guide continuation's verification-job dependency with upload/run
identity. Unresolved upload outcomes remain unavailable rather than guessed.

### 2. Manifest and run-scoped file access

Replace GuideSufficiencyMaterialPort and its extracted-content aggregate with a
metadata-only guide document manifest capability. It returns project, guide,
snapshot/generation, ordered source-item IDs, source checksum/size/media type,
and exact committed storage identity for server use. The model-facing projection
contains opaque document handles and safe generated names; it excludes storage
coordinates. Manifest hashing is deterministic and contains no document body.

`app.adapters.artifacts` constructs the ART-owned typed document byte grant
using the existing store/scratch roots; `app.adapters.projects` injects its
public port into the coordinator. `app.workers.project_setup` remains a thin
public-composition consumer. Reuse fixed ARTIFACT_GUIDE_READER and
artifact.guide_source.read; do not add a reader identity/action. Replace old
verification facts with attempt/manifest, exact item/ingest/put/replica, project,
guide/snapshot/generation, namespace, checksum, size and media facts.
The manifest is bound before the fence; the runtime receives its already-fenced
opaque grant. Losing/replayed deliveries perform zero OpenAI I/O. Each open resolves an opaque handle in that grant,
checks exact ownership/version/current authority and streams only the resolved
object through ArtifactStore. No caller-supplied bucket/key/URL is accepted.
Before any provider file upload, each requested object is fully staged into
bounded scratch and its checksum/size matched to the committed document receipt.
No corrupt bytes are streamed onwards before that check; this read does not mark
the shared replica verified. Closure/cancellation/expiry invalidates the grant;
a new run cannot reuse it. Fixed-service/source denial at tool time aborts the
run, rather than becoming recoverable tool text. Original PM consent retains
POL-04B1 semantics; later PM role changes are not retroactive consent withdrawal.
Any local temporary staging uses ArtifactScratchManager with aggregate bounds.

### 3. Runtime workspace and configuration

Keep ADR 0014's typed ProjectGuideAgentRuntime factory and separate immutable
runtime/model/instruction configuration. The sole current implementation is the existing OpenAI SDK with a dedicated
hosted Code Interpreter container. This
uses existing supported DOCX/PDF/PPTX inspection rather than rebuilding a
Workstream extraction pipeline. Prove the pinned SDK/provider supports the required container isolation and
document controls before implementing the wider cutover. If that probe fails,
revise the plan rather than shipping an unsupported or fallback path.

After winning the fence, the trusted adapter creates a fresh explicit empty
container with network_policy disabled. Its local `open_guide_document(handle)`
tool resolves one authorized source, verifies its staged bytes, uploads it with
purpose=user_data and bounded expiry, records the provider ID, and attaches it
to that exact container. Filenames are generated from source-item UUID plus
trusted extension. The returned model-facing value contains its workspace path
and source-version reference, never an S3 coordinate or provider-file selector.
Set parallel_tool_calls=False and serialize duplicate opens with a bounded
per-handle lock. Repeated opens validate the grant but stage the same document
at most once. Known ART denial, missing/corrupt bytes or stale authority aborts
Runner with no subsequent model turn and no retry; SDK tool-error formatting
must not convert these failures to recoverable text. After an initial model
call, conservative provider-uncertain classification remains explicit.
No automatic container reuse, shared conversation, previous-response reuse,
File Search/vector store, MCP, S3 credentials or general storage API is exposed.
Only explicitly opened assigned files are mounted. Code Interpreter supplies
inspection and temporary notes; its output is not saved as source content.

OpenAI + Responses + hosted Code Interpreter is the sole current adapter
combination. Reject/remove the unmerged chat-completions and openai-compatible
execution branches; another adapter can implement an explicitly supported
provider later. Set ModelSettings(store=False) on all Responses requests and
use input-based, non-stored compaction when applicable. Provider Files and
containers still have application-state retention: deletion/expiry are cleanup
controls, not a claim of immediate erasure or zero-data-retention. No transcript,
raw tool output, guide-document bodies or workspace notes go into PostgreSQL or
application logs. Ordinary task-example text is stored with guide metadata in
PostgreSQL, as specified in the required-example contract below.

Expose immutable limits for file count/bytes, model turns, wall time, tool work,
context compaction and temporary workspace lifetime. Use supported SDK/provider
context controls inside the single run, not just between user conversations.
Reject unsupported provider/API/tool combinations before execution; do not
silently downgrade to one-shot inference. Model and instructions remain explicit
in .env.example and independently configurable.

Provider resource custody is mandatory and owned by the compilation attempt.
Persist each allocation operation and each returned file/container ID with its
exact manifest mapping, state, cleanup deadline and runtime identity. Use a
public typed custody port composed through PROJECTS, not direct ORM imports in
the SDK adapter. The allocation capability is issued by the winning fence and
cannot record another attempt's resources. Cleanup authority is limited to those
allocated resources and remains usable after project/source access is revoked.

On exit perform bounded cancellation-shielded container-first then uploaded-file
deletion. An exact-ID cleanup reconciler retries recorded resources without
listing the OpenAI project's Files or Containers. Set bounded file/container
expiry at creation for process loss and unknown-create windows. Unknown
allocation is recorded as uncertain; it cannot be guessed successful, rediscovered
by global listing or retried as another agent run. Cleanup failure must not erase
a known valid/invalid result, change its classification or clear provider
uncertainty. Never persist generated container files or delete S3 originals as
part of this cleanup. All OpenAI creation/upload/model operations occur after
the fence; unknown staging/model outcomes remain provider-uncertain.

### 4. Result, evidence and projections

Preserve one complete structured result, distinct pre/post proposals, canonical
catalogue validation and the manager approval pause. Replace extraction-based
source references with exact document/source-version references. Storage access
receipts prove the files made available to the run; model-authored page/section
references remain untrusted proposal evidence, not independent proof of semantic
correctness. Do not claim a retrieved hit proves full-guide comprehension.

Require at least one successful document-open receipt before accepting a
compilation, and require every cited source to belong to the manifest and opened
set. Ready output must account for every assigned document; unavailable/unread
material cannot silently disappear from the findings. Bind the immutable
manifest and content-free run file-access evidence into
accepted-result custody and downstream projection checks. Adapt current
sufficiency/report and submission-policy provenance consumers together. Keep
fresh action-bound projection authority, locked lineage, atomic acceptance,
immutable finalization and current-authority replay. Unknown runtime outcomes
remain unresolved; recovery may not launch an uncontrolled second run.

### 5. Remove superseded affected paths

Remove mandatory guide format/extraction orchestration, whole-guide prompt
assembly, their active composition and obsolete execution tests. Trace shared
consumers before deleting parser helpers. Preserve submission ZIP processing,
required artifact scratch protections and immutable historical evidence. If old
extraction tables/rows are retained for references, make that retention explicit;
there must be no live fallback reader or new writes preserving the old flow.
Use a reviewed migration for current contracts, without fabricated backfills or
deletion of retained source/evidence data. Update schema/ORM/API parity together.

## Canonical metadata and retained-data disposition

The sole document-version source is GuideSourceSnapshotItem +
GuideSourceArtifactIngest + its exact object_confirmed ArtifactPutAttempt +
ArtifactReplica, with receipt, checksum, size and media. Do not create a second
corpus/document-version table. Add only attempt-bound provider allocation,
access and cleanup custody. Projection `_add_source_usages`, current report
validation/source refs, submission-policy mutation, AUTH material facts and
finalizer checks all switch together to this manifest/access owner.

Keep prior extraction/binding/content/usage rows and their necessary ORM metadata
read-only; new execution/reports/derivation/activation never consume them.
Retained extraction-backed reports are not eligible for new actions. Existing
locked task/policy facts remain intact; no fallback or fabricated backfill makes
old reports eligible. Guard retained tables against new writes after cutover.

Remove content_markdown from current guide create/update/response, assignments,
source/hash logic and docs. PATCH remains for bounded change_summary metadata
only. Rename the physical column to retained_content_markdown, preserving values,
make it nullable, retain only the same-name nullable ORM retention mapping, and
add database guards: new INSERT requires NULL and UPDATE cannot change it.
There is no current API/read/inference path or empty-string fallback for it.
Migration tests prove preservation and rejection of new writes/direct SQL edits.

## Test replacement map and precise guard boundaries

Replace guide setup/extraction material tests in test_guide_setup.py and
relevant test_guide_bindings.py sections. Retain/adapt test_guide_artifacts.py
PREP/admission/lineage/replay/concurrency, provider ownership and scratch cleanup,
plus submission verification coverage. Delete extractor-specific PDF/DOCX/PPTX
and general extraction tests only with their production consumers. Supported
format proof becomes actual ingress fixtures plus opt-in hosted read fixtures.
Automatic request/context/projection fixtures use committed-document/access
lineage. Preserve eager dispatch_pending/queued delivery, crash and replay tests.

Initial preflight rejects an invalid manifest before any OpenAI request. A forged
model-called handle is rejected before S3/scratch/provider staging for that call;
it does not erase the earlier model/container activity. Same-size corruption,
truncation or missing bytes discovered during an authorized open cause zero
provider-file creation for those bytes and no subsequent model continuation,
while exact cleanup calls remain permitted. Direct capability and whole-runtime
probes report these different boundaries honestly.

Use two valid projects/runs/generations and same-content items, mutate one
selector at a time, and test namespace/ref/hash/size drift separately from
permission. Same content/replica never grants another item's access. The live
isolation probe leaves an unrelated provider File in the same OpenAI project,
tries a foreign-ID substitution at the trusted staging boundary, lists only the
run's explicit container to verify its assigned file set, and tests actual
outbound network denial and absent OpenAI/S3 credentials. Clean up probe-owned
foreign fixtures too. Stage crashes, partial uploads, allocation-before-receipt,
delete failures and cancellation must preserve exact cleanup/replay custody.

Scripted SDK/model tests prove tool/config serialization, multiple turns, limits,
ephemeral state and compaction wiring. Only the paid probe establishes actual
hosted file inspection, note use and within-run compaction. Required fixtures are
DOCX + PDF, and PPTX before advertising it; no 429 or mocked tool execution is
reported as successful live-agent proof.

## Real project-guide acceptance fixture

Use only the creator-authorized private documents and examples through the same
authorized upload, manifest and runtime flow as a project manager. Keep source
identities, titles, paths, contents and detailed receipts private and outside Git
and the PR. Public verification notes report generic behavior and aggregate
results only. Do not import unrelated workspace material. Synthetic foreign-file,
corruption and SDK-parser probes remain separate discriminating controls.

The realistic run must distinguish sufficiency from currently executable checker
capability. A complex ML task guide can produce supported structural pre/post
proposals, human-review requirements and explicit capability gaps. A blocked
result may be correct; do not invent live model judges or weaken validation to
force a ready result. Inspect grounded findings and both stage classifications,
then verify persistence, replay, exact-file isolation and resource cleanup.

## Allowed files and boundaries

- `backend/app/interfaces/project_agents.py`, `project_guide_runtime.py`,
  `artifact_operations.py`; consumer-owned guide document contracts in
  `backend/app/modules/projects/api/guide_documents.py` and their focused
  PROJECTS scope implementation.
- `backend/app/adapters/project_agents/`, affected artifact composition and
  `backend/app/core/project_agents.py`, `project_guide_instructions.py`, config.
- Guide-only ART source/binding/materialization/extraction/preparation paths,
  relevant storage-completion and repository branches, schemas/models and tests.
- PROJECTS guide upload/readiness/queue/worker, guide compilation context,
  orchestration, accepted evidence, projections, report/policy provenance and
  affected authorized mutation/read callers; relevant schema/model definitions.
- Existing AUTH guide-resource/preflight/PREP facts and evaluators solely to
  reconcile exact stored-document lineage. No broader roles/actions/service
  permissions. Add a focused public capability only when owner review requires.
- Required migration, dependency metadata/lock, .env.example, README, canonical
  guide/ART/agent specs, roadmap, affected initiative navigation and local exports.
- Affected focused tests/fixtures, API/MinIO drill and an explicit opt-in live
  agent probe. CI metadata may change only for accurate ownership/selection;
  no reduction in required behavior checks, floors or test execution. Remove the
  extractor-only dependency gate/allowlist and image/PDF decoder packages together
  with their deleted consumers; keep pinned defusedxml for bounded OOXML ingress
  and replace parser-confinement assertions with the current runtime/ingress boundary.

Affected API cleanup removes the superseded post-submit setup read, approval
and correction routes, their exclusive schemas/service helpers and the retired
setup-read AUTH action. Keep current diagnostic reads, explicitly manual
sufficiency and policy operations, and planned POL-06 action vocabulary. Manual
approval admits only its canonical manual lineage; retained separate-agent
policies cannot enter new approval or activation. Shared post-submit stored
records and locked-policy consumers remain readable. Downstream test fixtures
must identify seeded prerequisites honestly and cannot claim public approval
proof. Route-registration/OpenAPI absence tests replace obsolete route tests.

The shared verifier and Operator recovery stay active for submission-bundle and
checker-output producers. Their scanner, claim, direct execution and recovery
replay must exclude retained guide jobs by originating put producer; a shared
replica never makes a valid submission job ineligible. Current retry requests
require project/task scope, while retained read models preserve nullable history.
Remove the redundant recovery service entry and route tests through its canonical
retry port. Keep the PostgreSQL clock and checker-lineage repository helpers,
which still have shared consumers. Generic verifier tests use current checker
outputs; adversarial retained-guide rows prove zero dispatch, read or recovery.
Upload acknowledgement and successful exact-generation observation are distinct
valid custody receipts, both accepted by current manifest and SQL access guards.

Prohibited: frontend work; PM approval/rerun APIs belonging to POL-05; automatic
acceptance; checker evaluation; compensation/reputation; changes to submission
verification; unrestricted storage/network tools; parallel runtime paths;
repository-wide cleanup; deletion of retained data; unrelated dependency updates.

## Acceptance criteria

1. Uploading supported files stores originals and metadata only; setup starts
   after all assigned uploads commit, without extraction or verification jobs.
   Unknown/partial upload, stale generation and unauthorized actor controls fail.
2. Shared-source bytes cannot bypass submission verification. Probe guide upload
   followed by submission of the same content as a discriminating control.
3. Two projects and two runs with distinct sentinel files prove exact-file
   isolation: foreign/forged/stale handles and key/URL substitution fail before
   the attempted file read or provider staging; expired/closed grants and traversal attempts cannot read bytes.
4. Real SDK tool configuration admits only a fresh container with the assigned
   opened assigned files and disabled network. Cleanup and cancellation tests cover every
   allocated resource, including partial staging/provider uncertainty.
5. Scripted SDK/model tests exercise multiple document-open turns, stable
   run/container identity, limits, ephemeral context and compaction request
   serialization. A max-turn-one mutant fails sequencing while valid controls
   pass. Concurrent duplicate opens produce one staged upload/attachment and
   exact cleanup custody. Hosted reads, note use and actual compaction are
   established only by the paid probe in item 8.
6. Actual SDK parser rejection remains sanitized invalid-terminal, including
   redaction on/off and exception traceback custody. PostgreSQL replay proves
   that invalid/uncertain/complete outcomes do not start another agent run.
7. PostgreSQL tests bind manifest/source evidence to accepted results and both
   atomic authorized projections/finalization; substitution and stale authority
   controls must reach the intended guard rather than an earlier invalid shape.
8. Opt-in paid smoke uses the user's ignored .env, real DOCX and PDF with distinct
   content, at least two document inspections and a multi-step investigation.
   Verify structured findings/proposals and persisted replay, source-version
   evidence, workspace isolation and cleanup. Record provider/model/tool usage;
   no key or raw confidential document output in logs. PPTX gets its own fixture
   before support is advertised. Test unreadable/insufficient guides explicitly.
9. Run Ruff, appropriate focused tests and MinIO/API/PG proof, then final hosted
   full lanes/coverage/Agent Gates without skips/deselections. Perform stale
   wording and markdown-link checks; reconcile roadmap/navigation after main.

## Traced assigned-task consumer

The existing task work-context response also reads inline guide markdown. This
cutover removes that field while retaining the exact locked guide ID/version,
change summary, effective time, policy requirements and lifecycle guards. The
locked policy-context port remains a policy-lineage capability.

Assigned contributors still require a separate bounded guide-document delivery
capability before the complete guide-to-task loop is usable. It must authorize
the current assignment against the task-stamped guide snapshot and stream only
those originals through ART. Record this in the remaining guide work; do not
reuse the setup fixed-service grant, expose storage coordinates, or add a retained
markdown reader. This is an explicit dependency, not delivered document access.

## Risk and review routing

Architecture and security review this concrete plan before product edits. QA/
test-delta review the real guard reachability and paid-test design. After shared
checks, freeze a clean candidate and run architecture/reuse, security, QA/
test-delta, product/docs and CI-integrity tracks. Batch repairs and replay only
affected reviews. The size exception is one explicitly authorized cohesive
replacement within the existing unmerged PR, reviewed by owner boundary; it is
not permission for unrelated cleanup or an unbounded new agent platform.

Human focus: exact-file isolation; originals versus temporary data; no extracted
content database; a real tool-using run; correct source-version grounding;
separate draft policies; manager approval pause; no duplicated run on replay.

## Evidence

The following provider references and execution observations support the bounded
verification strategy above. Failed probes remain identified alongside later
results; execution custody and limits are stated for each.

### References

- [OmniCoreAgent](https://github.com/omnirexflora-labs/omnicoreagent)
- [Deep Agents context management](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- [OpenAI SDK tools](https://openai.github.io/openai-agents-python/tools/)
- [OpenAI file inputs](https://developers.openai.com/api/docs/guides/file-inputs)
- [OpenAI Code Interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter)

### Runtime model selection

Use `gpt-5.6-terra` through `WORKSTREAM_PROJECT_AGENT_MODEL` for the real
guide acceptance run. Luna and Terra were both retrieved successfully using
the configured OpenAI account. Earlier GPT-5.4-mini probes remain evidence
of those earlier executions, not Terra verification. Changing models does
not change the runtime adapter; each selected model still needs a smoke test.

Terra is also the code default when the model setting is omitted. Keep the
single `backend/.env.example` aligned with supported settings and code defaults;
remove obsolete settings when their implementation is replaced. Credentials
remain required operator input and are never supplied as runtime defaults.

The first Terra platform probe opened both assigned PDFs but ended
with `APITimeoutError` at the provider boundary. It is not a passing guide
execution. All receipt-owned container/file deletion calls completed; final
product integration and Terra guide-result verification remain required.

### Transient provider recovery (creator-requested)

Keep Terra as the default. Add bounded transient-request recovery inside one
already-fenced runtime attempt, not another Runner execution or setup generation.
Allowed additions remain the SDK adapter, immutable runtime configuration,
composition, affected migration/config/docs and focused runtime tests.

The transport policy has one owner; disable hidden SDK retries. Configure request
timeout, maximum attempts, exponential backoff with jitter, capped Retry-After,
and circuit failure threshold/cooldown. A worker-local provider circuit prevents
repeated calls during an outage and admits one half-open probe after cooldown;
it is explicitly not a distributed provider health authority. Keep cleanup calls
available while the inference circuit is open. Record only sanitized outcomes.

Retry connection failures proven to occur before transmission, explicit transient
rate limits, and idempotent reads/deletes. Never retry authentication, billing
quota, bad request, validation, denied file access or cancellation. For model
read timeouts and server failures after possible dispatch, first establish how
ongoing hosted execution is reconciled: blindly replaying the request can run
Code Interpreter twice against the same workspace. Reviewer proof must resolve
that boundary before enabling such replay. Resource creates with unknown outcomes
retain allocation custody and expiry; no guessed IDs, list/discovery or retry.
A known response ID may be polled/retrieved with retry without creating another
inference. Overall runtime deadline and hosted-work limits include recovery.

Verification must discriminate success after transient failure, retry exhaustion,
Retry-After/jitter bounds, permanent failures and cancellation without retry,
circuit open/half-open recovery and concurrent probe exclusion, cleanup while
open, and no duplicate local tool execution or setup attempt. Actual SDK boundary
tests must preserve invalid-terminal persistence and no-invocation replay proof.
Architecture and security review the recovery boundary before implementation;
QA/test-delta review the resulting proof alongside the existing required tracks.

The creator selected a 300-second configurable per-request timeout through
`WORKSTREAM_PROJECT_AGENT_REQUEST_TIMEOUT_SECONDS`, independently bounded by
the 1,800-second default whole-run deadline, including retries and backoff.

Use native Agents SDK `ModelSettings.retry` with a strict application policy,
not a second model retry engine. Defaults: two retries after the first request,
one-second initial backoff, thirty-second maximum backoff with jitter; honor
Retry-After only within that bound, otherwise defer rather than retry early.
The worker-local model circuit defaults to three transient failures and sixty
seconds cooldown, with one half-open probe and epoch-protected completion.
Preserve SDK response-started/replay-unsafe vetoes and never approve unsafe
replay. Explicit provider replay-safe advice can permit a transient retry;
status alone cannot. The observed Terra read timeout remains unresolved rather
than being represented as safely replayed. A fresh test run uses the configured
300-second request timeout. Recovery does not silently switch the selected model.

The subsequent Terra SDK probe passed with request timeout 300s:
three model requests, eighteen Code Interpreter calls, ten compaction items,
all pages across the assigned documents, and separate pre/post proposal shapes.
Usage was 35,510 input and 5,350 output tokens. All receipt-owned container/file
deletion calls succeeded. No transient error occurred in this run, so it is not
live retry evidence. The 37 native-SDK/circuit tests pass (92% resilience-module
statement coverage); a broad provider-suggested timeout-retry mutant fails the
one-invocation assertion. These are bounded SDK proofs, not product end-to-end
or semantic-accuracy completion. Original PDF bytes/tool transcripts remain out
of the repository and PostgreSQL. Pin the directly consumed OpenAI3.11.0 and
httpx2 2.12.0 alongside Agents SDK0.22.2 so transport classification is explicit.


### Final document-runtime and affected-path reconciliation

The affected scope includes retiring the dormant role-only guide activation
service, its exclusive response schema/helpers, and tests of that superseded
command. Public activation remains absent and AUTH-12H remains planned; draft
setup cannot activate a guide. Keep active-guide read validation, policy models,
locked TASK consumers and retained setup evidence. Downstream tests seed coherent
approved policy and active-guide prerequisites explicitly, without pretending to
exercise future approval or activation commands.

Pre-submit bindings now carry capability identity only. Intake configuration has
one owner in `submission_artifact_policy`; remove the duplicated binding parameter
copy and its exclusive validator/tests. Post-submit bindings retain independent
evaluator configuration. SDK schemas expose identifier and array bounds; runtime
instructions state the contextual disposition, citation, prose and configuration
rules. Invalid model output remains terminal; no retry attempts to repair it.

Real-provider verification exercised two product outcomes with Terra. Two original
PDFs produced `sufficiency_blocked`; a complete synthetic two-document
DOCX guide produced `policy_draft_ready`. Each used actual API upload, MinIO
originals, the production async worker handler/coordinator, OpenAI Agents SDK and
PostgreSQL: one attempt, one compilation, one finalization, two document accesses,
and five provider allocations deleted. Replay with runtime construction disabled
returned the identical outcome. Broker acknowledgement was scripted and delivery
was invoked directly; this does not establish live Celery broker transport or
semantic accuracy across arbitrary guides. Earlier invalid-output probes remain
failures and demonstrated terminal persistence without replay invocation.

A separate hosted workspace probe extracted assigned DOCX/PPTX sentinels, excluded
an unassigned provider file, checked absence of exact application credential names,
and verified network denial and resource deletion. It did not establish the
provenance of unrelated provider-managed environment names or inspect their values.
Retained guide text preservation and write rejection are tested in PostgreSQL;
the all-document citation guard has a valid-transition control and a transactional
mutant proving the missing-citation assertion detects removal of that exact guard.


Document contracts belong to the PROJECTS consumer API, not a new shared-interface
namespace. PROJECTS locks the exact current draft guide, snapshot, generation,
ingest and execution fence; ART independently verifies its committed receipts,
replicas, namespace and bytes. Adapter composition binds both ports to the same
session, retaining their locks through authorized staging. The scope query does
not select retained guide text. A PostgreSQL race observes the attempt writer
blocked on that lock and proves terminal attempts cannot reacquire source bytes.
The public dependency graph remains acyclic and the frozen private-import ledger
shrinks without new edges. ORM allocation/access declarations use the existing
model-only metadata registration path. The recovery dispatch predicate has one
PROJECTS continuation owner shared by dispatch and scanning.

### Exact provider-file custody repair

The file allocation is the immutable pre-upload mapping for one selected original:
exact source item, ingest, put, content, replica, namespace, hash, size and media.
Database guards reconstruct that chain from committed ART evidence. Attachment
rows reference exact file and container allocations; accesses follow the attachment
back to its file. Container and attachment rows cannot duplicate document facts.
Cleanup changes only allocation lifecycle fields. No separate grant lifecycle or
second corpus is introduced. Architecture and security assessed this bounded
repair design; implementation remains subject to final review and verification.

The sole opaque-handle derivation is SHA-256 over lowercase UUID text in
`workstream.guide-document-handle.v1:<run>:<source>:<ingest>`, truncated to 16 bytes
as a UUID without changing variant/version bits. Python/SQL parity and independent
identity-substitution probes protect the canonical chain, including a removed-guard
probe. The unmerged UUIDv5 implementation is replaced outright. The manifest still
defines the complete assigned set; ready acceptance requires all originals opened
and cited. A shared test-owned migration helper reconciles affected current-head
and retained-guard scenarios without weakening production downgrade protections.

### Required task-example context (creator correction)

Guide sufficiency must be assessed with project rules and representative task
examples together. The creator requires `task_examples` to contain at least one
non-empty example before guide creation is accepted and before inference starts.
An example may be a starting idea, task description, skeleton, or richer sample;
a title, labels and additional context are optional. Do not require deliverables,
acceptance criteria, a completed solution or benchmark-specific fields on each
example. The guide supplies project-wide requirements. Preserve every supplied
example in the same immutable version/run context. Examples illustrate intended
work; they do not silently add universal rules or override the guide. Missing
input is an admission error, not an agent `sufficiency_blocked` judgment.

Replace the unused optional single `RepresentativeTaskPolicyContext` and its
exclusive tests. Do not add a second optional/fallback inference input. Keep original uploaded guide documents in ArtifactStore/S3. Store task-example
text in PostgreSQL, explicitly authorized by the creator: these are ordinary
structured text inputs, not uploaded documents. Bind them to the guide version
and exact inference context. Reuse guide creation, source capture, authorization
and idempotency owners rather than adding a separate task-setup subsystem. Example inputs do
not create Workstream Tasks.

This correction extends the allowed affected schema/context, guide create/source
capture, runtime instructions and current documentation
paths already listed above. It does not authorize checker execution, policy
approval/activation, broader storage access, or deletion of retained evidence.
Required proof includes missing/empty rejection before provider or persisted
creation effects, one minimal example accepted, multiple diverse examples carried
without loss, immutable source binding, foreign/stale substitution rejection,
and real guide-plus-example inference with specific persisted findings. Earlier
no-example provider probes establish mechanics only, not completion of this
corrected input contract.

Observed input controls: examples may be starting ideas or fuller descriptions
with optional titles, labels, targets and caveats. They are project inputs, not
completed submission packages. Use only explicitly assigned examples. The common
requirement is meaningful example content, not a particular source's field set.
Optional metadata remains optional; at least one example is mandatory.

#### Required-example implementation contract

The existing guide-create request requires an ordered `task_examples` list.
Each example has nonblank `content`; `title` and `labels` are optional. Initial
operational bounds are 1–100 examples, 65,536 characters per content field,
500 characters per title, 20 labels of at most 100 characters each, and 128 KiB
for the complete canonical UTF-8 JSON list. The aggregate budget reserves space
for guide metadata and checker capabilities within the default 256,000-byte
provider prompt limit and existing 1,000,000-byte full context limit. A maximum
input fixture must prove both bounds with the default runtime configuration. Bounds limit input size, not task
subject matter. Preserve content and order; use whitespace stripping only to
detect empty input. No deliverable, acceptance-criteria, solution, language or
benchmark field is required. Additional prose belongs in content.

Store the list as PostgreSQL JSON on the owning guide version. It is an immutable
setup input for that version; no optional fallback or manufactured example fills
missing data. Existing retained guide records are not rewritten with invented
examples. They cannot start new inference without satisfying the current input
contract. No new S3 object, ART admission, source kind, initialization state,
external-I/O transaction or separate task-example table is needed. Uploaded
PDF/DOCX/PPTX guide documents continue through the existing S3 custody path.

Use the example commitment/count in the guide-create AUTH projection and replay
hash, not raw text. Include the exact example list in the bounded compilation
context and bind its digest to immutable snapshot/run provenance. Reconstruct
from the owning guide version and reject absent, changed or foreign context
before provider construction. Replace `RepresentativeTaskPolicyContext` and
`representative_task` outright. Preserve the current guide/source ownership and
transactional authorization; final plan review must trace the database guards
and request/execution identity so the digest cannot be omitted or substituted.

Instructions distinguish guide requirements from illustrative examples. They
must assess both together and must not infer a guide deficiency merely because
an example omits requirements supplied by the guide. Missing examples are an
input error, never a model sufficiency judgment. Task examples do not create
Workstream Tasks. Manager correction/manual rerun remains the planned POL-05
boundary; this change must preserve immutable evidence rather than silently
editing an existing run's examples.

Required proof: missing/empty/whitespace-only rejection before guide creation;
one minimal example; diverse multiple examples and exact PostgreSQL roundtrip;
content-sensitive same-key replay conflict; immutable example binding across
snapshot/request/execution; foreign/stale/missing rejection before provider I/O;
and original guide plus actual assigned examples through the real
provider. Retain sanitized outcome findings for the smoke so a blocked result
can be explained. Scope and required review tracks remain those of this change.

Owner review adopts the existing single guide-create transaction and separate
snapshot operation. Add guide-owned example JSON and its domain-separated hash;
nullable columns preserve retained data only, while new insert guards require
valid input. The sole new public snapshot shape is identified by
`guide_source_snapshot.task_examples`; retain no older execution validator.
Snapshot metadata binds example hash/count, not duplicate example bodies.
Extend create-resource AUTH binding with the request digest and example
commitment/count, and prove those facts against the persisted guide and replay
reservation in database custody. Direct SQL must enforce example shape/hash,
new insert requirements, immutable updates, and snapshot/guide commitment parity.
Automatic and explicit execution share the existing context constructor and
canonical input hash; ART document grants and material hashes stay document-only.
Validation tests claim zero guide/snapshot/setup/provider effects, rather than
zero actor provisioning effects from unrelated request dependencies.

Plan-review dispositions: SEC-TASKEX-PLAN-001 is accepted; extend setup custody
to compare its snapshot's project/guide/version/hash as one ownership chain,
including a foreign fixture with identical example text/hash. POL04B-EX-QA001
uses the equivalent exact chain above: immutable guide examples -> manifest
commitment -> snapshot hash -> existing setup/request/attempt/finalization
source binding and canonical input hash. Do not duplicate example columns on
every downstream row.

For POL04B-EX-OPS001, reject snapshot creation for missing examples before new
snapshot/run rows. For retained unfinished runs, expose a read-only
`setup_input_invalid` diagnostic with stable `task_examples_missing` and require
a fresh guide version containing examples. A delivery returns that bounded
input failure before provider construction, without transport retries or a
fabricated model judgment. Preserve already finalized receipts. No retained
evidence is edited or discarded to perform this recovery.

For POL04B-EX-OPS002, the authorized guide-create response and its exact replay
return the persisted example list/hash. Existing guide responses use the same
projection; retained rows truthfully return null. This supplies confirmation
before document upload without adding another public route or permission.
POL04B-EX-QA002 requires independent exact-prompt transfer and no-Task assertions,
Unicode/escaping byte-bound cases, and a complete-guide/minimal-example smoke;
API acceptance alone never asserts semantic readiness.


Review repair disposition: keep task examples at project scope. Setup proposes
one guide policy across the project task set; it cannot demand selection of one
example or defer to per-task policy compilation. Genuine absent project-wide
intake limits may still block and must be identified precisely, without invented
values or copying one task's budget into universal rules. The same assigned private
documents and examples must be replayed after this instruction correction;
mechanically persisted findings alone are not semantic acceptance proof.

Affected downstream test prerequisites use current normalized examples and
snapshot commitments. Their explicit fixture-only authorization suspension does
not claim guide-creation proof. Negative tests supply valid earlier inputs and
assert their intended custody error; the example hash guard has a wrong-hash
valid-shape case. Large text cases use short test IDs without changing values.
Canonical data-model, adopted guide ADRs and authorization runbook/specification
are in this repair's documentation scope; remove their current claims about the
superseded Markdown, URL ingestion and extraction path together.

The final proof repair adds independent malformed guide-AUTH fact cases and
ART checks for identity mismatches after scope resolution and stream drift
after successful scratch verification. These tests preserve the current
coverage floors and join the canonical lane inventory; they introduce no
production compatibility path or expanded storage permission.

Final review adopts SEC-04B-009 / QA005 / TEST-04B-001: hash the exact second
stream while copying to the bounded buffer, then compare digest and size before
yielding. Same-size substitution must fail without releasing bytes or leaking
scratch; a test-of-test removes only that second digest comparison and observes
the same altered fixture become readable. This remains inside the ART grant.
DOC-003/004 reconcile remaining current guide-entry pages, the artifact spec and
the roadmap's bounded guide-plus-example provider evidence in this PR.

The existing runtime-cleanup composition is included in verification scope: prove
that retained configuration selects the runtime, exact cleanup custody supplies
only owned resources, construction/identity/provider failures preserve retryable
evidence, and constructed runtimes close. Completed deletion must not select
that attempt again or enter inference. Keep every hosted coverage floor intact.

The same proof batch exercises the existing SDK model-turn work budget,
compaction boundary, exact cleanup and independent admission, context manifest
and example drift, and sanitized owner errors. These tests cover required
behavior in the affected owners without changing their contracts or CI floors.

The unfinished diagnostic proof must use no finalization and no attempt, so
missing examples reach input validation instead of replaying a persisted result.
Repository verification covers exact setup lookup, foreign-project exclusion,
next generation, and absent compiled policy reads during setup. These current
shared readers remain required by task and authorized diagnostic consumers.

### Catalogue growth through project requirements

The creator clarified that setup must help grow the checker catalogue from real
project needs. Match existing capabilities first; do not invent gaps when the
catalogue already covers the guide. For every required unsupported pre-submit
or post-submit automated requirement, return an actionable non-executable
capability suggestion linked to that exact requirement and stage, with rationale
and guide evidence. A manager reviews the report and requests engineering work;
engineering implements, tests and registers the capability, deploys it, and a
fresh authorized setup run can select it. Suggestions never register, execute,
approve or activate capabilities. Required gaps keep setup blocked. Human-review
requirements remain human review, not fabricated automated gaps. Optional ideas
may be setup notes; the capability-gap report describes required missing checks.
A mature catalogue may correctly produce zero capability suggestions.

Allowed files for this bounded clarification: the existing compilation result
contract, default instructions, their tests and current guide/setup docs in this
PR. Add explicit requirement/stage references to the existing suggestion shape;
replace its affected callers and tests together, without parallel schemas or
compatibility defaults. Validate exact gap coverage, references and evidence;
prove a valid blocked report persists and replays without provider reinvocation,
and prove fully covered requirements need no suggestions. Preserve immutable
result hashes and existing canonical persistence; no new persistence owner or
migration. Risk remains L1. Review: architecture/reuse, security, QA/product-ops,
test-delta, docs and CI integrity. Human focus: useful engineering handoff without
invented executable capability or unnecessary project blockage. POL-05 retains
manager review/correction/approval and fresh rerun ownership. A manager feedback
loop and catalogue engineering UI are explicitly deferred, not added here.

Plan-review resolutions: mixed blocked reports retain existing exact supported
binding proposals as catalogue-match evidence in canonical custody. They still
contain no submission artifact policy. Keep exact catalogue ID, version, stage,
selectability and parameter validation; no bare unsupported assertion of a
supported match. Existing blocked-status projection and finalization gates must
produce only sufficiency evidence, zero policy/checker rows and null policy
output pointers. No new match-reference subsystem is needed.

Align each stage's binding limit and the suggestion limit with the existing
200-requirement cap; cover 50/51, 100/101 and 200/201 boundaries. Enforce the
existing PostgreSQL JSON envelope ceiling of 4,194,304 bytes in the current
result validator before acceptance and during stored-result revalidation.
Measure the default driver JSON serialization (ASCII escaping, default spaces,
UTF-8 byte count); preserve the canonical hash serializer and SQL constraints.
Prove serializer parity against persisted PostgreSQL JSON, multibyte threshold
cases, and terminal invalid-output classification without another provider call.

Verification includes mixed exact pre/post matches plus both gap stages, missing,
orphan, duplicate, wrong-stage and empty/foreign-evidence suggestions, invalid
catalogue matches, and a fully supported empty-suggestion control. A fresh private
real-provider drill uses authorized originals and examples with an explicitly
separate synthetic test addendum requiring unsupported checking in both stages.
A separate synthetic supported control proves exact catalogue selection without
unnecessary suggestions. Keep private source identities, contents and detailed
receipts out of Git and the PR; publish aggregate evidence only. This chunk
creates the immutable structured handoff inside canonical compilation custody;
it does not claim that today's public diagnostic response exposes suggestions.
POL-05 owns that manager-facing review surface. The feedback loop remains deferred.
