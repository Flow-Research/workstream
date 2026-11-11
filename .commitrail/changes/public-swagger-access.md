# Public Swagger access

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Expose the existing FastAPI Swagger UI and schema on the public Workstream hostname.

## Intent

The public proxy currently hides FastAPI's `/docs` and `/openapi.json`, making API exploration unavailable despite a working deployment. Extend its existing API path allowlist with those two exact paths. Keep the backend's method handling, token verification and authorization unchanged; documentation supplies no product authority.

## Bounded change

Allowed files: `deploy/hosted/public.Caddyfile`, `scripts/test_public_ingress.py`, `deploy/hosted/PUBLIC_ACCESS.md`, `experiments/demo_identity/README.md`, `deploy/hosted/SINGLE_HOST.md`,
`docs/operations_authorization_service.md`, affected README/roadmap wording and this record.
Prohibited: new application endpoints, auth bypass, wildcard documentation exposure, issuer/MCP runtime changes, unrelated deployment changes or additional worktrees.

## Acceptance criteria

1. Add the exact documentation paths to the existing backend proxy.
2. Extend the real Caddy socket regression: both paths reach the API upstream; adjacent/unrelated paths and foreign hosts remain denied before upstream access.
3. Update operator guidance and the affected capability statement.
4. Review, validate and install the configuration on the existing host; verify trusted HTTPS Swagger/schema, backend health and unauthorized API denial.

## Risk and review routing

Risk: L2, bounded public metadata exposure. Focused security/architecture and QA/docs review cover exact routing and unchanged authority. Human review focus: publicly readable schema is intentional, credentials are still required for protected API operations. Existing ingress proof and relevant documentation checks remain required. No claim that public Swagger implements login or grants project access.

## Evidence

Plan review found the exact shared proxy matcher sufficient. Real Caddy socket proof passes; removing the documentation paths or broadening `/docs` to a wildcard makes the corresponding regression fail at its intended assertion. Live deployment proof is recorded separately from these fixtures.

User-requested documentation extension: make the existing Rust issuer README a complete four-endpoint operator reference, including separate administrator bootstrap, request/response/token contracts, participant onboarding and unsupported recovery. Cross-link the existing Workstream bootstrap owner; introduce no new identity API or behavior. Validate the descriptions against the Rust routes and schemas and review the final docs delta.
