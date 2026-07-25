# WS-AUTH-001-11 External Review Response

## Comments addressed

- GitHub Agent Gates run `30169027253` failed the stale-authorization
  documentation scan because new planning prose repeated superseded helper and
  request-claim vocabulary. The wording now states the canonical invariant:
  local grants are the sole product-authority source after each hard cutover.
- No scanner rule, exception, historical-path allowlist, or CI behavior changed.
- CodeRabbit correctly noted that catalogue-only 11A cannot remove route
  authority. `CHUNK_MAP.md` now assigns the hard runtime cutover only to 11B,
  11C1, and 11C2.
- CodeRabbit's evidence-integrity comment is addressed: the bundle now records
  the initial hosted failure, the repaired local passes, twelve changed
  Markdown files, and the fact that the hosted rerun remains required.

## Comments deferred

None.

## Human decisions needed

None. The repair preserves the already reviewed hard-cutover intent and changes
no action, permission, role, route, or resource design.

## Commands rerun

```text
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Remaining risks

Hosted Agent Gates must pass on the repaired exact head. Backend full-suite and
CodeRabbit checks remain independently required.
