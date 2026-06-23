# External Review Response: WS-POL-001-01

## PR

https://github.com/Flow-Research/workstream/pull/26

## Chunk

`WS-POL-001-01`

## Source

CodeRabbit, GitHub checks, and human PR review.

## Summary

External review feedback is tracked separately from internal sub-agent evidence.
Internal sub-agent results live in
`WS-POL-001-01-internal-review-evidence.md`.

## External Findings

| Source | Finding | Severity | Status | Response |
|---|---|---:|---:|---|
| CodeRabbit | `WS-POL-001-03` acceptance criteria repeated no-side-effect wording. | Low | Fixed | Consolidated the no-row, no-version, no-transition, and no-durable-checker-run guarantee without weakening it. |
| Human review | Project owners must not author or approve Workstream internal `SubmissionArtifactPolicy`; Workstream derives it from open-ended project material and `admin` or `project_manager` approves the internal bundle. | High | Fixed | Updated planning artifacts, ADRs, glossary, architecture docs, specs, templates, operating manual, data flow, and first user flows. |
| Human review | Project-guide material is open-ended, not a fixed checklist; Workstream must run sufficiency and derivation agents internally. | High | Fixed | Added `ProjectGuideSufficiencyAgent`, `GuideSufficiencyReport`, and `SubmissionArtifactPolicyDerivationAgent` to the plan, ADR, data model, lifecycle, templates, and chunk map. |
| Human review | `PreSubmitCheckerPolicy` must be persisted and locked to the guide version, not derived on read. | High | Fixed | Updated plan, ADRs, data model, lifecycle, checker flow, and chunk contracts to require persisted snapshot/hash and locked effective policy hash. |
| Human review | Pre-submit failures should not use review decisions and should show pass/fail/warning details like the Snorkel-style static checker experience. | High | Fixed | Standardized `pre_submission_checker_failed` with structured pass/fail/warning details and explicit exclusion of `accept`, `needs_revision`, and `reject`. |
| Human review | Current planning PR must be mergeable before implementation starts. | High | Fixed | Updated status, chunk map, chunk contract, proof obligations, and review evidence while keeping backend implementation inactive. |
| CodeRabbit | ADR 0011 described pre-submit/review-decision separation but did not state how implementation must prove enforcement. | Major | Fixed | Added an implementation enforcement contract to ADR 0011. It explicitly says this PR is planning-only and lists the API, UI/demo, persistence, database, and chunk-level proof required before implementation chunks can close. |
| CodeRabbit | `docs/architecture_checker_framework.md` made `pre_submission_checker_failed` read like the response type instead of the failure condition represented by a failed pre-submit response. | Minor | Fixed | Reworded the checker framework to require `PreSubmitCheckResponse(status="failed", eligible_to_submit=false, results=[...])` for blocking failures, with `pre_submission_checker_failed` described as the user-facing failure condition rather than a response field. |

## Commands To Re-Run After Push

```bash
gh pr view 26 --json number,title,state,isDraft,url,reviewDecision,reviews,comments,statusCheckRollup
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

## Final External Review State

```text
latest local agent gate result: REVIEW_REQUIRED, with internal review evidence supplied
latest local evidence gate: pass after evidence refresh
latest local loop memory, Markdown links, stale wording, and diff checks: pass
GitHub checks and CodeRabbit must be re-read after every push before merge
```
