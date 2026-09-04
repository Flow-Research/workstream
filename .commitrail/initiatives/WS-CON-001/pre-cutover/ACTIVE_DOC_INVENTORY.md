# Active Documentation Inventory: WS-CON-001

## Current 02C implementation scope

Live implementation state is carried by `STATUS.md`, `SOURCE_MANIFEST.md`, the
`WS-CON-001-02C` chunk contract, `RUNTIME_VERIFICATION.md`, the 02C internal
review evidence and PR trust bundle, and the canonical schema sections in
`docs/spec_contribution_compensation.md` and `docs/architecture_data_model.md`.

`INTENT.md`, `DISCOVERY.md`, `PLAN.md`, `JOINT_RELEASE_HANDOFF.md`, and the
PLAN4 review artifacts are frozen historical planning evidence. Their recorded
PLAN4 SHA/head and planning-only stop statement are not live 02C status.

## Direct implementation scope

02C changes only the shared audit participant modules/tests, the exact
shared-audit note in `docs/architecture_data_model.md`, and WS-CON initiative
evidence. It adds runtime code but no migration, route, background executor,
product lifecycle behavior, roadmap/export, workflow, or other initiative change.

The PLAN4 package was:

- `INTENT.md`, `DISCOVERY.md`, `PLAN.md`, `CHUNK_MAP.md`, and `STATUS.md`;
- `DECISIONS.md`, `RISKS.md`, and `SOURCE_MANIFEST.md`;
- `CONFORMANCE_MATRIX.md` and `RUNTIME_VERIFICATION.md`;
- `AUTHORIZATION_HANDOFF.md` and `JOINT_RELEASE_HANDOFF.md`;
- the PLAN4 contract and the reconciled `02B`, `02C`, `03A`, `03B`, `03C`,
  `03D`, `04B`, and `08A` contracts.
- `docs/spec_contribution_compensation.md` only to replace the obsolete linear
  dispatcher-first order with the reconciled partial order.

## Reconciled current-state sources

- contribution/governance instructions at PLAN4 review time in `AGENTS.md`,
  `CONTRIBUTING.md`, and `.agent-loop/README.md`;
- current capability truth in `docs/roadmap_status.md`;
- merged AUTH, ART, REV, XINT, and CON history through the recorded PLAN4 baseline;
- current backend modules and migration graph;
- merged ART #249 runtime evidence and merged
  REV PLAN4 PR #258.

## Intentionally unchanged

Other canonical product specification sections remain aligned and are not
rewritten merely to restate this plan. Historical chunk evidence remains historical. Other
initiatives retain ownership of their own plans and runtime contracts. Local
roadmap XLSX/CSV exports are not changed because the roadmap is not changed.

The working-tree deletion of
`docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.pdf`
is user-owned, outside 02C scope, and remains untouched and unstaged. It is not
part of the 02C publication diff or its reference-spec integrity result.
