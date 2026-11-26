# Hosted Release Configuration

This directory prepares the Workstream API, durable Celery worker, Beat,
fixed guide-document parser and optional trusted model proxy on one dedicated
Linux amd64 host. The single-host profile uses the native Smol systemd node for
project PRE/POST and trusted ZIP intake. Compose does not start a checker
controller or grant access to its Docker socket. PostgreSQL and Redis are
required. Use the [private backing-service overlay](SINGLE_HOST.md) or managed
services.
AWS S3, Flow identity and the optional OTLP collector retain their separate
configuration and trust boundaries.

The checked-in [release environment template](release.env.example),
[Compose wrapper](compose.py), [preflight](preflight.py), native node and
[canonical Settings](../../backend/app/core/config.py) define the source
topology. An operator must still build and publish exact images, provision the
host and external services, configure private assets and credentials, run the
real S3 storage qualification, and verify the public journey for that deployment. A render,
image build or preflight alone does not establish hosted operation or a real
model call. The [capability ledger](../../docs/roadmap_status.md) and
[hosted drill report](https://github.com/Flow-Research/workstream/blob/d713594ebf04a125917edb0ec981d380cf8047b4/docs/reports/garden-hosted-drill-2026-11-06.md)
record what has actually been exercised; neither makes this directory an
automatic installer or qualifies another host.

## App host without KVM

Set `WORKSTREAM_HOSTED_PROFILE=app` and pin a backend image built from a release
that includes this profile. Remove `WORKSTREAM_CHECKER_CONFIG_FILE`,
`WORKSTREAM_CHECKER_SERVICE_BINARY`, `WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256`,
both `WORKSTREAM_ARTIFACT_INTAKE_*_DIGEST` values, and any trial-authority
selectors from the release environment. Use the normal hosted preflight,
migration and `compose.py ... resume` commands. The app profile
requires the same database, broker, identity, parser, and provider setup as the
single-host profile. It starts the configured setup model proxy before the
ordinary worker. API and worker use local ART scratch for their other work.

While this profile is active, the API returns a retryable HTTP 503 for ZIP
preparation. MCP reports the upstream error as a retryable tool failure. POST
evaluation requests and reconciliation remain in PostgreSQL until checker
delivery is available. Artifact verification, guide
compilation, and ordinary OUTBOX delivery, including completed evaluation
delivery, continue. The `single-host` profile, or an unset profile, keeps the
native Smol readiness checks and processes all delivery types. Private ingress
and worker attachment for a second checker host require separate qualification.

## Trust boundary

In the single-host profile, the native node uses KVM and its delegated
cpu/memory/pids cgroup under the same numeric UID/GID `10001:10001` as the
ART grant issuer. It owns fresh VM execution,
exact leases and cleanup. Neither the node nor project images receive provider
credentials. The optional Compose model proxy alone owns those credentials;
the native node connects to its host-visible private socket and forwards only
invocation-bound capability traffic through the Smol guest transport.

In that profile, the API and worker mount the node socket directory read-only.
Both typed capabilities use the same host endpoint with distinct closed
protocols and pinned images:

```text
/var/lib/workstream/scratch
/var/lib/workstream/checker-runtime/checker.sock
/var/lib/workstream/model-runtime/model.sock
```

`WORKSTREAM_DEPLOYMENT_ROOT` defaults to `/var/lib/workstream`. An independently
owned deployment may select one canonical absolute private root; all scratch,
checker/model/parser socket paths below it are derived together, with identical
absolute source/target paths in the containers. The root must be mode `0700`,
owned by `10001:10001`, and contain no config, provider secret or executable/cache
asset. Symlink roots, ancestor aliases and data/asset overlap fail preflight.
`WORKSTREAM_CHECKER_SERVICE_BINARY` defaults to the unit's installed path and
selects one absolute artifact under `WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256`.

For an isolated proof, use a newly owned `/var/tmp/workstream-hosted-smol-*`
prefix with a private `data` subdirectory and config/assets as separate siblings.
Give UID `10001` traversal access to the owned prefix; do not rely on another
user's private home ancestry. Configure the existing scoped unit's `ExecStart`
and cgroup path for that exact binary/config and preserve its ownership. This
uses the same release topology and preflight, without shared `/etc/workstream`
or `/var/lib/workstream` mutation. No source here deploys or restarts that unit.

These absolute paths and identities must match across native configuration,
API/worker containers and the proxy. ART material lives under the same scratch
root on host and clients; the native node independently verifies each opaque
ART grant before staging. Model proxy sockets and ART material are never assumed
to exist only inside a Docker namespace. Project guests receive guest-local
capability sockets, never the global host socket or a provider key.

Ordered non-model PRE and approved model-enabled POST retain their existing
owners. PRE model selectors remain unsupported: PRE has no supported paid-model
lineage/grant operation, and policy validation rejects those selectors. This
configuration does not introduce PRE model authority.

The [hosted qualification record](../../.commitrail/changes/hosted-smol-project-execution.md#live-hosted-model-continuation)
records the actual API/Celery/AWS baseline and one live OpenRouter POST through
this wiring. The model continuation preserves its original paid effect, reaches
governed acceptance and proves replay without another charge. It uses fixture
identity and a synthetic single-rubric submission; production identity and full
project grading remain separate qualifications.

Guide parsing uses a separate private Unix socket at
`/var/lib/workstream/guide-runtime/guide.sock`. The parser uses the immutable
backend image without network or secrets. Its bootstrap starts as root with only
`KILL`, `SETGID` and `SETUID`, then drops the broker to UID 10002 and GID 10001
before binding the socket. The broker retains those three capabilities only to
isolate and terminate parser children. Each of its two concurrent children uses
a distinct fixed identity (10003 or 10004), no supplementary groups and no
capabilities. The broker and children verify their process protections before
processing documents; startup fails if the required identity boundary is absent.
The broker owns the socket directory and socket. Only the guide worker mounts that directory as
a read-only client. API, Beat and the native node do not
receive it. The parser process validates directory and socket ownership before
binding. The health check drops to client UID/GID 10001 with no capabilities before
performing a framed protocol round trip against the fixed parser build identity.
Keep the configured capability allowlist, no-new-privileges, read-only root,
network isolation and process limits together; do not replace this profile with
a privileged container.

## Prepare source images

Builds are separate from release execution. Build the reviewed source, publish
each image to the approved registry, record its repository digest, then put only
the resulting `repository@sha256:...` identity in the release environment.
Compose never builds and rejects tags.

```sh
docker build --build-arg WORKSTREAM_PROJECT_AGENT_SDK_ENVIRONMENT=agents \
  --file docker/backend/Dockerfile.release \
  --tag registry.example/workstream/backend-agents:<source-commit> .
docker build --build-arg WORKSTREAM_PROJECT_AGENT_SDK_ENVIRONMENT=omnicore \
  --file docker/backend/Dockerfile.release \
  --tag registry.example/workstream/backend-omnicore:<source-commit> .
```

Backend and intake image definitions pin their base images. Each backend build requires one exact SDK
environment and installs only its committed `agents` or `omnicore` resolution,
without the development extra. The image records that choice in a root-owned
read-only marker. Select the worker image that matches the configured setup SDK.
For every model-proxy-enabled release, also publish the `agents` build separately as
`WORKSTREAM_MODEL_PROXY_IMAGE`: the dedicated trusted proxy uses its pinned
OpenAI 3.x input-count and Responses dependencies for both setup SDKs and POST
checkers. The proxy rejects any non-`agents` image before reading the provider
credential. `manager_authored` is accepted in either worker image with the exact
`none/none/none` setup tuple; `WORKSTREAM_MODEL_PROXY_ENABLED` independently
decides whether approved POST images can use the proxy. Build the native service and static guest from the same reviewed source using the
[node instructions](../../external_checkers/README.md#smol-microvm-engine). Record the
installed service digest in `WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256`; the
private node config pins Smol, the guest and every cached archive/config. A local build tag is build evidence only; the release file must
contain the registry-resolved digest after publication. The backend build's uv
package-download cache mount exists only on the builder; it is not retained in
the image. Runtime image inspection uses `uv --no-cache pip check` and bounded
temporary storage.

For native hosted backend-image proof, use the existing verifier with the
explicit `native-hosted` scope from a clean checkout of the exact source:

```sh
python3 scripts/verify_hosted_release_images.py --scope native-hosted \
  --expected-head <source-commit> --container-owner <numeric-run>-<attempt> \
  --backend-agents-image <agents-image> \
  --backend-omnicore-image <omnicore-image> \
  --evidence /private/backend-image-evidence.json
```

This scope proves both backend SDK images without requiring a checker controller
OCI image. It rejects `--checker-image` and records a closed backend-only
evidence shape. Installed native service, Smol, guest and cache identities remain
the full preflight's responsibility. Backend-image proof establishes no native
readiness or hosted journey result.

The [release-image workflow](../../.github/workflows/release-images.yml)
runs for release definitions and copied backend/checker source changes, building
the exact PR head without cache, publication or deployment credentials.
It first requires the canonical AWS Settings owner, then checks the copied
application/migration files, lockfiles, secret loader, production dependency
closure and default image commands. Bounded networkless containers verify the
Docker CLI and the checker's expected missing-configuration failure for the
separate controller artifact still used by the opt-in
[local agent-loop overlay](../../docker-compose.agent-loop.yml). The default
`all-release-images` verifier scope retains that artifact's regression proof;
it is not a native hosted deployment prerequisite. These checks do not
start Workstream or run a project checker. Its fixed JSON artifact records source
identity and local image IDs, not publishable repository digests. Full hosted
operation remains separate evidence. The proof builds and inspects both SDK
closures and rejects either SDK appearing in the other image. An unconditional workflow cleanup verifies
that no smoke container owned by that run remains after inspection or timeout.

## Prepare the host

Install Docker for the backend containers and the pinned native Smol bundle
for Linux amd64 with `/dev/kvm`, cgroup v2 and systemd 254 or later. Use the
[existing unit](../../external_checkers/deploy/workstream-checker.service), which
runs as `10001:10001`, places its controller in a delegated subgroup and preserves
independent guardians with `KillMode=process`. Review its explicit deployment
CPU/memory/PID/storage capacity against intake, checker and sequential trial
peak demand; this configuration does not increase registered checker limits.

Keep that storage capacity physically free on the native checker's filesystem,
not merely configured as a quota. ZIP intake seals and counts the upload first,
then reserves a data disk sized for those bytes, permitted expansion and its
qualified image/filesystem allowance, rounded up to whole GiB. Its separate
root overlay is explicitly limited to one GiB and charged as well. A healthy
socket does not prove that reservation can succeed. Subsequent
checkers require their own configured capacity. Monitor free space as well as
service health, and remove only identified obsolete build/staging assets when
needed. Preserve active images, credential state, database volumes and retained
artifact/evidence data. An intake capacity refusal is an infrastructure failure,
not a failed assessment of contributor work.

Provision a dedicated host service account and group at UID/GID `10001:10001`
before starting the unit. Numeric file ownership alone is insufficient: systemd
must resolve this account, otherwise it can fail with `217/USER`. Inspect
`getent passwd 10001` and `getent group 10001` first. If either ID belongs to an
unrelated identity, stop and resolve that host allocation; do not modify or reuse
the unrelated account. When both IDs and the name `workstream-checker` are unused:

```sh
sudo groupadd --gid 10001 workstream-checker
sudo useradd --system --uid 10001 --gid 10001 --no-create-home \
  --home-dir /nonexistent --shell /usr/sbin/nologin workstream-checker
```

Keep the account password locked and without a login or home directory. Grant no
sudo or Docker access. The unit's `SupplementaryGroups=kvm` supplies KVM access;
ensure that host group owns `/dev/kvm`. Existing dedicated service identities
must have the same UID, primary GID and restrictions.

Create canonical private roots on durable host storage:

```sh
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/scratch
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/checker-runtime
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/model-runtime
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/model-relays
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream-checker/smol
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream-checker/images
sudo install -d -m 0750 -o 10002 -g 10001 /var/lib/workstream/guide-runtime
```

Preserve the node socket parent's persistent owner/lease custody and all trial
root markers across restarts. Never clone them into another live deployment or
replace them with `/run`, tmpfs or container storage. Do not delete retained
inputs, product evidence, shared roots or unknown runtime resources during
recovery. Unknown ownership or cleanup refuses admission.

Provision project images and the pinned trusted intake image using the existing
[Smol cache command](../../external_checkers/README.md#smol-microvm-engine).
The native `trusted_intake` configuration selects the intake image; project
registrations cannot select that privileged purpose. Its image/config pins must
match the two `WORKSTREAM_ARTIFACT_INTAKE_*_DIGEST` values. Its required
`storage_envelope` binds the archive/config and Smol/guest hashes to qualified
entry/path limits, overhead bytes and maximum data-disk size. Use the evidence
for the exact release image and native runtime; requalify changed images or
limits. The example's zero overhead/size fields deliberately fail preflight
until replaced with measured bounds. Do not copy a guessed buffer into them.
Cold boot, archive spooling, maximum projected inventory, expanded content and
cleanup must fit; an example upload alone does not qualify the envelope.
The native owner disables automatic Smol image-seed creation and reuse; do not
qualify with an extra upstream seed VM outside the node reservation. Existing
cache data is preserved. Measure startup under the same enforced environment.
Both typed clients
connect through the one mode-`0600` socket in the mode-`0700` checker directory.

Copy `release.env.example` to an operator-owned non-secret environment file and
replace every example identity. The file contains paths and public configuration,
not secret values. Select real Flow issuer, audience, JWKS and algorithm values.
The release profile uses `WORKSTREAM_AUTH_PROVIDER=flow`; local Flow-HMAC and
development authentication are absent.

For invite-only accounts, the managed [Flow Identity provider](../identity/README.md)
uses stock Keycloak browser login and OAuth. Set the `FLOW_IDENTITY_*` values and
pin the backend to `https://IDENTITY_HOST/realms/flow`, audience `workstream-api`,
RS256 and that realm's JWKS endpoint. The provider uses its own database and role;
its credentials are never mounted into the API or workers. Follow the provider
guide for offline first-administrator bootstrap and participant provisioning.

The issuer port stays on loopback. The [Caddy ingress](public.Caddyfile) exposes
realm login, assets and the authenticated administration console on the fixed
identity hostname. Health, metrics and dynamic registration remain hidden. Confirm real login and token validation before switching the backend.
An issuer administrator receives no Workstream administrative grant. Preserve
retained actor links and records during any non-disposable cutover; never
substitute identities by matching email. Explicitly authorized development
resets use fresh actors and the existing guarded Workstream bootstrap.

Create each secret named by a nonempty configured path as a one-value regular
file. Make it owned by the runtime UID/GID with mode `0400`. The explicit role loader gives the
API only the database, broker, rate-limit and pagination secrets; the worker
gets the database and broker. For read-only GitHub forge facts, optionally set
`WORKSTREAM_GITHUB_APP_ID` and `WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE` together;
`WORKSTREAM_GITHUB_APP_INSTALLATION_ID` may select an installation explicitly.
Leave all three blank when unused. The private file contains the complete PEM,
including its newlines, with the same runtime ownership and `0400` mode.
The checked release command selects `compose.github.yml` only for this pair.
Only the outbox worker receives the mounted key and App settings; API/migrations,
Beat, parser and model proxy receive none. Preflight reads file
metadata only; the worker loader sets the adapter's existing private-key variable
without evaluating or logging its contents. Never put a raw private key in the
release environment. Follow the
[GitHub App instructions](../../examples/garden/github-app.md) for read-only permissions.
`WORKSTREAM_MODEL_PROXY_ENABLED=true` starts one
trusted model-proxy process independently of the setup runtime. Only that process
gets the database, each configured provider credential and the runtime ART identity.
For non-manager setup, the selected setup provider path is required and the other
provider is optional. Manager-authored setup requires at least one provider path
when the proxy is enabled. Nonempty provider paths select provider-specific Compose
overlays; the common inference overlay contains only the socket topology.
The setup worker receives a read-only
mount of `/var/lib/workstream/model-runtime` and the fixed socket selector; it
receives no provider credential or endpoint override. A proxy-disabled
`manager_authored` release omits both credential selectors, mounts and secret
definitions; a proxy-enabled one can still run approved POST model checks. Beat
gets only the database and broker secrets needed to schedule jobs. An absent required selector or unknown role stops
startup, and an unrelated secret is neither mounted nor loaded. The loader
independently requires the running identity and mode `0400`, performs no shell
evaluation and never prints a value. Do not put AWS static keys in these files.

Before setup or POST model calls, provision the existing service actors through
the public administrative API, including `workstream.artifact.checker_output`.
This principal admits private model request/response evidence; configuring the
proxy and provider credentials does not provision it. The canonical journey
service bootstrap includes it for both setup and checker model use.

With the proxy enabled, the native checker service reads the global
model socket from its canonical host path. Its separate writable
`/var/lib/workstream/model-relays` directory is private to the native service, owned by the runtime UID/GID with mode `0700`.
Start the proxy before the native node. The service creates an invocation relay
and the Smol transport exposes only its guest-local capability endpoint. Project
images receive neither the global socket nor provider credentials. API and Beat receive
neither model directory.
The two provider file paths are trusted release configuration. The proxy loads
only configured dedicated files as `OPENROUTER_API_KEY` or `OPENAI_API_KEY`; this is
independent of the setup provider because approved POST and setup profiles may
use different providers. An absent provider is not mounted or exported. The
proxy clears both native variables before loading configured files
and never exports a neutral key variable. The endpoints are
fixed by the registered adapter and cannot be supplied in the release file.
The parser receives no database, broker, S3, Flow, model or provider credential.
The release file also fixes the runtime, provider, model, model API, adapter
options and whole-run/document/tool budgets. Those non-secret values are shared
by API, worker and Beat so every Settings snapshot describes the
same release. The parser receives only its fixed socket selector. The example
selects `openai_agents_sdk` through OpenRouter with
`openai/gpt-5.6-terra`; changing a trusted selector requires another reviewed
release and never changes retained attempt evidence.
To select `omnicore_agent`, publish and choose the `omnicore` worker image digest,
retain the separate `agents` proxy digest, and retain OpenRouter with
`chat_completions`; ordinary model identity remains a reviewed release choice.
OpenRouter models with a colon routing suffix and
`openrouter/*` router identities are rejected.

Before either OpenRouter-backed runtime receives real guide material, the
operator must retain evidence for the exact account, organization or workspace
and credential scope showing that account plugins cannot override the request.
The evidence must cover the plugin catalogue, defaults, overrides, and especially
alignment; name the verifier and approver. Revalidate it after the selected
account, account ownership, organization, workspace, credential scope, plugin
catalogue or defaults, override policy, provider policy, selected model or runtime
changes. Request-level plugin-disable fields are defense in depth and do not prove
the external account state.
This provider credential is not reused for retained OpenAI resource cleanup.
The exact-ID historical cleanup reader has no hosted credential selector in
this slice and therefore fails closed until a separately reviewed retained-data
credential is supplied.
The hosted profile uses `WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE=aws_access_key`.
Set `WORKSTREAM_ARTIFACT_S3_RUNTIME_USER_ARN` to the dedicated IAM user and
`WORKSTREAM_ARTIFACT_S3_DIRECT_USER_CREDENTIAL_HOST_FILE` to its private JSON
credential file. Compose mounts it read-only at
`/run/workstream-artifact-credentials/aws-access-key.json` only in API, worker
and model-proxy. Beat, MCP, parser and checker guests receive no storage key.

Follow [S3 credential setup](../../docs/operations_aws_s3_credentials.md) for
restricted policies and rotation. Qualification verifies real conditional
upload/readback and denied destructive access before cutover. There are no
periodic proof jobs, certificate mounts or expiring database activations.
Keep operation deadlines bounded and measured against the deployment; a network
failure remains a recoverable storage failure, not permission to declare success.

`WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS` explicitly carries the
existing ART processing deadline to every backend role. The
template preserves its 3,400-second default. With the unchanged ZIP inspection,
cleanup margin and scratch TTL defaults, it must be finite and strictly between
300 and 3,600 seconds: ZIP inspection must fit inside processing, and processing
plus the 300-second cleanup margin must expire before the 3,900-second scratch
reservation TTL. Canonical Settings validates the same relationships at startup.
This is an operational deadline, not a project/checker resource cap. Choose a
value that accommodates the selected workload; a shorter owned qualification
may observe real expiry sooner, without resetting its original deadline or
changing registered checker limits.

Copy `checker-service.example.json` to the configured private mode-`0400`
path. The unit reads `/etc/workstream/checker-service.json`. Replace all example
binary, guest, archive, platform-manifest and config digests with independently
verified values. The default-behavior digest must match the built source's
canonical default checker. Runtime execution uses preloaded archives and never
pulls, resolves a tag or falls back to Docker/runsc.

For a proxy-disabled release remove both `model_proxy_socket` and
`model_relay_root`; preflight rejects partial or substituted selectors. For a
proxy-enabled release retain their exact host paths. The running service reads
its configuration from JSON, not the release environment.

Approved POST trial selectors additionally require the optional paired
`WORKSTREAM_CHECKER_TRIAL_AUTHORITY_MANIFEST_PATH` and
`WORKSTREAM_CHECKER_TRIAL_AUTHORITY_MANIFEST_DIGEST`. They activate
`compose.trials.yml`, which mounts that exact host file read-only only into the
model proxy. Set the native JSON's `trial_authority_manifest_path` and
`trial_authority_manifest_digest` to the same host source and digest, and supply
its existing `trial_runtime` object: private relay/scratch/child-home/cache roots,
pinned builder config ID, launcher/filesystem-tool paths and digests, deployment
owner, candidate archive ceiling and exact runtime-configuration digest. Provision
the builder cache entry and approved offline cache from the qualified runtime
release. Do not substitute a project-selected profile or copy the runtime into
this deployment layer. The native runtime and backend typed manifest loader
validate the authority catalogue; preflight checks their shared byte identity
and custody. API, worker and Beat do not read this catalogue or receive its mount.

Smol 1.31.4's longest Unix socket adds 48 filesystem bytes below its HOME. The
107-byte socket limit therefore permits a global `smol.home` of at most 59
bytes. A trial child adds `/ws-<32 hex digits>.home` first, so
`trial_runtime.child_home_root` must be at most 18 bytes. These are filesystem
byte limits, including multibyte characters. Use a separately owned short
private directory such as `/var/tmp/t-<6 hex>` for the trial child root; retain
its runtime owner marker and exact custody. Do not shorten invocation identities
or derive this root from a long deployment prefix. Preflight rejects excess
length before a VM is created.

## Validate without disclosure

The directory commands above describe the default production root. For another
owned root, create its derived children with the same identities and modes, and
replace native JSON socket/material/model paths with those exact derived paths.
Keep source/cache/config/credential files outside that data root.

Run full preflight and the Compose wrapper as the trusted root administrator or
through approved `sudo`. That operator needs authority to traverse the
`10001:10001`-owned `0700` deployment root, inspect private `0400` inputs and
access Docker. This also applies to a newly owned `/var/tmp` proof root. The
native node and health containers run as `10001:10001`; do not grant that runtime
identity Docker group membership or daemon access to make operator checks work.
Preflight never opens application secret files.

The configuration-only check renders Compose and validates fixed topology,
digest identities, Flow/AWS profile and the hosted checker selectors plus
declared cache-identity shape needed by this topology. The application and
checker startup owners validate their complete settings and config schemas,
including the canonical AWS credential settings described above. This check does not inspect host ownership, Docker, cache or any external
service:

```sh
sudo python3 deploy/hosted/preflight.py \
  --env-file /etc/workstream/release.env \
  --configuration-only
```

The full preflight additionally checks secret/config metadata without reading
secret contents, validates private directories and the one node socket owner/mode, and
hashes the installed native service, Smol, guest and cached archive/config assets.
It checks delegated cpu/memory/pids controls and calls the existing typed project
execution and trusted intake health adapters from the pinned backend image with
no credentials or network. Configuration-only mode performs none of those live checks.
Wrong runtime, image/config or default behavior rejects launch:

```sh
sudo python3 deploy/hosted/preflight.py --env-file /etc/workstream/release.env
```

Preflight cannot attest the active AWS identity, absence of extra IAM
permissions, Flow token acceptance, a successful VM boot, collector delivery,
backup recoverability or a live checker result. The
[S3 operations guide](../../docs/operations_aws_s3_credentials.md) describes
the restricted identity, bucket policy and storage qualification. Rendered
configuration does not establish live cloud behavior.

## Start and inspect

Use the checked-in wrapper for every Compose operation. It parses and validates
the approved environment file, renders the fixed topology, and gives Docker
Compose only that parsed allowlist plus fixed process path, operator home and
local Docker-socket values. Ambient shell values cannot replace an image, Flow
URL, secret path, Compose selector or Docker daemon selector. Normal `up`
reloads the node configuration and requires static custody plus both typed native
health checks before releasing API/worker services. `pull`, `ps` and fixed `stop`
remain usable while a node is unavailable.

### Provision project-points prerequisites

Use the fixed `provision-project-points` operation for the authenticated Finance
operator command. Before hosted use, the selected digest-qualified backend image
must contain the reviewed `scripts/provision_project_points.py` and current
adapter-binding replay authority fence. Older deployed images do not acquire
these changes from the host checkout. Build and release the intended backend
image first; do not mount replacement source or override the image/entrypoint.

An Access Administrator separately provisions the actual compensation-adapter
actor through the public service-actor route. Supply that actor UUID and the
project UUID. Store a short-lived real Finance Flow token in a canonical absolute
host file owned by `10001:10001`, mode `0400` or `0600`, with one hard link and no
symbolic links. The nonempty file must be at most 16,384 bytes; its path cannot
contain whitespace, colons or commas. Never put the bearer itself in argv or the
release environment file.

```bash
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  provision-project-points --project-id "$PROJECT_ID" \
  --adapter-actor-id "$ADAPTER_ID" --unit-code FLOW \
  --route-key flow_points.recording \
  --finance-token-file /etc/workstream/operator/finance-token
```

All five inputs are required. The wrapper validates the release and static host
inputs, then runs only the configured API image's embedded provisioner, retaining
the API role's entrypoint, secrets, network and TLS trust. It adds one read-only
mount at `/run/secrets/points_finance_token`; it does not publish API ports, start
dependencies, run migrations or launch a checker. Generic `run`, arbitrary
commands, environment/entrypoint overrides and source/image mounts are rejected.

The operator verifies the token and current Finance authority separately for each
committed step and exact replay. Its result contains actual owner receipts;
unit and binding commits are separate. Execution has a 120-second inner deadline
with five seconds to kill, a 150-second outer wait and a ten-second cleanup bound.
Normal completion removes the one-off container. Exceptional cleanup targets
only its generated name; uncertainty reports that name without claiming removal.
A timeout or start failure remains a failure even if a step committed. Retain
the receipts and inspect the outcome before an explicitly chosen retry; the
wrapper never retries automatically or infers readiness. No award, policy
publication or external fulfillment is performed by this operation.

Cold startup orders migrations before application services. `migrate` runs the
existing API image's Alembic command without application startup or checker
health checks. Ordinary API startup never applies migrations. Qualify the
configured storage credential before cutover, then start the optional model
proxy and the native node for the single-host checker topology. Run these
operator steps:

```sh
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env pull
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env migrate
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  up -d model-proxy
# Wait for the proxy health check, then start the reviewed native unit explicitly.
sudo systemctl start workstream-checker.service
sudo python3 deploy/hosted/preflight.py --env-file /etc/workstream/release.env
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  up --detach --wait
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env ps
```

A proxy-disabled release omits its proxy stage. Schema migration and any required
storage qualification still precede release cutover. Keep reviewed files unchanged
between validation and launch. These checks do not constrain a trusted host
administrator and do not attest the running node's complete source custody;
qualification separately records its actual process/binary identities.

The guide parser and enabled model proxy must pass their existing health checks
before the worker starts. Beat retains existing recovery schedules. API health
is a lightweight endpoint; Celery health checks its processes. Typed native
readiness verifies runtime/identity/cache-count and pinned intake/default facts;
exact image selection is independently checked during every execution. None of
these checks replaces a public authenticated journey, storage qualification, resource
qualification or restart/cleanup evidence. Each Compose service has its existing
finite restart policy; the native unit retains its own bounded systemd policy.

### Reconcile an installed host after reboot

Docker restart policies do not enforce Compose dependency health ordering at
host boot. The native node can exhaust its start attempts before the model proxy
socket is ready, and MCP can retain a stopped API's network namespace. Install
[workstream-hosted.service](workstream-hosted.service) after the initial schema,
storage qualification, pinned image installation and public journey have passed. Copy
the reviewed checkout to `/opt/workstream/source`, or edit both absolute source
paths in the copied unit to its permanent root-owned location. Keep that checkout
and `/etc/workstream/release.env` private and writable only by the deployment
administrator.

```sh
sudo install -m 0644 deploy/hosted/workstream-hosted.service /etc/systemd/system/workstream-hosted.service
sudo systemctl daemon-reload
sudo systemctl enable --now workstream-hosted.service
sudo systemctl status workstream-hosted.service
```

The unit runs exactly `compose.py --env-file /etc/workstream/release.env resume`
after Docker and network startup. This reconciles optional local data and identity
services, waits for the enabled model proxy, resets the native node's exhausted
start counter and starts that existing unit. It waits for canonical typed native
and intake readiness before reconciling API, workers and scheduler. MCP is held
out of the API health wait, then recreated against the current API namespace and
verified. An already active native node is preserved. Each attempt has management
deadlines; systemd retries failed reconciliation after 30 seconds and records
failures in its journal. Inspect `journalctl -u workstream-hosted.service` and
`journalctl -u workstream-checker.service` for diagnosis.

Resume uses installed digest-pinned images with `--pull never`; registry login
and network availability to the registry are unnecessary for reboot. A missing
image fails recovery. It never initializes accounts, rotates credentials,
migrates the schema or rotates credentials. Upgrades still follow the reviewed
migration and storage qualification procedure. Container restart can begin independently
before reconciliation; the unit repairs dependency races and checks readiness,
not a new runtime health monitor. Record an actual reboot and post-reboot public
journey before claiming restart qualification.

The hosted unit has no implicit stop action. Use the existing consumer-first
`compose.py ... stop` before planned maintenance, and disable the hosted unit
before shutting down a deployment permanently. To rerun reconciliation after an
operator repair, use `systemctl restart workstream-hosted.service`.

The API binds to host loopback for an environment-owned TLS reverse proxy. Do
not expose the checker socket, Docker socket, PostgreSQL, Redis or OTLP collector
as public ports.

## Diagnostics

Set an HTTPS `WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT` only for an approved
collector. The existing API/Celery instrumentation bounds fields, correlates
requests and jobs and fails independently of exporter outages. Restrict
collector and container-log access, transport and storage at the environment
boundary; apply a finite retention policy there. During the hosted drill,
confirm correlation for one success and each required infrastructure outcome,
confirm that private documents and tokens are absent, and prove that a collector
outage does not change product results. Configuration alone is not that proof.

## Drain, restart and upgrade

The wrapper's `stop` operation stops Beat and API first so they cannot produce
new work, gives the prefork worker its configured 7,320-second graceful window,
then drains the model proxy before stopping the parser. If the local backing-service
overlay is enabled, Redis and PostgreSQL stop last, preserving their data directories. It never stops the
native systemd node.
Keeping all socket services alive while the worker drains lets cancellation and
terminal persistence finish against their original dependencies. Guide inference
has a 7,260-second process backstop;
the shared Redis transport uses a 7,380-second visibility timeout with prefetch
disabled. The persisted guide-attempt deadline remains the ordinary, shorter
execution bound. Celery task hard limits and durable database/outbox custody
remain owned by the application.

```sh
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env stop
```

For an intentional worker-only interruption, the existing wrapper also accepts
exactly `stop worker` followed by `start worker`. Stop preserves API, Beat, proxy,
parser and native node while allowing the configured 7,320-second worker drain;
its CLI deadline adds 60 seconds for management. This is not a full deployment
drain: producers can continue creating durable work. Start repeats the full
private-input and typed native readiness checks, then reconciles only the worker
with a 60-second health wait and a 120-second CLI deadline. It does not start
dependencies. A failed or timed-out command requires state inspection; it never
automatically force-kills, retries or stops another service.

```sh
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env stop worker
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env start worker
```

For a restart or upgrade, preserve scratch until cleanup/recovery has classified
all retained work, update only reviewed digest identities/configuration, rerun
the cold/warm dependency sequence above, and start with `up --detach --wait`.
The scratch ownership marker binds the configured limits, including the total
preparation deadline. Changing those limits requires a drained scratch pool;
do not edit its marker to make a new release start. Stop all processes mounting
that pool, verify that no reservations or workspaces remain, and retain the old
directory intact before provisioning a fresh private directory at the canonical
path. Let the normal ART manager initialize it, recreate the affected container
and systemd mounts, and verify that API, worker, proxy and native node all see
the same new directory.
If retained work remains, complete its recovery under the original configuration
before changing the pool.

Before restarting or stopping the native unit, first drain producers and the
worker through the wrapper, retain the proxy until node calls settle, and
independently confirm that this node has no active owned leases, VMs or cgroups.
Preserve guardian recovery and use the exact owner-scoped inventory; never prune
shared resources or stop another deployment. Exercise an interrupted
job and verify the existing exact retry/reconciliation operations rather than
editing rows or replaying unknown work blindly.

Before upgrading through `0059_neutral_guide_runtime`, inspect retained guide
attempts using the currently deployed release's supported diagnostics and
recovery operations. The migration refuses an inferred attempt without
`adapter_profile` in `compilation_reserved` or `provider_result_accepted`, with
`old inferred guide attempt requires removed runtime recovery before upgrade`.
Finish supported recovery under the existing image and its compatible schema
before retrying the explicit migration. If that command refuses, do not start
the new API or enable its host recovery unit. If recovery cannot complete, keep
the upgrade blocked; do not edit the attempt, delete evidence, or redispatch uncertain work
under the new runtime. The new image preserves retained evidence and exact-ID
cleanup, not the removed inference implementation.

Database migrations are forward-only. Never downgrade a protected migration or
delete immutable rows/objects to force a code rollback. An older application
image may be restored only when its reviewed release evidence says it supports
the current schema. Otherwise repair forward with a new reviewed digest.

## Backup and restore proof

Use the selected PostgreSQL provider's consistent backup/snapshot facility and
the [AWS bucket versioning and custody procedure](../../docs/operations_aws_s3_credentials.md).
Before release, identify the provider's exact backup and restore operations,
retention policy, authorized operator and isolated restore target. Verify that
the target can read the retained artifact namespace without write authority.
Redis carries queue transport, not Workstream lifecycle truth; recovery scanners
rebuild eligible delivery from PostgreSQL owners. Never treat a Redis snapshot
as the record backup and never delete retained S3 objects during database
recovery.

Before a release, restore the database backup into an isolated environment with
the same application/schema digest and read-only access to the retained artifact
namespace. Verify migration head, representative project/task/assignment/
submission/checker/final-acceptance/contribution identities, immutable hashes,
outbox custody and artifact reads through public or owner-supported operations.
Do not repair product rows directly. Record provider backup IDs, restore target,
source/image/config identities, timestamps and bounded results without document
bytes, tokens, connection URLs or credentials.

Audit validation uses function-local search paths after
`0060_audit_restore_path`, so PostgreSQL's empty restore search path does not
prevent loading retained audit facts. Take a fresh backup after applying this
migration. Earlier archives retain their earlier function definitions and need
an operator-reviewed schema correction on the isolated restore target before
data loading; the two-function correction is defined by
[the migration](../../backend/alembic/versions/0060_audit_restore_path.py).
Do not disable validation or edit retained rows to force a restore to finish.

Run the selected provider's documented backup and restore operations for the
actual deployment. Record the exact commands or API operations, provider backup
ID, restore result and checks above in private release evidence. This repository
cannot supply one universal provider command for environment-managed PostgreSQL.

## Remaining release evidence

For each deployment, retain its exact source, service-image, checker-image,
configuration, native binary/cache and corpus identities with the results of
full preflight, real S3 storage qualification, public API/worker journey, drain
and restart, supported recovery and isolated backup restore. Verify real Flow
human/service authority, AWS custody and negative identity cases, registry
access, Smol isolation, representative CPU/memory/PID/disk/time limits,
missing-cache classification and collector behavior if OTLP is enabled. The
[current capability ledger](../../docs/roadmap_status.md) distinguishes source
delivery from live qualification and remaining release gates.

## Managed private MCP service

Set `WORKSTREAM_MCP_IMAGE` to the qualified MCP image digest to include
[`compose.mcp.yml`](compose.mcp.yml). Build that image from the repository root with
`docker build -f mcp_server/Dockerfile .`; its build context excludes backend
product code. The adapter receives no account password, server-wide bearer,
database credential or artifact-store key. It receives only its private Keycloak
exchange-client secret through `WORKSTREAM_MCP_EXCHANGE_SECRET_FILE`. Each client
supplies an MCP-scoped OAuth token; the adapter exchanges it for an API-only
token for the same user. The API retains all authorization decisions.

The adapter shares API's network namespace and calls only its loopback port 8000.
Its port 8080 is published on host `127.0.0.1` only. For private access, forward
local port 8080 to host `127.0.0.1:8080` through authenticated SSH and connect to
`http://127.0.0.1:8080/mcp`. Preserve that exact Host header. The configured OAuth
resource identity remains the public HTTPS MCP URL, even through a private
transport. Use the [public ingress](PUBLIC_ACCESS.md) for normal OAuth discovery
and browser authorization. Tokens belong in the client's protected credential
storage, never tool arguments or URLs; an API-only login token cannot access MCP.

Use the hosted wrapper for updates. When an `up` operation can replace API, the
wrapper stops MCP first and force-recreates it after the operation succeeds,
then checks its actual namespace against the current API container ID. With
`--no-start`, MCP remains stopped until the subsequent start. Shutdown stops MCP
before API. Direct Docker recreation of API bypasses this coupling and is not a
supported update procedure. The initial overlay requires a controlled API
replacement to add the private port; it cannot be hot-attached.

The health probe checks API health, protected-resource metadata and the
unauthenticated 401 challenge. It does not establish a caller's authority:
qualification must additionally call tools with fresh MCP-scoped tokens and
verify both permitted and denied access. API's Docker
bridge can still reach the listener, so exact Host checks, browser-Origin
rejection and per-call authentication remain necessary. For public OAuth clients, use the [public HTTPS ingress](PUBLIC_ACCESS.md) and
qualify the actual client before sharing the URL. It preserves these private
listeners and browser-Origin denial. Discovery support alone does not prove
Garden interoperability; that requires its registered client and live flow.
