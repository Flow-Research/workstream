# WS-AUTH-001-08 External Review Response

Reviewed code SHA: `a284a718e68f08e072cb965cc5834bcc7ab45ee9`
Reviewed at: `2026-07-16T07:43:50Z`

## GitHub Backend

Backend run `29478021300` failed because a historical canonical-actor migration
test expected the former `0021` head after a transactional downgrade refusal.
The failed assertion prevented state restoration and caused seven later
migration failures plus 342 setup errors. Repair `cd46420` captures the actual
pre-command revision and proves every guarded failure leaves it unchanged.

The full isolated Alembic suite passed all 17 tests. Replacement Backend run
`29479547151` passed in 16 minutes 19 seconds, including the repository-wide 78
percent coverage floor and later real-API checks.

## CodeRabbit Findings

| Finding | Disposition | Evidence |
|---|---|---|
| Couple bootstrap grant and authority control at transaction commit | Fixed | Deferred constraint triggers on both tables reject orphan grants and mismatched control references while allowing the valid paired transaction. |
| Align AUTH-08 evidence adoption and downgrade predicates | Fixed | One `AUTH_08_EVIDENCE_EVENTS` tuple drives both checks; bootstrap and both denial events are tested before `0022` adoption. |
| Use the authorizing grant as mutation evidence provenance | Fixed | Admin issue/revoke fixtures receive a distinct authorizer grant and assert it differs from the mutated resource. |
| Synchronize action counts in the operations runbook | Fixed | The runbook now states 57 actions, nine active, and 48 planned. |

All four repairs are in `a284a71`. Two direct regression tests and the complete
17-test isolated Alembic suite pass. Exact-head senior/CI/docs/reuse,
QA/test-delta/product, and security/architecture review pass with no remaining
finding.

## CodeRabbit Pre-Merge Warnings

- The PR description warning was valid; the PR body is aligned to the
  repository trust-bundle template as part of this response.
- The reported 42.25 percent docstring warning does not match the enforced
  repository gate. `docstr-coverage --config .docstr.yaml` passes at 92.5
  percent, and GitHub Backend's Docstring Coverage step passes. No threshold,
  exclusion, or docstring gate was changed.

## Remaining Gate

The final pushed head still requires replacement GitHub checks, CodeRabbit, and
explicit human merge approval. This response does not authorize merge or start
`WS-AUTH-001-09`.
