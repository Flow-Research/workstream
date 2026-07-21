# Risks: Parallel Initiative Execution

| Risk | Control |
|---|---|
| Same-initiative ownership ambiguity | Keep planning/implementation mutually exclusive per initiative in all three validators. |
| Updater/checker drift | Change and test application, replay validation, and independent checking together. |
| Cross-initiative file conflicts | Separate worktrees; exact-main rebase, CI, internal review, and Git merge conflict handling. |
| Semantic conflicts without textual overlap | Architecture/product reviewers compare all active work before merge. |
| Contract or scope drifts after rebase | Immutable selected contract remains authority; internal review rejects drift and rebase never reauthorizes scope. |
| Automation publication race | Existing shared concurrency group and prior-tip binding; inspect then fresh dispatch. |
| Bootstrap without signed start | Exact one-target, one-use recovery bound to WS-ENG-005-01 and consumed before publication. |
| Misleading global tail state | Queue and initiative projections remain canonical views of all active work. |
| Unsafe rollback after parallel history | Use only forward-compatible repair; never restore the old global replay rule over signed parallel transitions. |
| Excess resource usage | Operators choose starts; no automatic fanout or arbitrary daemon scheduling. |
