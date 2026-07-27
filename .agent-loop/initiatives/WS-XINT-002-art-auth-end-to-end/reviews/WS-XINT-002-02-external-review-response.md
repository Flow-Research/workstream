# WS-XINT-002-02 External Review Response

Date: 2026-07-27

## Comments addressed

- CodeRabbit correctly observed that the exhaustive
  `PreparedBundleMaterializationRequest` prose omitted its task and assignment
  selectors. The spec now names both fields.

## Comments deferred

- CodeRabbit's generic docstring-coverage warning is not actionable: the exact
  hosted repository Docstring Coverage step passed before the Backend job
  reached semantic tests. No coverage threshold or unrelated docstring was
  changed.

## GitHub checks

- Agent Gates: passed.
- Backend first run: one pre-existing PostgreSQL lock-observation test timed out
  under four-lane load after the other 1,596 shared-foundation tests passed.
  The evidence validator failed closed and interrupted the remaining lanes.
  The same exact-head failed job was rerun without changing a gate.

## Human decisions needed

None.

## Commands rerun

- Markdown link and stale documentation checks after the CodeRabbit fix.
- GitHub Backend failed-job rerun on the exact PR head.

## Remaining risks

The hosted Backend rerun must pass before merge.
