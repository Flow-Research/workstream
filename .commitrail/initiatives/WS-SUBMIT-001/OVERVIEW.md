# WS-SUBMIT-001 — Submission execution completion checklist

- Disposition: Planned
- Target: the complete [submission execution specification](../../../docs/spec_submission_execution.md).
- Delivery: one PR, #708, with focused commits; no merge request before complete verification.

## Implemented on this branch

Checked items describe implementation with focused proof. They do not mean the
complete acceptance matrix or deployment is qualified. Detailed runs and their
limits are in [the change record](WS-SUBMIT-001-01.md).

- [x] Exact intake/source identities, durable custody, leases and physical byte reservations.
- [x] Streaming Local/MinIO source upload and source-bound PRE orchestration.
- [x] Atomic T4 acceptance: pending task custody, accepted receipt and durable finalization event.
- [x] T5 formal Submission/binding/POST dispatch through existing owners, with replay and rollback tests.
- [x] Public raw-ZIP API and corresponding CLI/MCP submission/progress contracts.
- [x] One-image-per-phase policy guards and retained-policy refusal.
- [x] Revision expiry and assignment invalidation serialize with acceptance; accepted input remains protected.
- [x] Pending-revision protection prevents dispatch against the older Submission.
- [x] Cleanup claim, retention barriers, exact-generation deletion and confirmed charge release owners.
- [x] Production sealed-source sweep wiring: explicit profile, dedicated worker/task isolation, 12-hour schedule, indexed discovery and focused real-storage retry/retention proof.
- [x] Expired receiving/PRE recovery through the sweep: current authority and task-lock recheck, old-owner fencing, exact pointer release, retained source charge and separate time for sealed cleanup.
- [x] Historical cap fixture no longer depends on the old writer; capture, restore/recovery and neighboring upgrade controls passed.
- [x] Unsealed cleanup and discovered multipart handles use durable cleanup ownership; ambiguous empty discovery retains its charge.
- [x] Admission-only TASK writer removed; accepted-source finalization remains the sole Submission writer.
- [x] Source-backed POST reaches both default human review and automatic acceptance with exact contribution/award lineage and replay checks.
- [x] Real Redis publication recovery and Celery child SIGKILL/redelivery before observation and after commit preserve one finalized graph (08fd205d0); parent-process/Beat and deployed qualification remain separate.

Recent focused evidence includes atomic invalidation (`8a854f7a6`), public
ZIP/T5 lineage (`168e5268f`), and policy-error translation (`d31a45773`). These and the cleanup/recovery runs recorded below are bounded results, not
full-head qualification.

## Submitter experience reconciliation in PR 708

The user-provided `workstream_submission_pr_708_addition.md` supplements the
execution specification and supersedes conflicting public-input/guide-access
requirements. All implementation belongs in this PR; PR 709 is not part of this
work. Existing reward owners remain authoritative.

- [ ] Four required submission inputs and optional feedback; backend-selected revision context and exact actor-scoped replay.
- [ ] Forward migration preserves historical accepted commands and refuses unsafe old in-flight work before mutation.
- [ ] Approved project and governing task guides are readable/downloadable before claim under exact contributor authority.
- [ ] Exact task/assignment status exposes current safe feedback, processing activity, revision terms and accepted evidence without internal-ID discovery.
- [ ] CLI/MCP use the same contract, preserve useful PRE findings and document their distinct upload limits.
- [ ] Combined public contributor journey proves correction, revision, replay, history and applicable existing awards on the integrated code.

The submission, guide, assignment status, and CLI/MCP changes are implemented.
The dedicated queue topology, isolated scanner-to-T5 regression and native
caller conversion are integrated. Combined native execution and deployed
qualification remain open. The managed-style adapter substitution passed through public
ZIP acceptance, retained source custody, real T5 owner delivery and replay;
it does not establish a deployed managed provider or broker-consumer proof.

## Execution deployment decision

The API/application server and microVM execution run on separate infrastructure.
Celery workload queues must also have dedicated workers: no worker consumes a
mixed queue list, and no catch-all worker handles unrelated workloads. Outbox
publication must remain available while POST execution is stopped or saturated;
it must not share the POST or submission-finalization consumer. The PRE6 drill
accepted a fresh source but exposed publication waiting behind the paused general
worker. Dedicated scanner delivery now has a real Redis/prefork T5 proof;
combined native and deployed confirmation remain open.
The application instance is a verified t3.large; the dedicated always-on runner
is an m7i.large with native KVM. App-origin mTLS health and native transport
smoke receipts establish connectivity. V14 also proves the connected local API
and real remote runner through automatic acceptance, rejection and default
review_pending; it does not prove the deployed API/worker release. Do not require nested
virtualization, a Smol binary, host sockets or local KVM on the API instance.
Self-hosted microVM execution uses dedicated runner infrastructure. A paid
sandbox may implement the same qualified execution capability later.

One PRE session means one isolated execution session per PRE operation, not one
machine shared by the API and execution provider. Preserve source identity,
request/result binding, authenticated remote execution and session cleanup at
that boundary; keep host-specific controls inside the selected adapter. Test
native runtime behavior on its actual runner infrastructure. Missing local KVM
is not an API deployment blocker or a reason to build a local fallback.

Challenge existing implementation assumptions before adding mechanisms: reuse
one source object, one intake operation, one acceptance transaction and existing
durable delivery. Remove shared-host coupling and obsolete writers; do not grow
parallel local/remote product workflows. A named paid provider needs its own
qualification, not a redesign of submission ownership.

Keep the implementation boundary concrete: Workstream owns intake, immutable
source references, task state and acceptance; artifact storage owns durable ZIP
bytes; the selected execution adapter owns remote session creation, execution,
results and teardown. Runner scratch is disposable and never the sole retained
copy. Carry the intake/attempt identity and exact source identity across the
request and result so failures can be traced across services. Validate separation
with the API and runner on different hosts and no shared filesystem. A provider
change must not require a second submission lifecycle. These are implementation
and verification requirements, not claims that remote transport is complete.

ZIP preservation means retaining the exact uploaded source in artifact storage
and binding acceptance/results to that source; it does not require preserving a
VM, runner disk, or a second durable ZIP per execution. Transfer or mount only
what the selected execution capability needs into disposable scratch. Keep the
failure cases concrete: interrupted upload, lost storage acknowledgement, and
accepted input awaiting finalization. Extend existing custody and cleanup for
those cases; do not introduce provider orchestration or extra lifecycle states
solely to anticipate future sandbox vendors. Moving execution off the API host
removes its virtualization dependency; the chosen runner/provider still must
satisfy its own runtime requirements.

## Remaining work, in execution order

The user's current priority is integrating current main and proving the complete
submission journey using the existing app host and a separate, inexpensive,
always-on KVM runner. Prepare that infrastructure in the runner worktree while
integrating the application path. Do not let CI-only repair cycles displace this
journey. The remaining cleanup and verification requirements below still apply.

| Order | Required outcome | Concrete finishing evidence |
| --- | --- | --- |
| 1 | Reproduce the connected proof on the deployed API | V14 passes real PRE/T5/POST, automatic acceptance, exact ZIP/Contribution export, rejection, replay and default review_pending with a local API and separate AWS runner. The actual deployed API/consumers remain to activate and prove. |
| 2 | Finish affected qualification callers | Preparation API/materialization and the admission-only TASK writer are removed. Current qualification scripts use raw ZIP acceptance and dedicated finalization; remaining runtime fault vectors must use that same flow and preserve their evidence. |
| 3 | Complete separate-runner integration and runtime/provider/resource qualification | Activate the prepared authenticated remote configuration on the app deployment; actual Smol one-session/isolation proof on runner infrastructure; representative maxima, cold paths, concurrency and timing measurements; applicable AWS exact-version/uncertain multipart proof. Portable/MinIO evidence is insufficient for these claims. |
| 4 | Execute final full-system verification and close the acceptance matrix | Full backend lanes, CLI/MCP contracts and CI at the final head; every A01–A35 row linked to an executed, scope-matching result. Fix actual failures without weakening requirements. |
| 5 | Reconcile configuration and delivery documentation | Resolve C01–C07 using measured/approved values; update affected roadmap/overview/index and local spreadsheet exports; preserve the distinction between implemented, exposed and deployed. |

The connected public journey passed at 85ce76e17 (V14): 573 CLI invocations,
real PRE/T4/T5/POST, exact source and Contribution/export custody, PRE/POST
rejection and default review_pending; owned database/bucket cleanup passed.
Live AWS source qualification passed at 074cade5e with the actual restricted
runtime/cleanup identities, pinned versions, lost acknowledgements and exact
cleanup. Neither result claims a deployed API journey. The next boundary is
qualified AWS admission activation, separate-runner hosted cutover and remaining
native fault/isolation/capacity and final full-head qualification. Ordinary
indexed unsealed cleanup is implemented; optional absent-operation inventory is
not a new prerequisite. Known uncertain writes stay owned and charged until
settled. Do not repeat completed local proofs instead of closing these gaps.

The current unsealed change extends that same cleanup owner: Local incomplete
uploads can be reclaimed, and an observed late completion is retained until a
fresh aged claim identifies its exact version. Focused Local/PostgreSQL and MinIO
checks passed, as did the existing cleanup-owner suite. Recorded MinIO multipart
handles now settle only after parts/handle/version absence; a real PostgreSQL
lost-abort/replay case proves conservative charge retention then one release.
Remote initiation without a recorded handle now retains discovered IDs before
abort and binds them to a fresh cleanup authorization. Focused PostgreSQL/MinIO
checks cover growing observations and lost-abort replay. Empty ambiguous
discovery remains charged; deployed cleanup qualification remains open. Real
Redis outage recovery and Celery child redelivery are proved with unchanged
production leases/backoff; these do not qualify broker-server loss or hosted
operation.

## Acceptance evidence still to close

No row below is declared fully complete merely because some related tests pass.
This is the final qualification queue, not a claim that all listed code is absent.

| IDs | Existing implementation/focused evidence | Required closure |
| --- | --- | --- |
| A01–A03 | V14 connected public API/CLI journey with real separate-runner PRE and POST, T4/T5 and exact source checks | Reconcile each requirement and reproduce on the deployed release. |
| A04–A08 | Metadata/body replay, competing custody, interruption and T4 uncertainty tests | Reconcile exact cases and execute integrated final-head failure/retry matrix. |
| A09–A13 | T5 rollback/redelivery, actual local SIGKILL recovery, accepted authority, pending reads and old-POST guard | Real Redis publication outage and Celery child-redelivery proofs passed; reconcile the remaining exact cases at the final head. |
| A14–A18 | Cleanup lock/retention/charge owners, Local/MinIO tests and live AWS exact-version/lost-ack cleanup with retained-source survival | Production worker sweeps and exact acceptance-case reconciliation. |
| A19–A23 | Streaming/framing, safe archives, semantic identity and findings tests; local A19 496 MiB slow-provider memory/backpressure drill | Full permitted maxima and safety matrix, native/deployment scope where required. |
| A24–A30 | Source/result/fence contracts and runtime/capacity/substitution tests | Actual native isolation/failure/cleanup, multiple replicas/nodes, saturation and adapter qualification. |
| A31–A32 | V14 proves real POST automatic acceptance, exact Contribution/export and default review_pending; focused tests cover applicable awards/replay | Deployed release and final downstream tests. Keep default review_pending guards; live human review remains explicitly deferred by the user. |
| A33–A35 | Retained migrations, cardinality guards and API/CLI/MCP cutover | Affected old writers are retired; finish current-head migration/client convergence and remaining qualification callers. |

## Configuration and external evidence

C01–C07 remain open until individually reconciled with the specification and
actual deployment evidence. Test-only leases/profiles are not approved defaults.
Native Smol qualification must run on the dedicated execution infrastructure,
not the API host. V14 records connected public native proof; remaining runtime
faults/capacity and deployed API proof need their own receipts. Live AWS source
qualification passed separately from MinIO and ordinary SHA-object operation.
Current main's dedicated credentials replace expiring provider activation;
submission work must not reinstate the retired activation subsystem.
Request only concrete missing access or decisions after the corresponding drill
and proposed values are prepared.

The full goal includes D01–D18, I01–I12, T1–T5 and A01–A35. A partial green
suite, fixture capture, review approval or a single commit does not complete it.
