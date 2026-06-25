# Internal Review Evidence: WS-POL-001-01

## Chunk

WS-POL-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 2892c9d4cbe6d8e8e33fcbe37a84384193f003af

Reviewed at: 2026-06-25T15:44:21Z

Reviewer run IDs: 019eff2d-7d6f-7933-a5e2-c367ae5ae953, 019eff2e-bbf3-7bb0-b346-8ef3d3476c00, 019eff30-9758-75b2-997c-1afdf511bdf5, 019eff01-0840-7a32-b1a9-db38219edd0d, 019efec1-1d2a-7060-94b8-198914e52e8c, 019eff32-f3fc-7a22-8a21-06964464008d, 019eff36-0550-77a2-9935-e9780b94b693, 019eff4c-42bf-7482-b4bd-1de84dab816e, 019efec6-1c3d-70a2-929e-e1312ea2ff21

After reviewed SHA `2892c9d4cbe6d8e8e33fcbe37a84384193f003af`, only review evidence changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None remaining | Confirmed the project-scoped `PreSubmitCheckerPolicy` model is coherent. Earlier stale evidence blocker was fixed. |
| QA/test | PASS AFTER FIXES | None remaining | Confirmed stale-model patterns are wired into the gate/test, Chunk 2 has compiler semantic rejection proof obligations, and Chunk 3 has runtime-parameter negative proof obligations. Evidence refresh was the only remaining process item. |
| security/auth | PASS WITH LOW RISKS | None | Confirmed source-ref canonicalization, duplicate source rejection, runtime-parameter constraints, compiler default/severity rejection, and final project checker activation boundary. Low risk is that this is planning contract, not runtime implementation. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed project owner supplies material/business terms while Workstream derives internal policy, pre-submit failures are not review decisions, and long-term `evidence_policy` wording is rejected. |
| architecture | PASS WITH LOW RISKS | None | Confirmed no boundary violation. Chunk 1/2/3 split remains records and guards, compiler/enforcement, then task locked-context migration. |
| ci integrity | PASS | None | Confirmed the stale-wording gate is stricter, no bypass or allowlist was added, and regression tests cover the new rejected-model patterns. |
| docs | PASS AFTER FIXES | None remaining | Found and fixed remaining ambiguous active docs around task-policy wording, generated project checker wording, and effective project submission artifact policy wording. |
| reuse/dedup | PASS WITH LOW RISKS | None | Confirmed the change extends existing stale-wording checker/test logic without duplicated gate logic. Optional future cleanup can consolidate git file collection helpers. |
| test delta | PASS WITH LOW RISKS | None | Confirmed tests were strengthened, no assertions were weakened, and new pattern coverage is explicit. Low risk is manual synchronization between pattern list and fixture set. |

## Valid Findings Addressed

- Removed the rejected per-task policy/checker generation model from active docs.
- Restored the first-principles model: project guide, guide source snapshot,
  sufficiency report, project submission artifact policy, effective project
  policy, project `PreSubmitCheckerPolicy`, then tasks lock references to that
  context.
- Documented that `ProjectGuideSufficiencyAgent` checks the project guide
  against the project task set. If the guide does not cover the tasks,
  activation is blocked and the guide is improved or work is split into another
  project/guide.
- Removed stale submission provenance fields from the rejected per-task policy
  model.
- Added exact bundle-hash canonicalization:
  `sha256(canonical_json(manifest_json))` with UTF-8, sorted keys, deterministic
  source-item ordering, volatile-field exclusions, and duplicate source-item
  rejection.
- Added compiler semantic coverage rules: omitted required artifacts, skipped
  evidence rules, weakened severity, omitted platform defaults, and untraceable
  compiled rules must be rejected.
- Added task runtime parameter constraints: v0.1 uses only trusted task-contract
  fields, no free-form parameter map, and no runtime override of checks,
  severity, storage, forbidden artifacts, hash algorithm, or platform defaults.
- Expanded the stale wording gate to block the rejected task-owned policy/checker
  model and added regression coverage in `scripts/test_agent_gates.py`.
- Updated checker specs, templates, lifecycle docs, product flows, roadmap docs,
  packet conventions, ADRs, and the external review response to use the project
  `PreSubmitCheckerPolicy` model consistently.

## Commands Run

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

## Results

```text
Markdown link check passed for 39 changed Markdown files.
Stale wording check passed.
24 agent gate tests passed.
Loop memory state check passed.
git diff --check passed.
Agent gate result: REVIEW_REQUIRED because this bootstrap planning PR is large and touches risk-sensitive policy/spec/test-gate files.
```

## Remaining Risks

- `WS-POL-001-01` is planning-only and is not backend implementation approval.
- Chunk 2 must implement and test compiler semantic rejection, runtime parameter
  constraints, and the compiled project `PreSubmitCheckerPolicy` activation
  gate before backend enforcement is considered complete.
- Human review should confirm the corrected project-level checker model before
  merge.
