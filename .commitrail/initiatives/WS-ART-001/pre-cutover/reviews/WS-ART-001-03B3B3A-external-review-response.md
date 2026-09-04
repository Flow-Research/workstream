# WS-ART-001-03B3B3A External Review Response

## Comments addressed

- CodeRabbit correctly found that non-canonical root relationship parts such as
  `_rels/foo.rels` could use an incorrect relationship base. Root package
  relationships are now limited to `_rels/.rels`; nested root `_rels/`
  directories are rejected; and relationship target resolution fails closed
  for every relationship-part shape other than `_rels/.rels` or
  `<directory>/_rels/<part>.rels`.
- Focused regressions cover non-canonical root relationship files/directories
  and existing root traversal cases.

## Comments deferred

- CodeRabbit's generic docstring warning is superseded by the repository-owned
  hosted docstring gate, which passed on the reviewed head.

## Human decisions needed

None.

## Commands rerun

- focused OOXML security and coverage suite;
- Ruff;
- dependency, lock, lane, stale-contract, Markdown-link, and diff gates;
- hosted Backend and Agent Gates on the repaired head.

## Remaining risks

The complete hosted rerun and exact-head human approval remain publication
gates. No OOXML adapter or AUTH action is activated by this repair.
