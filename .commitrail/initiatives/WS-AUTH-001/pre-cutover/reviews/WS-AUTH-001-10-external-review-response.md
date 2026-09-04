# WS-AUTH-001-10 External Review Response

PR: `#168`

Pre-repair published head: `e0af0a6dddb5ede4707d309d2894409344733446`

## Comments addressed

- GitHub preflight run `29825312611` rejected the internal evidence because it
  used `Reviewed planning SHA` instead of the gate's canonical provenance label
  `Reviewed code SHA`. The evidence now uses the exact required label.
- Agent Gates run `29825436222` found branch-local current-state prose in the
  authored AUTH `STATUS.md`. That file is restored to trusted-main state;
  signed automation, not a PR branch, owns live active/review projection.
- The Backend aggregate `test` job failed only because preflight failed and its
  shards/API E2E prerequisites were skipped. No runtime test executed and no
  backend defect was reported.
- CodeRabbit posted five valid contract findings. The parent now explicitly
  allows `.agent-loop/REVIEW_LOG.md`; the grant `version` is persisted with the
  exact active-1/revoked-2 invariant; 10B/10C state that their 10A registrations
  remain planned until the owning child activates them with routes; the
  canonical issue operation includes idempotency, AuthorityControl/PREP locks,
  advisory absence serialization, and one route commit; and every endpoint
  example uses `/api/v1`.

## Comments deferred

None.

## Human decisions needed

None.

## Commands rerun

```bash
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

Agent Gate regression result: 88 passed. The evidence check intentionally
required exact-SHA repair review and an evidence-only descendant; internal
review passed repair SHA `1623e5b2dd85cc65df92af89989fda2ce7881bd0`, and the
initial evidence-only descendant bound that SHA.

All required internal tracks subsequently passed the five-finding CodeRabbit
repair at exact SHA `6a89dd5018d28be149dc6e77f1466a0b3c707296`; the final
PREP wording was repaired once more before that pass so final authorization
occurs only through `consume()` after canonical feature facts are locked.

## Remaining risks

Fresh GitHub checks, CodeRabbit re-review, and human review remain. No runtime,
migration, CI, test, or coverage behavior was changed by these documentation
repairs.
