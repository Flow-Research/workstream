# WS-DOCS-001-04 External Review Response

## Comments Addressed

1. CodeRabbit reported that README used two display names for the canonical
   roadmap. The remaining navigation label now uses `v0.1 Roadmap And
   Capability Status`.
2. The same stale display name was present in the current contributor entry
   path. `CONTRIBUTING.md` now uses the canonical label and explicitly includes
   hidden capabilities in the roadmap description.

## Comments Deferred

None. Historical planning documents retain their original link prose because
they are historical evidence rather than current navigation.

## Human Decisions Needed

None. The correction changes link labels only and does not change product,
architecture, authorization, or release semantics.

## Commands Rerun

```text
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main --head-ref HEAD
python3 scripts/check_active_state_projections.py --base-ref origin/main --head-ref HEAD
```

## Remaining Risks

None identified. Runtime, schema, migrations, dependencies, CI, tests, and
capability availability are unchanged.
