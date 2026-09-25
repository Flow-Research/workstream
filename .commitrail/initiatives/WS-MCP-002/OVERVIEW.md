# WS-MCP-002: Workstream MCP Adapter Approach

- Disposition: Planned
- Prepared by: OxVictor
- Purpose: Contributor implementation guide with confirmed caller-token design
- Repository baseline reconciled: `2a3a392fe014583a0675c0a3e1f5612daba0fda4`
- Pinned API handoff baseline: `6feef39834737eed106773fdaed6003561fd021a`
- Delivered foundation: [One-tool profile foundation](WS-MCP-002-01.md), merged in PR #418.
- Current change: [Own profile editing and project authorization context](WS-MCP-002-02.md).
- Next usable boundary: WS-MCP-002-03 administrative reads after this change is
  reviewed and merged; no later tool starts automatically.

## Current implementation

[`mcp_server/`](../../../mcp_server/README.md) is an independently packaged
Streamable HTTP adapter with three self-service tools: profile read, profile
update and exact-project authorization context. It includes a container,
selected response-schema validation and additive CI. Its integration tests
exercise the installed adapter against the real Workstream API. Workstream
still owns token verification and authorization. This is delivered packaging,
not proof of a deployed public gateway, production Flow integration or the
remaining 24 tools. The initiative remains Planned because that larger scope
is unfinished. Historical hashes below describe their stated design/proof;
each implemented binding records its current source baseline separately.

## 1. What I Understand We Are Building

I want to make Workstream available to MCP clients through a small service that calls the existing Workstream APIs. A user working from an MCP client should be able to perform supported Workstream actions under their own identity and permissions.

The adapter will be deployed separately. Updating or restarting it should not require redeploying Workstream. Workstream must still be running and reachable for its tools to complete API operations.

The wider experience includes creating projects, assigning contributors, working on tasks, submitting work, and reading contribution records. I propose delivering that experience in small stages, following the availability of the public backend contracts.

## 2. What I Have Checked

I have reviewed the current contribution guide, Commitrail guidance, architecture rules, roadmap, and the available Workstream MCP interactive design.

The MCP design is based on commit `c69ff85`. It describes 27 tools: 12 reads and 15 mutations, with operation keys required for 14 mutations. It exposes no resources or prompts and ends at project setup and access.

The maintainer supplied the fixed public API list. Section 6 preserves the historical mapping of all 27 tool names to route/schema owners at `6feef398`, with test references and original design differences. Each binding still needs current schema capture when implemented. Section 10 records the executed one-tool proof against the newer repository baseline; it does not certify the full catalogue.

The roadmap still distinguishes public capabilities from hidden implementations and planned work. A hidden backend service will not be treated as a public API available to the adapter.

I have also reviewed both complete Flow Identity designs. The architecture walkthrough, dated 10 September 2026, defines a human-only v0.1. The human and agent experience, dated 11 September 2026, defines an agreed future extension. Both are design records; neither claims that the integrations are deployed. I will keep that distinction clear in implementation and tests.

The original planning mapping used `6feef398`, including merged PR #400 and its API drill handoff. Public guide proposal review, pre-submission approval, correction and manual dispatch were outside that fixed 29-operation census and the proposed 27 tools. Guide creation changes at that baseline are recorded below. Current one-tool evidence uses `723c88ff`; recheck each later binding against concurrent owner work rather than treating this historical census as a current full-catalogue certification.

Closed contributor MCP PR #149 remains historical evidence, not an implementation baseline. The maintainer has now confirmed the caller-token design in section 5. Main risks are API contract drift, credential leakage, exposing hidden capabilities, unsafe mutation retries, and treating future agent support as available.

## 3. First Release Scope

The maintainer's [review addendum](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5653317895) confirms the 27-tool, human-only first release. Each binding still needs verification against the public API before implementation.

| Area | Proposed tools |
| --- | --- |
| Own profile and access | Read profile, update profile, read own authorization context |
| Authorization definitions | List permissions and administrative role definitions |
| Administrative grants | List, issue, revoke, and inspect an actor's administrative grants |
| Actor and identity access | Read actors and identity links; suspend, reactivate, or deactivate actors; revoke or reactivate identity links |
| Project setup | Create and read projects; create and update draft guides; set review and revision policies |
| Project participation | Find contributor candidates; issue, list, read, and revoke project grants |

Some of these are privileged tools. Their presence in the catalogue does not give the caller permission to use them. Workstream must authorize every invocation.

Task, submission, review, and ContributionRecord tools will be added through later agreed changes when their public contracts are ready. The adapter will never create a contribution record directly; it can only expose operations the backend authoritatively supports.

The first release will use the human identity baseline. Agent registration, agent credentials, and Workstream delegation require the future contracts described below before agent tools can be enabled. The first release will not include a login system, database access, background lifecycle workers, prompts, or replacement services for unavailable product APIs. Test doubles may simulate API responses in tests, but will not be a production fallback.

## 4. How the Adapter Will Work

```text
User through an MCP client
          |
          v
Standalone MCP adapter
  - checks the request header shape, not the token signature
  - validates the selected tool's input
  - calls its fixed Workstream API operation
  - checks and returns the API result
          |
          v
Workstream API
  - verifies the forwarded Flow token
  - resolves the caller's identity
  - checks current permissions and resource access
  - applies business rules
  - owns database changes, audit, and replay handling
```

Following the review addendum, the adapter stays in the Workstream repository as a separate Python package, with its own entry point, dependency lock, tests, container build, configuration and release instructions. This keeps review close to the API contracts while allowing separate deployment. Its only Workstream runtime dependency is a configured, reachable public API base URL. It must not access backend queues or invoke private or hidden handlers.

The runtime will communicate over HTTP and will not import Workstream's database models, private services, or application startup code. Its package must install and start without installing the backend. ADR 0014 continues to govern backend-owned integrations; the standalone adapter will not import private backend factories to reuse their internals.

The package will have a few clear responsibilities:

| Part | Responsibility |
| --- | --- |
| Server | Register tools and serve MCP requests using the official SDK |
| Credential transport | Read the individual caller's bearer per request and forward it unchanged; Workstream verifies it |
| Tool contracts | Define accepted inputs, expected outputs, and fixed API mappings |
| HTTP client | Manage connections, timeouts, declared headers, and bounded responses |
| Error mapping | Return safe, accurate failures without leaking internal data |
| Configuration | Validate the trusted API address, transport settings, and deployment limits |

Use the official Python MCP SDK with a pinned package lock. The earlier local
experiment used MCP SDK 1.29.0 and protocol `2025-11-25`; that is historical
proof only. The independently packaged adapter delivered by PR #418 pins MCP
SDK 2.2.0 and Streamable HTTP protocol `2026-07-28`, with package, client and
real-process tests. This is Streamable HTTP, not the superseded HTTP+SSE transport.

## 5. Identity and Permissions

Flow Identity will remain responsible for issuing credentials. Workstream will remain responsible for deciding what the caller may do to a particular project or resource.

### Confirmed caller-token flow in v0.1

The maintainer's decision is a thin REST adapter with custom request-level
authentication. Each protected MCP invocation carries the caller's existing
Flow-issued Workstream access token in `Authorization: Bearer <token>`.
The adapter forwards that bearer unchanged to the fixed Workstream API operation.
Workstream verifies the token, resolves the actor/link, and checks current
authorization and lifecycle rules. The adapter never calls Flow Identity, obtains
another token, verifies JWTs locally, or probes a second API to authenticate first.

Missing, duplicate or malformed Authorization headers can be rejected before API
dispatch. A well-formed bearer with an invalid signature, issuer, audience or
expiry is rejected by Workstream after dispatch; preserve that denial. Do not
weaken Workstream's configured verifier to make forwarding succeed.

The client supplies a fresh request header on every protected call. Connections,
initialization and discovery never establish a shared authenticated identity.
Static initialization and tool listing may expose only the fixed public catalogue,
without product data or permission-dependent results. A later call must still
supply its own bearer. No cached grant, profile or earlier token authorizes it.

This deliberately does **not** implement the standard remote MCP OAuth
authorization profile, whose token-passthrough restriction differs from this
design. It supports clients explicitly configured to send the caller's API bearer;
do not promise compatibility with clients requiring OAuth discovery. Separate
container deployment does not change this trade-off or require a second identity
system. A future standards-profile change would need its own explicit design.

Tokens stay out of tool arguments, results, URLs, logs and traces. Use only a
trusted configured Workstream destination, disable redirects and environment
proxy inheritance, and keep credentials request-local. Public deployment requires
HTTPS and the deployment bounds in section 7; the local experiment is loopback-only.
The client and Flow own token acquisition/refresh; the adapter holds no refresh
token, signing key, issuer/JWKS configuration or privileged fallback credential.
Workstream's own verification may use JWKS or introspection; this design makes no
claim that production verification performs zero Flow network calls.

An AI-assisted client may use the human's supplied token: the resulting actor is
that human, exactly as with REST. This does not create separate agent identity or
delegation. Target actor IDs remain valid only where the fixed API explicitly
requires them; self-profile reading takes no actor selector.

### Future agent access

The second document gives a clear future direction: a human registers and approves an agent once through Flow Identity. Flow verifies control of that agent. The agent then authenticates with its own credential, which identifies both the actual agent and the human it represents. It does not use the human's bearer token.

In the proposed Workstream model, the human and each agent have distinct `ActorIdentityLink` records pointing to the same human `ActorProfile`. Connecting the agent creates no permission by itself. The human must explicitly delegate permitted actions and project access inside Workstream.

For example, an agent may submit work only when the human currently has the required grant, that particular agent has submission delegation, the project permits an agent caller, and the normal lifecycle checks pass. Removing the human's grant or the agent's delegation must stop subsequent guarded actions. Workstream owns those checks and the audit record distinguishing the human principal from the actual agent caller.

The MCP adapter will preserve these identities when the contracts become available. It will not register relationships, create identity links itself, or calculate delegation permissions locally. The design leaves claim names, registration APIs, delegation APIs, onboarding without an existing human profile, and revocation propagation unresolved. Agent support therefore needs a later bounded change and real backend evidence. Using an AI-assisted MCP client with a human credential does not establish this separate agent identity model.

## 6. API Contracts and Failures

The maintainer-owned API handoff is now received and mapped below. It covers all 27 original names without adding tools. The inventory records methods/routes, current body and result models, headers, success statuses and per-operation drill references. Schema differences and workflow limits are explicit for joint agreement before freezing the generated tool definitions. The agreed inventory will be the source for binding tests and contract-drift checks.

Tool calls will use a configured API destination and fixed routes. Users will not be able to supply arbitrary destinations or authentication headers. Redirects will not carry credentials to another destination.

For the 14 mutations that require an operation key, the client must supply and preserve that key. The adapter will forward it unchanged. The self-profile PATCH is the one unkeyed mutation. Automatic mutation retry is forbidden, including retry with the same key. If a response is lost after dispatch, the adapter cannot know whether the write completed. It will report uncertain execution without claiming failure or rollback. A later client-initiated attempt preserves the original key and follows the API's replay rules.

Policy updates will preserve required version selectors such as `If-Match`. A stale selector must produce the API's conflict outcome. If the initial catalogue lacks an operation needed to recover the current selector, I will document that limitation for review instead of using a write to imitate a read.

Errors will distinguish invalid credentials, invalid input, API denial, conflicts, unavailable dependencies, and uncertain execution. The result will preserve useful API status and correlation information while excluding secrets and raw internal exceptions. A successful MCP transport response does not mean the Workstream operation succeeded.

### API handoff mapping at `6feef398`

The maintainer supplied the [29-operation handoff](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654783507). The table below maps all 27 original tool names to that fixed list and the reconciled backend source at `6feef398`. It is a proposed mapping for joint review, not a claim of MCP runtime execution or an approved catalogue freeze.

**Result:** 27 distinct tools match 27 distinct handed-off method/path pairs. Keep 12 logical reads, 15 mutations and 14 keyed mutations. The two unused operations are row 1, `GET /api/v1/health` (operational liveness, not a user tool), and row 18, `POST /api/v1/service-actors` (not part of this human-only catalogue). A human administrator reading or managing an existing service actor does not enable service actors to authenticate as MCP callers.

All paths below have the fixed prefix `/api/v1`. `K` means required UUID `Idempotency-Key`; `K+M` also requires `If-Match`; `-` means neither mutation header. Authentication is request context, never a tool argument. Request/correlation IDs remain transport metadata. Success codes below are backend HTTP codes, not MCP transport success. Body and response names refer to current backend models, not the stale embedded HTML schemas.

### Mutation values at MCP ingress

Following the supplied interactive tool schemas, mutation values come from typed
fields in `tools/call.params.arguments`, alongside `body` and path selectors.
They are not MCP `_meta` values or incoming MCP HTTP headers. The adapter never
uses those other locations as a fallback or override.

- Every table row marked `K` or `K+M` requires `arguments.idempotency_key`: a JSON string validated as a UUID. Map it only to the downstream `Idempotency-Key` header, not the body or query. The adapter validates without replacing the original string with a UUID object's normalized serialization; valid spelling is forwarded unchanged. It never generates a missing key.
- Only `workstream_review_policy_put` and `workstream_revision_policy_put` (the `K+M` rows) additionally require `arguments.if_match`: a JSON string mapped only to downstream `If-Match`. Preserve its exact quotes and contents; do not trim, rebuild, select a policy, or fill a default selector.
- Rows marked `-`, including the unkeyed profile PATCH, have neither field in their closed input schemas and send neither header. Unknown mutation fields are rejected, not silently ignored.

The adapter's input validator rejects missing/null/wrong-type fields and invalid
UUID strings before any API request. Header values must also be safe to encode
as one HTTP field: reject CR/LF, NUL and other control characters or unencodable
values without dispatch. For `if_match`, Workstream remains responsible for
policy-selector syntax and current-state meaning: a transport-safe malformed
selector reaches the API unchanged and preserves `409 policy_precondition_invalid`;
a valid but stale selector preserves `409 policy_precondition_failed`. This
avoids copying policy parsing into the adapter. Workstream also retains its own
header validation, authorization and replay checks; local input failure is an
adapter failure, not a fabricated Workstream HTTP response.

Conformance for each affected binding must prove missing/null/wrong-type and
invalid UUID input causes zero dispatch; header-injection values cause zero
dispatch; valid values appear byte-for-byte in exactly one corresponding
downstream header and not in JSON/query data. Cover both policy tools with the
quoted initial selector, a current selector, a safe malformed selector and a
stale selector. Test that MCP HTTP headers or `_meta` cannot supply a missing
argument or override a valid one, and that every `-` row rejects extra mutation
arguments and omits both downstream headers. Direct-API fixtures separately
retain the drill's missing/invalid HTTP-header expectations. Repeat the same
client-retained key after adapter restart to exercise Workstream-owned replay;
the adapter stores no replay state and performs no automatic mutation retry.
These tests belong to the chunks that introduce the affected mutations, not
only the final release drill.

The **Drill** column names the exact row in the [fixed acceptance matrix](../../../docs/engineering/external-api-drill.md#fixed-29-operation-acceptance-matrix), including its named E/A cases, invalid inputs, authority, readback and replay controls. Linked response names point to the current route declaration for that binding; schemas are linked below. These references define the tests to reuse, not newly executed results.

| Tool | Method and path | Body model | Success data model | HTTP / headers | Drill |
| --- | --- | --- | --- | --- | --- |
| `workstream_profile_get` | `GET /actors/me` | None | [ActorProfileSelfResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/api/routes/auth.py#L43) | 200 / - | 2 |
| `workstream_profile_update` | `PATCH /actors/me` | `ActorProfileUpdateRequest` | [ActorProfileSelfResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/api/routes/auth.py#L113) | 200 / - | 3 |
| `workstream_authorization_context_get` | `GET /actors/me/authorization-context` | None | [ActorAuthorizationContextResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/api/routes/auth.py#L77) | 200 / - | 4 |
| `workstream_permissions_list` | `GET /authorization/permissions` | None | [PermissionDefinitionsResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L857) | 200 / - | 12 |
| `workstream_admin_roles_list` | `GET /authorization/admin-role-definitions` | None | [AdminRoleDefinitionsResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L885) | 200 / - | 13 |
| `workstream_admin_grants_list` | `GET /admin-role-grants` | None | [AdminRoleGrantCollectionResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L960) | 200 / - | 15 |
| `workstream_admin_grants_issue` | `POST /admin-role-grants` | `AdminRoleGrantIssueBody` | [AuthorityMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1021) | 201 / K | 14 |
| `workstream_admin_grants_revoke` | `POST /admin-role-grants/{grant_id}/revoke` | `AdminRoleGrantRevokeBody` | [AuthorityMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1125) | 200 / K | 17 |
| `workstream_actor_admin_grants_list` | `GET /actors/{actor_profile_id}/admin-role-grants` | None | [AdminRoleGrantCollectionResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L989) | 200 / - | 16 |
| `workstream_actor_get` | `GET /actors/{actor_profile_id}` | None | [ActorProfileAdminResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L775) | 200 / - | 5 |
| `workstream_actor_identity_link_get` | `GET /actors/{actor_profile_id}/identity-links` | None | [ActorIdentityLinkAdminResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L817) | 200 / - | 6 |
| `workstream_actor_suspend` | `POST /actors/{actor_profile_id}/suspend` | `ActorLifecycleBody` | [ActorLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L636) | 200 / K | 7 |
| `workstream_actor_reactivate` | `POST /actors/{actor_profile_id}/reactivate` | `ActorLifecycleBody` | [ActorLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L664) | 200 / K | 8 |
| `workstream_actor_deactivate` | `POST /actors/{actor_profile_id}/deactivate` | `ActorLifecycleBody` | [ActorLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L692) | 200 / K | 9 |
| `workstream_identity_link_revoke` | `POST /actor-identity-links/{identity_link_id}/revoke` | `ActorLifecycleBody` | [IdentityLinkLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L720) | 200 / K | 10 |
| `workstream_identity_link_reactivate` | `POST /actor-identity-links/{identity_link_id}/reactivate` | `ActorLifecycleBody` | [IdentityLinkLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L748) | 200 / K | 11 |
| `workstream_projects_create` | `POST /projects` | `ProjectCreate` | [ProjectResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/create_router.py#L83) | 201 / K | 19 |
| `workstream_projects_get` | `GET /projects/{project_id}` | None | [ProjectResponse or ContributorProjectResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/router.py#L193) | 200 / - | 20 |
| `workstream_guides_create` | `POST /projects/{project_id}/guides` | `ProjectGuideCreate` | [ProjectGuideCreateResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/guide_mutation_router.py#L161) | 201 / K | 26 |
| `workstream_guides_update` | `PATCH /projects/{project_id}/guides/{guide_id}` | `ProjectGuideUpdate` | [ProjectGuideResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/guide_mutation_router.py#L184) | 200 / K | 27 |
| `workstream_review_policy_put` | `PUT /projects/{project_id}/guides/{guide_id}/review-policy` | `ReviewPolicyInput` | [ReviewPolicyResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/policy_mutation_router.py#L112) | 200 / K+M | 28 |
| `workstream_revision_policy_put` | `PUT /projects/{project_id}/guides/{guide_id}/revision-policy` | `RevisionPolicyInput` | [RevisionPolicyResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/policy_mutation_router.py#L140) | 200 / K+M | 29 |
| `workstream_contributor_candidates_list` | `GET /projects/{project_id}/contributor-candidates` | None | [ContributorCandidateListResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1563) | 200 / - | 21 |
| `workstream_project_grants_issue` | `POST /projects/{project_id}/role-grants` | `ProjectRoleGrantIssueBody` | [ProjectRoleGrantMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1233) | 201 / K | 22 |
| `workstream_project_grants_list` | `GET /projects/{project_id}/role-grants` | None | [ProjectRoleGrantListResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1592) | 200 / - | 23 |
| `workstream_project_grants_get` | `GET /projects/{project_id}/role-grants/{grant_id}` | None | [ProjectRoleGrantRead](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1626) | 200 / - | 24 |
| `workstream_project_grants_revoke` | `POST /projects/{project_id}/role-grants/{grant_id}/revoke` | `ProjectRoleGrantRevokeBody` | [ProjectRoleGrantMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1420) | 200 / K | 25 |

### Input and output details

Path selectors are supplied only where shown above. The authenticated actor is never replaced by a target selector. Preserve backend selector types: authorization target IDs are UUIDs; project/guide selectors follow their route and tool schemas. Query parameters are:

- Authorization context: required `project_id`.
- Both administrative-grant lists: required `scope_type`; optional `scope_project_id`, `status` (default `active`), `limit` (default 50, 1-100) and `cursor` (at most 512 characters). A project scope must satisfy the backend's project selector rules.
- Contributor candidates: `limit` (default 50, 1-100) and `cursor` (at most 512 characters).
- Project-grant list: optional `status` (`active` or `revoked`, omitted means unfiltered), `role` (`submitter` or `reviewer`), `limit` (default 50, 1-100) and `cursor` (at most 512 characters).
- All other bindings: no query parameters. Omit absent/null optional query values; do not decode or manufacture cursors.

Use these current model owners for the full field types, requiredness, enum values, nested schemas and validation. The field summaries below are navigation, not replacement validators:

| Model owner | Mapped fields and output boundaries |
| --- | --- |
| [Actor schemas](../../../backend/app/modules/actors/schemas.py) | Profile PATCH accepts only optional nullable `display_name` (200 characters) and `contact_email` (320). Preserve omission versus explicit null and normalization/NUL rules. Self responses contain the caller's declared profile fields; administrative actor/link responses are separate projections without raw subject or contact email. The plural identity-links route returns one object, not a list. |
| [Administrative schemas](../../../backend/app/modules/authorization/admin_schemas.py) | Grant issue uses `target_actor_profile_id`, `role`, `scope_type`, optional `scope_project_id`, and `reason`; revoke uses `reason`. Collection responses include `items`, `total`, `next_cursor`. Mutation responses are receipts, not full grant objects. |
| [Authorization router](../../../backend/app/modules/authorization/router.py) | Actor/link lifecycle bodies contain `reason`. Keep the existing lifecycle response models, catalogue projections and exact action binding; lifecycle operations do not provision a new identity or grant. |
| [Project-role request schemas](../../../backend/app/modules/authorization/project_role_schemas.py) and [nested qualification/read schemas](../../../backend/app/modules/authorization/schemas.py) | Grant issue uses `target_actor_profile_id`, `role` (`submitter` or `reviewer`), `qualification`, `reason`. Qualification contains skills/reputation availability snapshots, prior-project work UUIDs and external expertise references. Preserve nested availability consistency and collection/token bounds. Revoke accepts `reason`. Candidate and project-grant pages have `items` and `next_cursor`, no `total`. |
| [Project and guide schemas](../../../backend/app/modules/projects/schemas.py) | Project create: `name`, `slug`, optional nullable `description`. Project read preserves the API-selected administrative projection or the exact contributor `id/name/status` projection. Guide create: required `version`, `task_examples`, `documents`, optional nullable `change_summary`. Documents are 1-100 declarations with `label` and `media_type`; IDs/order are returned by the API. Guide PATCH accepts only optional nullable `change_summary`. |
| [Policy schemas](../../../backend/app/modules/projects/schemas.py) | Review input requires positive preference-window and lease-duration seconds; optional fields include strict boolean `human_review_required`, one active lease, no self-review, reject policy, finding evidence requirement, second-review flag, allowed decisions and minimum finding fields. Revision requires positive `max_revision_rounds` and `revision_deadline_hours`; optional state list is exactly one `needs_revision`, and reassignment rule is nullable. Preserve full version/hash/predecessor responses. |

### Authority and failure mapping

Guide task examples use the [nested task-example schema](../../../backend/app/modules/projects/api/task_examples.py): 1-100 examples, each with required nonblank `content`, optional nullable `title` and optional `labels`. Preserve its per-field and aggregate 128 KiB serialized UTF-8 bound; OpenAPI field types alone do not capture every custom validator.

Each tool uses its linked route's existing action and authorization path; the adapter does not recreate role evaluation. Self-profile/context operations act on the authenticated caller. Catalogue, actor, identity-link and administrative-grant operations retain their administrative/audit boundaries. Project creation requires the backend's system-scoped project-manager authority. Project reads may use exact contributor access; project management, candidate discovery and grant/policy mutations retain their exact-project and current-role checks. An administrative tool being listed is not permission to invoke it.

Run the named tests for each matrix row under the same caller categories, including ordinary users, applicable administrators/auditors, project managers, foreign-project managers, revoked/suspended/deactivated actors and revoked links. Preserve concealed 404 responses where the API uses them; do not convert every denial to 403 or expose target existence. Retain self-grant/self-removal and final-effective-administrator safeguards in the API, never a parallel adapter implementation.

For all rows, preserve actual API status, safe error code and correlation metadata. Applicable cases include 401 token rejection, 403 authority refusal, concealed 404, 422 input/header rejection, 409 state/precondition/idempotency conflicts, and 429/503 rate/dependency failures. This is not a claim that every row produces every code. The per-row drill cases and [findings and fixes](../../../docs/engineering/external-api-drill-findings.md) are the observed error oracle; OpenAPI's declared success/validation responses alone are insufficient. In particular, key mismatch and state-changed replay conflicts are not interchangeable. Do not retry a mutation automatically, even on a retryable API error.

Candidate and project-grant lists also return `400 invalid_cursor` for invalid cursors; preserve that instead of relabeling it as schema validation. Policy selector errors distinguish `policy_precondition_invalid` from `policy_precondition_failed`, both HTTP 409.

For the 14 keyed mutations, retain the original key, normalized request semantics and API replay outcome. Recheck current authority on replay through the API. Do not promise that an earlier receipt can always be replayed after target state or authority changes. The unkeyed profile PATCH remains unkeyed. Reads may update admission timestamps, so read-only means no requested product mutation, not absolutely no database writes.

### Differences and decisions to freeze

1. **Guide contract has changed.** Remove `content_markdown` from guide input/output. Add required task examples and document declarations; create success is now `ProjectGuideCreateResponse`, including `documents` and `setup`. PATCH still returns `ProjectGuideResponse`. Preserve task-example content/hash and all declared metadata. Do not silently keep the old embedded schemas.
2. **This catalogue does not complete guide setup.** Creating a guide returns `awaiting_documents`; there is no upload tool among the 27. Upload/setup/findings and the four proposal APIs from PR #400 are outside the handed-off 29-operation census. Confirm that the first release deliberately stops at declarations and draft policy configuration, with uploads handled outside MCP. Adding that workflow requires an explicitly agreed scope change.
3. **Policy omission and selector behavior matter.** Review input/output now includes `human_review_required` and response semantics metadata. Omission of the mode preserves a selected predecessor's setting; ordinary omitted optional fields use backend defaults. Do not fill defaults in the adapter. First creation uses the quoted `"no-current-policy"` selector. A later selector is the quoted policy ID, generation and hash without its `sha256:` prefix, joined by dots, as specified by the [policy owner](../../../backend/app/modules/projects/policy_mutation_service.py). Forward a caller-supplied selector unchanged. The 27 tools have no policy-read operation for recovering a lost/stale selector; confirm an outside-MCP recovery path or separately agree a read tool. Never use a write as discovery.
4. **Refresh each selected schema, not just guide names.** Validation includes NUL rejection, qualification limits and revision-policy constraints. When implementing a binding, compare its operation and transitive schemas against `/openapi.json` from the exact pinned backend build. The historical 27-tool source mapping is complete, but full-catalogue running-schema capture and conformance have not been executed. The local self-profile proof in section 10 is separate evidence. Do not describe the original HTML JSON as the current schema.
5. **Credential flow is settled in section 5.** Forward the individual caller's existing Workstream Flow bearer unchanged. No new audience, exchange, adapter-side verifier or administrator identity is introduced; Workstream retains its normal audience checks.

For implementation evidence, reuse [the drill setup](../../../docs/engineering/external-api-drill.md#run) and per-row assertions through an actual MCP client and independently running adapter. Keep health, local bootstrap and service-actor fixture provisioning outside the 27-tool count. Setup may need backend-only calls, but tools must dispatch only their agreed endpoint. Retain direct-API parity checks, state/audit checks, rejection-before-write assertions and same-key recovery. Existing historical backend runs are useful evidence, not proof that the new MCP path or live Flow deployment passes.


### Exact request path

Every protected invocation follows this path:

1. Receive one request on the declared POST Streamable HTTP endpoint.
2. Validate the selected protocol's transport metadata, Origin policy and bearer header shape. Use the SDK's negotiated Streamable HTTP revision; do not require headers from an unimplemented later protocol.
3. Establish caller context for this request only. Shared connection pools must not retain a caller's credentials or actor context.
4. Resolve the tool from a fixed typed registry. Unknown tools cause no API dispatch.
5. Validate arguments against the tool's closed input schema.
6. Select the registry's fixed public API method and route under the configured base URL.
7. Encode path and query selectors in their declared locations and serialize only the declared model under the typed `body` argument.
8. Add only adapter-controlled headers: the unchanged request bearer, content type, required operation key and `If-Match`, and safe correlation identifiers. Arbitrary authorization, forwarding, host or destination headers are not tool inputs.
9. Send one bounded HTTP attempt.
10. Validate response status, content type, byte size, JSON shape and the declared success or error contract.
11. Return the structured MCP result, preserving the API's meaning and excluding credentials and internal exceptions.

Each tool has exactly one fixed method/path binding. Destination, route, method and authentication headers are never model-visible arguments. Authenticated redirects are disabled. Optional null query parameters are omitted, never serialized as the strings `None` or `null`. Partial updates preserve the difference between an omitted field and an explicit null, using JSON-safe, exclude-unset serialization rather than dropping every null.

UUIDs, timestamps, enums, cursor bounds, byte limits and cross-field rules must match the public API. Cursors remain opaque: no decoding, modification, fabrication or inferred totals. The adapter returns only data available to that caller through the API. It does not cache grants, authorization context, actor state, project policy or lifecycle eligibility.

## 7. Deployment and Operation

Authenticated MCP responses, including errors, must carry `Cache-Control: no-store`. The reverse proxy/CDN must preserve and respect this policy. Test headers and caller isolation through the deployed HTTP path, including error responses. v0.1 uses no identity-partitioned response cache; the prohibition on local authority and lifecycle caches remains in force.

The adapter will have its own container, configuration, and release instructions. Production HTTP connections will use TLS. Request sizes, response sizes, connection counts, timeouts and maximum in-flight calls will be configurable and tested. Backpressure must reject or limit excess work before an unbounded queue forms.

A liveness check will report whether the adapter process is running. Readiness and dependency reporting will make API unavailability visible without creating an actor or performing a business mutation as a health check.

Logs will record tool names, durations, safe outcomes, and correlation IDs. They will exclude credentials and sensitive request bodies. The separate Logfire feedback-loop work can be considered in its own PR; it is not a dependency for implementing this adapter.

## 8. How I Will Prove It Works

I will test the complete route from an MCP client, through the adapter, to a separately running Workstream API. Mocked HTTP tests will cover failures, but will not be presented as proof of live authorization.

| Test area | Evidence expected |
| --- | --- |
| Tool catalogue | Exactly the agreed tools and schemas; no unintended tools, resources, or prompts |
| HTTP mapping | Correct routes, bodies, query parameters, and required headers |
| Authentication | Missing/malformed headers cause no API dispatch; invalid, expired or wrong-audience bearers receive Workstream's denial after dispatch |
| Flow token profile | Workstream's configured verifier remains authoritative; the adapter neither duplicates nor bypasses its token policy |
| User isolation | Concurrent callers retain their own credentials and results |
| Product authorization | Allowed caller succeeds; missing, revoked, and cross-project authority is denied by the real API |
| Replay and conflict | Same-key retries follow backend behavior; changed payloads and stale policy selectors preserve conflicts |
| Dependency failures | Timeouts and malformed or oversized responses produce bounded, accurate failures |
| Privacy | Credentials never appear in results or telemetry; authorized API result fields remain distinct from prohibited diagnostic leakage, as confirmed in the response-data policy below |
| Key rotation | Verification and key rotation stay with Workstream; API verification failures never trigger an adapter fallback credential |
| Independent deployment | Adapter builds and starts separately and reports Workstream unavailability correctly |

Deployed integration uses valid caller credentials accepted by the configured Workstream API; it does not require a new MCP identity registration or token exchange. Locally signed fixtures are not certification of the deployed Flow service. Separate agent identity/delegation remains future work.

### Required conformance suites

The following are acceptance requirements from the review addendum, not claims that tests have already run. Each implementation record will identify the concrete tests and commands for its portion of this matrix.

| Suite | Required proof |
| --- | --- |
| 1. Catalogue | Exactly 27 unique tools, 12 reads, 15 mutations, 14 keyed mutations and one fixed binding per tool. No resources, prompts, login tool, generic HTTP tool, hidden route or extra capability. Input and structured-output schemas are complete and self-contained; references resolve locally; closed schemas reject unknown fields. Read-only, destructive, idempotent and open-world annotations match actual behavior. |
| 2. MCP protocol | Test the selected Streamable HTTP revision and actual supported clients: initialize, initialized notification, tools/list and tools/call; protocol negotiation, Origin, Accept/content type, malformed JSON-RPC, unknown tools/methods, cancellation and request/response limits. First foundation is stateless, with no authenticated session or resumable event stream. Catalogue is fixed across callers/restarts. Do not claim newer protocol features from SDK transport success. |
| 3. Caller-token transport | Exact per-request bearer forwarding, no JWT/JWKS verifier or extra authentication API request. Missing/malformed headers do not dispatch; Workstream denies invalid signature, issuer, audience, expiry and premature tokens. Prove first admission grants no authority, concurrent/alternating caller isolation, no retained credential on a later missing-token request, no redirects/environment-proxy leakage, and safe API denial propagation. This custom integration does not publish OAuth discovery as if that profile were implemented. |
| 4. All tool bindings | At least one positive wire-level case per tool proving exact method, encoded path, query omission/defaults, typed body, headers, successful status and structured response, with no extra API call. Cover both permitted project-response projections and every maximum-valid bounded input. Mock assertions support this proof but do not replace the release drill. |
| 5. Real authorization and lifecycle | Use the real API and PostgreSQL path. Prove first human profile/link provisioning grants no authority; self-edit remains self-only; missing authority, wrong administrative role, wrong scope and cross-project access are denied. Revoked grants and inactive actors/links stop subsequent actions. Preserve administrative self-grant/self-revoke guards and final effective Access Administrator protection. Contributor/admin projections must not leak into one another. Workstream guards and audit remain authoritative. |
| 6. Replay and concurrency | Same key and identical payload follows canonical replay; changed input conflicts. Concurrent duplicates match direct-API outcomes. Both policy writes preserve stale `If-Match` conflicts. Lost responses after possible commit report uncertainty without claiming rollback. No automatic mutation retry. Client restart preserves caller-retained keys, cursors, grant/resource IDs and policy selectors. |
| 7. Network failures | Bound connection refusal, DNS/TLS failures, connect/read/total/cancellation timeouts, applicable API 429/401/403/404/409/412/422/5xx responses, malformed JSON, wrong content type, schema-invalid success and oversized responses. Test API failure during a call and adapter shutdown with in-flight work. Never claim rollback of a possibly committed write. |
| 8. Privacy and observability | No credentials or authorization headers in results, logs, traces, exceptions, metric labels or URLs. Do not echo raw arguments or sensitive bodies into diagnostics. Profile data, guide content, reasons and cursor payloads must not enter telemetry. Allow only bounded tool name, fixed method/route template, duration, response size, safe status/error code and approved correlation IDs. Return the declared API fields the caller is authorized to receive, even when a field value also appeared in the request. Prove authorized profile/guide/cursor results are preserved while credentials and sensitive diagnostic content are excluded. Workstream remains audit authority. |
| 9. Independent deployment | Build, install and start without the backend package. Run in a separate process/container using only the configured public API. Invalid API URL or transport configuration fails startup safely. API unavailability affects readiness/calls without crashing catalogue discovery. No client-name-specific behavior. Two MCP clients see the same catalogue and are independently authorized. Authenticated success and error responses carry `Cache-Control: no-store`; verify proxy/CDN preservation and no cross-caller reuse through the deployed HTTP path. |
| 10. Contract drift | Use the source mapping in section 6 and jointly freeze the exact 27-tool definitions against the pinned running backend schemas, including routes, schemas, headers, statuses, authorization and API drill evidence. CI must fail on route, method, input/output, header, status, annotation or capability drift. Regeneration must not silently accept a changed contract. Changes require deliberate review and renewed proof. |

For annotations, a logical read is not automatically side-effect-free: first profile access may provision identity records. The annotation tests must reflect the actual API operation rather than its HTTP method alone. The implementation contract will trace the requested protocol assertions to the selected SDK and protocol sources; any mismatch must be raised for review before freezing behavior.

### Required release drill

```text
Real MCP client -> HTTP /mcp -> independently running adapter
  -> public Workstream HTTP API -> PostgreSQL
```

Use signed test tokens through normal verification, local bootstrap for the first Access Administrator and public grant APIs for subsequent authority. Do not disable guards or seed database authority to make a case pass. The harness may inspect database and audit state for proof; the adapter itself has no database access.

Exercise all 27 tools through HTTP MCP. For equivalent actors and intent, compare MCP execution with direct API execution for API outcome, response contract, database state, replay results, denial and audit provenance. Use equivalent isolated fixtures for the two paths so the first mutation does not change the second path's starting state.

Release requires 27/27 positive cases, corresponding negative and replay cases, zero unresolved schema drift, zero credential leakage, correct direct-API parity, independent package installation and a reviewed dependency lock. SDK tests, mock request counts, API-only drills and successful tool listing are supporting evidence, not substitutes for this gate. Fixture-token proof remains separate from proof of the deployed Flow service.

### Confirmed response-data policy

The maintainer's [clarification](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654493551) confirms that tool results return the declared Workstream API fields the caller is authorized to receive, including profile data, guide content and pagination cursors. A declared response field is allowed even when its value also appeared in the request. Do not add an indiscriminate input-echo filter that removes valid response data. Credentials must never appear in results. Sensitive business content stays out of logs, traces and diagnostic errors; raw arguments are not copied into diagnostic output. These rules preserve authorized response data without adding fields unavailable through the API.

## 9. Chunk Map and PR Boundaries

The caller-token decision is settled. WS-MCP-002-01 delivered the independent
profile-read foundation in PR #418. WS-MCP-002-02 delivers profile editing and
exact-project authorization context, bringing the catalogue to three tools.
Reconcile each later binding with its public API when that chunk starts; do not
reopen credential architecture or require all 27 implementations at once.

The following stable IDs replace the four broad headings. Rows 01 and 02 are
implemented; rows 03–10 remain planned, with proposed ownership under `mcp_server/`, not
claims that later tools exist. Each row is one bounded outcome. Tool names omit
only the common `workstream_` prefix; all 27 names in section 6 appear exactly
once. Each row also owns its change record and affected tests/docs, not backend
product behavior.

| Change ID and outcome | Depends on | Owned modules and exact new tools | PR acceptance evidence and next usable boundary |
| --- | --- | --- | --- |
| WS-MCP-002-01: one authenticated self-profile read through an independently installed adapter | Selected profile schema capture and confirmed section 5 design; [first contract](WS-MCP-002-01.md) | Package/container/configuration, `workstream_mcp/{server,auth,http_gateway,errors,schemas}.py`, `tools/profile.py`; `profile_get` only | Package-only install/container, protocol/credential isolation/privacy tests, real profile API parity, missing-header no-dispatch and invalid-token API-denial proof. Leaves one protected path and test harness for later bindings, not 27 working tools. |
| WS-MCP-002-02: own profile editing and project authorization context | 01 | `tools/profile.py`, `tools/context.py`, their schemas/registry entries; `profile_update`, `authorization_context_get` | Profile omission/null/normalization/atomic rejection, unkeyed PATCH and no automatic retry; exact-project context, revoked/foreign access and safe data tests. Leaves complete self-service surface. |
| WS-MCP-002-03: inspect authorization definitions and administrative projections | 01 | `tools/access_reads.py`; `permissions_list`, `admin_roles_list`, `admin_grants_list`, `actor_admin_grants_list`, `actor_get`, `actor_identity_link_get` | Frozen catalogue/projection fields, pagination/cursor behavior, admin/audit/ordinary denial matrix and no contact/subject leakage. Leaves administrative readback for mutation proofs. |
| WS-MCP-002-04: issue and revoke administrative grants | 03 | `tools/admin_grants.py`; `admin_grants_issue`, `admin_grants_revoke` | Exact receipts/history, scope and self-grant checks, last-admin protection, key mismatch/replay/current-authority checks and lost-response handling. Leaves HTTP-owned administrative authority changes. |
| WS-MCP-002-05: manage actor and identity-link admission | 03, 04 | `tools/actor_lifecycle.py`; `actor_suspend`, `actor_reactivate`, `actor_deactivate`, `identity_link_revoke`, `identity_link_reactivate` | Each reason/key boundary, self/final-admin guards, terminal deactivation, revoked-link admission and replay/current-state tests. Leaves bounded lifecycle administration, no new identity registration. |
| WS-MCP-002-06: create and read project shells | 01, 04 | `tools/projects.py`; `projects_create`, `projects_get` | System-manager create, duplicate slug/replay/conflict and administrative versus three-field contributor read projections. Leaves exact project selectors for project-scoped chunks. |
| WS-MCP-002-07: manage project participation | 03, 06 | `tools/project_grants.py`; `contributor_candidates_list`, `project_grants_issue`, `project_grants_list`, `project_grants_get`, `project_grants_revoke` | Populated bounded cursors, qualification fields, both roles, cross-project/target substitution, revoked access, replay/concurrency and unchanged-state denials. Leaves project access management, not task eligibility logic in MCP. |
| WS-MCP-002-08: declare guide documents and edit draft metadata | 06; agreement on upload exclusion | `tools/guides.py`; `guides_create`, `guides_update` | Current examples/documents schema, waiting-setup response, summary-only PATCH, immutable-field rejection, UTF-8/aggregate limits and replay. Leaves document declarations; actual uploads/setup completion stay outside MCP. |
| WS-MCP-002-09: configure draft review and revision policies | 08; agreement on selector recovery limitation | `tools/policies.py`; `review_policy_put`, `revision_policy_put` | Correct initial/current `If-Match`, omission versus defaults, human-review mode, stale/malformed selectors, lineage, exact-project denial and replay. Leaves draft policy configuration without approval/activation tools. |
| WS-MCP-002-10: prove the assembled 27-tool release | 02, 05, 07, 09 and their ancestors; agreed live identity/client environment | `tests/integration/`, release drill, deployment/client docs and contract snapshot validation; no new tools | Complete ten-suite matrix, 27/27 positives plus per-tool negatives and mutation replay, actual client-to-adapter-to-API/PostgreSQL parity, deployed proxy no-store/caller isolation and independent container. Leaves a release candidate for human decision, not an automatic merge/deploy. |

The dependency column describes technical prerequisites, not permission to start another chunk automatically. Default delivery follows row order. Independent branches may be proposed only after checking shared registry/schema ownership. One chunk finishes with its checks, focused review and human review/merge direction before beginning the next. If a chunk grows beyond its coherent behavior, revise its contract/map before adding unrelated implementation; do not silently combine rows into one PR.

Every binding chunk includes its route/body/query/header/status tests, public API authorization and error parity, snapshot drift checks, privacy checks, and relevant mutation replay/failure tests from its first PR. Tests may use public-API-only fixtures for prerequisite state that has no MCP tool; fixture setup must not masquerade as catalogue coverage. The final drill assembles existing proofs and adds deployed/live integration coverage; it is not the first test of any tool. Each partial catalogue is asserted exactly, with zero prompts/resources and no placeholder tools.

### Binding-specific implementation prerequisites

- **Catalogue and schemas:** for each chunk, capture only its selected operations and transitive schemas from `/openapi.json` of the pinned backend, with source SHA and explicit differences from the historical mapping. Review those differences in that implementation PR. WS-MCP-002-01 needs only the self-profile contract; reconciling all 27 tools is not a prerequisite to starting it. The full catalogue is assembled and verified by 10.
- **Credential contract (settled):** use section 5 unchanged caller-token forwarding. No further resource registration, token exchange or owner credential decision is required for this design.
- **Workflow limits:** agree that document upload/setup completion and recovery of lost/stale policy selectors remain outside this catalogue. No automatic extra endpoint, hidden route or write-as-read workaround.

The first record includes the earlier experiment and the delivered independent
foundation. Before each later chunk starts, create its own combined record from
the current template. Earlier planning and experiment context is retained here;
do not create another record to repeat completed packaging.

I will follow the current Commitrail process: one initiative overview for this multi-PR effort and one change record for each implementation PR. Each record will state the allowed files, non-goals, acceptance criteria, risks, and required review. Open PRs will be checked for overlapping changes before each boundary starts.

Review will follow the repository's risk routing, including security and architecture for the foundation. Relevant lint, type checks, tests, coverage requirements, and repository gates will be preserved. Roadmap impact will be assessed in the same PR. GitHub will hold current checks and approvals; the repository records will hold durable decisions. Merge remains a human decision.

## 10. Contributor continuation

PR #418 delivered [WS-MCP-002-01](WS-MCP-002-01.md), and
[WS-MCP-002-02](WS-MCP-002-02.md) adds the two remaining self-service tools.
The resulting catalogue has three of the proposed 27 tools: profile read,
profile update and exact-project authorization context. The package remains an
independently deployed custom bearer-header adapter, not a public deployment.

The next usable boundary is WS-MCP-002-03: authorization definitions and
administrative read projections. Start it only after this chunk is reviewed and
merged, recapture each selected operation from then-current backend OpenAPI, and
preserve the existing fixed-route, caller-token and no-private-import boundaries.

Keep the remaining 24-tool inventory and later mutation boundaries. Guide uploads/setup
completion and missing policy-selector recovery remain outside that inventory;
do not silently add tools to repair those workflow limits. GitHub permissions
govern contribution; these technical prerequisites are not another approval system.

## References

- [Maintainer API handoff](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654783507)
- [Fixed public API drill and cases](../../../docs/engineering/external-api-drill.md)
- [API drill findings and fixes](../../../docs/engineering/external-api-drill-findings.md)
- [Maintainer clarification: privacy, API handoff, headers and caching](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654493551)
- [Tested Streamable HTTP protocol baseline](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Maintainer review addendum: dispatch and conformance requirements](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5653317895)
- [Workstream contribution guide](../../../CONTRIBUTING.md)
- [Commitrail guidance](../../README.md)
- [Workstream capability status](../../../docs/roadmap_status.md)
- Workstream MCP interactive design shared in the group, baseline `c69ff85`.
- `Flow-Identity-v0.1-Interactive.html`, approved architecture dated 10 September 2026. Used for issuer ownership, token validation, client registration, renewal, suspension, and key rotation.
- `Flow-Identity-Human-and-Agent-Experience.html`, future extension design dated 11 September 2026. Used for separate agent credentials, shared human accountability, identity links, local delegation, and the boundary between agreed direction and pending implementation.
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
