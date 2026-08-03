# Canonical REV-AUTH Action Custody

This table is the planning source of truth for the v0.1 review and human-revision authorization surface. `WS-XINT-003-02C` completes all approved REV registration, fixed-principal, matrix, and database parity while keeping every lifecycle action unavailable. XINT-002 rows retain their runtime owners.

## Human and privileged actions

| ActionId | PermissionId | Principal and scope | Resource family | Surface owner | State | Activation wave |
|---|---|---|---|---|---|---|
| `project.review_policy.update` | `project.review_policy.manage` | Project Manager grant for exact project | draft guide + ReviewPolicy version | project/REV semantics; AUTH mutation | active | `WS-XINT-003-02B` after 02A lineage |
| `project.revision_policy.update` | `project.review_policy.manage` | Project Manager grant for exact project | draft guide + RevisionPolicy version | project/REV semantics; AUTH mutation | active | `WS-XINT-003-02B` after 02A lineage |
| `review.queue.read` | `review.queue.read` | reviewer grant; exact project; self-review denied | concealed current-work view | REV | registered planned | `WS-XINT-003-03A` |
| `review.claim` | `review.claim` | reviewer grant; exact project; self-review denied | queue entry + global reviewer lease state | REV | registered planned | `WS-XINT-003-03B` |
| `review.release` | `review.release` | owning reviewer and active lease | ReviewLease | REV | registered planned | `WS-XINT-003-03C` |
| `review.decline_preference` | `review.decline_preference` | offered reviewer for exact project | review preference | REV | registered planned | `WS-XINT-003-03C` |
| `review.preference_expiry.run` | `operations.timer.run` | fixed preference-expiry service only | due preference row | REV | registered planned | `WS-XINT-003-03D` |
| `review.lease_expiry.run` | `operations.timer.run` | fixed lease-expiry service only | due ReviewLease | REV | registered planned | `WS-XINT-003-03D` |
| `review.context.read` | `submission.read_for_review` | owning reviewer and active exact lease | immutable packet/context | REV | registered planned | `WS-XINT-003-04` |
| `review.finding_evidence.ingest` | `review.decision` | future reviewer evidence-upload scope | future evidence slot | REV | registered planned/unavailable | future separate REV-owned intent |
| `review.chain.read` | `review.chain.read` | owning reviewer and active exact lease | bounded task/Submission review chain | REV | registered planned | `WS-XINT-003-04` |
| `review.decision` | `review.decision` | owning reviewer and active exact lease | Review + findings/resolutions + lifecycle effects | REV | registered planned | `WS-XINT-003-06` |
| `review.finding_response_evidence.ingest` | `submission.create` | future contributor evidence-upload scope | future response evidence slot | REV | registered planned/unavailable | future separate REV-owned intent |
| `review.queue.inspect` | `review.queue.inspect` | Operator; bounded/redacted operational scope | queue operational view | REV | registered planned | `WS-XINT-003-08A` |
| `review.lease.force_release` | `review.lease.force_release` | Operator; canonical reason required | exact ReviewLease | REV | registered planned | `WS-XINT-003-08A` |
| `review.queue.routing.override` | `review.queue.override` | Operator; canonical reason required | exact queue entry/routing state | REV | registered planned | `WS-XINT-003-08A` |
| `review.queue.routing.correct` | `review.queue.override` | Operator; canonical reason required | exact invalid routing state | REV | registered planned | `WS-XINT-003-08A` |
| `review.queue.close` | `review.queue.override` | Operator; canonical reason required | exact stale queue entry | REV | registered planned | `WS-XINT-003-08A` |
| `review.revision_context.repair` | `project.task.manage` | Project Manager grant for exact project | invalid revision context | REV | install unavailable in 02C | `WS-XINT-003-08A` |
| `review.revision_obligation.close` | `project.task.manage` | Project Manager grant for exact project | exact unfulfillable obligation | REV | install unavailable in 02C | `WS-XINT-003-08A` |
| `review.revision_context.legacy_close` | `operations.reconcile.run` | Operator; canonical reason required | exact legacy revision context | REV | install unavailable in 02C | `WS-XINT-003-08A` |
| `review.lifecycle.activation.manage` | `operations.reconcile.run` | Operator; exact phase and reason | lifecycle release controller | REV | install unavailable in 02C | `WS-XINT-003-08B` |
| `review.reconcile.run` | `operations.reconcile.run` | one of two fixed reconciler identities | invalidation or general reconciliation batch | REV | registered planned | `WS-XINT-003-08B` |
| `review.artifact_reference.reconcile` | `operations.reconcile.run` | fixed artifact-reference reconciler only | bounded review artifact reference batch | REV | registered planned | `WS-XINT-003-08B` |
| `review.projection.rebuild` | `operations.projection.rebuild` | fixed projection rebuilder only | derived review projection batch | REV | registered planned | `WS-XINT-003-08B` |

The 19 registered `review.*` rows move from historical `AUTH_REV_*` planning labels to these exact XINT-003 waves only as planning custody. Their runtime `ActionOwner` values change with each later activation, never in 01.

## Fixed-service closure

| ActionId | Exact identity | Static membership | Server-derived mode/scope | Forbidden principals | Required audit/provenance |
|---|---|---|---|---|---|
| `review.preference_expiry.run` | `workstream.review.preference_expiry` | this action only | `due_preference`; claimed IDs/cursor | every human and all other services | actor/link, due boundary, IDs/cursor, request/idempotency, decision event |
| `review.lease_expiry.run` | `workstream.review.lease_expiry` | this action only | `due_lease`; claimed IDs/cursor | every human and all other services | actor/link, expiry boundary, IDs/cursor, request/idempotency, decision event |
| `review.reconcile.run` | `workstream.review.authority_invalidation_reconciliation` | this action only | `authority_invalidation`; affected authority scope | every human and `workstream.review.reconciliation` | identity, mode, trigger, IDs/cursor, request/idempotency, decision event |
| `review.reconcile.run` | `workstream.review.reconciliation` | this action only | `general`; bounded project/time shard | every human and `workstream.review.authority_invalidation_reconciliation` | identity, mode, reason, shard/cursor, request/idempotency, decision event |
| `review.artifact_reference.reconcile` | `workstream.review.artifact_reference_reconciliation` | this action only | `artifact_reference`; bounded review/reference shard | every human and all other services | identity, reference IDs, reason, cursor, request/idempotency, decision event |
| `review.projection.rebuild` | `workstream.review.projection` | this action only | `projection_rebuild`; named projection/shard | every human and all other services | identity, projection, watermark, cursor, request/idempotency, decision event |
| `artifact.review_packet.materialize` | `workstream.artifact.materializer` | global matrix also contains pre/post-submit materialization; this is its review-surface action | exact active-lease packet manifest | every human and all other services | actor/link, lease/packet/Submission/content, digests, request/transaction, decision event |
| `artifact.review_evidence.binding.create` | `workstream.artifact.binding` | future ART review-surface action | no approved v0.1 mode; planned/unavailable | every principal | future REV-owned contract required before implementation |

The six REV identities are provisioned and admitted with their closed static
matrix in 02C while all associated actions remain unavailable. Provisioning is
not execution authority. Celery payloads contain identifiers and provenance
only, and every command prepares fresh authority inside its transaction.

## Externally owned shared actions

| ActionId | PermissionId | Principal/resource constraint | Runtime owner and planned wave |
|---|---|---|---|
| `artifact.review_packet.materialize` | `artifact.review_packet.materialize` | fixed ART materializer; exact active-lease packet | runtime `WS-XINT-002-07`; activation sub-wave `07A` |
| `artifact.review_evidence.binding.create` | `artifact.binding.create` | future fixed ART binding service only | runtime catalogue custody `WS-XINT-002-07`; no approved activation wave |
| `artifact.submission_bundle.prepare` | `submission.create` | assigned contributor; exact human-revision preparation | availability `WS-XINT-002-05A`; revision-context evaluator extension `05D` |
| `submission.create` | `submission.create` | assigned contributor; exact prepared human revision | availability `WS-XINT-002-05B`; revision-context evaluator extension `05D` |

These actions are not XINT-003 custody. Generic artifact download, adjudication, automated routing, reputation, settlement, and agent workspace authority are out of scope.

## AUTH readiness and activation gates by action

02C installs the complete unavailable catalogue/principal matrix and 02D
publishes the corresponding fail-closed PREP contract before REV lifecycle
implementation begins. The table below is an activation gate, not a prerequisite
for AUTH readiness.

| Stage | AUTH-owned readiness | REV-owned hidden proof | Final activation proof |
|---|---|---|---|
| Every approved v0.1 action | 02C registration/principal/matrix parity and 02D closed PREP contract; real kernel denies unavailable | Canonical rows, locks, composers, lifecycle guards, idempotency and side-effect ordering in the exact REV child | Named XINT wave connects only the merged composer/evaluator, proves crossed denial/concurrency/atomicity, and changes only the named availability rows |

Activation chunks may not add ActionIds, PermissionIds, service identities,
resource-context classes, adapter protocols, lifecycle rules, or product routes.
Any such discovery returns to 02C/02D planning.

| ActionId | Exact prerequisite behavior/manifest |
|---|---|
| `project.review_policy.update` | 02A immutable identity/lineage plus refreshed REV-03P/AUTH-12D2; activated only by `WS-XINT-003-02B` |
| `project.revision_policy.update` | 02A immutable identity/lineage plus refreshed REV-03P/AUTH-12D2; activated only by `WS-XINT-003-02B` |
| `review.queue.read` | merged REV-05A admission and REV-05B concealed current-work view |
| `review.claim` | merged REV-03B persistence, REV-06A claim behavior, CON-06 freeze, and exact ART packet proof |
| `review.release` | merged REV-06B owned release behavior |
| `review.decline_preference` | merged REV-06B preference behavior |
| `review.preference_expiry.run` | merged REV-06C preference timer command |
| `review.lease_expiry.run` | merged REV-06C lease timer command; expiry-versus-decision is re-proved with 06 |
| `review.context.read` | merged REV-07A context/packet membership plus XINT-002-07A packet materialization |
| `review.finding_evidence.ingest` | future only; approved v0.1 records note/findings without uploaded evidence |
| `review.chain.read` | merged REV-07A bounded chain behavior plus active context boundary |
| `review.decision` | merged REV-10 first canonical decision commit plus CON-03C/07, audit, and outbox proof; REV-08 alone is insufficient |
| `review.finding_response_evidence.ingest` | future only; requires separate approved REV evidence-upload intent |
| `review.queue.inspect` | merged REV-11A bounded/redacted queue inspection |
| `review.lease.force_release` | merged REV-11A force-release command |
| `review.queue.routing.override` | merged REV-11A override command |
| `review.queue.routing.correct` | merged REV-11A correction command |
| `review.queue.close` | merged REV-11A close command |
| `review.revision_context.repair` | 02C unavailable registration plus merged REV-11B covered-project repair command |
| `review.revision_obligation.close` | 02C unavailable registration plus merged REV-11B obligation-close command |
| `review.revision_context.legacy_close` | 02C unavailable registration plus merged REV-11D legacy-close command |
| `review.lifecycle.activation.manage` | 02C unavailable registration plus merged REV-12A4 lifecycle controller transition/recovery behavior |
| `review.reconcile.run` | merged REV-11C invalidation and general reconciliation commands |
| `review.artifact_reference.reconcile` | merged REV-12P2 artifact-reference command and typed ART repair port |
| `review.projection.rebuild` | merged REV-12P2 derived-projection command |
| `artifact.review_packet.materialize` | XINT-002-07A after hidden ART packet behavior and REV active-lease manifest |
| `artifact.review_evidence.binding.create` | future only; remains planned/unavailable in v0.1 |
| `artifact.submission_bundle.prepare` | XINT-002-05D after merged REV-09A1-09B human-revision preparation and replay behavior |
| `submission.create` | XINT-002-05D after merged REV-09A1-09B verified, consumable human-revision admission |
