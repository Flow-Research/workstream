# Hosted Release Configuration

This directory prepares the Workstream API, general Celery worker, exclusive
submission-finalization and source-cleanup workers, Beat, fixed guide-document
parser and optional trusted model proxy on an app-only Linux amd64 host.
PostgreSQL and Redis may use the host-local data overlay or separately managed
services. Project PRE/POST and trusted ZIP intake run only on the separately
administered, always-on remote runner.

The checked-in [release environment template](release.env.example),
[Compose wrapper](compose.py), [preflight](preflight.py), and
[canonical Settings](../../backend/app/core/config.py) define the app topology.
The runner unit/config examples live under
[external_checkers/deploy](../../external_checkers/deploy). An operator must
still build and pin exact images, provision both hosts, install private
credentials, qualify storage and runner health, and verify the public journey.
A render, image build or preflight alone is not deployment evidence.

## App host without KVM

Hosted releases set `WORKSTREAM_HOSTED_PROFILE=app`. Supply the private runner
address, port and certificate name through
`WORKSTREAM_EXTERNAL_RUNNER_{HOST,PORT,SERVER_NAME}`; supply the CA, client
certificate and client key through the corresponding `*_FILE` selectors.
Pin `WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST` and
`WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST` to the images installed on the
runner. Preflight refuses partial endpoint or TLS configuration.

The API and worker connect directly to the runner for PRE, POST and trusted
intake. When model execution is enabled, the worker forwards bounded callback
frames between its app-local model-proxy socket and the same authenticated TLS
connection that owns the remote execution.
There is no local native checker socket, KVM device, checker binary/config or
shared API/runner material filesystem, and there is no single-host fallback.

## Trust boundary

The runner listener requires TLS 1.3 client authentication and the configured
application DNS SAN. The app validates the runner certificate name. PRE source
and POST material cross this boundary in bounded frames. The runner validates
the canonical request/source/grant binding before creating one private local
workspace, invokes the native checker through runner-internal Unix IPC, and
removes that exact session on success, error, timeout or disconnect.

The runner's native service owns KVM, delegated cpu/memory/pids cgroups, Smol
leases and cleanup. Project guests receive only guest-local capability sockets.
They never receive TLS keys, model-provider credentials, AWS credentials or the
runner-global Unix sockets. The optional model proxy retains provider keys on
the app host. Callback loss closes that invocation; the runner never selects a
different app replica or a runner-global callback owner.

Only the app security group needs private TCP access to runner port 9443.
Do not publish 9443 to the internet. Install the client key as a mode-0400
Compose secret and never place it in the release environment or command line.
Future managed execution providers must preserve the same typed
task/source/result contract; this release does not qualify a vendor adapter.

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
decides whether approved POST images can use the proxy. Build and install the
native service, static guest, remote edge and pinned image cache on the separate
runner using the [node instructions](../../external_checkers/README.md#smol-microvm-engine).
Record their exact digests in the runner qualification receipt. A local build
tag is build evidence only; the app release file must
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
evidence shape. Installed runner service, Smol, guest and cache identities remain
the runner qualification's responsibility. Backend-image proof establishes no native
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

## Prepare the app host

Install Docker for the backend containers. Provision the dedicated app runtime
account at UID/GID `10001:10001`, then create only the app-owned durable roots:

```sh
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/scratch
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/model-runtime
sudo install -d -m 0750 -o 10002 -g 10001 /var/lib/workstream/guide-runtime
```

Do not install KVM, Smol, a native checker unit, image cache or checker runtime
directory on this host. Qualify the runner separately using the native and edge
units under `external_checkers/deploy`. Restrict runner TCP 9443 ingress to the
app security group, install the CA/client certificate/client key as private app
secrets, and verify the certificate SAN and pinned image identities before app
activation.

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
gets only the database and broker secrets needed to schedule jobs. An absent required selector or unknown role stops
startup, and an unrelated secret is neither mounted nor loaded. The loader
independently requires the running identity and mode `0400`, performs no shell
evaluation and never prints a value. Do not put AWS static keys in these files.

Before setup or POST model calls, provision the existing service actors through
the public administrative API, including `workstream.artifact.checker_output`.
This principal admits private model request/response evidence; configuring the
proxy and provider credentials does not provision it. The canonical journey
service bootstrap includes it for both setup and checker model use.

With the proxy enabled, its process owns the app-local model socket. The Celery
worker mounts that socket read-only and forwards opaque normal-model,
trial-evidence and setup-model frames only while its exact remote execute TLS
connection remains active. The native service connects only to the runner-local
model socket. The Smol transport exposes only its guest-local capability
endpoint. Project images receive neither global socket nor provider credentials.
API and Beat receive no model directory.
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
`/run/workstream-artifact-credentials/aws-access-key.json` only in API, general
worker, exclusive finalization worker and model-proxy. Set
`WORKSTREAM_ARTIFACT_S3_CLEANUP_USER_ARN` and
`WORKSTREAM_ARTIFACT_S3_CLEANUP_USER_CREDENTIAL_HOST_FILE` to the separately
authorized deletion identity. Only the exclusive source-cleanup worker receives
that file; preflight rejects a reused ARN, path or inode. Beat, MCP, parser and
checker guests receive no storage key.

Follow [S3 credential setup](../../docs/operations_aws_s3_credentials.md) for
restricted policies and rotation. Qualification verifies real conditional
upload/readback and denied destructive access before cutover. There are no
periodic proof jobs, certificate mounts or expiring database activations.
Keep operation deadlines bounded and measured against the deployment; a network
failure remains a recoverable storage failure, not permission to declare success.

`WORKSTREAM_SUBMISSION_EXECUTION_PROFILE` and
`WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE` are required JSON objects. The
template intentionally contains sentinels rather than guessed values. Static
preflight rejects missing or malformed objects and requires the cleanup
profile's `upload_principal` to equal the runtime upload ARN. Full preflight,
every `up`, and reboot reconciliation then run the canonical strict profile
validators from the pinned backend image before activating services. The
guide compilation, project control, artifact work, outbox scanning, POST delivery,
submission finalization, and source cleanup each have one dedicated prefork
worker consuming exactly one named queue. Beat always
receives the required cleanup profile, so the cleanup schedule cannot disappear
because of an omitted setting.

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

Runner configuration is installed and reviewed separately. It pins the native
service and edge binaries, Smol/guest digests, trusted intake and checker image
manifests/configs, PRE root and capacity profile, private material/model-relay
roots, and TLS server identity. The runner system journal and a non-secret
qualification receipt record actual health, PRE/POST execution and cleanup.
App preflight validates only the configured endpoint, TLS files and intake
digests; it does not infer runner qualification from local files.

## Validate without disclosure

The directory commands above describe the default app production root. Runner
socket/material/model paths belong only to the separately administered runner;
keep its source, cache, config and TLS files outside app-local ART scratch.

Run full preflight and the Compose wrapper as the trusted root administrator or
through approved `sudo`. That operator needs authority to traverse the
`10001:10001`-owned `0700` deployment root, inspect private `0400` inputs and
access Docker. This also applies to a newly owned `/var/tmp` proof root. Do not
grant the application runtime Docker group membership or daemon access to make
operator checks work.
Preflight never opens application secret files.

The configuration-only check renders Compose and validates fixed topology,
digest identities, Flow/AWS profile and the remote-runner selectors. The app
and runner startup owners validate their complete settings and config schemas,
including the canonical AWS credential settings described above. This check does not inspect host ownership, Docker, cache or any external
service:

```sh
sudo python3 deploy/hosted/preflight.py \
  --env-file /etc/workstream/release.env \
  --configuration-only
```

The full preflight additionally checks app secret/config metadata without reading
secret contents, validates private app directories, and runs the pinned image's
strict submission execution/source-cleanup profile validators. Runner runtime, cache,
capacity and cleanup are established by its separate qualification and the
typed remote health/execution paths. Wrong endpoint, TLS or pinned intake
identity rejects launch:

```sh
sudo python3 deploy/hosted/preflight.py --env-file /etc/workstream/release.env
```

App preflight cannot attest the active AWS identity, absence of extra IAM
permissions, Flow token acceptance, a successful remote VM boot, collector
delivery, backup recoverability or a live checker result. The
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
existing API image's Alembic command without application startup. Ordinary API
startup never applies migrations. Qualify the configured storage credential and
the remote runner before cutover, including mTLS health from the app network.
Then run these operator steps:

```sh
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env pull
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env migrate
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
before the guide worker starts. The exclusive finalization and cleanup
workers must also become healthy, and Beat retains its recovery schedules. API
health is a lightweight endpoint; Celery health checks its processes. Remote health
verifies runtime/identity/cache-count and pinned intake/default facts; exact
image selection is independently checked during every execution. None of
these checks replaces a public authenticated journey, storage qualification, resource
qualification or restart/cleanup evidence. Each Compose service has its existing
finite restart policy; the runner units retain their own bounded systemd policy.

### Reconcile an installed host after reboot

Docker restart policies do not enforce Compose dependency health ordering at
host boot, and MCP can retain a stopped API's network namespace. Install
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
services and waits for the enabled model proxy. It requires configured remote
runner and intake readiness before reconciling API, workers and scheduler. MCP is held
out of the API health wait, then recreated against the current API namespace and
verified. Each attempt has management
deadlines; systemd retries failed reconciliation after 30 seconds and records
failures in its journal. Inspect `journalctl -u workstream-hosted.service` on
the app host and the two runner unit journals for diagnosis.

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
not expose Docker, PostgreSQL, Redis or the OTLP collector as public ports. The
runner listener is private and restricted to the app security group.

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
overlay is enabled, Redis and PostgreSQL stop last, preserving their data directories.
It never stops or reconfigures the separately administered runner. Keeping
the remote runner available while the worker drains lets cancellation and
terminal persistence finish against the invocation's original connection. Guide inference
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
parser and the external runner while allowing the configured 7,320-second worker drain;
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
and mounts, and verify that API and worker see the same new app-local directory.
If retained work remains, complete its recovery under the original configuration
before changing the pool.

Before restarting or stopping a runner unit, first drain producers and the
worker through the wrapper, retain the proxy until calls settle, and independently
confirm that the runner has no active owned leases, VMs or cgroups.
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
