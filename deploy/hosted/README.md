# Hosted Release Configuration

This directory prepares the Workstream API, durable Celery worker, Beat,
fixed guide-document parser and optional trusted model proxy on one dedicated
Linux amd64 host. Project PRE/POST and trusted ZIP intake use the existing native
Smol systemd node. Compose does not start a checker controller or grant access
to its Docker socket. PostgreSQL, Redis, AWS S3, Flow identity and the optional
OTLP collector remain environment-managed dependencies.

The checked-in [release environment template](release.env.example),
[Compose wrapper](compose.py), [preflight](preflight.py), native node and
[canonical Settings](../../backend/app/core/config.py) define the source
topology. An operator must still build and publish exact images, provision the
host and external services, configure private assets and credentials, run the
fixed AWS proof, and verify the public journey for that deployment. A render,
image build or preflight alone does not establish hosted operation or a real
model call. The [capability ledger](../../docs/roadmap_status.md) and
[hosted drill report](../../docs/reports/garden-hosted-drill-2026-11-06.md)
record what has actually been exercised; neither makes this directory an
automatic installer or qualifies another host.

## Trust boundary

The native node uses KVM and its delegated cpu/memory/pids cgroup, under the same
numeric UID/GID `10001:10001` as the ART grant issuer. It owns fresh VM execution,
exact leases and cleanup. Neither the node nor project images receive provider
credentials. The optional Compose model proxy alone owns those credentials;
the native node connects to its host-visible private socket and forwards only
invocation-bound capability traffic through the Smol guest transport.

The API and worker mount the node socket directory read-only. Both typed
capabilities use the same host endpoint, while retaining distinct closed
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
a read-only client. API, Beat, proof jobs and the native node do not
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
decides whether approved POST images can use the proxy. The backend image
also installs the official Roles Anywhere helper 1.8.5 at its fixed path, with
architecture-specific hashes checked during the build and image proof. Build the native service and static guest from the same reviewed source using the
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

For invite-only demo accounts, the optional [external Rust issuer](../../experiments/demo_identity/README.md)
provides administrator provisioning, login and password change. It stays outside
Workstream core. Set all `DEMO_IDENTITY_*` essentials in the release environment
and pin Workstream's issuer, audience, algorithms and JWKS URL to the same
service. The wrapper validates the issuer's exact image, private mounts,
UID 12001, network and resource bounds. Initialize its persistent state once;
then start only the issuer and wait for verified HTTPS readiness:

```sh
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env start demo-identity
```

This bootstrap does not start or reconfigure the backend.

The issuer port stays on loopback. Public participants require the chosen DNS
name, a trusted TLS certificate and a bounded HTTPS ingress; see the
[Caddy example](demo-identity.Caddyfile) and issuer instructions. Confirm real
login and token validation before switching the backend. An issuer administrator
receives no Workstream administrative grant. Preserve retained actor links and
records during cutover; never substitute identities by matching email.

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
Beat, parser, model proxy and proof jobs receive none. Preflight reads file
metadata only; the worker loader sets the adapter's existing private-key variable
without evaluating or logging its contents. Never put a raw private key in the
release environment. Follow the
[GitHub App instructions](../../pilots/garden/github-app.md) for read-only permissions.
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
gets the database and broker secrets because its startup guard verifies the
current artifact-provider activation before scheduling jobs. An absent required selector or unknown role stops
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
images receive neither the global socket nor provider credentials. API, Beat and proof jobs receive
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
by API, worker, Beat and proof roles so every Settings snapshot describes the
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
This external-host profile selects Roles Anywhere and mounts the runtime leaf
certificate/key read-only into API and worker. Beat keeps only its database and
broker secrets: its startup guard validates the stored provider activation and
namespace without constructing the S3 adapter or signing helper. The checker
controller receives no AWS identity. Three profile-gated proof jobs receive
their own leaf pairs one at a time; the coordinator receives no certificate.
EC2 instance-role authentication remains an independent native-AWS application
method, but it is not this hosted topology. Follow the complete CA, AWS, renewal
and revocation procedure in
[`docs/operations_aws_roles_anywhere.md`](../../docs/operations_aws_roles_anywhere.md).

Set the immutable release digest and every exact AWS role, managed-policy,
trust-policy, Roles Anywhere resource and bucket-policy identity from the
approved release evidence. The release wrapper allowlists these non-secret
values and the shared Compose environment passes them unchanged to API, worker
and Beat.
The [canonical application Settings](../../backend/app/core/config.py) defines
these fields and validates their format and relationships. It rejects a
malformed digest or ARN, a mixed AWS partition/account, reused workload roles
or trust-policy digests, or reused managed policies when any of those processes
starts. Preflight checks presence and rendered custody only so it does not
create a second IAM-policy validator.

The proof command loads this exact Settings contract with distinct active IAM
identities. Run the wrapper's fixed `proof --group-nonce <uuid>` operation. It
executes runtime immutability, readiness, negative access and then the
credential-free coordinator. Arbitrary Compose `run` commands remain outside
the wrapper. A locally rendered job is still not live AWS evidence.

Recurring proof jobs use the exact digest-pinned backend image already cached
on the release host (`pull_policy: never`). They do not refresh registry login
or contact the registry to start a proof. Acquire the reviewed images through
the authenticated release `pull` operation before starting verification. If the
selected image is absent, verification fails and later proof identities do not
run; restore that exact image through the release process. There is no alternate
image or implicit download. Deployment services retain their normal pull policy.
An image-cache failure does not extend AWS evidence freshness: activation becomes
unavailable when its existing proof window expires, even if process health
checks remain green.

If a recurring proof timer is enabled, check its oneshot state and the exact
group receipts before release finalization or a database preservation check.
An in-progress group is unsettled evidence even when earlier groups passed;
let it finish and verify its result before using a settled interval for the
final check. Keep the timer's normal cadence and the proof guard intact. The
wrapper does not coordinate a release finalization window automatically; do
not delete a running receipt or treat it as a pass.

The [example S3 and completion timeouts](release.env.example) are starting
values, not latency measurements. Canonical Settings requires:

```text
max(S3 operation total, complete-read deadline)
  + terminal-persistence margin + 300-second proof refresh
  + 120-second proof sequence allowance + 30-second clock margin
  <= 900-second activation validity
```

Preflight checks only that these required values are finite and positive. The
canonical application owner validates eligibility at startup. Replace the example values only with values supported by the hosted AWS
drill; satisfying the arithmetic does not prove live latency, AWS identity or
activation.

`WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS` explicitly carries the
existing ART processing deadline to every backend role and proof job. The
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
including the canonical AWS evidence fields described above. This check does not inspect host ownership, Docker, cache or any external
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
[AWS operations guide](../../docs/operations_aws_roles_anywhere.md) describes
the exact role, policy, bucket and certificate preparation and the fixed proof
group. This configuration carries those values into every long-running process
environment for canonical startup validation. Rendered values and valid formats
do not prove the underlying cloud facts or completed proof-job execution.

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

Cold startup has explicit prerequisite stages to avoid a schema/activation/proxy/
node dependency cycle. `migrate` runs only the existing API image's Alembic command
with no dependencies. The fixed AWS `proof` sequence and exactly
`up -d model-proxy` validate static topology and private inputs but require no live
node and release no API, worker or scheduler. The proof command retains its exact
credential-separated AWS observations and coordinator; it does not use intake or
project execution. The API image's release entrypoint loads its API role secrets
and executes the supplied Alembic command without application startup or service
health checks. Alembic loads settings and model metadata, then connects directly
to PostgreSQL; activation and proxy/node readiness follow migration. Run these
reviewed operator steps:

```sh
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env pull
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env migrate
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  proof --group-nonce <fresh-uuid>
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
fresh AWS activation still precede API startup. Keep reviewed files unchanged
between validation and launch. These checks do not constrain a trusted host
administrator and do not attest the running node's complete source custody;
qualification separately records its actual process/binary identities.

The guide parser and enabled model proxy must pass their existing health checks
before the worker starts. Beat retains existing recovery schedules. API health
is a lightweight endpoint; Celery health checks its processes. Typed native
readiness verifies runtime/identity/cache-count and pinned intake/default facts;
exact image selection is independently checked during every execution. None of
these checks replaces a public authenticated journey, provider proof, resource
qualification or restart/cleanup evidence. Each Compose service has its existing
finite restart policy; the native unit retains its own bounded systemd policy.

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
then drains the model proxy before stopping the parser. It never stops the
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
before retrying the upgrade. API startup applies migrations, so this refusal also
prevents the new API from starting. If recovery cannot complete, keep the upgrade
blocked; do not edit the attempt, delete evidence, or redispatch uncertain work
under the new runtime. The new image preserves retained evidence and exact-ID
cleanup, not the removed inference implementation.

Database migrations are forward-only. Never downgrade a protected migration or
delete immutable rows/objects to force a code rollback. An older application
image may be restored only when its reviewed release evidence says it supports
the current schema. Otherwise repair forward with a new reviewed digest.

## Backup and restore proof

Use the selected PostgreSQL provider's consistent backup/snapshot facility and
the [AWS bucket versioning and custody procedure](../../docs/operations_aws_roles_anywhere.md#provision-the-closed-aws-trust).
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
full preflight, a fresh fixed AWS proof group, public API/worker journey, drain
and restart, supported recovery and isolated backup restore. Verify real Flow
human/service authority, AWS custody and negative identity cases, registry
access, Smol isolation, representative CPU/memory/PID/disk/time limits,
missing-cache classification and collector behavior if OTLP is enabled. The
[current capability ledger](../../docs/roadmap_status.md) distinguishes source
delivery from live qualification and remaining release gates.

## Managed private MCP service

Set `WORKSTREAM_MCP_IMAGE` to the qualified MCP image digest to include
[`compose.mcp.yml`](compose.mcp.yml). Build that image from `mcp_server/`, not the
repository root. The adapter receives no account password, server-wide bearer,
database credential or artifact-store key. Each client supplies its own fresh
Rust-issued Workstream access token; the API retains all authorization decisions.

The adapter shares API's network namespace and calls only its loopback port 8000.
Its port 8080 is published on host `127.0.0.1` only. For private access, forward
local port 8080 to host `127.0.0.1:8080` through authenticated SSH and connect to
`http://127.0.0.1:8080/mcp`. Preserve that exact Host header. This is custom
bearer-header MCP, not OAuth discovery or a public browser endpoint. Tokens belong
in the client's protected header configuration, never tool arguments or URLs.

Use the hosted wrapper for updates. When an `up` operation can replace API, the
wrapper stops MCP first and force-recreates it after the operation succeeds,
then checks its actual namespace against the current API container ID. With
`--no-start`, MCP remains stopped until the subsequent start. Shutdown stops MCP
before API. Direct Docker recreation of API bypasses this coupling and is not a
supported update procedure. The initial overlay requires a controlled API
replacement to add the private port; it cannot be hot-attached.

The health probe checks API health and the static MCP catalogue. It does not
establish a caller's authority: qualification must additionally call tools with
fresh login tokens and verify both permitted and denied access. API's Docker
bridge can still reach the listener, so exact Host checks, browser-Origin
rejection and per-call authentication remain necessary. For public native bearer
clients, use the [public HTTPS ingress](PUBLIC_ACCESS.md) and run its external
login/client checks before sharing the URL. It preserves these private listeners
and browser-Origin denial. Clients requiring OAuth discovery remain unsupported
by this profile.
