# Keycloak identity and Garden MCP OAuth

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Replace the disposable Rust identity deployment with Keycloak and qualify Garden-to-Workstream MCP OAuth without changing product authorization.

## Intent

Use a maintained external identity provider for browser email/password login,
required password changes, sessions and OAuth. Preserve issuer-owned profile
email, locally editable display names and Workstream's independent role owners.
The approved implementation contract is [the Keycloak plan](../../workstream_keyloack.md).
A provider-only harness or passing CI is not delivery of the Garden connection.

## Current behavior

`experiments/demo_identity/` issues short-lived JWTs through password JSON APIs.
`backend/app/adapters/auth/flow.py` verifies signed external identities;
`backend/app/modules/actors/service.py` owns profile observations.
`mcp_server/workstream_mcp/server.py` extracts incoming bearers and forwards them
through its HTTP gateway; it has no OAuth discovery/exchange boundary.
Hosted `compose.py`/`preflight.py` own exact deployment topology and boot order.

## Bounded change

### Allowed

- `workstream_keyloack.md`, this record, affected README/architecture/authentication
  and deployment docs plus `docs/roadmap_status.md` and relevant current navigation.
- `deploy/identity/**`, `deploy/hosted/**`, affected Docker identity build and
  private-secret entrypoints, and their existing tests under `scripts/`.
- `experiments/demo_identity/**` and its exclusive scripts/tests/workflow:
  remove the superseded issuer; retain provider-neutral proofs in their owner.
- `packages/external-services/**`, direct backend adapter imports and backend/MCP
  build/lock/wheel consumers: extract the existing dependency-free adapter
  convention once; remove its old location without a re-export alias.
- `mcp_server/**`: OAuth settings, typed provider capability/composition,
  discovery, credential validation, bounded exchange, existing tool integration,
  dependency locks and focused protocol/integration tests.
- `backend/app/core/config.py`, external-authentication adapter/contracts and
  their tests only where real provider claims require correction. Existing
  actor/bootstrap/authorization owners are reused, not redesigned.
- `scripts/identity_*.py` and focused tests: browser OAuth client and redacted
  qualification; existing exact CI test catalogues/workflows only to replace
  retired issuer proof and execute required new proof without weakening gates.
- Explicitly inventoried disposable hosted database/queue/scratch/identity state
  and private operator credentials at authorized reset/cutover. No credentials
  or reusable tokens enter Git or public evidence.

### Not allowed

No Workstream password endpoints, custom OAuth server, dual issuer/fallback,
identity-mapping migration, product grant bypass, checker/lifecycle redesign,
finance or intake work owned by other PRs, blanket shared-resource deletion,
unapproved compute resizing, open dynamic registration or fabricated Garden proof.
Garden repository changes are not silently included in this Workstream PR;
identify any concrete connector-owner gap and coordinate it explicitly.

## Design and decisions

Keycloak owns credentials; Workstream owns actor identity and permissions.
Use exact issuer/audiences, stock browser code+S256 PKCE and Standard Exchange V2.
MCP accepts its own resource credentials and exchanges them for an API-only token
with the same subject. The API still enforces current local authority.
Use the existing independent MCP package boundary; do not import backend product
modules into it to reuse authentication machinery.
Initial Keycloak administration and Workstream's one-time first Access
Administrator bootstrap remain distinct; retire only the Rust-specific bootstrap.
Reset only the approved disposable development resources, keeping runtime
immutability/authorization guards intact for fresh data. Ordinary restart retains
new state. No reset or deployment is implied by merely rendering configuration.

## Acceptance criteria

- [ ] Exact pinned provider configuration passes real browser, claim, profile,
  refresh, exchange, admin-isolation and database-isolation proofs.
- [ ] MCP discovery/challenges and request-bound exchange reject wrong audiences,
  sources and users before effects; no direct bearer-forwarding fallback remains.
- [ ] Actual Garden connection performs allowed tools and denies forbidden,
  suspended/revoked and cross-user access, including renewal/reconnect.
- [ ] Fresh bootstrap/service/project setup uses existing owner APIs; issuer
  email and local name edit/clear behavior survive direct and exchanged access.
- [ ] Hosted reset and ordinary restart pass with bounded resources and fresh
  storage proof; obsolete Rust deployment/scripts/credentials are retired.
- [ ] Affected tests, docs, required internal reviews and hosted CI pass on the
  exact candidate; evidence distinguishes implementation from deployment.

## Risk and review routing

- Risk class: L0
- Required reviewers: Security; Architecture/reuse; QA/test delta;
  Docs/product operations; CI integrity for changed proof wiring.
- Human review focus: issuer/MCP/API credential separation, reset resource scope,
  private administration, real Garden evidence and retained product authority.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Plan preserves intended owners | Focused plan review and Markdown/stale-scope checks | Passed plan consistency | Runtime behavior unproven |
| Provider configuration is accepted | Isolated production-mode Keycloak 26.8.2 with PostgreSQL 16; realm import and user-profile Admin API | Passed after explicitly defining the basic subject scope and removing the unsupported unmanaged-attribute enum | Browser login, exchange enforcement and hosted capacity remain unproven |
| Scope and profile configuration regression | `python3 -m unittest scripts.test_keycloak_configuration -q` | Seven checks passed | Configuration checks supplement, not replace, real provider proofs |
| Real provider token boundary | Local HTTPS Keycloak/PostgreSQL, browser-form HTTP code+PKCE flow, signature/issuer/audience verification and actual MCP adapter exchange | Direct/MCP login and API-only exchange preserve subject/email; exchange lifetime capped and no refresh credential returned | Protocol evidence includes renewal/reuse denial and unchanged backend verifier acceptance; actual browser UI, Garden and deployed API proof remain pending |
| MCP request credential boundary | Focused `test_oauth_provider.py` and `test_oauth_transport.py` | 21 checks passed, including substitution, per-request exchange, missing/duplicate credentials and API revocation denial | Full existing suite and real Garden connection remain pending |
| Garden has OAuth browser/callback routes | Read current `api/executor/oauth/start.ts`, `api/oauth/callback.ts` and `executor-engine/auth-contract.ts` | Existing client selection and dynamic registration; server-managed preset currently Google-specific | Exact operator registration and live Garden configuration must be proven |
| Repeatable provider integration | `PYTHONPATH=.:backend:mcp_server backend/.venv/bin/python scripts/test_identity_provider.py -q` | Passed stock offline bootstrap, runtime without bootstrap credentials, real password change, code/PKCE login, direct/exchanged verifier checks, wrong-audience rejection, refresh replay denial, account/key persistence after restart and database CONNECT isolation; owned containers/network removed | Hosted operator wrapper, actual browser UI and Garden are not covered by this run |
| Hosted configuration and ingress | 99 focused configuration/initialization tests; pinned Caddy over real sockets | Passed private administration and public route boundaries | Real deployed routing and administrator UI remain unproven |
| Participant browser login | Real Chrome 157 with Playwright 1.57, isolated NSS trust, sandbox enabled; `scripts/test_identity_browser.py` | Two tests passed: forced password change, consent, loopback code callback, private credential persistence/renewal plus inherited provider restart/isolation; owned resources cleaned | Hosted browser, named administrator MFA/recovery and Garden remain separate |
| Packaged MCP transport | `scripts/test_hosted_mcp_container.py` with image `sha256:258e40374656cafd1e78f54f4be0010ed0cd5a00dbdbe6bacc4974a3f6f947b3` | 132 authenticated tools, signed HTTPS exchange, two callers, restart, API replacement and stale-namespace counterexample passed | Fixture provider; actual Garden session not established |
| API/MCP profile and authority parity | Installed wheel, HTTPS signed fixture issuer, real API and isolated PostgreSQL; `test_profile_flow.py` | 11 passed, including concurrent callers, signed profile observations, local display-name edits, admission and revocation | Remaining owner suites and hosted Garden still require their own evidence |
| API/MCP owner integration | Installed wheel, HTTPS signed fixture issuer and fresh isolated PostgreSQL per suite | All eight suites passed: profile 11 tests plus access reads, admin grants, actor lifecycle, projects, project grants, guides and policies; cleanup confirmed | Fixture issuer integration does not establish deployed Garden interoperability |
| Real provider denial boundaries | Owned Keycloak fixture, direct execution of `test_provider_denies_marker_tampering_exchange_widening_and_closed_sessions` | Passed profile-marker injection, unmarked/nonhuman exchange, scope/audience/refresh rejection, logout and disabled-account renewal/login; removing and restoring the provider claim executor reproduced the intended counterexample | Exact-head CI and hosted provider operation still required |
| Release shared-package custody | `scripts.test_hosted_release_images` plus actual frozen dependency exports for both SDK environments | 21 tests passed; both exports include the exact shared package; same-permission shared-code substitution is rejected | Fresh image inspection remains hosted CI work |
| Delivery | Acceptance matrix in approved plan | Implementation underway | Hosted qualification and final reviews remain |

## Review findings

Plan correction preserves email claims, includes actual Garden OAuth delivery,
retires local Rust helpers and retains independent first-administrator bootstrap.
Provider resource-indicator maturity and exact Garden registration need pinned
runtime proof; neither is assumed from a green health endpoint.

Implementation review confirmed the shared adapter extraction and typed MCP
boundary. It identified missing real-provider negative proofs and current hosted
instructions that still described Rust tokens without OAuth discovery. The
provider proof now exercises those denial paths, and both hosted instruction
sections describe MCP-scoped tokens, the exchange-secret mount and actual health
checks. Image verification also follows the relocated shared package's locked
identity and installed source bytes instead of assuming every dependency export
is a registry requirement. These corrections require affected review replay.

## Reconciliation

- Current-source reconciliation: main `94334ccf4`; open intake/finance/CLI work
  remains outside this change's implementation ownership.
- Next usable boundary: qualified Keycloak and real Garden MCP OAuth access.
- Remaining risks: provider feature compatibility, Garden client provisioning,
  shared-host capacity and scoped destructive reset must be resolved with proof.
