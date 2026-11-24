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

Recent focused evidence includes atomic invalidation (`8a854f7a6`), public
ZIP/T5 lineage (`168e5268f`), and policy-error translation (`d31a45773`). These and the cleanup/recovery runs recorded below are bounded results, not
full-head qualification.

## Execution deployment decision

The API/application server and microVM execution run on separate infrastructure.
The user reports a new t3.large EC2 application instance; this is deployment
context, not independently verified provisioning evidence. Do not require nested
virtualization, a Smol binary, host sockets or local KVM on the API instance.
Self-hosted microVM execution will use dedicated runner infrastructure. A paid
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
| 1 | Finish uncertain/unsealed and genuine-orphan reconciliation | Reconcile interrupted multipart and lost acknowledgements; retained/stalled sources survive; actual absence and settled writes release charges once; exercise worker loss/restart. |
| 2 | Remove superseded preparation/submission writers and remaining consumers | Trace all remaining callers, preserve their distinct authority/history contracts, then delete obsolete implementation. Current T5 `create_accepted` remains. |
| 3 | Complete separate-runner integration and runtime/provider/resource qualification | Authenticated remote execution replacing the current API-side Unix-socket coupling; actual Smol one-session/isolation proof on runner infrastructure; representative maxima, cold paths, concurrency and timing measurements; applicable AWS exact-version/uncertain multipart proof. Portable/MinIO evidence is insufficient for these claims. |
| 4 | Execute final full-system verification and close the acceptance matrix | Full backend lanes, CLI/MCP contracts and CI at the final head; every A01–A35 row linked to an executed, scope-matching result. Fix actual failures without weakening requirements. |
| 5 | Reconcile configuration and delivery documentation | Resolve C01–C07 using measured/approved values; update affected roadmap/overview/index and local spreadsheet exports; preserve the distinction between implemented, exposed and deployed. |

The concrete next runtime gap is order 1. Sealed-source scheduling and task
isolation passed scoped implementation review at `8928f3924`; focused integration
cases passed across two runs. This is not deployed-provider or broker-crash
qualification. Expired-foreground recovery passed scoped review at `81d69a207`,
including blocked-task progress and after-lock service revocation. Unsealed/
uncertain and genuine-orphan reconciliation remain unfinished. Further optional test
migration must not displace closing this integration.

The current unsealed change extends that same cleanup owner: Local incomplete
uploads can be reclaimed, and an observed late completion is retained until a
fresh aged claim identifies its exact version. Focused Local/PostgreSQL and MinIO
checks passed, as did the existing cleanup-owner suite. Recorded MinIO multipart
handles now settle only after parts/handle/version absence; a real PostgreSQL
lost-abort/replay case proves conservative charge retention then one release.
Remote initiation without a recorded handle now retains discovered IDs before
abort and binds them to a fresh cleanup authorization. Focused PostgreSQL/MinIO
checks cover growing observations and lost-abort replay. Empty ambiguous
discovery remains charged; genuine-orphan reconciliation and operational crash
drills remain open. This partial implementation does not complete order 1.

## Acceptance evidence still to close

No row below is declared fully complete merely because some related tests pass.
This is the final qualification queue, not a claim that all listed code is absent.

| IDs | Existing implementation/focused evidence | Required closure |
| --- | --- | --- |
| A01–A03 | Public ZIP flow, default/project PRE and formal finalization tests | Complete API/CLI journey with required real runtime and POST evidence. |
| A04–A08 | Metadata/body replay, competing custody, interruption and T4 uncertainty tests | Reconcile exact cases and execute integrated final-head failure/retry matrix. |
| A09–A13 | T5 rollback/redelivery, accepted authority, pending reads and old-POST guard | Real worker crash/broker-unavailable drill and final-head reconciliation. |
| A14–A18 | Cleanup lock/retention/charge owners and Local/MinIO provider tests | Production sweeps, accepted-source survival, AWS versions and uncertain multipart ownership. |
| A19–A23 | Streaming/framing, safe archives, semantic identity and bounded findings code/tests | Measured permitted maxima/slow-provider memory bounds and complete safety matrix. |
| A24–A30 | Source/result/fence contracts and runtime/capacity/substitution tests | Actual native isolation/failure/cleanup, multiple replicas/nodes, saturation and adapter qualification. |
| A31–A32 | Existing governed POST/revision/acceptance owners preserved with focused journeys | Final combined downstream tests, exact ContributionRecord/award facts, both review branches. |
| A33–A35 | Retained migrations, cardinality guards and API/CLI/MCP cutover | Finish old-writer retirement and full current-head migration/client convergence proof. |

## Configuration and external evidence

C01–C07 remain open until individually reconciled with the specification and
actual deployment evidence. Test-only leases/profiles are not approved defaults.
Native Smol qualification must run on the dedicated execution infrastructure,
not the API host. The current local environment does not supply that evidence. AWS source
qualification remains separate from MinIO and ordinary SHA-object operation.
Current main's dedicated credentials replace expiring provider activation;
submission work must not reinstate the retired activation subsystem.
Request only concrete missing access or decisions after the corresponding drill
and proposed values are prepared.

The full goal includes D01–D18, I01–I12, T1–T5 and A01–A35. A partial green
suite, fixture capture, review approval or a single commit does not complete it.
