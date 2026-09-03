# WS-ENG-009-02 — Live Workstream Commitrail Stress Test

## Goal

Use one necessary bounded Workstream change to test Commitrail end to end and
record any method defects demonstrated by that use.

## Allowed files

- The one Commitrail change record and applicable initiative index/overview
- The product and test files explicitly selected in the future change record
- Related current documentation

## Not allowed

- `.agent-loop` restoration or compatibility
- Unrelated product work
- New process records not justified by observed risk
- Reviewer fanout unrelated to the change's impact cone

## Acceptance criteria

- A contributor identifies the work from current repository entry points.
- The change uses one combined record unless multi-PR scope is independently
  justified.
- Scope, tests, review, exact candidate, PR, rebase, and human merge work
  without stale state repair or a second reconciliation PR.
- Measured friction and escaped ambiguity are recorded.
- No Commitrail method implementation is changed in the product PR. A proven
  defect may become a separate bounded correction after this evaluation.

## Risk class

To be assigned from the selected real change. Any later Commitrail method
correction is a separate L1 process change.

## Verification commands

Defined in the selected change record after the human selects the product
boundary. Repository-standard CI remains blocking.

## Required reviewers

Impact-routed from the real change. Architecture, CI, docs, security, payment,
or product-operations review runs only where that surface is affected.

## Human review focus

- Did Commitrail make the change easier to understand and govern?
- Did it omit a control that would have caught a real risk?
- Did it require any file, check, or reviewer that added no decision value?

## Merge state

- Outcome on merge: `planned`

This chunk cannot start until `WS-ENG-009-01` is merged and the human selects
the real Workstream boundary.
