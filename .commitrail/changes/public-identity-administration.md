# Browser administration and official participant API/CLI login

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Browser administration plus native CLI and Swagger code/PKCE login on the canonical identity provider.

## Intent

The administrator must invite participants through the normal HTTPS identity website, without SSH tunnels. Replace the superseded private console origin with the existing fixed identity origin; preserve Keycloak authentication/MFA and independent Workstream authorization.

## Bounded change

Change deploy/hosted/public.Caddyfile, compose.identity.yml, preflight.py, deploy/identity/README.md, related hosted documentation, scripts/test_public_ingress.py and affected identity configuration tests, docs/roadmap_status.md, and this record. Hosted reconciliation changes only ingress, identity configuration and the master realm frontend URL, preserving other realm attributes and all accounts/data. No Garden, product roles, OAuth scopes, registration activation, database reset or secret disclosure.

## Acceptance criteria

- Public /admin/ reaches Keycloak console; admin browser login and MFA succeed.
- Missing credentials and participant tokens cannot read administrative user data.
- Participant login/password change, flow issuer discovery and MCP audiences remain unchanged.
- Health/metrics, dynamic client registration and unrelated hosts remain denied; upstream stays loopback with verified TLS and overwritten forwarding headers.
- Remove private console route and stale deployment guidance; document creating a human account, temporary password, and separate Workstream authority.
- Real-socket ingress and configuration tests; hosted administrator/browser and denial probes. Preserve named admin MFA and recovery before removing the old origin.

## Risk and review routing

L1 security-sensitive ingress change. Focused plan and final security/architecture/QA/docs review. Human focus: deliberately public authenticated administration, stable issuer, no anonymous administration or product grants. Deployment proof is separate from source and CI checks.

## Evidence

Real-socket Caddy proof passed, including exact-host routing, body limits, forwarded-header replacement and denied management/registration paths. Hosted-release and Keycloak configuration tests passed (91 tests, 325 subtests); the added canonical-admin override regression independently passed.

Hosted configuration from ab97028e5 was applied without rebuilding application images or resetting data. The fixed public admin URL serves the console. A fresh sandboxed browser rejected invalid MFA then authenticated the named administrator with valid MFA and read the master realm. Fresh participant code/PKCE login passed. Administrative user reads reject absent credentials and a freshly issued participant token. Both realms retain disabled registration; the flow issuer and admin-only human marker remain unchanged. Health, metrics and both realm dynamic-registration paths returned 404. Private credential material and browser evidence remain outside Git.

The initial deployment pull failed because registry authentication had expired. Temporary ECR authentication allowed the pinned image reconciliation and was removed afterward. A first participant proof expected consent on every login; the existing consent legitimately skipped that screen, so the proof now accepts either consent or the verified callback. Neither observation required a product permission change.

## API and CLI onboarding extension

The same requested identity usability correction also removes dependence on a repository login helper. Native CLI `login`, `logout`, and explicit `auth token` use the existing public code/S256-PKCE client, private locally stored refresh credentials, same-subject renewal and fixed audience/issuer validation. Normal CLI commands consume the saved session unless an explicit environment bearer is supplied; reject saved credentials bound to a different API origin. Refresh is serialized and an uncertain refresh response requires fresh login rather than automatic retries. No participant passwords are handled by the CLI or Workstream.

Swagger gains a public PKCE OAuth client with one exact HTTPS callback and origin, while preserving bearer API support and the unchanged backend verifier. API consumers can sign in using Authorize or a standard OAuth client; direct participant password grants stay disabled. Allow files additionally: cli auth owner/commands/tests/dependency lockfiles/docs, backend Swagger/OpenAPI owner and focused tests, realm configuration/tests and hosted callback ingress/tests, identity browser/protocol proofs and affected identity CI helper references. Remove the superseded participant Python helper and replace its distinct proof with native-client and provider tests; preserve browser/provider integration coverage. No Garden, signup, SMTP, machine impersonation or human-review work.

Proof must cover callback state/PKCE and timeout, invalid issuer/audience/token, OS credential-store and lock custody, API-origin substitution, concurrent/uncertain refresh, logout and explicit token output; a real invited participant browser login with the built CLI and direct API call; Swagger browser authorization against the hosted provider. Review security and architecture before implementation and replay relevant QA/docs/CI tracks before readiness.

### Concrete onboarding contracts

- Default API origin is `https://workstream.flowresearch.tech`; default issuer is `https://identity.flowresearch.tech/realms/flow`. Login's explicit `--api-url`/`--issuer` bind its saved credential to those exact HTTPS origins. `WORKSTREAM_TOKEN` takes precedence for existing automation; absent that bearer, reject any configured API origin differing from the saved binding before network access. No HTTP production login endpoints.
- Store one participant session in the OS credential store (Linux Secret Service, macOS Keychain, Windows Credential Manager), not a plaintext-token file. If the store is unavailable or locked, fail with an actionable message; do not silently fall back. Use an owner-private standard user-config directory and advisory lock to serialize login/refresh/logout; reject symlink/nonregular lock paths and insecure Unix directory modes. Credential-store replacement is a single secret operation; write a refresh-in-flight marker before sending a refresh. An interrupted/failed refresh requires a fresh browser login. Logout removes the local secret even when remote logout cannot be confirmed, reporting that limitation without claiming access-token invalidation.
- Verify signed RS256 tokens with the maintained OIDC verifier and bounded, nonredirecting HTTPS transport: exact issuer, API audience, `azp=workstream-cli-login`, `typ=Bearer`, `subject_kind=human`, nonempty subject/email, issued-at/expiry and required access scope. Discovery/JWKS endpoints remain same fixed issuer paths. Refresh must retain subject/client identity. State and PKCE are fresh per login; callback binds only IPv4 loopback17843, exact method/host/path, singleton state/code parameters, and a five-minute login deadline inherited from the existing helper.
- Swagger explicitly serves `/docs/oauth2-redirect`, exposes that exact ingress path, initializes `workstream-swagger` with S256 PKCE, and adds an OAuth authorization-code alternative to bearer-secured OpenAPI operations (OR, not AND). Runtime bearer parsing/verification stays unchanged. Register only the exact API-origin callback and browser webOrigin; no client secret or token persistence in Swagger.
- Native CLI auth code owns provider/client+OS-secret-store integration; command.go owns command registration and client resolution. Existing provider/Chrome tests must invoke the built CLI, retaining forced-password-change, signed token, renewal and cleanup proof. Identity CI builds the binary instead of installing the deleted Python login helper. New tests belong to CLI auth/command and existing backend docs/OpenAPI owner; package checks and current boundary catalogues must still pass.

Native-client proof replaces the retired helper's callback substitution, signed
contract, foreign-origin, same-subject renewal, uncertain refresh, logout and
concurrent-operation tests. File-token permission tests are replaced by OS-secret
storage and private lock custody checks; the old memory-only child-process mode
and no-overwrite file workflow are removed rather than preserved as alternate
login paths. Browser proof invokes the built binary and keeps forced password
change, renewal and provider-session logout assertions. The hosted Linux CLI
already completed browser PKCE, OS-keyring storage, exact-email `whoami`, explicit
token output and logout; Swagger hosted qualification remains to be completed.

The replacement real-provider/browser fixture passed with the built native CLI:
forced first-password change, browser code/PKCE, signed API identity, near-expiry
renewal, local logout and absence of its provider session. Its first run reached
logout but the test's final admin read used an expired operator token; renewing
that test credential fixed the proof without changing product behavior. Go package
checks and login race tests passed; the Windows binary cross-build passed, which
is not Windows credential-store runtime qualification. Hosted Linux runtime proof
uses the real Secret Service. Measured hosted access/refresh strings were 1,046
and 844 bytes; platform credential-store limits still apply and failures are
reported without plaintext fallback.
