# Public identity and native client qualification

The deployment qualification used implementation commit
`7719a81496295cb824b78c9df2cdd1c0591325b5` and the issuer image
`sha256:fadd9a76fe8bcefd04fa1345da0fe4f1bd41daa206968a6df5217d8f6307fed2`.
It retained the existing backend, checker, CLI and MCP artifacts and contribution
facts. Subsequent documentation changes do not imply a different deployed image.

## Observed behavior

- Both `identity.flowresearch.tech` and `workstream.flowresearch.tech` resolved
  to the replacement host's Elastic IP and served publicly trusted HTTPS.
- The explicit issuer upgrade preserved every existing subject, email, password
  hash, administrator flag and the signing key. Retained non-admin accounts
  required password rotation. The old issuer was stopped and its maximum token
  lifetime plus clock-skew margin elapsed before participant access resumed.
- Administrator API provisioning created a separate test participant. Initial
  login returned only a password-change credential. Workstream rejected that
  credential; changing the password enabled normal login and the old password
  was rejected. No product grants were added to that account.
- An existing admitted contributor also completed the mandatory change. Reusing
  the consumed credential and choosing the same password were rejected. The
  contributor retained their original actor and project authority.
- The deployed CLI and real MCP SDK each performed four public HTTPS operations:
  own profile, concealed denial for a closed assignment's work context, accepted
  Submission read, and exact ContributionRecord read. Both clients matched the
  previously retained accepted submission/contribution evidence.
- Public MCP discovery returned 132 tool definitions. A browser-Origin request
  was rejected with 403; a profile tool call without a bearer returned an explicit
  401 tool error. A substituted public Host returned 404. Forwarding-header
  substitution did not redirect the health request.
- A fresh independent instance of Workstream's unchanged verifier fetched the
  public HTTPS JWKS using ordinary CA roots, accepted an access token and
  rejected the separate issuer-administration token.

## Supporting checks and limits

Seven optimized Rust tests, three real HTTPS/verifier tests and the isolated
container restart/account proof passed. The earlier debug timing failure was
resolved by running the optimized release; its timing assertion was unchanged.
The real Caddy socket test proves route/header custody, verified issuer upstream
TLS, oversized identity-request rejection and API byte preservation. API and MCP
body ceilings are asserted in the adapted configuration; this test does not send
oversized bodies to those two routes. The final BuildKit image independently
passed the container proof before immutable registry publication.

Email remains an unverified login identifier. Initial credentials are delivered
privately out of band; SMTP, inbox verification and public signup are not enabled.
This supports native bearer MCP clients, not OAuth-only connectors or browser
MCP sessions. Four authenticated tools are representative live evidence, not a
claim that all 132 tools were individually exercised. No new contribution,
award, payment or human-review outcome is claimed by this access qualification.
The preceding product drill supplies that separate lifecycle evidence.

See the [public access runbook](../../deploy/hosted/PUBLIC_ACCESS.md) and
[issuer account contract](../../experiments/demo_identity/README.md).
