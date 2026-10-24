# Smol lifecycle qualification evidence

On 2026-10-23 the opt-in probe ran the unchanged Terminal Systems Python PRE
checker in Smol 1.31.4 on Linux x86_64, EC2 m7i.xlarge with nested KVM enabled.
This establishes the tested mechanism, not a deployed Workstream integration or
an SLA. No external model was called. Production pre/post execution is unchanged.

## Measured behavior

The [seven-case live receipt](live-results.json) is captured from
`run_live_matrix.py`, using the valid and missing-file project fixtures. Every
ordinary trial independently checked the owned VM absent from inventory and ZIP
scratch absent. The parent-death case checked the same after SIGKILL and preserved
a separately owned control VM, which the harness then deleted explicitly.

| Trial | Preparation | Stage/check | Cleanup | Outcome |
|---|---:|---:|---:|---|
| First run, cache cold | 17.101 s | 0.326 s | 0.081 s | Passed; VM absent |
| Cached image, upload held open | 0.645 s | 0.325 s | 0.081 s | Passed; zero post-upload VM wait |
| Missing required file | 0.635 s | 0.326 s | 0.081 s | Work failed with actionable `instruction.md` finding |
| Truncated/oversized stream | 0.624–0.625 s | No execution | 0.081 s | Upload rejected; no checker result |
| Abandoned stream | 0.646 s | No execution | 0.081 s | Five-second work deadline; cleanup confirmed |
| Sleeping checker | 0.635 s | Deadline interrupted | 0.081 s | Infrastructure failure; no work verdict |
| Request process killed | Running VM observed | No submitted material staged | Watcher at expiry | Owned VM removed; control survived |

These are individual runs on one host, not latency percentiles or throughput
measurements. The first cold run excludes image build/download time. Warm trials
reuse the trusted image cache, never a previous submission's VM. The cold receipt
was collected during initial bring-up; the JSON matrix records the later warm
candidate built from `04faf7fc7d1cb32334d1abfc37a098253c2caa4f`; subsequent
review repairs add regression tests and update documentation only. Report timing starts after preflight. Whole-process timing in the JSON
also includes roughly one second to hash the image archive; it includes
the harness's deliberate upload delays. Production image verification belongs at
trusted cache provisioning, not on each upload.

## Identities and custody

- Smol release: `v1.31.4`, [upstream Linux x86_64 archive](https://github.com/smol-machines/smolvm/releases/tag/v1.31.4).
- Distribution SHA-256: `b5eac8d2643aed414e4557dfd67df73be033d2c915848c3deb59c99802da2cf6`.
- Launcher SHA-256: `b67b25f363403e19deceb6897e5a4d94be30a079f8cb751372782f17fc99003a`.
- ELF binary SHA-256: `bde76030c7f6dcfbc2da730c6c51a46eea0ba51124c07ed50fcf9e21184797a3`.
- Live matrix probe SHA-256: `62e70d4599210c3e71a49d3038d98764093c9b8bd7c4b442d7d5a1012365e0d3`.
- Image source: existing `pilots/terminal_systems/checkers/pre/Dockerfile` and `checker.py` from base `7f6a71a69daf563742b72c706e6d09aa742ac25e`, built separately and exported with `docker save`.
- Archive SHA-256: `83952c661d5bbbcedda082f683e402cf7e9ac0cb1448783cd174e4b1625aefd7`.
- Embedded Linux/amd64 image config: `sha256:7fd64da84293336bcf24ccae10577d6fd8ac03c85ef760eb9ed5b20161ec5470`; Docker image index: `sha256:3bde4c6d7de386c2e5c6ed47b64a4b223047be4d3cc703609189a60332311e54`.
- Host kernel: `7.0.0-1014-aws`; KVM API 12. Probe VM: one vCPU, 512 MiB guest memory, 2 GiB storage, 1 GiB overlay.
- Smol inventory reported network disabled, zero host mounts, zero ports. In-guest observation before upload found UID 65532, no `/work/input`, and only `dummy0`/`lo` interfaces. This is configuration/guest observation, not a packet-level egress audit.

The release archive checksum was verified before extraction. Its guest rootfs
contains absolute symlinks, so extraction checked member paths and rejected any
member traversing an archive symlink before preserving guest symlinks. The probe
pins its launcher; distribution integrity remains an operator prerequisite.
No credentials, host mounts or project data were forwarded to the VM. Minimal
fixture request IDs are synthetic and confer no production authority.

## Remaining production requirements

- Integrate through the existing typed adapter and upload command, after initial
authorization and with locked-policy revalidation after upload.
- Preserve canonical ART verification, exact material grants, selected execution
leases, immutable submission custody and both review-policy branches.
- Add bounded concurrency and durable cleanup reconciliation across host/service
restarts. This test covers a killed request with its watcher alive, not watcher
loss, host reboot or creation races in the runtime daemon.
- Qualify fractional CPU quota, host RSS/disk/PID/output enforcement, read-only
filesystem behavior, and concurrent load. Integer vCPU count is not `cpu_millis`.
- Design restricted external-model access and credentials; this matrix is offline.
- Qualify representative Rust/C/C++/C# workloads and post-submission execution.
The probe's Python guest staging is not a universal image contract.

Local proof also covers three-attempt preparation bounds, no retry after uncertain
cleanup, exact owner-label rejection, successful delete without actual removal,
stalled CLI timeout, and ZIP path/symlink/expansion limits. These controlled tests
do not establish microVM resource enforcement. Failed cleanup remains explicit
and retains evidence for operator recovery.
