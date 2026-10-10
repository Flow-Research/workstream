# WS-ARCH-001 — Current delivery plan through allow_review

## First complete contributor milestone

The goal remains **claim -> upload ZIP -> pre-submit feedback or immutable
Submission -> automatic post-submit checking -> outcome**. For an eligible
project with locked `human_review_required=false`, the outcome includes shared
FinalAcceptance, the submitter ContributionRecord and applicable award facts.
This journey is not yet publicly usable end to end.

### Delivered foundations — do not restart

| Delivered work | What it supplies | What it does not claim |
| --- | --- | --- |
| Public guide setup/approval/activation and TASK creation/claim/start | A contributor works under exact locked project rules | Public ZIP intake or automatic acceptance |
| [B4 checked packet custody](../WS-ARCH-001-04E1BB4.md), [B5 bounded content](../WS-ARCH-001-04E1BB5.md), and [B6 atomic Submission/dispatch](../WS-ARCH-001-04E1BB6.md) | Hidden intake creates the exact verified Submission, receipts, initial evaluation request and shared outbox event atomically | Live delivery or public intake |
| [B7 request delivery](../WS-ARCH-001-04E1BB7.md) and existing CHECKERS execution | Hidden request recovery and exact invocation-fenced execution with retained evidence | Registered production handlers or completion routing |
| [B8 completion delivery](../WS-ARCH-001-04E1BB8.md) and 04E2-B outcomes | Hidden true handoff or false shared acceptance, exact replay and commit-before-ACK | Production registration or public false-guide activation |
| REV-04C / CON-07 shared participants and [REV-12A4A scoped controller](../../WS-REV-001/WS-REV-001-12A4A.md) | Atomic acceptance/task/contribution/award participation and authorized enable/stop control | Genuine acceptance-source authority, complete outcome guarantees or payment delivery |

### Remaining work — governing order

These are four remaining outcome groups, **not four promised PRs**. Each implementation
record must identify its group, the observable gap it closes, existing owners
it reuses and its proof. Review the record against current main before coding.
Do not add another foundation unless an observed blocker to this journey is
explained; do not restart delivered work or substitute a broader subsystem.

| Order | Existing boundary | Required outcome and proof |
| --- | --- | --- |
| 1 | [ARCH-04F remediation and recovery](chunks/WS-ARCH-001-04F-checker-remediation.md) | Contributor-correctable failures expose bounded findings and accept a replacement ZIP under the same locked policy. Preserve prior evidence; distinguish infrastructure retry and project/setup faults. Prove against hidden result/handler contracts before live false-policy activation. |
| 2 | ARCH-04E3 live composition and false-policy readiness | Register the proven handlers and extend the existing controller's manifest/readiness with exact production source custody. Prove success, remediation, shutdown and restart before enabling false. Preserve default-true policy and deny unsupported paths. |
| 3 | ARCH-02I public intake and outcome access | Expose initial upload/preparation, verification progress, feedback, admission-backed creation, checker-remediation resubmission and outcome reads through exact authorized APIs. Remove superseded touched paths; no compatibility route or provider-coordinate exposure. |
| 4 | First-layer integration drill | A real project completes guide approval, task creation/claim/start, failed intake/correction, verified Submission, automatic checking, post-check remediation and false-policy acceptance with exact contribution evidence. Exercise real PostgreSQL, S3-compatible storage and broker/workers, lost responses, duplicate delivery, restart, revocation/isolation and recovery. |

**Immediate next implementation:** group 1, checker remediation and recovery.
Hidden completion delivery is complete; production registration remains disabled.
No user-facing completion claim is valid until group 4 passes.

The first public intake scope is **initial submissions and checker remediation**.
The historical pre-cutover ARCH-02I contract's requirement to implement human
review revisions before any public intake is not adopted for this milestone.
Human-review revision remains unavailable until its own live authority and
lineage are implemented through the same canonical intake operation; it gains no
permissive placeholder or alternate endpoint. The current bounded ARCH-02I record
must use this scope when implementation starts.

ARCH-04F can be implemented and proven against hidden current-result and routing
participants before production false-policy activation. Its dependency is the
required 04E handler/result contracts, not a fully live false branch. This avoids
a cycle: prove success and failure paths first, then activate the connected runtime.
True human-review handoff remains independent of CON/shared acceptance and is not
a requirement to activate human review queues for this first milestone.

Live human review/decisions and reviewer contributions, controlled human revision,
contributor claim expiry/skip, external integrations, frontend expansion, runtime
reputation and unrelated cleanup follow later unless the user changes priority.
Applicable award facts stay atomic in group 1 for paid and unpaid policies.
Fulfillment admission and payment delivery remain unavailable; their obligation
roots, ordinals and cutoff/drain machinery are required before a successor
manifest enables fulfillment, not before the first contribution path. Supported registered
checks must genuinely meet the selected project's requirements: structural checks
must not be advertised as substantive judges, and an unsupported required evaluator
blocks that project rather than being silently omitted.

[ARCH-04E1B-B5](../WS-ARCH-001-04E1BB5.md) delivers shared bounded evaluation content and rejects unrepresentable ZIP input before durable admission. ARCH-04E1B-B6 reuses this projection in atomic Submission/dispatch creation with exact AUTH receipts and select-only replay. B7 delivers hidden request delivery with exact invocation fencing; 04E2-B supplies complete authorized outcomes; B8 supplies hidden completion delivery; remediation is next. Production registration remains unavailable.

[ARCH-04E1B-B4](../WS-ARCH-001-04E1BB4.md) binds Submission summary and attestation to the packet retained by intake, including database custody. B6 now commits the initial reservation and request event with exact receipts and fresh-authorized replay. B7 supplies hidden request delivery; 04E2-B supplies complete authorized outcomes; B8 supplies hidden completion delivery; remediation is next.

[ARCH-04E1B-B3](../WS-ARCH-001-04E1BB3.md) retains the inspected ZIP manifest in immutable ART evidence and returns verified file metadata on admission consumption. ARCH-04E1B-B6 commits that content, exact authority, generation-one reservation and shared request event with each new Submission. No delivery handler or routing authority is activated.
[ARCH-04E1B-B2](../WS-ARCH-001-04E1BB2.md) supplies exact source preparation through
TASK, CHECKERS and historical PROJECTS policy facts. It stages only the existing
routing request; proposed source facts have no fabricated creation timestamp.
04E2-B now publishes the authorized source and complete outcome. B8 supplies hidden completion delivery; production activation remains required. False composition must acquire its REV lifecycle
fence before TASK and revalidate policy under TASK custody; true admission
remains independent of that fence.


[ARCH-04E2-B](../WS-ARCH-001-04E2B.md) delivers the hidden authorized outcome operation.
It consumes canonical fixed-router AUTH and retains the actual immutable decision
with exact Submission, materialization and checker receipts. Locked true moves
TASK to `review_pending` without REV/CON. Locked false uses the shared acceptance
participant to atomically stage FinalAcceptance, TASK/assignment completion,
submitter contribution, applicable awards and audit/outbox evidence. Database
closure rejects incomplete outcomes; fresh-authorized replay returns the stored
complete tuple. No Review or reviewer contribution is fabricated.

B8 supplies hidden completion delivery with commit-before-ACK. Next: 04F remediation, 04E3 production
composition, public intake and the first-layer drill. False-guide activation,
live human review/revision and payment delivery remain unavailable. Internally
valid false-policy fixtures establish the hidden operation, not public readiness.

ARCH-04E1B-B1 supplies TASK-before-CHECKERS custody for reservation, current
reads and admission. B6 atomically creates the Submission and initial dispatch;
04E2-B owns the later authorized outcome. B8 consumes that outcome and commits
before acknowledgment. Remediation is next. Both request and completion handlers
remain absent from production registration.

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
| [AUTH-12H](../../WS-AUTH-001/WS-AUTH-001-12H.md) | POL-07, CP07, merged AUTH-12B2 | Complete: exact manager authority and internal composition for CP07; ARCH-03A completes internal guide facts; AUTH-18 delivers public manager activation/context |
| [ARCH-03A](../WS-ARCH-001-03A.md) | AUTH-12H, CP07 | Complete active and exact frozen PROJECTS guide facts before CP08 |
| [CP08](../WS-ARCH-001-CP08.md) | ARCH-03A | Complete: TASK initial-attempt lineage schema, public facts and minimal existing writers together |
| [ARCH-03B1](../WS-ARCH-001-03B1.md) | ARCH-03A, CP08 | Complete: TaskService detached PROJECTS display and draft lookup |
| [ARCH-03B2](../WS-ARCH-001-03B2.md) | ARCH-03B1 | Complete: hidden project-scoped contributor ready queue facts; no live queue authority/HTTP |
| [ARCH-03B3](../WS-ARCH-001-03B3.md) | ARCH-03B2 | Complete: hidden all-state management and status-only operational queues |
| [ARCH-03B4](../WS-ARCH-001-03B4.md) | ARCH-03B3 | Complete: hidden exact-project contributor and management task detail with assignment visibility |
| [ARCH-03B5](../WS-ARCH-001-03B5.md) | ARCH-03B4 | Complete: replace existing authorized contributor/manager work context with current task facts and exact locked policy references |
| [ARCH-03B6](../WS-ARCH-001-03B6.md) | ARCH-03B5 | Complete: shared historical validation and distinct management/operational/audit locked-context projections; retained management HTTP authority unchanged |
| [ARCH-03B7](../WS-ARCH-001-03B7.md) | ARCH-03B6 | Complete: immutable contributor/management requirements through one historical translator and TASK-before-visibility locking; retained HTTP authority unchanged |
| [ARCH-03B8](../WS-ARCH-001-03B8.md) | ARCH-03B7 | Complete: bounded hidden task audit evidence with atomic scope and exact transition references |
| [ARCH-03B9](../WS-ARCH-001-03B9.md) | ARCH-03B8, CON-02B and AUTH-OUTBOX-02 | Complete: hidden exact-assignment invalidation with committed cause and delivery custody |
| [ARCH-03C1](../WS-ARCH-001-03C1.md) | ARCH-03B9, AUTH-OUTBOX-02 | Complete: exact reconciler authority and decision-bound release receipts |
| [ARCH-03C2](../WS-ARCH-001-03C2.md) | ARCH-03C1 | Complete: atomic originating publication and registered assignment delivery with enforced prefork topology |
| [ARCH-03C3](../WS-ARCH-001-03C3.md) | ARCH-03C2 and hidden TASK owner contracts | Complete: exact manager create/screen/release authority, atomic evidence and replay |
| [ARCH-03C4](../WS-ARCH-001-03C4.md) | ARCH-03C3 | Complete: exact-authorized contributor, manager and operational public queues |
| [ARCH-03C5](../WS-ARCH-001-03C5.md) | ARCH-03C4 | Complete: exact-authorized Contributor/Manager detail and requirements |
| [ARCH-03C6](../WS-ARCH-001-03C6.md) | ARCH-03C5 | Complete: distinct exact-authorized locked-context reads |
| [ARCH-03C7](../WS-ARCH-001-03C7.md) | ARCH-03C6 and hidden TASK owner contracts | Complete: bounded Audit Authority history access; public guide activation, ARCH-03D hidden intake, hidden post-submit materialization, ARCH-04B2 output custody, ARCH-04C execution, ARCH-04D1/04D2 custody/authority and ARCH-04E1A source-only facts/types delivered |
| [CP05A](../WS-ARCH-001-CP05A.md) | CP05, existing policy owners | Complete: public Finance policy administration and selector recovery; public manager activation, ARCH-03D hidden intake, hidden post-submit materialization, ARCH-04B2 output custody, ARCH-04C execution, ARCH-04D1/04D2 custody/authority and ARCH-04E1A source-only facts/types delivered |
| Physical economic cleanup (Complete; historical CP09 grouping) | [Migration 0023 cleanup](../../../changes/remove-obsolete-task-payment-policy.md) removes unused storage and remaining consumers with retained-data refusal | No repeated removal or public 02I prerequisite; acceptance and fulfillment activation remain separate |
| [ARCH-03D](../WS-ARCH-001-03D.md) | AUTH-18, ARCH-03A, CP08 and merged ART preparation | Complete: hidden durable intake uses exact historical TASK/PROJECTS ports; public cutover remains ARCH-02I |
| ARCH-04B | ARCH-04A, POL-07, ARCH-03C, merged ARCH-02H | Complete: ART hidden verified Submission input; exact live authority is delivered by ARCH-04D2 |
| [ARCH-04B2](../WS-ARCH-001-04B2.md) | ARCH-04A and merged ART admission/verification/binding foundations | Complete: hidden bounded checker-output store/recovery and verified binding, no routing or live reservation |
| ARCH-04C | ARCH-04A, ARCH-04B, delivered ARCH-04B2, POL-07 | Complete hidden CHECKERS execution/result/currentness and worker recovery, including exact empty output sets |
| [ARCH-04D1](../WS-ARCH-001-04D1.md) | ARCH-04B, ARCH-04C | Complete: canonical ART custody for terminal evidence retaining material |
| [ARCH-04D2](../WS-ARCH-001-04D2.md) | ARCH-04D1 | Complete: exact AUTH input, execution and finalization; no output-file authority |
| AUTH-OUTBOX-01 | Merged shared outbox persistence and AUTH service/PREP foundations | Complete: planned dispatcher identity/action/matrix and unavailable typed authority contract |
| CON-02B | AUTH-OUTBOX-01 | Complete: shared hidden dispatcher/claim fencing, typed handlers and recovery |
| AUTH-OUTBOX-02 | CON-02B exact hidden manifest | Exact dispatcher mechanics only; no feature authority |
| [ARCH-04E1A](../WS-ARCH-001-04E1A.md) | ARCH-04C/04D2 | Complete: route-neutral immutable TASK source schema/detached facts and source-neutral accepted-effects types; REV-04C uses a bounded exact-source verifier, with no general routing publication writer/reader, handlers, current pointer or routing authority |
| ARCH-04E1B-A | ARCH-04E1A, AUTH-19A | Complete: TASK caller-session request/source-identity reservation; no source publication, handler or commit |
| [ARCH-04E2-A](../WS-ARCH-001-04E2A.md) | ARCH-04E1B-A | Complete: strict AUTH-private resource/request/consequence matcher and nominal fixed-router adapter through canonical PREP; action stays planned/unavailable, with no handle, allow, receipt, source write or effect |
| [ARCH-04E1B-B1](../WS-ARCH-001-04E1BB1.md) | REV-04C and existing CHECKERS coordinator | Complete: required TASK reservation/current-read guard, ordered admission INSERTs, exact terminal replay and mechanical race proof; no handler or activation |
| [ARCH-04E1B-B2](../WS-ARCH-001-04E1BB2.md) | 04E1B-B1, existing historical PROJECTS context | Complete: exact detached source preparation and reserved identity; no publication, authority or handler effect |
| [ARCH-04E1B-B3](../WS-ARCH-001-04E1BB3.md) | Existing ART inspected manifest and evidence custody | Complete: retained verified ZIP metadata and consumed-only projection; B6 supplies atomic Submission/dispatch |
| [ARCH-04E1B-B4](../WS-ARCH-001-04E1BB4.md) | Existing intake packet commitment and hidden Submission composition | Complete: service/database checked-packet custody; B6 supplies atomic Submission/dispatch |
| [ARCH-04E1B-B5](../WS-ARCH-001-04E1BB5.md) | Existing inspected FILE metadata and exact TASK/PROJECTS facts | Complete: shared bounded evaluation content before durable admission; reused by B6 atomic Submission/dispatch |
| [ARCH-04E1B-B6](../WS-ARCH-001-04E1BB6.md) | B3/B4/B5 plus existing TASK/ART/AUTH/CHECKERS/outbox owners | Complete: atomic new Submission, exact creation/binding receipts, generation-one request and shared event; fresh-authorized select-only replay; handlers remain unregistered |
| [ARCH-04E1B-B7](../WS-ARCH-001-04E1BB7.md) | B6 plus existing execution/authorization/outbox owners | Complete: hidden request handler, exact committed invocation and per-phase fencing; UNKNOWN never automatically repeats execution; production registration remains unavailable |
| [ARCH-04E1B-B8](../WS-ARCH-001-04E1BB8.md) | Complete ARCH-04E2-B authorized outcome operation and CON-02B; delivered B7 already supplies request handling | Complete: consumes the receipt-bound operation with exact typed result and commit-before-ACK; proves replay, uncertainty and generation/finalization races. Production registration remains ARCH-04E3 |
| [REV-12A4A scoped controller](../../WS-REV-001/WS-REV-001-12A4A.md) | Same REV-12A1 fence and REV-04C participants | Complete: internal Operator transitions, immutable AUTH/history custody and current-generation participant gates. The initial manifest refuses pre-authority acceptance rows; 04E2-B supplies exact source custody; B8 completion delivery is implemented; remediation and production readiness remain group 1/2 work. |
| [ARCH-04E2-B](../WS-ARCH-001-04E2B.md) | Exact source preparation and REV-12A4A generation | Complete: mandatory actual AUTH receipt, database complete-set enforcement, shared audit/outbox and atomic true/false outcomes; B8 supplies hidden completion delivery; production registration remains |
| ARCH-04E3 | ARCH-04E2, ARCH-04D2, AUTH-OUTBOX-02; shared acceptance proof for false | TASK live dispatch/routing composition: true to allow_review, false/pass to shared acceptance when proven |
| ARCH-04E | ARCH-04E3 | Completed coordination boundary consumed by downstream REV |
| ARCH-04F (before false activation and public intake) | Required hidden 04E result/handler contracts; no live false-branch prerequisite | CHECKER failure facts and TASK/ART remediation resubmission, not REV |

False guide activation additionally requires shared acceptance, exact AUTH,
a valid generation through the delivered REV-12A4A controller with
production readiness verified at ARCH-04E3 and
the usable ARCH-04F failure route. The true routing foundation may ship first
with false still unavailable; neither route invents a new acceptance subsystem.
Shared REV acceptance persistence/CON participation can precede live human
queues or decisions, so this extension adds no REV-admission dependency cycle.
The first complete contributor milestone includes public claim/upload/pre-check
feedback, immutable Submission, automatic checking, failure remediation and, for
locked false, shared FinalAcceptance plus the submitter ContributionRecord and
applicable awards. Complete it before live human review/revision; independent
review work requires an explicitly assigned parallel scope and must not delay that path.

CP05 and ARCH-04A have independent prerequisites. POL-04B consumes the corrected
ARCH-04A catalogue/schema before producing approval-eligible generations. Owners may
work concurrently if allowed paths do not overlap; shared catalogue/schema
changes must be serialized or rebased, not implemented twice. ARCH-03A completes the existing internal guide-context port after AUTH-12H.
CP08 completes its schema and minimal existing writers together. Projections
through 03B8 are complete: detached metadata, queues, detail, work context,
locked context, requirements and bounded audit evidence. ARCH-03B9 completes
hidden exact-assignment invalidation on the delivered shared dispatcher.
ARCH-03C1 completes exact reconciler authority and decision-bound receipts.
ARCH-03C2 supplies originating-transaction-only per-assignment producer events
and first handler registration with enforced prefork topology; it must never
backfill or dispatch retained invalidation rows. Public TASK activation is complete through ARCH-03C7. AUTH-18 delivers public
manager guide activation/context; ARCH-03D hidden intake, hidden exact post-submit materialization and ARCH-04B2 output custody are delivered; ARCH-04C hidden execution is delivered; ARCH-04D1 canonical custody, ARCH-04D2 authority and ARCH-04E1A source-only facts/types are delivered. Subsequent
PR-sized contracts name exact files, public types, current migration head and
runnable proof before implementation; they refine this design, not create a
new permission requirement.

### Supporting foundations required by automatic routing

Delivered supporting foundations are [ARCH-04B2](../WS-ARCH-001-04B2.md),
[AUTH-OUTBOX-01/02](../../WS-AUTH-001/planning/PLAN.md#ws-auth-001-outbox-01--unavailable-dispatcher-contract),
and [CON-02B](../../WS-CON-001/OVERVIEW.md#con-02b-current-dispatcher-contract).
REV-12A1 delivers disabled controller/fence mechanics, CON-07 delivers the
hidden source-neutral submitter participant and complete frozen award-set owner,
and REV-04C composes hidden FinalAcceptance/TASK/CON effects. The current
false-branch priority follows the first-layer sequence: delivered atomic Submission/dispatch and request delivery, then complete authorized outcomes before completion delivery.
Both branches have request reservation 04E1B-A and hidden AUTH preparation
04E2-A delivered; complete authorized outcomes 04E2-B precede completion delivery 04E1B-B and live 04E3; true routing can proceed after its own prerequisites without CON or
shared acceptance. False adds those participants and scoped lifecycle activation.
See [ARCH-04E1B/04E2/04E3](chunks/WS-ARCH-001-04E-canonical-allow-review.md#current-bounded-sequence)
and ARCH-04F. ARCH-04E1A is delivered as the source-only predecessor.
Each numbered section is a current bounded design, expanded into its own change
record on implementation; the parent is not a multi-owner implementation PR.

The shared module supplies append/flush and idempotency, and CON-02B supplies
hidden claim/invoke/finalize, custody and recovery. AUTH-OUTBOX-01 has supplied
dispatcher metadata and typed authority; AUTH-OUTBOX-02 has activated
that exact manifest with real phase audit custody and bounded prefork workers.
The production registry contains only assignment invalidation; each later feature
requires its own authority. None depends on ContributionRecord, fulfillment
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

Hidden ARCH-04B2 ART checker-output storage and binding are delivered, not
implicit in CHECKERS result persistence. They supply bounded generated-output
ingestion, generic quota admission attributed to the fixed service, independent
reread verification and exact checker-output binding. CHECKERS
reservation/currentness is implemented, output authority remains deny-only, and the current
structural catalogue reserves zero output slots; controlled nonempty fixtures
prove ART mechanics only. ARCH-04C finalizes only that exact empty output set, using the
[bounded execution contract](../WS-ARCH-001-04C.md). A future registered
output-producing capability must add real producer and atomic binding proof
before output authority activation; controlled nonempty fixtures do not establish
that capability. [ARCH-04D2](../WS-ARCH-001-04D2.md) activates only current
materialization, execution and finalization authority. A later real output
producer owns write/binding activation. In that planned output flow, external byte I/O occurs
before the final caller transaction; binding publication and final result become
visible atomically.
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

ARCH-04B input proof is delivered in `test_post_submit_materialization.py` and
`test_post_submit_selection.py`, including deny-before-I/O composition. ARCH-04B2
delivers output custody proof; ARCH-04C delivers hidden durable execution proof. ARCH-04D2 supplies exact input/execution/finalization authority and durable receipt custody. The delivered
[ARCH-04D1 canonical material custody](../WS-ARCH-001-04D1.md)
requires independent admission/replica/manifest substitution rejection at durable
finalization before activation.

The delivered 04C/04D2 row names implemented proof. Other rows retain future
implementation obligations; each owner's bounded record fixes its final module
path and compatible execution evidence. Run them through `cd backend && uv run pytest <owner-test-file>`
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
| ARCH-04C/04D2 | `test_revoked_after_consumer_cannot_publish`, `test_outer_deadline_revalidates_material_after_cleanup`, `test_terminal_replay_validates_both_stored_receipts_without_side_effects`, `test_stale_worker_cannot_finalize_after_takeover` | Consume delivered 04B2 custody; Local/MinIO, real worker/provider contract and PostgreSQL races; independent sessions and staged/final state |
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
