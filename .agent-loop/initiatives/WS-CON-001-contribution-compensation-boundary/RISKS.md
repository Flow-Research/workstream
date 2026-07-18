# Risks: WS-CON-001 Contribution Record And Compensation Boundary

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Competing award-eligibility models | Critical | ContributionPolicy is sole authority; semantic then physical clean cut with no fallback | CON-05A/B |
| Review commits without contribution | Critical | Mandatory flush-only participant and one REV-owned commit; fault-injection rollback | CON-07 + REV |
| Reviewer contribution depends on branch state | Critical | Required reviewer operation precedes every branch and has no FinalAcceptance/submitter input; separate accept-only submitter operation | CON-07 + REV-08/10 |
| Submitter contribution inferred from mutable decision shape | Critical | REV-owned immutable FinalAcceptance is the sole accepted_submission source; unique task/Review/Submission and source-shape constraints | REV + CON-03C/07 |
| Mandatory ART projection blocks product truth | Critical | No ART/evidence work in core transaction or release; optional successor only | CON-07/09/11 |
| Wrong frozen policy | Critical | Assignment/lease freeze before work; immutable versions; concurrency proof | CON-05A/06 |
| task.claim activates before submitter policy freeze | Critical | AUTH-PREP + task seam -> CON-05A hidden participant -> task-owned composition -> AUTH-13 activation; pre-activation real-kernel denial | AUTH + task + CON-05A |
| Dispatcher inherits handler authority | Critical | Dispatcher-only action; exact independent service authority for protected handlers | CON-02B/08A/10C + AUTH |
| Release cutoff misses admitted fulfillment work | Critical | Shared fence before every writer ordinal; maximum-ordinal same-session observation; both-order cutoff races; completion-only drain | CON-03D/08/10B/C/11 + REV-12A |
| Operations request authority leaks into execution | Critical | 10B persists bounded human requests only; 10C uses exact fixed-service actions, cross-executor denial, replay/finding proof, and projection-only mutation | CON-10B/10C + AUTH |
| Broad or dynamic service access | Critical | Closed ServiceIdentity/static rows, controlled provisioning, AUTH-09E, cross-service denial | AUTH + CON |
| Partial ART/REV custody transfer | High | Reference complete WS-XINT handoffs; no local subset or dual writer | AUTH |
| Cross-domain deadlock/partial commit | Critical | AUTH-first common prefix; operation-specific REV/task lifecycle-before-policy order; one session/commit; both-order PostgreSQL tests | AUTH + REV + CON |
| Prepared handle substitution or stale authority | Critical | Exact session/action/actor-ref/idempotency/request-digest binding; AUTH consumption after final-fact recomposition; single use and non-consumption on rejected substitution | AUTH + each mutation owner |
| Wrong grant substitutes for shipping authority | High | Exact submitter and reviewer grants only; unrelated project/admin grants deny; no adjudication dependency | AUTH + task/REV |
| Provider I/O under locks | Critical | Durable pre-I/O state; release transaction/fence before adapter call | CON-08A/outbox |
| Callback spoofing/replay | Critical | Exact service identity/static row, binding match, prepared protocol, idempotent receipt | CON-08B + AUTH |
| Legacy row ambiguity | High | Human-approved deterministic rebuild/classification; migration fails closed | Human + CON-05 |
| Premature public release | High | Hidden OpenAPI, exact manifest, AUTH activation, joint REV/CON gate | CON-11 + REV |
| Adjudication scope leaks into v0.1 | High | Accept/reject are terminal; no adjudication model/action/queue/state/contribution/readiness or initiative gate | REV + CON |

No runtime work starts while a blocking decision or prerequisite remains open.
