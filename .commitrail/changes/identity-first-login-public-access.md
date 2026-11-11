# First-login password change and public demo access

Initiative: None
Status: Planned
Risk: L1 — identity credentials and public ingress

## Intent

The administrator creates participant accounts with an initial password through
the existing external Rust issuer API. First login returns only a short-lived
password-change credential. The participant must choose a different password
before receiving Workstream access. Email remains an unverified identifier;
mail delivery, inbox verification and public signup are explicitly deferred.
Finish the existing public HTTPS boundary for identity, API and MCP, then prove
participant login and client access. Workstream owns no password/login service.

## Allowed files

- experiments/demo_identity/** and its affected integration fixtures.
- deploy/hosted/{demo-identity.Caddyfile,compose.mcp.yml,compose.py,preflight.py,
  release.env.example,README.md} plus bounded public-ingress files if required.
- MCP host/origin configuration only if the existing setting cannot securely
  represent the public endpoint; affected deployment/client tests.
- Affected current docs, docs/roadmap_status.md and this record.
- scripts/test_public_ingress.py and .github/workflows/demo-identity.yml for
  actual Caddy transport proof in the existing issuer lane (no new lane).

## Prohibited changes

No product permission changes, automatic project grants, public signup, email
verification claims, SMTP, OAuth implementation, replacement identities, deleted
retained data, disabled TLS checks, exposed database/native-checker ports or
unrelated changes to PR #704. Existing issuer subjects and signing keys persist.

## Plan and acceptance

1. Persist must_change_password for newly provisioned participants. Bootstrap
   administrator is created locally with its chosen password. Provide an explicit `upgrade DATA_DIR` command for a versioned,
   transactional schema upgrade preserving existing identities; conservatively
   require retained non-admin accounts to rotate, never invent prior rotation.
2. Initial login returns a purpose-specific credential with a separate audience,
   bounded lifetime and no Workstream access/admin token or access scope. Only
   the existing password-change operation accepts it. Enforce current password,
   different new password, pending rotation and atomic compare-and-swap; replay
   and concurrent changes cannot reuse that first-login credential after success.
   A subsequent normal login yields standard Workstream access. Ordinary password
   changes continue through the same operation. Existing access JWTs retain their
   documented short expiry; deployment cutover stops the old issuer and waits out pre-upgrade tokens
   through the maximum 900-second lifetime plus configured verifier skew.
3. Preserve generic invalid-login responses and bounded hashing/rate limits.
   Prove password-change credentials reject at the actual Workstream verifier,
   issuer administration, and after use/expiry; test restart and retained-state
   migration, no reset on subsequent restarts, and concurrent changes.
4. Configure Caddy public certificates for the DNS names now pointing at the new
   Elastic IP. Proxy API and /mcp using exact public virtual hosts, fixed loopback MCP
   upstream Host and unchanged Origin (browser origins remain denied);
   upstreams stay loopback, identity upstream TLS stays verified. Do not trust
   client-supplied forwarding headers as authority. Preserve upload size/time
   limits deliberately rather than applying the identity 4KiB limit to ZIPs.
5. Test external trusted HTTPS, new account initial login -> change -> normal
   login -> unchanged real verifier, CLI and SDK MCP calls. Unauthorized requests
   must remain denied. No claim that testing one tool proves all tool behavior,
   native OAuth discovery, or external connector compatibility.

Plan review: PASS WITH LOW RISKS. Explicit migration, atomic pending/hash
comparison, expiry-plus-skew drain and hostile Host/Origin regressions are
required; API transport budgets must accommodate the existing 3400-second
preparation deadline plus upload time (3600-second response, 4200-second write).
No new MCP configuration or consumed-token subsystem is needed.

## Verification and review

Run issuer Rust tests, real HTTPS verifier tests, affected container/deployment
and MCP configuration tests. Use discriminating regressions for token audience,
purpose, consumed rotation and atomic update. Run plan review before code and
focused security/architecture plus QA/test-delta/docs review of the frozen head.
Assess roadmap and current deployment docs; full hosted checks before readiness.
Human focus: credential delivery remains private and out-of-band; email is not
verified; API/MCP require bearer authentication and Workstream authorization;
public TLS and localhost custody are independently proven.
