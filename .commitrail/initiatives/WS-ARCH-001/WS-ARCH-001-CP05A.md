# WS-ARCH-001-CP05A — Public ContributionPolicy administration

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: Finance Authority can discover, create, edit, publish,
  read and retire the existing project ContributionPolicy through the public API.

## Intent

Finish the public prerequisite for complete-guide activation. A manager must bind
an explicitly published policy; activation must not invent an unpaid default or
bypass Finance Authority. This is exposure of existing policy behavior, not award
materialization or fulfillment.

## Current behavior

Main `724459bc` includes ARCH-03C7. CP05 supplies the five live exact Finance
permissions; `contributions/service.py` and `policy_publication.py` own policy
commands, frozen versions, replay and validation. Their application adapters
compose PROJECTS eligibility and verified compensation bindings. There is no
public policy router. `scripts/api_contract_e2e.py::activate_guide_for_e2e`
still publishes a prerequisite internally. Public activation also lacks a manager
context containing discoverable approval/policy selections; that is the next
bounded change, not a reason to expose an unusable activation POST first.

## Bounded change

### Allowed

- `backend/app/api/routes/contribution_policies.py`, its request dependency and
  top-level API router: closed request bodies, typed responses and transactions.
- `backend/app/modules/contributions/api/`, `schemas.py`, `service.py`,
  `repository.py`, `policy_mutation_support.py`, and the existing CON application adapter: a narrow typed
  operations port and project-current discovery through the existing read action.
- Existing application AUTH adapter composition and typed denial/unavailable
  propagation; AUTH-owned scope-denial context in `domain/contribution_policies.py`,
  `domain/audit_targets.py`, `domain/action_groups.py`, `prepared.py`, `kernel.py` and
  `contribution_policy_authorization.py` to retain existing PREP scope denials.
  Extract the touched prepare-denial classification into existing action groups
  and refresh the exact structural ledger with shrinking kernel debt.
  No new role, permission, action or migration.
- Focused `backend/tests/contributions/` HTTP tests and signed Finance fixtures;
  `backend/tests/authorization/contribution_policies/{test_contracts,test_scope_locks,test_revocation,test_postgresql}.py`; existing
  contract, route/action inventory, semantic-lane and behavior-ownership
  registrations and the two current `.ci/behavior-contracts/contribution-policy-*`
  proof references that name the obsolete hidden-route test; API drill may exercise this policy workflow without claiming
  full public activation. Retain existing CON behavior and binding proof.
- README, canonical contribution specification, operating manual, roadmap and
  current ARCH/AUTH/CON/POL navigation, `docs/operations_authorization_service.md`
  and authorization activation-custody prose; this record; local sheet exports only if present.

### Not allowed

New policy semantics, default policy creation, Project Manager policy mutation,
new authorization powers, relaxed binding validation, award/payment/fulfillment
implementation, guide activation or Submission exposure, checker execution,
compatibility APIs, data deletion, new dependencies, weakened CI or required behavior proof.
Preserve the merged WS-QUAL-003-16 test-audit implementation and tooling policy;
this product chunk does not redesign them.

## Design and decisions

Use one API composition dependency with authenticated human context and the
existing exact Finance authorization adapter. End identity-read transactions
before entering the caller-owned policy transaction. Validate response facts
before commit so serialization failure rolls back mutation and authority evidence.
Preserve a typed AUTH denial separately from unavailable/invalid AUTH execution.
Every policy read/prelock/PREP denial precedes policy effects: the HTTP caller
commits only this canonical denied decision before returning concealed 404.
Evidence/storage or invalid prepared-boundary failures roll back and return
retryable 503. Ordinary missing product state still returns concealed 404;
other exceptions never use the denial commit path.

A refused mutation scope has no final policy/version facts. Bind its requested
project, observed existence and exact closed mutation action in an AUTH-owned
scope-denial context. Extend existing `deny_unsupported` before its final-fact
binding; only this scope-only context permits absent caller input. Observe project
existence without a product lock after AUTH locks. Existing projects receive exact
project audit selectors; absent projects retain only the requested target reference,
with nullable project/resource selectors. Never invent policy/version IDs.
Existence-query or audit-write failures remain unavailable, not denied.

Expose project-scoped create-draft, exact version update/publish/retire and
exact policy/version read. Require one UUID Idempotency-Key on mutations; reject
missing, duplicate and malformed headers before actor resolution/product SQL,
without claiming precedence over token verification. Server context supplies
actor identity. Reuse the owner operation identifier as the replay selector;
never accept actor or authority facts in a body.

Add a bounded project-current discovery read under `contribution.policy.read`.
The owner performs bounded nonlocking ID-only preselection (at most two
candidates), rejecting absence or ambiguity. Do not reuse `get_reusable_policy`:
its FOR UPDATE would acquire product locks before AUTH. Authorize the selected
exact policy using the existing read port, then obtain current draft/published
selectors with one nonlocking project-scoped query. Return only that same
still-non-retired aggregate; reject retirement/replacement, disappearance or
multiple non-retired aggregates after AUTH. Never return the preselection row.
A same-aggregate draft created between selection and AUTH is returned from the
post-AUTH projection. A replacement aggregate requires a new read/authorization.
Do not assume the partial active-policy unique index also prevents duplicate
draft aggregates. Fail closed on this corruption without a new migration. An independent Finance actor can recover these
selectors without the creator's receipt or idempotency key. Exact-ID reads keep
retired history available to authorized Finance callers. Absence/foreign/denial
remain concealed; no parallel policy list, cursor or permission system.

Support the already-defined complete unpaid graph (accepted_submission and
completed_review, no award definitions). Compensated graphs continue to require
valid verified bindings; binding administration remains separately internal.
Do not silently convert invalid compensated rules to unpaid rules.

## Acceptance criteria

1. Signed API flow creates, discovers, edits, publishes, reads and retires the
   existing policy with exact system/project Finance grants. Another Finance
   actor can discover a saved draft after the creator is revoked and finish it.
2. Project Manager, Operator, Contributor, foreign Finance, revoked actor/link/
   grant and service callers cannot access or mutate the resource. Exact project
   filters prevent foreign resource locks/data access; concealed errors persist.
3. Same-key same-command replay returns immutable original results after live
   exact read reauthorization, including after product state advances. Altered
   command/project/actor under that key conflicts; a fresh operation against a
   stale version fails current-state guards. Header errors reject before product composition; duplicate headers reject.
4. Public bodies cannot supply actor IDs, authority facts or storage fields.
   Both required contribution rules remain mandatory. Unpaid publication succeeds;
   malformed graphs and unsupported/foreign/unavailable compensated bindings fail
   using the existing validator, preserving state and evidence atomically.
5. Invalid headers reject before CON composition/actor resolution. Invalid bodies
   reject before any CON operation or policy-authority decision; ordinary FastAPI
   dependency resolution may already have admitted identity and composed the port.
   Post-consume response validation/serialization failure observes real staged
   lifecycle and ALLOW rows, then proves their rollback independently. A targeted
   real audit INSERT failure proves its exact PostgreSQL error, no later response
   construction, rollback and successful same-key retry after injection removal.
   It does not claim a successfully staged ALLOW. No early commits.
6. Discovery returns only authorized current policy and draft/published selectors;
   exact historical reads remain available. OpenAPI and current documentation
   describe policy administration as public, activation/intake as still pending.

## HTTP contract

All paths are relative to `/api/v1/projects/{project_id}/contribution-policies`.
All responses use the canonical owner facts; authenticated context supplies actor.

| Method and suffix | Existing action | Response |
|---|---|---|
| POST `/drafts` | contribution.policy.create_draft | ContributionPolicyMutationResult |
| GET `/current` | contribution.policy.read | ContributionPolicyProjectSelection (policy ID, published and open-draft IDs) |
| GET `/{policy_id}` with optional version_id query | contribution.policy.read | ContributionPolicyView |
| PUT `/{policy_id}/versions/{version_id}` | contribution.policy.update_draft | ContributionPolicyMutationResult |
| POST `/{policy_id}/versions/{version_id}/publication` | contribution.policy.publish | ContributionPolicyMutationResult |
| POST `/{policy_id}/versions/{version_id}/retirement` | contribution.policy.retire | ContributionPolicyMutationResult |

Mutation headers map their single UUID Idempotency-Key to the existing CON
request `operation_id` (a caller replay selector, not a generated row identifier).
Closed bodies carry only name, rule graph, or an empty decision object as
applicable. They cannot supply actor IDs or a second operation ID.

## Risk and review routing

- Risk class: L1, bounded Finance authorization/public policy exposure.
- Required reviewers: security/architecture/reuse; QA/test-delta/product-ops;
  documentation. CI integrity for exact ownership/lane registration changes.
- Human review focus: Finance versus manager powers, project scoping, recovery,
  unchanged explicit unpaid/compensated semantics and no premature activation.
- Size rationale: the cohesive public-policy boundary exceeds the preferred
  500-line review guideline because it includes signed PostgreSQL recovery,
  isolation, replay, revocation and transaction proofs plus current navigation.
  Product changes extend the existing CON owner, delivery composition and AUTH
  prepare-denial evidence path; there is no new migration, permission, economic
  behavior or independent chunk. The AUTH repair uses existing denial machinery
  and moves its closed classification into existing action groups, shrinking the
  touched oversized kernel rather than adding structural debt.

## Evidence

Named proof nodes below are under `backend/tests/contributions/public_policy/`.
They bind the implemented behavior to focused tests; full hosted evidence belongs
in the PR trust summary.

| Behavior atom | Named proof and valid control |
|---|---|
| All six routes, exact actions, strict fields and typed responses | `test_contracts.py::test_public_policy_contract`; replaces the obsolete `test_policy_routes_absent.py`; binding-hidden assertions remain |
| Signed complete unpaid workflow, project/system Finance | `test_workflow.py::test_public_policy_lifecycle`; both required rules, no bindings; exact policy/version/event identities and stored matched grant |
| Lost-response handoff | `test_workflow.py::test_second_finance_recovers_draft`; create with A, revoke A publicly, independently grant B, discover without A receipt/key, B edits/publishes; A created_by preserved, B actor and exact grant recorded; revoked A must be denied after the actual revoke |
| Current published and open-draft discovery together | `test_discovery.py::test_current_selectors`; publish, create successor draft, discover both exact version IDs |
| Retirement/replacement between preselection and AUTH | `test_discovery.py::test_discovery_rechecks_after_authorization`; pause selection, retire/replace under another valid Finance actor, resume; no replacement disclosure; fresh read succeeds |
| Same-aggregate draft appears during read | `test_discovery.py::test_discovery_refreshes_same_policy`; return the post-AUTH draft selector, not stale preselection |
| Corrupt duplicate draft aggregate | `test_discovery.py::test_ambiguous_current_policy_is_concealed`; otherwise-valid direct SQL second draft, fail closed, remove it and restore positive control |
| No product lock before discovery AUTH | `test_discovery.py::test_discovery_does_not_take_product_locks`; hold the policy row independently, prove discovery does not wait and observe pre-AUTH ID-only SQL |
| Roles, scope and revocation | `test_workflow.py::test_public_policy_denials`; valid exact target, signed PM/Operator/Contributor/foreign Finance and revoked identity; existing CP05 principal matrix remains owner proof |
| Foreign selector non-wait/non-access | `test_discovery.py::test_foreign_policy_selector_does_not_wait`; valid live Finance grants and two real projects; independently hold foreign policy/version rows, then exact read/update/publish/retire with requested-project path plus foreign IDs must promptly conceal without foreign read/lock; same-project unlocked control succeeds |
| Live authority changes | `test_workflow.py::test_public_policy_revocation`; real stored active grant/profile/link control, independently revoke grant, suspend profile or revoke identity link, observe public denial with otherwise-valid policy, then issue a new grant or use supported profile/link reactivation and prove success; never restore a revoked grant or terminally deactivated profile; cannot rely on an absent grant as another failure |
| Nonhuman API admission | `test_contracts.py::test_nonhuman_policy_admission`; validly signed nonhuman token is rejected before CON composition; valid human control reaches composition |
| Immutable replay after advancement | `test_workflow.py::test_policy_replay_after_publication`; original draft operation still returns its original receipt; no extra lifecycle rows |
| Key actor/project/body substitutions | `test_workflow.py::test_policy_replay_conflicts`; B holds live same-project Finance; A holds live grants on both real projects; otherwise-valid requests fail the event actor/project/digest comparison, original replay succeeds |
| Fresh stale-version mutation | `test_workflow.py::test_new_operation_rejects_stale_version`; real successor state and fresh key isolate the lifecycle guard from replay-digest checks |
| Header/body rejection | `test_contracts.py::test_mutation_input_admission`; all four mutation routes, missing/duplicate/malformed key uses fail-if-entered CON dependency; forbidden body fields use fail-if-invoked owner operation; valid input reaches each intended boundary |
| Graph and binding validation | `test_workflow.py::test_invalid_policy_graph`; complete valid compensated control with active same-project unit and verified binding; vary only binding project/status/capability, assert intended guard and unchanged lifecycle/AUTH rows; retain existing deep CON validator tests |
| Post-consume response rollback | `test_failures.py::test_response_failure_rolls_back`; observe actual lifecycle+ALLOW in caller and absence independently, inject validation/serialization failure, verify all effects absent independently and same-key retry succeeds |
| Actual storage failure | `test_failures.py::test_real_audit_insert_failure`; unchanged real writer under temporary PostgreSQL constraint, exact INSERT/constraint/SQLSTATE proof and marker rollback; clean same-key retry |

Discriminating probes against the new behavior: remove the
post-AUTH same-policy/currentness check (retirement test fails); replace
ambiguity rejection with first-row selection (duplicate test fails); return
preselection selectors instead of the post-AUTH projection (fresh draft test
fails); select first duplicate header (admission test fails); move commit ahead
of response validation (rollback test fails). Controls run on restored code; mutations remain ephemeral. Remove the repository project-correlation predicate
for the foreign-selector proof: the held foreign row must then cause a wait or
the read must disclose the wrong resource, failing the original assertion. Existing replay and binding guards are reused, not
reimplemented merely to add tests.

Run affected owner proofs, route/schema and boundary checks, Ruff, Markdown
links, stale wording and Commitrail checks. Hosted canonical PostgreSQL/MinIO
lanes and complete-execution evidence remain mandatory; coverage is diagnostic. No real inference/private guide input is
needed. Plan feasibility is inspected evidence, not runtime proof.

## Review findings

Initial feasibility review confirmed that public activation cannot precede a
usable public published-policy prerequisite. It also identified lost-selector
recovery; project-current discovery is included instead of requiring the next
Finance actor to possess the creator's original response. Further plan review
requires nonlocking preselection, post-AUTH refresh, ambiguity rejection,
immutable replay after advancement, independently authorized negative controls,
and separate actual-INSERT versus post-consume rollback proofs. These are
incorporated above before implementation.

## Reconciliation

- Current-source reconciliation: CP05/CP06/CP07/AUTH-12H and ARCH-03C7 are
  delivered. This change adds public Finance policy administration and selector
  recovery; public guide activation remains absent.
- Next usable boundary: manager activation context and public activation using
  CP07/AUTH-12H, then approved-guide intake integration. The API drill's internal
  activation helper is removed when its complete public replacement lands.
- Remaining risks: compensated policy creation still needs an existing verified
  binding; public binding administration and fulfillment are not claimed here.


## Implementation proof and limits

The public dependency composes the existing AUTH adapter and CON owner, with
one caller transaction and declared-response validation before commit. No role,
permission, policy lifecycle, binding rule, migration or compensation behavior
is added. The sole new owner read uses bounded ID-only preselection and a fresh
same-aggregate projection. The original hidden-route assertion is removed;
required owner, scope, binding and replay proofs are retained.

Six ephemeral discriminators detected aggregate replacement, first-candidate
ambiguity acceptance, stale selector return, foreign-row locking after removal
of project correlation, first-duplicate-header acceptance, and commit before
response validation. The response failures run after real lifecycle/ALLOW staging;
the audit failure reaches the unchanged real INSERT and verifies PostgreSQL
constraint `23514`, transaction-local marker rollback and same-key recovery.
These are isolated PostgreSQL/ASGI proofs, not hosted transport or compensation
provider execution. No local sheet exports are present.


## Implementation review corrections

Security review identified rollback of canonical denied decisions and erasure of
AUTH unavailability into 404. Typed boundary errors now preserve both distinctions;
all six public operations prove retained denial evidence with unchanged product
state and authorized controls. Real audit INSERT failures on allowed and denied
requests prove 503/retryable, rollback, and same-actor/key recovery. Application
adapter tests distinguish invalid prepared failures from actual denials.
`test_scope_denial_targets_requested_project` proves all four mutations record
only the requested project (including nonexistent targets), never substituted
policy custody; the original project remains unchanged.
`test_scope_denial_rejects_substituted_or_invented_facts` rejects mismatched
actions/projects, fabricated policy identifiers and inappropriate caller input.
Scope denials remain outside the general final-resource union and are admitted
only by the existing denial path. The extracted prepare-denial classifier retains
all previous action/context pairs. Existing AUTH scope tests retain their
no-capability assertion and now require policy scope refusals to be evidenced;
invalid/service callers and binding-only behavior remain unchanged. An ephemeral
removal probe bypassed `deny_unsupported`; the retained-denial regression then
failed specifically because its audit query found no decision. No probe patch
or test-only production switch is retained.
Documentation review reconciled four stale current exposure claims in the
publication proof map, roadmap, CON overview and authorization-custody guide.
The public request documentation also makes existing aggregate-name retention
explicit. No AUTH permission or policy lifecycle is changed by these repairs.

The existing real revocation race and sequential revoked-grant proofs expect the exact typed denial on
post-revocation mutation and replay, replacing its obsolete generic-conflict
expectation. Both policy-first and revocation-first ordering, unchanged persisted
state and the positive committed policy outcome remain asserted.

Main reconciliation preserves the merged test-necessity audit, including its
project-role proof decomposition, behavior-based CI policy, and structural
ledger reductions. CP05A's four public test modules remain selected alongside
main's added project-role modules; its kernel reduction remains in the combined
ledger. Public capability and next-boundary wording remains unchanged.


External documentation review corrected the AUTH, CON and POL overview navigation:
CP05A delivers public Finance policy administration; manager activation context
and public guide activation are next, followed by approved-guide intake. The
README distinguishes AUTH decision ownership from the CON caller transaction's
atomic policy, AUTH-evidence and replay commit, and describes discovery as a draft
selector, a published selector, or both. The roadmap already states this outcome
and sequence, so this correction requires no additional roadmap edit. Runtime
code, tests and authorization behavior are unchanged.

The README and authorization operating manual also distinguish delivered CP08
Task/Assignment/Submission lineage from the remaining public activation and
approved-guide intake integration.

## CI completion repair

The user authorized repairing the repeated TASK lane timeout in this PR. The
two-part TASK partition exhausted the unchanged 1,200-second execution budget at
different late-suite points (598/614 and 596/614 completed), without an assertion
failure. The same tests previously completed in 801 seconds. This supports
insufficient partition headroom, not a demonstrated product deadlock.

Plan: extend the existing deterministic TASK node partition from two lanes to
three. Reuse the existing catalogue, isolated runner, matrix and aggregate; do not
add a scheduler or change test fixtures. Every canonical node must still execute
exactly once, with independent database/role/MinIO custody per lane.

Allowed repair files: `backend/scripts/test_lane_catalogue.py`,
`.github/workflows/backend.yml`, `backend/tests/test_ci_lane_catalogue.py`,
`backend/tests/test_test_lane_evidence.py`, `backend/tests/test_ci_test_lanes.py`,
`scripts/test_lightweight_agent_gates.py`, `docs/operations_backend_testing.md`,
`backend/scripts/validate_test_lane_evidence.py`,
`backend/tests/test_isolated_database_runner.py`, `docs/roadmap_status.md`,
and this record. Prohibited: product code, assertion weakening, skips, timeout
increases, coverage/gate relaxation, altered database durability or reset rules.
Risk: L1 CI evidence integrity. Reviewers: CI integrity and QA/test delta; focused
documentation review for the changed operational instructions. Human focus:
complete node-set preservation and all nine lane artifacts required by aggregate.

Acceptance and verification: preserve the old canonical manifest's node union
while assigning each TASK node to exactly one of three nonempty partitions; prove
each missing partition is rejected, all nine artifacts are required and existing
partial-retry validation remains intact. Run catalogue/runner/evidence/aggregate
regressions, lightweight gate tests, links/stale wording and Commitrail checks;
then require exact-head hosted completion of every canonical test and the API
contract drill. Reconcile the roadmap's CI allocation from eight to nine lanes; CP05A's
product outcome and next boundary remain unchanged. No local sheet exports
are present.
