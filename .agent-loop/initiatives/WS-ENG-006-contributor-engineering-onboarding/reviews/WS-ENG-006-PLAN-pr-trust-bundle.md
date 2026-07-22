# PR Trust Bundle

## Chunk

`WS-ENG-006-00` — First-new-initiative planning intake and exact root repair

Merge intent: `.agent-loop/merge-intents/WS-ENG-006-00.json`

## Goal

Make the engineering loop work from a contributor's first non-trivial change:
one reviewed planning-only intake establishes a new initiative, then each
approved implementation chunk can be signed and run concurrently with chunks
from other initiatives.

## Human-approved intent

See `../INTENT.md` and `../chunks/WS-ENG-006-00-first-planning-intake.md`.

## What changed

- Added a closed, planning-only first-initiative merge classification.
- Added independent generated-state validation and adversarial tests.
- Rebound the existing one-use recovery certificate to this exact root repair.
- Added the complete WS-ENG-006 plan and the reviewed WS-ENG-006-01 contract.
- Updated engineering policy, agent rules, memory documentation, and runbook.

## Why it changed

Previously, repository policy required signed state before an initiative could
create the very planning artifacts needed to become signable. That circular
bootstrap pushed contributors toward manual owner intervention.

## Design chosen

The first merge may contain only a schema-v2 PLAN intent, the canonical
initiative planning files, canonical chunk contracts, and exact review/trust
evidence. It records the initiative stopped with no active chunk. The first
implementation still requires the normal authenticated explicit-start event.
Distinct initiatives remain independently startable and concurrent.

## Alternatives rejected

- Relaxing signed starts was rejected because it weakens traceability.
- Treating CodeRabbit as start authority was rejected because it is an external
  reviewer, not an authenticated repository writer.
- Requiring reviewed-head Git objects forever was rejected because squash and
  rebase heads may be deleted and pruned.

## Scope control

Only the files allowed by the WS-ENG-006-00 chunk contract changed. No backend,
frontend, dependency, coverage-threshold, product lifecycle, or runtime
authorization behavior changed.

## Product Behavior

- [x] No Workstream product behavior changed.

## Acceptance criteria proof

- [x] Closed planning intake — exact path grammar and 94-test adversarial suite.
- [x] Stopped post-merge state — reducer and replay tests.
- [x] Ordinary explicit implementation start remains required — policy and state tests.
- [x] Concurrent distinct initiatives remain supported — per-initiative active-state policy.
- [x] Root repair is exact and consumed — recovery replay/collision tests.

## Tests/checks run

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_agent_gates.py
git diff --check origin/main...HEAD
```

Result: all passed; 94 Agent Gate tests passed.

## Test delta

- Added planning-intake schema, collection, path, check provenance, recovery,
  replay, squash, rebase, pruning, collision, and mutation coverage.
- No tests were removed or skipped.

## CI integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## External review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | Runs after PR publication; supplementary evidence only. |
| GitHub checks | Pending | Runs after PR publication. |

## Reviewer results

Reviewed code SHA: a297588f614820dc8566df3bee1000b8107b2509

Reviewed at: 2026-07-22T06:16:09Z

Reviewer run IDs: eng006_senior_arch_docs, eng006_qa_ci_tests, eng006_security_ops_reuse

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Exact final SHA reviewed. |
| QA/test | PASS AFTER FIXES | None | 94 tests passed. |
| security/auth | PASS AFTER FIXES | None | Admission and recovery boundaries pass. |
| product/ops | PASS | None | Product behavior unchanged. |
| architecture | PASS AFTER FIXES | None | Durable single-path design. |
| CI integrity | PASS AFTER FIXES | None | No gate weakening. |
| docs | PASS AFTER FIXES | None | Policy and runbook consistent. |
| reuse/dedup | PASS | None | Existing machinery reused. |
| test delta | PASS AFTER FIXES | None | Adversarial merge-shape coverage added. |

## Remaining risks

External PR checks have not yet run. The one-use recovery certificate remains
high impact but is exact-target, first-parent-bound, consumed, and replay-inert.

## Follow-up work

After this PR merges and automation reconciles it, dispatch the ordinary signed
start for `WS-ENG-006-01`; do not implement it in this PR.

## Human review focus

- Closed planning-only path grammar.
- Durable first-parent-to-merge proof across merge shapes.
- Exact recovery consumption and absence from signed state.
- Separation between planning admission and implementation authorization.

## Human ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
