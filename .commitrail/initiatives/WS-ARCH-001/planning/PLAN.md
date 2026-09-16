# WS-ARCH-001 — Current delivery plan through allow_review

## Current dependency contract

This section and the corrected pending child contracts are the current
cross-initiative delivery order. Completed records and review notes preserve
their original evidence; they do not restart superseded work. The stop point
of this reconciliation is canonical `allow_review`; downstream REV execution
is not redesigned here. The [shared acceptance extension](../../../../docs/spec_review_lifecycle.md#finalacceptance)
adds the locked false/pass outcome to the same routing handler without changing
the human review/revision design. 04F preserves the required
checker-remediation boundary before public Submission cutover.

| Boundary | Hard predecessors | Sole output owner |
|---|---|---|
| POL-04B1 | Existing AUTH-12I request contract and immutable compilation/ART material foundations | AUTH/PROJECTS automatic request origin custody, no provider call |
| POL-04B | POL-04B1 plus merged POL-04A/04A3/04A2, AUTH-12I/12J/12B2, ARCH-04A catalogue/schema foundation | PROJECTS live unified setup wiring, no new compiler/finalizer |
| CP05 | Merged CP04A/CP04B | AUTH exact policy-action activation |
| [CP06](../WS-ARCH-001-CP06.md) | CP05 | Complete CON exact-version validation facts; no guide/attempt write |
| [CP07](../WS-ARCH-001-CP07.md) | CP06 | Complete: PROJECTS hidden activation/binding and replacement readiness guard; live authority is delivered by AUTH-12H |
| ARCH-04A | Merged canonical CHECKER catalogue and unified compilation contracts | CHECKERS post-phase public facts and registered evaluator conformance, no live run |
| POL-05A | POL-04B | PROJECTS hidden effective/pre approval and separate immutable operation provenance |
| AUTH-12F4 | POL-05A | AUTH approval adapter |
| POL-05B | POL-05A, AUTH-12F4 | PROJECTS live pre-policy approval |
| POL-06A | POL-05B | PROJECTS hidden post-policy projection/approval/correction provenance |
| AUTH-12G | POL-06A | AUTH exact post-policy action adapters |
| POL-06B | POL-06A, AUTH-12G | PROJECTS live post-policy configuration, zero evaluator calls |
| POL-07 | POL-06B, ARCH-04A, merged ART pre executor | One facade over ART pre and CHECKERS post contracts; no new persistence |
| [AUTH-12H](../../WS-AUTH-001/WS-AUTH-001-12H.md) | POL-07, CP07, merged AUTH-12B2 | Complete: exact manager authority and internal composition for CP07; ARCH-03A completes internal guide facts; HTTP exposure remains pending |
| [ARCH-03A](../WS-ARCH-001-03A.md) | AUTH-12H, CP07 | Complete active and exact frozen PROJECTS guide facts before CP08 |
| [CP08](../WS-ARCH-001-CP08.md) | ARCH-03A | Complete: TASK initial-attempt lineage schema, public facts and minimal existing writers together |
| [ARCH-03B1](../WS-ARCH-001-03B1.md) | ARCH-03A, CP08 | Complete: TaskService detached PROJECTS display and draft lookup |
| ARCH-03B remaining | ARCH-03B1; AUTH-OUTBOX-01 and CON-02B for invalidation | Queues and actor-specific projections; hidden assignment invalidation only after shared committed claims |
| ARCH-03C | ARCH-03B, AUTH-OUTBOX-02 | AUTH exact task/assignment activation and integrated readiness proof |
| CP09 (later cleanup coordination) | All legacy consumers replaced, including CHECKER and public 02I path | Physical economic deletion; not on the allow_review critical path |
| ARCH-04B | ARCH-04A, POL-07, ARCH-03C, merged ARCH-02H | ART exact stored Submission materialization |
| ARCH-04B2 | ARCH-04A and merged ART admission/verification/binding foundations | ART bounded checker output/log ingestion and verified binding, no routing |
| ARCH-04C | ARCH-04A, ARCH-04B, ARCH-04B2, POL-07 | CHECKERS durable execution/result/currentness and worker recovery |
| ARCH-04D | ARCH-04B, ARCH-04C | AUTH post-submit materialization/result activation |
| AUTH-OUTBOX-01 | Merged shared outbox persistence and AUTH service/PREP foundations | Planned dispatcher identity/action/matrix and unavailable typed authority contract |
| CON-02B | AUTH-OUTBOX-01 | Shared hidden dispatcher/claim fencing, typed handlers and recovery |
| AUTH-OUTBOX-02 | CON-02B exact hidden manifest | Exact dispatcher mechanics only; no feature authority |
| ARCH-04E1A | ARCH-04C | TASK routing-manifest schema/public facts and accepted-effects port, no handlers or REV dependency |
| ARCH-04E1B | ARCH-04E1A, CON-02B hidden contract; shared REV-04B + CON-03C/07 + REV-12A shared fence foundation for false | TASK hidden handlers; consume one shared acceptance operation on false/pass |
| Scoped XINT-003-08B controller activation | Early existing REV-12A foundation and hidden shared acceptance/writer/observation proof | Existing Operator lifecycle-control action for the bounded shared manifest, not human runtime |
| ARCH-04E2 | ARCH-04E1B; scoped XINT-003-08B controller activation for false | AUTH exact TASK routing authority |
| ARCH-04E3 | ARCH-04E2, ARCH-04D, AUTH-OUTBOX-02; shared acceptance proof for false | TASK live dispatch/routing composition: true to allow_review, false/pass to shared acceptance when proven |
| ARCH-04E | ARCH-04E3 | Completed coordination boundary consumed by downstream REV |
| ARCH-04F (later public-cutover prerequisite) | ARCH-04E | CHECKER failure facts and TASK/ART remediation resubmission, not REV |

False guide activation additionally requires shared acceptance, exact AUTH,
a valid generation through scoped XINT-003-08B controller activation and
the usable ARCH-04F failure route. The true routing foundation may ship first
with false still unavailable; neither route invents a new acceptance subsystem.
Shared REV acceptance persistence/CON participation can precede live human
queues or decisions, so this extension adds no REV-admission dependency cycle.

CP05 and ARCH-04A have independent prerequisites. POL-04B consumes the corrected
ARCH-04A catalogue/schema before producing approval-eligible generations. Owners may
work concurrently if allowed paths do not overlap; shared catalogue/schema
changes must be serialized or rebased, not implemented twice. ARCH-03A completes the existing internal guide-context port after AUTH-12H.
CP08 completes its schema and minimal existing writers together; ARCH-03B retains
queues/invalidation and broader projections after completed 03B1 metadata cutover.
The invalidation handler additionally requires CON-02B committed claims; actor-wide
changes need explicit per-project TASK events, not arbitrary outbox scope. Subsequent
PR-sized contracts name exact files, public types, current migration head and
runnable proof before implementation; they refine this design, not create a
new permission requirement.

### Supporting foundations required by automatic routing

Current supporting contracts are [ARCH-04B2](chunks/WS-ARCH-001-04B-art-post-submit-materialization.md#arch-04b2--separate-art-output-custody-child),
[AUTH-OUTBOX-01/02](../../WS-AUTH-001/planning/PLAN.md#ws-auth-001-outbox-01--unavailable-dispatcher-contract),
[CON-02B](../../WS-CON-001/OVERVIEW.md#con-02b-current-dispatcher-contract), and
[ARCH-04E1A/04E1B/04E2/04E3](chunks/WS-ARCH-001-04E-canonical-allow-review.md#current-bounded-sequence).
Each numbered section is a current bounded design, expanded into its own change
record on implementation; the parent is not a multi-owner implementation PR.

An outbox row is not a running dispatcher. The existing shared module supplies
append/flush and idempotency, but delivery is still CON-02B work. Reuse that
existing boundary: AUTH first supplies planned dispatcher metadata and typed
authority; CON-02B builds hidden claim/invoke/finalize mechanics; AUTH then
activates that exact manifest. None depends on ContributionRecord, fulfillment
or REV implementation. TASK must not implement an alternative outbox worker.
Registration and activation are distinct product-authority changes, not
extra planning/administrator approval ceremonies.

04E integrates two explicitly registered typed event handlers: TASK evaluation
request to CHECKERS execution, and CHECKERS final-result notification to TASK
routing. Each handler validates the committed outbox claim and obtains its own
feature authority; dispatcher credentials never authorize artifact reads,
checker finalization or task transitions. The implementation contract must
name those feature action/resource manifests, not infer authority from the
event type. Lost delivery/redelivery cannot create a new logical evaluation.

ART checker-output storage is also missing, not implicit in CHECKERS result
persistence. An ART-owned child of 04B supplies bounded generated-output/log
ingestion, generic quota admission attributed to the fixed service, independent
reread verification and exact checker-output binding. Its controlled hidden
fixtures use 04A public request/run facts, not a future TASK dispatch row or
private CHECKERS import. 04C composes the resulting verified binding references
with final-result persistence; 04D activates the exact ART write/binding and
CHECKERS completion surfaces. External byte I/O occurs before the final caller
transaction; binding publication and final result become visible atomically.
Failed storage never becomes contributor blame or an `allow_review` result.
No second artifact store, quota ledger or historical ART-06B implementation
lane is introduced.

Required capability support is a real prerequisite, not an optimistic label.
The current structural post-submit catalogue is not proof of substantive work
evaluation for a requirement claiming that coverage. ARCH-04A owns the missing registered capability/conformance work
for each selected automated capability. Explicitly approved `human_review`
requirements remain valid; unsupported automation is never silently reassigned. If a new capability changes the catalogue,
an old setup generation cannot adopt it in place: compile and approve a new
generation from that exact snapshot. Unknown required checks block the affected
guide; they never become permissive fallback checks.

### One mutation owner per boundary

- ART compiles/executes intake and owns admission/materialization/binding.
  POL consumes its default-plus-project compiler; it does not fork it.
- PROJECTS owns proposal/approval/activation and separate downstream operation
  records. A finalized setup row/receipt is immutable; approval is not another
  finalization or an in-place continuation of its closed row.
- CHECKERS owns registered work evaluation, durable attempts/results and
  currentness. POL-07 owns only facade composition. TASK projects the current
  recommendation, not a second checker decision.
- CON validates that the explicit expected policy version matches the active
  aggregate's current published selector under lock; PROJECTS binds it on
  activation. Existing work retains its frozen version. CP08 owns TASK lineage
  schema and minimal existing writers together after ARCH-03A. ARCH-03B owns remaining task surfaces. Neither CON
  nor AUTH calls back into PROJECTS activation.
- ARCH-04B/04D/04F replace historical ART-06A, XINT-06B/AUTH-14 and XINT-05C
  respectively; those old plans do not open parallel implementation lanes.

### Feasibility and falsification proof for future implementations

For each row, prove its output using only predecessor outputs and controlled
owner fixtures; do not seed future live authority to make a fixture pass.
In particular: activate a guide without a Task/CheckerRun/legacy PaymentPolicy;
deny missing review/revision configuration and required checker gaps; keep
finalization byte-for-byte unchanged across approval/correction/replay; reject
a structurally valid but substantively failing artifact through any evaluator
claiming substantive coverage; preserve mandatory defaults; reject cross-generation intake
evidence reused as post-submit evidence. AUTH denial before I/O means no read;
late revocation after I/O means no final current result/routing, not impossible
retroactive removal of an already-authorized read. Prove crash/retry identity,
atomic outbox/result/manifest custody and independent-session races in the
owning implementation, not with planning prose or fake database claims.


## Historical continuity and implementation scope

### Named proof targets for the remaining design

These are required future implementation tests, not tests claimed present or
executed by this planning PR. Each owner's bounded record fixes the final
module path alongside implementation; the symbols preserve the behavioral
obligation. Run them through `cd backend && uv run pytest <owner-test-file>`
and the unchanged hosted suite/coverage gates. Database, I/O and concurrency
claims require their real custody, not unit substitutes.

| Owner boundary | Future proof symbol(s) | Required custody / counterexample |
|---|---|---|
| POL-04B | `test_live_setup_uses_only_unified_attempt`, `test_finalization_replay_makes_zero_provider_calls` | Real API/worker composition and PostgreSQL; legacy call injection must fail |
| POL-05A/05B | `test_approval_preserves_finalized_setup`, `test_effective_intake_keeps_platform_defaults` | PostgreSQL rollback/race plus canonical ART compiler; attempted default removal and mixed hash deny |
| POL-06A/06B | `test_post_policy_operation_preserves_finalization_without_provider_or_evaluator_calls`, `test_corrected_generation_replaces_policy_and_retains_original_receipts` | PostgreSQL provenance and provider-call spy; stale upstream approval denies |
| ARCH-04A/POL-07 | `test_registered_evaluator_rejects_invalid_work`, `test_checker_facade_delegates_once` | Actual registered evaluator fixtures and typed composition; presence-only mutant must fail |
| CP06/CP07/AUTH-12H | `test_activate_without_legacy_payment_or_task`, `test_activation_requires_exact_selected_policy`, `test_activation_rejects_missing_review_revision_config` | PostgreSQL atomic command plus full response serialization; foreign/retired/incomplete new binding denies |
| CP08/ARCH-03A/03B/03C | `test_ready_preserves_screening_policy_lock`, `test_claim_copies_policy_without_current_lookup` | PostgreSQL and actual AUTH/owner composition; later publication leaves existing attempt unchanged |
| ARCH-04B/04C/04D | `test_exact_post_materialization_denies_before_io`, `test_late_revocation_cannot_publish_result`, `test_unfinished_checker_recovery_reuses_attempt`, `test_terminal_retry_requires_operator_and_new_attempt` | Local/MinIO, real worker/provider contract, PostgreSQL races; independent sessions and staged/final state |
| ARCH-04E | `test_submission_to_current_allow_review`, `test_superseded_run_cannot_route`, `test_duplicate_dispatch_has_one_manifest`; false tests in the shared acceptance contract | Real DB/worker/storage path, exact authority-event references; true creates no acceptance, false creates the shared atomic acceptance with no human Review |

Owner-local schema names and migrations are chosen from the then-current
baseline in the same implementation PR. No migration numbers or future
runtime success are invented here.

The [preserved plan](../pre-cutover/PLAN.md) retains the complete original
architecture/debt and downstream REV/CON history. It is not the current
dependency order. Current [chunk map](CHUNK_MAP.md) and the corrected child
contracts in this directory supersede conflicting pending sequencing there.
Unchanged predecessor evidence remains in the preserved records; no completed
work is repeated. No backend capability, route or authorization is activated
by this planning update.

Each implementation uses one bounded change record in its existing initiative,
expanded from these current contracts with exact files, current schema head,
proof commands and affected reviewers in the same implementation PR. No
additional planning-only PR or administrator permission is implied by that
expansion. Human approval and merge remain GitHub responsibilities.
