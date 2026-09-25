# WS-QUAL-003-14 — Make AUTH cursor and decision-boundary tests discriminating

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: Remove one unreachable cursor-size test and correct
  the authority-mutation test input so its decision mutations reach the intended
  authorization checks.

## Intent

Continue the test-necessity audit with two directly demonstrated defects in
existing AUTH evidence. Remove a test whose input cannot reach its claimed
decoder boundary, and make the existing decision-binding matrix use a valid
reason digest so rejection demonstrates the changed authorization fact.

## Current behavior

- `backend/tests/test_authorization.py::test_authorization_read_cursor_rejects_oversized_decoded_value`
  creates 385 decoded bytes, which encode to 514 unpadded Base64url characters.
  `backend/app/modules/authorization/pagination.py::_decode_base64url` rejects
  any input longer than 512 characters before `decode` reaches its 384-byte
  decoded-value guard. The existing malformed-encoding matrix already verifies
  rejection of a 513-character value. This separate test cannot prove the
  decoded-size branch.
- `test_admin_mutations_reject_decisions_not_bound_to_exact_request` sets the
  request digest to a fixed synthetic value but calls completion with
  `reason="Bounded reason"`. `AdminRoleGrantService.complete_issue` and
  `complete_revoke` reject the mismatched digest before the decision matcher,
  masking the decision mutations in those calls.

## Bounded change

### Allowed

- `backend/tests/test_authorization.py`: remove only the unreachable cursor-size
  test; use `derive_reason_digest("Bounded reason")` for both admin mutation
  request variants in the decision-binding matrix.
- This change record and the WS-QUAL-003 overview link.

### Not allowed

- No production, API, schema, migration, CI, workflow, coverage policy,
  dependency, roadmap capability, or unrelated test changes.
- Do not remove other cursor boundary cases or any decision mutation variant.
- Do not claim that a passing focused test establishes database or route-level
  behavior; this is pure service-input evidence.

## Design and decisions

Keep the production decoded-byte guard unchanged. The current encoded-length
bound already prevents a canonical Base64url input from exceeding that decoded
size, so the impossible-input test adds no distinct proof. Keep the existing
513-character malformed-input case for the public encoded limit.

Correct the matrix input instead of splitting or duplicating it: the reason
digest must match the reason passed to the service, leaving each changed
authorization-decision field as the intended reason for rejection. Keep all 16
issue/revoke mutation variants and their independent denial-consumer checks.

## Acceptance criteria

- [x] The unreachable decoded-size case is removed without changing the
  malformed-input or decoded-value production guards.
- [x] Both decision-matrix request variants bind their digest to the supplied
  reason; all existing decision mutations remain.
- [x] Focused AUTH tests pass, including a test-of-the-test where bypassing the
  decision matcher no longer leaves the matrix green.
- [x] Roadmap review confirms no product capability or exposure claim changes.

## Risk and review routing

- Risk class: L1 — AUTH test evidence only; no runtime authority change.
- Required reviewers: test-delta review only after the candidate is frozen.
- Human review focus: confirm that the deleted test was unreachable and that
  decision mutations no longer pass through reason-digest rejection first.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current suite inventory | `uv run pytest --collect-only -q` with `dev` and `agents` extras | 7,843 tests collected; exit 0 | Collection is not execution. |
| Pre-change targeted tests | Three selected nodes in `test_authorization.py` and `test_artifact_authorization.py` | 18 passed | Establishes the current cases are green, not their necessity. |
| Cursor bound | Source trace: 385 bytes -> 514 Base64url characters; owner rejects over 512 first | Confirmed unreachable | The inner decoded-size guard remains deliberately unchanged. |
| Changed AUTH cases | `uv run pytest -q tests/test_authorization.py::test_authorization_read_cursor_rejects_malformed_encoding tests/test_authorization.py::test_admin_mutations_reject_decisions_not_bound_to_exact_request` | 21 passed | Focused pure/service proof only. |
| Decision test-of-test | In-process mutation: replace each admin decision matcher with unconditional allow, then run its changed-action case | Both issue and revoke cases fail at forbidden repository access instead of passing | Controlled mutation, not a production-runtime exploit test. |
| Final suite collection | `uv run pytest --collect-only -q` with `dev` and `agents` extras | 7,842 tests collected; exit 0 | One unreachable collected case removed; no test execution claimed. |

No roadmap update is needed: this change alters only the quality of existing
AUTH test evidence and does not change a product capability, public exposure,
completed work, remaining product scope, or dependency.

## Review findings

Focused test-delta review: the 513-character malformed cursor cases remain; the
unreachable separate decoded-size test alone is removed. All 16 admin decision
mutations remain, now with valid reason digests. Unconditional-allow mutations
of each operation's matcher are rejected before any repository operation can
pass as an expected authorization denial.

## Reconciliation

- Current-source reconciliation: based on `main` at `da39ed4c350847b9cc454e6da1f2200f9b735ccf`; the prior local audit branch remains preserved separately and was not merged or rebased.
- Next usable boundary: continue the module-by-module test-necessity audit after this bounded AUTH correction.
- Remaining risks: the broader AUTH monolith and other test modules remain unaudited in this change.
