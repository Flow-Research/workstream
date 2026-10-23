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

## Smol lifecycle qualification

The opt-in [Smol experiment](../experiments/precheck_smol_lifecycle/README.md)
measures fresh microVM preparation overlapping ZIP upload and exact-owner cleanup.
It runs the existing project Python checker without changing this production
service, its supported runtimes or ART custody. The [live evidence](../experiments/precheck_smol_lifecycle/QUALIFICATION.md)
includes upload failures, checker timeout and request-process death; production
resource parity, external-model access and the typed upload-preparation integration
remain unimplemented.
