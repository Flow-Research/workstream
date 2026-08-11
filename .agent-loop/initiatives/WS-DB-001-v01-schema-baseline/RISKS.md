# Risks

| Risk | Severity | Control |
|---|---|---|
| Trigger/function/partial-index omitted from metadata-only baseline | Critical | Compare normalized PostgreSQL catalog manifests from old head and new baseline. |
| Authorization catalogue or service seed row omitted | Critical | Exact database/runtime parity tests for permissions, actions, owners, availability, and identities. |
| Existing database is accidentally treated as upgradeable | High | Clean-cut documentation and a single root revision; no bridge/stamp logic. |
| Dump contains owners, credentials, environment names, or nondeterministic data | High | Generate a normalized allowlisted schema/reference manifest and scan committed files. |
| Baseline becomes an unreviewable opaque blob | High | Separate deterministic schema SQL/reference SQL, stable ordering, manifest tests, and focused reviewers. |
| Historical tests are deleted without replacement | Critical | Test-delta review maps each retained current invariant to baseline parity or database-enforcement proof. |
| Full-suite speed improves by skipping coverage | Critical | Preserve exact node custody and all coverage floors; only obsolete intermediate-state tests are removed. |
| Concurrent work adds migration 0064 during reset | High | Rebase before generation and reject any head other than the recorded source head. |
| Baseline mutates an old or non-empty database | Critical | Preflight the public schema before DDL; test old-head, old-stamped, and unversioned non-empty refusal. |
| Root downgrade becomes a destructive escape hatch | Critical | `downgrade()` raises unconditionally before mutation; test schema/data preservation. |
| Manifest omits an object class on both sides | Critical | Fix the extractor's closed object-class inventory and test each supported class with a sentinel fixture. |
