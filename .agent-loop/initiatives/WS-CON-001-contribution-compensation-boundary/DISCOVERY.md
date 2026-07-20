# Discovery: WS-CON-001 Contribution Record And Compensation Boundary

## Baseline inspected

- trusted `origin/main` refreshed to `8d5eb15b`, including contributor-foundation
  PR #153, AUTH-09D-B PR #152,
  ART-02B1 PR #151, planning-only REV PLAN2 PR #150, AUTH-09D-A PR #148, REV-02 PR #147,
  REV-01 PR #145, AUTH-09C PR #146, ART PR #141, CON-01 PR #144, AUTH-09B PR
  #143, REV planning PR #128, AUTH-09A, AUTH PR #140, and the earlier WS-XINT
  PR #139 boundary;
- complete WS-XINT intent, decisions, plan, REV/CON, AUTH/role-service,
  AUTH/REV, AUTH/ART, and ART/REV handoffs;
- current WS-CON initiative package and archival reference inputs;
- canonical README, glossary, architecture lockdown/data model/lifecycle,
  authorization spec, artifact spec, roles/operations docs, and ADRs 0012-0015;
- current backend project/task/submission/checker, AUTH, audit, artifact, and
  migration code/tests;
- human-approved 2026-07-17 FinalAcceptance/no-adjudication direction and the
  complete merged WS-REV-001 planning package;
- stale wording, authorization, artifact, link, loop-memory, and agent-gate
  scanners/tests.

## Current runtime observations

- The backend stops before the human Review/ContributionRecord implementation.
- Project code still has the retired guide-bound economic schema. There is no
  canonical ContributionPolicy aggregate, ContributionRecord,
  CompensationAward, fulfillment receipt, or status projection runtime.
- Existing Submission rows carry `version` and supersession lineage. A separate
  SubmissionVersion model would duplicate current identity. The handoff field
  named `submission_version_id` therefore maps to canonical `Submission.id` and
  is stored as `submission_id`.
- No FinalAcceptance runtime exists yet. Merged REV PR #128 plus PLAN2 PR #150
  are reviewed planning authority and define the exact schema/transaction, but
  CON-03C still waits for the REV-04B runtime target.
- The merged AUTH catalogue has 74 PermissionIds and 65 ActionIds. Seventeen
  actions are active and 48 are planned. AUTH-09B activates only
  `actor.service.provision`; AUTH-09C activates only `actor.profile.read` and
  `actor.identity_link.read`; AUTH-09D-A activates only the three actor-profile
  lifecycle actions; AUTH-09D-B activates only `actor.identity_link.revoke`
  and `actor.identity_link.reactivate`. No WS-CON or task-claim ActionId is
  registered. The contributor-field/canonical-human foundation is merged:
  TaskAssignment and Submission now expose `contributor_id`, enforce canonical
  human ActorProfile lineage, and revalidate active human writers. AUTH-09E
  fixed-service admission remains proposed.
- Current AUTH supports actor-self, AdminRoleGrant evaluation, and controlled
  human-administrator provisioning of an approved fixed service
  ActorProfile/ActorIdentityLink. Independent ProjectRoleGrant runtime,
  fixed-service runtime admission, CON evaluators, ART/REV custody transfer, and
  the cross-domain prepared mutation protocol remain future AUTH work. PR #140
  adds their reviewed plans, not runtime.
- AUTH's static service-action matrix is typed code; it is not a database grant
  table. AUTH-09E is the required runtime admission path.
- PR #129 added inactive ART preparation/source values only. It added no
  contribution-evidence capability, ART admission/provider execution, binding,
  action, permission, or CON dependency.
- No shared transactional outbox exists with the required generic dispatcher,
  claim fencing, replay, and typed handler outcome contract.

## CON-02A focused discovery

- Trusted `main` at `8d5eb15b` ends its migration chain at AUTH-owned
  `0027_contributor_foundation`; CON-02A owns linear revision
  `0028_shared_transactional_outbox` and must import its model through
  `backend/app/db/models.py` so metadata and migration truth agree.
- `app.core.hashing.canonical_json_hash` is the only repository canonical JSON
  encoder. It sorts object keys, rejects non-finite numbers, uses compact UTF-8
  JSON, and returns a `sha256:` digest. The outbox must call it directly and
  must not introduce another serializer or digest helper.
- `AuthorityIdempotencyRepository` establishes the local concurrency pattern:
  insert with PostgreSQL `ON CONFLICT DO NOTHING`, lock the existing namespace
  row, compare the canonical digest, and complete through the caller's
  `AsyncSession` without committing. Outbox append can reuse this sequence
  without importing AUTH or creating a second generic idempotency framework.
- The common event envelope requires stable event ID, type, version, producer,
  project, correlation, causation, idempotency key, canonical object payload,
  and database-authoritative occurrence time. Delivery attempt/state fields
  are operational metadata and must be independently mutable without allowing
  immutable envelope drift.
- CON-02B has no migration allowance. CON-02A must therefore land the complete
  feature-neutral persistence shape needed later for pending/claimed/retryable/
  acknowledged/dead-letter dispatch, claim generation/lease, attempts,
  eligibility, bounded failure evidence, and retention while exposing only
  append/replay behavior in this chunk.
- Existing audit and AUTH repositories flush and refresh on the supplied
  session but never commit or publish. PostgreSQL triggers are already used for
  append-only/immutable custody and guarded downgrade checks; the shared outbox
  should follow those repository conventions.
- ART PR #141 adds artifact adapters, startup wiring, and an artifact delivery
  executor but no shared outbox module, outbox route, dispatcher registry,
  broker publication seam, or outbox permission. CON-02A therefore remains
  feature-neutral and authorization-neutral and does not call ART.
- AUTH-09C PR #146 adds serialized administrative actor/profile reads and
  activates their already-canonical action/permission pairs. It adds no
  migration, CON/outbox identifier, service admission, or dispatcher seam.
- REV-01 PR #145 canonically publishes the Review/revision lifecycle and keeps
  REV transaction ownership, ordered CON flush-only participation,
  FinalAcceptance source integrity, and shared audit/outbox staging intact. It
  changes documentation/gates only and adds no runtime outbox consumer.
- REV-02 PR #147 is planning-only chunk decomposition for future guide,
  ReviewPolicy/task, and submission-attribution work. It adds no backend,
  migration, test-runner, CON, or outbox behavior.
- REV PLAN2 PR #150 is a planning/specification-only runtime-readiness refresh.
  It preserves the two ordered CON operations and REV-owned atomic decision
  transaction while splitting future runtime gates: CON-03B precedes REV-03A,
  CON-02A/02C precede REV-04B, CON-03C/07 precede REV-10, the shared outbox
  dispatcher/handler registry precedes REV-12P1, CON lifecycle hooks precede
  REV-12A3, and CON-11 precedes the sole product release in REV-13C. It changes
  no 02A runtime or migration.
- ART-02B1 PR #151 adds the S3-compatible adapter, MinIO/AWS configuration,
  exact SDK pins, CI MinIO service, and substantial artifact/configuration test
  coverage. It adds no migration, outbox import, shared dispatcher seam, or
  core CON dependency. It therefore leaves 02A's implementation boundary
  unchanged while requiring fresh repository-wide evidence on the larger
  dependency and test tree.
- AUTH-09D-B PR #152 activates exactly the two identity-link lifecycle
  mutations and expands AUTH routes/tests without adding a migration, CON
  action, task-claim action, fixed-service admission, or outbox seam. The
  at that point the reviewed contributor foundation followed it; AUTH-09E
  remains a later gate.
- Contributor-foundation PR #153 clean-cuts TaskAssignment and Submission
  attribution to `contributor_id`, installs database-enforced
  canonical-human lineage, and adds transaction-local active-human write
  revalidation. It owns migration `0027_contributor_foundation` and therefore
  moves CON-02A to linear child `0028_shared_transactional_outbox`. It changes
  no ActionId, PermissionId, availability, grant, evaluator, service admission,
  review lifecycle, dispatcher seam, or outbox behavior.
- ART-02C1 PR #154 owns `0028_artifact_admission` on trusted main `44f2467c`.
  It adds no outbox seam or CON authority, so CON-02A moves unchanged to the
  linear child `0029_shared_transactional_outbox`.

## Canonical merged changes affecting CON

1. `ContributionPolicy`, `ContributionPolicyVersion`, `ContributionRule`, and
   `ContributionAwardDefinition` decide award eligibility. CompensationAward
   is the evaluated downstream result.
2. Every valid Review creates reviewer `completed_review`. REV creates exactly
   one FinalAcceptance for `accept`; submitter `accepted_submission` consumes
   FinalAcceptance rather than inferring acceptance from Review.decision.
3. Core contribution creation is a flush-only CON participant in the REV-owned
   transaction. It performs no ART call or evidence projection.
4. CON copies the stabilized versioned Submission/packet digest supplied by REV
   into `ContributionRecord.artifact_hash`; it does not verify or rederive it.
5. The current shipping path consumes exact submitter and reviewer grants only.
   The separate global AUTH role catalogue is not expanded here; no adjudication
   behavior or readiness dependency enters WS-CON.
6. ActionOwner is AUTH activation custody. ART and REV transfers must be
   complete across their full current catalogues; WS-CON cannot prescribe
   partial subsets.
7. Fixed services use provisioned ActorProfile/ActorIdentityLink, immutable
   ServiceIdentity, exact static ActionId row, and AUTH-09E admission.
8. The shared outbox dispatcher cannot inherit protected feature-handler
   authority. Delivery, reconciliation, rebuild, and callback boundaries need
   exact approved service contracts.
9. REV owns FinalAcceptance persistence, Review/task effects, shared audit/
   outbox staging, and the single commit. CON validates the locked acceptance
   fact, flushes contributions/awards, returns a typed result, and never commits.
10. PR #140 fixes the prepared handle to exact session, ActionId,
    actor-reference kind/reference, idempotency key, and canonical request
    digest bindings. Final resource facts are recomposed after feature locks;
    AUTH consumes the handle, evaluates once, and stages evidence.
11. PR #140 publishes complete 25-ART/19-REV custody-transfer maps, but those
    availability-neutral runtime transfers remain proposed. CON depends on the
    complete REV transfer and never restates a two-action subset.
12. Trusted main has stable PermissionId `task.claim` but no task-claim
    ActionId. CON-05A's hidden TaskAssignment policy freeze must merge into
    task-owned claim composition before AUTH-13 enumerates/registers and
    activates that action.
13. Merged REV rejects the prior omnibus CON decision input. One mandatory
    participant exposes a reviewer operation before the decision branch and an
    accept-only submitter operation after FinalAcceptance and accepted task
    effects. Neither input carries nullable cross-actor source/policy facts.
14. REV-12A1/12A3 require one shared `JointLifecycleMutationFence`. Every CON
    fulfillment-obligation creation/requeue/successor/repair writer must fence
    before allocating an immutable monotonic root ordinal. CON must expose the
    current maximum ordinal with drain counts; delivery-draining dispatch and
    callback may complete only same-generation roots at or below REV's cutoff.

## Relevant files and symbols

| Source | Observation |
|---|---|
| `docs/architecture_data_model.md` | Canonical policy/rule/definition, binding, contribution, award, receipt, and projection names/fields |
| `docs/decision_0015_project_contributor_roles_are_independent.md` | Exact project role values and independent revocation |
| `docs/spec_authorization_service.md` | Stable permissions, current actions, ActionOwner semantics, static service matrix, AUTH-09E order |
| `WS-AUTH-001/ACTIVATION_CUSTODY.md` | Exact complete custody transfers, feature-manifest activation gates, and mandatory CON participant prerequisite for review.decision |
| `WS-AUTH-001-PREP` chunk | Exact prepared-handle bindings, authority-first locks, single use, caller-owned commit, and concurrency/rollback proof |
| `WS-AUTH-001-13` chunk | Future task-claim ActionId enumeration, registration, evaluator integration, and activation owner; exact submitter grant, task-owned resource composition, and AUTH-PREP dependency |
| `WS-AUTH-001-16` chunk | Aggregate proof that active review.decision uses one rollback-safe REV+CON transaction with no ART/fallback |
| `WS-XINT-001/REV_CON_HANDOFF.md` | Exact core participant sequence and optional-evidence boundary |
| `WS-REV-001/CON_INTEGRATION_REVIEW.md` | Merged two-operation participant, exact lineage, interleaving, and release-control dependencies |
| `WS-REV-001-08/10` chunks | Decision input freeze followed by first hidden canonical Review commit only after exact CON participant merge |
| `WS-REV-001-12A1/12A3` planning children | Single shared lifecycle fence, obligation-writer ordinal order, cutoff capture, and drain-phase behavior required from CON |
| `WS-XINT-001/AUTH_ROLE_SERVICE_HANDOFF.md` | Fixed service and project grant contract |
| `WS-XINT-001/AUTH_REV_HANDOFF.md` | Full review activation-custody/hidden behavior sequence |
| `WS-XINT-001/AUTH_ART_HANDOFF.md` | Full 25-action ART transfer; not a core CON gate |
| `backend/app/modules/projects/{models,schemas,repository,service}.py` | Current guide-bound economic fields and consumers to cut over/remove |
| `backend/app/modules/tasks/**` | TaskAssignment creation and future submitter policy freeze seam |
| `backend/app/modules/tasks/models.py::Submission` | Existing immutable version identity: `id`, integer `version`, and `supersedes_submission_id`; no SubmissionVersion table |
| `backend/app/modules/authorization/{catalogue,policy,kernel,schemas}.py` | Current 74/65/17/48 runtime and stable PermissionIds; only AUTH administrative actor/profile/service/link lifecycle actions are active; no CON/task-claim ActionId |
| `backend/app/modules/audit/**` | Shared append-only audit extension point |
| `backend/app/modules/artifacts/{preparation,sources}.py` | Inactive ART-only preparation; no core CON import |

## Existing tests and gaps

- Project/task tests cover current setup/claim/submission behavior but not
  ContributionPolicy freezes or retirement of the legacy economic schema.
- AUTH tests cover catalogue parity, planned denial, actor-self/admin grants,
  decision digest, scope evidence, and route commit/rollback. PR #140 changes
  planning/tests for documentation gates but does not implement CON contexts,
  independent project grants at CON call sites, AUTH-09E CON identities,
  custody transfer, or prepared cross-domain mutations.
- ART tests prove preparation only. No optional evidence projection capability
  exists or is needed for core contribution tests.
- No tests yet cover ContributionRecord cardinality, frozen rule evaluation,
  money/points award uniqueness, fulfillment callback, delivery replay,
  shared-outbox handler isolation, or REV/CON atomic rollback.
- No tests yet cover FinalAcceptance one-per-task/Review/Submission constraints,
  accept-only creation, source-lineage exclusivity, or rollback when CON fails.
- No tests yet cover the two ordered CON operation inputs, reviewer-before-
  branch fault boundaries, immutable fulfillment root ordinals, every writer
  versus cutoff capture, or same-generation pre-cutoff drain completion.

## Dependencies

- AUTH: AUTH-10 independent project grants, AUTH-09A-E fixed-service sequence,
  complete ART/REV custody transfers, AUTH-PREP, reviewed CON registration and
  later activation chunks, exact CON service identities/static rows, and
  action-specific evaluators. Task claim activation must consume the merged
  CON-05A freeze participant; review.decision activation must consume CON-07.
- REV: ReviewLease reviewer policy FK; canonical claim/decision composition;
  REV-owned FinalAcceptance with exact policy-context typing; stabilized
  artifact-hash facts; mandatory CON participant injection; REV-staged shared
  audit/outbox; single route commit; and no no-op fallback.
- REV release control: CON writer/dispatch/callback hooks, immutable root
  ordinal allocation under the shared fence, and same-session maximum-ordinal/
  drain observation must merge before REV-12A3.
- Task/Submission: submitter policy freeze and stable assignment/version lineage.
- Shared outbox/audit: caller-transaction append and feature-neutral dispatch.
- ADR 0014 adapters: typed capability port, factory, and composition-root
  registration for external fulfillment.
- ART: no core dependency; optional projection only after separate approval.

## Risks

| Risk | Mitigation |
|---|---|
| Two award-eligibility models | Clean semantic then physical cutover; no fallback |
| Contribution missing after Review | Mandatory flush-only participant and one caller commit |
| Reviewer contribution ordered after branch | Two operation-specific inputs; reviewer operation always precedes branch and cannot depend on branch effects |
| Submitter contribution inferred from Review decision | REV-owned immutable FinalAcceptance is the only submitter source; exact one-to-one constraints and lineage checks |
| ART outage suppresses contribution | No core ART/evidence operation |
| Wrong policy version | Assignment/lease freeze before work; immutable published versions |
| Cross-domain deadlock | AUTH-first lock order and two-order PostgreSQL tests |
| Dispatcher gains feature authority | Exact dispatcher-only action plus independent handler authorization |
| Dynamic/broad service access | Closed ServiceIdentity/static rows, AUTH-09E, cross-service denial |
| Role coupling | Independent grants and role-specific invalidation consumers |
| Partial activation transfer | Consume complete WS-XINT AUTH handoffs, never local subsets |
| Legacy row ambiguity | Human-approved deterministic rebuild/classification before migration |
| Premature public surface | Hidden behavior until AUTH activation and joint release proof |
| Shutdown loses or admits fulfillment work | Shared fence before every writer ordinal; immutable cutoff; same-generation pre-cutoff completion only; exact drain counts |
| Adjudication leaks into v0.1 | No adjudication type/action/state/queue/readiness dependency; reject and accept remain terminal |

## Resolved FinalAcceptance policy lineage

Merged REV-04 retains the handoff's `policy_context_ref` field as a foreign key
to canonical immutable `ReviewPolicy.id` and retains `recorded_by` for the
reviewer ActorProfile. REV must enforce that exact locked policy and its same
project/task/Submission/Review lineage. CON adds no renamed aliases and does not
interpret review policy as contribution policy or award authority.

## Open questions

- Exact D11 AdminRole candidates for award detail, delivery recovery, and audit.
- Exact ServiceIdentity/ActionId/static-row contracts for delivery,
  reconciliation, projection rebuild, and callback execution.
- Deterministic treatment of pre-production legacy rows.
- Whether optional evidence projection is ever approved; it is not part of the
  current core plan.

## Conventions to preserve

- Review decisions are only `accept`, `needs_revision`, and `reject`.
- PostgreSQL owns canonical contribution/award/receipt truth.
- External I/O occurs only after commit and outside lifecycle/database locks.
- Domain participants flush and never commit.
- AUTH and feature repositories never cross-import.
- Fixed service identity is authorization; Celery executor/generation is
  separate execution fencing.
- `/api/v1` is the only public prefix.
