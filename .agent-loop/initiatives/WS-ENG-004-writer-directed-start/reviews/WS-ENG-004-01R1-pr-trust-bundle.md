# WS-ENG-004-01R1 PR Trust Bundle

## Goal

Repair the failed post-#169 loop-memory bootstrap without weakening signed
state, ledger, manifest, renderer, or recovery controls.

## Incident

Loop Memory run `29835344158` authenticated by first applying the new renderer
to existing signed projections. Renderer drift caused valid prior bytes to be
discarded before cryptographic authentication, so recovery received no state.

## Design

- Validate current state schema, complete ledger chain and exact tail, closed
  ordered manifest, regular paths, digests, exact tree, and Ed25519 signature.
- Permit renderer mismatch only inside the rebuild-source authenticator.
- Copy only authenticated `STATE.json` and `MERGE_LOG.jsonl` into a fresh root.
- Regenerate loop view, queue, every initiative projection, and manifest with
  current code, then run strict current-renderer validation.
- Bind recovery to exact PR #169 merge `dda60ed0` followed by this repair chunk;
  consume both exemptions without persisting either.

## Scope

Loop-memory updater/checker code, tests, exact recovery policy, bounded chunk
memory, review evidence, and one merge intent. No workflow, product, dependency,
secret, cancellation, coverage-floor, or generated-branch edit.

## Proof

- 207 focused tests and 89 agent gates pass.
- Updater/checker branch coverage: 90.07/90.18 percent against unchanged 90
  percent floors.
- The real signed automation tip authenticated locally; PR #169 reconciled;
  recovery was consumed; the independent checker passed.
- All nine internal reviewer tracks pass exact SHA `d845fcca` with no blocker.

## External review

Fresh GitHub checks and CodeRabbit are pending after publication. The valid
duplicate-latest-map comment from PR #169 is included in this repair.

## Remaining risk

The repair PR must merge before unrelated main changes so its exact two-merge
certificate remains the expected reconciliation plan. Any mismatch fails closed.

## Human review focus

Verify migration-only renderer tolerance, semantic-only copying, complete fresh
projection generation, strict final validation, and exact recovery identity.

## Human merge ownership

Only the user may approve merging this specific repair PR. Automation must not
merge it.
