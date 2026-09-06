# Workstream PR Trust Bundle

Use this summary with the smallest applicable Commitrail record. Do not copy
transient check or approval state into durable repository files.
Link durable design/scope sections rather than duplicating them. Omit empty
optional headings; report unavailable evidence honestly until ready.

## Change

`<change-id or small-change>` - `<title>`

## Goal

## Intent And Planning Context

For larger or higher-risk work, link the applicable records. For a small
change, state the intent directly here.

- Intent:
- Commitrail record or PR-only reason:

## What Changed

## Why It Changed

## Design Chosen

## Alternatives Rejected

-

## Scope Control

### Allowed Files Changed

-

### Files Outside Stated Scope

- None

## Product Behavior

- [ ] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here:

## Evidence

### Commands Run

```bash

```

### Result Summary

```text

```

## Acceptance Criteria Proof

- [ ]

## Test Delta

### Tests Added

-

### Tests Modified

-

### Tests Removed Or Skipped

- None

## Impact-Routed Reviewer Results

List only reviewers required by the affected risks. Do not add fixed ceremonial
rows. Use the receipt vocabulary: `PASS`, `PASS AFTER FIXES`,
`PASS WITH LOW RISKS`, `BLOCKED`, `PROVISIONAL`, or
`N/A - with approved reason`. Pending or unavailable proof is not a passing
readiness claim. Mark old affected results historical after a push.

Reviewed code SHA:

Reviewed at:

Reviewer run IDs:

| Reviewer | Result | Blocking findings | Proof boundary and uncertainty |
|---|---:|---|---|
| `<affected specialty>` | `<result>` | `<none or IDs>` | `<summary>` |

## External Review

Summarize material external findings and their disposition. Read GitHub for
current check, conversation, approval, and merge state.

## CI And Gate Integrity

- [ ] No workflow weakening.
- [ ] No lint/test/docstring gate weakening.
- [ ] No coverage threshold weakening.
- [ ] No package script weakening.
- [ ] No unpinned new GitHub Action.
- [ ] Checkout credential persistence disabled where checkout is used.

## Remaining Risks

## Follow-Up Work

## Human Review Focus

Please inspect:

-

## Human Merge Ownership

The human completes the acceptance/merge checks; agents must not tick them on
the human's behalf or infer approval from a passing CI status.

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
