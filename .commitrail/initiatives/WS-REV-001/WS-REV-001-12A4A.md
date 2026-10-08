# REV-12A4A — Scoped first-contribution lifecycle control

- Initiative: `WS-REV-001`
- Durable disposition: `Planned`
- Risk: L1 — Operator authority, lifecycle concurrency and immutable evidence.
- Intended merge outcome: the existing lifecycle controller has an authorized,
  generation-bound transition operation for the first contribution path. This
  does not enable production routing, human review or payment delivery.

## Intent and human decision

The first contributor milestone needs one usable lifecycle generation before
false-policy acceptance can be composed. The canonical lifecycle specification
previously made fulfillment-obligation roots, ordinals and shutdown cutoffs a
prerequisite even while the milestone deferred fulfillment. The user explicitly
selected: keep payment delivery deferred and scope the controller to the first
contribution path. Conditional award facts remain atomic with contributions;
paid projects are not silently excluded. Obligation admission, dispatch and
callbacks remain unavailable until their own successor manifest and proofs.

This extends REV-12A1's controller and the existing
`review.lifecycle.activation.manage` Operator action. It introduces no second
availability switch, bootstrap SQL, provider, generic drain framework or
compatibility path. Exact routing AUTH receipts and complete atomic consequences
remain the subsequent ARCH-04E2-B prerequisite before a production consumer.

## Plan

1. Reconcile canonical lifecycle/compensation specifications and the current
   first-layer sequence with the selected scope. Preserve the four phases and
   the future obligation writer/cutoff requirements before fulfillment activation.
2. Extend the singleton with immutable transition history and exact operation
   replay. REV owns legal edges: disabled -> shadow -> live -> draining ->
   disabled, plus shadow -> disabled. Each successful transition increments the
   generation. Database time governs deadlines. No transition seeds an allow.
3. Use existing AUTH PREP with live system Operator authority before the REV
   advisory/controller lock. Bind the exact singleton, operation, expected
   generation, source/target phases, request, manifest and server observations.
   AUTH consumes after locked validation; history and controller change commit
   with its immutable decision in the caller's root transaction. Commit-time
   closure requires exactly one N/P -> N+1/Q update, history row and matching
   AUTH action/system target/resource digest/actor/grant receipt. Replay acquires
   the same lock and looks up operation history before applying original
   generation/deadline as new-effect guards. It requires the unchanged request
   and receipt plus fresh same-actor live system Operator authority, with no
   controller/history/audit mutation. Changed collisions deny. Bigint overflow
   denies rather than wrapping the generation.
4. A fixed reviewed manifest describes the actual bounded participants. The
   initial LIVE readiness check refuses any retained pre-authority FinalAcceptance
   rows: mechanical storage cannot establish the missing originating receipt.
   This is a real persisted observation, not an invented completeness claim.
   No data is deleted or repaired. ARCH-04E2-B must add exact source custody and
   update this evaluator before consuming retained facts in production.
   Composition/inventory tests prove absent routing, human and fulfillment
   registrations, rather than presenting their absence as runtime zero counts.
   Atomic acceptance writers retain the existing advisory lock through commit,
   so obtaining it fences earlier writers. No acceptance lease or asynchronous
   acceptance queue is invented to drain.
5. New effects through the existing REV/TASK/CON participants require a live,
   nonzero current generation. Consumer fence ports expose typed phase/generation
   facts; owners derive new/replay from locked persisted state, then gate only
   new effects. Keep exact verified terminal replay read-only
   after shutdown using the current controller generation as its fence precondition,
   with unchanged stored source/effect identities. Reuse existing select-only
   participant replay branches; do not add a parallel replay implementation. A
   stale generation denies. Award-free replay cannot attest a correlation value
   that was never persisted. A future manifest
   enabling asynchronous routing or fulfillment must add its actual drain proof
   before activation.

## Allowed files

- REV `backend/app/modules/reviews/api/lifecycle.py`,
  `lifecycle/{models,fence,service}.py`, and `acceptance/participant.py`.
- Existing TASK accepted-effects and CON participation owner modules and their
  consumer-owned typed fence ports; no private cross-owner SQL/imports.
- AUTH `review_contracts.py`, `catalogue.py`, `kernel.py`, `prepared.py`, runtime
  resource/digest/audit contracts, and focused lifecycle resource/PREP adapter
  modules. Existing composition roots only for explicit controller construction.
- One successor Alembic migration, model registration, exact schema inventory;
  focused REV lifecycle and AUTH tests plus affected acceptance/participation
  tests and shared fixtures. Existing production inventory tests prove absent
  surfaces; do not create a parallel registry.
- Exact behavior ownership and lane inventory files/tests; no CI gate changes.
- This record; REV/AUTH/CON/ARCH/POL current overviews, ARCH/AUTH/POL current
  plans/maps, Commitrail index; canonical review/compensation specifications,
  relevant authorization custody docs, README and roadmap. Local roadmap exports
  only if present. Historical completed records remain historical.

## Prohibited

No fulfillment obligation/root/counter/ordinal/cutoff storage; payment admission,
dispatch or callback; production routing handler registration; public acceptance,
human queue/decision/revision runtime; new role/action/controller; invented Review;
retained-data deletion or rewriting; default permissive generation; generic
service locator; timeout/completeness/boundary weakening; unrelated cleanup.

## Acceptance and verification

- Real PostgreSQL and real AUTH prove the allowed edges, exact grant provenance,
  revocation, wrong actor/scope, stale generation, expired deadline, request and
  manifest substitution, operation collision and response-loss replay.
- Direct SQL cannot mutate/delete history, skip a generation, change phases
  without the exact authorized history, substitute receipts or shadow protected
  controller/history tables. This is not a claim of database LIVE guards on
  mechanical acceptance storage. Retained controller identity/genesis and
  existing records survive.
- Independent sessions prove writer-first and transition-first ordering through
  actual participant writes; rollback removes state/history/AUTH effects together.
  Managed and raw savepoints remain rejected by the canonical root fence.
- New participant effects fail in disabled/shadow/draining and at generation zero.
  Mechanically composed live paid and unpaid controls preserve exact contribution and complete award
  facts. Verified replay during draining/disabled performs no inserts or updates.
- The initial manifest refuses pre-authority retained acceptance facts before
  LIVE (including reactivation) and unsupported enabled surfaces.
  Fulfillment and routing registration remain unavailable. Shutdown does not
  claim to cancel jobs or drain owners absent from this bounded manifest.
- Guard-removal probes must fail at the relevant phase/authority/history assertion,
  not an unrelated fixture or digest guard. Retain existing meaningful proofs.
- Run focused PostgreSQL suites, lint, module boundaries, ownership/inventory,
  links, stale wording, Commitrail and diff checks, then exact-head hosted CI.

## Review and human focus

Plan review before implementation; architecture/reuse, security, QA/test delta,
documentation/product operations and CI integrity review the clean candidate.
Review whether this stays the same controller/action, keeps contribution/award
facts atomic, and cannot enable payment or human runtime. Controller permission
is not routing or acceptance authority. Scope and phase history must be verifiable
without relying on receipt-shaped caller values or misleading drain counts.
