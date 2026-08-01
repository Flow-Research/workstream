# Status: WS-XINT-003 REV-AUTH End-to-End Contract

## Current status

Planning complete after focused internal review. No runtime code or action
availability is changed.

## Baseline

- Planning branch began from `origin/main` at `99dc0b34` after AUTH-12D merged.
- Existing REV actions remain planned/unreleased as product surfaces.
- XINT-002 remains the owner of review artifact materialization/binding and
  human-review submission-artifact activation.

## Main finding

REV-03P and AUTH-12D2 overlap around review/revision policy persistence and
mutation. The first implementation wave must settle one persistence path:
REV-owned semantics with AUTH-owned mutation authorization.

## Next step

Open and review the planning PR. Do not implement `WS-XINT-003-01` until the
planning PR merges and the user explicitly requests that chunk from a refreshed
current-main contract.

Planning complete. Awaiting human approval before implementation.
