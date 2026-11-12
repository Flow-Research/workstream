# External checker boundary

The Rust workspace contains the shared execution service and optional Rust SDK.
Its crates do not implement project rules or restrict which projects and tasks
may use Workstream. The separate `harnessy_proof/` image supports the opt-in
[local agent-loop drill](../docs/engineering/local-agent-loop.md); it is outside
the Rust workspace and is not a required dependency or the checker for the
Terminal Systems guide.

## Project-owned images

Engineering implements a project's requirements in separately built checker
images. Keep each implementation in a project-owned source location with its
own build context, dependencies and tests. For example, a project repository
may contain `checkers/pre/` and `checkers/post/`. These are engineering source
paths, not arbitrary filesystem paths supplied to the Workstream runner.

An image may implement one or several checks. Approved policies bind the required
registered capabilities and exact image/configuration identities for each stage.
Projects may reuse an implementation where its declared contract matches their
requirements. A new project does not require a new crate here, a task-ID allowlist,
or a source change or rebuild of Workstream or this shared service. Operators
still provision the approved image cache and service configuration; the current
service reads that configuration at startup.

The image implementation language is independent of the runner language. An
implementation can use the Rust SDK or implement the same versioned JSON
request/result contract directly. It must be compatible with the supported
container platform and sandbox; the SDK does not grant additional privileges.

Use the generic [checker image command](../docs/engineering/checker-images.md)
to build a project-owned Dockerfile, test positive/negative samples, and optionally
publish the same image to private ECR. It produces a verified digest and inputs
for separate runner provisioning and Operator registration; it changes no policy.

## Shared responsibilities

- Workstream owns guide compilation, authorization, policy approvals, registry
  identity, immutable submission custody and lifecycle decisions.
- ART provides request-bound verified material. The service independently checks
  its grant and manifest before mounting the material read-only.
- The service executes the selected cached digest-pinned image under the
  configured sandbox, limits, deadline and output budget, then validates its
  normalized result and settles owned resources.
- The image evaluates the approved project requirements and returns bounded
  findings. It cannot approve a submission, mutate project policy, select another
  image, mount another project's files or request a private host-side continuation
  through its final output.

POST grants use one aggregate v2 workspace with fixed role roots and a separate
temporary manifest for each selected binding. Current work mounts at
`/work/input`. A registry-declared, policy-approved revision-context selection
may additionally expose the exact prior attempt at `/work/context/predecessor`
and bounded prior findings in `input.evaluation_context`. Neither a global
Submission version nor a project image request authorizes historical access.
Initial attempts carry explicit null prior context, including after another
contributor releases a task. PRE keeps its distinct pre-admission grant; there
is no POST fallback to the PRE protocol. See the
[POST contract](../docs/architecture_checker_framework.md#post-submit-contract)
for selection, evidence, quota and replay rules.

The service does not interpret project-private build plans. An image that needs
to compile or test submitted work may use the typed generic invocation-local
trial tool only when its exact POST binding and administrative profile authorize
that capability. The image supplies bounded generic operations, safe relative
selectors and workload argument arrays through `/work/execution.sock`; it never
selects Docker flags, host paths, mounts, runtime, images, network, devices,
credentials or resource enlargements. Opaque profile material roles control
build and runtime visibility. Shared Rust contains no project filenames, task
allowlists, rubrics or command allowlists.

A visible read-only role occupies one profile-selected top-level workspace
name. Nested overlay destinations and existing-entry collisions are refused;
the launcher removes its temporary mountpoint before retaining workspace
state. Build-context and state-seed selectors may still use safe nested paths.

The service keeps Smol launch authority, approved offline material, protected
role projection, aggregate limits, observation and cleanup custody. Workload
argv is passed to the trusted guest launcher as bounded workload arguments; it
is never interpreted as host launcher flags. Trial observations become usable
only after required operations and cleanup complete. A dependent model call
resolves server-owned same-invocation receipt facts instead of trusting JSON
copied by the checker. Unsupported runtime or material remains an explicit gap;
it is not permission to expose the host Docker socket or add a named-project
service branch.

Candidate images are checked before Smol loads them: ordered uncompressed
layer digests must match the image configuration, and streaming expansion plus
conservative file/directory allocation must fit the invocation's remaining
byte and entry allowances. Repeated layers consume that allowance again.
Malformed archives and unsupported sparse/device representations are refused.
Smol does not create anonymous storage from image `Volumes` metadata; the
trusted launcher owns writable mounts and their quotas. These are runtime
capability limits, not additional project requirements. Project checks must report unavailable execution distinctly
from a verified work failure.

Every completed build or step records `export_outcome` separately from the
child's exit code or signal. `exported` means the bounded candidate or workspace
was retained; `capacity_exceeded` means its logical bytes or entries exceed the
allowance; `invalid` means it cannot be represented by the supported export
format. The latter two produce `disk_exceeded` or `export_invalid` observations
while preserving the actual child status. A forced runtime stop records
`unavailable` and does not invent an exit code or signal. `not_started` covers
dependency-skipped steps and failed builds that never request candidate export.
Only an exported workspace whose work outcome the profile permits may feed a
later step. Host storage or export I/O failures remain infrastructure failures;
they are not evidence that submitted work exceeded its allowance. Project
images interpret these execution facts against their own approved requirements.

## Optional model socket

An entitled post-submit invocation may receive one invocation-local Unix socket
at `/work/model.sock`. The image opens one connection and sends sequential
closed `workstream.model_session.v2` call objects as UTF-8 JSON, each prefixed
by a four-byte unsigned big-endian body length. A call supplies its exact
zero-based `call_index`, a non-empty `prompt` and a bounded unique
`required_receipt_handles` array. Each frame is at most 1 MiB. The reply echoes
the call index and is one closed session result object:

- A completed result has `outcome: "completed"`, a non-empty string `output`, a
  lowercase `sha256:` `receipt_digest` and a null `failure_code`.
- An unavailable result has `outcome: "unavailable"`, null `output` and
  `receipt_digest`, and a bounded lowercase-identifier `failure_code`.

Both results also contain the exact `protocol_version` and `session_exhausted`;
extra or missing fields are invalid. The locked model profile bounds calls,
prompt/response bytes, tokens, trusted receipt count/bytes, deadline and the
whole session budget. Receipt handles resolve only inside the current invocation;
the relay injects their ART-verified canonical bytes before spend and hashes
those retained facts rather than the transient handles. This image-facing
protocol is project-agnostic. The image needs no
Workstream project code, provider SDK, provider credential, model coordinate or
access to the global proxy endpoint. The service wraps the prompt with the
invocation's private grant and request digest. Setup and POST sessions share one
project-lifetime metered account while retaining distinct typed setup-attempt and
checker-invocation lineage. The checker container remains on `--network none`.

The dedicated singleton model-proxy worker is optional for provider-free
deployments. Add `model-proxy` to the existing backend and agent-loop Compose
profiles to enable model-backed setup or POST checks. That profile
sets
`WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET=/run/ws-model-proxy/model-proxy.sock` and
binds the listener. The setup task worker connects through a read-only mount of
that socket but never owns it or receives provider credentials; the ordinary API
and Beat processes do not mount it. An empty value outside the model-proxy and
authorized setup-worker processes leaves the listener disabled. The Rust service configuration must set both
`model_proxy_socket` to that same mounted path and `model_relay_root` to a
daemon-visible private relay directory. The local configuration generator's
`--enable-model-proxy` switch emits that pair, using
`/var/lib/docker/volumes/<compose-project>-checker-relay/_data` for the relay
root. Enabling only one side does not activate model calls.

The proxy and relay roots must be canonical mode-`0700` directories owned by the
shared service UID and GID. The global proxy socket and each invocation socket
are mode `0600`. The singleton model-proxy worker has read-write access to the
proxy volume, the Rust service connects through its read-only volume mount and
creates invocation sockets in the relay volume, and a checker receives only its
individual socket file. A different service/sandbox identity is rejected
because this path does not rely on privileged ownership changes.

Docker development proves only the ordinary runtime path. A gVisor `runsc`
deployment must separately enable `host-uds=open` before a mounted host Unix
socket can work. This repository does not claim that the model relay has been
qualified under gVisor at the current source; historical runsc composition
evidence applies only to its recorded implementation.

Smol exposes guest-local model and execution sockets through its trusted guest
stream. The host forwards only the capabilities granted to that invocation to
the existing relays. A persistent model connection can remain open while an
execution request runs. Each execution session carries one request and response,
then closes with exact EOF. The transport uses a fresh execution-relay connection
for each request and reaps completed handlers, retaining at most one handler per
channel. The current trial relay authorizes one plan and one execution connection
per checker invocation; transport support for sequential sessions does not grant
additional trials. Workload stdout never carries control frames. No host
socket or provider credential is mounted into the microVM. Trials use fresh
Smol sibling VMs and have no Docker/runsc fallback. Controlled KVM composition
013 passed on native build `b2ce3fa45`: trusted intake, two trials of 17 steps, four controlled
model effects, verified PostgreSQL/MinIO ART receipts, replay without new model
calls and confirmed VM/cgroup cleanup. Builder and candidate-step execution
verified the shared syscall filter. The [qualification record](../.commitrail/changes/terminal-systems-project-checkers.md#repaired-confinement-and-resource-qualification-on-real-kvm)
binds the exact source, artifacts and 2 GiB aggregate disk profile. This initial
submission composition does not exercise predecessor material; direct proof 36
separately covers predecessor transport/custody and guest resource ceilings.
Active nested caller cancellation, exact child VMM death and controller death/restart
passed in physical cases 026–028 at proof source `8012f2792`, using the same native
build: no false completion or trial ART effects, full owned cleanup, and both
admission slots reusable. See the [interruption evidence](../.commitrail/changes/terminal-systems-project-checkers.md#active-nested-interruption-qualification-on-real-kvm).
Hosted Smol composition and its scoped AWS proof are tracked separately in
[PR #692](https://github.com/Flow-Research/workstream/pull/692); that owned baseline
does not establish live-model grading or the full Terminal Systems
guide-to-contribution journey.

The [hosted composition](../deploy/hosted/README.md) uses that same native node
for typed intake and project execution, with credentials confined to the trusted
proxy. Its configuration/readiness checks do not establish a live model call or
public lifecycle qualification. PRE model selectors remain unsupported; only
existing approved POST model lineage can issue that grant.

The opt-in
[`model_relay_docker.py`](workstream-checker-service/tests/model_relay_docker.py)
probe drives a real Docker-development checker from its invocation-local socket,
through the Rust relay, to a fake private global proxy. It records the created
checker before cleanup and verifies `--network none`, a read-only root filesystem,
read-only material and socket mounts, the closed proxy request and exact reply,
and removal of the checker and invocation directory. It uses only already-local
`alpine:3.20` and `registry:2` images, creates a small disposable checker layer,
and makes no provider call:

```console
CARGO_TARGET_DIR=/dev/shm/workstream-checker-target \
  cargo build --locked -p workstream-checker-service
TMPDIR=/absolute/daemon-visible/private-directory python3 \
  workstream-checker-service/tests/model_relay_docker.py \
  --service /dev/shm/workstream-checker-target/debug/workstream-checker-service
```

Run those commands from `external_checkers/`. Set `TMPDIR` to a private directory
that resolves to the same files in both the command process and the Docker daemon;
a service-private `/tmp` or `/dev/shm` may not be shared. The probe never pulls images,
scans Docker state for cleanup, or qualifies the gVisor path. Its fake reply is
transport evidence only; it does not prove provider execution, budget settlement,
or a completed product model-evaluation journey.

## From guide to an active project

Use the real guide and task examples as setup input. Inspect the resulting
requirements and capability gaps, implement missing checks, and register exact
images through the supported Operator API. Then recompile or correct the
proposal, obtain the separate policy approvals and activate the guide. Image
registration alone neither changes an existing approved policy nor activates a
project. Task import, screening and release follow the governed task flow.

See the [checker architecture](../docs/architecture_checker_framework.md) for
the canonical execution and lifecycle contract, and the
[Terminal Systems onboarding inputs](../pilots/terminal_systems/README.md) for
the current real-project preparation. Ordinary platform regression tests protect
this execution boundary; their passing results do not establish a live project
journey or the correctness of a project's checker images.

## Container recovery ownership

The service creates `.workstream-checker-owner` (mode `0600`) inside its locked
private socket directory. Preserve this file and directory across restarts.
Different deployments must use separate directories; never clone an owner file
into another concurrently running deployment. Containers are labelled and named
with that owner, and recovery verifies the exact Docker ID and attempt before
deletion. Docker administrators remain trusted infrastructure.

Malformed, linked, partial or unsafe owner files reject startup before container
cleanup. If custody is lost, stop the deployment and reconcile its orphaned
containers by independently verified exact IDs. Startup never adopts unowned
generic containers. Before installing this repair, drain the prior service and
settle its containers with the prior deployment; it cannot prove ownership of
containers that lack the new owner label. Do not remove unrelated containers,
product artifacts or immutable evidence.

The opt-in `workstream-checker-service/tests/container_ownership.py` proof uses
a built service and an already local image, two private socket directories and
disposable containers. It checks foreign-container survival and restart recovery;
it is not a hosted deployment or sandbox-security certification.

## Retiring the fixed-project profile

The former sample-specific build continuation is removed, including its private
configuration and SDK plan type. Before upgrading any environment that used it,
stop admission to that profile, drain or reconcile its owned in-flight work and
confirm cleanup using the existing deployment. Remove that profile from service
configuration before starting this version; unknown configuration is rejected.

Retain registry entries, locked policies, submissions and historical evidence.
Do not rewrite them to point at replacement images. Any replacement needs the
normal versioned registration, proposal and approval process. A retained image
that returns `project_private_plan.v1` or another private plan as its outer
output still produces an invalid-output infrastructure failure, not a
continuation or a contributor-work failure. The typed invocation tool does not
parse an outer result to start host work. Do not blindly retry a retired plan as
if that capability still exists.

## Smol microVM engine

The hosted node uses the deployment pair `smolvm` / `smol-microvm`. Python still
uses the single `external_checker_execution/unix_socket` provider; neither a
project policy nor a checker request can choose the engine. The trusted guest
receives typed current and optional predecessor material roots and the authorized
callback capabilities. Each execution gets
a fresh VM and the same verified ART grant and JSON result contract. The native
bootstrap has no Python or shell dependency in a project image.

Use Linux x86-64 with `/dev/kvm`, cgroup v2 and Smol 1.31.4. The
[systemd unit](deploy/workstream-checker.service) delegates cpu/memory/pids and
places the controller in its own subgroup; `DelegateSubgroup` requires systemd
254 or later ([systemd documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#DelegateSubgroup=)).
Set `smol.cgroup_root` to that unit's delegated root, not the controller subgroup.
The service refuses startup outside its delegation. Use the ART grant issuer's numeric UID/GID (`10001:10001` in the hosted unit)
and a separate private socket directory, Smol HOME and image cache for each node. The sample unit's CPU, memory and task ceilings are deployment
capacity; individual registered checker limits remain unchanged. Hosted releases
may select one canonical private deployment root and a digest-pinned native
binary path; the same derived absolute scratch/socket paths must appear in the
node JSON and API/worker mounts. See the
[hosted operator sequence](../deploy/hosted/README.md#start-and-inspect) for
migration/activation/proxy prerequisites and native readiness.

Keep the canonical Smol HOME path at most 59 filesystem bytes. Trial-enabled
nodes also need a separately owned `trial_runtime.child_home_root` at most 18
bytes (for example, an operator-created private `/var/lib/wschild`). Smol appends
its VM directory and socket names; each child additionally receives its full
random private HOME name. Startup rejects longer paths before accepting work.
These bounds count encoded bytes, not characters. Do not use symlink aliases or
shorten invocation identities to fit the Linux Unix-socket limit.

For this engine omit `docker_binary`, and configure `smol` with absolute `binary`,
`home`, `guest_binary`, `cgroup_root` paths; `binary_sha256` and `guest_sha256`;
and required positive `maximum_parallel` and `maximum_storage_bytes`. Install the verified Smol release bundle together and
keep it operator-controlled. Build `workstream-checker-guest` for
`x86_64-unknown-linux-musl`; the node and bootstrap must come from the same source.
Each existing cache entry additionally has `smol.archive`,
`smol.archive_sha256` and `smol.image_config`. The
[cache preparation command](../backend/scripts/checker_smol_cache.py) verifies an already local
Docker-save archive against its approved platform manifest, config and rootfs identities.
It writes a distinct canonical USTAR archive containing only the closed Docker-save
manifest and exact approved platform/config and selected/approved layer bytes. Nullable
source tags, layer-source hints and unrelated compatibility metadata confer no authority
and are omitted. The source archive and its permissions remain unchanged; the new archive
has its own hash while the approved platform/config/layer identities stay the same.

Run from `backend/` with two new, distinct output paths:

```sh
uv run python -m scripts.checker_smol_cache \
  --archive /absolute/source/image.tar --repository registry.example/checker \
  --manifest sha256:<approved-platform-manifest> \
  --archive-output /absolute/cache/image.tar --config-output /absolute/cache/config.json
```

The command bounds raw headers, paths and metadata before parsing, rejects aliases,
links, unsupported tar extensions and conflicting ancestry, and rehashes graph bytes
while copying. Outputs are created exclusively and sealed read-only; failure removes
only partial files still matching this invocation's created inodes. It shares platform
validation with the image publisher and verifies each layer's uncompressed identity.
It emits cache configuration; it neither registers the image nor activates a policy.
Runtime execution needs no Docker daemon, registry credentials or image pull. Smol
retains private hard links to imported archives; link count alone is not an integrity check.

The node reserves aggregate memory, disk and concurrent slots before launch.
A trial invocation reserves the outer checker plus one sequential child VM
atomically, before either VM launch or model spend. A one-slot node rejects such
an invocation instead of waiting for capacity while holding its only slot. A guest
supervisor applies the exact requested CPU and memory controls, a bounded PID
limit, non-root IDs, no capabilities, read-only root/material, a 16 MiB `/tmp`,
and denied management syscalls and network access. Image-owned `/work` and `/tmp`
links or non-directory mount roots are rejected before the image command runs.
Submitted material is staged
on bounded VM disk, separate from checker heap. The host bounds VMM resources
and charges virtualization overhead separately. Results are returned only after
VM and cgroup removal is confirmed. Unknown cleanup closes admission and requires
startup reconciliation. Failures before lease creation or after confirmed cleanup
return recoverable infrastructure failure without stopping other checks.
The private trial stream carries the export header, export bytes, retained stdout,
retained stderr and final receipt in that order. Each output length and digest is
bound by both header and final receipt; successful exit and exact EOF are required.
The combined raw output ceiling is the approved profile's bound, at most 4 MiB;
JSON control frames remain at most 1 MiB. Output capture and transmission stay in
the finite guest operation envelope. Observations retain exact UTF-8 text and its
hash. When an enforced output cut splits a trailing UTF-8 scalar, only that
incomplete suffix (at most three bytes) is trimmed, without changing the
`output_exceeded` outcome. Intrinsically invalid UTF-8 is an explicit unsupported
text-protocol failure; it is never replaced, silently discarded or rehashed as
empty output.
Independent lease guardians survive controller death;
`KillMode=process` preserves that cleanup lifetime. Preserve the private owner
file and lease directory across restarts. Never clone them between running nodes.

The opt-in [runtime matrix](workstream-checker-service/tests/smol_runtime.py)
uses synthetic grants and separately built Python/native fixture images. It
covers the node contract; it is not public upload, admission, durable POST or
FinalAcceptance evidence. The [recovery proof](workstream-checker-service/tests/smol_recovery.py)
requires an isolated test unit: it kills the controller and injects a deletion
failure while checking foreign VM/cgroup survival, bounded cleanup and closed
readiness. The [creation proof](workstream-checker-service/tests/smol_creation.py)
checks that denied lease or cgroup creation preserves an already running check
and keeps the controller available after confirmed cleanup. Never run either
proof against a shared production node.
The [guest mount proof](workstream-checker-service/tests/smol_guest_mounts.py)
uses a clean image and two variants built from the
[test Dockerfile](workstream-checker-service/tests/fixtures/mount-targets/Dockerfile)
with `MOUNT_ROOT=work` and `MOUNT_ROOT=tmp`. It checks a command marker and the
bootstrap rejection reason, so an error after image code ran cannot pass. Run
it only with an isolated runtime home; exact test machines and disks are removed.

## Trusted submission intake

ART uses the separate typed `trusted_submission_intake/unix_socket` capability.
After task/project authorization, the upload request receives, hashes and seals
the ZIP before allocating its size-bound trusted VM. Preparation binds the exact
server-counted length; inspection rejects a substituted length before accepting
archive bytes. The sealed artifact reader streams the exact bytes into that VM
for canonical inspection and extraction. ART verifies every exported path,
size, mode and hash in quota-owned scratch. The default PRE checker runs inside
the trusted VM only after the selected PRE reservation commits. Cleanup must be
acknowledged before project checker execution, including on a one-slot node.
POST uses the same intake capability during authorized artifact download and
retains its existing lease and material revalidation.

Build `intake/Dockerfile` from the repository root, pin its platform manifest and
config, and provision it with the same cache command. Configure the node's
`trusted_intake` object with `platform_manifest_digest`, `storage_envelope` and
`default_behavior_sha256` (the canonical `WORKSTREAM_DEFAULT_BEHAVIOR_SHA256` from
`app.modules.checkers.api.default_checker`). The node selects this image; project
registrations cannot select the trusted intake mode. The trusted guest uses
1 CPU and 2 GiB memory. Its data disk is the whole-GiB ceiling of sealed ZIP
bytes, permitted expansion (`min(expanded limit, ZIP bytes * ratio limit)`) and
qualified image/filesystem overhead. A separate one-GiB root overlay is enforced
and charged. Aggregate node capacity also includes virtualization overhead.
The required closed `storage_envelope` binds archive/config and Smol/guest hashes,
qualified entry/path/depth ceilings, overhead bytes and maximum data-disk GiB.
Requests outside that qualification fail before allocation. Establish its bounds
with cold startup, maximum accepted inventory/expansion and cleanup on the exact
runtime; there is no production default overhead. Its private writable scratch
is bounded processing space, never artifact storage.
Workstream sets `SMOLVM_IMAGE_SEEDS=0` in the native command environment so one
lease cannot spawn an unaccounted automatic image-seed VM. The pinned image
archive cache remains available; existing seed data is not deleted. Qualification
and latency measurements must use this same enforced cold-start behavior.

Backend API and durable workers require all three settings:

- `WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET`: private absolute Unix socket path.
- `WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST`: exact trusted platform manifest digest.
- `WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST`: exact image config digest.

The configured socket must serve Smol with the expected trusted image and default
behavior. The hosted release uses the same native node socket for this typed capability
and project execution; the protocols and privileged intake image remain separate.
Missing or mismatched configuration fails closed. Local Docker-only mechanism
configurations still cannot supply Smol intake readiness.

The original artifact deadline bounds upload and intake preparation together.
Only known pre-launch infrastructure failures permit at most three preparation
attempts, after confirmed cleanup, with 100/200 ms backoff inside that deadline.
No retry occurs after archive bytes are accepted. Upload failure, cancellation,
EOF or expiry closes the lease; capacity remains reserved until guardian cleanup.
A lost cleanup acknowledgment is an infrastructure failure, never evidence that
resources were released. Used VMs are destroyed; only capacity is reused.

The opt-in [intake proof](workstream-checker-service/tests/trusted_intake.py) uses
backend dependencies and an isolated `maximum_parallel=1` node. It exercises
retained ART inspection/export/grant custody, poisons host ZIP/default execution,
and checks cancellation, abandoned uploads and idle expiry. Run with

```bash
PYTHONPATH=backend python external_checkers/workstream-checker-service/tests/trusted_intake.py \
  --socket /absolute/node.sock --image sha256:... --config sha256:...
```

This matrix proves the adapter/ART boundary. The separate
[public lifecycle drill](../experiments/pilot04_external_checker_runtime/README.md)
connects the same node to API uploads and durable workers, including the public
Operator retry and both governed policy branches. Its recorded Flow/inference
fixtures do not certify production identity, live models or hosted deployment.

### Trusted root provisioning for single-session PRE development

`backend/scripts/checker_trusted_root.py` provisions a separate pinned Python
root for the single-session PRE supervisor under development. This command and
the guest bundle reader do not yet replace the current submission PRE flow or
establish native runtime qualification.

The command first verifies the approved local image graph with the existing Smol
cache provisioner. A trusted offline Docker daemon must already contain that
exact config image ID. It checks the platform and ordered layer identities,
creates a container with pulling disabled, verifies its exact image and created
state, exports without starting it, and removes the owned container. Images with
volumes are refused. The daemon is build infrastructure; it is not used for PRE
execution, and no submission bytes enter this provisioning path.

Run the module from `backend/` with `--archive`, `--repository`, `--manifest`,
`--archive-output` and `--config-output` as for the cache command. Also supply
new `--bundle-output` and `--descriptor-output` paths, `--docker`,
`--default-behavior-sha256`, `--maximum-export-bytes`, `--maximum-root-bytes`,
`--maximum-entries`, and `--timeout-seconds`. All bounds and identities are
explicit; the command does not choose deployment values. Keep the emitted
bundle and descriptor operator-controlled and pin their identities independently
before use. Completed cache files may remain if later bundle provisioning fails;
a partial bundle/descriptor never establishes readiness.

The `WSROOT1` format carries bounded closed JSON records and inline regular-file
bytes. Hard links become independently charged file content; symlinks are
installed last. No image paths are extracted on the host. The guest library
verifies the entire bounded spool and descriptor, stages into a fresh private
root, and rechecks consumed bytes before returning. The caller must provide a
protected parent, aggregate deadline/cancellation checks, and capacity for both
the spool and expanded root, then mount the root read-only before executing a
trusted child. Combined supervisor wiring and native isolation proof remain
required; this library alone does not authorize project execution.
