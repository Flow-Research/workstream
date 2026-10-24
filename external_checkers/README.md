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
  image, mount another project's files or request a private host-side continuation.

The service does not interpret project-private build plans. An image that needs
to compile or test submitted work must implement that behavior within the
supported isolation and resource contract. Unsupported runtime needs must be
resolved explicitly before approving that capability; they are not permission
to add a named-project exception or expose the host Docker socket.

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
that returns a private plan now produces an invalid-output infrastructure failure,
not a continuation or a contributor-work failure. Do not blindly retry it as if
the capability still exists.

## Smol microVM engine

The node also accepts the deployment pair `smolvm` / `smol-microvm`. Python still
uses the single `external_checker_execution/unix_socket` provider; neither a
project policy nor a checker request can choose the engine. Each execution gets
a fresh VM and the same verified ART grant and JSON result contract. The native
bootstrap has no Python or shell dependency in a project image.

Use Linux x86-64 with `/dev/kvm`, cgroup v2 and Smol 1.31.4. The
[systemd unit](deploy/workstream-checker.service) delegates cpu/memory/pids and
places the controller in its own subgroup; `DelegateSubgroup` requires systemd
254 or later ([systemd documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#DelegateSubgroup=)).
Set `smol.cgroup_root` to that unit's delegated root, not the controller subgroup.
The service refuses startup outside its delegation. Use the ART grant issuer's
Unix identity and a separate private socket directory, Smol HOME and image cache
for each node. The sample unit's CPU, memory and task ceilings are deployment
capacity; individual registered checker limits remain unchanged.

For this engine omit `docker_binary`, and configure `smol` with absolute `binary`,
`home`, `guest_binary`, `cgroup_root` paths; `binary_sha256` and `guest_sha256`;
and `maximum_parallel`. Install the verified Smol release bundle together and
keep it operator-controlled. Build `workstream-checker-guest` for
`x86_64-unknown-linux-musl`; the node and bootstrap must come from the same source.
Each existing cache entry additionally has `smol.archive`,
`smol.archive_sha256` and `smol.image_config`. The
[cache preparation command](../backend/scripts/checker_smol_cache.py) checks an already local
Docker-save archive against its platform manifest, config and rootfs identities.
Run it from `backend/` with `uv run python -m scripts.checker_smol_cache`.
It shares platform-manifest validation with the image publisher and verifies
every declared layer blob and its uncompressed identity. It emits cache configuration; it neither registers the image nor activates a
policy. Runtime execution needs no Docker daemon, registry credentials or image
pull. Smol retains private hard links to imported archives; link count alone is
not an image-integrity check.

The node reserves aggregate memory and concurrent slots before launch. A guest
supervisor applies the exact requested CPU and memory controls, a bounded PID
limit, non-root IDs, no capabilities, read-only root/material, a 16 MiB `/tmp`,
and denied management syscalls and network access. Submitted material is staged
on bounded VM disk, separate from checker heap. The host bounds VMM resources
and charges virtualization overhead separately. Results are returned only after
VM and cgroup removal is confirmed. Unknown cleanup closes admission and requires
startup reconciliation. Independent lease guardians survive controller death;
`KillMode=process` preserves that cleanup lifetime. Preserve the private owner
file and lease directory across restarts. Never clone them between running nodes.

The opt-in [runtime matrix](workstream-checker-service/tests/smol_runtime.py)
uses synthetic grants and separately built Python/native fixture images. It
covers the node contract; it is not public upload, admission, durable POST or
FinalAcceptance evidence. The [recovery proof](workstream-checker-service/tests/smol_recovery.py)
requires an isolated test unit: it kills the controller and injects a deletion
failure while checking foreign VM/cgroup survival, bounded cleanup and closed
readiness. Never run it against a shared production node.
## Trusted submission intake

ART uses the separate typed `trusted_submission_intake/unix_socket` capability.
After task/project authorization, the upload request starts one trusted VM while
receiving the ZIP. The sealed artifact reader streams the exact bytes into that
VM for canonical inspection and extraction. ART verifies every exported path,
size, mode and hash in quota-owned scratch. The default PRE checker runs inside
the trusted VM only after the selected PRE reservation commits. Cleanup must be
acknowledged before project checker execution, including on a one-slot node.
POST uses the same intake capability during authorized artifact download and
retains its existing lease and material revalidation.

Build `intake/Dockerfile` from the repository root, pin its platform manifest and
config, and provision it with the same cache command. Configure the node's
`trusted_intake` object with `platform_manifest_digest` and
`default_behavior_sha256` (the canonical `WORKSTREAM_DEFAULT_BEHAVIOR_SHA256` from
`app.modules.checkers.api.default_checker`). The node selects this image; project
registrations cannot select the trusted intake mode. The trusted guest uses
1 CPU, 2 GiB memory and 3 GiB private disk; aggregate node capacity must include
virtualization overhead. Its private writable scratch is bounded processing
space, never artifact storage.

Backend API and durable workers require all three settings:

- `WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET`: private absolute Unix socket path.
- `WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST`: exact trusted platform manifest digest.
- `WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST`: exact image config digest.

The configured socket must serve Smol with the expected trusted image and default
behavior. A Docker/runsc project node can remain separate, but cannot satisfy ART
intake readiness. Missing or mismatched configuration fails closed; there is no
host ZIP/default fallback. Existing Docker-only deployment compositions therefore
need a separately provisioned Smol intake node before accepting uploads or POST.

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
