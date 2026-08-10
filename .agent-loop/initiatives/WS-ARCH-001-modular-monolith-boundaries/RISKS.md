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
| TASK becomes a facade over PROJECT/CHECKER internals | Critical | Separate immutable PROJECT locked-policy and CHECKER effective-plan capabilities before ART preparation activation |
| AUTH preparation activates over a partly private path | Critical | Keep action unavailable through hidden public-capability and transaction work 02A-02F; activate only in 02G after exact manifests and denial proof |
| Binding authority activates before atomic TASK/ART composition exists | Critical | Merge hidden 02F transaction proof and 02G preparation activation before 02H binding/consumption availability; public route remains legacy until deferred 02I clean cut |
| Legacy and admission-backed Submission paths coexist | Critical | One 02I cutover removes caller package identity, standalone precheck, internal guard, aliases and fallbacks while enabling the admission-only command |
| Initial-only cutover strands `needs_revision` contributors | Critical | Defer 02I until checker-remediation and reviewer-requested revision contexts consume the same admission-backed path with exact predecessor/obligation lineage |
| Submission cutover precedes visible post-submit checker results | Critical | Require ART-06A/06B, XINT-06B replacements, repair/audit proof, and REV admission handoff before 02I public reachability |
| Composition root absorbs domain decisions | High | Composition opens the unit of work and wires transaction-bound ports only; TASK command owns Submission sequencing and each target port enforces its own invariants |
