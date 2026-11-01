# Local Agent Loop Stack

This runbook extends the [local pilot stack](local-pilot.md) so that one
persistent Compose project has the checker, identities and lifecycle that agent
work through the existing public contributor flow needs. It adds the external
checker service, a networkless proof checker image and the operator steps that
register the checker, provision service identities, configure a
no-human-review project and activate the acceptance lifecycle.

The contributor flow cannot run until guide rules select the checker. Guide
compilation, which selects the registered checker into the locked
pre-submission and post-submission policies, is a separate decision and is a
placeholder step below.

It uses only existing public APIs and owner operations. It declares a draft
guide only to hold the review and revision policies. It does not compile,
approve or activate a guide, bypass the checker or write lifecycle facts
directly.

## What the overlay adds

`docker-compose.agent-loop.yml` is an overlay for `docker-compose.yml`:

| Service | Profile | Purpose |
|---|---|---|
| `checker-volumes-init` | `backend` | One-shot root step that makes the material and socket volume roots private (`0700`) and owned by `LOCAL_UID:LOCAL_GID` |
| `checker-registry` | `agent-loop` | Loopback-only OCI registry, so the daemon records a platform-manifest digest |
| `checker` | `agent-loop` | The existing Rust checker service (`docker/checker/Dockerfile.release`) in `docker-dev` isolation with the `runc` runtime |

The overlay also gives the API, Celery worker and beat services two shared
named volumes:

- **Material root.** The volume `<project>-checker-material` is mounted at its
  own Docker daemon path, `/var/lib/docker/volumes/<project>-checker-material/_data`,
  in the API, Celery worker, beat and checker containers. The checker starts each
  checker image with `docker run --mount type=bind,src=<material path>`. The
  daemon resolves that source in the Docker VM (or on the Linux host), so the
  path must be identical everywhere. `WORKSTREAM_ARTIFACT_SCRATCH_ROOT` and
  `WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT` both name it, as the settings
  require. This assumes Docker's default `/var/lib/docker` data root; rootless
  Docker or a custom data root needs a different path.
- **Socket.** `WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET` is
  `/run/ws-checker/checker.sock` on a separate named volume. Do not move it to a
  host bind mount: Docker Desktop host-shared paths refuse `chmod` on Unix
  sockets, and the service sets its socket to `0600`. Socket paths must also
  stay within 107 bytes.

The checker runs as `LOCAL_UID:LOCAL_GID`, the same identity as the API and
Celery worker, because the socket is `0600` and the service requires each grant
directory to be owned by its sandbox UID. It has no network, a read-only root,
no capabilities and `no-new-privileges`. It mounts the Docker socket, which is
root-equivalent access to the daemon: use this profile only on a development
machine you control. Docker Desktop exposes the socket inside containers as
`root:root 0660`, so the default `WORKSTREAM_DOCKER_SOCKET_GID` is `0`. On a
Linux host, set it to the `docker` group ID (`getent group docker`).

Docker Desktop on Apple Silicon (including M4) can advertise OpenSSL CPU
features that crash PyCA's bundled OpenSSL with `SIGILL`. The backend
development image already sets `OPENSSL_armcap=0`, so the API, Celery worker and beat
use the generic implementation. The checker service (Rust and the Docker CLI)
and the proof checker (standard-library Python without TLS) do not load that
OpenSSL, so the overlay adds no further default.

## Configure the checkout

Follow [Configure one checkout](local-pilot.md#configure-one-checkout) first.
Then add these lines to the ignored `.env`:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.agent-loop.yml
COMPOSE_PROFILES=backend,agent-loop
WORKSTREAM_CHECKER_REGISTRY_HOST_PORT=15000
WORKSTREAM_CHECKER_CONFIG_FILE=./.local-agent-loop/checker-service.json
# Linux only: WORKSTREAM_DOCKER_SOCKET_GID=<docker group id>
```

`COMPOSE_FILE` makes every `docker compose` command in this checkout include
the overlay. Port 5000 is often taken
by macOS AirPlay, so choose an unused registry port. `.local-agent-loop/` is
ignored by Git.

## Bring up the profile

Confirm that the daemon uses the default data root, which the material path
assumes, then start the `backend` profile and the registry, but not the checker
yet. The checker service refuses to start without at least one cached image.
The `--profile backend` flag overrides `COMPOSE_PROFILES` from `.env`, so the
first `up` does not start the checker:

```bash
test "$(docker info --format '{{.DockerRootDir}}')" = /var/lib/docker
docker compose --profile backend up --build --wait
docker compose up --wait checker-registry
```

Build and publish the proof checker, then write the checker-service
configuration and the post-submission registry body. Run this on the Docker host from the
repository root:

```bash
set -a; . ./.env; set +a
python3 external_checkers/harnessy_proof/publish_local.py \
  --registry "localhost:$WORKSTREAM_CHECKER_REGISTRY_HOST_PORT" \
  --compose-project "$COMPOSE_PROJECT_NAME" \
  --sandbox-uid "$LOCAL_UID" --sandbox-gid "$LOCAL_GID" \
  --out-dir .local-agent-loop
docker compose up --build --wait checker
docker compose ps
```

The script pushes with `--provenance=false --sbom=false`, so the registry holds
one platform manifest instead of an index. It pulls that exact digest so the
daemon's `RepoDigests` contain it. `ps` must show `checker` healthy. If the
checker restarts, `docker compose logs checker` prints one bounded reason such
as `configured runtime unavailable` or `material root is not private`.

If the Docker credential helper hangs during `pull` or `push`, run the command
with an empty client configuration, for example
`DOCKER_CONFIG="$(mktemp -d)" docker compose ...`.

Rebuilding the proof checker changes its digest. The registry holds one
immutable entry per phase, capability and version, so rerun `publish_local.py`
with a new `--capability-version` (the default is `v2`; use, for example, `v3`), recreate the checker with
`docker compose up --wait --force-recreate checker`, and register the new
body. Registering a new digest under an existing version returns
`external_checker_registry_conflict`.

## Create operators and service identities

Take only `API_URL`, `curl_with_token` and `new_key` from the
[local pilot identity steps](local-pilot.md#create-distinct-identities-and-grant-authority);
do not run its bootstrap. The Access Administrator bootstrap is irreversible and
runs once per database. On a new database, run the bootstrap below once. If the
database is already bootstrapped, skip that command and use the existing
Access Administrator subject wherever this runbook says `local-access-admin`.
This runbook uses these Flow subjects:

| Subject | Role |
|---|---|
| `local-access-admin` | Access Administrator (bootstrap) |
| `local-operator` | system `operator`: checker registry and lifecycle |
| `local-manager` | system `project_manager` |
| `local-finance` | system `finance_authority` |
| `agent-claude` | project `submitter` |

Build the CLI from this checkout; an older build may lack the `operations`
commands. `ws_as` signs a short-lived token for one subject and passes it only
through the CLI's environment. A personal `workstream-local --as SUBJECT`
wrapper that does the same is equivalent:

```bash
(cd cli && go build -trimpath -o ../.local-agent-loop/workstream ./cmd/workstream)
ws_as() {
  local subject="$1"; shift
  WORKSTREAM_API_URL="$API_URL" \
  WORKSTREAM_TOKEN="$(docker compose exec -T backend python scripts/issue_local_flow_token.py --subject "$subject")" \
    ./.local-agent-loop/workstream "$@"
}
actor() { ws_as "$1" whoami -o json | jq -r .actor_profile_id; }
ADMIN_ID="$(actor local-access-admin)"
OPERATOR_ID="$(actor local-operator)"
MANAGER_ID="$(actor local-manager)"
FINANCE_ID="$(actor local-finance)"
AGENT_ID="$(actor agent-claude)"
ADMIN_TOKEN="$(docker compose exec -T backend python scripts/issue_local_flow_token.py --subject local-access-admin)"
docker compose exec -T backend python scripts/bootstrap_access_administrator.py \
  --actor-profile-id "$ADMIN_ID" --execute
grant_system_role() {
  curl_with_token "$ADMIN_TOKEN" --fail --silent --show-error -X POST \
    -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
    -d "{\"target_actor_profile_id\":\"$1\",\"role\":\"$2\",\"scope_type\":\"system\",\"reason\":\"Local agent loop\"}" \
    "$API_URL/api/v1/admin-role-grants" | jq
}
grant_system_role "$OPERATOR_ID" operator
grant_system_role "$MANAGER_ID" project_manager
grant_system_role "$FINANCE_ID" finance_authority
```

Provision the fixed service identities used by guide upload, PRE/POST checking,
routing to FinalAcceptance, assignment reconciliation and materialization. The
script calls `POST /api/v1/service-actors` with the administrator's own
authority and a stable `Idempotency-Key` per identity. A rerun reports
`provisioned` again (the exact replay), an identity created earlier under
another subject reports `existing`, and any other outcome reports
`failed:<status>:<code>` with a nonzero exit. It waits for `Retry-After` when the
administrative rate limit (30 mutations per minute by default) is reached. It
sends the administrator's token only to loopback HTTP or to HTTPS; any other
`--api-url`, such as `http://backend:8000`, exits 2 with `invalid_api_url`. The
default `http://127.0.0.1:8000` is the API inside the backend container:

```bash
docker compose exec -T backend python scripts/provision_local_service_actors.py \
  --admin-subject local-access-admin
```

## Register the proof checker

Registration needs a current system `operator` grant. The body is an
`ExternalCheckerRegistrySpec` for the post-submission phase with the exact
platform-manifest digest. The checker needs forge facts, which pre-submission
checking never has, so it is not registered for PRE. Keep the key with its file;
replaying the same key and body returns the same immutable entry:

```bash
POST_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
ws_as local-operator operations checker registry register \
  --input .local-agent-loop/registry-post.json --idempotency-key "$POST_KEY" -o json
```

The equivalent API call is
`POST /api/v1/operations/external-checker-registry` with an `Idempotency-Key`
header and the same body.

Registration publishes an immutable definition. It does not select, enable or
run the checker for any project.

### What the proof checker checks

`external_checkers/harnessy_proof/checker.py` (capability version `v2`,
[WS-GHPROOF-001](../../.commitrail/initiatives/WS-GHPROOF-001/OVERVIEW.md)) is a
post-submission checker with one mode, and it fails closed. It reads
`proof.json` at the root of the submitted ZIP, compares it with forge facts
(GitHub today) that WorkStream read from the git host, and returns
`external_checker_result.v1`. A "forge" is the git host and a "change" is its
pull or merge request. The checker has no network access and no credential.
Every failed rule is one `error` finding on `proof.json`, and the verdict is
`failed` exactly when an error finding exists. A proof never passes on its own
claims.

The POST binding configuration must select the forge facts version and name the
forge, the forge instance's web origin, the repository and the base branch. It
may set integrity options whose defaults are the safe ones:

```json
{"workstream_forge_facts_version": "v1", "forge": "github",
 "forge_origin": "https://github.com",
 "repository": "Flow-Research/harnessy-v2", "base_branch": "main"}
```

`forge` accepts only `github` today. `forge_origin` is `https://`, a host and an
optional port, with no path or trailing slash; it tells GitHub Enterprise or a
self-hosted GitLab or Forgejo instance apart from `https://github.com`.
`repository` uses a forge-neutral path grammar: two or more `/`-joined segments
of `A-Z a-z 0-9 . _ -`, none `.` or `..`, at most 255 characters, so GitLab
subgroups fit. Each forge provider enforces its own stricter grammar.

| Option | Default | Effect |
|---|---|---|
| `allow_unbound_required_checks` | `false` | When false, a required check that accepts any producer is an error |
| `protected_paths` | `[]` | Globs added to `.github/**`, `**/CODEOWNERS`, `.gitlab-ci.yml`, `.gitlab/**`, `.circleci/**`, `.forgejo/**`, `.gitea/**`, `.woodpecker/**`, `.woodpecker.yml`, `.woodpecker.yaml` |
| `required_independent_approvals` | `1` | Independent approvals needed on the head commit (1 to 10) |
| `operator_logins` | `[]` | Logins whose approval alone adds the `harnessy.operator_approved` warning |

WorkStream places the facts in the request `input` under `forge_facts`, so the
request digest binds them. Each forge provider maps its host into the same
`workstream.forge_change_facts.v1` facts; anything a provider cannot prove is
null or absent, and the checker then fails closed. The facts are bound to one
change state (`head_sha`, `landed_commit_sha`). A commit id is 40 (SHA-1) or 64
(SHA-256) lowercase hexadecimal characters:

```json
{
  "forge_facts": {
    "schema_version": "workstream.forge_change_facts.v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "Flow-Research/harnessy-v2",
    "change_number": 12,
    "change_url": "https://github.com/Flow-Research/harnessy-v2/pull/12",
    "state": "closed",
    "merged": true,
    "landed_commit_sha": "<commit id; null unless merged>",
    "base_ref": "main",
    "head_sha": "<commit id>",
    "author": {"login": "agent-bot", "id": 501, "kind": "bot"},
    "reviews": [{"id": "61", "reviewer": {"login": "reviewer", "id": 7, "kind": "user"},
                 "reviewer_write_access": true,
                 "state": "approved", "commit_id": "<head sha, or null>",
                 "submitted_at": "2026-10-24T11:00:00Z"}],
    "changed_files_count": 1,
    "changed_files": [{"path": "src/app.py", "previous_path": null, "status": "modified"}],
    "required_checks": [{"name": "backend", "conclusion": "success",
                         "required_producer": "github_app:15368",
                         "judged": [{"producer": "github_app:15368", "sha": "<head sha>"}],
                         "run_url": "https://github.com/Flow-Research/harnessy-v2/actions/runs/345"}],
    "fetched_at": "2026-10-24T12:00:00Z",
    "responses": [{"request": "pull_request", "sha256": "sha256:<64 hex>"}]
  }
}
```

Every object has exactly these keys. `change_number` is the per-repository
number (a GitLab merge request's `iid`). `landed_commit_sha` is the commit the
change landed as on the base branch, whether by merge, squash or rebase; it is
present exactly when `merged` is true, and a merged change must be `closed`.
`reviews` are in chronological order, oldest first. A review `id` is an opaque
string of 1 to 100 characters, and the checker never orders review ids.
`reviewer_write_access` says whether the reviewer currently has write (merge)
access to the repository; it is null when the forge cannot prove it. An actor
`kind` is `user`, `bot` or `other`. A review `state` is `approved`, `changes_requested`, `dismissed`,
`commented`, `pending` or `other`. `judged` lists every result the provider
judged for the check; its `producer` is null when the forge gives no producer
identity, such as a GitHub commit status.

Rules on the claims themselves (`harnessy.proof.*`): `schema` equals
`harnessy.work.proof.v1`; `commit_sha` is 40 or 64 hexadecimal characters;
`ci_conclusion` equals `success`; `merged` is the JSON value `true`. Rules
against the facts (`harnessy.proof.forge.*`):

| Code | Fails when |
|---|---|
| `configuration` | the configuration is missing, lacks a required key, names an unsupported facts version or forge, or has an invalid option |
| `facts_missing` | the input has no facts; the message names the configured repository and `forge_origin` that `pr_url` must point to |
| `facts_invalid` | the facts do not have the exact `workstream.forge_change_facts.v1` shape, including `merged` if and only if `landed_commit_sha` is set, and `merged` only when `closed` |
| `facts_binding` | a judged result names a commit other than `head_sha` |
| `repository` | the facts' forge is not `forge`, their `forge_origin` is not exactly `forge_origin`, or their repository is not `repository` (case-insensitive) |
| `base_branch` | the change's base branch is not `base_branch` |
| `change_url` | `pr_url` is not exactly the facts' `change_url` |
| `ci_run` | `ci_run_url` is not exactly the `run_url` of a required check |
| `merged` | the forge reports the change as not merged |
| `landed_commit_sha` | `commit_sha` is not the commit the change landed as (case-insensitive) |
| `required_check` | one finding per required check whose result is not `success` |
| `unbound_required_check` | a required check has no `required_producer` and `allow_unbound_required_checks` is false |
| `producer_mismatch` | a required check is bound to a producer and one of its judged results comes from another producer or from an unknown one |
| `protected_path_changed` | a changed file, or a rename's previous path, matches a protected glob; the work needs explicit human acceptance and cannot be auto-accepted |
| `independent_approval_missing` | fewer than `required_independent_approvals` reviewers approve the head commit. Each reviewer's last `approved`, `changes_requested` or `dismissed` review by list position decides. It counts only from a `user` account that is not the author (id, or login ignoring case) and whose `reviewer_write_access` is `true` |

The checker parses no URL and builds no forge URL. URL comparison is exact and
case-sensitive against the URLs the facts report, so a trailing slash, query,
fragment, port, user information, percent encoding, backslash, different case or
non-ASCII character fails. A review whose `commit_id` is null never approves.
Nor does a review whose `reviewer_write_access` is null or false, so a
contributor's second account without write access cannot supply the
independent approval.

When every qualifying approval comes from `operator_logins`, the checker adds a
non-blocking `warning` finding with code `harnessy.operator_approved`: the work
may earn points but may not be paid in money until an independent reviewer
confirms it. The verdict does not change.

**Where the facts come from.** For a POST binding that selects forge facts,
WorkStream's POST evaluation reads the claimed `pr_url` from `proof.json`,
and, when it names a change in the configured repository on the configured
`forge_origin`, reads that change's facts from the forge before running the
checker (initiative chunk 04). GitHub is read as the read-only GitHub App
configured by the `WORKSTREAM_GITHUB_APP_*` settings in `backend/.env.example`;
its web origin follows the API URL (`https://github.com` for the public API,
the Enterprise host otherwise), and a binding whose `forge_origin` differs ends
as an infrastructure failure. For reviewers who approved the head commit, the
App also reads their current repository permission, so an approval counts only
from someone with write access. A missing, oversized or malformed `proof.json`
fails with the checker's `missing`, `too_large` or `invalid_json` finding. A
claim that names another repository, a change the forge does not have, a
change into another base branch, or one with more changed files, reviews or
checks than GitHub lists (3000 files) yields no facts, and the checker fails
with `facts_missing`; so do facts too large for the 1 MiB checker input. If the forge is
unreachable, refuses the credential, cannot read the configured repository or
answers outside its protocol, or the App is not configured, the evaluation ends
as an infrastructure failure that an Operator can retry; it never passes.
There is deliberately no shape-only mode.

## Create the manager project and the agent submitter

```bash
PROJECT_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
ws_as local-manager project create --name 'Agent loop' --slug agent-loop \
  --idempotency-key "$PROJECT_KEY" -o json
```

Record the returned `id` as `PROJECT_ID`. The agent's actor profile was
created by its first `whoami` (`AGENT_ID` above). Issue its project `submitter`
grant and confirm the agent sees only that role:

```bash
jq -n --arg agent "$AGENT_ID" '{
  target_actor_profile_id: $agent, role: "submitter",
  qualification: {
    skills_snapshot: {availability: "unavailable", reference_ids: [], unavailable_reason: "no_record"},
    reputation_snapshot: {availability: "unavailable", reference_ids: [], unavailable_reason: "no_record"},
    prior_project_work_refs: [], external_expertise_refs: []},
  reason: "Local agent submitter"}' > .local-agent-loop/agent-grant.json
ws_as local-manager project role-grant issue "$PROJECT_ID" \
  --input .local-agent-loop/agent-grant.json --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
ws_as agent-claude project access "$PROJECT_ID" -o json
```

## Set review, revision and contribution policies

Review and revision policies belong to a draft guide. Declare the guide as in
the [CLI guide steps](../../cli/README.md#declare-a-guide-and-its-setup-inputs)
and record `GUIDE_ID`. Then attach the policies with the manager's token. The
first version uses `If-Match: "no-current-policy"`:

```bash
MANAGER_TOKEN="$(docker compose exec -T backend python scripts/issue_local_flow_token.py --subject local-manager)"
GUIDE_ROOT="$API_URL/api/v1/projects/$PROJECT_ID/guides/$GUIDE_ID"
curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X PUT \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -H 'If-Match: "no-current-policy"' \
  -d '{"human_review_required":false,"review_preference_window_seconds":3600,"review_lease_duration_seconds":1800,"allowed_decisions":["accept","needs_revision","reject"]}' \
  "$GUIDE_ROOT/review-policy" | jq
curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X PUT \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -H 'If-Match: "no-current-policy"' \
  -d '{"max_revision_rounds":2,"revision_deadline_hours":48,"allowed_resubmission_states":["needs_revision"]}' \
  "$GUIDE_ROOT/revision-policy" | jq
```

With `human_review_required:false`, TASK routing invokes the same authorized
FinalAcceptance operation as a human `accept` after required checks pass,
without a Review, ReviewLease or reviewer contribution. This path is not yet
drilled on this stack.

Finance publishes an UNPAID ContributionPolicy for the project. Record the
`contribution_policy_id` and `contribution_policy_version_id` from the `create`
output as `POLICY_ID` and `VERSION_ID`:

```bash
printf '{"name":"Agent loop contributions"}\n' > .local-agent-loop/policy-name.json
printf '%s\n' '{"rules":[{"contribution_type":"accepted_submission","compensation_mode":"unpaid","definitions":[]},{"contribution_type":"completed_review","compensation_mode":"unpaid","definitions":[]}]}' \
  > .local-agent-loop/policy-rules.json
ws_as local-finance project contribution-policy create "$PROJECT_ID" \
  --input .local-agent-loop/policy-name.json --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
ws_as local-finance project contribution-policy update "$PROJECT_ID" "$POLICY_ID" "$VERSION_ID" \
  --input .local-agent-loop/policy-rules.json --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
ws_as local-finance project contribution-policy publish "$PROJECT_ID" "$POLICY_ID" "$VERSION_ID" \
  --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
```

## Enable project points

Flow awards contributions in one unit, `FLOW`, shown to people as "Flow
Points". Partner communities may get separate units later. A unit is
project-scoped in Workstream, so each Flow project gets its own `FLOW` unit
with the same code; equal codes in different projects are still different
units, and Workstream does not add them together.

A `project_points` award rule needs three things for the project: the
`workstream.compensation.adapter` service actor, the project's `FLOW` unit and
an active `project_points` adapter binding. The unit and the binding have no
public route. The script below creates each one that is missing, in this order
and through the owners' authorized commands:

1. the adapter actor through `POST /api/v1/service-actors` with the Access
   Administrator's authority (the same call as `provision_local_service_actors.py`);
2. the unit through `contribution.compensation_unit.create` with the Finance
   Authority's AUTH decision;
3. the binding through `compensation.adapter_binding.create` with the same
   Finance Authority.

```bash
docker compose exec -T backend python scripts/provision_project_points.py \
  --project-id "$PROJECT_ID" --finance-actor-profile-id "$FINANCE_ID" \
  --admin-subject local-access-admin
```

The script prints one JSON line. Record `adapter_binding_id` as `BINDING_ID`:

```json
{"adapter_actor": "provisioned", "adapter_actor_id": "...", "adapter_binding_id": "...",
 "binding": "created", "project_id": "...", "result_code": "ready", "unit": "created",
 "unit_code": "FLOW"}
```

Each step commits on its own, so a rerun reports `existing` for what is already
there and changes nothing. If a step
fails, the output lists the steps that already committed; fix the cause and run
the script again. It exits 3 with `result_code: unavailable` when the adapter
actor is missing and `--admin-subject` is absent, or when the Finance actor
does not have exactly one active identity link. An AUTH denial (for example, an
actor without a Finance Authority grant covering the project) exits 1 with
`error_type`; the failed step creates nothing, and an adapter actor provisioned
earlier in the run stays. An active binding with another adapter actor or route
key exits 3 with `active_binding_mismatch`. The script refuses to run when
`WORKSTREAM_ENVIRONMENT` is production-like (`staging`, `preview`, `prod`,
`production`). `--unit-code` and `--route-key`
(default `flow_points.local`) override the defaults. Like the lifecycle script,
it does not authenticate its caller and is a local operator tool only.

A compensated policy then names the unit and binding. For example, 10 Flow
Points for an accepted submission and 3 for a completed review:

```bash
jq -n --arg binding "$BINDING_ID" '{rules:[
  {contribution_type:"accepted_submission",compensation_mode:"compensated",
   definitions:[{instrument_type:"project_points",unit_code:"FLOW",quantity:"10",adapter_binding_id:$binding}]},
  {contribution_type:"completed_review",compensation_mode:"compensated",
   definitions:[{instrument_type:"project_points",unit_code:"FLOW",quantity:"3",adapter_binding_id:$binding}]}]}' \
  > .local-agent-loop/policy-rules.json
```

Create, update and publish it with the Finance commands above. Guide activation
locks the selected policy version, so new tasks award points only after a guide
version that selects the new published policy is activated.

## Placeholder: compile, approve and activate the guide rules

> **Not covered here.** Selecting `harnessy.work_proof` into the locked
> post-submission policy is guide compilation, followed by the manager's
> separate PRE and POST approvals and guide activation. How rule
> setup works for this stack is being decided separately. Until it is, no task
> can be created for the project, and the contributor flow below cannot run.
> Provider-backed compilation needs `OPENROUTER_API_KEY` (for the default OpenRouter provider); see the
> [local pilot guide upload](local-pilot.md#declare-and-upload-a-real-guide-document)
> and the [CLI approval steps](../../cli/README.md#approve-an-exact-pre-submission-proposal).

## Move the acceptance lifecycle from shadow to live

Automatic FinalAcceptance commits new effects only while the joint review
lifecycle is `live`. A new database starts `disabled`. The script runs the owner
`JointLifecycleController` with the operator's own AUTH decision, one committed
transition per step (`disabled -> shadow -> live`). Rerunning at the target
phase prints `unchanged` without making an AUTH decision, because nothing
changes:

```bash
docker compose exec -T backend python scripts/transition_review_lifecycle.py \
  --actor-profile-id "$OPERATOR_ID" --phase shadow
docker compose exec -T backend python scripts/transition_review_lifecycle.py \
  --actor-profile-id "$OPERATOR_ID" --phase live
```

The script does not authenticate its caller. Anyone who can run
`docker compose exec backend` already holds the database credentials, so naming
an operator's profile ID is acceptable only on this local stack; AUTH still
requires that operator's current grant. Going live is refused while any
retained FinalAcceptance lacks a valid routing receipt. Leaving `live` uses the
owner's draining path and is not part of this script.

## Contributor flow for the agent

After guide activation and task release, the agent works as `agent-claude`.
`TASK_ID`, `ASSIGNMENT_ID`, `READY_ADMISSION_ID` and `SUBMISSION_ID` come from
the preceding outputs:

```bash
CLAIM_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
START_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
PREPARE_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
ws_as agent-claude task ready "$PROJECT_ID" -o json
ws_as agent-claude task claim TASK_ID --idempotency-key "$CLAIM_KEY" -o json
ws_as agent-claude task start TASK_ID --idempotency-key "$START_KEY" -o json
ws_as agent-claude task requirements TASK_ID -o json
# work.zip contains proof.json at its root, plus whatever the guide requires
ws_as agent-claude task prepare TASK_ID --assignment ASSIGNMENT_ID \
  --file work.zip --idempotency-key "$PREPARE_KEY" --summary 'Completed work'
ws_as agent-claude task submit TASK_ID --assignment ASSIGNMENT_ID \
  --admission READY_ADMISSION_ID --summary 'Completed work'
ws_as agent-claude submission findings SUBMISSION_ID -o json
ws_as agent-claude contributions --project "$PROJECT_ID" -o json
```

Keep each key with its command. A pending preparation is repeated with the same
command, key and bytes. The [CLI contributor steps](../../cli/README.md#prepare-submit-and-inspect-contributor-work)
define replay and revision behavior.

## Stop or dispose

`docker compose down` keeps the project's volumes, including the material,
registry and checker socket/owner volumes. Checker execution containers are
created directly, not by Compose: `down --volumes` does not remove them.
Before disposal, stop admission and drain checker executions while the service
is running. Verify that no container remains for this deployment's exact owner.
After a crash, retain the socket volume and restart its owning service to recover
its containers, or reconcile independently verified exact container IDs first.
Do not delete the custody volume while container ownership remains unsettled.

Only after that verification, confirm the project name as in
[Stop, retain or dispose](local-pilot.md#stop-retain-or-dispose) and remove its
Compose resources and images:

```bash
docker compose down --volumes
docker image rm "$COMPOSE_PROJECT_NAME-checker:local" \
  "localhost:$WORKSTREAM_CHECKER_REGISTRY_HOST_PORT/harnessy-proof:local"
```

Checker containers that the service started carry the label
`workstream.external-checker=true` and a deployment owner label. The service
removes its containers after each run; startup recovery verifies that same
owner, exact Docker ID, name and attempt before removal. Preserve the private
socket directory's `.workstream-checker-owner` across restarts; do not copy it
between deployments. See [container recovery ownership](../../external_checkers/README.md#container-recovery-ownership)
for lost-custody reconciliation. Generic labels alone never authorize cleanup.
