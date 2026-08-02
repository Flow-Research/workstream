# WS-DOCS-001-01 External Review Response

## Comments Addressed

1. Aligned the decision record with the capability ledger's exact
   `Implemented`, `In progress`, `Planned`, and `Historical` labels.
2. Removed the historical checker trial's claim that it proves current backend
   behavior and routed current claims to the capability ledger and merged
   evidence.
3. Named the Workstream product lifecycle explicitly in the backend component
   diagram text so it cannot be confused with the engineering loop.
4. Routed readers of the historical planning index through `CONTRIBUTING.md`.
5. Clarified that v0.1 preserves contribution evidence for a future reputation
   projection; runtime reputation projection remains deferred.
6. Reworded the residual historical-document risk as mitigation rather than an
   absolute guarantee that archive notices prevent misuse.

## Comments Deferred

None.

## Human Decisions Needed

None.

## Commands Rerun

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `git diff --check`

## Remaining Risks

Historical checker records intentionally retain their original scenario and
result vocabulary. Their archive notice and current-evidence link reduce the
risk that they are used as current implementation authority.
