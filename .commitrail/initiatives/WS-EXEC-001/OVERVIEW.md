# WS-EXEC-001 — Managed lifecycle for self-hosted checker microVMs

- Disposition: Complete
- Intent: finish the real upload -> isolated intake -> pre-check -> immutable Submission -> durable post-check -> governed outcome path through Workstream's typed adapters. Preparation begins after authorization while the same request uploads its ZIP. Success, rejection, disconnect, deadline, runtime failure and controller restart must release exactly owned resources. User explicitly authorized continuing through all implementation boundaries and live EC2 proof; the standalone qualification is not completion.

## Observed owners and concrete gaps

`PreparedSubmissionBundlePreparationCommand.prepare` authorizes TASK/PROJECT,
starts trusted intake preparation while the same request uploads, then relocks
the policy before inspection. ART consumes canonical ZIP/default processing
through its typed intake capability, independently verifies raw exports and
closes intake before ordered project PRE execution. POST uses the same intake
under its durable execution/lease/outbox custody. `ExternalCheckerExecutionAdapter`
and its explicit factory compose the Rust node's project execution capability.
The node supports bounded Smol execution, exact-owner cleanup and independent
guardians. Both capabilities have owner/adapter proof and a combined public API/Celery
journey on an isolated one-slot Smol node. Hosted composition requires pinned
intake configuration; the intended production Flow/AWS deployment remains separate.

The Smol 1.31.4 qualification (PR #672) proves fresh VM overlap, real Python checker
execution, cancellation/deadlines and request-process recovery, but not production
resource parity, host/controller restart recovery, ART integration or deployment.
The existing model-runtime worktree is independently owned and uncommitted; do
not replace its gateway/budget ownership with arbitrary network access or secrets
in a VM. Integrate its stable capability when available, preserving private grants.

## Design

Keep project checker languages/images independent of the Rust runtime. Extend the
existing execution capability and composition root rather than adding a second
product job system. Prepared sandboxes are transient resource capabilities, never
Submission/Review/acceptance facts or prematurely issued ART grants. Revalidate
the locked policy after upload before consuming a preparation.

Two narrow typed capabilities share one Rust node: ART owns trusted intake;
CHECKERS owns registered project-image execution. Each has one explicit typed
`unix_socket` factory registration. The private Rust engine is not a public
command API. One deployment selects one engine; project policy cannot select it.

Always prepare the service-owned, pinned Workstream intake image during upload,
including default-only policies. Do not speculatively allocate project VMs. This
keeps the finite preparation footprint to one VM per uploading request; project
PRE bindings run in their existing order, each in a new VM after default passes.

Intake is two-phase. First, stream the sealed archive into its prepared intake
VM and run canonical ZIP inspection/extraction only. Return the inventory and
archive/image receipt; populate an `ArtifactScratchManager`-allocated workspace
with bounded raw file streams, checked by ART against every normalized path,
size and hash. The backend never decompresses the ZIP. ART retains quota and
sealed-tree custody and issues the existing callback-scoped material grants.
Second, after policy relock and manifest-bound selected PRE reservation commits,
run the canonical default evaluation inside that same sealed intake session,
bound to the committed reservation and exact default input. Only a passing
default permits project PRE execution. No project image can return authoritative
structural/default facts. Receipt validation binds the service-configured intake
platform/config image identities and `WORKSTREAM_DEFAULT_BEHAVIOR_SHA256`.

POST uses this same ART intake/materialization capability under its existing
durable CHECKERS lease. Boundary 2 replaces production host calls to
`SubmissionArchiveInspector.inspect`, `_projected_tree`, and
`evaluate_verified_archive`; retain their canonical implementations in the trusted
guest and conformance fixtures, not as a production fallback. The node lease is
private transient execution custody, never durable artifact storage or product
state. Final admission, immutable evidence and governed outcome owners stay put.

The Rust node service owns bounded preparation/execution capacity, private durable
leases, exact labels, finite retry and cleanup budgets, and startup/expiry
reconciliation. Disconnection cannot orphan a VM indefinitely. Unconfirmed
cleanup makes the node unavailable; never report released capacity prematurely.
Smol receipts identify Smol, not gVisor. Enforce the existing requested CPU/memory
limits with workload cgroups and bound virtualization overhead separately at the
host; preserve non-root execution, PID/output limits, read-only submitted material
and default-deny networking. Runtime insufficiency is an infrastructure failure.

## Authorized implementation boundaries

1. Production Rust Smol engine: generic guest launcher, resource enforcement,
   exact image cache identity, bounded concurrent sessions, preparation and
   restart/expiry cleanup; extend the existing adapter's health/isolation vocabulary.
2. Same-request upload preparation and isolated ART intake: typed request-scoped
   preparation, policy relock, canonical guest ZIP/default processing, verified
   material handoff, cancellation/retry and existing immutable admission owners.
3. Deployment composition and public durable-worker drill: exercise both PRE and
   POST, invalid work vs infrastructure failure, retry, cancellation, timeout,
   controller restart, foreign-resource survival and final contribution evidence.

These are reviewable PR boundaries, not stopping points for the authorized task.
Do not merge any PR without specific user approval. Use isolated EC2 directories,
services, ports and databases; preserve the other integration work and data.

## Proof and risks

Use focused regressions at every changed owner, existing contract suites, real
PostgreSQL/artifact-provider integration and a live KVM public-API/worker drill.
The acceptance record must bind exact submitted bytes, locked rules, checker
results and governed outcome. Test CPU/memory/PID/output enforcement rather than
inferring limits from vCPU count. Resource exhaustion, cancellation and unknown
execution outcomes must not become failed-work verdicts or unsafe execution retries.

All three implementation boundaries are complete for the self-hosted lifecycle.
The public drill proves cancellation, ordered PRE, bounded launch retries,
controller recovery, durable POST recovery through the public Operator route,
true-policy review routing and false-policy acceptance with exact contribution
and conditional award facts. It uses a local Flow verifier fixture, recorded guide
inference and MinIO; it does not certify production Flow, native AWS S3, live model
invocation or the intended hosted deployment. Next usable boundary: provision the
pinned intake and approved checker images in that deployment and repeat its
provider/identity-specific proof. This does not authorize merge or a new initiative.
