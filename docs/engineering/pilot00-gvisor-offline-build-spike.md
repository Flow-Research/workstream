# PILOT-00 offline gVisor build spike

## Result

A digest-pinned sample Dockerfile built successfully with the maintained Kaniko
fork inside gVisor with networking disabled, no host container socket and a
non-privileged container configuration. A trusted launcher then loaded the
resulting image tar and ran the oracle in a second gVisor sandbox. The oracle ran
as UID 65532 with no effective capabilities, a read-only root filesystem, only
loopback networking and no Docker socket.

This establishes feasibility for the small included fixture. It does not
establish production readiness or resource limits for a typical Terminal-Bench
task. The measured builder runs as UID 0 *inside gVisor* with only `CHOWN`,
`DAC_OVERRIDE`, `FOWNER` and `SYS_CHROOT`; its Docker container is not
privileged and does not receive `SYS_ADMIN`. The second oracle sandbox is
non-root and capability-free.

The development probe uses a privileged, networkless Docker-in-Docker container
as trusted outer infrastructure because the available host cannot register a
new Docker runtime without administrator access. The submitted Dockerfile and
oracle never enter that outer trust boundary directly: they run in inner
`runsc` containers. This harness is a way to test gVisor on a development host,
not evidence that a whole deployment is privilege-free. A hosted launcher needs
a dedicated Linux execution node where an administrator has registered `runsc`; it must
fail closed when that runtime is absent.

## Recommendation for PILOT-04 and PILOT-06

Use the maintained `osscontainertools/kaniko` executor for the first bounded
external image builder, and execute the produced image in a second gVisor
sandbox. Keep image preparation, output import and sandbox launch in the trusted
launcher. Do not expose its Docker or containerd socket to the builder, produced
image, submitted tests or oracle.

The launch sequence should be:

1. On trusted infrastructure, resolve each approved base to a platform manifest
   digest, fetch it before the attempt and create a digest-bound OCI cache.
2. Mount the request context and sealed cache read-only into a fresh, networkless
   Kaniko sandbox. Give it one bounded writable output directory and no secret.
3. Hash the image tar outside the sandbox and bind that attempt-specific digest
   to the immutable evaluation request and result contracts selected in
   PILOT-04. The spike does not add a transport or persisted field.
4. Import the tar through the trusted launcher and run each oracle/test phase in
   a new `runsc` sandbox with a read-only root, non-root UID, no capability,
   no socket, no external network and phase-specific CPU, memory, PID, disk and
   deadline limits.
5. Preserve the distinction between a checker/work result and launcher,
   material or capacity failure. Remove all attempt containers and writable
   scratch after evidence has been sealed.

`canonical-base-image` should select an approved image family and platform.
`pinned-from` should require the exact platform manifest digest that indexes a
present sealed cache entry. An index digest alone is insufficient when the
execution platform has not been fixed. Missing cache material must fail the attempt
as infrastructure; the launcher must not turn networking on to repair it.
Remote `ADD`, package downloads and other network-dependent Dockerfile steps are
therefore unsupported unless all required bytes are supplied as verified input.

The first launcher limits may use the tested envelope of one CPU, 1 GiB and 128
PIDs for this builder and 0.5 CPU, 256 MiB and 32 PIDs for this oracle. These are
probe settings, not safe production limits. PILOT-04/PILOT-06 must benchmark an
adjudicated, representative task before fixing defaults. In particular, output
disk needs room for the image tar plus builder scratch and evidence; the 1 MiB
negative probe failed while the sample tar alone was 3,638,784 bytes.

## Reproducible probe

The artifact is under
[`experiments/pilot00_gvisor_offline`](../../experiments/pilot00_gvisor_offline/README.md).
On Linux x86_64 with Docker available to the current user:

```bash
PILOT00_RUN_ID=repro ./experiments/pilot00_gvisor_offline/probe.sh all
PILOT00_RUN_ID=repro ./experiments/pilot00_gvisor_offline/probe.sh cleanup
```

`prepare` is the network-using trusted phase. `run` is offline and produces
machine-readable results, launch inspection, logs and point-in-time resource
samples. `cleanup` removes only the labeled outer container and volume for its
run ID. Run IDs accept a lowercase letter or digit plus up to 30 lowercase
letters, digits or hyphens. Optional evidence IDs accept an ASCII letter or
digit plus up to 47 ASCII letters, digits or hyphens. The script validates each
before using it and refuses to mount, start or clean a container or volume
without its ownership label.

The final Linux replay used these identities:

| Component | Exact identity |
| --- | --- |
| Host | Ubuntu 24.04, Linux `6.8.0-142-generic`, x86_64, 4 CPUs, 16,377,068 kB memory |
| Docker | client/server `29.1.3`, `overlay2`, systemd cgroups |
| gVisor | `runsc release-20260928.0`, `systrap`; archive SHA-512 `4ce35ca83aef7f96b06cde668e0b23aa98b05aa1829508e974196c2a1e02786c95f5bf79315fd7ddcfd88fe7a00f083ed8053e25eff7673d28d5256440caae8b` |
| Trusted outer harness | `docker@sha256:173f284a4299164772a90f52b373e73e087583c0963f1334c9995f190ef6f3f5` |
| Builder | `ghcr.io/osscontainertools/kaniko@sha256:d6d74217dc077acfd3094992e917c357080a2d3fdd1042a49e34e29a7e57c572`; loaded image ID `sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3` |
| Base index | `alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc` |
| Base linux/amd64 manifest | `alpine@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e` |
| Sealed cache manifest | SHA-256 `0d7c48edceae685051d2f60497b0df7f55a0f3f8dd6d29c5e82b9c0cd75a40e1` |

The final replay evidence ID was `20261008T120000Z`. The result JSON SHA-256 was
`afc06f12ed50606372147a97824467ec448d28037ab8a5baa8dc26616b844c81`.
It recorded:

| Probe | Result | Elapsed time |
| --- | --- | ---: |
| Offline sample image build | Completed; 3,638,784-byte tar, SHA-256 `0e8a6f4236304340e5bd56c6d45457880c19f27b6bd7994b2b4bbed66797aa29` | 16.420 s |
| Separate oracle sandbox | Passed payload digest, gVisor marker, UID, capability, socket and network checks | 3.226 s |
| Intentional Dockerfile `exit 42` | Genuine work failure; no output image | 17.953 s |
| Empty offline base cache | Infrastructure candidate; registry unavailable with network disabled, exit 1 | 11.030 s |
| Five-second deadline followed by bounded stop | Infrastructure candidate; still running at deadline, exit 143 | 9.645 s including stop |
| 16 MiB builder limit | Infrastructure candidate; cgroup OOM, exit 137 | 3.206 s |
| 1 MiB output filesystem | Infrastructure candidate; `no space left on device`, exit 1 | 17.242 s |

The one-CPU build samples observed a 102.5% peak from Docker's interval
sampler, 27,283,948 bytes peak memory, 35 PIDs and `0B / 0B` network I/O. The
sealed base cache occupied 3,633,138 bytes and the downloaded/extracted gVisor
tools occupied 457,587,497 bytes. The cache was mounted read-only and its files
were rehashed after the failure probes. The measured numbers cover a tiny
Alpine fixture and cannot be extrapolated to a typical Terminal-Bench task.

Two identical-input successful builds in the retained replays produced tar SHA-256 values
`22538c93231e0cc76359de6c96ff19b3bebd47ff935d8f8abe317a160e038fc5`
and `0e8a6f4236304340e5bd56c6d45457880c19f27b6bd7994b2b4bbed66797aa29`
because Kaniko records creation timestamps. The trusted launcher can bind and
verify the exact output of each attempt, but this mechanism does not provide
byte-reproducible output across attempts. If PILOT-04 requires reproducible image
bytes rather than request-bound attempt identity, it needs a normalization or
different-builder decision before implementation.

## Mechanisms rejected by this host probe

The pinned `moby/buildkit:v0.26.2-rootless` entrypoint did execute in a gVisor
sandbox, but RootlessKit could not install its subordinate UID/GID mappings:

```text
[rootlesskit:parent] error: failed to setup UID/GID map:
newuidmap ... failed: fork/exec /usr/bin/newuidmap: operation not permitted
```

Adding gVisor's `--allow-suid` did not change that result. An ordinary `runc`
control also failed during RootlessKit user-namespace startup on this Ubuntu
host, so the evidence does not prove a BuildKit-specific or gVisor-only defect.
Rootful BuildKit could start its executor only after adding mount/ownership
capabilities that exceed the selected submitted-code boundary. Buildah was not
pursued after the maintained Kaniko path satisfied the bounded sample.

This result selects Kaniko for the pilot design; it is not a general claim that
rootless BuildKit can never work on another correctly configured Linux node.

## Failure classification input

PILOT-04 owns the final contract. The spike supplies these transport-neutral
classification candidates against the existing post-submission result family:

| Observation | Classification input |
| --- | --- |
| Contributor Dockerfile command exits 42 | Genuine checker/work result, not infrastructure |
| Oracle executes and reports a mismatch | Genuine checker/work result, not infrastructure |
| Digest-bound base absent from sealed cache | `material_unavailable` candidate |
| Attempt crosses its deadline | `deadline_exceeded` candidate |
| Memory, PID or disk quota stops execution | `capacity_exceeded` candidate |
| Registered runtime or builder cannot start | `implementation_unavailable` candidate |
| Launcher receives malformed or oversized checker output | `invalid_output` candidate |

No-op success, test instability and other checker conclusions also remain
member results. The spike does not define new persisted field names, lifecycle
states, acceptance behavior or retry policy.

## macOS and deployment limits

No macOS host was available, so no Docker Desktop runtime evidence was
executed. gVisor runs on Linux; ordinary Docker Desktop containers run in its
Linux VM but are not thereby `runsc` sandboxes. A local macOS fallback may use
the explicitly recorded `docker-dev` isolation mode required by PILOT-04, and
must never report it as gVisor or hosted-grade evidence. A custom Docker Desktop
VM/runtime registration path, Apple Silicon behavior and performance are all
unverified.

The probe also does not establish hosted execution-node hardening, multi-tenant
isolation, representative task sizing, cache distribution/eviction, retained
image availability, output normalization, concurrency, cleanup after host loss,
or a production launcher. Those remain PILOT-04/PILOT-06 work.

## Primary references

- [gVisor installation platforms](https://gvisor.dev/docs/user_guide/install/)
- [gVisor Docker runtime registration](https://gvisor.dev/docs/user_guide/quick_start/docker/)
- [gVisor networking modes](https://gvisor.dev/docs/user_guide/networking/)
- [gVisor rootless operation](https://gvisor.dev/docs/user_guide/rootless/)
- [gVisor production guidance](https://gvisor.dev/docs/user_guide/production/)
- [Docker inside gVisor](https://gvisor.dev/docs/tutorials/docker-in-gvisor/)
- [BuildKit rootless mode](https://github.com/moby/buildkit/blob/master/docs/rootless.md)
- [Maintained Kaniko fork](https://github.com/osscontainertools/kaniko)
