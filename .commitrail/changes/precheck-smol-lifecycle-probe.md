# Qualify upload-overlapped Smol preparation

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Add an executable Rust probe for fresh Smol preparation during ZIP upload, bounded execution and resource cleanup before changing production's verified-material boundary.

## Intent

Start a clean checker environment when the authorized submission upload starts.
Once upload and preparation both finish, unpack and check in that environment.
Cancel or expire unused environments and reclaim their capacity. Keep the Rust
runner and language-independent checker contract. Existing product limits remain
owned by their current policies; probe parameters are not new project policy.

## Current behavior

`PreparedSubmissionBundlePreparationCommand.prepare` reads authorized TASK and
PROJECT context before receiving `request.stream()`, but starts selected PRE
execution only after ART seals and inspects the archive. The Rust service accepts
health/execute, handles connections serially, verifies callback-scoped ART material
and runs gVisor or docker-dev containers. Terminal Systems PRE is a standalone
Python image. No Smol backend, upload reservation or VM cleanup exists today.

## Bounded change

### Allowed

- `experiments/precheck_smol_lifecycle/**`: Rust lifecycle probe, guest-side ZIP
  staging, real existing Python checker invocation, focused failure tests and runbook.
- This record and a precise runtime qualification note in `external_checkers/README.md`.

### Not allowed

- Production API, authorization, ART custody, checker result or database changes.
- Claiming synthetic process tests prove VM isolation, live latency or deployed support.
- Managed services, new project limits, named-task behavior in the shared runner,
  replacing the existing Python checker, or publishing/deploying a runtime.

## Design and decisions

First qualify the proposed runtime mechanism in a separate executable experiment.
An upload is represented by stdin, allowing throttling, truncation and disconnect
without a second upload API. Prepare a new named VM concurrently; use a single
absolute deadline across upload, preparation retries, staging and checker work.
No submitted material reaches a VM before the upload completes. Extract only in
the guest. Clean up on every ordinary exit, preserve evidence when cleanup fails,
and explicitly test process-death/expiry recovery before production adoption.
Emergency cleanup has its own 15-second budget after the work deadline. A
separate watcher survives the request process; all Smol CLI calls run under an
independent OS timeout. Recovery waits for the work deadline plus a bounded
termination margin, locks the private trial directory, checks exact name and
owner label, deletes only that VM and confirms its absence. Unconfirmed cleanup
retains evidence and prevents retry; it is never a successful capacity release.
The probe retries only `runtime_command_failed` from create/start/readiness,
normalized as `preparation_unavailable`, for at most three attempts with bounded backoff
and confirmed deletion between attempts; execution is never retried.

Stdin has a caller-declared exact byte count, SHA-256 and a fixed probe ceiling.
Temporary ZIP bytes are deleted after settlement, including watcher settlement.
The guest extractor is Python-specific experimental machinery for the existing
Terminal Systems image, not a new production parser or a portable staging ABI.
Fake-process tests prove orchestration only. This probe does not establish
production AUTH/ART grant custody, canonical ZIP/manifest verification, selected
reservation/lease behavior or immutable contribution evidence.

Use a prebuilt local `docker save` archive, verified by SHA-256 before each trial.
Record its embedded OCI manifest/config identity and platform at build time. No
registry pull or credential change occurs inside a trial; image construction and
host recovery are separate operational steps.

Record the runtime launcher version and SHA-256, verified distribution checksum,
image archive SHA-256 and OCI identity, architecture, host
KVM availability and VM identity. Compare the integer vCPU count, guest memory,
disk, PID/output limits, read-only filesystem, network and UID/mount behavior
against the current runner; do not claim resource parity from VM boot alone.
Image provisioning network and checker workload network are distinct.

Production integration must use the first authorized locked policy snapshot,
revalidate it after upload, and extend the existing execution capability. Preparation
must not fabricate the post-upload selected lease or grant. The Rust listener needs
bounded concurrency; Smol must truthfully report its own isolation identity. The
existing trusted ZIP/manifest verification must be preserved when extraction moves.
Fractional CPU limits and host-memory/disk enforcement require qualification: guest
vCPU/MiB settings are not automatically identical to current container ceilings.

## Acceptance criteria

- [x] Verify local image archive bytes and record embedded image identity/platform.
- [x] Demonstrate prepare-ready before delayed upload EOF; execution starts only after both.
- [x] Exercise truncated/overlimit uploads without execution, expired waiting, bounded retry, at-most-once checker execution and cleanup failure evidence.
- [x] Kill the live parent after VM creation; the independent watcher removes only its owned VM and preserves a foreign control VM.
- [x] Run the existing Terminal Systems Python checker on a ZIP extracted in Smol.
- [x] Record preparation, upload, post-upload wait, checking and cleanup timings.
- [x] Distinguish fake-process tests, live VM proof and remaining production work.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, qa, test_delta, documentation
- Human review focus: cleanup under process death; runtime enforcement gaps; exact scope of live proof.

## Evidence

| Claim | Command/proof | Result | Remaining uncertainty |
|---|---|---|---|
| Orchestration | `cargo +1.85.1 test --manifest-path experiments/precheck_smol_lifecycle/Cargo.toml` | Eight lifecycle and three controlled-process tests pass with Rust 1.85.1 | This local command does not prove VM behavior; the live row below supplies that evidence |
| Guest archive handling | `python3 -m unittest discover -s experiments/precheck_smol_lifecycle -p 'test_*.py'` | Six focused extraction tests pass | Not canonical production ART verification |
| Live lifecycle | Runbook matrix: valid/invalid Terminal Systems ZIP, delayed/truncated stdin, deadline, SIGKILL and foreign VM | Live seven-case matrix passes; see experiment qualification | No production isolation/resource-parity claim |
| AWS host | Authorized CPU-option change, KVM boot and service-health verification | Authorized CPU option enabled; KVM API 12 and live VM boot verified | Existing containers restored; AWS live proof refreshed; API/worker/beat/checker healthy |

The unchanged default Rust 1.84 toolchain crashed in compiler/linker dependencies.
A task-specific Rust 1.85.1 toolchain builds the probe; the global default is unchanged.

## Review findings

Plan review required explicit cleanup budget, exact ownership, process-death and
foreign-VM controls, bounded input/retry, resource inventory and honest proof scope.
Those requirements are now included above. Review also added regressions proving
final cleanup failure cannot report success and preparation failure cancels a
still-open upload before its deadline. Documentation reflects completed
qualification while retaining the production integration boundary.

Preparation must not occupy the existing single connection handler while waiting
for upload; no private material grants may be issued before verification. Runtime
ownership must survive process death and cleanup must never sweep foreign VMs.

## Reconciliation

- Current-source reconciliation: origin/main `7f6a71a69`; the Terminal Systems worktree has unrelated changes and is left untouched.
- Next usable boundary: preserve resource/ART/auth contracts while implementing the production adapter and upload overlap; durable host/service restart reconciliation and creation-race proof remain required.
- Remaining risks: resource-enforcement parity, host-reboot/creation-race recovery and production integration remain unqualified.

Roadmap assessment: this opt-in experiment changes no publicly exposed or deployed
Workstream capability, policy branch, current runtime support, or required product
dependency. `docs/roadmap_status.md` retains those capability claims unchanged;
the execution-owner README links the separate qualification evidence. No local
spreadsheet exports are present in this checkout.
