# Discovery: WS-XINT-003 REV-AUTH End-to-End Contract

## Canonical references

- [Review lifecycle specification](../../../docs/spec_review_lifecycle.md)
- [Authorization service specification](../../../docs/spec_authorization_service.md)
- [Roles and permissions](../../../docs/operations_roles_permissions.md)
- [XINT-002 human-review revision owner](../WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-05D-human-review-revision.md)
- [XINT-002 reviewer artifact activation](../WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-07A-reviewer-artifact-activation.md)
- [XINT-002 response artifact extension](../WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-07B-response-artifact-extension.md)
- [Historical XINT-002 combined split record](../WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-07-review-artifact-activation.md)

## Baseline

Initial discovery was performed from `origin/main` merge `99dc0b34`, after
AUTH-12D. The 02 refresh re-ran discovery at merge `ad8da7e5`, after PRs #236
and #237. This refresh changes planning only and no application behavior.

## Current implementation and plans

- `backend/app/modules/authorization/catalogue.py` already declares the review
  queue, claim, release, preference, context, chain, evidence, decision,
  registered recovery/reconciliation/projection, and ART review actions. The
  four privileged lifecycle/recovery actions named below remain absent until
  the availability-neutral 08R registration wave.
- Migrations `0018`, `0021`, `0022`, `0023`, `0036`, and `0041` contain
  historical permission/action evidence and planned service mappings. Current
  availability and exact migration parity must be derived, never copied from
  historical counts in REV documents.
- `backend/app/modules/projects/models.py`, `schemas.py`, `repository.py`, and
  `service.py` contain existing `ReviewPolicy` and `RevisionPolicy` behavior.
  `backend/app/modules/projects/authorization_reads.py` locks and composes these
  policies into current project authorization facts.
- Current Alembic head is `0045_guide_metadata_authority`; the old PR #195
  migration descended from historical head 0033 and is preservation input, not
  a mergeable migration.
- `ProjectRepository.upsert_review_policy()`,
  `upsert_revision_policy()`, `ProjectService._review_policy_model()`, and
  `_revision_policy_model()` remain in current code but have no call sites.
  Their removal is therefore a clean-cut deletion, not a compatibility break.
- `ActionId.PROJECT_REVIEW_POLICY_UPDATE` and
  `PROJECT_REVISION_POLICY_UPDATE`, their catalogue mappings, and their strict
  typed resource contexts already exist. Both actions remain planned and the
  PREP service does not yet accept them.
- `GuideMutationService` and `guide_mutation_router.py` provide the current
  project-scoped PREP/idempotency/decision-evidence composition convention.
  Policy mutation must reuse that convention without turning guide mutation
  into a generic service locator or retaining a second writer path.
- AUTH-12D2 proposes separate review-policy and revision-policy mutation routes.
  REV-03P also proposes policy persistence. This is an ownership collision:
  there must be one persistence model and one mutation path.
- `WS-REV-001` defines hidden behavior from durable final/current checker
  `allow_review` admission through queue, lease, packet context, immutable
  decisions/findings/resolutions, human revision preparation, contribution
  integration, recovery, projection, and final release.
- `WS-XINT-002` owns `artifact.review_packet.materialize`,
  `artifact.review_evidence.binding.create`, and human-review revision artifact
  preparation/Submission binding. REV-AUTH must consume those exact merged
  manifests rather than duplicate them.

## Principal classes

### Human reviewer

Requires an active canonical human ActorProfile, active identity link, exact
project `reviewer` grant, no self-review conflict, and—after claim—one exact
active lease. Reviewer authority never comes from submitter/adjudicator grants,
an AdminRoleGrant alone, token roles, or queue visibility.

### Contributor in human revision

Requires an active exact-project submitter grant, active/replacement assignment,
the exact immutable human Review-rooted revision obligation and preparation
head/digest, predecessor Submission, required finding responses/evidence,
unexpired deadline, and remaining revision round. Checker remediation is a
separate CheckerRun-rooted variant.

### Project Manager and Operator

Project Managers configure policy and perform only exact covered-project repair
or obligation closure actions. Operators inspect bounded operational state and
perform explicitly reasoned recovery actions; they receive no reviewer decision
or artifact-read authority.

### Fixed services

Preference expiry, lease expiry, authority-invalidation reconciliation, general
review reconciliation, artifact-reference reconciliation, projection rebuild,
ART packet materialization, and ART evidence binding use separately admitted
fixed service identities and closed action matrices. A Celery payload carries
identifiers and provenance only, never a prepared handle or executable human
authority.

## Canonical action inventory to reconcile

Human reviewer actions:

- `review.queue.read`
- `review.claim`
- `review.release`
- `review.decline_preference`
- `review.context.read`
- `review.chain.read`
- `review.finding_evidence.ingest`
- `review.decision`

Contributor revision action:

- `review.finding_response_evidence.ingest`
- shared XINT-002 `artifact.submission_bundle.prepare` and `submission.create`
  with the closed human-review revision context

Project Manager actions:

- `project.review_policy.update`
- `project.revision_policy.update`
- `review.revision_context.repair`
- `review.revision_obligation.close`

Operator/administrative actions:

- `review.queue.inspect`
- `review.lease.force_release`
- `review.queue.routing.override`
- `review.queue.routing.correct`
- `review.queue.close`
- `review.revision_context.legacy_close`
- `review.lifecycle.activation.manage`

Fixed-service actions:

- `review.preference_expiry.run`
- `review.lease_expiry.run`
- `review.reconcile.run` with two separately admitted identities where the
  product contract requires separate invalidation and general reconciliation
- `review.artifact_reference.reconcile`
- `review.projection.rebuild`
- XINT-002 `artifact.review_packet.materialize`
- XINT-002 `artifact.review_evidence.binding.create`

## Required resource facts

The union of typed feature-owned contexts includes actor and identity link,
project and exact role grant, task, assignment, finalized Submission and
predecessor, final/current CheckerRun admission, queue entry, preference,
ReviewLease and frozen policies, packet manifest and verified bindings,
predecessor Review, findings/responses/resolutions, decision request, revision
obligation and preparation head/digest, deadline/round, guide and policy
versions, lifecycle phase, operation/idempotency/request digest, session/root
transaction, and fixed-service identity where applicable.

No single omnibus nullable context should represent every action. Each action
needs a closed typed context with only its valid shape.

## Existing tests and gaps

- `backend/tests/test_authorization.py` proves planned catalogue presence and
  some role/service matrices, but not the complete live REV transaction chain.
- REV planning calls for PostgreSQL immutability, concurrency, replay, lease,
  and decision/CON tests; most runtime modules and tests do not exist yet.
- XINT-002 covers artifact-side activation contracts but cannot prove reviewer
  lease or revision-obligation semantics before REV implements them.
- Missing end-to-end proof includes self-review races, lease expiry versus
  decision, revocation versus decision, stale packet/version, finding evidence
  binding versus decision, predecessor advancement, revision deadline/round
  exhaustion, replacement contributor authority, and recovery-vs-live-command
  crossings.

## Dependencies

- AUTH-12D2 and REV-03P must be reconciled before either policy writer is built.
- The reconciled implementation is split: 02A can merge because it activates
  no route/action and removes only unused mutation callables; 02B is the only
  action-availability and external-writer transition.
- REV hidden feature chunks must merge before matching AUTH action activation.
- XINT-002 remains the sole activation owner for ART review-artifact actions and
  shared human-review submission actions. WS-XINT-003-01 split the combined
  review-artifact contract into 07A finding availability and 07B response
  evaluation after the human revision obligation exists.
- CON atomic participant and FinalAcceptance integration must merge before
  `review.decision` activation.
- Final product routes remain absent until the complete dependency conformance
  wave passes.

## Risks discovered

- The entry REV plan contained obsolete signed-start and generated-loop gates;
  WS-XINT-003-01 removed them from current authority while preserving relevant
  historical provenance.
- Historical action counts and owner chunk names are stale after many AUTH/ART
  migrations and cannot be used as exact implementation inputs.
- `review.finding_evidence.ingest -> review.decision` and
  `review.finding_response_evidence.ingest -> submission.create` share
  permissions but remain distinct actions and resource shapes.
- `review.reconcile.run` serves separate fixed identities but has one global
  ActionId availability. Both identities therefore remain planned until one
  shared activation wave; service identity still determines server-derived mode
  and scope after activation.
- `review.revision_context.repair`, `review.revision_context.legacy_close`,
  `review.revision_obligation.close`, and `review.lifecycle.activation.manage`
  are approved manifests but are absent from the current closed catalogue. They
  require an availability-neutral registration wave before activation.

## Unknowns to resolve at each activation wave

- Exact merged feature symbol/manifest and migration head at chunk start.
- Exact bounded fields for queue inspection and chain/context reads.
- Provisioning/migration state for the exact fixed identities named in
  `ACTION_CUSTODY.md` on then-current main.

These are implementation-time evidence questions, not reasons to place product
lifecycle logic in AUTH.
