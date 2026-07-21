# WS-ENG-004-01R1 External Review Response

## Incident addressed

- Loop Memory run `29835344158` failed after PR #169 because rebuild
  authentication applied the new initiative renderer before authenticating the
  existing signed manifest. Valid prior-renderer projections were discarded,
  leaving recovery without `STATE.json`.

## CodeRabbit comment addressed

- PR #169 identified duplicate `_latest_by_initiative` computation in authority
  transition validation. The repair reuses the already required global latest
  map without changing either global-active or basis-active failure behavior.

## Deterministic reproduction

The repair authenticated the real signed automation tip `e89e42e5`, rebuilt all
projections in a fresh directory, reconciled PR #169 at `dda60ed0`, consumed the
single-target inventory, and passed the independent generated-state checker.
The repair PR uses an exact two-merge certificate so the hosted rerun can
reconcile both PR #169 and `WS-ENG-004-01R1` without persistent authority.

## Remaining gates

Exact-SHA internal review, fresh GitHub checks, CodeRabbit, and explicit human
approval of the repair PR remain.
