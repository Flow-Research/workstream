# Workstream PR Trust Bundle

This PR template mirrors `.agent-loop/templates/PR_TRUST_BUNDLE.md`; keep both
in sync when the trust-bundle structure changes.

## Chunk

`<chunk-id or small-change>` - `<title>`

For a chunk PR, confirm its contract contains `## Merge state` with one
`Outcome on merge`, and that the chunk map, initiative status, and current
engineering state already describe the result that will land on `main`.

## Goal

## Intent And Planning Context

For larger or higher-risk work, link the applicable records. For a small
change, state the intent directly here.

- Intent:
- Chunk contract:

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

## Internal Reviewer Results

Allowed result values: `PASS`, `PASS AFTER FIXES`, `PASS WITH LOW RISKS`, or
`N/A - with approved reason`. Any `N/A - with approved reason` row must include
the reason in `Notes`.

Reviewed code SHA:

Reviewed at:

Reviewer run IDs:

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | Pending | | |
| QA/test | Pending | | |
| Security/auth | Pending | | |
| Product/ops | Pending | | |
| Architecture | Pending / N/A - with approved reason | | |
| CI integrity | Pending / N/A - with approved reason | | |
| Docs | Pending / N/A - with approved reason | | |
| Reuse/dedup | Pending / N/A - with approved reason | | |
| Test delta | Pending / N/A - with approved reason | | |

## External Review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | |
| GitHub checks | Pending | |

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

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
