# PILOT-00 — Establish The Offline gVisor Build Boundary

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Preserve a reproducible feasibility result that either identifies a bounded offline image-build and oracle-test mechanism under gVisor or gives PILOT-04 and PILOT-06 concrete evidence to select a separate build boundary.

## Intent

Resolve the highest-risk execution unknown before the external-checker launcher is designed: whether a contributor Dockerfile and its oracle can be built and exercised inside gVisor with networking disabled, without a host container socket or privileged sandbox. The spike must distinguish an unsupported infrastructure path from a contributor work failure and must not create a product runtime.

## Current behavior

Current `main` provides the local API/worker/PostgreSQL/Redis/MinIO stack but no external-checker launcher or gVisor runtime. [`docs/roadmap_status.md`](../../docs/roadmap_status.md) records the external runner as remaining pilot work. PILOT-04 and PILOT-06 require the PILOT-00 result before selecting their build and execution design.

The Linux probe established that the maintained Kaniko fork can build the included digest-pinned Alpine fixture inside gVisor from a sealed cache. A second gVisor sandbox ran its oracle offline. Rootless BuildKit could not establish its subordinate user mapping on this host under either gVisor or an ordinary `runc` control. The host still has no registered `runsc` runtime; an isolated trusted Docker-in-Docker harness supplied the runtime registration for the experiment only.

## Bounded change

### Allowed

- `.commitrail/changes/pilot-gvisor-offline-build-spike.md` for this bounded intent, evidence and disposition.
- `experiments/pilot00_gvisor_offline/**` for a minimal sample Dockerfile, oracle, pinned-input manifest and reproducible probe.
- `docs/engineering/pilot00-gvisor-offline-build-spike.md` for the measured decision input and explicit platform limits.
- Narrow PILOT-00/PILOT-04/PILOT-06 facts in `docs/roadmap_status.md` after the evidence changes the current pilot dependency.
- GitHub issue references that link the final recommendation from #491 and #493 after review.

### Not allowed

- Backend, frontend, CLI, database schema/migration, authorization, policy, catalogue, composition-root or production workflow changes.
- A product launcher, checker SDK, model proxy, hosted deployment, Kubernetes path or macOS implementation.
- A privileged submitted-code sandbox, host Docker/containerd socket in the sandbox, writable host cache, enabled external network during build/test, or secret injection.
- Removal or mutation of existing containers, images, volumes, networks, local pilot data or unrelated host configuration.
- Treating Docker Desktop's ordinary Linux runtime as gVisor or claiming hosted/macOS evidence that was not executed.

## Design and decisions

Use a project-scoped disposable probe with exact tool/base identities and retained machine-readable measurements. The selected builder is a non-privileged Kaniko container running as root inside gVisor with only `CHOWN`, `DAC_OVERRIDE`, `FOWNER` and `SYS_CHROOT`; it has external networking disabled, no host socket, no `SYS_ADMIN` and read-only digest-bound offline inputs. Run the oracle against the produced image in a separately identified, non-root and capability-free gVisor execution boundary.

Installing or registering a runtime on the development host is probe setup, not product code. This host was not mutated: a privileged, networkless outer Docker-in-Docker container acted as trusted development infrastructure and registered `runsc` only for its inner daemon. This does not prove a privilege-free deployment. A failed mechanism is a valid result when the failure is reproduced and classified without silently relaxing isolation.

## Acceptance criteria

- [x] Record the exact Linux host, Docker, gVisor, builder and pinned base-image identities used by the probe.
- [x] Build one sample Dockerfile and run its oracle under gVisor with external networking disabled, no host socket and no privileged sandbox, or preserve a reproducible reason the mechanism cannot satisfy that boundary.
- [x] Prove the offline cache/base identity, sandbox user/capability/socket/network facts and output identity without trusting submitted output alone.
- [x] Measure elapsed time, sampled CPU, peak observed memory and disk use for the stages that this host can honestly execute.
- [x] Demonstrate a genuine Dockerfile/work failure separately from runtime, cache, builder and limit failures.
- [x] Record a provisional tested envelope and the effect of timeout, memory and disk limits without converting infrastructure failure into contributor failure.
- [x] State the Docker Desktop/macOS development fallback and every unverified platform limit accurately.
- [x] Give PILOT-04 and PILOT-06 an explicit recommendation and link the reviewed result from [#491](https://github.com/Flow-Research/workstream/issues/491#issuecomment-6059462336) and [#493](https://github.com/Flow-Research/workstream/issues/493#issuecomment-6059463258).

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, qa, test_delta, documentation, product_ops
- Human review focus: Whether the executed evidence proves the named isolation boundary, whether any workaround weakens it, and whether the recommendation should keep image builds inside gVisor or move them to a dedicated build VM boundary.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current host and runtime boundary | `uname`, Docker inventory, pinned `runsc` archive checksum, outer/inner container inspections | Ubuntu 24.04 / Linux 6.8 x86_64, Docker 29.1.3; host daemon retains only `runc`; inner daemon registers `runsc release-20260928.0` | Hosted execution-node registration and hardening remain unproved |
| Offline build and oracle boundary | `PILOT00_RUN_ID=replay1 PILOT00_STATE_DIR=/tmp/ws-pilot00-replay1 PILOT00_EVIDENCE_ID=20261008T120000Z ./experiments/pilot00_gvisor_offline/probe.sh run` | PASS: 16.420 s build and 3.226 s second-sandbox oracle; result JSON SHA-256 `afc06f12ed50606372147a97824467ec448d28037ab8a5baa8dc26616b844c81` | Tiny Alpine fixture only; output is attempt-bound but not byte-reproducible across builds |
| Isolation and resources | Builder/oracle launch inspections, in-sandbox assertions and sampled stats under `/tmp/ws-pilot00-replay1/results/20261008T120000Z/` | `runsc`, network none, no socket, builder non-privileged with four bounded in-sandbox capabilities; oracle UID 65532/capability-free; one-CPU build peak sample 27,283,948 bytes and 35 PIDs | Trusted outer DIND is privileged development infrastructure; representative sizing is unproved |
| Failure classification | Intentional exit, empty cache, forced stop, 16 MiB and 1 MiB output probes in the same replay | Exit 42 stayed a work failure; cache/deadline/OOM/disk cases remained infrastructure candidates | PILOT-04 owns final transport-neutral mapping and retry policy |
| Rootless BuildKit comparison | Pinned rootless image under gVisor plus ordinary `runc` control | Both controls failed RootlessKit user-namespace setup on this host; no isolation relaxation was adopted | Not a general result for every configured Linux host |
| Collision, input and startup guards | Same-name foreign-volume probe, fake-Docker `../../` evidence-ID probe and `experiments/pilot00_gvisor_offline/test_probe.sh` | Exit 73 left the foreign label/data unchanged and created no harness container; exit 64 made zero Docker calls and created no escaped path; immediate and 45-attempt daemon-readiness paths passed | Concurrent hostile Docker administration is outside this local experiment |
| macOS behavior | Official gVisor platform constraints and honest host inventory | Linux proof only; ordinary Docker Desktop is an explicitly recorded `docker-dev` fallback, not gVisor | No macOS host was available; Apple Silicon and custom VM runtime paths are unverified |

## Review findings

- A pre-existing same-name outer volume was reusable before its ownership label was checked. The probe now refuses a foreign volume before mounting or starting the privileged harness and rechecks ownership immediately after creation.
- An operator-supplied evidence ID could escape its results directory. The probe now accepts only a bounded ASCII alphanumeric/hyphen grammar and rejects invalid input before filesystem or Docker access.
- Exhausted inner-daemon readiness checks previously fell through to an opaque runtime-inventory failure. The probe now stops with an explicit bounded-readiness diagnostic, with stubbed immediate-success and 45-failure controls.

## Reconciliation

- Current-source reconciliation: Reconciled with `main`
  `b169e83f816bba417fc0618a6e2d419acb2f94ed`, retaining the merged local pilot,
  checker-delivery and lane-catalogue owners. The spike changes no backend
  contract, migration, authority, product composition or workflow.
- Next usable boundary: After review and issue linkage, PILOT-04 can adopt the sealed-cache Kaniko builder and separate gVisor oracle boundary; PILOT-06 still owns checker images and representative fixtures.
- Remaining risks: Actual hosted infrastructure, representative Terminal-Bench resource limits, cleanup after host loss, byte-reproducible image output and macOS Docker Desktop behavior remain unproved.
