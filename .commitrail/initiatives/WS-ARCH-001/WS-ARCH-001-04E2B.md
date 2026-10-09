# WS-ARCH-001-04E2B — Commit authorized post-submit outcomes

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: One hidden callable operation commits exact routing
  authority with its full governed outcome; completion delivery and production
  registration remain separate consumers.

## Intent

Close group 1's authorization/effect gap on the first contribution journey.
Passing required checks under locked false policy must produce FinalAcceptance,
accepted TASK/completed assignment, the submitter ContributionRecord and the
complete applicable award set atomically. Locked true retains its independent
TASK human-review handoff without a REV queue or invented Review. Preparation
alone must never be acknowledged as a completed outcome.

B4/B5/B6/B7 and REV-12A4A are delivered foundations, not public end-to-end
readiness. This record also carries the reviewed current-plan reconciliation:
five remaining groups, authorized outcomes before completion delivery, and no
repeated initial-dispatch work. It supersedes the local planning-only record;
no separate planning PR or new prerequisite is introduced.

## Current behavior

TASK `post_submit_routing/source.py` and `requests.py` retain exact current
source proposals and a stable request/manifest identity. AUTH
`post_submit_routing_authorization.py` prepares a planned/unavailable action.
REV `acceptance/participant.py` composes TASK and CON under the existing fence
but lacks mandatory source AUTH custody. Existing positive acceptance fixtures
are mechanical human-source proof, not genuine acceptance authorization.

AUTH currently requires `TaskPostSubmitManifestFacts.created_at` before source
publication, although the INSERT guard owns that timestamp. False consequence
also omits lifecycle generation. Both gaps must be corrected in the same
canonical contracts before activating the exact operation.

## Bounded change

### Allowed

- Existing TASK `api/post_submit_routing.py`, owner-local `post_submit_routing/`
  request/source/models and cohesive outcome/consumer-port files; affected
  `repository.py` and `accepted_effects.py` only for exact outcome/replay custody.
- Existing AUTH `api/acceptance_source.py`, `acceptance_source_contracts.py`,
  `post_submit_routing_authorization.py`, `domain/post_submit_routing.py`,
  canonical catalogue/parity/resource/audit/PREP matching and exact replay paths.
  No alternate authorization service.
- REV `api/acceptance.py`, `acceptance/{models,repository,participant}.py`, and
  existing lifecycle service/manifest readiness only where mandatory source
  custody changes its retained-source validation. Existing fence is reused.
- ART `post_submit_materialization.py` and CHECKERS `api/materialization.py`,
  `api/execution.py`, execution/coordinator/models plus their focused material
  custody tests, only to retain the actual input-materialization decision that
  the current result discards. Reuse B6 creation/binding receipts; no reverse
  audit search or borrowed phase receipt. Keep pre-consumption material facts
  distinct from the post-consumption receipt, without a compatibility default.
- Existing TASK/REV/CON typed participants and explicit `app/adapters/` roots;
  shared AUDIT/outbox append participants and bounded outcome event contracts.
- One successor migration after 0028, model registration if necessary, Alembic
  preflight/head inventory and measured schema reset fingerprint.
- Focused AUTH routing/source, TASK routing, REV acceptance/lifecycle and CON
  participation tests and their affected fixtures; migration/storage/replay,
  branch and concurrency regressions; required ownership/lane inventories only.
- This record, current ARCH plan/map/overview and active 04E child, index,
  affected AUTH/REV/CON current navigation and canonical specs, README and
  roadmap. Update local XLSX/CSV only if present.

### Not allowed

No completion handler or production registration, public route, false-guide
activation, human decision/queue/revision runtime, contributor lease timers,
fulfillment/payment delivery, new service/action/role/dispatcher/source store,
compatibility receipt or retained-data rewrite/deletion. No weakened gates,
skips, coverage quotas or replacement of required proof with permissive mocks.

## Design

- Reuse one TASK outcome operation and explicit composition root; existing owners
  remain sole writers. Consumer-owned ports/adapters prevent TASK/REV/AUTH cycles.
  The caller-owned root transaction contains all writes; only the transaction
  root commits. The return value is not an outbox acknowledgment.
- Observe the locked-policy branch through a bounded nonlocking TASK read before
  locks, then revalidate exact lineage under mutation custody. False acquires
  REV-12A4A before TASK/Assignment/Submission, PROJECTS and CHECKERS, then AUTH;
  true never acquires REV/CON. Retain exact outbox invocation custody through
  commit using the existing port. Prove actual interleavings, not just order lists.
- Prepare/consume AUTH over `TaskPostSubmitSourceProposal`; keep persisted
  `ManifestFacts` for stored reads. One canonical semantic digest excludes only
  database-created time. Never invent a timestamp or publish a receipt-less row.
- Bind the original authorized false lifecycle generation in the strict
  consequence and resource digest. New acceptance requires that exact current
  LIVE generation. Terminal replay separately acquires the current controller
  generation, verifies the original receipt with its stored authorized generation,
  and proves complete replay disposition before allowing those generations to
  differ. Current generation never authorizes new effects with an old receipt.
  Reuse canonical fixed-router PREP and fresh-authority replay; only the existing
  `task.post_submit.route` action becomes executable internally.
- Extend the existing manifest with mandatory actual immutable decision-event
  custody and the exact reconstructible authority context. Harden the same
  FinalAcceptance input/row with a mandatory same-source decision reference.
  Detached receipts remain untrusted until AUTH verifies the retained event.
- Source publication binds distinct original Submission creation/binding,
  input-materialization, execute/finalize and routing decisions from their
  canonical retained owners. Propagate the materialization decision through
  its existing result/finalization custody; a material-bearing terminal result
  cannot support routing without it. No-material infrastructure outcomes do
  not fabricate a materialization receipt.
- Refuse upgrade with retained pre-authority manifests/acceptances unchanged.
  SQL independently verifies exact service/link/action/permission, project,
  request/source/claim/consequence and generation, using schema-qualified tables
  and safe function search paths. No NULL/default compatibility path.
- Deferred database closure rejects a standalone routing allow, incomplete or
  crossed manifest/outcome, missing TASK/assignment/contribution/award members,
  and missing shared audit/outbox consequence. A constructed, not-invoked,
  expired, finalized or foreign outbox claim cannot produce an outcome;
  the callable operation uses actual committed invocation custody. Reuse existing award-set guard;
  do not implement a second compensation evaluator.
- Exact replay verifies the original complete tuple with fresh authority,
  returning its original IDs without new receipts/events/effects. Partial
  retained effects are errors, never repaired by replay. Stopped false replay
  follows the existing controller generation contract without new acceptance.

## Acceptance criteria

- Real AUTH and PostgreSQL commit each exact true/false outcome, with paid zero,
  one and two applicable award sets as governed. False creates no Review or
  reviewer contribution; true creates no acceptance or CON effects.
- Cross-project and mixed valid-record selections, wrong receipt/source/claim,
  altered consequence/generation and revoked principal deny with no effects.
- Direct SQL cannot commit partial or mismatched outcomes or an orphan allow;
  safe-path controls succeed. Retained data is preserved on refused migration.
- Rollback after each participant including audit/outbox leaves no partial
  outcome. Duplicate/restarted delivery preparation can invoke select-only
  replay, without executing a handler in this PR.
- PostgreSQL tests observe branch revalidation and actual intermediate waits for
  REV/TASK/AUTH, acceptance/successor and outbox custody races in both orders.
- Replace obsolete receipt-less acceptance positives with real authorized false
  outcomes while retaining their distinct lineage, rollback and immutability
  proof. Human runtime stays unavailable; do not fabricate allowed AUTH events.
- Clearly scoped test setup may seed otherwise unreachable, internally valid
  false guide lineage; routing authority/effects must use real owners. This does
  not establish public false-guide activation or first-layer readiness.

## Risk and review routing

Risk: L1, cohesive multi-owner atomic authorization outcome. The migration,
source/effect custody and affected fixture replacements may exceed the preferred
500-line guide because splitting a genuine allow from its mandatory consequence
would permit incomplete commits. Keep modules cohesive and scope bounded.
Required reviewers: architecture/reuse, security, QA/test-delta, CI integrity and
substantive docs/product-ops. Human focus: exact source authority, complete
transaction/database closure, lock order and truthful hidden-versus-live scope.

## Evidence

Before implementation: inspect existing owner seams and review this contract.
During implementation: focused pure contract tests and real PostgreSQL outcome,
SQL guard, migration, rollback and concurrency tests. Each reproduced defect
needs a discriminating guard-removal or pre-fix failure, not just a happy path.
Verify all affected tests, module/AUTH boundaries, ownership/lane catalogue,
lint, links, current wording and Commitrail; full hosted suite remains required.
No percentage gate. Real storage/broker first-layer drill remains group 5;
this operation does not claim production delivery.

## Reconciliation

Base is merged #516/#517. Carry the reviewed five-group plan correction in this
product PR. After this operation, complete hidden completion delivery, then
remediation, live composition, public intake and the real drill. Default-true
review policy stays independent; human runtime and payment delivery stay deferred.
