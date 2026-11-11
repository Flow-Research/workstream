# Clean single-host installation

Use this path for a new deployment with PostgreSQL and Redis on the application
host. Both services are required; managed services remain an alternative to the
local overlay. This procedure does not reset an existing installation or import
demo accounts. A successful installation still needs the journey checks below.

## Host and release preparation

Use a dedicated Linux amd64 host with working KVM and cgroup v2 delegation for
[the native Smol node](../../external_checkers/README.md#smol-microvm-engine).
The proposed MVP target is 2 vCPU, 8 GiB RAM and 100 GiB encrypted persistent
storage. This is a qualification target, not a published capacity guarantee.
Enable nested virtualization on a supported instance type before boot and verify
`/dev/kvm` on the actual host. Start with one Celery process and one native
execution slot; preserve the node's measured memory and disk limits.

For EC2, associate a tagged Elastic IP with the instance and retain its allocation
identity. Point the identity hostname at that address. Open SSH only to the
operator's current address, and HTTP/HTTPS for the reviewed TLS ingress. Never
publish PostgreSQL, Redis, native sockets or the Docker daemon. Do not replace
an uncertain cloud create with another create: inspect the recorded request and
resource IDs first.

Build and publish images on a builder, not this host. Follow the
[release image instructions](README.md#prepare-source-images), recording reviewed
source, registry digests and native asset hashes. Install Docker Engine and its
Compose plugin, Python 3, and the reviewed native assets. Copy this directory
from that same reviewed checkout. Use one Compose project name for the deployment.

Authenticate the deployment operator to the approved image registry before
Compose pulls. For private ECR, obtain a short-lived login token through that
operator's AWS identity and pass it to Docker through private stdin. Use a
root-owned private Docker configuration directory, remove its registry token
when deployment operations finish, and refresh it before later pulls. Do not put
provisioning access keys in application containers or copy them onto the host.
Normal Docker container restart uses the already installed image; an explicit
Compose reconciliation can pull and needs valid registry authentication again.

Configure Docker's `local` logging driver with `max-size=10m` and `max-file=3`
before creating containers. Preserve any other required daemon settings; validate
the configuration before restarting Docker. Bound systemd journal retention too.
Do not keep a build daemon or development registry on the application host.
Inspect disk with `df`, `docker system df` and owner-scoped directory sizes.
Remove only explicitly identified retired images and owned temporary files after
checking running containers and recovery evidence. Never use volume pruning as
an upgrade or scratch-cleanup procedure.

## Initialize private backing services

Copy [release.env.example](release.env.example) to a root-owned private
`/etc/workstream/release.env` and fill the canonical release configuration.
Choose reviewed digest-qualified PostgreSQL 16 bookworm and Redis 7 bookworm
images whose service identity is `999:999`. Do not substitute an Alpine image
with a different numeric identity.

On a fresh host:

```sh
sudo python3 deploy/hosted/initialize-local-data.py
```

The command creates `/var/lib/workstream-local-data` and prints only file paths.
It refuses an existing directory, including an incomplete previous attempt.
Inspect failures explicitly; rerunning must never rotate live credentials.
The PostgreSQL bootstrap administrator password is separate from the non-superuser
Workstream database account. Redis requires its own generated password. Secrets
are private files, not values to paste into the release environment or logs.

Set the seven printed `WORKSTREAM_*` file/directory entries in the release file,
plus `WORKSTREAM_POSTGRES_IMAGE` and `WORKSTREAM_REDIS_IMAGE`. The database and
broker URL files are consumed by the existing application secret loader.
No database or broker port is published. Keep persistent backing data outside
`WORKSTREAM_DEPLOYMENT_ROOT`, which is reserved for runtime scratch and sockets.

Generate the API rate-limit and pagination HMAC secrets independently as 32
random bytes encoded in canonical padded Base64, not hexadecimal. Write each
directly to its configured private secret file without printing it. Preserve
these keys on restart; do not regenerate them during deployment reconciliation.
The application validates their encoding before migration or startup.

After completing the release environment, initialize only the backing services:

```sh
sudo python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env start local-data
```

This waits for their health checks without starting API, workers, identity or the
native node. Health alone does not prove application database access; the next
migration step exercises the non-superuser connection.

## Identity, storage and application activation

Initialize fresh accounts through the independent
[Rust identity issuer](../../experiments/demo_identity/README.md#initialize-and-run).
Follow its private-stdin password procedure and persistent account/signing-key
ownership. An issuer administrator is not a Workstream administrator. Bootstrap
Workstream authority using its existing supported operator command, not database
edits or saved fixture tokens.

Configure the issuer's trusted HTTPS origin and JWKS URL. Use the existing
[Caddy deployment instructions](../../experiments/demo_identity/README.md#hosted-https-and-cutover).
Public participant access requires DNS and a trusted public certificate. The
documented private access profile remains suitable only for authorized operators;
never disable TLS verification to bypass missing DNS.

Prepare the existing scoped AWS identities, certificate files and S3 configuration
using the [AWS runbook](../../docs/operations_aws_roles_anywhere.md). Retain the
bucket and its immutable objects during a compute rebuild. Install the native
node configuration, pinned cache and systemd unit using the canonical node
instructions. Keep private credentials out of the checker guests.

Follow the [ordered activation commands](README.md#start-and-inspect): migrate,
run a fresh fixed AWS proof, start the model proxy when enabled, start the native
unit, run full preflight, then start the application. Start identity through its
existing fixed bootstrap command before any step requiring token verification.
The AWS proof and native readiness are required for this exact release; results
from a retired deployment are not interchangeable.

After the API is healthy, complete admission and authorization bootstrap:

Log in to the issuer, then call `GET /api/v1/actors/me` with that access token to
admit the initial human actor. Use the returned actor ID with
[`bootstrap_access_administrator.py`](../../backend/scripts/bootstrap_access_administrator.py),
first with `--dry-run`, then `--execute`, in the configured API image with its
normal private database secret. Provision the journey's fixed service identities
through `POST /api/v1/service-actors` under that administrator's fresh access
token. The identity list in
[`provision_local_service_actors.py`](../../backend/scripts/provision_local_service_actors.py)
is a reference; that local-development script's token issuer is not the hosted
Rust login path. Do not import its fixture tokens into this installation.


For this continuously running AWS deployment, install and enable the
[five-minute proof renewal timer](../../docs/operations_aws_roles_anywhere.md)
before exercising uploads. Verify its first group completed successfully. A
one-time activation expires after 15 minutes; healthy application containers do
not keep it valid. The recurring proof uses the exact cached release image and
does not need a retained registry login. Preserve the fail-closed expiry guard
and inspect failed renewal receipts instead of extending evidence validity.

Install the [host boot recovery unit](README.md#reconcile-an-installed-host-after-reboot)
after initial activation. Set its checkout path to this installed release and
enable it for subsequent boots. It restores prerequisite readiness and reconnects
MCP to the current API namespace using cached images; it does not migrate or
initialize account/database state. Docker restart policies alone do not establish
this host-level startup order.

## Qualification, restart and retirement

With fresh participant logins, exercise API, CLI and the configured private MCP
service. Prove claim, malformed ZIP feedback with no Submission, valid upload,
verified S3 custody, external POST, governed acceptance, ContributionRecord,
applicable award and exact replay. Check denied identities and infrastructure
recovery separately. Record source/image/configuration identities and bounded
results without participant tokens or document contents. Keep participant passwords
in a private persistent operator credential store; temporary `/run` files are
suitable for short-lived tokens, not the only copy of account credentials.

Measure peak memory, filesystem use and scratch cleanup during this actual
journey. Confirm the database role is not superuser and cannot create roles or
databases. Verify Redis rejects unauthenticated access. Drain through the hosted
wrapper: backing services stop after their consumers. Restart backing services
first, then repeat the canonical readiness/start order. Confirm accounts,
contribution facts and pending recoverable work survive; never reinitialize state.

The [backup/restore requirements](README.md#backup-and-restore-proof) apply to
retained work. An explicitly disposable test environment can be retired without
preserving its database only with its owner's authorization. Identify the exact
instance, volume and deployment directories before deletion; retain unrelated
resources, S3 objects and the stable address needed by the replacement. Confirm
old billable compute is terminated after the replacement is qualified.

The [single-host qualification report](../../docs/reports/mvp-single-host-2026-11-11.md)
records the bounded private demo and restart proof, including its limits.
