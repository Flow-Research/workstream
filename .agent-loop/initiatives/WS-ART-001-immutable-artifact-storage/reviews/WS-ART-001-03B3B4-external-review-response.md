# WS-ART-001-03B3B4 External Review Response

## Comments addressed

- Hosted Agent Gates identified ambiguous human-worker vocabulary in two chunk
  contract lines. Both now say `extraction child`, matching the isolated parser
  process and avoiding confusion with the Workstream contributor role.
- CodeRabbit identified valid Pillow mode normalization for 16-bit
  grayscale-alpha PNG. Decoder agreement now accepts Pillow's `RGBA` mode
  while retaining the independent header-derived `grayscale_alpha` identity,
  with a real 16-bit regression fixture.
- CodeRabbit's `NoReturn`, pytest monkeypatch, architecture-test separation,
  and compound-modifier clarity suggestions were applied as small in-scope
  maintainability improvements.

## Comments deferred

- CodeRabbit's generic docstring warning is not applicable: the repository's
  authoritative hosted Docstring Coverage step passed on the reviewed head.

## Human decisions needed

None.

## Commands rerun

- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_markdown_links.py`
- `git diff --check`
- Focused image, architecture, extraction, and dependency tests with the image
  branch-coverage gate.

## Remaining risks

Hosted Backend must pass again on the repaired head. Agent Gates and the prior
hosted Backend run passed.
