# WS-CLI-001 — First-class Workstream CLI

- Disposition: Planned
- Intent: Give humans and agents an installable terminal interface to public
  Workstream operations without creating another identity, authority, or product
  lifecycle implementation.
- Delivered boundary: [WS-CLI-001-01](WS-CLI-001-01.md), caller-owned profile and
  exact-project authorization context; [WS-CLI-001-02](WS-CLI-001-02.md), human
  self-profile editing through the public REST API; [WS-CLI-001-03](WS-CLI-001-03.md),
  exact-project inspection with server-owned full/minimal disclosure;
  [WS-CLI-001-04](WS-CLI-001-04.md), public manager task pagination and detail;
  [WS-CLI-001-05](WS-CLI-001-05.md), contributor ready-task discovery and instructions;
  [WS-CLI-001-06](WS-CLI-001-06.md), public contributor claim/start with explicit retry keys;
  [WS-CLI-001-07](WS-CLI-001-07.md), contributor governing context and locked intake requirements;
  [WS-CLI-001-08](WS-CLI-001-08.md), draft project shell creation with explicit caller-owned replay;
  [WS-CLI-001-09](WS-CLI-001-09.md), guide declaration, illustrative tasks and document upload selectors;
  [WS-CLI-001-10](WS-CLI-001-10.md), declared-original upload with hash/size-bound storage receipts;
  [WS-CLI-001-11](WS-CLI-001-11.md), latest exact-guide setup diagnostics and compilation lineage;
  [WS-CLI-001-12](WS-CLI-001-12.md), exact finalized-proposal findings and policy inspection;
  [PILOT-13](../../changes/pilot13-assigned-task-guide-documents.md), assigned-task locked-guide listing/download.

## Current boundary

The backend exposes `GET /api/v1/actors/me` and
`GET /api/v1/actors/me/authorization-context` in
`backend/app/api/routes/auth.py`. The selected 29-operation
[external-client drill](../../../docs/engineering/external-api-drill.md) covers
those operations, but is not a certification of every public or hidden route.
The independent [MCP adapter](../../../mcp_server/README.md) forwards caller
bearers to the same API; it is not a CLI client library. The independent Go
package under `cli/` implements `whoami`, `project access PROJECT_ID`, and
`profile update` for caller-owned human display fields. `project show PROJECT_ID`
reads only the existing public project's server-selected disclosure shape.
`project tasks PROJECT_ID` and `project task PROJECT_ID TASK_ID` add the public
manager queue/detail journey with server-owned authority on each page.
`task ready PROJECT_ID` and `task show TASK_ID` add the contributor projection
with exact Submitter authority and server-owned assignment visibility.
`task claim TASK_ID --idempotency-key UUID` and `task start` add the public
contributor writes, with server-owned fresh authority, assignment and lineage.
Exact caller keys support manual replay; uncertainty never triggers automatic retries.
`task context TASK_ID` and `task requirements TASK_ID` read governing guide,
policy selectors, server action hints and locked intake rules. Hints are not
authority; these reads do not expose the hidden submission intake.
`project create --name TEXT --slug TEXT --idempotency-key UUID` creates a draft
shell through the public POST. The API owns system-scoped creation authority
and committed recovery; guide upload, approval and activation are not added.
`project guide create PROJECT_ID --input FILE --idempotency-key UUID` declares
a draft guide, task examples and document targets; setup awaits document upload.
This is a stored creation receipt, not live readiness. The API reauthorizes
guide creation replay, unlike project-shell committed recovery.
`project guide upload PROJECT_ID GUIDE_ID DOCUMENT_ID --file FILE --media-type
MIME --idempotency-key UUID` streams one declared original through the public
binary POST and rechecks the open original's size, modification time and full hash
before success. Its exact-byte receipt establishes storage only, not setup readiness,
approval or activation; unconfirmed outcomes require deliberate unchanged-input
replay. `task guide TASK_ID [--download DIR]` lists or downloads the assigned
task's locked originals with verified byte identity; setup examples stay private.
`project guide setup PROJECT_ID GUIDE_ID` reads the latest exact-guide setup
and compilation lineage through one public GET. It does not poll, execute setup,
approve policies or activate the guide; successful reading is not readiness.
`project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID` reads the explicit
finalized proposal, complete findings, requirements and intake/evaluation
bindings, without selecting latest, approving, correcting or activating it.
All have text/JSON
output and built-binary integration proof. Mutations preserve omitted/null
semantics and explicitly report uncertain outcomes without automatic retries.
Further public workflows
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

## Delivered and later boundaries

1. **WS-CLI-001-01:** Independent Go package, safe caller-token transport, exact
   self-profile and project-authorization reads, human/JSON output, built-binary
   integration proof, package CI, and documentation. `GET /actors/me` can cause server-owned first
   admission and last-seen updates; the CLI must not describe it as side-effect
   free.
2. **WS-CLI-001-02:** Human profile editing through the existing public PATCH,
   with explicit omission/null and uncertain-mutation behavior. It changes no
   identity, authority or backend policy.
3. **WS-CLI-001-03:** Inspect a known project alongside its current authority,
   through the public project read. Preserve administrative/contributor response
   boundaries; do not invent a public project-list contract.
4. **WS-CLI-001-04:** Browse a manager task page and open its exact project/task
   detail, passing opaque continuation unchanged without automatic pagination.
5. **WS-CLI-001-05:** Discover one ready-task page and inspect contributor
   instructions through public reads, without management metadata or task writes.
6. **WS-CLI-001-06:** Claim ready work and start the caller's assignment through
   public POSTs with caller-supplied keys, exact response validation and explicit
   uncertain outcomes. No local authority decisions or operator override.
7. **WS-CLI-001-07:** Inspect contributor work context and exact submission
   requirements through public reads. Preserve historical selectors, server
   hints and contributor disclosure without fetching files or evaluating policy.
8. **WS-CLI-001-08:** Create a draft project shell through the public POST with
   explicit caller-supplied keys, exact 201/full-response validation and unknown
   outcomes. Reuse project inspection parsing/output; no guide activation.
9. **WS-CLI-001-09:** Declare a guide, required illustrative tasks and source
   document targets through public POST using an exact bounded JSON file.
   Setup awaits actual original upload.
10. **WS-CLI-001-10:** Upload one declared PDF/DOCX/PPTX or UTF-8 Markdown (`.md`)
   original through public binary POST; validate storage receipt against local bytes and preserve manual
   replay custody. Approval and activation remain.
11. **WS-CLI-001-11:** Inspect latest exact-guide setup and compilation lineage
    through the public diagnostic read. No polling, local readiness rules,
    execution, approval or activation.
12. **WS-CLI-001-12:** Inspect an explicitly selected finalized proposal through
    its public GET, retaining complete display findings and distinct intake and
    evaluation proposals without making a decision or substituting latest.
13. **Later governed-work commands:** Add further project setup, submission,
   review, revision, and contribution reads/writes only as their actual public
   contracts and authority boundaries become available. Split by user journey,
   not one PR per endpoint or one giant catalogue PR.
14. **Optional TUI:** Add a focused public queue/evidence view after its API
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
reproduced failure. The shipped CLI calls only the named public API routes;
test setup may use the documented local bootstrap to arrange authority but
cannot create a private CLI dependency.

The CLI is a separate client package, not an ADR 0014 backend adapter. It does
not change backend authority or deploy an external provider. A release process,
installer/signing, and a full contribution journey remain future boundaries;
source build and CI are not claims of public distribution.
