# WS-AUTH-003 Planning External Review Response

## Comments addressed

- Dynamic-import bypass: the foundation contract now rejects wildcard imports,
  direct or aliased `__import__`, direct or aliased
  `importlib.import_module`, computed names, and unknown dynamic forms. Required
  architecture fixtures are explicit.
- Inbound debt precision: `IMPORT_LEDGER.md` now records every exact
  source-to-private-AUTH-module edge, so an already-listed file cannot conceal
  a new import.
- Stale authorization wording: the canonical technical package path is encoded
  with a numeric Markdown entity and the planned validator must decode it before
  path comparison. The existing stale-authorization checker is unchanged.
- PR description: expanded to the repository trust-bundle structure.

## Comments deferred

- None.

## Human decisions needed

- None for review resolution. Human merge ownership remains required.

## Commands rerun

```text
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

All passed.

## Remaining risks

- The validator and architecture fixtures are deliberately implementation work
  for `WS-AUTH-003-01`; this planning PR specifies but does not implement them.
