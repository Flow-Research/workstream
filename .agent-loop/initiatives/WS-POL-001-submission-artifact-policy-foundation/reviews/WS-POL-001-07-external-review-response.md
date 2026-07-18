# External Review Response: WS-POL-001-07

## Source

PR #68 CodeRabbit review on 2026-07-05.

## Comments Addressed

1. `docs/spec_chunk_8_submission_artifact_policy_checkers.md`
   - Finding: `check_required_files` wording overstated runtime inputs by
     naming both `SubmissionArtifactPolicy` and
     `EffectiveProjectSubmissionArtifactPolicy`.
   - Resolution: Updated the spec to state that the checker derives required
     artifact paths from `context.effective_policy` and compares those paths to
     `submission.artifact_hash_manifest[*].artifact`.

2. `docs/template_task.md`
   - Finding: The task template used a stamped `submission artifact policy
     version` label that does not match the backend locked-context fields.
   - Resolution: Replaced that label with the backend-aligned stamped context:
     guide source snapshot id/hash, effective project submission artifact policy
     id/hash, project pre-submit checker policy id, and project pre-submit
     checker bundle hash.

## Comments Deferred

None.

## Human Decisions Needed

None.

## Commands Rerun

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Results:

- stale wording scan: passed
- Markdown link check: passed for 14 changed Markdown files
- diff whitespace check: passed

Evidence refresh commands rerun after the docs-delta review:

```bash
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
```

Results:

- internal review evidence gate: passed
- loop memory state check: passed

## Remaining Risks

None known. The comments were documentation consistency fixes and did not
change runtime code.
