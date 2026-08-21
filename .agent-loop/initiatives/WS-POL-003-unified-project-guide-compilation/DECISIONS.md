# Decisions: WS-POL-003 - Unified Project Guide Compilation

1. One logical structured model attempt is used per immutable source snapshot,
   catalogue snapshot, and setup generation. A durable attempt row and provider
   idempotency key serialize dispatch. The current provider boundary cannot
   prove retrieval or same-key replay after an unknown outcome, so recovery
   remains `provider_outcome_unresolved` and never redispatches. A future
   provider capability may retrieve or reuse the accepted result only after it
   proves exact same-key observation. Invalid or unsafe output consumes the
   attempt and blocks that generation.
2. `ProjectGuideCompilation` is immutable provenance/proposal evidence, not a
   canonical policy replacement.
3. Existing policy objects and Project Manager approval gates remain separate.
4. Agent-derived projections are immutable. Corrections create a new
   generation. A manual replacement, if retained, has separate provenance and
   invalidates every dependent unified proposal.
5. The fixed `workstream.project.setup` service performs compilation and
   service-owned projection mutations using fresh action-specific PREP. Human
   authority only requests/recoveries, acknowledges, corrects through an
   approved replacement path, and approves.
6. Platform coverage and selectable project capabilities remain separate
   projections even when supplied by the same phase owner.
7. ART-04B1 owns the complete pre-submit catalogue and effective-plan compiler,
   including mandatory platform entries and its closed selectable project-rule
   namespace. CHECKER/POL owns durable post-submit capability truth. WS-POL-003
   consumes these exact owners and creates no parallel dispatch registry.
8. Unsupported required capabilities block activation. Optional/advisory gaps
   require explicit Project Manager acknowledgement.
9. Evidence references are closed structured identifiers; raw excerpts,
   provider responses, hidden reasoning, URLs, paths, credentials, and
   executable content are not persisted.
10. Representative task context is optional and bounded; its absence cannot
    block project guide compilation.
11. Setup failures, capability gaps, timeouts, and retries create no
    ContributionRecord, settlement, award, or negative reputation evidence.
12. No backward-compatibility aliases or dual model-inference paths survive
    final cleanup.
13. Pre-submit has no standalone feedback/execution API. One canonical
    submission preparation/admission request executes one effective plan that
    contains mandatory platform checks plus exact task-locked project rules.
14. Post-submit normal execution is automatically dispatched once from the
    successful Submission creation/finalization boundary. Callers cannot
    select or separately invoke platform, project, or individual checkers.
15. An authorized checker repair/requeue command may exist only when it accepts
    a Submission/run identity and atomically claims the canonical phase-attempt
    row under the phase owner's repository transaction. The idempotency key is
    the phase, exact locked material/plan lineage, and attempt ID. Concurrent
    repair/requeue calls either observe the existing terminal result or one
    caller resumes the same non-terminal run; they cannot rerun completed
    members or create a second business effect. A genuinely new evaluation
    requires a new attempt identity. This is not an alternative checker API.
16. Setup approval/correction-request APIs configure policy, and read APIs
    expose bounded evidence; neither is a checker execution path.
17. AUTH must activate two narrow compilation actions before runtime cutover:
    a Project Manager dispatch/recovery request and a fixed
    `workstream.project.setup` execution action. Execution owns only the model
    call and immutable compilation parent/supersession; 12E/12F/12G retain
    custody of their separate canonical projections.
18. CHECKER exposes one internal typed service port with exactly two phase
    commands: one complete pre-submit evaluation and one complete post-submit
    evaluation. Artifact-flow orchestration invokes each command once at the
    ART material boundary and never calls an individual checker.
19. The pre command is a facade over ART-04B1-04B3's sole compiler, executor,
    attempt, result, and evidence writer. The post command uses CHECKER's sole
    durable executor/repository. The facade creates no duplicate member rows or
    evidence and returns only the canonical phase result/reference.
20. Feature behavior is built hidden before AUTH activation, then cut live;
    AUTH owns action/PREP/evidence custody and POL owns product behavior.
21. The complete unified result, including the post-submit proposal, exists
    before any approval. Separate approval gates never cause inference.
22. Compilation execution uses pre-I/O authorization, a committed durable
    attempt/idempotency reservation, external I/O without held DB locks, and
    fresh result-bound PREP for final persistence.
23. AUTH-12E/12F3 are transitional separate-call implementations. POL-04B
    removes all three legacy inference methods from live reachability; POL-08
    later deletes the retired code without compatibility aliases.
24. Post-submit projection is deterministic from the stored unified component
    and performs zero model calls in projection, approval, correction, replay,
    or recovery.
