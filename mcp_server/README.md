# Workstream MCP Adapter

An independently installed adapter exposing 132 tools under the caller's authority:

- `workstream_profile_get` calls `GET /api/v1/actors/me`.
- `workstream_profile_update` calls the unkeyed `PATCH /api/v1/actors/me`.
- `workstream_authorization_context_get` calls
  `GET /api/v1/actors/me/authorization-context` for one supplied project.
- `workstream_permissions_list` calls `GET /api/v1/authorization/permissions`.
- `workstream_admin_roles_list` calls `GET /api/v1/authorization/admin-role-definitions`.
- `workstream_admin_grants_list` calls `GET /api/v1/admin-role-grants`.
- `workstream_actor_admin_grants_list` calls
  `GET /api/v1/actors/{actor_profile_id}/admin-role-grants`.
- `workstream_actor_get` calls `GET /api/v1/actors/{actor_profile_id}`.
- `workstream_actor_identity_link_get` calls
  `GET /api/v1/actors/{actor_profile_id}/identity-links`.
- `workstream_admin_grants_issue` calls keyed `POST /api/v1/admin-role-grants`.
- `workstream_admin_grants_revoke` calls keyed
  `POST /api/v1/admin-role-grants/{grant_id}/revoke`.
- `workstream_actor_suspend` calls keyed
  `POST /api/v1/actors/{actor_profile_id}/suspend`.
- `workstream_actor_reactivate` calls keyed
  `POST /api/v1/actors/{actor_profile_id}/reactivate`.
- `workstream_actor_deactivate` calls keyed
  `POST /api/v1/actors/{actor_profile_id}/deactivate`.
- `workstream_identity_link_revoke` calls keyed
  `POST /api/v1/actor-identity-links/{identity_link_id}/revoke`.
- `workstream_identity_link_reactivate` calls keyed
  `POST /api/v1/actor-identity-links/{identity_link_id}/reactivate`.
- `workstream_projects_create` calls keyed `POST /api/v1/projects`.
- `workstream_projects_get` calls `GET /api/v1/projects/{project_id}`.
- `workstream_contributor_candidates_list` calls
  `GET /api/v1/projects/{project_id}/contributor-candidates`.
- `workstream_project_grants_issue` calls keyed
  `POST /api/v1/projects/{project_id}/role-grants`.
- `workstream_project_grants_list` calls
  `GET /api/v1/projects/{project_id}/role-grants`.
- `workstream_project_grants_get` calls
  `GET /api/v1/projects/{project_id}/role-grants/{grant_id}`.
- `workstream_project_grants_revoke` calls keyed
  `POST /api/v1/projects/{project_id}/role-grants/{grant_id}/revoke`.
- `workstream_guides_create` calls keyed
  `POST /api/v1/projects/{project_id}/guides`.
- `workstream_guides_update` calls keyed
  `PATCH /api/v1/projects/{project_id}/guides/{guide_id}`.
- `workstream_review_policy_put` calls keyed and preconditioned
  `PUT /api/v1/projects/{project_id}/guides/{guide_id}/review-policy`.
- `workstream_revision_policy_put` calls keyed and preconditioned
  `PUT /api/v1/projects/{project_id}/guides/{guide_id}/revision-policy`.
- Thirteen contributor/project workspace reads cover the caller's projects,
  assignments, submissions, summary and contributions; project submissions,
  assignments, summary, imports and preparations; the active guide and ready queue.
- Three contribution-policy reads expose retained versions, the current
  selection and one exact version.
- Four keyed contribution-policy mutations create, replace, publish and retire
  an exact policy version.
- Twenty-four guide-lifecycle tools cover retained guide reads, bounded verified
  document bytes, setup and sufficiency records, submission-artifact policies,
  compiled proposals, corrections, approvals and activation.
- Ten checker/delivery/registry tools cover contributor and manager checker
  projections plus deliberate operator retry, reconciliation and registration.
- Nine operator-artifact tools cover readiness, bindings, replicas, receipts,
  verification/recovery, admission usage and audit events.
- Eighteen task-execution tools cover bounded preparation ZIPs, contributor and
  manager task context, screen/release/claim/start, guide-document reads and
  admission-backed submission creation/history.
- Twenty-four project, task-management, import, audit, service-actor and model
  operations complete the current public product catalogue. Task-import source
  content uses an 8 MiB exact-byte boundary; health routes remain operational
  liveness rather than user tools.

Each call forwards the caller's bearer to its fixed public Workstream operation.
There are no MCP resources or prompts. Workstream, not the adapter, owns every
administrative authorization decision and lifecycle effect.

## Authentication Boundary

This is the maintainer-approved **custom bearer-header integration**, not the
standard remote MCP OAuth authorization profile. Use a client that can send an
explicit `Authorization: Bearer <Workstream access token>` header on every tool
invocation. OAuth discovery and compatibility with hosted clients that require
that discovery are not provided.

The caller obtains and refreshes its token through the existing identity flow.
The adapter rejects missing, duplicate or malformed headers, then forwards a
well-formed bearer unchanged to the configured API. Workstream verifies the
signature, issuer, audience and expiry and applies its current actor and access
rules. The adapter does not call Flow, inspect JWT claims, hold refresh tokens,
calculate grants or perform an extra authentication API call.

Initialization and tool listing reveal only the static catalogue. They do not
authenticate a session. Tokens never belong in tool arguments, URLs, logs or
prompts. An AI client using a human bearer acts as that human; this is not future
agent registration or delegation.

## Local Run

Python 3.12 and uv are required. From this directory:

```bash
uv sync --frozen --extra dev
WORKSTREAM_API_URL=http://127.0.0.1:8000 uv run --frozen workstream-mcp
```

The endpoint is `http://127.0.0.1:8080/mcp`. The default listener is loopback.
Configuration is read from environment variables; `.env.example` documents
the settings but is not loaded automatically. No server-wide caller token is
configured. A separate Workstream API must already be running.

Ordinary JSON responses default to a 64 KiB bound. Guide-document reads and
submission-bundle uploads use separate 64 MiB bounds and a 120-second operation
timeout so binary transfers do not enlarge the allowance or timeout for every API
call. Configure document reads independently with `WORKSTREAM_MCP_MAX_DOCUMENT_BYTES` and
`WORKSTREAM_MCP_DOCUMENT_TIMEOUT_SECONDS`; the adapter still buffers one bounded
document before returning its Base64 representation.

The profile read takes `{}`. Profile update accepts at least one of
`display_name` and `contact_email`, preserving omission and explicit `null` while
matching Workstream's normalization and bounds. Authorization context requires
one `project_id`; Workstream decides whether the caller may see that exact
project. First admission can create the actor/link and update admission
timestamps, but does not grant roles. Lifecycle and access denials follow
Workstream. Errors are MCP tool failures with safe status/code information, not
fabricated results.

Definition tools take `{}` and return definitions, not the caller's effective
permissions. Actor reads require a UUID `actor_profile_id`. Grant lists require
`scope_type` (`system` or `project`); `scope_project_id` is required for project
scope and forbidden for system scope;
the actor-history tool also requires `actor_profile_id`. Optional `status`
(`active`, `revoked`, `all`), `limit` (1-100) and `cursor` (up to 512 characters)
are forwarded only when supplied. Omission uses backend defaults; null is not a
query value. Cursors are opaque: retain and return them unchanged with the same
scope and filters. Workstream validates cursor syntax and current authority on
every call; these grant cursors are not cryptographically bound to query scope.
Administrative projections exclude contact details and
external identity subjects; read calls may still update admission/audit state.
Actor display names and grant/revocation reasons are caller-controlled. Their
model-visible text is explicitly marked as untrusted data while
`structuredContent` preserves the exact validated API object.

Administrative mutations take a required UUID `idempotency_key` as a typed tool
argument. Grant issue also takes a closed `body` with target actor, role, exact
system/project scope and a 1-500 UTF-8 byte reason. Revoke takes a UUID `grant_id`
and a reason body. The adapter validates shape and forwards the key unchanged as
`Idempotency-Key`; it never reads the key from MCP HTTP headers or `_meta`, generates
one, stores replay state or retries automatically. Workstream enforces caller
authority, self-action guards, duplicate/current-state rules and final-administrator
protection. A lost or malformed response after dispatch is reported as uncertain;
the caller can recover by repeating the same arguments and key.

Actor and identity-link lifecycle mutations use the same typed key and reason
contract. Each takes exactly one target UUID and a closed reason body. Workstream
alone enforces caller authority, self and final-administrator guards, current
state, link admission and terminal actor deactivation. The adapter accepts only
the exact bounded receipt for the requested UUID and performs no retry.

Project creation takes a closed body with `name`, `slug` and optional
`description`, plus the required typed UUID `idempotency_key`. Workstream alone
checks current system Project Manager authority, owns duplicate-slug and replay
state, and creates the draft project. `idempotency_pending` tells the caller that
a later same-key recovery is allowed; the adapter still never retries
automatically. Project read takes one UUID. Workstream selects the full
administrative response or the exact contributor response containing only
`id`, `name` and `status`; the adapter validates that projection and the returned
project identity without calculating access itself.

Project participation reads take one project UUID. Candidate and grant lists
accept an optional bounded `limit` and opaque `cursor`; grant lists also accept
optional `active`/`revoked` status and `submitter`/`reviewer` role filters. Issue
takes a target human actor UUID, one of those two roles, explicit bounded
qualification evidence, a reason and a typed UUID idempotency key. Revoke takes
the canonical project/grant UUID pair, a reason and a typed key. Workstream
alone decides candidate visibility, target eligibility, manager authority,
duplicate/current state and replay. The adapter forwards caller inputs unchanged,
validates project/target/grant binding in successful responses and never turns
project participation into task eligibility.

Guide creation declares a version, one or more illustrative task examples and
one or more PDF, DOCX, PPTX or Markdown document records. It returns immutable
document identifiers and an `awaiting_documents` setup identity. The adapter
does not upload document bytes or continue setup. Guide update accepts only the
draft guide's optional `change_summary`; version, examples, documents, policies
and lifecycle fields are rejected by its closed input schema. Both mutations
require caller-supplied UUID idempotency keys and rely on Workstream for project
authority, draft-state checks, version uniqueness and durable replay.

Guide policy mutation takes a closed review or revision body, a typed UUID
`idempotency_key` and an explicit `if_match` string. Use
`"no-current-policy"` for the initial policy or retain the exact selector for the
currently selected policy. The adapter forwards both values unchanged as
`Idempotency-Key` and `If-Match`; it never discovers, generates, trims or repairs
them. Omitted optional policy fields remain omitted. Workstream owns defaults,
review-mode inheritance, immutable lineage, stale/malformed preconditions,
authorization and replay. Selector recovery, approval and activation remain
outside these two guide-policy tools.

Workspace reads accept only their documented UUID selectors, filters, bounded
page size and opaque cursor. Contribution export is JSON-only in MCP; the
adapter sets `format=json` and does not expose CSV bytes as structured tool
output. Workstream owns visibility and pagination authority on every call.

Contribution-policy reads expose current selectors and immutable version
history without granting mutation authority. Create, update, publish and retire
take a caller-supplied UUID `idempotency_key`; decision bodies are explicit
empty objects. The adapter forwards each body and key once to its fixed route,
binds successful receipts to the requested project, policy, version and
operation IDs, and reports unverifiable success as uncertain execution.

Task execution uses separate contributor and manager read tools so the adapter
never chooses an authority path on the caller's behalf. Screen, release, claim
and start require typed UUID idempotency keys; claim performs only the claim
request. Submission creation consumes caller-supplied admission and assignment
identifiers and stays unkeyed because that is the current backend contract.
Preparation accepts a bounded Base64 ZIP, decodes it once and forwards the
caller's typed assignment/key and optional submission or revision fields as the
fixed backend headers. Revision preparation ID and digest must be supplied
together. Workstream owns ZIP validation, pre-submit checks, replay and all task
state changes. A checker rejection is a normal safe tool failure; an unverified
mutation success remains uncertain and is never retried automatically.

## Deployment Boundary

Build from this directory only:

```bash
docker build -t workstream-mcp-foundation:local .
```

The image contains the adapter and its locked dependencies, not the backend.
Configure a fixed trusted `WORKSTREAM_API_URL`, exact allowed Host values and
listener settings. Non-loopback API destinations require HTTPS. Put public
ingress behind HTTPS, with rate limits and matching body, header, connection
and timeout bounds. Preserve `Cache-Control: no-store` on successes and failures;
disable authenticated response caching and redact Authorization and business
payloads in proxy telemetry. Do not expose the container directly as a public
HTTP service. Browser-origin requests are rejected by this native-client profile.

The adapter disables redirects, environment proxy inheritance and automatic
retries. A mutation transport failure, upstream 5xx response, or unexpected
success/redirect response is reported as non-retryable uncertain execution.
Connections may be pooled, but
caller credentials and results are not shared or cached. Response validation is
pinned to the 132 selected public contracts in `contracts/`; upstream drift
must be reviewed, not silently accepted. There is no fallback service or
backend-private import.

## Verification

```bash
uv run --frozen ruff check workstream_mcp tests
uv run --frozen mypy workstream_mcp
uv run --frozen pytest -q --ignore=tests/integration
uv build
```

Real API tests require the repository's isolated PostgreSQL runner, controlled
fixture identities and a separate installed adapter process. Never supply a
production database or real user token to a test. Integration and container
commands are recorded in the additive MCP workflow and the
[current chunk record](../.commitrail/initiatives/WS-MCP-002/WS-MCP-002-13.md).
Selected schemas are compared with the running backend OpenAPI operations;
custom admission, lifecycle and exact-project semantics are exercised separately.

Local fixture evidence does not certify the deployed Flow provider, a public
gateway or all MCP clients. The assembled release proof remains a bounded
change in the
[initiative](../.commitrail/initiatives/WS-MCP-002/OVERVIEW.md).
