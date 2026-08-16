# WS-CI-004-02 External Review Response

External review sources: CodeRabbit reviews of PR #342 at implementation heads
`aa5b5c242008b087166211fde79b9254606f9b0a` and
`d464529c72e61f93e1f2cb5a25331be83877ba87`.

## Comments addressed

- `PRRT_kwDOSwL_U86Zjhg5`: parse the reviewer matrix canonical-ID column,
  require exact agreement with the configured reviewer registry, and reject
  unknown handoff IDs.
- `PRRT_kwDOSwL_U86Zjhg-`: require every custom reviewer agent contract to
  retain its cross-specialty handoff instruction.
- `PRRT_kwDOSwL_U86ZjhhC`: reject duplicate expectation IDs and duplicate or
  incorrectly sized output sets before per-case validation.
- `PRRT_kwDOSwL_U86Zj4yd`: reject non-string case, reviewer, and finding IDs as
  validation failures instead of allowing unhashable values to raise.
- `PRRT_kwDOSwL_U86Zj4yb`: distinguish private session evidence from durable
  PR evidence and bind the published summary to its evaluated target.
- `REUSE-LOW-001`: make direct single-output validation share the same
  non-object input guard as complete output-set validation; malformed JSON and
  unreadable files now return controlled validation failures.

Each correction has a focused regression test. The complete saved blind output
set still passes the strengthened validator.

## Comments deferred

None.

## Human decisions needed

None beyond normal review and merge ownership.

## Commands rerun

```bash
python3 -m unittest -v scripts.test_reviewer_contracts
python3 scripts/reviewer_contracts.py
python3 scripts/reviewer_contracts.py validate-fixtures
python3 scripts/reviewer_contracts.py validate-output-set \
  --output /tmp/ws-ci-004-02-blind-results.json \
  --receipts /tmp/ws-ci-004-02-blind-receipts.json
cd backend && uv run ruff check ../scripts/reviewer_contracts.py \
  ../scripts/test_reviewer_contracts.py
python3 scripts/review_target.py --base origin/main --head HEAD --format json
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

The private blind-run files contain 45 cases across all nine canonical
reviewers. Every output and receipt names evaluated head
`a2eb98cc382f2c30b003432f6b46aafd7048cc0d`; receipt verdicts are
`PROVISIONAL`; positive/replay cases carry stable finding IDs. The validator
checks every case/reviewer/head/classification/handoff/finding binding against
its matching canonical receipt.

The required post-push evidence summary is published at
<https://github.com/Flow-Research/workstream/pull/342#issuecomment-5304699021>.
That comment records the evaluated head, all 45 classifications, receipt
verdict, finding-ID coverage, and the later clean exact-head reviewer result.
The JSON files remain private session evidence and are not repository truth.

At the last exact-head review barrier, all requested reviewer sessions were
complete and no sub-agent session remained open. A later push invalidates that
statement until the final-head barrier is rerun and the PR evidence comment is
updated.

## Remaining risks

The findings from the second CodeRabbit review and the later internal reuse
review remain open until these fixes are pushed, final-head deterministic and
internal reviews pass, the PR evidence is updated, and CodeRabbit re-reviews
the new head. No claim of zero unresolved risk is made while those steps remain
pending.
