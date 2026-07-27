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
  Reruns use the same exact PR head without changing a gate. GitHub checks,
  rather than committed prose, own transient rerun and merge-readiness state.

## Human decisions needed

None.

## Commands rerun

- Markdown link and stale documentation checks after the CodeRabbit fix.
- GitHub Backend failed-job rerun on the exact PR head.

## Remaining risks

The PR's exact-head Backend and Agent Gates checks must pass before merge; their
live state remains in GitHub and is not duplicated in this durable record.
