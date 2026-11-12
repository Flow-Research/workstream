# Workstream: clean Keycloak development setup

## Implementation specification and coding-agent handoff

**Status:** Corrected implementation plan for a disposable development environment. Planned behavior below is not a claim of implementation or deployment. This revision replaces the earlier specification in full.

**Prepared:** 2026-11-12
**Repository reviewed:** `Flow-Research/workstream`
**Source baseline:** `94334ccf4085c26c7bfaa054465fc05cfbdad1fc`
**Delivery order:** Fresh identity provider and Workstream setup, independent token-exchange proof, then MCP OAuth and a real Garden connection—all within this delivery objective.
**Explicit user decision:** No backward compatibility and no migration. Existing development accounts, credentials, actor records, project data, and test history may be discarded and recreated. Do not build preservation or identity-replacement machinery.

## 1. Goal and decision

Replace the temporary Rust demo identity issuer with **self-hosted Keycloak**, using Keycloak's existing login screens, account management, OAuth/OIDC implementation, signing keys, sessions, and administration tools.

The completed work must let a newly provisioned person sign in through a browser, obtain a short-lived access token, and use a freshly initialized Workstream environment through its ordinary actor-provisioning and authorization paths. It must also independently prove that a token intended for MCP can be exchanged for a token intended for the Workstream API, without another password prompt, then use that boundary in the actual Workstream MCP server and prove browser authorization from Garden. Provider-only proof is an intermediate milestone, not completion.

The earlier specification incorrectly assumed that old users and records had to survive. That assumption is removed. Start clean: create new Keycloak users, let Workstream create new actors, and configure the development roles/projects through existing owner operations. A user must resolve to the same new actor across direct API access and later token exchange; there is no requirement to preserve an actor from the Rust demo.

We are integrating a maintained identity product. Do not implement an OAuth server, password verifier, consent engine, or custom login frontend. Do not extend the demo Rust issuer into a production identity platform. No Keycloak hosted-service account or subscription is required for this deployment; it runs on infrastructure we control. Infrastructure, DNS, administrative access, and ongoing operation still need an owner. [K1–K4]

### 1.1 Ownership

| Component | Owns |
|---|---|
| Keycloak, presented to users as Flow Identity | Credentials, login, required password changes, authentication sessions, OAuth consent, clients, scopes, signing keys, and token issuance. |
| Workstream | Actor records, user admission, actor lifecycle, system roles, project memberships, project permissions, and all product history. |
| Workstream MCP | Client-facing MCP authorization discovery, validation of MCP credentials, exchange into API credentials, and requests to Workstream under the resolved user. |
| Deployment operator | Host, DNS, TLS, restricted administration, secrets, monitoring, and the bounded development reset/setup. |

A Keycloak account, realm role, or administrative privilege must not confer a Workstream role. The scope `workstream:access` permits an authentication credential to enter Workstream's existing authorization process; it is not a project grant. [W2–W5]

### 1.2 Fixed decisions

| Item | Decision |
|---|---|
| Provider | Self-hosted Keycloak, version **26.8.2** as the researched baseline, with immutable container digests. |
| Realm | `flow`, display name `Flow Identity`. |
| Public identity origin | `https://identity.flowresearch.tech`. |
| Trusted issuer | `https://identity.flowresearch.tech/realms/flow`, exactly, without a trailing slash. |
| Login | Authorization code flow with mandatory PKCE S256; Keycloak's stock UI. |
| Workstream API audience | `workstream-api`, consistently in all fresh configuration. `API_AUDIENCE` below means this exact value. |
| MCP resource identifier | `https://workstream.flowresearch.tech/mcp`. |
| Existing development state | Disposable. Reset the identified Workstream development state and initialize the supported current schema. |
| Actor model | Keep the existing one-identity-link-per-actor model and normal first-access provisioning. |
| Accounts and credentials | Create fresh Keycloak accounts and credentials; no account mapping, password import, or forced correspondence to old IDs. |
| API verification | Exact issuer, pinned JWKS and RS256, existing claims and local authorization checks; explicitly configured offline JWT verification in this phase. |
| Delegated API access | Keycloak Standard Token Exchange V2, same realm, fixed source/target policy; prove it independently before changing MCP. |
| Deployment | Existing hosted environment and Caddy, subject to capacity checks; dedicated identity database and database credential. |

`API_AUDIENCE` is shorthand for the selected value `workstream-api`, not a new public configuration variable. The inspected repository has differing example/default values; align the affected active settings, examples, clients, and tests to the single selected value. Do not retain old audience aliases. [W6]

If either public origin differs in the actual installation, record the corrected deployment binding once and apply it everywhere before creating clients or tokens. Do not support competing issuer spellings or aliases.

### 1.3 Scope of this delivery

Deliver the provider deployment, reproducible provider configuration, login/proof tooling, a bounded development reset/setup procedure, removal of obsolete demo issuer wiring, a verified fresh Workstream authentication path, and Garden-to-Workstream MCP OAuth through the actual connector.

There is no requirement for a populated-database upgrade, old-user continuity, old-token support, dual issuers, old/new deployment modes, a preservation backup, or rollback to the Rust issuer. Ordinary schema initialization using the repository's current Alembic chain still applies. This task introduces no migration-specific schema or authorization features.

Include the MCP server's OAuth credential validation, protected-resource metadata, `401` challenges, real Garden client registration, token-exchange runtime, and a real Garden connection. Implement these after the independent provider proof, but do not close the overall goal before they pass. Inspect Garden's actual connector before choosing callbacks, client type or registration mechanism; no callback or client capability is assumed. A standalone harness is not a substitute for the Garden test.

Also defer social login, enterprise federation, self-registration, custom UI, custom Keycloak extensions, preview delegation features, generalized multi-account linking, and a new identity product API. The future dedicated team service can use these standard interfaces without Workstream taking ownership of passwords.

## 2. Read the existing owners before editing

Read `AGENTS.md`, `CONTRIBUTING.md`, current architecture decisions, the current capability ledger, and the relevant authorization owners at the implementation checkout. Reconcile changes since the pinned baseline. Use the repository's bounded-change, focused-test, review, PR, and human-merge workflow. The user has explicitly chosen a development reset and does not require preserving old data. Apply that decision to the identified Workstream development resources, not unrelated databases, shared host services, or other projects. [W1]

The important inspected behavior is:

1. Workstream already verifies external tokens. It does not own login or credential storage.
2. The verifier requires `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `subject_kind`, and `scope`. Humans need `subject_kind=human` and `workstream:access`. Services have a distinct contract.
3. An unknown, valid human identity can automatically create a new actor. Use this existing path after initializing the clean database.
4. Each actor currently has exactly one total identity link. Keep the ORM, unique constraint, and deferred guard enforcing that model.
5. The existing first Access Administrator bootstrap and normal role/project/service-actor operations provide the setup path. They do not need an identity-replacement action.
6. The CLI reads `WORKSTREAM_TOKEN` and calls the API; it does not acquire OAuth credentials or save sessions.
7. Hosted deployment validates exact environment keys, service topology, mounts, ports, and startup procedures. A new Compose file alone is insufficient. [W3–W9]

Do not implement the earlier proposal's current-link pointer, historical replacement links, nullable verification exception, replacement receipts, migration principal, mapping manifest, reversal command, or additional lifecycle guards. None is needed for this fresh setup. Keep ordinary product authorization and immutable-history protections intact for records created after initialization.

## 3. Target behavior

### 3.1 Direct Workstream access

The login helper opens Keycloak in the user's browser. The user authenticates and, when required, changes their temporary password and approves the client. The helper redeems the authorization code with PKCE and receives an API access token. On first valid access, Workstream creates the actor through its existing flow. Subsequent tokens for the exact same issuer/subject resolve to that actor and are evaluated against locally assigned permissions.

No password, browser session, or Keycloak admin credential enters Workstream's database or API.

### 3.2 MCP access: independent proof, then the real Garden connection

A separate proof client obtains an MCP access token. The confidential `workstream-mcp` client exchanges that access token at Keycloak's token endpoint for an API access token. Both tokens identify the same user in the same realm. The API token has the API audience; the original MCP token does not.

The exchange itself involves no browser or password prompt. An initial login or a new client's consent screen may still be required when establishing a client session. An existing Keycloak browser session can satisfy later authentication according to the realm's session policy.

Token exchange is our chosen boundary between the services, not a mechanism mandated by MCP. The MCP adapter must use the exchanged token for API calls rather than forward the MCP token unchanged. [K4, S1–S3]

### 3.3 Authority remains local

The exchange must preserve the user's `sub`. It must not use client credentials to turn the request into a generic service account, accept a user ID supplied in a tool argument, or mint a Workstream administrator role. Workstream must still reject an inactive actor, a revoked current identity link, or a request outside the user's project access.

## 4. Deployment and public routing

### 4.1 Runtime and image

Use the released Keycloak **26.8.2** distribution as the baseline. Resolve and record its real image digest; do not invent a digest or use `latest`. If a newer security release is required when implementation begins, record the version change and rerun the affected proof suite. This baseline includes relevant token-exchange lifetime fixes. [K2, K5]

Use production startup. An optimized image built from the pinned official image is acceptable to enable PostgreSQL, health checks, and metrics at build time. It must contain no custom identity-provider code, custom Java SPI, or credentials. Record both the upstream and final deployed digests. Do not use `start-dev` in hosted environments. [K6]

Measure existing API/worker/database/native-checker steady-state and peak headroom before restarting this stopped development host for deployment. The current intended host has 2 vCPU and 8 GiB RAM; a 2 GiB identity limit is a budget to qualify, not proof that all services fit. Include concurrent login and checker activity in the capacity proof. Do not silently resize the paid instance or reduce checker safety limits.

Run a single Keycloak instance initially, with local cache configuration and no publicly exposed clustering port. Start with a 2 GiB memory limit, a bounded database connection pool of at most 10, and explicit CPU/PID limits justified by measured startup and login behavior. Inspect host headroom first; do not reuse the demo issuer's small Rust limits. If capacity is insufficient, report the measured deficit and a concrete hosting change instead of weakening runtime checks.

### 4.2 Database isolation

Prefer the existing supported PostgreSQL server when its capacity and isolation are sufficient. Create a separate database named `flow_identity` and a separate runtime owner/login named `flow_identity`.

Requirements:

- Keycloak never uses the Workstream database, schema, role, or migration credentials.
- The identity role has no superuser, role-creation, database-creation, replication, or row-security-bypass privilege.
- Remove public access to the identity database and explicitly scope database access. Prove the identity runtime role cannot read or create objects in the Workstream database, and Workstream runtime roles cannot read identity data. Inspect existing grants before modifying shared-cluster permissions.
- Add a dedicated private `identity_db` network containing the identity service and PostgreSQL. Publish no additional database port. Update the deployment topology validation for this deliberate network change.
- Provision/reset the named development databases through bounded administrative operations. Fresh-volume initialization scripts do not rerun on an existing cluster. Reset a dedicated Workstream development volume only if all its contents are within the selected reset scope; otherwise reset named databases without deleting the shared cluster.
- Validate the existing PostgreSQL version against the pinned Keycloak release's supported database matrix. [W8, K7]

The database is authoritative identity state, including credentials, provider configuration, sessions, and signing material. A deliberate development reset may discard it and recreate it from configuration; an ordinary restart must retain it.

### 4.3 Hostnames and endpoints

Configure:

```dotenv
KC_HOSTNAME=https://identity.flowresearch.tech
KC_HOSTNAME_ADMIN=https://identity-admin.localhost:19443
KC_HOSTNAME_BACKCHANNEL_DYNAMIC=false
KC_HOSTNAME_STRICT=true
```

The expected public endpoints are:

| Purpose | URL |
|---|---|
| Issuer | `https://identity.flowresearch.tech/realms/flow` |
| OIDC discovery | `https://identity.flowresearch.tech/realms/flow/.well-known/openid-configuration` |
| JWKS | `https://identity.flowresearch.tech/realms/flow/protocol/openid-connect/certs` |
| Authorization and token endpoints | Read and validate them from that discovery document. |

Use the existing Caddy process as the only public HTTPS entrypoint. Route `/realms/flow`, `/realms/flow/*`, and required `/resources/*` traffic to Keycloak without stripping the realm path. Deny administrative and unlisted paths on the public listener, including `/admin`, `/admin/*`, `/realms/master`, `/realms/master/*`, health, and metrics. Do not expose every realm as a convenience. Discovery must actually work from outside the host. [K8, K9]

Caddy must overwrite forwarded metadata with verified values. Keycloak may trust forwarded headers only from the observed, explicitly configured proxy addresses. Derive those addresses from the real host/container path; do not trust arbitrary client headers or every private subnet.

Use TLS between Caddy and Keycloak. Reserve `127.0.0.1:18443` on the host for Keycloak's container port `8443`, with a separately managed upstream certificate/key and verification by Caddy. Do not disable TLS verification. Remove the old demo issuer's listener. The upstream TLS key is distinct from the realm's token-signing keys.

Keep management port `9000` private. Probes must use a supported private route or network and valid TLS as configured. Do not assume the Keycloak image contains `curl` or publish management endpoints to make probing easy.

### 4.4 Private administration

Add a second listener to the **same Caddy process**:

```text
https://identity-admin.localhost:19443
bind 127.0.0.1
private TLS certificate issued by the existing Caddy internal CA
```

An authorized operator reaches it through an SSH local forward, with the private CA trusted on their workstation. It must not bind on all interfaces. Do not add a second independent Caddy process that competes for public ports or state.

Set the **master realm** attribute `frontendUrl` to the private base URL:

```json
{
  "attributes": {
    "frontendUrl": "https://identity-admin.localhost:19443"
  }
}
```

Merge this attribute through supported Admin REST/CLI operations; preserve other attributes. Do not append `/realms/master` to that value. Leave the `flow` realm's `frontendUrl` unset so it inherits the fixed public origin. `KC_HOSTNAME_ADMIN` alone is not enough to guarantee that master authentication uses the private origin. Configure this during private bootstrap, then prove the entire administration browser flow on the pinned image. [K9, K10]

Use Keycloak's supported initial administrator setup once, create a named administrator, require MFA for administrative access, verify recovery access, and remove the temporary bootstrap administrator/secret from routine runtime configuration. The Rust-specific local administrator initializer is removed; this does not eliminate Keycloak's initial administrator setup or Workstream's independent first Access Administrator bootstrap. Keep administrative authority separate from user access and Workstream roles. Never publish admin credentials in an example realm export.

### 4.5 Integrate with hosted release ownership

Inspect and update the actual owners, including:

- `deploy/hosted/compose.py`: composition, initial startup, and resume behavior.
- `deploy/hosted/preflight.py`: accepted keys, selected files, exact services, networks, mounts, secrets, ports, and readiness.
- `deploy/hosted/release.env.example`: complete nonsecret configuration and secret-file references.
- `deploy/hosted/public.Caddyfile`: public and private routing.
- Relevant Compose overlays, shutdown procedures, and hosted runbooks.

Replace the active demo issuer deployment with Keycloak directly. Remove the demo service, its obsolete Compose overlay, routes, environment keys, signing-secret wiring, startup helpers, and tests/docs that exist only to support it. Trace shared consumers before deleting a file so reusable provider-neutral code remains with its owner. The Git history is sufficient for discarded implementation history; do not ship a fallback Rust service or a compatibility mode.

Do not loosen `DEMO_IDENTITY_*` checks to disguise Keycloak as the demo. The existing demo-specific JWKS path, origin, port, and algorithm assertions must be replaced through the correct new deployment contract.

The MCP container shares the API service's network namespace in the inspected deployment. If the API container is replaced, stop MCP first, replace the API, force-recreate MCP, and verify the resulting namespace. Apply the Keycloak settings consistently to all relevant API and worker processes during fresh setup. [W8, W9]

## 5. Realm and user configuration

### 5.1 Realm behavior

Use Keycloak's stock login, consent, required-action, account, and admin interfaces. Set the display name to `Flow Identity`; a logo or simple theme setting is optional, not a delivery prerequisite.

Configure:

| Setting | Required value/behavior |
|---|---|
| Self-registration | Disabled. Accounts are explicitly provisioned by an authorized identity operator. |
| Social/federated identity | None in this phase. |
| Human password policy | Minimum 14 characters; use Keycloak's standard password policy implementation. |
| Brute-force protection | Enabled, with tested temporary lockout and recovery. |
| Email-based recovery/verification | Do not require or advertise it until SMTP and delivery have been configured and proved. |
| Remember-me | Disabled initially. |
| SSO session idle | 1,800 seconds. |
| SSO session maximum | 28,800 seconds. |
| Browser/API-source access token life | 300 seconds. |
| Refresh rotation | Revoke Refresh Token enabled; Max Reuse `0`; serialize refresh in the helper. |
| Offline access | Not assigned to these clients. |
| Signing algorithm | RS256, with a real `kid` and the corresponding published JWK. |

Treat these as the selected deployment policy, not claims about product defaults. Record any required adjustment with its reason and changed acceptance expectation.

### 5.2 Human marker

Workstream requires a reliable `subject_kind` claim. Do not attach an unconditional `human` claim to every token in the realm: that can misclassify service accounts.

Define a managed user attribute named `workstream_subject_kind`:

```json
{
  "name": "workstream_subject_kind",
  "multivalued": false,
  "permissions": {
    "view": ["admin"],
    "edit": ["admin"]
  },
  "validations": {
    "options": {"options": ["human"]}
  }
}
```

It has no default, no group-provided value, and no user-edit permission. Set it to `human` only for deliberately provisioned human users whose provider record has no service-account association. Ensure unmanaged-attribute behavior cannot supply a competing value.

Create a hidden default client scope, `workstream-identity`, with **Include in token scope OFF**. Use the built-in user-attribute mapper to put the attribute into the access token as the scalar string claim `subject_kind`. Do not place it in ID tokens or user-info solely to satisfy the API.

Representative mapper configuration, to be validated against the pinned release's Admin API/export schema:

```json
{
  "name": "workstream-subject-kind",
  "protocol": "openid-connect",
  "protocolMapper": "oidc-usermodel-attribute-mapper",
  "config": {
    "user.attribute": "workstream_subject_kind",
    "claim.name": "subject_kind",
    "jsonType.label": "String",
    "access.token.claim": "true",
    "id.token.claim": "false",
    "userinfo.token.claim": "false",
    "introspection.token.claim": "true",
    "multivalued": "false",
    "aggregate.attrs": "false"
  }
}
```

An absent or malformed marker must cause Workstream human verification and human token exchange to fail. A service account must not gain human authority by choosing a scope. [W3, K11]

### 5.3 Accounts and passwords

Create fresh development users through Keycloak's authenticated Admin API or stock admin UI. Keycloak's user ID is the opaque `sub`; do not derive it from email or force it to equal a Workstream UUID.

For newly created accounts, generate a unique random temporary password, require `UPDATE_PASSWORD`, and distribute the temporary credential through the operator's approved private channel. The coding agent can provision accounts and prepare the workflow, but cannot choose a user's permanent password or complete their MFA enrollment. Do not send credentials to people without explicit authorization for that communication.

Discard the old Rust account/password state within the development reset. There is no hash conversion, account import, old-to-new identity mapping, or requirement for users to retain their previous password. Temporary-password rotation is a normal new-account setup action.

Create separate fresh test users for allowed, forbidden, suspended, and revoked-access scenarios. Establish their Workstream state through normal product operations. Keycloak enabled state never overrides Workstream actor/link status.

## 6. Clients, scopes, audiences, and exchange

### 6.1 Separate clients with explicit responsibilities

Create the following four provider/proof clients first. All IDs are case-sensitive. Add a separate real Garden client after inspecting its connector; do not reuse a loopback proof client or the confidential MCP exchange client for Garden browser login. Record its exact client ID, callbacks, public/confidential type and supported PKCE/registration behavior before configuration.

| Client ID | Purpose | Configuration |
|---|---|---|
| `workstream-cli-login` | Browser login helper obtaining direct API credentials. | Public OIDC client; authorization code only; PKCE S256 required; exact redirect `http://127.0.0.1:17843/callback`; consent enabled. |
| `workstream-mcp-proof` | Independent identity-stage MCP-token proof. | Public OIDC client; authorization code only; PKCE S256 required; exact redirect `http://127.0.0.1:17844/callback`; consent enabled. |
| `workstream-mcp` | Confidential requester for server-side token exchange. | Client authentication on, `client_secret_basic`; Standard Token Exchange V2 enabled; consent on this requester disabled; all other credential acquisition flows disabled. |
| Exact value of `API_AUDIENCE` | Workstream API resource/audience representation. | All login and grant capabilities disabled; no credential distributed to the API. |

For the public clients, disable implicit, direct-access/password, service-account, device, CIBA, JWT authorization grant, and token-exchange capabilities. Do not configure a client secret. No wildcard redirects or web origins. The loopback exceptions are local callback endpoints, not hosted plaintext login endpoints.

For the exchange client, also disable standard/browser flow and service accounts. Its secret authenticates the requesting application; it must not permit a client-credentials token to become a human API token. Store the secret privately. During provider-only qualification, give it only to the operator proof harness. During MCP activation, mount the same explicitly scoped credential through the MCP deployment secret owner. Never give it to Garden browser code, public login helpers, tool arguments or the Workstream API.

Keep **Full Scope Allowed OFF**. Remove unnecessary default `roles`, broad `profile`, and `offline_access` scopes from these clients. Replace broad profile defaults with the explicit bounded profile mapping below; do not omit required account email merely to minimize claims. Retain the built-in `basic` scope and verify that `sub` remains present. There must be no role-based audience resolver or inherited mapper adding unexpected service audiences. [K3, K4, K11]

After the real Garden client is qualified, disable the proof client if it is not actively needed. It is not a registration for a real external MCP client. Later clients need their own reviewed client IDs, exact callbacks, and policy.

### 6.2 Scope assignment

Create `workstream:access` as a **literal** client scope, with parameterized-scope behavior off and **Include in token scope ON**. It conveys the existing API entry permission string and has no audience mapper. Give its consent text a clear explanation of Workstream access.

Create separate audience-binding scopes so a public client cannot ask for both resource types:

| Scope or mapper | Assigned to | Effect |
|---|---|---|
| Built-in `basic` | Both public proof/login clients, registered Garden client and exchange client, default | Retain standard token claims, including `sub`. |
| `workstream-identity` | Both public clients and exchange client, default; same contract for the registered Garden client | Administrator-controlled human marker plus bounded issuer profile observations; hidden from the `scope` string. |
| `workstream:access` | Optional on proof/login clients and registered Garden client; default on exchange client | Literal permission string; login helpers and Garden must request it explicitly. |
| `workstream-api-audience` | Optional on `workstream-cli-login`; hidden default on `workstream-mcp` | Add the exact API resource client ID to `aud`; Include in token scope OFF. |
| `workstream-mcp-audience` | Optional on `workstream-mcp-proof` and the exact registered Garden client only | Add `workstream-mcp` and the canonical MCP resource URL to `aud`; Include in token scope OFF. |

The API audience binding is a hidden default scope on the exchange client.
The real provider proof found that its downscope executor filters a dedicated
client mapper, making the requested API audience unavailable. The hidden default
scope retains that binding without granting another visible permission scope.

The exchange client has **no optional scopes**. Do not make the audience-binding scopes realm defaults or assign the API binding to the MCP proof client or Garden client. Avoid duplicates inherited through client templates/scopes.

The two public authorization requests use:

```text
Direct API: openid workstream:access workstream-api-audience
MCP proof/Garden: openid workstream:access workstream-mcp-audience
```

The MCP token's two audience entries identify the same logical MCP service: its Keycloak requester client ID and its canonical resource URL. The client ID is needed by Keycloak's exchange requester check. They must not include the API audience. [K4]

### 6.3 Token contracts

Normalize `aud` to a set when testing; JSON string versus single-element-array encoding is not an authorization distinction.

| Claim/property | Direct API token | MCP source token | Exchanged API token |
|---|---|---|---|
| `iss` | Exact public `flow` issuer | Same | Same |
| `sub` | Target Keycloak user ID | Same user ID | Exactly equal to source `sub` |
| `aud` set | `{API_AUDIENCE}` | `{workstream-mcp, https://workstream.flowresearch.tech/mcp}` | `{API_AUDIENCE}` |
| `subject_kind` | `human` | `human` | `human` |
| Permission scope | Contains `workstream:access` | Contains `workstream:access` | Contains `workstream:access`; no elevated permission |
| Lifetime | At most 300 seconds | At most 300 seconds | At most 120 seconds and no later than source expiry |
| Token type used by API | Access token | Must be rejected by API | Access token |
| Refresh credential | Rotated browser-client refresh token | Rotated browser-client refresh token | None |

All access tokens must satisfy the existing verifier's other bounds and checks, including `iat`, `exp`, `jti`, signature, and `kid`. ID tokens are never API bearer credentials. Include the canonical Keycloak account `email` in direct, MCP-source and exchanged human access tokens from the start. Require an email when provisioning these human accounts. Map an optional bounded `name` when present; omit absent values. Use supported stock protocol mappers, preserve the current Workstream claim bounds, and prove the claims on each token path. Do not claim mailbox verification without configured verification and delivery. These are profile observations, not identity-link or permission authority. [W3, W6]

If generated tokens contain an extra audience such as `account`, fix the scope/mapper configuration. Do not make the acceptance tests permissive to accommodate an accidental audience.

### 6.3.1 Preserve the delivered profile contract

Email/password remains the human sign-in experience, but the password is entered only into Keycloak's stock browser UI. The public clients' password/direct-access grant remains disabled. An identity administrator creates the account with a temporary password; Keycloak requires its replacement before issuing usable credentials. No SMTP prerequisite is introduced.

Workstream email is read-only in REST, CLI and MCP. A later signed issuer email observation synchronizes through the existing authorized self-profile operation using the existing strictly-newer `iat` rule. Equal/older observations cannot revert email; absent values do not erase it. Identity is still exact issuer plus subject, never email. Keycloak email changes must be governed there, not exposed as Workstream edits.

An optional signed name seeds initial admission only. Later issuer tokens must preserve local display-name edits and explicit clears. Verify this behavior through direct API and exchanged MCP access, including the existing self-profile tools. Do not introduce new profile storage or a second synchronization mechanism.

### 6.4 Exchange request

Send an HTTPS form request to the token endpoint discovered from the fixed issuer. Authenticate the `workstream-mcp` client using `client_secret_basic`.

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=<the in-memory MCP access token>
subject_token_type=urn:ietf:params:oauth:token-type:access_token
requested_token_type=urn:ietf:params:oauth:token-type:access_token
audience=<exact API_AUDIENCE>
scope=workstream:access
```

The notation above specifies a request; it is not a shell command containing real credentials. Keep the source token and secret out of argv, shell history, URLs, logs, and evidence files.

No `requested_subject`, arbitrary target, external issuer import, user-supplied audience, or user-supplied exchange URL is allowed in the helper or MCP runtime. Standard V2 here exchanges Keycloak tokens from the same realm. It does not turn an old Rust token into a Keycloak token. [K4, S3]

### 6.5 Enforce the exchange boundary at the issuer

Use stock Keycloak client policies, selected only for `workstream-mcp`:

- `downscope-assertion-grant-enforcer`: requested permission scopes cannot exceed the source token's scopes.
- `jwt-claim-enforcer`: the source `subject_kind` must match `^human$`.
- Fixed configured audience availability: only the API target is available on this requester.

Use a supported exact-client policy condition or a dedicated administrative marker to select this client. Export the resulting policy and prove that it applies to this client. Resolve serialized configuration keys from the pinned release rather than inventing Admin API fields. Hidden default mapper scopes are acceptable only when they do not add permission scope or unintended audiences.

Set on the **exchange requester**:

```text
Access Token Lifespan = 120 seconds
Allow refresh token in Standard Token Exchange = No
Allow exchange token expiration after subject token expiration = OFF
```

Verify:

```text
exchanged.exp <= source.exp
exchanged.exp <= exchanged.iat + 120
exchanged.sub == source.sub
exchanged.aud == {API_AUDIENCE}
```

Do not assume the `audience` request parameter prevents scope escalation: scope enforcement is a separate policy requirement. Some unknown scopes can be ignored rather than rejected; the invariant is that no unauthorized scope or audience is issued. Prove the actual downscope policy with a controlled fixture scope in an isolated test configuration, then remove the fixture. [K4, K5, K12]

Do not enable legacy exchange V1, preview token-exchange delegation, JWT authorization grants, impersonation, or custom SPI code to get the proof to pass. This phase preserves the user's identity but does not promise an RFC 8693 `act` claim in Workstream's audit records; the current verifier does not carry such a claim into its authority model.

### 6.6 MCP integration and Garden compatibility boundary

The provider client configuration alone is not a declaration of full MCP OAuth interoperability. MCP authorization also requires resource discovery, HTTP challenges, resource-bound requests, and a registration method compatible with the actual client. Keycloak documents additional MCP-related features whose maturity must be checked at implementation time. [S1, K13]

Begin with preregistered proof clients and explicit audience mapping. Inspect the actual Garden connector and prefer an exact preregistered Garden client if it supports that path. Keep anonymous registration denied. If Garden requires another registration method, record the concrete gap and resolve its supported, bounded configuration before activation; do not enable unrestricted registration or invent a custom OAuth server.

Pin the MCP protocol version actually supported by Garden and Workstream and test its authorization requirements. Keycloak's documentation currently labels Resource Indicators and client-ID metadata support experimental. Do not claim stable generic interoperability from audience scopes alone. Prove Garden's authorization and token requests carry the canonical `resource`, and that the chosen pinned provider configuration issues only the intended MCP audiences. Document whether stock scope-to-audience mapping meets this specific integration or a narrowly enabled provider feature is required, including negative resource/audience tests. If a required behavior cannot be proved, report it as an unresolved delivery gap rather than declaring Garden connected. [K13, S1, S5]

MCP runtime requirements:

1. Publish protected-resource metadata at the standards-compliant path for the canonical MCP resource, advertise only the trusted Keycloak authorization server and relevant scopes, and return a correct `WWW-Authenticate` challenge with metadata discovery for unauthenticated requests. Update Caddy's exact allowed paths accordingly.
2. Validate incoming credentials against the trusted issuer/JWKS, MCP resource audience, lifetime, human marker and required scope before dispatching a tool or performing exchange. Reject API-only tokens at the MCP boundary; reject MCP-only tokens at the API boundary. Do not keep the old API-token forwarding path as a compatibility mode.
3. Exchange a valid MCP source token only for the fixed API audience using the confidential client. Keep the same user subject and enforce the documented output claims/lifetime. Never forward the original MCP token to the API. The existing API verifier and live local authorization remain authoritative.
4. Keep credentials bound to the caller/request. No global user token, actor supplied through tool arguments, cross-session token reuse or logged authorization headers. Do not replay product mutations automatically when exchange or a downstream response is uncertain.
5. Use the existing MCP SDK authorization facilities where suitable, with the repository's typed external-adapter convention for provider I/O. No Workstream login/password endpoints or custom authorization server. Garden obtains and renews its own browser-client credentials; the MCP server must not receive user passwords or browser refresh tokens.
6. Prove the real Garden browser consent/login, MCP initialize/tool discovery, an allowed tool call, a forbidden project call, expired credential renewal/re-login, and a second-user isolation case. Keycloak roles or Garden ownership must not grant Workstream authority. Native CLI API access remains separate and uses API credentials.

Keep MCP admission closed during the intermediate provider-only stage if its OAuth enforcement is not yet installed. Reopen only with the new credential boundary qualified. This is a staged deployment, not an old/new authentication fallback.

## 7. Workstream verifier and ordinary access

Keep the existing external-authentication adapter and local authorization owners. Configure the fresh release with:

```dotenv
WORKSTREAM_TOKEN_ISSUER=https://identity.flowresearch.tech/realms/flow
WORKSTREAM_TOKEN_JWKS_URL=https://identity.flowresearch.tech/realms/flow/protocol/openid-connect/certs
WORKSTREAM_TOKEN_AUDIENCE=workstream-api
WORKSTREAM_TOKEN_ALGORITHMS=RS256
WORKSTREAM_REQUIRED_HUMAN_SCOPE=workstream:access
WORKSTREAM_REQUIRED_SERVICE_SCOPE=workstream:service
WORKSTREAM_TOKEN_INTROSPECTION_MODE=disabled
```

Set `WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON` to a truthful explanation of this deployment's short-lived offline JWT policy. Do not copy an old explanation saying the issuer lacks introspection.

Retain the existing 30-second skew unless a reviewed operational need changes it. Preserve bounded token/header/payload sizes, exact issuer comparison, signature and JWK algorithm checks, safe JWKS retrieval, and rejection of untrusted key-location headers. Do not normalize issuer paths or silently accept both issuers. [W3, W6]

Offline verification means a previously issued token can remain cryptographically acceptable until its expiry plus configured skew, even after Keycloak logout or account disable. With this policy the upper bound is approximately 330 seconds for a newly issued direct token and 150 seconds for an exchanged token, subject to source expiry. Provider logout/disable must block new sessions or renewal as appropriate. Workstream's actor/link/project restrictions continue to be checked through their existing owners; do not claim immediate provider-side access-token revocation at the API. [K4]

Do not weaken local admission or authorization to accommodate new claims. Do not add login, password reset, user sessions, or Keycloak-admin endpoints to Workstream.

### 7.1 Fresh service identities

List only the service actors and credentials actually needed by the selected development deployment. Recreate required service actors through the existing service-actor owner using a real Keycloak-backed human administrator bearer. Capture the newly returned IDs in the deployment configuration.

The existing `workstream admin service-actor provision` command is available. Do not use `provision_local_service_actors.py` unchanged for hosted Keycloak: that helper issues local-development tokens internally. Do not add a local-token fallback to the hosted verifier. Distinguish owner-resolved internal service identities from any caller that actually needs an external service access token. [W4, W5]

If the current deployment actually requires an externally issued service token, configure a dedicated service client with its exact service subject, `subject_kind=service`, `workstream:service`, and API-only audience, then provision its actor through the existing owner. Keep that configuration separate from the four human/exchange clients. No service account receives the human marker or human scope by default. Do not introduce hypothetical service-token infrastructure for workers that already use fixed internal identities.

## 8. Clean development reset and initial setup

### 8.1 Reset contract

The selected Workstream development environment is disposable. Existing development accounts, password state, actors, role grants, projects, contributions, audit records, queued jobs, and associated test artifacts do not have to survive this change.

Reset the environment at the infrastructure boundary and initialize the current schema. Do not edit existing identity rows, relax immutable-record guards, or add a product API for deleting historical records. The normal runtime must continue to enforce Workstream's current invariants on newly created data.

The coding agent must produce an executable runbook using actual discovered resource names. A generic migration/reset framework is not required. The user's reset decision is already made; do not ask them to choose a preservation strategy or approve migration work they did not request.

### 8.2 Identify the exact reset scope

Record the selected Compose project/release, database endpoint and database names, exclusively owned queue/state resources, qualified artifact namespace and policies, scratch paths, and obsolete Rust identity state. This inventory identifies what to reset, not what to migrate.

Use named database reset when PostgreSQL is shared. An entire PostgreSQL volume can be recreated only when all its contents belong to this disposable development environment. Do not run blanket `docker compose down --volumes`, volume pruning, `FLUSHALL` on shared Redis, or deletion of a shared artifact bucket. Preserve the qualified S3 bucket, private prefix, IAM policies, retained objects and immutability protections. ART's closed policy validation binds those protections to the configured prefix; changing it for an identity reset would expand the storage-security scope and could leave retained keys without their deny protections. [W1, W8, W11]

If an exact resource cannot be identified, finish the implementation and name that specific missing deployment fact. Do not guess a deletion target. No old-data backup, identity export, or migration manifest is a gate for this authorized disposable reset.

### 8.3 Reset and initialize

Follow the repository's existing deployment owners:

1. Close development API/MCP admission and stop API consumers, workers, scheduler, and owned checker activity using the existing shutdown order. Stop MCP before replacing its API namespace. Do not let stale workers execute against a newly empty database.
2. Remove the Rust issuer service and obsolete routes/configuration. There is no parallel old/new preparation mode.
3. If the hosted shutdown also stopped local PostgreSQL/Redis, start only the required backing services using the supported `start local-data` path before administrative reset. An externally managed database server can remain available.
4. Drop/recreate the named disposable Workstream database using its administrative owner; create/reset the separate `flow_identity` database and restricted runtime role. Do not rerun a fresh-root initializer against an existing shared data root.
5. Reset only this deployment's stale queues, owned runtime scratch and disposable database admission/reference state. Requalify storage activation and prove fresh work uses newly created product lineage without restoring prior admissions, submissions or grants. Existing identical bytes may be reused only through the normal verified content-addressed admission path; retained bytes confer no product authority.
6. Apply the repository's current schema to the empty Workstream database through the supported hosted wrapper:

   ```sh
   python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env migrate
   ```

   The environment-file path must match the actual release. In a normal local backend environment the equivalent schema command is `python -m alembic upgrade head`. This is standard schema initialization, not a new identity migration. Do not stamp an incompatible database or invent a `compose.py reset` command. [W8, W11]

7. Start Keycloak, configure the realm/clients/policies, and create fresh test users. Start the API with only Keycloak issuer/JWKS and `workstream-api` audience settings.
8. Complete the initial administrator and project setup below before starting dependent workloads and reopening ordinary development access.

Document actual commands and environment for every step. The hosted wrapper does not provide an arbitrary `run` facility; use a supported existing path or implement the smallest necessary explicit management operation through its owner. Do not bypass deployment validation by documenting an unsupported convenience command.

### 8.4 First user and administrator

Obtain a real Keycloak human access token using `workstream-cli-login`, then call:

```text
workstream whoami
```

The ordinary first-access path creates a new ActorProfile and its single identity link, with a genuine verification timestamp. Record the returned new actor UUID. Repeated valid tokens for that exact issuer/subject must resolve to the same new actor; different subjects must create distinct actors. [W3, W4, W9]

Run the existing first-administrator bootstrap in the correctly configured backend execution environment:

```text
python -m scripts.bootstrap_access_administrator --actor-profile-id NEW_ACTOR_UUID --dry-run
python -m scripts.bootstrap_access_administrator --actor-profile-id NEW_ACTOR_UUID --execute
```

`NEW_ACTOR_UUID` means the value returned from this fresh environment. These module commands exist; a hosted `compose.py bootstrap` subcommand is not assumed to exist. Document how the backend module is invoked under the actual deployment tooling. Bootstrap must retain its existing one-time guard. [W5, W12]

The bootstrap grants **system Access Administrator only**. It does not grant Project Manager, submitter, reviewer, finance, or other product authority.

### 8.5 Seed the development permissions and projects

With the real Keycloak-backed administrator bearer, use existing public owner operations:

```text
workstream admin role-grants issue --input admin-grant.json --idempotency-key UUID
workstream admin service-actor provision --input service-actor.json --idempotency-key UUID
workstream project create --name NAME --slug SLUG --idempotency-key UUID
workstream project role-grant issue PROJECT_ID --input project-grant.json --idempotency-key UUID
```

Generate request files against the actual current CLI/API schemas. Grant `project_manager` with system scope to the intended new actor before using that actor to create projects. Obtain each participant's new actor UUID through their real first login/`whoami` before assigning a project role. Include the existing qualification payload for contributor grants. Create only the test roles, projects, and service actors needed to prove the identity path. [W5, W9]

Do not insert grants directly into database tables, copy old IDs, derive local authorization from Keycloak realm roles/email, or assume the first administrator automatically has every role. Product setup must keep using the normal owners and their audit behavior.

### 8.6 Repeatability

An ordinary restart retains the new Keycloak and Workstream databases. A deliberate full development reset discards both identity/account state and the dependent Workstream test state, then repeats provisioning and setup. New subjects and actor IDs are expected after that reset.

If a failed attempt leaves uncertain partial seed state, a fresh bounded reset is an acceptable recovery. There is no requirement for migration reversal, retained old-link history, old-token usability, or restoration of the Rust issuer. Re-running configuration without an explicit reset must not delete users, regenerate IDs, or silently replace secrets on every startup.

## 9. Browser login and proof tooling

Implement a small OAuth **client** helper and proof harness using suitable existing dependencies or a maintained client library. This is not an authorization server or a new Workstream authentication endpoint.

Required behavior:

1. Use only the fixed trusted discovery URL; validate the returned issuer and HTTPS endpoint origins against configuration.
2. Bind the exact loopback callback before opening the browser. Fail clearly if the registered port is occupied; do not switch to an unregistered callback or wildcard.
3. Generate a cryptographically random PKCE verifier, S256 challenge, and state. Use and validate an OIDC nonce if consuming the ID token for client login state.
4. Open the system browser with the exact client, callback, and scope set. Never collect the user's password in the helper.
5. Reject wrong/missing state, unexpected callback paths/hosts, duplicate callbacks, code reuse, and expired attempts. Stop listening after completion or timeout.
6. Redeem the code through verified TLS and validate the resulting access-token contract. The provider-only proof can stop here; the application proof then deliberately invokes ordinary actor creation in the fresh development environment.
7. Support refresh rotation with serialized refresh, logout/credential removal, and a clear re-login path when renewal fails.
8. Keep tokens in memory by default. If an explicit local credential file is needed, use a private directory and mode `0600`, bounded content, atomic replacement, and no shared/repository directory. Never print tokens in ordinary output or diagnostic reports.
9. Support launching the existing CLI as a child with `WORKSTREAM_TOKEN` set to the unprefixed API token and `WORKSTREAM_API_URL` set to the trusted API origin. Do not invent a `workstream login` command that the Go CLI does not implement.
10. Produce a redacted JSON proof report: checks, timestamps, deployment/config digests, issuer/audience summaries, lifetime results, and correlation identifiers; no reusable credentials.

Use a verifier harness for the provider-only proof, then use `workstream whoami` and existing project access/read commands against the newly initialized development API. First-access actor creation is intended in this environment. The helper may obtain the two proof token types; only its operator mode may read the exchange client secret, and that mode must remain separate from ordinary public-client login. [W3, W9, S4]

Refresh tokens for public clients belong to those clients. Do not forward them to the API or exchange requester. The MCP runtime will exchange the fresh source access token and will not hold the user's browser-client refresh credential unless separately required and designed by its client protocol.

## 10. Delivery sequence and gates

### Gate A — Implement the clean provider setup

Read the current checkout and identify the selected development environment. Implement Keycloak deployment/configuration, remove the active Rust issuer integration, update verifier settings and examples, and build the login/proof tooling. Keep the current Workstream actor model, first-access behavior, and authorization owners.

The only deployment facts to resolve are actual hosts, resource names, DNS, ports, runtime access, and required service callers. The architecture decision is fixed: fresh Keycloak, `workstream-api`, disposable old development state, no compatibility layer.

### Gate B — Reset and prove Keycloak independently

Execute the bounded setup from section 8 when the environment is accessible. Configure the public realm and private administration, create fresh users, and prove discovery, login, required password change, refresh, exact token claims, and exchange with the standalone harness.

Do not postpone all useful work because host or DNS access is unavailable. Finish available code, configuration, local tests, and exact deployment instructions; report only the specific access-dependent proof as blocked.

### Gate C — Prove fresh Workstream access

Initialize the Workstream schema, configure its single issuer, and use real Keycloak tokens to create new actors. Bootstrap the first administrator using the existing operation. Provision the required service actors and assign project roles through the existing owners.

Prove that direct API and exchanged API tokens for the same Keycloak subject resolve to the same new Workstream actor. Prove allowed project access, forbidden project denial, and suspended/revoked access denial. No old actor or grant needs to be reconciled.

### Gate D — Repeat, restart, and clean up

Complete a fresh setup drill, ordinary restart drill, and one full reset/retry drill. Check the API/MCP namespace lifecycle, stale queue cleanup, private administration, consistent process configuration, and the absence of obsolete demo routes or fallback credentials.

Use the normal repository review and human-merge process. There is no additional migration approval, preservation sign-off, old-issuer handback rehearsal, or production cutover project in this specification.

### Gate E — Activate MCP OAuth and prove the Garden connection

Provide the exact trusted issuer/JWKS, API audience `workstream-api`, canonical MCP resource URL, registered exchange client ID, secret reference, allowed scopes, lifetime policy, claim contract, and redacted passing exchange proof. Do not put the secret in the handoff document.

The provider milestone is complete when fresh login, direct Workstream access and independent exchange pass. Continue within this delivery objective to implement and deploy the MCP discovery, challenge, exact Garden registration and runtime exchange behavior in section 6.6. Completion additionally requires the actual Garden connector tests; do not stop at a passing harness or an MCP health endpoint. Repeat the restart/reconnect and full reset/reprovisioning proof after MCP activation so final evidence covers the complete installed system, not only the earlier provider stage.

## 11. Failure and retry behavior

A failed development setup may be fixed in place or reset and rerun. The runbook must make that repeatable using the exact selected resources. Do not build a rollback protocol for the discarded Rust issuer or preserve a second authentication path.

When Keycloak is unavailable, new login, refresh, and exchange fail clearly. Already issued API access tokens may continue only within the documented offline validity window. Invalid tokens, unexpected keys, wrong audiences, and failed authorization must fail closed. There is no local signing-token fallback, unsigned-token mode, or authorization bypass.

Distinguish a user's authentication failure from a provider infrastructure failure in bounded diagnostics without logging credentials. An ordinary restart must retain the new account and product state; only the explicit development reset discards it.

## 12. Development operations

Keep provider configuration reproducible and sanitized. Do not commit user passwords, access/refresh tokens, client secrets, private signing keys, or bootstrap credentials. Startup realm import is not ongoing configuration reconciliation: applying configuration to an already initialized realm must be deliberate and repeatable. [K14]

Store the provider and Workstream state persistently across normal restarts. Maintain separate database credentials and secret references. Record a concise procedure to rotate the confidential exchange secret and publish new signing keys without changing the issuer or accepting unsigned credentials.

Normal signing-key rotation can retain a retiring verification key for the maximum access-token lifetime plus skew. A full identity reset instead creates fresh identity state; recreate dependent development actors and clear process credential/JWKS caches as part of that reset so stale credentials are not reused.

Monitor provider readiness, database availability, failed login/refresh/exchange, TLS expiry, disk pressure, and startup resource use. Keep authentication request bodies and reusable credentials out of logs and evidence.

Old-state backups, restore-time targets, preserved migration archives, and disaster-recovery qualification are not acceptance gates for this disposable development task. A retention/backup policy for real retained users and data can be defined when that requirement exists. Do not turn it into a prerequisite for proving this identity setup.

## 13. Acceptance tests and evidence

Use focused owner tests plus real pinned-Keycloak integration tests. Mocks alone cannot prove provider mapper behavior, consent, refresh rotation, exchange policy, or token lifetimes. Run reset/retry tests against the identified disposable environment and keep unrelated infrastructure outside their scope.

### 13.1 Provider and browser flow

| ID | Test | Passing result |
|---|---|---|
| ID-01 | Fetch discovery/JWKS from outside the host. | Exact issuer and HTTPS endpoints; usable RS256 key with `kid`; no internal hostname leakage. |
| ID-02 | Fresh human login with a temporary password. | Stock UI requires password update; code+S256 PKCE succeeds; password never enters Workstream/helper. |
| ID-03 | Wrong verifier, missing verifier, wrong state, wrong callback, reused code. | Each fails safely; no usable credential delivered to the wrong caller. |
| ID-04 | Refresh, then reuse old refresh token. | Rotation succeeds once; disallowed reuse fails; helper does not race its own refresh. |
| ID-05 | Expired session, logout, disabled account. | New login/renewal follows the configured denial/re-login policy; offline API-token window is reported accurately. |
| ID-06 | Private administration through SSH. | Login, admin operation, logout, fresh login, iframes and resources work without public master endpoints. |
| ID-07 | External admin/master/management probes and forged proxy headers. | Restricted paths remain denied; issuer/redirect origin cannot be attacker-controlled. |
| ID-08 | Restart with persistent database. | Users/configuration/signing state remain valid; bootstrap credentials are not required or leaked. |
| ID-09 | Account/profile attribute tampering. | User cannot assign the human marker; duplicate/unmanaged values cannot create authority. |
| ID-10 | Anonymous client registration attempt. | No client is created; only authorized private administration can create the configured clients. |

### 13.2 Token and exchange boundary

| ID | Test | Passing result |
|---|---|---|
| TOK-01 | Direct API token through the real verifier. | Exact expected audience and required claims; valid token accepted. |
| TOK-02 | MCP source token directly to API verifier. | Rejected for wrong audience. |
| TOK-03 | Valid exchange by the confidential client. | Same `sub`; API-only audience; required human scope; no additional permission; no second login. |
| TOK-04 | Wrong/missing exchange secret, unapproved requester, or requester absent from source `aud`. | No API token issued. |
| TOK-05 | Expired, wrong-issuer, tampered, malformed, or ID-token subject credential. | Exchange fails; API verifier also rejects invalid bearer forms. |
| TOK-06 | Source missing `workstream:access`, source kind not human, marker absent, or service-account fixture. | Human API authority cannot be obtained. |
| TOK-07 | Extra requested scope or different target audience. | No unauthorized scope/audience is issued; the configured downscope fixture is rejected. |
| TOK-08 | Source close to expiry. | Output expiry is no later than source expiry and no more than 120 seconds after issuance. |
| TOK-09 | Requested refresh token in exchange. | No exchange refresh token is issued. |
| TOK-10 | Browser source refresh, then fresh exchange. | New source remains MCP-only; exchanged result remains API-only and same user. |
| TOK-11 | Normal signing-key rotation and provider outage. | Documented verification continuity/failure boundaries; no old-issuer fallback. |
| TOK-12 | Extra `account`/role-derived audiences or unexpected mappers. | Configuration check fails; no permissive adjustment of expected audience sets. |

### 13.3 Fresh provisioning and permissions

| ID | Test | Passing result |
|---|---|---|
| APP-01 | Initialize an empty Workstream database. | The current supported schema is installed without stamping, legacy data transforms, or identity-specific schema additions. |
| APP-02 | First real Keycloak login and `whoami`. | One new ActorProfile and its single identity link are created with genuine verification evidence. |
| APP-03 | Repeat login/refresh and concurrent first access for the same subject. | The same new actor is returned; no duplicate actor/link. |
| APP-04 | A different Keycloak user logs in. | A distinct new actor is created; email/username matching cannot merge authority. |
| APP-05 | First administrator bootstrap. | Existing bootstrap grants system Access Administrator and retains its one-time guard. |
| APP-06 | Project creation before/after the explicit Project Manager grant. | Access Administrator alone cannot create a project; the proper role enables the normal operation. |
| APP-07 | Assign project roles through the public owners. | Required qualifications and audit behavior remain enforced; no direct table grants or identity-provider roles bypass them. |
| APP-08 | Allowed and forbidden project reads. | Access is determined by the newly assigned local project permissions. |
| APP-09 | Direct and exchanged API tokens for the same user. | Both resolve to the same new actor and produce the same local authorization decisions. |
| APP-10 | Suspended actor or revoked identity link. | Access remains denied despite a valid Keycloak token. |
| APP-11 | Required service actors and worker callers. | New identities are explicitly provisioned; services cannot acquire human authority. |
| APP-12 | Whole development reset and retry. | Fresh accounts/actors/projects can be recreated; no old jobs, IDs, tokens, or artifact references are required. |
| APP-13 | Repository and deployment cleanup. | No live Rust issuer, obsolete demo configuration, dual issuer/audience acceptance, or migration/replacement subsystem is introduced. |

### 13.4 Profile and real MCP/Garden proof

| ID | Test | Passing result |
|---|---|---|
| PROFILE-01 | New human login through direct and exchanged access. | Canonical issuer email appears on the same Workstream actor; local email mutation is rejected. |
| PROFILE-02 | Change email at Keycloak, then use newer and older signed observations. | Newer authorized self-read synchronizes; older/equal observation cannot revert it. No email-based actor merge. |
| PROFILE-03 | Edit and clear display name locally, then refresh/exchange. | Optional issuer name does not overwrite the local edit/clear. |
| MCP-01 | Unauthenticated MCP access and metadata discovery. | Correct challenge and trusted resource/server metadata through public ingress. |
| MCP-02 | Actual Garden login/consent and callback. | Browser code+PKCE produces an MCP-bound credential; no pasted token or password-prompt helper substitutes for this test. |
| MCP-03 | MCP exchange and allowed tool execution. | Same subject/actor reaches the API with an API-only token; expected result returned to Garden. |
| MCP-04 | Wrong audience, issuer, expired token or failed exchange. | Denied before tool/product effects; no original-token forwarding fallback. |
| MCP-05 | Two Garden users plus forbidden/suspended/revoked access. | No cross-user credentials/results; live Workstream permissions remain enforced. |
| MCP-06 | Expiry, browser refresh/re-login and reconnect. | Fresh credentials work without extending expired source authority or repeating uncertain mutations. |
| MCP-07 | Exact scopes, resource and registration behavior. | Real Garden requests match the pinned provider configuration; unsupported behavior is reported, not claimed passing. |

### 13.5 Deployment and repeatability

Prove database role isolation, configuration repeatability without secret leakage, Caddy public/private routing, correct API/MCP namespace recreation, consistent worker settings, bounded startup/login resource use, ordinary restart persistence, and a repeatable reset of the exact development state.

Evidence must identify the tested commit and image/config digests, environment, executed checks, results, and actual remaining limitations. Distinguish local tests from hosted proof. Do not describe an unrun test as passing, and do not claim MCP OAuth integration is complete from issuer-only tests.

## 14. Implementation packages and affected owners

Use bounded changes and the repository's normal review process:

| Package | Deliverable |
|---|---|
| 1. Replace the demo deployment | Pinned Keycloak image, separate identity database, public/private Caddy routes, release/preflight integration, secrets, and removal of obsolete Rust wiring. |
| 2. Configure and prove the provider | Realm, clients, scopes, policies, stock UI, safe login helper, real token/refresh/exchange tests. |
| 3. Initialize Workstream | Existing schema initialization, Keycloak-only verifier settings, ordinary first-access creation, existing administrator bootstrap, and normal service/project setup. |
| 4. Connect Garden through MCP OAuth | Protected-resource discovery/challenges, verified MCP tokens, bounded API-token exchange and exact Garden client configuration. |
| 5. Qualify the complete delivery | Real Garden allowed/denied/isolation/renewal tests, API/CLI/profile proofs, restart and reset/retry drill, exact runbook and redacted evidence. |

Do not create an identity migration work package. Trace the affected current owners and keep changes limited to actual integration needs:

```text
AGENTS.md
CONTRIBUTING.md
README.md
backend/app/adapters/auth/flow.py
backend/app/schemas/auth.py
backend/app/core/config.py
backend/app/api/deps/authorization.py
backend/app/modules/actors/                  # existing behavior to use/test
backend/app/modules/authorization/           # existing bootstrap/grant owners
backend/scripts/bootstrap_access_administrator.py
cli/README.md
cli/internal/command/command.go
deploy/hosted/compose.py
deploy/hosted/preflight.py
deploy/hosted/release.env.example
deploy/hosted/public.Caddyfile
deploy/hosted/compose*.yml
deploy/hosted/README.md
deploy/hosted/PUBLIC_ACCESS.md
experiments/demo_identity/                  # remove obsolete implementation
mcp_server/                                # discovery, credential boundary, exchange and tests
```

Suggested new artifacts, explicitly new rather than claimed existing commands:

```text
deploy/hosted/compose.identity.yml
deploy/identity/README.md
deploy/identity/realm-config/                # sanitized desired configuration
scripts/identity_login.py                   # or appropriate existing owner path
scripts/prove_identity_flow.py
docs/keycloak-development-setup.md
```

Remove obsolete demo-only helpers, docs, tests, and secret/environment references together with their runtime. Inventory and retire operator-local Rust onboarding helpers too, including the current `get-access-token.sh`, `add-participant.sh` and `workstream-login.sh` under `/home/abiorh/workstream-onboarding`, their saved Rust login/token/header files, and the obsolete Rust administrator credential reference. Do this at the explicit reset/cutover, not during plan editing or while those credentials still support the running service. Replace participant instructions with browser login and the new OAuth helper, and administrator instructions with Keycloak's stock private UI/Admin API. Do not commit any operator-local credentials. If a file contains shared provider-neutral behavior, move/use that behavior under its proper existing owner rather than deleting another feature or retaining the whole demo as a fallback.

Do not add `current_identity_link_id`, identity replacement receipts, historical multi-link support, nullable human verification exceptions, mapping/reversal commands, or a new migration authorization principal. Keep the existing actor/auth/audit boundaries. No new identity-specific Alembic revision is justified by this clean setup.

## 15. Deployment facts to resolve

| Fact | How to resolve |
|---|---|
| Exact development release/Compose project | Current deployment configuration and operator access. |
| Database endpoint, named databases, owned queue/scratch/artifact state | Current release resource inventory before reset. |
| DNS and TLS ownership | Existing identity/API records and Caddy deployment. |
| PostgreSQL version and host capacity | Running environment and pinned Keycloak support matrix. |
| Trusted proxy address and available ports | Actual network/listener inspection. |
| Image digests | Official registry and recorded image build provenance. |
| Fresh setup participants and required service actors | The smallest test population and actual deployment owner requirements. |
| Garden connector protocol, callbacks, registration and credential ownership | Inspect the actual Garden implementation before client configuration; prove the actual connector during this delivery. |

These are environment facts. They do not reopen the decisions to use `workstream-api`, discard old development state, or omit migration/backward compatibility.

If a stock-provider feature fails a required proof, report the exact failure and the smallest proposed correction. Do not silently switch providers, add a custom OAuth server, accept old credentials, weaken authorization, or introduce a compatibility subsystem.

## 16. Definition of done

The coding agent must return:

1. Implemented/reviewed provider deployment, configuration, proof tooling, and removal of obsolete demo issuer integration.
2. Reproducible fresh setup with exact image/configuration digests and a sanitized desired-state configuration.
3. Passing evidence for browser login, password setup, refresh, exact token claims, independent exchange, and wrong-audience rejection.
4. Passing fresh Workstream actor creation, existing administrator bootstrap, local role/project authorization, and correct service identity behavior.
5. A bounded development reset/retry runbook and proof that ordinary restarts retain the new state.
6. A precise account of what was implemented, tested, and deployed, plus any concrete external access or human credential action still needed.
7. Passing real Garden-to-MCP browser authorization, discovery, scoped token exchange, tool calls, denial/isolation and renewal evidence.
8. Preserved issuer-owned email and local display-name behavior, plus removal of obsolete Rust onboarding credentials/scripts at cutover.

**Successful end state:** Keycloak is the only active issuer. Fresh users receive fresh Workstream actors through the existing path. Local permissions control access. Browser login and renewal work. An MCP token can independently exchange into a short-lived API token for the same newly provisioned user. The actual Garden connector uses MCP OAuth and the MCP server exchanges its user token before calling the API. Email remains issuer-owned and display names remain locally editable. The old Rust demo, its deployment wiring and obsolete onboarding paths are removed. A provider harness alone does not satisfy this end state.

## 17. Sources and source-of-truth notes

Repository links below are pinned to the reviewed commit. Implementation must inspect the actual checkout and explicitly reconcile changes. Product documentation can change; the deployed version and passing tests determine the realized behavior. Requirements and selected settings in this document are design decisions, not claims that every option is a product default.

### Workstream source

- **[W1]** [Repository working rules](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/AGENTS.md) and [contribution process](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/CONTRIBUTING.md).
- **[W2]** [External Flow authentication boundary](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/docs/decision_0006_external_flow_auth_boundary.md) and [Workstream authorization decision](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/docs/decision_0012_workstream_authorization_service.md).
- **[W3]** [External-token verifier](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/adapters/auth/flow.py), [verified-token schema](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/schemas/auth.py), and [request authorization resolution](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/api/deps/authorization.py).
- **[W4]** [Actor models](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/actors/models.py), [repository](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/actors/repository.py), and [service](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/actors/service.py).
- **[W5]** [Authorization catalogue](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/authorization/catalogue.py), [administration service](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/authorization/admin_service.py), [service-actor owner](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/authorization/service_actor_service.py), and [audit schemas](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/modules/audit/schemas.py).
- **[W6]** [Runtime settings](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/app/core/config.py) and [hosted release environment example](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/deploy/hosted/release.env.example).
- **[W7]** [Database baseline and immutable-history guards](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/alembic/baseline/v01_schema.sql) and [current migration directory](https://github.com/Flow-Research/workstream/tree/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/alembic/versions).
- **[W8]** [Hosted deployment](https://github.com/Flow-Research/workstream/tree/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/deploy/hosted), especially [preflight](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/deploy/hosted/preflight.py), [composition](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/deploy/hosted/compose.py), and [Caddy routing](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/deploy/hosted/public.Caddyfile).
- **[W9]** [CLI credential contract](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/cli/README.md) and [MCP server](https://github.com/Flow-Research/workstream/tree/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/mcp_server).
- **[W10]** [Rust demo identity implementation](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/experiments/demo_identity/src/main.rs).

- **[W11]** [Existing fresh database and disposable reset procedure](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/README.md).
- **[W12]** [Existing first Access Administrator bootstrap](https://github.com/Flow-Research/workstream/blob/94334ccf4085c26c7bfaa054465fc05cfbdad1fc/backend/scripts/bootstrap_access_administrator.py).

### Keycloak primary documentation

- **[K1]** [Keycloak project](https://www.keycloak.org/).
- **[K2]** [Keycloak 26.8.2 release](https://www.keycloak.org/2026/11/keycloak-2682-released).
- **[K3]** [Server administration, 26.8.2](https://www.keycloak.org/docs/26.8.2/server_admin/).
- **[K4]** [Standard Token Exchange](https://www.keycloak.org/securing-apps/token-exchange).
- **[K5]** [26.8.2 upgrade notes](https://www.keycloak.org/docs/26.8.2/upgrading/).
- **[K6]** [Running Keycloak in a container](https://www.keycloak.org/server/containers).
- **[K7]** [Database configuration](https://www.keycloak.org/server/db).
- **[K8]** [Reverse proxy configuration](https://www.keycloak.org/server/reverseproxy).
- **[K9]** [Hostname configuration](https://www.keycloak.org/server/hostname) and [separate administration routing example](https://www.keycloak.org/server/traefik-reencrypt).
- **[K10]** [Official maintainer discussion of admin/frontend hostnames](https://github.com/keycloak/keycloak/discussions/46572). The private master-realm configuration must be proved on the exact deployed image.
- **[K11]** [Protocol mapper reference](https://www.keycloak.org/admin-api/protocol-mappers).
- **[K12]** [Assertion-grant client policy executors](https://www.keycloak.org/securing-apps/jwt-authorization-grant#client-policies-and-jwt-authorization-grant). This source documents policies also applicable to Standard Token Exchange; it is not a requirement to enable JWT authorization grants.
- **[K13]** [Keycloak as an MCP authorization server](https://www.keycloak.org/securing-apps/mcp-authz-server).
- **[K14]** [Import/export limitations](https://www.keycloak.org/server/importExport) and [bootstrap/recovery administration](https://www.keycloak.org/server/bootstrap-admin-recovery).

### Protocol sources

- **[S1]** [MCP authorization, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization).
- **[S2]** [MCP token-passthrough security guidance](https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices#token-passthrough).
- **[S3]** [RFC 8693: OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html).
- **[S4]** [RFC 7636: PKCE](https://www.rfc-editor.org/rfc/rfc7636.html) and [RFC 9700: OAuth security best current practice](https://www.rfc-editor.org/rfc/rfc9700.html).
- **[S5]** [RFC 8707: Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707.html), [RFC 9728: Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728.html), and [RFC 8414: Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html).
