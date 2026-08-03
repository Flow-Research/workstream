# WS-DOCS-001-02 Review And PR Trust Bundle

## Intent and scope

Reconcile the remaining current-facing calendar wording, classify preserved
early planning and review material as history, refresh the v0.1 capability
ledger after merged REV/AUTH readiness, and correct the DOCS initiative's own
status. No product code, workflow, CI policy, architecture contract, or other
initiative implementation changes.

## Files and design

- `docs/current_system_data_flow.html` describes the current checker outcome
  without implying that the unimplemented review queue is live.
- `docs/historical_planning.md` indexes every top-level early `review*.md`
  record and preserves those records without rewriting their historical text.
- `docs/roadmap_status.md` records merged REV/AUTH readiness while explicitly
  keeping review lifecycle behavior unavailable and under integration.
- The WS-DOCS-001 status, chunk map, and chunk contract record the bounded
  reconciliation and the merged disposition of chunk 01.

## Deterministic evidence

Passed on the final repaired working tree:

- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_review_contracts.py`
- `python3 scripts/check_markdown_links.py`
- `PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py`
- `git diff --check`

No local `sheets/workstream_roadmap.xlsx` exists in this worktree, so workbook
sheet-count and export-parity checks are not applicable. The roadmap export was
not changed.

## Internal review

- Docs: initial FAIL because the historical index covered only four early
  reviews; repaired by linking every top-level `docs/review*.md`; final PASS.
- Product/operations: initial FAIL because the data-flow page implied a live
  review queue; repaired with exact current checker outcomes and an explicit
  availability boundary; final PASS.
- QA: initial staging/evidence finding; the complete bounded diff and contract
  were staged and the deterministic checks completed; final PASS.
- Senior engineering: PASS, with the availability wording observation resolved
  by the product/operations repair.

## Risks and human review focus

Historical bodies deliberately retain their original calendar language because
rewriting audit evidence would erase context. Review that every such document
is reached through the historical index and that the capability ledger does
not overstate live REV behavior.

## External checks and merge

CodeRabbit's two valid findings were repaired: the checker outcome is now
separate from the task lifecycle state, and the merged REV/AUTH readiness claim
names PRs #242, #248, #255, and #257 as evidence. GitHub CI must pass again on
the repaired exact head. Explicit human merge approval remains required.
