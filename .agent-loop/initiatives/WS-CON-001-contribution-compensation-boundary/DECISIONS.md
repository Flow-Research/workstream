# Decisions: WS-CON-001 Contribution Record And Compensation Boundary

## D1 - Canonical Contract Is Repository-Owned

**Status:** accepted.

The supplied reference files are archival inputs. The active implementation
contract is `docs/spec_contribution_compensation.md` plus ADR 0016, produced by
CON-01 and reconciled with trusted `main`, including AUTH PR #140, merged
AUTH-09B PR #143, and WS-XINT-001 PR #139. Archival files are not edited or
treated as runtime authority.

## D2 - ContributionPolicy Is The Only Award-Eligibility Policy

**Status:** accepted; supersedes the older WS-CON naming.

The canonical aggregate is `ContributionPolicy`, immutable
`ContributionPolicyVersion`, `ContributionRule`, and
`ContributionAwardDefinition`. It decides whether a ContributionRecord is
unpaid or creates money and/or project-points CompensationAwards. The retired
guide-bound economic schema is completely removed in CON-05A/05B. There is no
alias, automatic conversion, historical fallback, or second executable policy.

## D3 - Existing Submission Is The Version Identity

**Status:** accepted.

Existing `Submission` plus its `version` and `supersedes_submission_id` is the
versioned identity. ContributionRecord uses `submission_id` and the stabilized
artifact-hash lineage supplied by REV. WS-CON does not add a
`SubmissionVersion` table or reload artifact bytes through ART.

## D4 - AUTH Owns Registration, Evaluation, And Activation

**Status:** accepted by WS-XINT-001 D1/D2.

WS-CON proposes product actions and typed facts, but AUTH owns ActionId,
PermissionId mapping, ActionOwner activation custody, typed resource contexts,
principal admission, evaluator dispatch, decision evidence, grants, the fixed
service static matrix, and availability. Each action follows planned
registration -> hidden feature behavior -> AUTH evaluator integration and
activation. CON never changes availability or implements a local role fallback.

The stable PermissionIds may retain older broad namespace strings. New policy
ActionIds use `contribution.policy.*` and map to existing
`compensation.policy.manage`; the PermissionId string does not rename the
canonical product model.

## D5 - Derived Contributions And Awards Are Review Participants

**Status:** accepted by WS-XINT-001 D7 and the REV/CON handoff.

The authorized `review.decision` transaction invokes one mandatory CON
participant in the caller's AsyncSession. It creates a reviewer
`completed_review` for every committed Review. For accept only, REV first
creates FinalAcceptance and CON creates `accepted_submission` from that locked
fact, never directly from Review.decision. CON evaluates each applicable frozen
ContributionRule, stages applicable contribution/award rows, returns typed
audit/outbox inputs to REV, flushes, and never commits. REV stages the shared
audit/outbox records and owns the single commit. There is no `contribution.materialize` or
`compensation.award.materialize` action and no no-op production participant.

## D6 - ART Is Not A Core Contribution Dependency

**Status:** accepted by WS-XINT-001 D7; supersedes the prior mandatory evidence
design.

Core contribution creation performs no ART capability call, artifact
authorization, provider I/O, or evidence projection. CON copies the stabilized
Submission/packet digest supplied by REV into
`ContributionRecord.artifact_hash` and does not verify or rederive it.

An evidence document may be proposed later only as an optional asynchronous
projection with independent status/failure semantics, a separately reviewed ART
capability, and a separate AUTH action. Its failure cannot alter Review,
ContributionRecord, CompensationAward, fulfillment receipt, or status truth.

## D7 - Shared Outbox Is A Prerequisite

**Status:** accepted through ADR 0016 and explicit CON-01 start.

One generic shared outbox owns append, claim, retry, dead-letter, replay, and
finalization mechanics. Feature handlers return typed outcomes and do not query
or mutate outbox persistence directly. No review-private or compensation-
private dispatcher is allowed.

## D8 - Coherent Public Activation

**Status:** accepted through ADR 0016 and explicit CON-01 start.

Contribution-policy, binding, contribution, award, callback, and operations
routes remain hidden until exact AUTH actions/evaluators/principals, required
REV participants, outbox/audit, migrations, and release proof are complete.
Optional contribution-evidence projection is not a release dependency.

## D9 - External Rails Fulfill Awards But Never Decide Eligibility

**Status:** accepted.

Workstream persists immutable awards, exact outbound instructions, delivery
evidence, immutable fulfillment receipts, and rebuildable status. External
money settlement and project-points adapters own provider execution, accounts,
balances, and ledger entries. They cannot create, change, void, or infer award
eligibility.

## D10 - AUTH Owns Prepared Cross-Domain Mutation Authorization

**Status:** required architecture contract.

AUTH locks and revalidates human actor/link/grant rows or fixed-service
actor/link rows first. Fixed services additionally require immutable
ServiceIdentity, exact static service-action matrix membership, AUTH-09E typed
admission, and active action as code-owned validations rather than lock targets.
AUTH returns one opaque, single-use `PreparedAuthorizationHandle` bound exactly
to session, ActionId, actor-reference kind/reference, idempotency key, and
canonical request digest. The feature then locks product rows and recomposes
final typed facts; AUTH consumes the handle, evaluates exactly once, and stages
decision evidence. AUTH and feature participants flush only; the route or
service command commits once.

Missing, reused, serialized, caller-constructed, cross-session/action/actor/
request, binding-mismatched, or authority-lost handles fail closed before
feature mutation. A failed substitution does not consume an otherwise valid
handle. Product-first locks, unlocked resource snapshots, double decisions,
and feature-side catalogue changes are rejected.

## D11 - Project Roles Are Independent; Admin Candidate Differences Remain Exact

**Status:** project-role model resolved by ADR 0015; AdminRole surface choices
remain human gates before CON-10A/10B.

The current shipping path requires exact `submitter` for task claim and exact
`reviewer` plus no-self-review for review claim/decision. Any unrelated project
or administrative grant does not substitute. The existing global AUTH project-
role catalogue remains AUTH-owned, but WS-CON adds no adjudication grant,
action, invalidation consumer, or readiness dependency.

Merged AUTH currently gives Finance Authority
`compensation.delivery.reconcile` but not Operator, while the earlier WS-CON
candidate also proposed reason-bound Operator recovery. Merged Project Manager
has `compensation.award.read`, while the earlier candidate narrowed award
detail. Audit candidates also differ. The human must select each exact action
candidate set before registration. Any change is AUTH-owned and evaluator-
closed; CON never queries roles or infers access from PermissionId membership.

## D12 - ActionOwner Is AUTH Activation Custody

**Status:** resolved by WS-XINT-001 D1-D3; no local alternative remains.

AUTH must provide one exact activation custodian for each proposed CON action
and complete, not partially repeat, the canonical transfers for all current ART
and REV actions. Every ActionId-to-PermissionId mapping is preserved, and closed
typed/SQL/audit/definition-owner parity rejects dual, missing, unused, or extra
owners. WS-CON depends on review.claim/review.decision but does not prescribe a
two-action REV transfer or an eleven-action ART subset.

## D13 - Fixed Service Admission Uses Static Matrix Membership

**Status:** accepted architecture; exact new identities/actions remain an
AUTH/human registration gate.

There is no database service-grant or service-action-assignment model. A fixed
service uses verified token -> ActorIdentityLink -> service ActorProfile ->
immutable closed ServiceIdentity -> exact static ActionId row -> AUTH-09E typed
context -> feature resource facts -> decision.

The shared outbox dispatcher may only claim/invoke/finalize outbox work under
`outbox.dispatch`; it does not inherit protected handler or provider authority.
Outbound delivery, asynchronous reconciliation, contribution projection
rebuild, and fulfillment callback each require an exact approved service
identity/action/static row or an explicitly approved closed dual-principal
evaluator before implementation. Missing provisioned rows deny runtime but do
not prevent application startup or administrative provisioning.

## D14 - Optional Evidence Is A Deferred Successor

**Status:** deferred and not approved for implementation.

CON-09A/09B are outside the core dependency order. If the human later approves
them, their chunk contracts must be refreshed against then-current ART/AUTH
contracts and internally reviewed again. The optional evidence action is not
counted as a core release action and cannot gate product reads or release.

## D15 - FinalAcceptance Is The Sole Submitter-Acceptance Source

**Status:** accepted by explicit human direction on 2026-07-17; REV merge is an
upstream implementation gate.

REV owns immutable FinalAcceptance and creates it only inside an authorized
`Review(accept)` transaction. There is no manual/public create API and no
separate authorization action: creation is a lifecycle consequence of the
already-authorized review operation. `needs_revision` and `reject` create none.

The non-accept effects follow REV's canonical lifecycle: `needs_revision` sets
the Task to `needs_revision` and keeps its TaskAssignment `active`; `reject`
sets the Task to `rejected` with a bounded human reason and blocks only the
same-task TaskAssignment with its source Review. Reject changes no grant or
unrelated task. The archival `closed/review_rejected` wording is not adopted.

The repository's existing immutable `Submission` row is already the submission
version identity. Therefore FinalAcceptance stores canonical `submission_id`,
not `submission_version_id`, and enforces unique task, source Review, and
Submission lineage. Merged REV-04 retains `policy_context_ref` as the foreign
key to canonical immutable `ReviewPolicy.id` and retains `recorded_by` as the
reviewer ActorProfile field; REV proves the locked same-chain lineage. CON adds
no aliases and does not interpret review policy as contribution policy or use
it to decide awards.

`completed_review` keeps direct Review/ReviewLease lineage and is unique per
Review. `accepted_submission` requires `source_final_acceptance_id` plus the
exact TaskAssignment and is unique per FinalAcceptance; its direct
`source_review_id` is null because the FinalAcceptance already owns that link.
Database checks enforce the mutually exclusive source shapes.

REV creates Review and optional FinalAcceptance, applies task/assignment
effects, invokes the mandatory CON flush-only participant, stages shared audit/
outbox records, and commits once. CON failure rolls the entire unit back. ART
and provider calls remain absent; fulfillment begins asynchronously after
commit. V0.1 has no adjudication policy, queue, lease, state, decision,
contribution type, branch, action, readiness check, or initiative dependency.

## D16 - AUTH Planning And Provisioning Do Not Activate CON

**Status:** accepted by merged AUTH PR #140 and AUTH-09B PR #143 on 2026-07-17.

Trusted main `053242b` after AUTH-09B has 74 PermissionIds, 65 ActionIds, ten
active actions, and 55 planned actions, with no registered CON or task-claim
ActionId. AUTH-09B activates only `actor.service.provision`; its controlled
human-administrator route can create the ActorProfile/ActorIdentityLink for an
already-approved closed ServiceIdentity but grants no service execution,
runtime admission, role, grant, or database action assignment. PR #140 supplies
the exact prepared protocol, complete ART/REV custody maps, and feature-manifest
activation rule; those runtime implementations remain upstream work.

CON removes speculative `AUTH_CON_*` owner labels. Its proposed action mappings
remain unregistered and non-final until each complete feature manifest exists
and AUTH assigns an exact `WS-AUTH-001-*` custodian. Only the `task.claim`
PermissionId exists today; AUTH-13 must not register or activate a task-claim
ActionId before task-owned composition consumes CON-05A's immutable
TaskAssignment policy freeze. `review.claim` similarly consumes CON-06 through
REV, and `review.decision` consumes CON-07 through the rollback-safe REV-owned
transaction. AUTH alone registers/evaluates/activates; CON alone supplies its
hidden facts and participants. Future CON fixed services require new reviewed
ServiceIdentity/static-matrix additions and later AUTH-09E admission; AUTH-09B
does not make the current ART-only fixed identity set reusable by CON.

## D17 - Review Contribution Integration Uses Two Ordered Operations

**Status:** accepted from merged REV PR #128 on 2026-07-17.

One mandatory CON participant exposes two operation-specific flush-only methods
in REV's caller session. The reviewer method runs after immutable Review/
finding/resolution creation plus lease/queue closure and before the decision
branch. It accepts no FinalAcceptance, submitter source, or submitter policy.
The submitter method exists only after `accept` creates FinalAcceptance and
applies accepted Task/TaskAssignment effects. It accepts no direct Review/
ReviewLease contribution-source shape. An omnibus input with nullable
FinalAcceptance or both actors' policy contexts is prohibited.

Each method evaluates only its frozen ContributionRule, creates its own
contribution and eligible awards, returns typed shared-audit/outbox inputs, and
never commits. REV collects the invoked results, stages the shared rows, and
the request route or service command commits once.

## D18 - REV Owns One Joint Controller; CON Supplies Fenced Fulfillment Hooks

**Status:** accepted from merged REV PR #128 on 2026-07-17.

REV-12A owns the sole PostgreSQL `JointLifecycleReleaseControl` and shared
`JointLifecycleMutationFence`. CON creates no parallel phase/controller. Every
fulfillment-obligation root creation, requeue, successor, and repair writer
must acquire that fence before it allocates one immutable, monotonically
increasing root ordinal or locks obligation rows.

CON's same-session drain observation returns outbox/fulfillment counts and the
current maximum ordinal. REV atomically persists that value as the generation
cutoff after admitted writers drain. During `delivery_draining`, dispatch and
callback may finalize only a same-generation root at or below the cutoff and
cannot create follow-on obligations. Provider I/O occurs after the fenced
pre-I/O transaction commits and releases every database/advisory lock.

## D19 - Economic Quantities And Provider Receipts Are Bounded Canonical Facts

**Status:** accepted through ADR 0016 security review.

All policy definitions, immutable awards, and fulfilled quantities use
`NUMERIC(38, 18)` with canonical decimal-string input, common Pydantic,
application, and PostgreSQL bounds, and no binary float, exponent, rounding, or
conversion path. Money units are enabled uppercase ISO 4217 codes;
project-points unit identity is `(project_id, unit_code)`.

Immutable fulfillment receipts store only closed status/failure facts,
binding-scoped bounded non-secret opaque event/reference identifiers, exact
quantities, and canonical digests. Raw provider secrets, authentication tokens,
unbounded bodies, free-form messages/codes, headers, signatures, endpoints,
credentials, URLs, markup, or metadata are never persisted, logged, emitted,
exported, or returned. The bounded receipt identifiers are not authentication
tokens and may appear only in their canonical receipt/status fields. Unknown
provider failures map to the closed generic failure code before persistence.
