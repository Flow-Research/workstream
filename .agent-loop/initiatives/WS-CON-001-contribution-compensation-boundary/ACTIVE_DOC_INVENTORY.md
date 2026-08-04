# Active Documentation Inventory: WS-CON-001-PLAN4

## Direct reconciliation scope

This planning refresh updates the WS-CON-001 initiative package plus the stale
Required Implementation Order in the canonical contribution specification. It
does not change runtime code, migrations, other specification sections,
roadmaps, exports, workflows, or another initiative's files.

The active package is:

- `INTENT.md`, `DISCOVERY.md`, `PLAN.md`, `CHUNK_MAP.md`, and `STATUS.md`;
- `DECISIONS.md`, `RISKS.md`, and `SOURCE_MANIFEST.md`;
- `CONFORMANCE_MATRIX.md` and `RUNTIME_VERIFICATION.md`;
- `AUTHORIZATION_HANDOFF.md` and `JOINT_RELEASE_HANDOFF.md`;
- the PLAN4 contract and the reconciled `02B`, `02C`, `03A`, `03B`, `03C`,
  `03D`, `04B`, and `08A` contracts.
- `docs/spec_contribution_compensation.md` only to replace the obsolete linear
  dispatcher-first order with the reconciled partial order.

## Reconciled current-state sources

- current contribution/governance instructions in `AGENTS.md`,
  `CONTRIBUTING.md`, and `.agent-loop/README.md`;
- current capability truth in `docs/roadmap_status.md`;
- merged AUTH, ART, REV, XINT, and CON history through `2feaf47d`;
- current backend modules and migration graph;
- merged ART #249 runtime evidence and merged
  REV PLAN4 PR #258.

## Intentionally unchanged

Other canonical product specification sections remain aligned and are not
rewritten merely to restate this plan. Historical chunk evidence remains historical. Other
initiatives retain ownership of their own plans and runtime contracts. Local
roadmap XLSX/CSV exports are not changed because the roadmap is not changed.

The pre-existing deletion of
`docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.pdf`
is user-owned and remains untouched and unstaged.
