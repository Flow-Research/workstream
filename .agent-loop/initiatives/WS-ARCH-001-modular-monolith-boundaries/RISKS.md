# Risks: WS-ARCH-001 Modular Monolith Boundaries

| Risk | Severity | Mitigation |
|---|---|---|
| Cosmetic `api` re-exports leak private implementations | Critical | Leak/reachability tests and immutable public types only |
| Import cleanup changes locks, transactions, replay, or denial behavior | Critical | Capability-sized chunks with behavior-preservation and PostgreSQL concurrency proof |
| Generic orchestrator becomes a new shared domain | High | Owning application command coordinates injected public ports; composition root only wires concretes |
| Two boundary initiatives create competing validators | High | General validator consumes/adopts AUTH ledger rather than replacing AUTH-003 |
| Feature delivery adds debt faster than cleanup | High | Exact protected-base edge ledger; no additions and touched-edge reduction required |
| One broad refactor becomes unreviewable | High | One capability and one PR per repair; no bulk moves |
| Migration collisions across active branches | High | Resolve next identifier only after rebasing on current main |
| ORM relationships are mistaken for runtime API authority | Medium | Keep database constraints, but prohibit cross-module model imports in services |
