# ARCH-04E1B-B8 — Hidden evaluation completion delivery

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Risk: L1 — delivery custody, authorization, transaction completion and replay.
- Intended merge outcome: one unregistered completion handler invokes the existing
  authorized outcome operation and acknowledges only its committed result.

## Intent

Complete the remaining 04E1B-B delivery connection in the
[first contributor milestone](planning/PLAN.md#first-complete-contributor-milestone).
B7 recovers and executes the initial checker request. Merged 04E2-B owns exact
routing authority, source publication, true human-review handoff or false shared
acceptance with contribution/award facts. Its caller still owns commit, and no
completion handler connects its result to shared delivery acknowledgment.

Reuse that operation and the shared outbox. No second dispatcher, acceptance
operation, request store, retry engine or delivery state is needed. Replace the
operation's dictionary return with the strict frozen TASK-owned result required
by 04E2-B's review disposition before adding its first consumer.

## Bounded change

1. TASK returns a closed immutable outcome value containing exact project, task,
   Submission and completion-event identities, routing manifest, actual authority
   and outcome-event IDs, optional acceptance/economic identities, and replay
   disposition. Enforce coherent human/economic shape and update every affected
   caller/test; retain no mapping compatibility API.
2. The hidden completion handler validates the envelope and closed CHECKERS
   completion shape and checks independently committed invocation before owner
   access. Wrong event/version/aggregate/project and non-success recommendations
   reject before effects. Payload identifiers remain selectors, never authority.
   Remediation and setup-blocked outcomes are not handled as success.
3. Delivery obtains the expected lifecycle generation from server-owned context,
   never from broker payload or a runtime constant. Reuse the exact-project
   locked-review-policy observation and a narrow REV-owned generation observation
   only for the false branch. REV observation is phase-agnostic and may return
   generation zero or a stopped generation; only the existing fenced operation
   decides eligibility. These observations acquire no mutation locks and
   grant no authority. The existing outcome operation revalidates branch and exact
   generation under its REV-before-TASK custody; true never touches REV/CON.
   Implement `TaskPostSubmitOutcome.observe_delivery_generation(envelope)`
   using the same extracted review-mode helper as `apply`; false delegates
   `RoutingAcceptancePort.observe_generation()` through the existing adapter and
   REV acceptance participant to its fence owner. Preserve explicit
   expected-generation semantics and all existing stale,
   stopped-replay and generation-zero proofs.
4. Open one owned root transaction, invoke the existing outcome, validate its
   exact typed result against the completion, then leave the transaction context
   successfully before returning ACKNOWLEDGE. The outcome remains flush-only.
   Invalid result, deferred constraint failure, commit failure or cancellation
   must not acknowledge. Exceptions after entering the effect operation propagate
   to shared UNKNOWN handling; never invent RETRY for uncertain effects.
5. Exact duplicate invocation while its claim remains current and unfinalized after a committed outcome rechecks live router
   authority and retained custody, then returns retained identities without new
   effects. Invocation expiry/finalization, stale completion or revoked authority
   cannot bypass the existing operation. Shared delivery owns finalization and
   recovery; no automatic replay of an UNKNOWN effect is introduced.
6. Add explicit composition beside the existing TASK request/outcome factories.
   Keep both completion and request handlers absent from production registration.

## Allowed files

- TASK `api/routing_outcome.py`, `post_submit_routing/{outcome,ports}.py`, and
  cohesive `evaluation_completion_delivery.py`; existing TASK composition in
  `app/adapters/tasks/__init__.py` and `routing_acceptance.py`.
- REV `api/acceptance.py`, `acceptance/participant.py` and `lifecycle/fence.py`
  only for the bounded owner generation observation through the existing public
  acceptance port and TASK acceptance adapter; no controller transition, fence ordering,
  permission or activation change.
- Existing affected routing/acceptance/contribution/lifecycle tests and fixtures
  only for typed-result migration; focused completion-delivery contract,
  PostgreSQL/AUTH, shared-outbox, rollback and race tests under TASK tests.
- Required behavior-ownership/lane inventories and their exact tests. No CI gate
  change. Existing boundary registries only if the actual owner seam requires it.
- This record; affected current ARCH/AUTH/POL/REV/CON overview/map/plan/index,
  canonical TASK/checker/authorization/lifecycle/artifact/compensation specs,
  architecture lockdown, product brief, authorization custody docs, README, operator docs and
  roadmap. Local roadmap spreadsheet exports only if present.

## Prohibited changes

No migration or new persisted state, new public endpoint, production handler
registration, false-guide activation, live human review/revision, remediation
implementation, external checker runtime, payment delivery, contributor leases,
compatibility path, weakened tests/gates or retained-data modification/deletion.
Do not repeat completed initial-dispatch work or broaden fixed-service authority.

## Acceptance criteria

- Pure result tests reject incoherent economics, wrong scalar/extra fields and
  mutation; the handler revalidates constructed/copied instances before commit.
- Real PostgreSQL/AUTH/shared delivery commits true handoff and false acceptance,
  both unpaid and applicable awards, before ACK. No fabricated Review/reviewer
  contribution. Pause after the final staged outcome write: the handler has not
  returned and an independent session sees no outcome. Release, then require ACK
  and complete committed facts. Use unpaid and one both-awards representative;
  retain existing detailed award-shape tests. True proof forbids REV observation.
- Corrupt the real operation's typed return after valid staging; handler revalidation
  must fail before commit and preserve the full pre-operation snapshot.
- Lost acknowledgment followed by same invoked-envelope replay returns exact
  retained outcome with unchanged source, audit, contribution/award and notice
  rows; retain the existing fresh-router-revocation proof. A finalized invocation rejects.
- Intrinsic malformed/crossed envelopes and absent/finalized observations return
  REJECT before owner entry. Retain the existing real stored-source substitution
  matrix at the canonical owner so observer digest checks cannot mask it. Once
  outcome entry begins, foreign retained lineage, stale generation, revoked
  authority, malformed result or commit errors propagate to shared UNKNOWN.
  A valid foreign envelope is processable for its own project, not inherently invalid.
- A real deferred database constraint failure at transaction exit prevents ACK
  and rolls back the staged outcome, AUTH, audit and economic effects. Cancellation
  before commit likewise rolls back. A failure after actual commit remains UNKNOWN
  and never authorizes automatic uncertain-effect retry. Once shared delivery
  finalizes UNKNOWN, its old invocation is closed: reject direct reinvocation and
  prove duplicate transport creates no effects. Exact replay proof applies only
  while the original invoked claim remains current and unfinalized.
- Independent PostgreSQL sessions prove generation observation followed by a
  controller transition cannot use stale authority, and invocation finalization
  at the intermediate wait cannot commit an unfenced outcome. Retain existing
  outcome lock-order/currentness races rather than duplicating them mechanically.
- Production registry absence remains asserted. Shared delivery is exercised
  through its actual handler invocation and finalization; live broker transport
  is not claimed by this hidden integration.
- Each new regression includes a valid control reaching the intended boundary.
  Deliberate guard/order removal must fail its behavior assertion, not fixture
  setup. Run focused proofs, deterministic boundaries/docs checks, then complete
  hosted suite with zero skip/deselection and real PostgreSQL/MinIO cleanup.

## Risk and review routing

Required plan review before implementation; implementation tracks: architecture/
reuse, security, QA/test-delta, CI integrity, docs/product operations. Freeze a
clean target and distinguish compatible runtime proof from final hosted status.
Human focus: ACK after commit, UNKNOWN after uncertainty, exact source selection,
fresh authority, true-branch independence and bounded false generation selection.

## Next boundary

After hidden completion delivery: checker remediation 04F, connected production
readiness/false-guide activation 04E3, public intake and the real first-layer drill.
This chunk alone does not make the contributor path publicly usable.

## Evidence

The named proofs protect the implemented boundaries. Owner symbols are existing
operations unless explicitly introduced by this record; current execution and
review results belong in the PR.

| Behavior and owner | Proof |
| --- | --- |
| Strict `TaskRoutingOutcome` and handler result validation | `backend/tests/tasks/evaluation_delivery/test_completion_contracts.py::test_result_is_closed_and_immutable`; `test_result_binds_branch_and_completion` |
| `EvaluationCompletionHandler` true branch, commit before ACK and no REV | `backend/tests/tasks/evaluation_delivery/test_completion.py::test_completion_handler_true_commits_before_ack_without_rev` |
| Shared false `TaskPostSubmitOutcome.apply` with unpaid and award-bearing policy | `backend/tests/tasks/evaluation_delivery/test_completion.py::test_completion_handler_false_commits_acceptance_before_ack` |
| Live invocation exact replay and fresh router AUTH | `backend/tests/tasks/evaluation_delivery/test_completion.py::test_completion_handler_committed_replay_is_exact` |
| Commit exits through actual deferred outcome guard | `backend/tests/tasks/evaluation_delivery/test_completion_custody.py::test_completion_handler_deferred_constraint_failure_never_acknowledges` |
| Shared dispatcher UNKNOWN after a real commit; no repeated effect | `backend/tests/tasks/evaluation_delivery/test_completion_custody.py::test_completion_handler_response_loss_is_unknown_without_duplicate_effects` |
| Cancellation while staged but uncommitted | `backend/tests/tasks/evaluation_delivery/test_completion_custody.py::test_completion_handler_cancellation_rolls_back` |
| Intrinsic malformed/non-success completion and production absence | `backend/tests/tasks/evaluation_delivery/test_completion_contracts.py::test_completion_handler_rejects_crossed_or_non_success_completion`; `backend/tests/tasks/evaluation_delivery/test_completion.py::test_completion_handler_is_absent_from_production_registry` |
| REV observation then intervening actual transition | `backend/tests/tasks/evaluation_delivery/test_completion_custody.py::test_completion_handler_stale_observed_generation_cannot_commit` |
| Actual outbox finalization at intermediate handler wait | `backend/tests/tasks/evaluation_delivery/test_completion_custody.py::test_completion_handler_finalized_invocation_cannot_commit` |

Plan review refinements: the generation observation stays behind the REV public
acceptance port. Returning a closed result does not assert commit; only handler
transaction exit establishes acknowledgment eligibility. Loss before outbox
finalization and a finalized UNKNOWN are distinct recovery cases.

Additional proof: `test_completion_custody.py::test_completion_handler_invalid_result_rolls_back` exercises corrupted typed results after real staging. Retain `test_mixed_stored_sources_reject_without_effects` for canonical stored-source isolation; do not substitute observer rejection. The handler finalization race pauses after its independent observation and before outcome entry, distinct from existing outcome-level races. UNKNOWN assertions inspect delivery attempts and finalization alongside outcome snapshots.


## Implemented boundary

The TASK handler uses the existing outcome transaction and revalidates the closed
result before commit. REV exposes only a phase-agnostic generation observation;
existing fenced preparation remains authoritative. The provisional dictionary
return and affected mapping callers are replaced, without aliases. Current
navigation advances to remediation. No migration, production registration,
public route or dependency is added. Local spreadsheet exports are absent.

Plan review resolved disposition ambiguity and strengthened the proof to pause
before commit, corrupt results after staging, distinguish active replay from
closed UNKNOWN, and retain the existing stored-source isolation matrix.

Review corrections preserve the accepted-effects and acceptance-rollback source
guard tests while replacing all nine remaining mapping accesses with typed
attributes. Current capability documents distinguish delivered hidden completion
delivery from unavailable production registration and public intake.
