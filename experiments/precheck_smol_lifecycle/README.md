# Smol upload/pre-check lifecycle qualification

This is an opt-in Rust experiment, not a production checker backend. It receives
ZIP bytes on stdin while preparing a fresh microVM, then stages and extracts
inside that VM and invokes the existing Terminal Systems Python checker. It
records phase timing and requires confirmed deletion before reporting success.

The source image is the existing
[`pilots/terminal_systems/checkers/pre`](../../pilots/terminal_systems/checkers/pre/)
image. No checker rule is reimplemented here. `guest.py` is Python-specific probe
staging, not a general image contract. The fixture request contains the fields
that checker consumes; it is not a production authorized invocation.

## Local mechanism tests

```sh
cargo +1.85.1 test --manifest-path experiments/precheck_smol_lifecycle/Cargo.toml --locked
python3 -m unittest discover -s experiments/precheck_smol_lifecycle -p 'test_*.py'
```

Install the isolated toolchain if needed with
`rustup toolchain install 1.85.1 --profile minimal`. Rust 1.85.1 was used locally because the installed default 1.84 compiler/linker
crashed while building unchanged dependencies. No global toolchain is changed.

## Live host prerequisites

- Linux with accessible `/dev/kvm` and KVM API version 12.
- An explicitly installed `smolvm` release. Pin its release checksum; fixture
  creation additionally records the exact executable SHA-256 and version.
- GNU `/usr/bin/timeout`, used as an independent deadline supervisor for CLI
  processes even if the Rust request process dies.
- A prebuilt local `docker save` archive of the Terminal Systems PRE image.
  The probe checks its SHA-256 before every run; record its embedded image config
  identity and platform when building. No registry credentials or pulls are used
  during trials. Qualify
  image acquisition separately from warmed starts. No guest network, host mount,
  published port, credential or SSH-agent forwarding is requested.
- A private local trial directory on a host where only trusted operators share
  the OS account. Do not run against live submission data.

The live qualification used an M7i Linux host with nested virtualization enabled.
Do not infer KVM access from `Hypervisor vendor: KVM`: that describes the hypervisor
hosting EC2, not `/dev/kvm` availability inside the instance.

## One valid and one invalid check

Build the existing project image in an isolated workspace, then export it with
`docker save`. Record its config digest and platform. The archive hash pins the
exported bytes; it is not an OCI manifest digest. The variables below are operator
inputs; no example path is treated as verified content.

```sh
cargo +1.85.1 build --manifest-path experiments/precheck_smol_lifecycle/Cargo.toml --locked
export PROBE_SMOLVM=/absolute/path/to/verified/smolvm
export PROBE_IMAGE=/absolute/path/to/terminal-pre.tar
python3 experiments/precheck_smol_lifecycle/make_fixture.py \
  --smolvm "$PROBE_SMOLVM" --image "$PROBE_IMAGE" \
  --sample pilots/terminal_systems/checkers/pre/samples/valid \
  --output /tmp/ws-smol-valid-input
experiments/precheck_smol_lifecycle/target/debug/workstream-smol-lifecycle-probe \
  /tmp/ws-smol-valid-input/config.json /tmp/ws-smol-valid-trial \
  < /tmp/ws-smol-valid-input/submission.zip
```

Repeat with `samples/missing-file` and different input/trial directories. The
valid result must say `passed`; the invalid result must say `failed` and identify
the missing file. Both can report successful *probe execution*: inspect
`checker-result.json` for the work verdict, not the probe's process exit alone.

Every trial directory must be new. It contains the exact configuration, a private
lease (random name/owner, expiry and binary identity), bounded command logs,
`checker-result.json`, `report.json` and `cleanup-confirmed`. ZIP scratch is removed
on confirmed settlement, including watcher settlement. Preserve bounded evidence
for diagnosis and remove it deliberately after the experiment.

Run the complete live matrix with a private runtime HOME, valid and missing-file
fixture directories, and a new output directory:

```sh
python3 experiments/precheck_smol_lifecycle/run_live_matrix.py \
  --probe experiments/precheck_smol_lifecycle/target/debug/workstream-smol-lifecycle-probe \
  --valid-input /tmp/ws-smol-valid-input --invalid-input /tmp/ws-smol-invalid-input \
  --output /tmp/ws-smol-matrix
```

This matrix assumes the image cache is warm enough to prepare before the
three-second delayed upload completes; a cold cache failing that assertion is a
latency result to investigate, not permission to skip the assertion.

## Failure and recovery matrix

| Case | Procedure | Required observation |
|---|---|---|
| Overlap | Feed the ZIP slowly through stdin | Preparation finishes before EOF; checking begins only after both are ready |
| Upload fails | Feed only part of the ZIP then close stdin | No staging/check execution; exact owned VM removed |
| Upload exceeds declared bytes | Append bytes to the fixture stream | Size mismatch, no check, cleanup confirmed |
| Abandoned upload | Keep stdin open without finishing; use a short work deadline | Deadline expires; no permanent reserved VM |
| Preparation failure | Use a controlled runtime failure | At most three attempts, confirmed deletion between attempts, one original deadline |
| Check timeout | Run a fixture command that exceeds the deadline | Infrastructure failure, never a contributor-work verdict |
| Parent death | Kill the Rust parent with SIGKILL after VM creation | Independent watcher removes its VM after the original expiry; no result fabricated |
| Foreign VM | Keep a separate control VM with a different owner label through recovery | Control VM survives; no prefix-wide deletion |
| Delete failure | Refuse deletion in the controlled runtime | No cleanup-success marker; retained failure evidence; no retry after uncertain cleanup |

The watcher waits until work expiry plus two seconds for independent CLI timeout
termination, then uses a separate 15-second cleanup budget. A per-trial file lock
serializes cleanup. It checks exact name and owner label before deletion and
checks inventory afterward. A cleanup failure still requires operator attention;
neither a successful delete command nor an expired lease proves freed capacity.

## Scope of evidence

See [qualification evidence](QUALIFICATION.md) for the measured live matrix and
its limits. Unit and controlled-process tests establish local orchestration and
archive-helper behavior only. The live parent-death test kills the request after
VM boot; it does not prove host-reboot recovery or arbitrary daemon failure during
creation. Recovery relies on a live independent watcher and host clock. Production
needs durable reconciliation across service/host restarts.

Reports measure upload/preparation from after binary/image preflight. The live
matrix additionally records process wall time: hashing the local image archive
cost about one second in these trials. Production should verify the trusted
cached image at provisioning, rather than hash a large archive per request.

Production work remains: extend the existing typed execution capability; begin
preparation after the first authorized locked-policy snapshot and revalidate it
after upload; add bounded concurrency to the Rust listener; preserve canonical
ART ZIP/manifest verification and callback grants; preserve selected PRE lease,
replay and admission ownership; introduce truthful Smol isolation receipts.

Resource parity remains a separate gate: integer vCPUs do not enforce fractional
`cpu_millis`; guest memory does not establish a host-process RSS cap; disk sizes,
PID limits, output buffering, filesystem mutability and network/model access need
explicit qualification. The probe's sample sizes and resource values are not
new Workstream project limits. No production configuration is changed here.
