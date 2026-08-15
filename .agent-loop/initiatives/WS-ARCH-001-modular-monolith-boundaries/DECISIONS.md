# Decisions: WS-ARCH-001 Modular Monolith Boundaries

## D1: Keep twelve existing modules

Keep nine business modules (`actors`, `authorization`, `projects`, `tasks`,
`artifacts`, `checkers`, `reviews`, `contributions`, `compensation`) and three
supporting modules (`audit`, `outbox`, `api_controls`). Do not add a generic
workflow or orchestrator domain module.

## D2: Public API is the only runtime import surface

Outside a module, the only permitted runtime import prefix is
`app.modules.<target>.api`. Public APIs are capability-oriented and introduced
only with a real consumer.

## D3: Coordination does not transfer ownership

One contributor may edit several modules in one bounded cross-module chunk.
The worktree or coordinating initiative does not determine domain ownership.

## D4: Incremental strangler recovery

Freeze exact existing debt, reject new edges, and remove touched edges with
each delivery chunk. Do not perform a repository-wide reorganization.

## D5: Submission belongs to TASKS

TASKS owns immutable Submission creation and its predecessor chain. ART owns
ready-admission consumption and exact artifact binding through public ports.
The composed TASK application command coordinates the final transaction.

## D6: Existing specialist initiatives remain authoritative

`WS-AUTH-003` owns AUTH internals and its private-import ledger.
`WS-QUAL-002` owns behavior/test ownership. WS-ARCH-001 owns the canonical
module map, general cross-module dependency rule, and coordinated debt-removal
sequence.

AUTH edges are never copied into a WS-ARCH ledger. The general validator loads
WS-AUTH-003's canonical ledger through its existing parser and fails if the
AUTH-specific and general views diverge.

## D7: Application wiring is classified, not exempted

API delivery, adapters, durable workers, and legacy shared interfaces are all
scanned. Their current private product imports are protected debt and may not
grow. `backend/app/interfaces/**` is not a permanent public contract surface.
Database metadata discovery is a distinct infrastructure concern: only the
exact registered discovery path may import module model declarations, and that
exception grants no runtime command, repository, service, or authority access.

## D8: Submission preparation requires PROJECT and CHECKER capabilities

TASKS owns task, assignment, predecessor, and Submission lifecycle facts. It
does not own locked Project Guide/policy persistence or effective checker-plan
compilation. WS-ARCH-001-02 therefore includes explicit PROJECTS and CHECKERS
prerequisite contracts rather than preserving those private imports behind a
TASK facade.

## D9: Activation follows hidden public-boundary proof

Typed owner APIs merge first while operations remain hidden or deny-only.
Contributor preparation activates only after its complete hidden path consumes
public owner capabilities. Binding/human consumption authority activates only
after the hidden TASK/ART transaction is proven. Public reachability changes
last, in the same clean cut that removes legacy input and precheck behavior.

## D10: Composition owns wiring, not lifecycle truth

The application composition root opens the transaction and constructs
transaction-bound port implementations. The TASK-owned application command
sequences Submission creation through injected AUTH and ART ports. AUTH, ART,
PROJECTS, CHECKERS, and TASKS retain their own locks and invariants; the
composition layer contains no product-state branching or authorization policy.

## D11: Public clean cut waits for all submission contexts

Initial preparation may become live behind its hidden surface after 02G, and
the hidden consumption transaction may receive exact authority after 02H. The
public Submission route remains on its guarded legacy path until initial,
checker-remediation, and reviewer-requested revision contexts all use the same
admission-backed contract and post-submit checker/REV handoffs are live. 02I is
therefore deferred across the required WS-ARCH-001-03/04/05 splits; it cannot
strand `needs_revision` contributors or create Submissions that cannot reach
visible checker and reviewer admission facts.

## D12: Canonical allow-review is the upstream completion milestone

The next cross-module milestone is not REV lifecycle implementation and is not
the public 02I cutover. It is one hidden but production-authorized,
admission-backed Submission reaching a durable current post-submit checker
result of `allow_review` through owner public APIs. Existing legacy pre-review
behavior is regression evidence only and cannot satisfy this milestone.

## D13: Separate readiness, review admission, and public release

PROJECT/POL readiness and TASK assignment authority complete first. ART and
CHECKERS then materialize, execute, persist, and expose the exact current
post-submit result. Only after that merged manifest may REV activate admission
for the Submission. Independent REV schema/packet foundations may proceed
earlier. CON validates policy at guide activation and at a controlled human
revision rebase, then participates in every final decision. Ordinary task and
review claims only copy locked lineage; CON is not downstream-only. The admission-only public API clean
cut remains later still, after initial, checker-remediation, and
reviewer-requested revision contexts all use the same path.

## D14: ContributionPolicy is the sole award-governing policy

CON owns `ContributionPolicy` and immutable `ContributionPolicyVersion`.
`CompensationAward` is an evaluation result, not a policy. PLAN2 uses only the
exact frozen submitter and reviewer ContributionPolicyVersion references. All
retired economic-policy vocabulary and fields are removal debt for the owning
clean-cut chunks before public release; they are not authority and receive no
compatibility alias or fallback.

## D15: ContributionPolicy cutover is registration-behavior-activation

Adapter-binding and ContributionPolicy capabilities follow separate AUTH
registration -> hidden CON behavior -> exact AUTH activation sequences. Future
fulfillment callback authority is not a prerequisite and cannot be inherited.

## D16: Aggregate owners persist policy lineage

CON validates and returns immutable policy-version facts. PROJECTS alone binds
the version to ProjectGuide. TASKS alone locks it on Task, copies it to
TaskAssignment, and stamps it on Submission. ReviewLease later copies only the
Submission stamp. No product service imports another module's model or
repository to perform those writes.

## D17: v0.1 removal is clean, not compatible

The consolidated baseline is the current schema authority. The retired
guide-bound economic path is removed only after canonical lineage is live, with
no alias, fallback, dual read/write, guessed conversion, or historical backfill
unless future discovery proves an actual deployed-data obligation.

## D18: Debt retirement follows delivery without blocking unrelated work

New architectural and test debt is prohibited. A capability change removes the
existing debt it directly exercises, but unrelated frozen debt is not a merge
prerequisite. When safe removal would enlarge the approved product or safety
boundary, the exact stranded debt is recorded for a later owner-sized closure
chunk and cannot grow in the meantime. Repository-wide cleanup, arbitrary
per-PR quotas, and cosmetic test splitting are rejected.

WS-ARCH-001 remains the general boundary owner, WS-AUTH-003 remains the AUTH
boundary and structural-debt owner, and WS-QUAL-002 remains the behavior/test
ownership authority. Their ledgers are reported independently where their
measurements overlap.

## D19: Adapter-binding lifecycle truth is CON-owned and authorization remains AUTH-owned

CON owns typed binding commands/results, the active/suspended state machine,
canonical row locking, and immutable created/suspended/resumed lifecycle
events. AUTH owns Finance Authority, action availability, opaque PREP handles,
authorization decisions, and decision evidence. Read uses request-scoped
authorization; create/suspend/resume use one domain-specific opaque
prepare/consume/close port backed by AUTH only in CP03B. CP03A owns the exact
adapter target identity and PROJECTS/ACTORS eligibility prerequisite. CON never
imports AUTH internals or translates the CON-owned `instrument_type` value.
