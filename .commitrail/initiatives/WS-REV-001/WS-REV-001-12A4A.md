# REV-12A4A — Scoped first-contribution lifecycle control

- Initiative: `WS-REV-001`
- Durable disposition: `Complete`
- Risk: L1 — Operator authority, lifecycle concurrency and immutable evidence.
- Intended merge outcome: the existing lifecycle controller has an authorized,
  generation-bound transition operation for the first contribution path. This
  does not enable production routing, human review or payment delivery.

## Intent

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

## Bounded change

1. Reconcile canonical lifecycle/compensation specifications and the current
   first-layer sequence with the selected scope. Preserve the four phases and
   the future obligation writer/cutoff requirements before fulfillment activation.
2. Extend the singleton with immutable transition history and exact operation
   replay. REV owns legal edges: disabled -> shadow -> live -> draining ->
   disabled, plus shadow -> disabled. Each successful transition increments the
   generation. Database time governs deadlines. No transition seeds an allow.
3. Acquire the REV advisory/controller fence before existing AUTH PREP obtains
   live system Operator authority. This respects acceptance REV -> TASK and
   task-read TASK -> AUTH custody; transitions never retain AUTH while waiting
   for REV. The fence is mechanical serialization, not permission to change state. Bind the exact singleton, operation, expected
   generation, source/target phases, request, manifest and server observations.
   For this action only, AUTH locks the actor profile FOR NO KEY UPDATE, retaining
   link/grant FOR UPDATE: actor foreign-key reads may complete under a prior REV
   writer, while actor status changes/revocation still serialize.
   Refresh the ORM controller from locked database state before assigning the
   successor, even when the caller previously cached it.
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
  `repository.py` for lifecycle-only actor NO KEY UPDATE custody,
  resource/digest/audit contracts, `backend/app/modules/audit/schemas.py` for the
  exact UUID lifecycle target kind, and focused lifecycle resource/PREP adapter
  modules, including `prepared_admin_authority.py` for existing admin lock orchestration
  and existing `domain/{guide_mutations,prepared_guide_mutations}.py` for shared
  review/revision lineage validation and binding. Existing composition roots only for explicit controller construction.
- One successor Alembic migration, current-head preflight and graph inventory, model registration, exact schema inventory;
  focused REV lifecycle and AUTH tests plus affected acceptance/participation
  tests and shared fixtures. Existing production inventory tests prove absent
  surfaces; do not create a parallel registry.
- Exact behavior ownership and lane inventory files/tests; shrink affected frozen AUTH structural debt through cohesive owner extraction, then refresh fingerprints without adding debt or relaxing limits. No CI gate changes.
- This record; REV/AUTH/CON/ARCH/POL current overviews, the CLI current overview
  for merged guide-format consistency, ARCH/AUTH/POL current
  plans/maps, Commitrail index; canonical review/compensation specifications,
  relevant authorization custody, operations and roles/permissions docs, canonical authorization/data-model specifications, README and roadmap. Local roadmap exports
  only if present. Historical completed records remain historical.

## Prohibited

No fulfillment obligation/root/counter/ordinal/cutoff storage; payment admission,
dispatch or callback; production routing handler registration; public acceptance,
human queue/decision/revision runtime; new role/action/controller; invented Review;
retained-data deletion or rewriting; default permissive generation; generic
service locator; timeout/completeness/boundary weakening; unrelated cleanup.

## Acceptance criteria

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
  A three-session read/acceptance/transition regression must observe acceptance
  waiting on TASK and transition waiting on REV before resuming the reader.
  A cached controller must accept a valid command after another transaction advances it.
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

## Risk and review routing

Plan review before implementation; architecture/reuse, security, QA/test delta,
documentation/product operations and CI integrity review the clean candidate.
Review whether this stays the same controller/action, keeps contribution/award
facts atomic, and cannot enable payment or human runtime. Controller permission
is not routing or acceptance authority. Scope and phase history must be verifiable
without relying on receipt-shaped caller values or misleading drain counts.

## Evidence

This L1 change exceeds the preferred 500-line guideline because the same
transition must bind AUTH, REV storage and all three existing participant gates
atomically. Splitting those gates would temporarily preserve permissive
acceptance writers. Most additional paths are existing consumer fixtures,
required ownership/lane inventories and current documentation; no independent
product feature is included.

The existing `test_production_registry_claims_only_registered_invalidation`
(`tests/outbox/test_worker_postgresql.py`) remains the exact production-registry
proof; `test_observed_task_inventory_matches_every_registered_workstream_task`
retains worker inventory coverage. Existing review catalogue tests now allow
only the scoped controller action and keep other review actions planned. These
composition checks are not represented as runtime drain observations. Full-suite
execution remains required; partial local batches are not completeness evidence.

Review repairs retain the canonical append-only audit guard: direct PostgreSQL
receipt-edit and unrelated-event transformation tests reject through that owner,
so no duplicate immutability trigger is added. New transition closure independently
checks active actor, exact link and Operator grant. Owner-specific phase probes
avoid sibling guards masking each other. Reset proof begins at authorized LIVE
and preserves singleton identity/time while restoring only the isolated test DB.

PostgreSQL stamps transition history time independently of caller input; an expired
command with an explicitly backdated timestamp rejects and rolls back all three
owners. This closes deadline custody without trusting application timestamps.

The stopped-new-effect integration proof shares one source across sequential
`draining`, `disabled` and `shadow` transitions. Each denial uses a fresh caller
transaction and must preserve the original effect snapshot. This removes two
redundant graph setups while retaining all phase assertions and the separate
owner-isolation proofs. Hosted evidence also exposed inadequate TASK-lane
capacity. The whole lifecycle-participant module therefore runs beside the
existing acceptance and contribution participant modules in the three project
partitions, which have measured headroom. Exact node ownership/completeness is
retained; no execution limit is relaxed.

External review reproduced a three-transaction cycle through actual task detail,
acceptance and transition owners, plus an ORM update that omitted the phase after
another session committed a transition. The repair orders the controller fence
before authority custody and refreshes the locked controller before mutation.
The regressions fail against the prior ordering and cached update at their actual
PostgreSQL boundaries; the prior two-session proof remains required. No runtime
activation or capability scope changes follow from these repairs.

Current planned review claim/decision and compensation choreography also obeys
REV-before-TASK-before-AUTH custody, with TASK before CHECKERS currentness. Their
exact idempotency, queue, lease and dependent-row order still requires the owning
runtime chunk's PostgreSQL proof before activation; this correction activates
none of those surfaces. Historical pre-cutover records remain unchanged.

Main's Markdown guide-media migration owns revision 0027. This unmerged lifecycle
migration follows it as 0028, preserving both invariants in one linear history.
The schema fingerprint is measured from their combined PostgreSQL catalog, and
the upgrade-preservation proof begins at the merged Markdown predecessor.
