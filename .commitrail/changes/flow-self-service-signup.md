# flow-self-service-signup — Verified Flow registration and branded account access

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Flow Identity supports branded self-registration, verified email and password recovery without granting Workstream permissions.

## Intent

Participants create their own Flow account and continue the existing Garden MCP,
CLI, Swagger or direct API login. Flow branding replaces provider branding on
participant-facing identity screens. Invited accounts remain supported.

## Current behavior

`deploy/identity/realm_config.py` disables registration, verification and recovery.
The human identity marker is administrator-owned. Keycloak owns credentials and
sessions; Workstream verifies scoped tokens and separately enforces authority.
PR716 delivered native CLI, Swagger and dedicated issuer password grants.

## Bounded change

### Allowed

- `deploy/identity/**`: provider configuration, minimal theme, registration
  marker provisioning if no stock configuration safely supports it, documentation.
- `deploy/hosted/**`: only identity email configuration and operator instructions.
- `scripts/*identity*`, `scripts/test_keycloak_configuration.py`, identity test
  fixtures, `.github/requirements/identity-browser.*` and `.github/workflows/identity.yml`: real provider/browser/email proofs.
- `scripts/check_stale_artifact_contracts.py` and its focused asset regression: recognize binary image assets without exempting source/configuration text.
- `docs/roadmap_status.md`, affected onboarding docs, this record.

- `mcp_server/tests/test_oauth_provider.py`: repair collection-time expiration values exposed by slow CI; retain all denial assertions.

### Not allowed

- Workstream-owned login/passwords, project/admin grants on signup, Garden primary
  authentication changes, data reset, weakened verification or browser protections.
- Public unverified registration while production mail delivery is unavailable.
- Invented Flow logo or unrelated UI/application redesign.

## Design and decisions

Use Keycloak's existing registration, verification and reset flows; inherit its
maintained login templates and override only branding/assets/messages/CSS where
possible. Theme uses the user-supplied Flow wave logo, preserved unchanged, with responsive blue-accent presentation.
Use local SMTP capture for deterministic real email-flow testing; production SMTP
credentials remain private. Activation validates mail configuration and delivery
before enabling public registration. No real participant email is marked verified
administratively. An unverified account row may exist, but browser/direct API credentials must wait for verification. Inventory existing unverified invited accounts before activation and require genuine email verification. Activation must reject a missing registration provider and bind its listener in the same activation patch. Signup gets trusted human identity without exposing its marker
as an editable form field. Pinned Keycloak26.8.2 source shows profile defaults are filtered by field edit permissions; making the marker writable would break custody. Use a minimal Flow-realm REGISTER event listener in the provider transaction to assign human only to successful self-registration. Do not handle admin-create events or alter existing accounts. Compile against the exact provider jars with a pinned JDK21 build stage, adding no runtime framework.
Preserve invited users and existing issuer/sub/audience/token-exchange contracts.

### Account-console correction

The hosted signup completes, but the provider account console has no token scopes
because the explicit realm scope import omits stock defaults. Complete the same
signup journey by configuring only the stock `account-console` client with the
basic subject scope and account-only role/audience mappers. Keep its existing
account-role scope mappings, PKCE and account-path redirects; never add Workstream
API/MCP audiences, realm-administrator roles or broad full-scope access. Let Keycloak create both built-in account clients during realm import, then
reconcile the existing `account-console` using the same bounded helper for new
and hosted realms; never import a duplicate or recreate the `account` client. Prove the real account page loads after signup and its tokens cannot enter
Workstream API/MCP. Assign `basic` through the dedicated default-client-scope endpoint; client PUT only updates the mapper representation. Existing users and permissions remain unchanged.

## Acceptance criteria

- [ ] Browser signup completes only after email verification; supplied marker or
  privilege fields cannot grant authority or choose a service identity.
- [ ] Verification/reset links are single-use and expire; wrong/replayed links,
  wrong passwords and unverified direct grants deny.
- [ ] Verified accounts use existing CLI/API/MCP scopes, with no Workstream grants.
- [ ] Browser login, signup, required password change, verify/reset and consent
  screens show Flow branding, work on mobile and retain accessible labels.
- [ ] SMTP outage preserves credentials and shows non-enumerating retry/support guidance.
- [ ] Existing invited-account login/renewal/exchange proofs remain passing.
- [ ] Deployment instructions cover SMTP, theme updates and existing realm updates
  without reset; production signup remains disabled until delivery is proven.

## Risk and review routing

- Risk class: L1
- Required reviewers: security, architecture, QA/test delta, documentation;
  CI integrity if test wiring changes.
- Human review focus: account verification, marker custody, separate Workstream
  permission grants, brand assets and production delivery readiness.

## Evidence

Real isolated Keycloak/PostgreSQL and local SMTP capture, browser form and link
flows, signed token identity/audience assertions, unchanged authorization tests,
rejection controls, responsive screenshots, links and applicable CI.

## Reconciliation

- Current-source reconciliation: based on main a2154e8a4 (merged PR716).
- Next usable boundary: qualify persistent Garden renewal and reconnection; hosted signup and recovery are enabled after real SMTP proof.
- Remaining risks: each deployment must prove its SMTP sender and delivery; enabling verification affects existing unverified accounts. Provider upgrades require repeating the registration and denial proofs.

### Signed-in account usability

Extend the same account-console correction with Flow branding inherited from
Keycloak v3, without copying its application or templates. Map only given name,
family name and preferred username into the console's ID token for its account
menu; keep account-only audience/role restrictions and API/MCP denial proofs.
Exercise the sidebar's Signing in password update, prove the old password denies
and the replacement succeeds, and check named header and Flow logo in the real
browser. Document the password navigation and collapsed menu. No user permission
changes or Workstream password endpoints.

### Persistent Garden connection correction

The user approved a 30-day offline idle timeout and a 90-day absolute maximum
for Garden's personal MCP connection. Ordinary API access tokens remain short-lived;
Garden stores and rotates the refresh credential through its existing Executor
owner. Limit the offline grant to the registered Garden MCP browser clients;
do not extend primary browser sessions or API password grants. Existing ordinary
grants require one reauthorization to obtain the new grant. Revocation and
connection removal must prevent further renewal. Garden must present a known
unusable grant as requiring reconnection, not merely as a saved connection.

Garden requests offline access through its dedicated client configuration; MCP
resource discovery continues advertising only its resource-access scopes. Verify real refresh,
audience preservation, revocation, and two-user isolation before claiming hosted
completion. Garden's status/projection repair belongs in its own repository and
must not change Garden's primary authentication or general chat-stream ordering.

The focused plan review requires explicit existing-realm reconciliation through
Admin API scope endpoints and issuer revocation before Garden disconnect succeeds.
Prove revoking a credential after concurrent rotation invalidates its successor;
retain retryable connection custody when the issuer is unavailable. Do not apply
persistent hosted grants until these checks pass.
