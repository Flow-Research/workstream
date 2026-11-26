# Remove obsolete repository material

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Remove superseded standalone experiments and documentation without changing product behavior or active qualification coverage.

## Intent and current behavior

The repository still carries a one-tool MCP prototype, an unused gVisor build
spike, an empty retired issuer directory, a local evidence JSON, and old planning
and review documents. Current documentation links a known stale architecture PDF.
These obscure the production MCP, Keycloak deployment and current specifications.

## Bounded change

Allowed: delete `experiments/mcp_caller_token/`, `experiments/pilot00_gvisor_offline/`,
`experiments/demo_identity/.gitignore`, `examples/terminal_benchmark/`,
`mcp-experiment-evidence.local.json`, `workstream_keyloack.md`, superseded calendar
plans, early `docs/review_*` and `docs/internal_reviews/` records, the gVisor spike
report and the stale architecture PDF. Update inbound Markdown links, current
documentation navigation, stale-document exclusion lists, PDF ignore rules and
this record. Historical references use immutable Git links, not replacement
archive copies.

Not allowed: product code changes, retained data deletion, CI weakening,
Commitrail history deletion or pre-cutover edits, pilot reorganization, removal
of active hosted-drill/identity fixtures, or overlapping implementation from
open submission/finance PRs.

## Proof retained and obsolete proof removed

The MCP prototype tests target its removed server/client. Production
`mcp_server/tests/test_protocol.py` retains exact caller isolation, no-store,
argument rejection, duplicate authorization and ingress bounds; production
HTTP gateway tests retain transport/response safety. Loopback-only prototype
configuration tests do not define the deployed OAuth service contract.
The gVisor tests protect only the removed spike's shell lifecycle. No current
code consumers were found for either experiment. Active Smol qualification,
production MCP tests, backend tests and all CI selection remain unchanged.

## Acceptance criteria

- Obsolete paths are removed and retained Markdown links resolve or point to
  their exact historical source.
- Current navigation leads to maintained documentation, not removed reports.
- Stale-wording, Markdown, Commitrail and diff checks pass.
- Focused production MCP regression checks pass; no suite selection is weakened.
- No pre-cutover file or active pilot/hosted fixture changes.

## Risk and review routing

- Risk class: L2
- Required reviewers: documentation and test_delta/ci_integrity (combined bounded review).
- Human review focus: deletion scope and preservation of active verification.

## Reconciliation

The roadmap changes only its obsolete MCP experiment reference. No runtime
capability or deployment status changes. No local spreadsheet exports are present.
Pilot naming, active drill consolidation and Commitrail history remain separate
follow-up work explicitly excluded by the user from this pass.
