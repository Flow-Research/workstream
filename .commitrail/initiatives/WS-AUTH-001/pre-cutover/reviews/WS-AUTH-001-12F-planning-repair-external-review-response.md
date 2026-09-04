# WS-AUTH-001-12F Planning Repair External Review Response

## Comments addressed

- Defined one mutable replay reservation row, its sole
  `pending -> committed` transition, the separate append-only authorization
  decision stream, human/service uniqueness constraints, operation-UUID lookup,
  and concurrent exact-call convergence.
- Changed the 12G prerequisite to require merged 12F4 explicitly.
- Named the full 12E/12F2/12F3/12F4/12G product/provenance chain before 12B2.
- Clarified that the public derive endpoint remains current legacy behavior
  until 12F3 merges; service-only derivation begins at that cutover.
- Authorized only the exact 12F3 technical path scanner exemption in the parent
  contract; narrative wording and every other path/rule remain checked.
- Required one total shared-row lock order across 12F3, 12F4, 12G, and every
  overlapping mutation path.

## Comments deferred

None.

## Human decisions needed

None beyond the repository-required human review and merge of PR #283.

## Commands rerun

```text
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Exact correction-head Agent Gates and the full hosted Backend matrix are
required again after push.

## Remaining risks

The PR activates nothing. Runtime risk remains gated behind separately started,
reviewed, tested, and merged 12F1 through 12F4 implementation chunks.
