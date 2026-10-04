# WS-CLI-001 — First-class Workstream CLI

- Disposition: Planned
- Intent: Give humans and agents an installable terminal interface to public
  Workstream operations without creating another identity, authority, or product
  lifecycle implementation.
- Delivered boundary: [WS-CLI-001-01](WS-CLI-001-01.md), caller-owned profile and
  exact-project authorization context through the public REST API.

## Current boundary

The backend exposes `GET /api/v1/actors/me` and
`GET /api/v1/actors/me/authorization-context` in
`backend/app/api/routes/auth.py`. The selected 29-operation
[external-client drill](../../../docs/engineering/external-api-drill.md) covers
those operations, but is not a certification of every public or hidden route.
The independent [MCP adapter](../../../mcp_server/README.md) forwards caller
bearers to the same API; it is not a CLI client library. The independent Go
package under `cli/` implements `whoami` and `project access PROJECT_ID`, with
text/JSON output and built-binary integration proof. Further public workflows
and binary distribution remain proposed below.

## Design

Use one independently built Go `workstream` command. Commands call only public
REST operations; Workstream verifies the caller's Flow-issued bearer and owns
admission, authorization, policy, evidence, and all writes. The CLI does not
verify JWTs, call Flow Identity, import backend internals, cache roles, or infer
authority from a prior read. A human bearer used by an AI-driven CLI remains
that human's credential, not a registered agent identity.

Make every operation complete without a terminal: stable JSON output, safe
errors, exit status, and no required prompts. Add optional terminal assistance
only where it improves an actual workflow. A future `workstream ui` can browse
public queues and evidence when enough of that lifecycle is ready; it must use
the same client operations and never become a second state machine. Prefer
purposeful commands over generating a flag mirror of every OpenAPI route.

Go is the chosen implementation language. Cobra owns command parsing/help and
completion. Bubble Tea is a candidate for a later, bounded TUI change, not a
dependency of the foundation. Do not add Python, TypeScript, or Rust duplicate
CLIs. Keep the package independent of backend and MCP runtime dependencies.

## Proposed PR boundaries

1. **WS-CLI-001-01:** Independent Go package, safe caller-token transport, exact
   self-profile and project-authorization reads, human/JSON output, built-binary
   integration proof, package CI, and documentation. `GET /actors/me` can cause server-owned first
   admission and last-seen updates; the CLI must not describe it as side-effect
   free.
2. **Later self-service writes:** Profile editing and any further public
   self-service operation, with explicit omission/null and uncertain-mutation
   behavior. Define its own bounded record when started.
3. **Later governed-work commands:** Add project setup, task, submission,
   review, revision, and contribution reads/writes only as their actual public
   contracts and authority boundaries become available. Split by user journey,
   not one PR per endpoint or one giant catalogue PR.
4. **Optional TUI:** Add a focused public queue/evidence view after its API
   workflow is complete. Never require a TUI for agents or scripts.

## Risks and proof

The highest risks are bearer leakage, an unsafe configurable destination,
redirect/proxy credential forwarding, reporting stale authorization as current,
API shape drift, and falsely advertising hidden lifecycle work as live. Keep
tokens out of arguments, URLs, config files, output, logs, and error text;
reject non-loopback plaintext HTTP; fail closed on redirects and malformed
responses. Prove the first boundary through two built-binary, process-level
integration suites: one against an isolated real Workstream API for admission,
exact response parity, project authority and denial; one against an adversarial
HTTP fixture for credential/destination safety, malformed responses and
noninteractive output. The fixture is not a substitute for the real API.
Avoid function-level tests, coverage targets and duplicated assertions for
this CLI slice. Add a focused case only for a distinct observable contract or
reproduced failure. The shipped CLI calls only the two named public API routes;
test setup may use the documented local bootstrap to arrange authority but
cannot create a private CLI dependency.

The CLI is a separate client package, not an ADR 0014 backend adapter. It does
not change backend authority or deploy an external provider. A release process,
installer/signing, and a full contribution journey remain future boundaries;
source build and CI are not claims of public distribution.
