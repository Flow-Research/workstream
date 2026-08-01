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
6. Finding evidence, response evidence, and ART byte binding are separate
   actions with separate human/service principals. Reviewer finding evidence
   may activate before decision; contributor response evidence activates only
   after `needs_revision` creates the exact obligation and preparation.
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
17. XINT-002-07A is the only review-evidence binding availability transition;
    07B adds response-slot evaluator shape without changing availability.
18. XINT-003-02 is split into 02A persistence adoption and 02B prepared mutation
    activation. 02A is merge-safe because the four retired callables have no
    current-main call sites and both ActionIds remain planned. 02B is the only
    external writer and policy-action availability transition.
19. PR #195 is preservation evidence, not a merge base or authorization source.
    Valid policy semantics and PostgreSQL proofs must be recreated from current
    head 0045; its historical 0034 migration, old writer path, merge intent, and
    signed-start records are not adopted.
