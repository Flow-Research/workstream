# PR Trust Bundle: WS-ENG-007-00R3

## Intent

Restore signed loop-memory reconciliation without allowing mutable post-merge
reruns to block unrelated initiatives or rewrite accepted merge evidence.

## Scope

- Freeze protected `agent-gates` and backend `test` evidence at PR merge time.
- Persist selected-run provenance in signed records.
- Recover exact PRs #187–#189 plus this activation once from signed PR #178.
- Use one atomic reconciliation reducer in merge and explicit-start workflows.

## Reviewed Revision

`fa73182fb271d990bcc8efd827552c26a70aee88`

## CI Integrity

- No test, coverage floor, required reviewer, human merge checkpoint, or signed
  start rule was removed or weakened.
- CodeRabbit remains supplementary external evidence.
- Both workflows fail before signing, publication, or authority application if
  reconciliation or recovery consumption fails.

## Reviewer Result

All nine required internal tracks passed after fixes. No Critical or High
finding remains open.

## Human Review Focus

- Confirm only exact historical PR #189 receives recovery-only evidence.
- Confirm the new activation PR still requires ordinary protected evidence.
- Confirm both workflows invoke the same `reconcile` command before authority or
  publication.
- Confirm the four-entry bridge is exact, consumed, and non-reusable.

## Remaining Risk

An intervening `main` merge invalidates the exact recovery bridge and must fail
closed.
