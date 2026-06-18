# PR Trust Bundle

Canonical source for trust-bundle structure. Keep `.github/pull_request_template.md`
in sync with this template.

## Chunk

`<CHUNK_ID>` — `<TITLE>`

## Goal

What this PR is meant to accomplish.

## Human-approved intent

Link to initiative/chunk contract.

## What changed

Short summary.

## Why it changed

Intent and rationale.

## Design chosen

Explain the design in human-readable terms.

## Alternatives rejected

- Alternative A: rejected because...
- Alternative B: rejected because...

## Scope control

### Allowed files changed

- ...

### Files outside scope

- None / list with reason and approval.

## Product Behavior

- [ ] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here:

## Acceptance criteria proof

- [ ] Criterion 1 — evidence
- [ ] Criterion 2 — evidence
- [ ] Criterion 3 — evidence

## Tests/checks run

```bash
<commands>
```

Result summary:

```text
<output summary>
```

## Test delta

### Tests added

- ...

### Tests modified

- ...

### Tests removed/skipped

- None / explain.

## CI integrity

- [ ] Coverage threshold unchanged
- [ ] Lint unchanged
- [ ] Typecheck unchanged
- [ ] No workflow weakening
- [ ] No package script weakening
- [ ] No unpinned new GitHub Action
- [ ] Checkout credential persistence disabled where checkout is used

## External review

External review response file:

- `.agent-loop/initiatives/<initiative>/reviews/<chunk-id>-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | |
| GitHub checks | Pending | |

## Reviewer results

Allowed result values: `PASS`, `PASS AFTER FIXES`, `PASS WITH LOW RISKS`, or
`N/A - with approved reason`. Any `N/A - with approved reason` row must include
the reason in `Notes`.

Reviewed code SHA:

Reviewed at:

Reviewer run IDs:

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | Pending | | |
| QA/test | Pending | | |
| security/auth | Pending | | |
| product/ops | Pending | | |
| architecture | Pending / N/A - with approved reason | | |
| CI integrity | Pending / N/A - with approved reason | | |
| docs | Pending / N/A - with approved reason | | |
| reuse/dedup | Pending / N/A - with approved reason | | |
| test delta | Pending / N/A - with approved reason | | |

## Remaining risks

Summarize any remaining risks and their accepted owner.

## Follow-up work

What should happen in later chunks.

## Human review focus

Please inspect:

- ...

## Human ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
