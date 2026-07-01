# External Review Response: WS-POL-001-02

## Status

External review was received for PR #61 and addressed in reviewed code SHA
`89420d15184d6ff00b13a537d81de94e0703f3af`.

## External Systems

- GitHub Actions before the final external-review fix: passing.
- CodeRabbit before the final external-review fix: passing status with actionable comments.
- Human PR review: pending.
- Post-fix GitHub Actions and CodeRabbit rerun: pending after final branch push.

## CodeRabbit Findings Addressed

| Source | Finding | Response |
|---|---|---|
| `backend/app/main.py` | Validation-error response should be encoded before returning JSON. | Applied `jsonable_encoder()` around the sanitized validation error payload and kept raw input redaction. |
| `backend/app/modules/projects/service.py` | Approval trusted stored `policy_hash` even if `policy_body` changed. | Added approval-time canonical body/hash consistency check and a focused regression test. |
| `docs/spec_chunk_3_project_guide_foundation.md` | Route reuse wording blurred sufficiency-agent reuse with derivation-agent behavior. | Clarified that `run-sufficiency-agent` can reuse an existing sufficiency row, while `derive-submission-artifact-policy` rejects manual sufficiency reports and only reuses agent-derived policies. |
| Internal evidence wording | Tighten “a small number of” phrasing. | Updated evidence wording to “a few default literals.” |

## Validation

```bash
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'sufficiency_agent_reuses_existing_manual_report or submission_artifact_policy_approval_rejects_body_hash_mismatch or project_guide_rejects_non_finite_source_metadata or review_policy_rejects_invalid_decision_names or project_create_validation_errors_are_structured' -q
cd backend && .venv/bin/python -m ruff check app/main.py app/modules/projects/service.py tests/test_projects.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

Result:

```text
Focused tests passed: 5 passed, 174 deselected in 50.32s.
Ruff touched files passed.
Docstring coverage passed: 100.0% (499/499).
Markdown link check passed.
Stale wording check passed.
git diff --check passed.
```

## Notes

Internal reviewer evidence is tracked separately in
`WS-POL-001-02-internal-review-evidence.md`. External review supplements the
internal reviewer evidence; it does not replace it.
