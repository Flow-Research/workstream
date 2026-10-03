# WS-ARCH-001-04E2A — Exact hidden routing authorization preparation

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: exact routing preparation and receipt-staging contracts
  extend canonical AUTH/PREP while `task.post_submit.route` remains unavailable.

## Intent

Continue the governed Submission-to-outcome sequence after request reservation.
Prepare the existing routing issuer for both locked ReviewPolicy branches without
publishing an early allow, source manifest, human admission or final acceptance.
False/pass remains the selected first complete runtime path; it invokes shared
acceptance without a fabricated Review or reviewer contribution. Submitter
claim leases and skip remain deferred.

## Current behavior

Main `176952e6` includes ARCH-04E1B-A. TASK reserves an immutable operation ID,
future manifest ID and exact completion selectors, with currentness and caller
root transaction custody. AUTH-19A supplies untrusted source/receipt DTOs and the
planned fixed router identity. AUTH/PREP's existing kernel rejects planned actions
before issuing any handle; direct service authorization also denies. The source
writer, full owner projection, mandatory receipt storage and atomic consequences
are not implemented. Those facts constrain this chunk's proof: a successful
value preparation is not an issued capability or persisted allowed decision.

## Bounded change

### Allowed

- This record and affected current ARCH/AUTH/POL/CON/REV navigation, coordination
  contract, `.commitrail/INDEX.md`, README, roadmap, canonical authorization and
  review specifications and authorization custody documentation.
- `backend/app/modules/authorization/domain/post_submit_routing.py`,
  `post_submit_routing_authorization.py` and existing `acceptance_source_contracts.py`;
  existing `api/acceptance_source.py` only if the existing receipt contract requires it.
- AUTH `prepared.py`, `runtime.py`, `domain/prepared_service.py`,
  `domain/resource_digest.py`, `domain/audit.py` and `domain/audit_targets.py`
  only for the exact routing action's typed extension; no persisted audit registry change.
- Existing TASK public request/source contracts if a concrete owner seam is
  missing; no TASK source writer or routing handler.
- `backend/tests/authorization/post_submit_routing/{test_contracts,test_prepared,support}.py`;
  existing `tests/test_authorization.py` and `tests/authorization/runtime_support.py`
  service-matrix fixtures,
  `tests/authorization/test_acceptance_source_contracts.py` and
  TASK `tests/tasks/post_submit_routing/{support,contract_fixtures}.py` only for reuse.
- Exact `backend/scripts/{behavior_ownership,test_lane_catalogue}.py`,
  `.ci/behavior-ownership/partition.v1.json`, `backend/tests/test_ci_lane_catalogue.py`
  inventory registration, plus `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`
  measured shrink refresh; no runner/workflow/cap/skip/threshold changes.

### Not allowed

No action availability change, new service identity/permission, hidden bypass,
production handler, public route, source insertion/current pointer, Review or
FinalAcceptance writer, contribution/award effect, schema migration, audit allow
registry activation, generic new preparation framework or compatibility path.
Do not modify observability, dependencies, application or Celery bootstrap in
this branch; the concurrent observability worktree owns those changes.

## Design and decisions

Reuse strict TASK request/source values and AUTH's canonical source commitment.
Reconcile every shared selector between request, future source and completion
claim; mismatched project, Submission/version, checker request/generation/result,
manifest identity, route operation/digest or policy branch must reject.
The exact resource distinguishes the true human-admission consequence from the
false shared-acceptance consequence, including its allocated acceptance identity.
No value or digest proves persisted ownership, live authority or currentness.
The prepare value contains the revalidated reserved request, including its
retained timestamp; semantic request/source digests keep their existing
timestamp exclusions. Do not redefine either TASK digest.

Extend existing AUTH/PREP binding and consumption seams rather than constructing
another capability. Retain planned-action rejection in the kernel and fixed
service matrix. Source projection/currentness supplied by future owner composition
must be validated under the same transaction and lock order before any eventual
consumption. The nominal receipt participant only projects after canonical PREP consumption
returns a real decision; it writes or commits nothing. This code is unreachable
while planned, with no alternate callable allow path. Source receipt shape is
derived from the exact context and canonical
source commitment; genuine immutable audit-event verification and mandatory
persisted receipt custody remain activation prerequisites, not an assumed fact.

Adding the routing binding must not enlarge existing structural debt. Keep the
unchanged setup-sufficiency binding parser behind a private helper so PREP's
`_binding` shrinks while retaining its existing request shape. Reuse one private
principal-context base for duplicated human/service principal and request fields
so `runtime.py` also shrinks while both concrete strict schemas, required fields
and literal principal kinds remain unchanged. Refresh only the measured debt
entries; do not change a gate or remove a test.

Preparation must not acquire TASK locks and then attempt to acquire fixed-service
locks. The future routing composition acquires its live service authority first,
then owner locks, and stages the eventual decision and consequences together.
Do not add a test-only activation switch or commit fabricated allows to obtain
positive pre-activation integration proof.

### Exact symbols and field custody

`PostSubmitRoutingResourceContext` is AUTH-private, strict, frozen and closed.
It contains `resource_type=task_post_submit_routing_manifest`, `resource_id`,
`scope_project_id`, `request: TaskRoutingRequestFacts`,
`source: TaskPostSubmitManifestFacts`, `claim: OutboxClaim`, and a closed
`consequence` union. It uses existing owner public DTOs rather than copied
request/source/claim shapes. `resource_id == request.routing_manifest_id ==
source.id`; scope equals all project identities including the claim. Match
request and source task, Submission/version, checker run, evaluation request,
evaluation request digest (source.request_digest), generation, result ID/digest,
completion event and literal allow_review. Claim event/project equals completion
and project. Claim lease/payload facts enter the resource digest but remain
untrusted until the future OUTBOX owner validates the stored invocation.

The source already contains assignment/contributor/contribution-policy identity,
exact guide/pre/post/review/revision lineage, artifact admission/binding/content/
replica/hash/size/semantic manifest, phase receipts and predecessor. Its locked
review policy ID/generation/hash and human_review_required boolean are bound.
Use `routing_source_commitment(source, route_operation_id, route_request_digest)`
and `acceptance_source_commitment_digest`, never another source-hash algorithm.

- `HumanAdmissionConsequence`: discriminator `kind=human_admission`,
  expected_task_status=evaluation_pending, target_task_status=review_pending.
  The resource's source/submission IDs identify exact publication/currentness.
  No queue/admission reservation IDs, acceptance IDs or accepted-effect fields.
- `AutomatedAcceptanceConsequence`: discriminator `kind=final_acceptance`,
  `task_effects: TaskAcceptedEffectsRequest`. Reuse its exact project/task/
  assignment/Submission/version/contributor/contribution-policy/content/hash,
  allocated final_acceptance_id and expected_task_status=evaluation_pending.
  The allocated acceptance identity must be UUIDv7, matching canonical storage.
  Require equality with the resource/source. Its intended target is accepted
  and completed assignment; it has no review_pending or queue fields.
  Future shared acceptance maps id=task_effects.final_acceptance_id,
  acceptance_source=task_post_submit_route, source_review_id=null,
  source_routing_manifest_id=source.id, accepted_submitter_id=source.contributor_id,
  policy_context_ref=source.locked_policy.locked_review_policy_id, and
  recorded_by=the AUTH-resolved fixed router profile. No REV private DTO import.

True requires exclusively HumanAdmissionConsequence; false requires exclusively
AutomatedAcceptanceConsequence. The exact false lifecycle fence, obligation
custody and contribution/award participant outcomes remain activation/composition
requirements; this value boundary does not assert them verified.

`post_submit_routing_prepare_values(request)` produces the single closed
routing_request field from the existing request DTO's JSON representation.
`parse_post_submit_routing_prepare` revalidates it and rejects extras.
`post_submit_routing_prepare_matches` checks exact request equality and final
resource validation; `_validate_consumption` additionally binds the existing
PREP caller idempotency, fixed context request ID and correlation ID to
request.route_operation_id. Requested project scope equals request.project_id.
The named new `_PreparedAuthorizationBinding.routing_request` field stores that
revalidated request. Route remains outside CHECKERS' POST_SUBMIT_ACTIONS.

`post_submit_routing_resource_digest` uses canonical_json_hash with domain
`workstream.authorization.task_post_submit_route.v0.1`, the exact routing
request/source commitments, full claim, branch consequence and resource scope.
Every semantic nested field participates; use canonical existing source/request
hashes rather than copying their field inventories. `authorization_resource_digest`
dispatches to it; runtime union, project-scope/resource matching,
`_scope_from_resource`, audit resource type and project audit target gain only
this typed resource. Audit database registry stays unchanged/unavailable.

`PostSubmitRoutingAuthorization.prepare(request)` is the nominal fixed router
adapter using the existing fixed_service_prepared_authorization and PREP service.
It cannot select a different identity or bypass availability. Its private prepared
participant calls canonical consume and only then projects the existing
AcceptanceSourceReceiptFacts. The projection checks allowed, revalidated,
FIXED_SERVICE kind, exact action/permission, resource type/manifest ID, canonical
resource digest and route-operation request/correlation/idempotency identities.
Project is checked through exact resource/source/claim scope (fixed-service
AuthorizationDecision intentionally has no matched project grant).
Actor profile and identity link come only from FixedServicePreparedAuthorization,
not caller-supplied UUIDs. No exported helper accepts arbitrary constructed
AuthorizationDecision values. Projection writes/commits nothing; no receipt can
be produced while the action is planned. A future consumer still verifies the
actual immutable AUTH event and exact fixed identity, never only this DTO.

## Acceptance criteria

1. Valid preparation values for both policy branches bind every exact request,
   source and consequence selector; independent substitutions reject or change
   the canonical commitment as appropriate.
2. Shared PREP matches the same action/project/request/operation and final facts;
   existing supported actions preserve behavior.
3. A real provisioned router still cannot obtain a prepared executable handle or
   commit an allowed decision through the planned action; unrelated service and
   human principals cannot substitute. Rejection leaves no source or product effect.
4. Receipt candidates are explicitly untrusted; mismatched issuer, request,
   resource or source commitment cannot be silently projected as the exact receipt.
5. Real caller rollback keeps the previously committed TASK request unchanged
   and leaves zero new audit/source/product effects. Planned denial occurs before
   TASK staging/locks; this is not a positive composed authority/owner-lock proof.
   Positive handle/receipt/lock-order/atomic-outcome execution is not reachable
   while planned and is not claimed: exercise value matchers with valid controls
   and prove actual PREP denial without fabricating an allowed decision.
6. Current navigation identifies the next usable CON-07/shared acceptance or
   hidden-handler prerequisite without claiming live routing or acceptance.

## Risk and review routing

- Risk class: L1, bounded authorization/architecture and workflow contract.
- Plan review: architecture and security, including fixture feasibility.
- Implementation reviews: architecture/reuse, security, QA/test delta,
  documentation/product operations, CI integrity for any proof inventory change.
- Human review focus: no early allow, no alternate issuer, exact source and
  request commitments, and both policy branches retained.

## Evidence

Named pure-test evidence in tests/authorization/post_submit_routing/test_contracts.py:
`test_valid_policy_branch_resources`, `test_each_request_source_selector_rejects`,
`test_exclusive_branch_consequences`, `test_each_consequence_identity_rejects`,
`test_prepare_parse_and_match_exact_request`, `test_digest_binds_claim_and_source`,
`test_fixed_principal_and_decision_receipt_checks`. Valid true/false controls are
strict values; false is transport/matcher proof only because false policy
activation remains unavailable. Do not call those values persisted/authorized.
`test_each_resource_and_claim_identity_rejects` independently substitutes all
six top-level manifest/scope and nested source/request/claim identities, with a
specific identity-error assertion. Removing the claim-project conjunct must fail
that assertion. `test_acceptance_identity_requires_uuid7` proves a valid allocated
control and rejection of a UUIDv4 acceptance identity before future storage.

Named real PostgreSQL evidence in test_prepared.py:
`test_provisioned_router_remains_planned` uses valid real committed request/source
facts and genuine provisioned service, expects kernel ACTION_UNAVAILABLE and
zero handle/receipt/allow/source/product effects;
`test_foreign_service_and_human_cannot_prepare_route` keeps principal controls
separate; `test_planned_denial_rollback_preserves_request` compares retained
request and exact audit/source/effect snapshots. No test activation flag.
Receipt validation helpers may test predicate rejection with synthetic values
only; no fabricated allowed event is stored or described as issued authority.
Delete the request equality matcher and the private receipt consistency check
in isolated probes: each named substitution regression must fail at its expected
rejection assertion, not setup. Real positive receipt/handle execution is deferred.

Commands: `cd backend && .venv/bin/pytest tests/authorization/post_submit_routing/test_contracts.py tests/authorization/test_acceptance_source_contracts.py -q`;
real PostgreSQL proof uses:

```sh
cd backend && .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /tmp/arch04e2a-pg.json --timeout-seconds 1200 -- \
  .venv/bin/python -m pytest \
  tests/authorization/post_submit_routing/test_prepared.py -q --tb=short
```

Supply `WORKSTREAM_TEST_ADMIN_DATABASE_URL` from the existing local Docker
fixture without printing credentials; the runner creates its own isolated database.

Run focused pure routing/source contract tests, real PostgreSQL planned-action
and rollback proofs, retained PREP/source tests and canonical module/AUTH/test
boundaries. Add named guard-removal probes for discriminating substitution tests.
Run Ruff, Commitrail/link/stale-wording checks and full hosted completeness with
no skips/deselections. Positive live issuer, persisted receipt and outcome proofs
belong to the activation chunk and must not be claimed here.

## Reconciliation

- The two new AUTH routing proof modules run once on existing task lane A.
  Task lane C exceeded its unchanged 1,200-second bound in hosted execution;
  its earlier passing run had only about 46 seconds of headroom. Task lane A
  measured about 685 seconds before this allocation. Existing routing-request
  proofs stay on C; no test, existing assignment, lane count or timeout is removed
  or weakened.

- Retained service-matrix tests now supply a valid routing request, project scope
  and matching operation/request/correlation IDs before asserting planned-action
  or wrong-service denial. Empty input would stop at shape validation and fail to
  prove either authorization boundary. The exhaustive action rows and zero-handle,
  zero-lookup and zero-evidence assertions remain intact.

- Current-source reconciliation: merged #467 supplies exact TASK reservation;
  #465 supplies inert AUTH source contracts. No code change is authorized by an
  old plan where it contradicts these current owner boundaries.
- Next usable boundary: CON-07/shared acceptance preparation and hidden handlers,
  followed by exact receipt/consequence activation and live composition.
- Remaining risks: source projection and actual receipt custody are still future
  work; detached values never substitute for the immutable AUTH event.
