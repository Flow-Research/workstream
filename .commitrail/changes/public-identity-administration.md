# Browser-accessible Flow Identity administration

Initiative: None
Status: Planned

## Intent and scope

The administrator must invite participants through the normal HTTPS identity website, without SSH tunnels. Replace the superseded private console origin with the existing fixed identity origin; preserve Keycloak authentication/MFA and independent Workstream authorization.

## Plan and allowed files

Change deploy/hosted/public.Caddyfile, compose.identity.yml, preflight.py, deploy/identity/README.md, related hosted documentation, scripts/test_public_ingress.py and affected identity configuration tests, docs/roadmap_status.md, and this record. Hosted reconciliation changes only ingress, identity configuration and the master realm frontend URL, preserving other realm attributes and all accounts/data. No Garden, product roles, OAuth scopes, registration activation, database reset or secret disclosure.

## Acceptance and verification

- Public /admin/ reaches Keycloak console; admin browser login and MFA succeed.
- Missing credentials and participant tokens cannot read administrative user data.
- Participant login/password change, flow issuer discovery and MCP audiences remain unchanged.
- Health/metrics, dynamic client registration and unrelated hosts remain denied; upstream stays loopback with verified TLS and overwritten forwarding headers.
- Remove private console route and stale deployment guidance; document creating a human account, temporary password, and separate Workstream authority.
- Real-socket ingress and configuration tests; hosted administrator/browser and denial probes. Preserve named admin MFA and recovery before removing the old origin.

## Risk and review

L1 security-sensitive ingress change. Focused plan and final security/architecture/QA/docs review. Human focus: deliberately public authenticated administration, stable issuer, no anonymous administration or product grants. Deployment proof is separate from source and CI checks.
