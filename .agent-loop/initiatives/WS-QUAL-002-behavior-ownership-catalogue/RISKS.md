# Risks: WS-QUAL-002 Behavior Ownership Catalogue

| Risk | Impact | Mitigation |
|---|---|---|
| Inferred execution is mistaken for assertion ownership | Vacuous catalogue | Keep candidates non-authoritative; engineering review and future mutation evidence confirm ownership |
| Retired callable-wide behavior returns under a new name | Contributor blocking and false survivors | Require exact changed-line selection and negative proof that unchanged executable lines never enter mutation |
| Broad test nodes make mutation slow | Contributor latency | Calibrate contexts and require bounded owning nodes/groups |
| Protected ownership is narrowed by PR data | Gate bypass | Protected-base merge semantics and explicit additive remap validation |
| Catalogue becomes stale after renames | False failures or escapes | Exact AST, target, collected-node, rename, and deletion checks |
| 168-module population is unreviewable | Review failure | Four subsystem data chunks with focused reviewers |
| Context coverage is too slow or produces oversized artifacts | Contributor latency | Keep it local/manual; accept only at no more than two minutes and 10 MiB per artifact |
| Structural modules hide executable behavior | Gate bypass | Machine-checkable AST criteria, a required reviewer rationale, and negative tests |
| Concurrent population overlaps or omits targets | Stale review and merge conflicts | Commit one exact target-to-group partition before population; make population PRs data-only |
