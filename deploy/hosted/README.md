# Hosted Release Configuration

This directory contains the first bounded release composition for the Workstream
API, durable Celery worker, Beat scheduler and existing Rust external-checker
service. It targets one dedicated Linux runner host with Docker and gVisor
`runsc`. PostgreSQL, Redis, AWS S3, Flow identity and the optional OTLP collector
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
/run/workstream-checker/checker.sock
```

Do not replace either path with a named volume or another in-container path.

## Prepare source images

Builds are separate from release execution. Build the reviewed source, publish
each image to the approved registry, record its repository digest, then put only
the resulting `repository@sha256:...` identity in the release environment.
Compose never builds and rejects tags.

```sh
docker build --file docker/backend/Dockerfile.release \
  --tag registry.example/workstream/backend:<source-commit> .
docker build --file docker/checker/Dockerfile.release \
  --tag registry.example/workstream/checker-service:<source-commit> .
```

Both Dockerfiles pin their base images. The backend build installs the committed
Python resolution with the agent runtime and without the development extra. The
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
operation remains separate evidence. An unconditional workflow cleanup verifies
that no smoke container owned by that run remains after inspection or timeout.

## Prepare the host

Install and configure Docker and gVisor using the approved host process. Confirm
that Docker reports a `runsc` runtime. Installation and daemon configuration are
outside this repository configuration.

Choose one nonzero runtime UID/GID and find the Docker socket GID. Create the
fixed private directories with that runtime identity:

```sh
sudo install -d -m 0700 -o 10001 -g 10001 /var/lib/workstream/scratch
sudo install -d -m 0700 -o 10001 -g 10001 /run/workstream-checker
stat -c '%g' /var/run/docker.sock
```

Copy `release.env.example` to an operator-owned non-secret environment file and
replace every example identity. The file contains paths and public configuration,
not secret values. Select real Flow issuer, audience, JWKS and algorithm values.
The release profile uses `WORKSTREAM_AUTH_PROVIDER=flow`; local Flow-HMAC and
development authentication are absent.

Create each secret as a one-value regular file at the configured path. Make it
owned by the runtime UID/GID with mode `0400`. The explicit role loader gives the
API only the database, broker, rate-limit and pagination secrets; the worker
gets the database, broker and OpenAI secrets because it hosts setup jobs; Beat
gets only the broker secret. An absent required selector or unknown role stops
startup, and an unrelated secret is neither mounted nor loaded. The loader
independently requires the running identity and mode `0400`, performs no shell
evaluation and never prints a value. Do not put AWS static keys in these files:
the runtime uses the selected AWS workload identity. This first single-host
profile requires the dedicated host's IAM role; web-identity token and
container-role transports need a different reviewed topology and fail this
preflight.

Set the immutable release digest and every exact AWS role, managed-policy,
trust-policy and bucket-policy identity from the approved release evidence. The release wrapper allowlists these eleven non-secret values
and the shared Compose environment passes them unchanged to API, worker and Beat.
The integrated canonical application `Settings` from #582/PR #592 defines
these fields and validates their format and relationships. That owner rejects a malformed digest or ARN, a mixed AWS partition/account, reused
workload roles or trust-policy digests, or reused managed policies when any of
those processes starts. Preflight checks presence and rendered custody only so
it does not create a second IAM-policy validator.

The #582 proof command will load this exact Settings contract after its owner is
merged. Its readiness, runtime-immutability and negative-access modes require
distinct active IAM identities, so they must not be run through the long-lived
API, worker or Beat identity. The dedicated proof-job profile is pending the
stable #493 integration; this release configuration does not invent an interim
Compose service or claim that the three proof modes have run.

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
time:

```sh
python3 deploy/hosted/preflight.py --env-file /etc/workstream/release.env
```

Preflight cannot attest the active AWS identity, absence of extra IAM
permissions, Flow token acceptance, external service health, collector delivery,
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
private-host-input and Docker-runtime/cache checks before starting anything.
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

The API applies forward migrations before serving. Worker startup uses the
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

Stop Beat first to prevent new periodic publication, stop the API to stop new
requests, then give the prefork worker its configured 3700-second graceful
window. Celery task hard limits and durable database/outbox custody remain owned
by the application.

```sh
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  stop beat api
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  stop --timeout 3700 worker
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  stop checker-service
```

For a restart or upgrade, preserve scratch until cleanup/recovery has classified
all retained work, update only reviewed digest identities/configuration, rerun
full preflight, pull, and start with `up --detach --wait`. Exercise an interrupted
job and verify the existing exact retry/reconciliation operations rather than
editing rows or replaying unknown work blindly.

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
