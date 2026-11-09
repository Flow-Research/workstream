# Login-based CLI and MCP private hosted proof

The current CLI and MCP adapter at `03f7f379c` were exercised against a temporary
Workstream API on the EC2 drill host and its existing database. Tokens came from
real password login to the external Rust issuer, not the offline fixture signer.
The API used the deployed backend's clean base image, exact issuer hostname and
verified private HTTPS JWKS. A pinned SSH tunnel exposed only a local API port.
This is private integration evidence, not public DNS/TLS or normal-deployment
issuer cutover.

## Verified behavior

- The actual compiled Go CLI and actual MCP server both resolved the new accounts
  through the public self API. The unprivileged participant could not list
  administrative grants or read the known Garden project.
- A temporary, explicit exact-project Project Manager grant enabled the new
  administrator account to create one draft Garden task through the CLI.
- CLI replay returned the identical full response. MCP replay of the same body,
  project and key returned that same response; changing the body under that key
  returned `409 idempotency_mismatch`.
- MCP's management read matched the task's identity, title, creator and source
  provenance. The participant's project and task reads returned concealed 404s.
- After revocation of the temporary Project Manager grant, both clients still
  authenticated for self reads but were denied the task read and exact replay.
  A retained successful receipt did not bypass fresh authorization.

The task remains an unreleased draft. No screening, claim, Submission, checker
execution, acceptance, award or paid inference occurred in this client proof.
The original Garden contribution drill remains separate evidence.

## Transport and limits

MCP used the actual SDK client and Streamable HTTP protocol `2026-07-28` against
the running adapter, which advertised 130 tools. Only the operations above were
exercised live. The adapter uses explicit bearer headers; this does not prove
OAuth discovery, a native ChatGPT/Codex connector or all advertised tools.
The CLI received its login token through its existing environment interface.
Tokens were kept in private temporary files and were not supplied as command
arguments, MCP arguments or committed evidence.

The CLI binary SHA-256 was
`ce1f8f37eba5c3e7167aa2f68c95a419e2a905e0acb60d2c998ca12726d99277`.
Focused CLI owner tests and 35 built-process HTTP tests passed; 114 focused MCP
authentication, protocol, project, workspace, task and privacy tests passed.
These complement the real hosted calls; they do not replace them.

The temporary project grant was revoked. Temporary client tokens, MCP process,
API candidate and SSH tunnel are removed after the proof; retained accounts,
the new administrator's cutover grant, task and authorization evidence remain.
The subsequent [active private cutover](demo-identity-active-cutover-2026-11-07.md)
records the normal deployment separately; the bounded evidence above remains
from the earlier temporary API.
