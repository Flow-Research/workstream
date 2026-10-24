# Hosted Release Configuration

This directory contains the first bounded release composition for the Workstream
API, durable Celery worker, Beat scheduler, fixed guide-document parser and
existing Rust external-checker service. It targets one dedicated Linux runner
host with Docker and gVisor `runsc` for project execution, plus a separately
provisioned KVM/Smol node for trusted ZIP intake. PostgreSQL, Redis, AWS S3, Flow identity and the optional OTLP collector
are external services managed by the approved environment.

The files prepare a release; they do not provision or deploy one. A successful
render, image build or preflight is not AWS, Flow, recovery, performance or
hosted-isolation proof. Parent issue #555 owns the connected deployed evidence.

## Trust boundary

The checker service controls the host Docker daemon through
`/var/run/docker.sock`. That is host-level authority. gVisor isolates the
untrusted checker containers launched by the service; it does not protect the
host from compromise of the trusted checker-service controller. Use a dedicated
runner host and a trusted daemon. Do not place unrelated workloads or credentials
on that host.

The checker controller has no network, runs as a fixed non-root UID/GID, drops
all Linux capabilities and mounts verified material read-only. Its supplemental
group grants only access to the Docker socket. The API and worker use the same
absolute host paths as the controller because the host daemon, rather than the
controller container's mount namespace, resolves checker bind sources:

```text
/var/lib/workstream/scratch
/var/lib/workstream/checker-runtime/checker.sock
/var/lib/workstream/intake-runtime/checker.sock
```

Keep these absolute paths consistent across the host and clients. The intake
node owns its private socket directory; API and Celery mount it read-only. It
needs no Docker socket, provider credentials or project model credentials.
Trusted ZIP inspection and default checks run in its pinned guest image; project
PRE/POST still use the separately configured execution capability.

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
a read-only client. API, Beat, proof jobs and the checker controller do not
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
docker build --file docker/checker/Dockerfile.release \
  --tag registry.example/workstream/checker-service:<source-commit> .
```

Both Dockerfiles pin their base images. Each backend build requires one exact SDK
environment and installs only its committed `agents` or `omnicore` resolution,
without the development extra. The image records that choice in a root-owned
read-only marker; startup rejects a configured inference runtime that does not
match it before reading the provider credential. `manager_authored` is accepted
in either image with the exact `none/none/none` model tuple and reads no provider
credential. The backend image
also installs the official Roles Anywhere helper 1.8.5 at its fixed path, with
architecture-specific hashes checked during the build and image proof. The
checker-service build compiles the committed Rust lock and copies the pinned
Docker client. A local build tag is build evidence only; the release file must
contain the registry-resolved digest after publication. The backend build's uv
package-download cache mount exists only on the builder; it is not retained in
the image. Runtime image inspection uses `uv --no-cache pip check` and bounded
temporary storage.

The scoped [release-image workflow](../../.github/workflows/release-images.yml)
runs for release definitions and copied backend/checker source changes, building
the exact PR head without cache, publication or deployment credentials.
It first requires the canonical AWS Settings owner, then checks the copied
application/migration files, lockfiles, secret loader, production dependency
closure and default image commands. Bounded networkless containers verify the
Docker CLI and the checker's expected missing-configuration failure; they do not
start Workstream or run a project checker. Its fixed JSON artifact records source
identity and local image IDs, not publishable repository digests. Full hosted
operation remains separate evidence. The proof builds and inspects both SDK
closures and rejects either SDK appearing in the other image. An unconditional workflow cleanup verifies
that no smoke container owned by that run remains after inspection or timeout.

## Prepare the host

Install and configure Docker and gVisor using the approved host process. Confirm
that Docker reports a `runsc` runtime. Installation and daemon configuration are
outside this repository configuration.

The hosted profile fixes backend processes at UID/GID 10001 and the parser broker
at UID 10002 with the shared client group 10001 after its identity bootstrap.
Find the Docker socket GID and
create the fixed private directories with these exact identities:

```sh
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/scratch
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/checker-runtime
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/intake-runtime
sudo install -d -m 0750 -o 10002 -g 10001 /var/lib/workstream/guide-runtime
stat -c '%g' /var/run/docker.sock
```

The checker runtime directory must be on durable host storage, not `/run`,
tmpfs or ephemeral container storage. Its private `.workstream-checker-owner`
file identifies containers recoverable after a service or host restart. Only the
checker service has a writable mount; API and worker socket mounts are read-only
so clients can connect but cannot replace recovery custody. Preserve the file
with the directory; never clone it into another live deployment. Before
changing or deleting this directory, drain checker work and verify cleanup of
its exact owned containers. If custody was lost, reconcile independently verified
container IDs; a new owner will not adopt old containers. See
[container recovery ownership](../../external_checkers/README.md#container-recovery-ownership).

Provision the [Smol node and pinned trusted image](../../external_checkers/README.md#trusted-submission-intake)
under UID/GID 10001 before launch. Its socket must be mode `0600` inside the
`0700` intake directory. Preserve its owner and lease files across restarts. Set
`WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST` and
`WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST` to the exact cached manifest/config;
project registrations cannot select that privileged purpose. Account for its
2 GiB guest memory plus VMM overhead when setting the delegated node budget.

Copy `release.env.example` to an operator-owned non-secret environment file and
replace every example identity. The file contains paths and public configuration,
not secret values. Select real Flow issuer, audience, JWKS and algorithm values.
The release profile uses `WORKSTREAM_AUTH_PROVIDER=flow`; local Flow-HMAC and
development authentication are absent.

Create each secret selected by the configured runtime as a one-value regular file at the configured path. Make it
owned by the runtime UID/GID with mode `0400`. The explicit role loader gives the
API only the database, broker, rate-limit and pagination secrets; the worker
gets the database and broker. Inference runtimes additionally select and mount
one project-agent provider credential because the worker hosts setup jobs;
`manager_authored` must omit that selector, mount and secret definition. Beat
gets the database and broker secrets because its startup guard verifies the
current artifact-provider activation before scheduling jobs. An absent required selector or unknown role stops
startup, and an unrelated secret is neither mounted nor loaded. The loader
independently requires the running identity and mode `0400`, performs no shell
evaluation and never prints a value. Do not put AWS static keys in these files.
The provider selector is trusted release configuration. For `openrouter`, the
entrypoint loads the worker-only file as `OPENROUTER_API_KEY`; for `openai`, it
loads the same selector as `OPENAI_API_KEY`. It clears both native variables
before selecting one and never exports a neutral key variable. The endpoint is
fixed by the registered adapter and cannot be supplied in the release file.
The parser receives no database, broker, S3, Flow, model or provider credential.
The release file also fixes the runtime, provider, model, model API, adapter
options and whole-run/document/tool budgets. Those non-secret values are shared
by API, worker, Beat and proof roles so every Settings snapshot describes the
same release. The parser receives only its fixed socket selector. The example
selects `openai_agents_sdk` through OpenRouter with
`openai/gpt-5.6-terra`; changing a trusted selector requires another reviewed
release and never changes retained attempt evidence.
To select `omnicore_agent`, publish and choose the `omnicore` image digest and
retain OpenRouter with `chat_completions`; ordinary model identity remains a
reviewed release choice. OpenRouter models with a colon routing suffix and
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
The integrated canonical application `Settings` from #582/PR #592 defines
these fields and validates their format and relationships. That owner rejects a malformed digest or ARN, a mixed AWS partition/account, reused
workload roles or trust-policy digests, or reused managed policies when any of
those processes starts. Preflight checks presence and rendered custody only so
it does not create a second IAM-policy validator.

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

The example S3 and completion timeouts are unmeasured starting values supplied
by the current #582 contract:

```text
max(S3 operation total, complete-read deadline)
  + terminal-persistence margin + 30-second clock margin
  + 300-second proof refresh <= 900 seconds
```

Preflight checks only that these required values are finite and positive. The
canonical application owner validates eligibility at startup. Replace the example values only with values supported by the hosted AWS
drill; satisfying the arithmetic does not prove live latency, AWS identity or
activation.

Copy `checker-service.example.json` to the configured private path, mode `0400`
and the same runtime owner. Replace the example cache with every approved
single-platform checker image supplied by the project checker/registry work.
For each entry, preserve the exact repository, platform manifest digest/media
type/byte count, Linux architecture and Docker config image ID. Pull every
`repository@sha256:...` identity before preflight. Full preflight checks that
point-in-time local cache identity. The checked-in runner independently rejects
a tag, missing image, substituted config ID, platform mismatch or absent runsc
for each execution.

## Validate without disclosure

Run preflight from the trusted host administrator account. Use `sudo` when the
operator account cannot read the runtime-owned `0400` checker configuration or
access the Docker socket; the script never opens application secret files.

The configuration-only check renders Compose and validates fixed topology,
digest identities, Flow/AWS profile and the hosted checker selectors plus
declared cache-identity shape needed by this topology. The application and
checker startup owners validate their complete settings and config schemas,
including the canonical AWS evidence fields described above. This check does not inspect host ownership, Docker, cache or any external
service:

```sh
python3 deploy/hosted/preflight.py \
  --env-file /etc/workstream/release.env \
  --configuration-only
```

The full preflight additionally checks secret/config metadata without reading
secret contents, validates the private directories and Docker-socket group, and
requires locally registered runsc plus every exact cached image at that point in
time. It also checks the private intake socket and calls the production typed
intake health adapter from the pinned backend image with no secrets or network.
Wrong runtime, image/config or default behavior rejects launch:

```sh
python3 deploy/hosted/preflight.py --env-file /etc/workstream/release.env
```

Preflight cannot attest the active AWS identity, absence of extra IAM
permissions, Flow token acceptance, a successful VM boot, collector delivery,
backup recoverability or a live checker result. Issue #582 and PR #592 own the
AWS release identity, exact role/policy and bucket-policy proof contract. This
configuration carries those values into every long-running process environment
for canonical startup validation. Rendered values and valid formats do not prove
the underlying cloud facts or completed proof-job execution.

## Start and inspect

Use the checked-in wrapper for every Compose operation. It parses and validates
the approved environment file, renders the fixed topology, and gives Docker
Compose only that parsed allowlist plus fixed process path, operator home and
local Docker-socket values. Ambient shell values cannot replace an image, Flow
URL, secret path, Compose selector or Docker daemon selector. Every `up` also
reloads the current checker configuration and repeats the checker-selector,
private-host-input, Docker-runtime/cache and typed intake readiness checks before starting anything.
Skipping the separate preflight does not skip these launch checks. `pull`, `ps`
and `stop` remain available without launch-only checks so an invalid host can
still be inspected or stopped. Run `up` from the same trusted administrator
account used for full preflight. Keep the private configuration and host inputs
unchanged between validation and launch and while the service runs; these
point-in-time checks do not constrain a trusted host administrator:

```sh
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env pull
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  up --detach --wait
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env ps
```

The API applies forward migrations before serving. The guide parser must pass
its protocol health check before the worker starts. Worker startup uses the
existing prefork lifecycle. Beat runs the existing recovery and cleanup
schedules. The checker health check requires its private socket and Docker's
registered runsc runtime. It does not attest cache identity; full preflight
observes the cache once, and the canonical runner verifies the exact image again
for each execution. API health checks a lightweight endpoint; the worker and
Beat health checks verify their local Celery processes. These checks do not
replace a public authenticated journey or dependency-specific provider probes.
Each process stops after five consecutive failed restarts so an invalid release
cannot remain in an unbounded crash loop.

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
then stops the parser and checker controller. Keeping both socket services alive
while the worker drains lets cancellation and terminal persistence finish against
their original dependencies. Guide inference has a 7,260-second process backstop;
the shared Redis transport uses a 7,380-second visibility timeout with prefetch
disabled. The persisted guide-attempt deadline remains the ordinary, shorter
execution bound. Celery task hard limits and durable database/outbox custody
remain owned by the application.

```sh
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env stop
```

For a restart or upgrade, preserve scratch until cleanup/recovery has classified
all retained work, update only reviewed digest identities/configuration, rerun
full preflight, pull, and start with `up --detach --wait`. Exercise an interrupted
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

Use the approved PostgreSQL provider's consistent backup/snapshot facility and
the AWS retention/versioning controls established by #582. Redis carries queue
transport, not Workstream lifecycle truth; recovery scanners rebuild eligible
delivery from PostgreSQL owners. Never treat a Redis snapshot as the record
backup and never delete retained S3 objects during database recovery.

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

The exact provider commands and completed restore observations belong to the
approved environment evidence. They are intentionally absent here because no
database, account or backup system has been authorized for this configuration
change.

## Remaining release evidence

Before #583 or parent #555 can claim a hosted release, retain evidence for real
Flow human/service identities, AWS custody and negative identity cases, selected
registry/LIVE controls, actual project checker images, gVisor isolation,
representative CPU/memory/PID/disk/time measurements, missing-cache and limit
classification, collector outage, drain/restart, supported recovery and isolated
backup restore. Bind that evidence to exact source, service-image, checker-image,
configuration and corpus identities.
