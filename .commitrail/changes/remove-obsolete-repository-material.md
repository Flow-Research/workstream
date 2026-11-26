# Remove obsolete repository material

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Remove retired experiments and duplicate documentation; organize retained examples and current contracts without changing product behavior.

## Intent

The user requires an audited, maintainable repository with obsolete development
paths removed. Retired simulated identity, internal checker experiments, unused
migration tooling, calendar plans and repeated presentation/report documents
obscure current Keycloak, production external checkers and maintained contracts.
Keep each current requirement in its owner documentation rather than parallel
historical implementations. Git retains deleted history; do not copy it into a
new archive directory.

## Bounded change

Allowed:

- Remove the remaining `experiments/` tree: one-tool MCP prototype, gVisor spike,
  simulated hosted identity and PILOT-04 harness, with their exclusive tests.
  Remove root local MCP evidence, obsolete Keycloak handoff and two obsolete
  Terminal Benchmark history notes.
- Remove the unused actor-classification utility, its CLI and exclusive tests.
  Its retired `actor_identities` consumer is absent from current migrations and
  product code. Update only its exact ownership, identifier and test-lane entries,
  existing exact removal allowlist, and semantic-family count/digest.
- Remove superseded calendar/chunk plans, early review records, dated reports,
  duplicate HTML/architecture-brief presentation and its exclusive renderer.
  Consolidate principles and role guidance into their existing canonical owners.
  Reconcile current project-guide requirements into `spec_project_guides.md`;
  rename the retained task specification to `spec_task_assignment.md`.
- Move Garden, Terminal Systems and Incident Summary sample assets from `pilots/`
  into their respective `examples/` directories. Preserve checker/fixture/guide
  bytes apart from path instructions; update real consumers and workflow paths.
- Repair current navigation, stale scanner path inventories and affected roadmap
  references. Historical citations use immutable Git links. Preserve Commitrail
  prose and repair its links only, excluding pre-cutover snapshots entirely.
- Replace the stale backend component PUML/SVG pair with one inline Mermaid view
  in its existing Markdown owner. Reconcile claim-start and optional setup docs.

Prohibited: product behavior changes beyond removing the unused classifier;
retained data/schema deletion; compatibility copies; weaker CI or lost required
proof; Commitrail history/source-manifest deletion; pre-cutover edits; modifying
other agents' submission or finance branches; claiming new hosted qualification.
Imported `docs/reference_specs/` inputs remain because preserved source manifests
bind them. No local spreadsheet exports are present.

## Proof ownership

Production MCP protocol/gateway tests retain caller isolation, no-store,
argument/duplicate authorization rejection and transport bounds. Removed MCP and
gVisor tests only target their deleted experiments. Current Keycloak and
production external-checker tests remain in their owners.

The retired hosted harness required a simulated issuer and minted fixture tokens;
it does not qualify current Keycloak. Its four exclusive script suites and three
exclusive backend test functions are removed. Retained setup/runtime tests still
cover actual adapter behavior, custody, cancellation, quotas and lifecycle rules.
Release-image workflows retain image build/inspection, parser, AWS and identity
checks. Sample workflow test/build selection remains the same at the new paths.

The deleted classifier's exclusive module is the only backend lane module
removed. Exact inventory checks and rejection of arbitrary removals remain.
The `legacy_actor_identities` retained data/model is not touched.

## Acceptance criteria

- Removed paths have no current runtime/workflow consumers or broken Markdown
  links; historical references point to their exact Git source.
- Each retained sample has a clear purpose, with byte-preserving functional moves
  and passing checker tests; no alias remains at its old path.
- Current docs describe optional setup proposals, independent external PRE/POST,
  claim immediately starting work, and policy-governed automatic acceptance while
  preserving the default human-review branch and its planned runtime boundary.
- Focused retained product, ownership/catalogue, deployment and documentation
  checks pass. No test deletion loses a distinct current requirement.
- Commitrail history and other agents' branches remain untouched apart from
  non-pre-cutover link repairs. No deployment/runtime changes are claimed.

## Risk and review routing

- Risk class: L2.
- Required review: documentation, architecture, test-delta and CI integrity;
  focused security review of the unused actor-migration utility removal.
- Human focus: obsolete versus current material, retained proof, current-doc
  ownership and integration reconciliation by other branches after merge.

## Evidence

Run Markdown links, all four stale-document scans, Commitrail and diff checks.
Retained MCP protocol/gateway, ownership/identifier/catalogue, setup/runtime,
hosted configuration/release-image/Keycloak and sample checker tests provide
focused regression evidence. Exact commands, outcomes and reviewer head freshness
belong in the PR. Documentation path changes do not prove a new live drill.

## Roadmap impact

The ledger retires the runnable simulated-issuer harness, corrects example and
contract links and distinguishes historical drill evidence from current runnable
qualification. Runtime capability and deployed readiness are unchanged. Current
subsystem requirements stay in maintained specifications; superseded plans remain
accessible through Git history, not as implementation authority.
