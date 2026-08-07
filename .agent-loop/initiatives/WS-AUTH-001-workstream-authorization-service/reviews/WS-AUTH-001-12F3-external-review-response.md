# External Review Response: WS-AUTH-001-12F3

## Comments addressed

- CodeRabbit reported no actionable review comments.
- Hosted Backend exposed stale OpenAPI inventory expectations after removal of
  the public derivation route; the exact route and protected-route inventories
  now describe the intended hidden fixed-service surface.
- Hosted Backend exposed stale active-action audit parity; the newly active
  fixed-service derivation action is now part of the exact allowed-action set.
- Hosted Backend exposed historical migration selectors that lost the derive
  action when its catalogue owner moved from `AUTH_12F` to `AUTH_12F3`; the
  frozen project-mutation owner set now includes the successor owner so all
  eighteen migration-0041 action pairs and downgrade exclusions remain exact.

## Comments deferred

None.

## Human decisions needed

None before review. Human approval remains required to merge PR #295.

## Commands rerun

- Ruff on the three corrected test modules.
- Focused OpenAPI and action-aware audit parity tests.
- Four focused PostgreSQL migration regressions covering migration-0041 action
  parity, downgrade custody, authorization-action evidence, and bootstrap
  authority passed.
- Full repository coverage remains assigned to exact-head GitHub Actions.

## Remaining risks

None identified from the external findings. The corrections change only exact
contract expectations; they do not weaken authorization or CI.
