# Decisions: WS-XINT-003 REV-AUTH End-to-End Contract

1. REV owns lifecycle meaning and persistence; AUTH owns authority evaluation,
   PREP custody/consumption, and decision evidence.
2. Existing review/revision policy persistence is reconciled once. REV-03P and
   AUTH-12D2 may not create duplicate models, routes, or writer services.
3. Queue visibility does not imply claim authority; claim does not imply packet
   or decision authority without the exact active lease.
4. Reviewer authority requires the exact project reviewer grant and denies
   self-review. Submitter/adjudicator/admin roles do not substitute.
5. `review.context.read` and `review.chain.read` expose bounded lease-scoped
   facts. Neither grants generic artifact or historical-byte access.
6. Reviewer note/findings and bounded contributor response text require no
   separate artifact upload in v0.1. ART review-evidence binding remains
   planned/unavailable pending separate REV-owned intent.
7. `review.decision` activates only after Review, findings/resolutions,
   FinalAcceptance when accepting, Task/Assignment effects, CON records, audit,
   and outbox are one fail-closed transaction.
8. Human Review revision and checker remediation remain separate closed
   contexts even when they share submission preparation/create actions.
9. Project Managers repair only covered-project revision state; Operators use
   distinct reason-bound recovery actions and never receive reviewer authority.
10. Both reconciliation identities share one ActionId and therefore one
    activation wave; their server-derived modes and scopes remain distinct.
11. Each fixed service command has a closed identity/action matrix. Prepared handles
    never enter Celery payloads.
12. XINT-002 retains sole custody of ART review actions and shared submission
    preparation/create activation. XINT-003 owns activation of the human REV
    context, finding, response, chain, and lifecycle actions.
13. WS-XINT-003-01 transfers the 19 registered planned REV action rows from the
    historical placeholder AUTH-REV groups into one canonical planning custody
    table and its waves without changing runtime `ActionOwner`, permissions, or
    availability in 01. Runtime owner evidence changes only in each refreshed
    activation chunk. XINT-002-owned rows are excluded from that transfer.
14. Registration/planning does not activate product behavior. Final route
    release waits for complete conformance.
15. Obsolete signed-start, active-chunk, and merge-intent language in historical
    REV planning does not govern current work under `AGENTS.md`.
16. Existing project ReviewPolicy/RevisionPolicy tables are the sole future
    persistence records. XINT-003-02 introduces the sole append-only writer and
    removes the four legacy callable mutator/construction paths named in the
    reconciled REV-03P/AUTH-12D2 contracts.
17. XINT-002-07A activates reviewer packet materialization only. Review-evidence
    binding remains planned/unavailable; 07B is reserved pending separate
    REV-owned intent.
18. AUTH readiness precedes REV lifecycle implementation. 02C installs the
    complete unavailable catalogue and fixed-principal matrix; 02D publishes
    closed PREP contracts. REV implementation is a prerequisite to later
    availability, not to AUTH readiness.
19. REV exclusively owns queue/lease persistence, reviewer selection,
    claim/release/preference semantics, packet-manifest semantics, Review,
    ReviewFinding, FindingResolution, FinalAcceptance, decision orchestration,
    human-revision replay, recovery/reconciliation/projection behavior,
    lifecycle fences, and product-router release.
20. `review.queue.read`, `review.claim`, release/decline, and timer actions use
    separate activation gates aligned to REV-05B, REV-06A, REV-06B, and REV-06C.
    `review.decision` waits for REV-10; REV-08 alone cannot activate it.
21. AUTH activation supports hidden integrated proof only. REV-13C is the sole
    product-router release and no earlier AUTH wave exposes a lifecycle route.
22. Evidence-upload actions carry a distinct future-intent-required,
    unavailable classification and cannot be swept into ordinary v0.1
    activation.
