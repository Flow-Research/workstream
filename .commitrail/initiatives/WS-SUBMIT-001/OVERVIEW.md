# WS-SUBMIT-001 — Submission execution completion checklist

- Disposition: Planned
- Target: the complete [submission execution specification](../../../docs/spec_submission_execution.md).
- Delivery: one PR, #708, with focused commits; no merge request before complete verification.

## Current delivery scope — user decision, 2026-11-26

The user explicitly defers scalability until the existing deployment works end
to end, is reviewed/merged, and launch verification finishes. This instruction
supersedes specification completion requirements for the deferred scope.
A28 multi-API/multi-runner races, scale-out/restart qualification, a temporary
second EC2 runner, and broad saturation/load campaigns are deferred, not passed.
No additional AWS provisioning permission is required for current delivery.
Retain existing dedicated queues and correctness/resource guards; do not remove
working scale-out code merely because its deployment qualification is deferred.

Current finish list, in execution order:

- [x] Reconcile main cleanup and preserve required owners/tests in PR708.
- [x] Prove the connected raw-ZIP PRE -> T5 -> POST -> same-assignment revision
  -> acceptance journey through CLI/MCP with the separate runner.
- [x] Integrate the reviewed preclaim-guide and pending-status assertions.
- [x] Back up retained data, migrate and activate the hosted API, MCP and
  dedicated Celery workers with the approved operational profiles.
- [x] Prove the native project PRE deadline and isolation fixture, fresh-VM retry
  to acceptance, test cleanup and restoration of normal runner admission.
- [ ] Reconcile the remaining native fault and uncertain-destroy cases for the
  existing runner; fix only observed defects needed for this deployment.
- [x] Prove the hosted contributor ZIP journey through PRE rejection, pending
  status, POST revision, same-assignment MCP correction and unpaid acceptance.
- [x] Confirm exact aged rejected-source deletion and accepted-version retention
  through the deployed Celery cleanup consumer. [Hosted cleanup evidence](WS-SUBMIT-001-01.md#hosted-age-eligible-source-cleanup)
- [ ] Finish hosted failure recovery, the required-review branch, retained ZIP
  custody checks and supported upload bounds.
- [ ] Run required final-head checks, resolve actual failures, and present PR708
  for explicit merge approval. Merge and post-merge smoke require that approval.
- [ ] Complete post-deployment/merge verification and hand over the release.

Live email delivery remains separately dependent on the user's sender DNS/key
setup. Keep notifications disabled until qualified. Live human review and a paid
sandbox provider remain outside current implementation scope. Do not reopen
completed proofs without a relevant change, failed check or uncovered requirement.

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

- [x] Four required submission inputs and optional feedback; backend-selected revision context and exact actor-scoped replay.
- [x] Forward migration preserves historical accepted commands and refuses unsafe old in-flight work before mutation.
- [x] Approved project and governing task guides are readable/downloadable before claim under exact contributor authority; hosted originals were verified before claim.
- [x] Assignment-ID status exposes rejected intake feedback, revision terms and accepted evidence in the connected journey without internal-ID discovery.
- [x] Qualify live pending processing through assignment status; the hosted journey observed the exact assignment in evaluation_pending.
- [x] CLI/MCP use the same contract, preserve useful PRE findings and document their distinct upload limits.
- [x] Maintained CLI baseline at `c715dbd47`: real remote PRE rejection, acceptance/replay, T5, automatic POST acceptance, incorrect POST revision, unpaid contribution custody and default review_pending; schema0093 test cleanup passed.
- [x] Combined CLI/MCP journey at `73d81da66` proves actionable PRE/POST feedback, same-assignment correction, replay, retained versions and exact unpaid acceptance/contribution through real isolated Keycloak and the remote runner.
- [ ] Quality-feedback email uses the stable assignment ID for POST revision requests and revision-limit rejection, with a dedicated consumer and no infrastructure-failure notifications; qualify delivery after sender DNS verification and private key configuration.

The checked items have focused contract/PostgreSQL proof and the maintained
connected CLI/MCP journey described above. The deployed core contributor
journey and paired replay passed. Remaining hosted qualification is listed below.
The dedicated queue topology and isolated scanner-to-T5 regression are integrated.
PR722 removes the retired experimental native harness, including branch-only
extensions. Its receipts remain historical; current native qualification must
use maintained client/runtime owners and the current authentication boundary.
The connected real-provider and hosted contributor journeys pass. The native
project-deadline/isolation fixture also passes; remaining native faults, cleanup
and supported-input qualification remain open. The managed-style adapter substitution passed through public
ZIP acceptance, retained source custody, real T5 owner delivery and replay;
it does not establish a deployed managed provider or broker-consumer proof.

## Execution deployment decision

The API/application server and microVM execution run on separate infrastructure.
Celery workload queues must also have dedicated workers: no worker consumes a
mixed queue list, and no catch-all worker handles unrelated workloads. Outbox
publication must remain available while POST execution is stopped or saturated;
it must not share the POST or submission-finalization consumer. The PRE6 drill
accepted a fresh source but exposed publication waiting behind the paused general
worker. Dedicated scanner delivery has real Redis/prefork T5 proof. Live queue
inspection found seven consumers with one named queue each. The hosted journey
still needs to verify scoped queue independence.
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
| 1 | Verify the contributor flow on the deployed API | The hosted release `2942dd4e7` passed the core contributor ZIP journey and paired CLI/MCP replay. The required-review branch, scoped failure recovery and remaining custody checks still need hosted evidence. |
| 2 | Finish affected qualification callers | Preparation API/materialization and the admission-only TASK writer are removed. PR722 retires the experimental harness; the maintained native CLI/MCP journey passes; complete its remaining fault proof through the same owners using raw ZIP acceptance and dedicated finalization. Do not restore the old harness. |
| 3 | Complete separate-runner integration and runtime/provider/resource qualification | The hosted app uses the authenticated separate runner. Finish Smol one-session/isolation, bounded failure/cleanup and timing measurements on that runner. Verify supported input bounds and applicable AWS exact-version/uncertain multipart behavior through the deployed path. |
| 4 | Execute final full-system verification and close the acceptance matrix | Full backend lanes, CLI/MCP contracts and CI at the final head; each current-scope acceptance row linked to an executed, scope-matching result, with user-deferred scalability explicitly excluded. Fix actual failures without weakening requirements. |
| 5 | Reconcile configuration and delivery documentation | Resolve C01–C07 using measured/approved values; update affected roadmap/overview/index and local spreadsheet exports; preserve the distinction between implemented, exposed and deployed. |

The historical connected public journey passed at 85ce76e17 (V14): 573 CLI invocations,
real PRE/T4/T5/POST, exact source and Contribution/export custody, PRE/POST
rejection and default review_pending; owned database/bucket cleanup passed.
Live AWS source qualification passed at 074cade5e with the actual restricted
runtime/cleanup identities, pinned versions, lost acknowledgements and exact
cleanup. The hosted cutover and core contributor journey passed. The deployed
cleanup consumer deleted the age-eligible rejected S3 version and preserved both
accepted versions. Remaining native faults, supported upload bounds, the hosted
required-review branch and full-head qualification remain open. Ordinary
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
discovery remains charged. Real Redis outage recovery and Celery child
redelivery are proved with unchanged production leases and backoff. Broker-server
loss and hosted operation remain separate proofs.

## Acceptance evidence still to close

No row below is declared fully complete merely because some related tests pass.
This is the final qualification queue, not a claim that all listed code is absent.

| IDs | Existing implementation/focused evidence | Required closure |
| --- | --- | --- |
| A01–A03 | Hosted `2942dd4e7` passed PRE rejection, T4/T5, POST revision and same-assignment correction through CLI/MCP; paired replay passed. | Reconcile any remaining scope in the exact acceptance rows. |
| A04–A08 | Metadata/body replay, competing custody, interruption and T4 uncertainty tests | Reconcile exact cases and execute integrated final-head failure/retry matrix. |
| A09–A13 | T5 rollback/redelivery, actual local SIGKILL recovery, accepted authority, pending reads and old-POST guard | Real Redis publication outage and Celery child-redelivery proofs passed; reconcile the remaining exact cases at the final head. |
| A14–A18 | Cleanup lock/retention/charge owners, Local/MinIO tests, live AWS lost-ack cleanup and deployed exact aged rejection deletion with both accepted sources preserved | Reconcile the remaining exact cases and scheduled sweep coverage. |
| A19–A23 | Streaming/framing, safe archives, semantic identity and findings tests; local A19 496 MiB slow-provider memory/backpressure drill | Full permitted maxima and safety matrix, native/deployment scope where required. |
| A24–A27, A29 | Source/result/fence contracts, dedicated queue tests and the real Smol project-deadline/isolation fixture passed | Reconcile remaining OOM/crash/output, uncertain-destroy and single-runner queue cases; broad saturation/load qualification is user-deferred. |
| A30 | Managed-style public source acceptance/T5/replay and four typed cases passed at `2f7d8d95c` | Substitution proof complete in its stated scope; no paid-provider integration is selected or required. |
| A28 | Multi-replica/multi-runner implementation and focused tests | User-deferred until after existing deployment delivery; no second instance is required now. Not claimed passed. |
| A31–A32 | Hosted corrected version 2 reached automatic acceptance with one unpaid contribution, zero Reviews and zero awards. The maintained isolated journey proves default review_pending. | Finish the hosted required-review guard and applicable downstream checks. Live human review remains deferred. |
| A33–A35 | Retained migrations, cardinality guards and API/CLI/MCP cutover | The hosted schema migrated from 0069 to 0093 with retained counts verified. Finish connected client contract and qualification evidence on the deployed release. |

## Configuration and external evidence

| Register | Current evidence | Remaining current-delivery action |
| --- | --- | --- |
| C01 | Connected CLI receipts observed 85.09s PRE rejection and 88.46s initial acceptance under the earlier 120s qualification deadline; these are command durations, not isolated PRE-stage percentiles. | The hosted release now uses the user-approved 300s PRE hard deadline, starting after upload, with separate 300s upload total and 30s upload idle limits. API, runner, CLI, MCP and proxy bounds are aligned. The maximum-size hosted retry remains to be qualified. The approximately 60s target remains unmet. |
| C02 | Exact native guest/root/image and resource profile passed the connected small-input journey. | Confirm the chosen existing-runner deployment profile against essential native isolation/failure and supported inputs. No new paid provider or hardware design. |
| C03 | Bounded upload/framing owner tests exist; the earlier 496 MiB slow-provider drill did not complete successfully. | Verify supported input size, memory/backpressure, idle/total timeout and edge limits through the deployed path. A failed near-limit upload is not a pass. |
| C04 | Dedicated queues and single-runner PRE/background resource reservations are implemented. | Verify the configured single-runner bounds and queue independence on deployment. Multi-replica/multi-runner and broad saturation testing are user-deferred. |
| C05 | Existing lease/retry/outbox owners have PostgreSQL and real broker/child-redelivery proof. | Reconcile exact release settings and hosted consumer/recovery behavior; reuse current owners. |
| C06 | The 12h sweep/2h minimum age and guarded exact-version cleanup are implemented. The deployed cleanup consumer deleted an eligible rejected version and preserved both accepted versions. AWS source permissions and lost-ack reconciliation passed. | Reconcile bounded runtime reaping on the hosted path. |
| C07 | Managed-style public source/T5/replay substitution and four typed cases passed at `2f7d8d95c`, recorded in `73d81da66`. | No selected paid provider and no vendor integration required for this delivery. Do not call the substitution proof live vendor qualification. |

## Spec reconciliation: bounded remaining delivery work

This reconciliation uses sections 5, 9, 12–18, 20, 23 and 24 of the canonical
specification, D01–D18/I01–I12, and the user's PR708 submitter-experience
addition. Apply the explicit scalability and human-review deferrals above.
Existing implementation/focused proof is not the same as deployed proof.

| Delivery gate | Type of remaining work | Concrete closure |
| --- | --- | --- |
| Contributor reads and revision terms (A13, A32, A35; PR708 addition) | Core hosted reads passed. | The contributor verified preclaim originals and the exact pending, revision and accepted assignment through the paired clients. Reconcile the remaining authorization, full history and applicable reward-changing cases through current owners. |
| Native failure and isolation (A24–A27) | Test execution and fixes only for demonstrated defects. | The maintained deadline/isolation fixture passed at `9fad17a04`, including destroyed VMs and normal admission restoration. Reconcile OOM/crash/output and uncertain-destroy requirements with matching maintained evidence. Valid accepted input must continue when destroy is uncertain, with capacity held. Fixture build alone closes none of these native outcomes. |
| Upload/retention limits (A14–A23) | Remaining deployed/provider verification. | Prove supported maximum/slow upload and framing/resource bounds, including tighter project archive-limit enforcement. The deployed exact-version cleanup preserved accepted sources. Reuse that result and the existing AWS adapter evidence. |
| Hosted cutover (section 20, A33–A35) | **Deployment complete.** | The drained backup and 0069-to-0093 migration retained all 132 existing table counts. The repaired `2942dd4e7` API, coupled MCP and seven dedicated Celery workers are active. The installed boot unit points to the repaired source. See the [cutover evidence](WS-SUBMIT-001-01.md#hosted-schema-and-release-cutover-completed). |
| Hosted end-to-end and recovery (A01–A18, A29 single-runner, A31–A32) | Core journey and paired replay passed. | PRE rejection, pending and revision under one assignment, MCP correction, exact replay and unpaid acceptance passed. Finish hosted failure distinction and recovery, retained-source checks, required-review guard and scoped queue independence. See the [hosted journey evidence](WS-SUBMIT-001-01.md#hosted-contributor-zip-journey-and-paired-replay-passed). |
| Release checks and handoff | Final verification/review. | Required final-head backend/CLI/MCP/migration/security checks and actual review findings resolved; PR708 presented for explicit merge approval; post-merge/deployment smoke and accurate operational handoff. No new PR or automatic merge. |

Email delivery is a separate user-deferred external setup item: notification code
exists, but DNS/key/test delivery remain incomplete. It must not block status
reads or falsely be reported as working. No second EC2 runner or its proposed
provisioning policy is part of the current finish list.

The original specification includes D01–D18, I01–I12, T1–T5 and A01–A35.
Apply the explicit user scope decision above when assessing current delivery;
do not claim deferred scalability is complete. A partial green suite, fixture
capture, review approval or a single commit does not complete current delivery.
