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
| Policy behavior starts before exact AUTH registration | Critical | CP01A and CP01B register their separate typed unavailable authority before CP02/CP04 behavior; CP03B/CP05 activate only after their hidden proof and exact prerequisites |
| Binding management inherits retirement, fulfillment, callback, or delivery authority | Critical | CP01A through CP03 exclude retirement actions plus fulfillment, callback, and delivery action IDs, permissions, identities, routes, evaluators, and service-matrix rows entirely |
| CON writes PROJECT or TASK aggregates | Critical | CP06 returns immutable validation facts only; CP07 and CP08 own their respective writes |
| Consolidated v0.1 schema gains fake compatibility debt | High | CP09 performs a clean current-baseline cut and forbids aliases, dual paths, and invented backfills |
| Legacy debt becomes a blanket blocker for v0.1 delivery | High | Block new debt and require directly touched debt to shrink; never require unrelated frozen debt in a bounded feature PR |
| Debt repayment expands a feature beyond a reviewable safety boundary | High | Record exact stranded debt, prove no growth, and create a later owner-sized closure contract rather than mixing product boundaries |
| Mechanical quotas reward noisy or cosmetic cleanup | Medium | Use exact edge/finding deltas and behavior ownership; prohibit arbitrary per-PR percentages and cosmetic test splitting |
| Overlapping ledgers are added together and misstate debt | Medium | Report general, AUTH, structural, and behavior-ownership measurements separately under their existing owners |
| Adapter-binding resume erases suspension attribution | Critical | CP02 appends one immutable CON lifecycle event per version in the same transaction; CP03B later stages AUTH decision evidence atomically beside it |
| Unrelated internal service is bound as a compensation adapter | Critical | CP02 requires an injected exact ACTORS eligibility capability; generic service kind and existing ART/REV identities fail closed; CP03A installs the exact target identity/owner rule before CP03B activation |
| CP02 invents a second authorization protocol or imports AUTH internals | Critical | CON defines only a domain-facing opaque prepare/consume/close port; production denies until CP03B adapts the existing AUTH PREP implementation |
