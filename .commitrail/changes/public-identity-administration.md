# Browser-accessible Flow Identity administration

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Browser administration on the canonical identity HTTPS hostname.

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
