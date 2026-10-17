# Local Pilot Stack

This guide starts the Workstream API, a prefork Celery worker, Celery beat,
PostgreSQL, Redis and MinIO for local pilot work. It uses the existing
`ArtifactStore`, Flow-token verifier, trust-root bootstrap and grant APIs. It
does not add a Workstream login, approve a guide, or provide the runner/model
proxy and complete contributor journey.

The tested host path is Docker Engine on Linux x86_64. Docker Desktop is the
supported macOS path because these images select the Docker VM's Linux
architecture. This change was not run on a macOS host, so file sharing,
Docker Desktop resource limits, sleep/resume and both Apple Silicon and Intel
startup remain unverified here.

## Configure one checkout

Install Docker Compose v2, `curl`, `jq` and OpenSSL. From the repository root:

```bash
cp .env.example .env
chmod 600 .env
```

Those are POSIX-shell commands. In Windows PowerShell, use `Copy-Item` and a
private NTFS ACL for the current user instead of `chmod`. `.env` is ignored.
Edit it before startup:

- give `COMPOSE_PROJECT_NAME` a unique lowercase name such as
  `ws-pilot-alex-api`;
- select unused loopback ports for API, PostgreSQL, Redis, MinIO API and MinIO
  console;
- set `LOCAL_UID` and `LOCAL_GID` to the host values from `id -u` and `id -g`;
  `LOCAL_UID` must be nonzero, so a root-run shell must instead supply the
  intended non-root developer UID;
- replace the PostgreSQL and MinIO values with checkout-local secrets;
- keep the password embedded in `WORKSTREAM_DATABASE_URL` identical to
  `WORKSTREAM_POSTGRES_PASSWORD` (use a URL-safe value);
- generate independent 32-byte Base64 secrets with `openssl rand -base64 32`
  for the API rate-limit and pagination keys;
- generate a separate local Flow HMAC secret with `openssl rand -hex 32`.

Set `OPENAI_API_KEY` only when running genuine guide compilation. Keep the
real key in this ignored file. Without it, the six services and artifact
upload can run, but provider-backed guide setup cannot complete successfully.

Compose rejects a missing project name or required secret instead of silently
sharing defaults. All published ports bind to `127.0.0.1`. Containers use the
internal names `postgres:5432`, `redis:6379` and `minio:9000`; host-port changes
do not alter service-to-service URLs.

## Start and inspect the six services

```bash
docker compose --profile backend up --build --wait
docker compose --profile backend ps
docker compose --profile backend exec -T worker celery -A app.workers.celery_app inspect ping
docker compose --profile backend exec -T backend python scripts/ensure_local_minio_bucket.py
```

`ps` must show `backend`, the Celery service, `beat`, `postgres`, `redis` and `minio`
healthy. The Celery command must report `pong`. The bucket command must report
the configured bucket as ready. API, Celery process and beat receive the same
`s3_compatible` MinIO configuration and share the Compose-project scratch
volume; only the API performs idempotent bucket provisioning before startup.

Resolve the configured client endpoints without assuming default ports:

```bash
API_URL="http://$(docker compose --profile backend port backend 8000)"
MINIO_URL="http://$(docker compose --profile backend port minio 9000)"
MINIO_CONSOLE_URL="http://$(docker compose --profile backend port minio 9001)"
curl --fail --silent --show-error "$API_URL/api/v1/health"
curl --fail --silent --show-error "$MINIO_URL/minio/health/ready"
```

Inspect `docker compose --profile backend logs backend worker beat` if startup fails. A disabled
artifact backend is intentionally incompatible with this stack's retained
MinIO settings. This probe must exit nonzero before constructing an adapter and
report that static artifact credentials require MinIO storage:

```bash
docker compose --profile backend run --rm --no-deps -e WORKSTREAM_ARTIFACT_STORE_BACKEND=disabled worker \
  python -c \
  'from app.adapters.artifacts import artifact_provider_activation_guard, create_artifact_store_bootstrap; from app.core.config import get_settings; settings = get_settings(); create_artifact_store_bootstrap(settings, activation_guard=artifact_provider_activation_guard(settings))'
```

## Create distinct identities and grant authority

The helper signs short-lived tokens using the exact local Flow-HMAC settings
already consumed by `FlowAuthVerifier`. It always emits empty role claims;
tokens identify actors but do not grant authority.

Keep shell tracing disabled while tokens are in scope. The request helper writes
each Authorization header to a mode-600 temporary file, gives `curl` only the
file path, removes the file after success or failure and returns `curl`'s exact
status.

```bash
set +x
set -o pipefail

curl_with_token() {
  local token="$1" header_file curl_status
  shift
  header_file="$(mktemp "${TMPDIR:-/tmp}/workstream-auth.XXXXXXXX")" || return
  trap 'rm -f "$header_file"' HUP INT TERM
  chmod 600 "$header_file" || {
    curl_status=$?
    rm -f "$header_file"
    trap - HUP INT TERM
    return "$curl_status"
  }
  printf 'Authorization: Bearer %s\n' "$token" >"$header_file" || {
    curl_status=$?
    rm -f "$header_file"
    trap - HUP INT TERM
    return "$curl_status"
  }
  if curl --header "@$header_file" "$@"; then
    curl_status=0
  else
    curl_status=$?
  fi
  rm -f "$header_file"
  trap - HUP INT TERM
  return "$curl_status"
}

ADMIN_TOKEN="$(docker compose --profile backend exec -T backend python scripts/issue_local_flow_token.py --subject pilot-access-admin)"
MANAGER_TOKEN="$(docker compose --profile backend exec -T backend python scripts/issue_local_flow_token.py --subject pilot-project-manager)"
CONTRIBUTOR_ONE_TOKEN="$(docker compose --profile backend exec -T backend python scripts/issue_local_flow_token.py --subject pilot-contributor-one)"
CONTRIBUTOR_TWO_TOKEN="$(docker compose --profile backend exec -T backend python scripts/issue_local_flow_token.py --subject pilot-contributor-two)"
FINANCE_TOKEN="$(docker compose --profile backend exec -T backend python scripts/issue_local_flow_token.py --subject pilot-finance)"
```

Create each actor profile through the public identity boundary and retain only
the returned IDs in the shell:

```bash
actor_id() {
  curl_with_token "$1" --fail --silent --show-error \
    "$API_URL/api/v1/actors/me" | jq -r .actor_profile_id
}
ADMIN_ID="$(actor_id "$ADMIN_TOKEN")"
MANAGER_ID="$(actor_id "$MANAGER_TOKEN")"
CONTRIBUTOR_ONE_ID="$(actor_id "$CONTRIBUTOR_ONE_TOKEN")"
CONTRIBUTOR_TWO_ID="$(actor_id "$CONTRIBUTOR_TWO_TOKEN")"
FINANCE_ID="$(actor_id "$FINANCE_TOKEN")"
```

The first Access Administrator transition is irreversible. Run it once on a
new database using the existing bootstrap operation:

```bash
docker compose --profile backend exec -T backend python scripts/bootstrap_access_administrator.py \
  --actor-profile-id "$ADMIN_ID" --execute
```

Issue the Project Manager and Finance grants through the authorized API. The
token claims remain empty:

```bash
new_key() { docker compose --profile backend exec -T backend python -c 'import uuid; print(uuid.uuid4())'; }
curl_with_token "$ADMIN_TOKEN" --fail --silent --show-error -X POST \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -d "{\"target_actor_profile_id\":\"$MANAGER_ID\",\"role\":\"project_manager\",\"scope_type\":\"system\",\"reason\":\"Local pilot project administration\"}" \
  "$API_URL/api/v1/admin-role-grants" | jq
curl_with_token "$ADMIN_TOKEN" --fail --silent --show-error -X POST \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -d "{\"target_actor_profile_id\":\"$FINANCE_ID\",\"role\":\"finance_authority\",\"scope_type\":\"system\",\"reason\":\"Local pilot finance administration\"}" \
  "$API_URL/api/v1/admin-role-grants" | jq
```

Provision the fixed service identities required by the existing guide artifact
and setup operations. This is also an authorized API operation:

```bash
for identity in \
  artifact.put_resolver \
  artifact.verifier \
  artifact.scheduler \
  artifact.binding \
  artifact.guide_reader \
  project.setup; do
  curl_with_token "$ADMIN_TOKEN" --fail --silent --show-error -X POST \
    -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
    -d "{\"service_identity\":\"workstream.$identity\",\"subject\":\"local-pilot-$identity\",\"reason\":\"Local pilot durable guide setup\"}" \
    "$API_URL/api/v1/service-actors" | jq
done
```

## Create a draft project and scoped contributor grants

Create two draft projects. The first is the guide-upload target; the second is
an authorization isolation control:

```bash
PROJECT="$(curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X POST \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -d '{"name":"Local pilot","slug":"local-pilot","description":"Checkout-local pilot evidence"}' \
  "$API_URL/api/v1/projects")"
PROJECT_ID="$(jq -r .id <<<"$PROJECT")"

OTHER_PROJECT="$(curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X POST \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -d '{"name":"Local pilot isolation","slug":"local-pilot-isolation","description":"Cross-project denial control"}' \
  "$API_URL/api/v1/projects")"
OTHER_PROJECT_ID="$(jq -r .id <<<"$OTHER_PROJECT")"
```

Grant each contributor the existing project-scoped `submitter` role. The
qualification snapshot records that this local seed has no external skill or
reputation records; it does not fabricate evidence:

```bash
grant_submitter() {
  curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X POST \
    -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
    -d "{\"target_actor_profile_id\":\"$1\",\"role\":\"submitter\",\"qualification\":{\"skills_snapshot\":{\"availability\":\"unavailable\",\"reference_ids\":[],\"unavailable_reason\":\"no_record\"},\"reputation_snapshot\":{\"availability\":\"unavailable\",\"reference_ids\":[],\"unavailable_reason\":\"no_record\"},\"prior_project_work_refs\":[],\"external_expertise_refs\":[]},\"reason\":\"Local pilot contributor\"}" \
    "$API_URL/api/v1/projects/$PROJECT_ID/role-grants" | jq
}
grant_submitter "$CONTRIBUTOR_ONE_ID"
grant_submitter "$CONTRIBUTOR_TWO_ID"
```

Both contributors can read the granted project and are concealed from the
ungranted project:

```bash
curl_with_token "$CONTRIBUTOR_ONE_TOKEN" --fail --silent --show-error \
  "$API_URL/api/v1/projects/$PROJECT_ID" | jq -e ".id == \"$PROJECT_ID\""
test "$(curl_with_token "$CONTRIBUTOR_ONE_TOKEN" --silent --output /dev/null --write-out '%{http_code}' \
  "$API_URL/api/v1/projects/$OTHER_PROJECT_ID")" = 404
```

Task release denial needs a real task under an activated guide. This base stack
does not fabricate an approved guide or task merely to satisfy that check; run
that negative case when the genuine guide below has passed the existing
approval/activation operations.

## Declare and upload a real guide document

Set `GUIDE_PDF` to a real bounded PDF. The document stays a draft source; this
flow does not approve or activate it.

```bash
GUIDE_PDF=/absolute/path/to/project-guide.pdf
test -f "$GUIDE_PDF"
GUIDE="$(curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X POST \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -d "{\"version\":\"initial\",\"change_summary\":\"Initial local pilot source\",\"task_examples\":[{\"title\":\"Pilot contribution\",\"labels\":[\"pilot\"],\"content\":\"Complete the assigned pilot work and return the required evidence.\"}],\"documents\":[{\"label\":\"$(basename "$GUIDE_PDF")\",\"media_type\":\"application/pdf\"}]}" \
  "$API_URL/api/v1/projects/$PROJECT_ID/guides")"
GUIDE_ID="$(jq -r .id <<<"$GUIDE")"
DOCUMENT_ID="$(jq -r '.documents[0].document_id' <<<"$GUIDE")"

curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X POST \
  -H "Content-Type: application/pdf" -H "Idempotency-Key: $(new_key)" \
  --data-binary "@$GUIDE_PDF" \
  "$API_URL/api/v1/projects/$PROJECT_ID/guides/$GUIDE_ID/documents/$DOCUMENT_ID/content" | jq
```

The upload is complete only when the response and Celery logs show the stored
object was verified through MinIO. Inspect the durable setup state rather than
assuming checker/provider success:

```bash
curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error \
  "$API_URL/api/v1/projects/$PROJECT_ID/guides/$GUIDE_ID/setup-runs/latest" | jq
docker compose --profile backend logs --since 10m worker beat
```

With a valid `OPENAI_API_KEY`, poll that endpoint until `finished_at` is set and
confirm `output_sufficiency_report_id` is non-null. A failure or unresolved
provider outcome is evidence to diagnose, not acceptance. Restart the Celery process
during a pending run and observe the same setup ID afterward to exercise the
existing recovery scans:

Without a provider key, the real Celery process records the durable setup and
compilation reservation, then stops before dispatch. The latest setup can
therefore remain `compilation_reserved` with no sufficiency report; preserving
the same setup ID across restart proves recovery identity, not successful model
compilation.

```bash
docker compose --profile backend kill -s KILL worker
docker compose --profile backend up -d --wait worker
curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error \
  "$API_URL/api/v1/projects/$PROJECT_ID/guides/$GUIDE_ID/setup-runs/latest" | jq
```

Exercise scheduler recovery separately. A forced beat restart must become
healthy again and continue using the same project-scoped schedule volume. The
schedule is durable, while the process PID file is container-local so a killed
container cannot strand a reusable PID in the volume:

```bash
docker compose --profile backend kill -s KILL beat
docker compose --profile backend up -d --wait beat
docker compose --profile backend ps beat
docker compose --profile backend logs --since 2m beat
```

## Prove two stacks do not interfere

Use two checkouts, each with a different `.env` project name, five different
host ports and its own secrets. In each checkout run:

```bash
docker compose --profile backend up --build --wait
docker compose --profile backend ps
```

Create a different project in each stack, then record the project IDs and
container/volume names:

```bash
PROJECT_NAME="$(docker compose --profile backend config --format json | jq -er '.name')"
docker compose --profile backend ps --format '{{.Name}}'
docker volume ls --filter "label=com.docker.compose.project=$PROJECT_NAME" --format '{{.Name}}'
```

From the first checkout, stop only its project without deleting volumes:

```bash
docker compose --profile backend down
```

In the second checkout, all six services must remain healthy, its project must
still be readable, and its bucket must still be present:

```bash
docker compose --profile backend ps
curl --fail --silent --show-error "$API_URL/api/v1/health"
docker compose --profile backend exec -T backend python scripts/ensure_local_minio_bucket.py
```

Never use `docker compose --profile backend down` without first confirming the checkout's
`COMPOSE_PROJECT_NAME`. Do not use `docker system prune`, `docker volume prune`,
or remove another checkout's containers or volumes.

## Stop, retain or dispose

Normal shutdown retains PostgreSQL, Redis, MinIO and scratch data for the exact
Compose project:

```bash
docker compose --profile backend down
```

`docker compose --profile backend up --wait` later reuses those named volumes. To delete all data
owned by this exact local project, first print and verify the project name and
resources, then remove its containers and named volumes:

```bash
PROJECT_NAME="$(docker compose --profile backend config --format json | jq -er '.name')"
printf 'Compose project: %s\n' "$PROJECT_NAME"
docker compose --profile backend ps -a
docker volume ls --filter "label=com.docker.compose.project=$PROJECT_NAME" --format '{{.Name}}'
docker compose --profile backend down --volumes
```

That final command permanently removes this project's database, broker state,
MinIO objects and processing scratch. It does not remove other Compose projects
when the project name is unique.
