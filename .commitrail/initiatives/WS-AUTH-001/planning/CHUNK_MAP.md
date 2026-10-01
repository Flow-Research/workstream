# WS-AUTH-001 — Current pre-review activation map

Use the [current plan](PLAN.md) and
[cross-owner order](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
The [verbatim former map](../pre-cutover/CHUNK_MAP.md) preserves all completed
work and historical proposals.

| Boundary | Current owner and prerequisite |
|---|---|
| AUTH-12B2 | Complete; POL-04B is the live consumer |
| [AUTH-12F4](chunks/WS-AUTH-001-12F4-submission-policy-approval.md) | Complete: full-proposal read, correction and approval authority; public POL-05B delivered |
| [AUTH-12G](chunks/WS-AUTH-001-12G-post-submit-checker-policy-mutations.md) | Complete: exact post-policy authority; public POL-06B delivered |
| [AUTH-12H](../WS-AUTH-001-12H.md) | Complete: exact manager authority for CP07; AUTH-18 exposes manager activation and selections publicly |
| CP05 | Complete: exact five policy actions; public Finance exposure delivered by CP05A |
| ARCH-03C | Complete through 03C7: task/assignment authority, public queues, projections and audit reads; replaces broad AUTH-13 |
| [AUTH-18](../WS-AUTH-001-18.md) | Complete: public manager activation/context over CP07 and AUTH-12H; ARCH-03D hidden intake, ARCH-04B input and ARCH-04B2 output custody are delivered; ARCH-04C hidden durable execution is delivered; ARCH-04D1 canonical custody is delivered; ARCH-04D2 exact input/execution/finalization authority is delivered; ARCH-04E1A routing-source facts are next |
| [ARCH-04D2](../../WS-ARCH-001/WS-ARCH-001-04D2.md) | Complete: exact materialization and execute/finalize authority; output write/bind unavailable; replaces AUTH-14/XINT-06B |
| [AUTH-OUTBOX-01](PLAN.md#ws-auth-001-outbox-01--unavailable-dispatcher-contract) | Complete: unavailable exact dispatcher identity/action/phase contract; CON-02B and AUTH-OUTBOX-02 mechanics complete; feature authority/registration remain separate |
| [AUTH-OUTBOX-02](PLAN.md#ws-auth-001-outbox-02--exact-dispatcher-activation) | Complete: exact dispatcher mechanics activation, phase audit custody and bounded prefork delivery; ARCH-03C2 subsequently registers assignment invalidation, while future handlers require their own exact authority |
| [ARCH-04E2](../../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md#current-bounded-sequence) | Exact TASK routing handler authority after hidden 04E1, before live 04E3 |

Guide activation needs CP05 -> CP06 -> hidden CP07 and POL-07, which also
requires independent ARCH-04A registered-capability proof. It does not need
a Task, Submission, CheckerRun, CP09 deletion or REV execution.
