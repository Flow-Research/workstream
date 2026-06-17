# Human Review Checklist

## Before reading code

- [ ] Read PR trust bundle.
- [ ] Read chunk contract.
- [ ] Confirm this PR maps to exactly one chunk.
- [ ] Confirm risk class and reviewer set are correct.

## Review tests first

- [ ] New tests match requirements.
- [ ] Modified tests were not weakened.
- [ ] No tests skipped/deleted without explanation.
- [ ] Bug fixes include regression coverage when feasible.

## Review CI integrity

- [ ] No workflow weakening.
- [ ] No lint/typecheck/test script weakening.
- [ ] No coverage threshold lowering.
- [ ] No `|| true`, skipped failures, or ignored paths added suspiciously.

## Review load-bearing paths

- [ ] Auth/permissions preserved.
- [ ] Payment/policy/data boundaries preserved.
- [ ] Architecture boundaries preserved.
- [ ] No speculative abstraction.
- [ ] No hidden coupling.

## Final decision

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] Merge or send back.
