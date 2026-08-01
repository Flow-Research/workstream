# Status: WS-XINT-003 REV-AUTH End-to-End Contract

## Current status

WS-XINT-003-01 is merged. Current-main reconciliation split policy work into
02A immutable persistence adoption and 02B prepared mutation activation. No
runtime code or action availability is changed by this planning refresh.

## Baseline

- Planning branch began from `origin/main` at `99dc0b34` after AUTH-12D merged.
- This refresh is reconciled against current `origin/main` at `ad8da7e5`, which
  includes merged PRs #236 and #237 and uses migration head 0045.
- Existing REV actions remain planned/unreleased as product surfaces.
- XINT-002 remains the owner of review artifact materialization/binding and
  human-review submission-artifact activation.

## Main finding

REV-03P and AUTH-12D2 overlap around review/revision policy persistence and
mutation. The first implementation wave must settle one persistence path:
REV-owned semantics with AUTH-owned mutation authorization.

## Current reconciliation

- `ACTION_CUSTODY.md` is the canonical action/principal/resource/wave table.
- REV-03P and AUTH-12D2 name one future append-only policy writer path.
- Runtime owner XINT-002-07 is split into planned sub-wave 07A, the sole
  reviewer-finding packet/evidence-binding availability transition, and 07B,
  an evaluator-only response-slot extension that cannot change availability.
- All registered review actions remain planned; four lifecycle/recovery actions
  remain missing until 08R; no service identity is provisioned by chunk 01.

## Next step

Review and merge this contract refresh, then implement only WS-XINT-003-02A.
Do not begin 02B automatically and do not resume independent REV-03P work.
