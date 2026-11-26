# Remove obsolete repository material

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Remove superseded experiments, documentation and unused actor-migration tooling without changing current product behavior or weakening retained verification.

## Intent

The repository still carries a one-tool MCP prototype, an unused gVisor build
spike, an empty retired issuer directory, a local evidence JSON, and old planning
and review documents. Current documentation links a known stale architecture PDF.
These obscure the production MCP, Keycloak deployment and current specifications.
The unused actor-classification utility also remains after its migration consumer
was retired; remove that tool and its exclusive tests together.

## Bounded change

Allowed: delete `experiments/mcp_caller_token/`, `experiments/pilot00_gvisor_offline/`,
`experiments/demo_identity/.gitignore`, `examples/terminal_benchmark/`,
`mcp-experiment-evidence.local.json`, `workstream_keyloack.md`, superseded calendar
plans, early `docs/review_*` and `docs/internal_reviews/` records, the gVisor spike
report and the stale architecture PDF. Update inbound Markdown links, current
documentation navigation, stale-document path lists, PDF ignore rules and
this record. Historical references use immutable Git links, not replacement
archive copies.

Not allowed: product behavior changes beyond removing the unused utility, retained data deletion, CI weakening,
Commitrail history deletion or pre-cutover edits, pilot reorganization, removal
of current Keycloak or production external-checker verification, or changing
the implementation branches of
open submission/finance PRs.

Also allowed: remove the superseded actor-classification migration utility
(`backend/app/modules/actors/legacy_classification.py`), its CLI and exclusive
test module; update their exact ownership, identifier and test-lane inventory
entries, the existing exact migration-tool removal allowlist in
`backend/scripts/behavior_ownership.py` (verified by the existing rejection test
in `backend/tests/test_behavior_ownership.py`), and the semantic-family fingerprint in
`backend/tests/test_ci_lane_catalogue.py`. It reads the retired `actor_identities` layout and has no importer in
current product code or Alembic migrations. No current schema, migration or
authentication behavior changes.

## Retire the superseded hosted experiment

The user explicitly requires removal of the simulated issuer and old PILOT-04
execution path. `HostedAttachment.inspect` requires the simulated issuer and
`token_for_label` mints fixture tokens. This cannot qualify current Keycloak.
The PILOT-04 directory is a standalone test harness, not the production Rust
runner/SDK in `external_checkers/`.

Allowed: remove the remaining `experiments/` tree and its exclusive
`scripts/test_public_guide_journey.py`, `test_public_hosted_attachment.py`,
`test_public_hosted_model_post.py`, and `test_public_smol_proof.py`; remove only
backend test cases exclusively exercising that retired harness; reconcile
release-image workflow references, current documentation links and historical
links. Keep real Keycloak provider/browser/signup tests, production checker
service/intake tests and product lifecycle/authorization tests. Do not replace
the retired code with another fake issuer, compatibility import or renamed
copy. Any distinct current behavior whose only proof lives here must retain
proof in its current owner before deletion.

PR #708 changes this harness. Reconcile its integration against the deletion;
this cleanup does not edit or claim delivery of that separate implementation.

## Proof retained and obsolete proof removed

The MCP prototype tests target its removed server/client. Production
`mcp_server/tests/test_protocol.py` retains exact caller isolation, no-store,
argument rejection, duplicate authorization and ingress bounds; production
HTTP gateway tests retain transport/response safety. Loopback-only prototype
configuration tests do not define the deployed OAuth service contract.
The gVisor tests protect only the removed spike's shell lifecycle. No current
code consumers were found for either experiment. Active Smol qualification,
production MCP tests and all retained backend tests remain selected. Only the
deleted classifier test module is removed from the lane catalogue; the exact
semantic-family count and digest are updated to match that deletion.

## Acceptance criteria

- Obsolete paths are removed and retained Markdown links resolve or point to
  their exact historical source.
- Current navigation leads to maintained documentation, not removed reports.
- Stale-wording, Markdown, Commitrail and diff checks pass.
- Focused production MCP regression checks pass; no suite selection is weakened.
- No pre-cutover file or sample project assets change; current Keycloak and
  production checker verification remain.

## Risk and review routing

- Risk class: L2
- Required reviewers: documentation, test_delta/ci_integrity and focused security/architecture review for removal of the unused migration utility.
- Human review focus: deletion scope and preservation of active verification.

## Evidence

Markdown link and all four stale-document scans pass. The retained-link scan
finds no references to removed files outside immutable pre-cutover snapshots.
The 33 lightweight-gate and stale-review tests pass. Production MCP protocol
and gateway regressions provide the retained caller-isolation and transport
proof; exact execution results and reviewer freshness belong in the PR.
Workflow selection changes remove only tests and filters belonging to the
retired experiment. Release-image build checks and current identity/checker
verification remain. The backend catalogue removes only the deleted classifier
module; retained selection and arbitrary-removal rejection remain enforced.

## Reconciliation

The roadmap records retirement of the runnable simulated-issuer harness and
updates the obsolete MCP experiment reference. No product runtime capability
or deployed identity changes. No local spreadsheet exports are present.
Pilot project naming and Commitrail history remain separate follow-up work.
The retained setup/checker tests protect product behavior; removed cases only
exercised the retired recorded runtime, harness sequencing and trace wrapper.
Real Keycloak/provider/browser tests stay under the current identity deployment
and production checker verification remains in its existing owners.
