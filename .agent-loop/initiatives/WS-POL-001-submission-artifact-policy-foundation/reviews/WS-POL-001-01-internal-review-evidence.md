# Internal Review Evidence: WS-POL-001-01

## Chunk

WS-POL-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 8b51a84b1bede193bbafe0b1eeb7b7981a271a0e

Reviewed at: 2026-06-26T21:22:31Z

Reviewer run IDs: 019f05c6-67db-7650-9f9e-d7313cfa3969, 019f05c6-6e02-7ca2-8d2f-1881c51ffd71, 019f05c6-71c2-7cc0-b86b-cab012596f23, 019f05c6-755b-7892-b9d3-cbd5a5bffdd6, 019f05c6-7d33-7af0-bbdf-340ff8ad6634, 019f05c6-848e-7b22-9405-1ee70f67ae55, 019f05c9-2556-7730-bed9-6d21ebf9fb20, 019f05cc-a82a-7d90-8277-2e13d0417252, 019f05cc-aa78-7ee0-922c-be066be11538

After reviewed SHA `8b51a84b1bede193bbafe0b1eeb7b7981a271a0e`, only review evidence, initiative status, and loop state changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed planning-vs-implementation separation, project-scoped `PreSubmitCheckerPolicy`, no per-task checker generation, `locked_pre_submit_checker_bundle_hash` as compiled bundle hash, and activation/READY boundaries. Low risk: some summary docs omit the word compiled while canonical docs are explicit. |
| QA/test | PASS WITH LOW RISKS | None | Confirmed project-guide-version checker reuse, blocked/split uncovered task sets, activation/READY locks, submission provenance, and strengthened stale-wording tests. Low risk: archived internal review docs intentionally preserve old target wording. |
| security/auth | PASS WITH LOW RISKS | None | Confirmed immutable guide-source bundle, server-derived source snapshot hash, append-only approved rows, non-weakening defaults, locked compiled bundle hash, constrained runtime parameters, and narrow stale-wording skip. Low risk: one plan sentence uses shortened sufficiency wording while chunk/data contracts include warning acknowledgement. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed project-owner boundary, setup checklist, activation/READY gates, pre-submit failure separation from review decisions, and no per-task checker generation. Low risk: setup checklist ordering is acceptable but could be polished later. |
| architecture | PASS WITH LOW RISKS | None | Confirmed no boundary violation, project/guide-version-scoped checker bundle, immutable `GuideSourceSnapshot`, chunk separation, and no hidden per-task policy channel. Low risk: runtime enforcement is future work by design. |
| ci integrity | PASS WITH LOW RISKS | None | Confirmed no workflow/package weakening, exact reviewer result parsing, reviewed-SHA binding, narrow stale-wording skip, and fail-closed agent gate behavior when `--fail-on-high` is used. Low risk: the default PR workflow keeps the static agent gate advisory, unchanged from main. |
| docs | PASS WITH LOW RISKS | None | Confirmed docs/templates cover guide-source snapshot id/hash, `locked_pre_submit_checker_bundle_hash`, pre-submit failure API contract, and product/engineering loop separation. Medium human-review risk remains only PR breadth. |
| reuse/dedup | PASS WITH LOW RISKS | None | Confirmed no duplicate task-owned policy/checker path, internal/external review separation, and one implementation table path for `SubmissionArtifactPolicy`. Low risk: `SubmissionArtifactPolicy` and `ProjectSubmissionArtifactPolicy` wording must stay explicit during implementation. |
| test delta | PASS | None | Confirmed tests were strengthened, no assertions were weakened, stale-wording coverage is additive, exact reviewer-result tests remain active, and reviewed-SHA binding remains covered. |

## Valid Findings Addressed

- Removed rejected per-task policy/checker generation from active contracts.
- Locked the project-guide-version model: every task under the same active guide
  version reuses that guide version's project `PreSubmitCheckerPolicy`; uncovered
  task sets block activation or are split into another project/guide.
- Clarified that `locked_pre_submit_checker_bundle_hash` means
  `PreSubmitCheckerPolicy.compiled_bundle_hash`, not a generic policy hash.
- Added immutable `GuideSourceSnapshot` bundle semantics with canonical
  manifest hash, source item refs, server-derived source hash, and activation
  invalidation rules.
- Added project activation and task `READY` gates requiring guide-source
  snapshot id/hash, effective project submission artifact policy hash, and
  project pre-submit checker bundle hash.
- Updated submission packet provenance to include locked guide-source snapshot
  id/hash, effective project submission artifact policy hash, and checker bundle
  hash from server-owned task context.
- Replaced stale target wording that read from `task.required_evidence` with the
  locked project `PreSubmitCheckerPolicy` and effective project submission
  artifact policy path.
- Documented that this PR is planning approval only. Runtime product behavior,
  schema/API changes, and frontend changes remain out of scope until the
  implementation chunk is approved.
- Expanded stale-wording guard coverage for rejected per-task policy/checker
  names and narrowed the historical-review skip to `docs/internal_reviews/`.
- Preserved separation between internal sub-agent evidence and external
  CodeRabbit/GitHub/human review response artifacts.

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
Markdown link check passed for 41 changed Markdown files.
Stale wording check passed.
25 agent gate tests passed.
Loop memory state check passed.
git diff --check passed.
Agent gate result: REVIEW_REQUIRED because this planning PR is large and touches risk-sensitive policy/spec/test-gate files.
```

## Remaining Risks

- `WS-POL-001-01` is planning-only and is not backend implementation approval.
- Runtime enforcement remains for later chunks, especially compiler execution,
  task locked-context persistence, and submission runtime migration.
- Human review must accept the large planning PR breadth before merge.
- Historical review archives under `docs/internal_reviews/` intentionally
  preserve old wording and are skipped by the stale-wording scan.
