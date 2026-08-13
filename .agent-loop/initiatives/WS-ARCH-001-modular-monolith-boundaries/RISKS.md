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
| Submission cutover precedes visible post-submit checker results | Critical | Require WS-ARCH-001-04A-04F materialization, activation, routing/remediation, repair/audit proof, and REV admission handoff before 02I public reachability |
| Existing legacy `allow_review` is mistaken for canonical readiness | Critical | Require an exact manifest rooted in the admission-backed Submission, verified binding, approved unified generation, final current CheckerRun and routing result |
| REV persistence progress is mistaken for a live review entry gate | High | Keep REV owner-local foundations distinct; no queue admission activation until the canonical upstream manifest is merged |
| Guide compilation and Submission work drift on different policy generations | Critical | Complete the POL-003 unified chain first and bind TASK, ART and CHECKER facts to the same approved generation and hashes |
| Architecture placeholders become oversized feature PRs | High | Replace parents 03/04/05 with explicitly ordered one-owner capability chunks before implementation |
| Retired economic-policy vocabulary becomes a second governing model | Critical | ContributionPolicyVersion is the only frozen award-governing policy; remove retired fields and names through owner clean cuts before public release, with no aliases or fallback |
| Live assignment or review claim loses the one task-governing ContributionPolicyVersion | Critical | Enforce immutable guide -> task -> assignment -> Submission/allow_review -> ReviewLease lineage; missing, cross-project, stale or mismatched facts deny before claim effects, and neither claim performs CON policy lookup |
| Review decision commits without mandatory contribution consequences | Critical | Stable REV schema precedes CON-03C/07; every decision atomically creates reviewer ContributionRecord/awards and accept additionally creates FinalAcceptance plus submitter record/awards |
| Composition root absorbs domain decisions | High | Composition opens the unit of work and wires transaction-bound ports only; TASK command owns Submission sequencing and each target port enforces its own invariants |
| Policy behavior starts before exact AUTH registration | Critical | CP01 registers typed unavailable authority before CP02/CP04 behavior; CP03/CP05 activate only after hidden proof |
| Binding management inherits fulfillment callback authority | Critical | CP01-CP03 exclude delivery/callback identities and permissions entirely |
| CON writes PROJECT or TASK aggregates | Critical | CP06 returns immutable validation facts only; CP07 and CP08 own their respective writes |
| Consolidated v0.1 schema gains fake compatibility debt | High | CP09 performs a clean current-baseline cut and forbids aliases, dual paths, and invented backfills |
