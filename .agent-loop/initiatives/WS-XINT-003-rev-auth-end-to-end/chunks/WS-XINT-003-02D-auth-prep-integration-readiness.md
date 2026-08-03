# Chunk Contract: WS-XINT-003-02D — AUTH PREP Integration Readiness

## Status

Implementation-ready contract refreshed from merged 02C at `745d9c3f`.

## Parent initiative

`WS-XINT-003` — REV-AUTH End-to-End Contract.

## Goal

Publish one complete fail-closed PREP integration surface for every approved
REV action so REV can implement its lifecycle using stable AUTH contracts
without AUTH implementing or interpreting REV product state.

## Why this chunk exists

Registration alone does not tell REV how to bind canonical locked facts to an
opaque prepared capability. Deferring each interface until activation causes
per-chunk AUTH discovery. This chunk closes those interfaces once while every
lifecycle action remains unavailable.

## Risk class and SLA

L1 authorization protocol and cross-subsystem boundary. No expedited review
SLA.

## Allowed files

Only these exact paths may change:

```text
backend/app/modules/authorization/review_contracts.py
backend/tests/test_review_authorization_contracts.py
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/ACTION_CUSTODY.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/REVIEW_LOG.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/chunks/WS-XINT-003-02D-auth-prep-integration-readiness.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02D-internal-review.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02D-pr-trust-bundle.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02D-external-review-response.md
```

## Not allowed changes

- No imports of REV repositories/models into AUTH evaluation or PREP custody.
- No REV lifecycle loaders, lock orchestration, queue/lease mutation, decision,
  revision behavior, routes, service jobs, or product persistence.
- No action activation, fixed-service execution, XINT-002 ownership change, or
  serialized prepared handle.
- No omnibus nullable resource context, generic dictionary/service locator,
  local REV policy engine, fallback authority, or role-only shortcut.
- No edit to `runtime.py`, `prepared.py`, `kernel.py`, `catalogue.py`, service
  identity registration, migrations, routes, workers, or REV product code.
- No XINT-002 contract implementation. Shared ART/submission rows are manifest
  references only and retain their existing owners, types, and activation gates.

## Closed contract families

`review_contracts.py` publishes strict frozen Pydantic models containing only
scalar identifiers, closed enums, digests, bounded reasons/timestamps and
server-composed booleans/counts. It defines no repository, loader, evaluator,
callback, ORM value, byte-bearing field, or authorization handle. The manifest
maps every XINT-003 action below to exactly one family and execution mode.

| Contract family | Exact XINT-003 actions | Required final facts |
|---|---|---|
| concealed queue | `review.queue.read` | a minimal `none` shape contains project, reviewer/grant, policy, phase and queue-state digest only; offer/active-lease shapes additionally bind queue entry/lease when present, task, assignment, Submission, CheckerRun admission, no-self-review actors and exact lineage |
| claim | `review.claim` | concealed-queue facts plus claim operation, idempotency, queue generation, reviewer global active-lease count, reviewer contribution-policy identity/generation/digest, packet-manifest digest |
| lease mutation | `review.release`, `review.lease_expiry.run`, `review.lease.force_release` | project, queue entry, lease/generation, reviewer, task, Submission, lease status/expiry, lifecycle phase, reason or due boundary, lease-state digest |
| preference mutation | `review.decline_preference`, `review.preference_expiry.run` | project, queue entry, preference/generation, preferred reviewer, source Review, source Submission, status/expiry, reason or due boundary, preference-state digest |
| reviewer reads | `review.context.read`, `review.chain.read` | project, task, assignment, exact active lease/reviewer, packet manifest, current Submission and binding, chain boundary/digest, lifecycle phase; chain read also binds requested subject actor and bounded cursor |
| decision | `review.decision` | mutually exclusive `initial` and `revision` shapes both bind project, task, assignment, current Submission, CheckerRun admission, queue entry, active lease/reviewer, packet manifest, Review operation, decision, findings/resolution digest, ReviewPolicy and reviewer ContributionPolicy freezes, artifact hash and lifecycle digest; the revision shape additionally requires a distinct predecessor Review/Submission, revision episode, exact preparation head generation/digest, and finding-response lineage/count |
| operator queue | `review.queue.inspect`, `review.queue.routing.override`, `review.queue.routing.correct`, `review.queue.close` | bounded project/shard, queue entry/generation when mutating, task, Submission, current routing/lease facts, requested mode, canonical reason, lifecycle phase, queue-state digest |
| reconciliation | `review.reconcile.run` | fixed execution mode, project/shard, trigger, bounded cursor, finding IDs digest, observed watermark/time, lifecycle phase/digest |
| artifact-reference reconciliation | `review.artifact_reference.reconcile` | project/shard, exact review/reference set digest, bounded cursor, reason, observed watermark, lifecycle phase/digest |
| projection rebuild | `review.projection.rebuild` | named projection, project/shard, source watermark, bounded cursor, source-event digest, lifecycle phase/digest |
| revision repair | `review.revision_context.repair` | project, task, source/current assignment, prior Submission, originating needs-revision Review, episode, exact head ID/digest/generation, canonical `kept`/`rebased`/`blocked` outcome and forward/backward direction, server-proven repairability, current guide and ReviewPolicy/RevisionPolicy identity triples, replacement assignment when any, canonical reason, lifecycle digest |
| revision obligation close | `review.revision_obligation.close` | project, task, assignment, originating needs-revision Review, episode/head, frozen revision-policy identity/generation/digest, approved limit/deadline facts, exact reached cause, lifecycle digest |
| legacy close | `review.revision_context.legacy_close` | reconciliation finding, project, task, assignment, optional queue, absence-of-recoverable-root proof digest, CheckerRun-remediation exclusion, canonical reason, lifecycle digest |
| lifecycle activation | `review.lifecycle.activation.manage` | singleton, operation, expected generation/current phase, adjacent target phase, reviewed manifest digest, drain observations digest, bounded batch/deadline, canonical reason |

The two future evidence-upload actions are manifest entries with execution mode
`unsupported_future_intent`, no resource model, and no prepare/consume support:
`review.finding_evidence.ingest` and
`review.finding_response_evidence.ingest`.

Every shared contract family carries its exact closed `action_id`; family-local
mode/reason fields are action-specific and validated so sibling actions cannot
substitute for one another. Every fixed-service model also carries the exact
`service_identity` and a closed server-derived `execution_mode`. In particular,
the two identities admitted for `review.reconcile.run` have disjoint modes and
tests must reject either identity using the other's mode.

Externally owned `artifact.review_packet.materialize`,
`artifact.review_evidence.binding.create`, `artifact.submission_bundle.prepare`,
and `submission.create` appear only in a closed external-handoff reference map.
02D must not define replacement contexts or adapters for them.

The already-active `project.review_policy.update` and
`project.revision_policy.update` rows are closed references to their existing
`ProjectReviewPolicyMutationResourceContext` and
`ProjectRevisionPolicyMutationResourceContext`; 02D neither replaces nor
changes those proven 02B contracts.

Every mutation/service contract includes exact operation/idempotency/request
binding through the existing `PreparedAuthorizationInput` and opaque
`PreparedAuthorizationHandle`; those protocol values are deliberately not
fields of the resource models. Read contracts use request-scoped evaluation,
not PREP consumption. Later activation adapters must revalidate actor and exact
identity link plus matched grant, or the exact fixed-service identity, before
evaluating these final server-composed facts.

## Acceptance criteria

- A closed action-to-resource-contract manifest covers every approved v0.1
  human, Project Manager, Operator, and fixed-service action in
  `ACTION_CUSTODY.md`; future evidence-upload actions remain explicitly
  unavailable and unsupported for execution.
- Contracts use typed stable identifiers, enums, digests, bounded timestamps,
  reasons, modes, and lineage facts. They contain no ORM rows, bytes, extracted
  content, provider credentials, scratch paths, or executable callbacks.
- REV remains responsible for locking its canonical rows and composing the
  exact final context. AUTH validates identity/link/grant or fixed-service
  authority, action, request digest, session/root transaction, resource digest,
  staleness inputs, and single-use consumption.
- The existing opaque `PreparedAuthorizationHandle` remains the only durable-
  boundary protocol. It is process-local, non-serializable, action-bound,
  principal-bound, session-bound, transaction-bound, resource-bound, and
  single-use.
- Unavailable actions fail closed at prepare and consume. Publishing a contract
  does not grant runtime authority.
- Existing PREP regression tests continue to prove copied, reconstructed,
  serialized, replayed, wrong-session, wrong-transaction, wrong-action,
  wrong-principal, revoked, and unavailable denial. New contract tests prove
  strict construction, action/mode/identity parity, cross-resource and stale-
  digest distinction, handle exclusion, and serialization-safe scalar shapes.
- Static scans prove Celery payloads cannot carry handles and AUTH does not
  import REV product repositories or implement lifecycle rules.
- The interface includes enough exact fields for REV to implement every later
  action without requesting a new AUTH protocol or context family. Any omission
  returns to planning before merge.

## Verification commands

```bash
cd backend
ruff check app/modules/authorization/review_contracts.py tests/test_review_authorization_contracts.py
mypy app/modules/authorization/review_contracts.py
.venv/bin/pytest -q tests/test_review_authorization_contracts.py
.venv/bin/coverage erase
.venv/bin/coverage run -m pytest -q tests/test_review_authorization_contracts.py
.venv/bin/coverage report --include='app/modules/authorization/review_contracts.py' --precision=2 --fail-under=90
cd ..
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_review_contracts.py
```

The PR exact head must also pass GitHub `Backend` including all five PostgreSQL
lanes and the aggregate repository-wide `coverage --fail-under=78`, plus Agent
Gates. No local full-suite execution is required on the user machine.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
test delta, reuse/dedup, and docs.

## Human review focus

Confirm the surface is complete enough for REV to build against while AUTH
does not own lifecycle facts or make any lifecycle action executable.

## Stop conditions

Stop on any need for AUTH to load REV state, any missing catalogue/principal
from 02C, any new protocol, or any action becoming available. Merge this chunk
and stop. REV may then begin its lifecycle implementation; later XINT chunks
perform bounded integrated activation.
