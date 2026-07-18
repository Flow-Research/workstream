# External Review Response: WS-POL-001-03

## Status

CodeRabbit and GitHub Actions passed on PR #63.

## Source

- CodeRabbit: pass
- GitHub Actions: pass
- Human PR review: completed before merge

## Notes

External review findings must stay separate from internal sub-agent evidence.
This file tracks CodeRabbit, GitHub Actions, and human PR-review feedback after
the PR exists.

## Backend CI Failure

Failing check:

- Backend `test`

Root cause:

- `backend/scripts/week1_api_e2e.py` submitted a packet that predated
  `WS-POL-001-03`.
- The locked project `PreSubmitCheckerPolicy` correctly returned
  `pre_submission_checker_failed` for missing required evidence token and
  required attestation terms.

Repair:

- Added `required_evidence_key = "checker_log"` to the E2E evidence metadata.
- Added exact platform/project attestation terms to the E2E worker attestation.
- Added the script to the chunk contract as CI drill alignment scope.

Local verification:

```text
ruff check scripts/week1_api_e2e.py passed.
Week 1 real API E2E passed locally.
GitHub Actions backend test passed after repair.
```
