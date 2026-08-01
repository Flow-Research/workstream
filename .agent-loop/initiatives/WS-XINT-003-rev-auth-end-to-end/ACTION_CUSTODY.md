# Canonical REV-AUTH Action Custody

This table is the planning source of truth for the v0.1 review and human-revision authorization surface. `WS-XINT-003-01` changes documentation only: every registered REV action remains `planned`, the four registration rows do not yet exist, and XINT-002 rows retain their runtime owners.

## Human and privileged actions

| ActionId | PermissionId | Principal and scope | Resource family | Surface owner | State | Activation wave |
|---|---|---|---|---|---|---|
| `project.review_policy.update` | `project.review_policy.manage` | Project Manager grant for exact project | draft guide + ReviewPolicy version | project/REV semantics; AUTH mutation | registered planned | `WS-XINT-003-02B` after 02A lineage |
| `project.revision_policy.update` | `project.review_policy.manage` | Project Manager grant for exact project | draft guide + RevisionPolicy version | project/REV semantics; AUTH mutation | registered planned | `WS-XINT-003-02B` after 02A lineage |
| `review.queue.read` | `review.queue.read` | reviewer grant; exact project; self-review denied | concealed current-work view | REV | registered planned | `WS-XINT-003-03A` |
| `review.claim` | `review.claim` | reviewer grant; exact project; self-review denied | queue entry + global reviewer lease state | REV | registered planned | `WS-XINT-003-03A` |
| `review.release` | `review.release` | owning reviewer and active lease | ReviewLease | REV | registered planned | `WS-XINT-003-03A` |
| `review.decline_preference` | `review.decline_preference` | offered reviewer for exact project | review preference | REV | registered planned | `WS-XINT-003-03A` |
| `review.preference_expiry.run` | `operations.timer.run` | fixed preference-expiry service only | due preference row | REV | registered planned | `WS-XINT-003-03B` |
| `review.lease_expiry.run` | `operations.timer.run` | fixed lease-expiry service only | due ReviewLease | REV | registered planned | `WS-XINT-003-03B` |
| `review.context.read` | `submission.read_for_review` | owning reviewer and active exact lease | immutable packet/context | REV | registered planned | `WS-XINT-003-04` |
| `review.finding_evidence.ingest` | `review.decision` | owning reviewer and active exact lease | finding slot + verified commitment | REV | registered planned | `WS-XINT-003-04` |
| `review.chain.read` | `review.chain.read` | owning reviewer and active exact lease | bounded task/Submission review chain | REV | registered planned | `WS-XINT-003-05` |
| `review.decision` | `review.decision` | owning reviewer and active exact lease | Review + findings/resolutions + lifecycle effects | REV | registered planned | `WS-XINT-003-06` |
| `review.finding_response_evidence.ingest` | `submission.create` | assigned contributor; exact human-revision obligation | response slot + preparation + predecessor | REV | registered planned | `WS-XINT-003-07` |
| `review.queue.inspect` | `review.queue.inspect` | Operator; bounded/redacted operational scope | queue operational view | REV | registered planned | `WS-XINT-003-08A` |
| `review.lease.force_release` | `review.lease.force_release` | Operator; canonical reason required | exact ReviewLease | REV | registered planned | `WS-XINT-003-08A` |
| `review.queue.routing.override` | `review.queue.override` | Operator; canonical reason required | exact queue entry/routing state | REV | registered planned | `WS-XINT-003-08A` |
| `review.queue.routing.correct` | `review.queue.override` | Operator; canonical reason required | exact invalid routing state | REV | registered planned | `WS-XINT-003-08A` |
| `review.queue.close` | `review.queue.override` | Operator; canonical reason required | exact stale queue entry | REV | registered planned | `WS-XINT-003-08A` |
| `review.revision_context.repair` | `project.task.manage` | Project Manager grant for exact project | invalid revision context | REV | missing-to-register | `WS-XINT-003-08R` then `08A` |
| `review.revision_obligation.close` | `project.task.manage` | Project Manager grant for exact project | exact unfulfillable obligation | REV | missing-to-register | `WS-XINT-003-08R` then `08A` |
| `review.revision_context.legacy_close` | `operations.reconcile.run` | Operator; canonical reason required | exact legacy revision context | REV | missing-to-register | `WS-XINT-003-08R` then `08A` |
| `review.lifecycle.activation.manage` | `operations.reconcile.run` | Operator; exact phase and reason | lifecycle release controller | REV | missing-to-register | `WS-XINT-003-08R` then `08B` |
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
| `artifact.review_evidence.binding.create` | `workstream.artifact.binding` | global matrix also contains guide/submission/checker binding; this is its review-surface action | 07A `reviewer_finding`; 07B adds `contributor_response`; exact slot/content | every human and all other services; response mode denied until 07B | identity, mode, review/lease or obligation/preparation, slot/content, request/transaction, decision event |

The six proposed REV identities are fixed planning names; they are not provisioned or admitted until their activation chunks. Celery payloads contain identifiers and provenance only, and every command prepares fresh authority inside its transaction.

## Externally owned shared actions

| ActionId | PermissionId | Principal/resource constraint | Runtime owner and planned wave |
|---|---|---|---|
| `artifact.review_packet.materialize` | `artifact.review_packet.materialize` | fixed ART materializer; exact active-lease packet | runtime `WS-XINT-002-07`; activation sub-wave `07A` |
| `artifact.review_evidence.binding.create` | `artifact.binding.create` | fixed ART binding service; exact finding/response slot | runtime `WS-XINT-002-07`; availability sub-wave `07A`, evaluator extension `07B` |
| `artifact.submission_bundle.prepare` | `submission.create` | assigned contributor; exact human-revision preparation | availability `WS-XINT-002-05A`; revision-context evaluator extension `05D` |
| `submission.create` | `submission.create` | assigned contributor; exact prepared human revision | availability `WS-XINT-002-05B`; revision-context evaluator extension `05D` |

These actions are not XINT-003 custody. Generic artifact download, adjudication, automated routing, reputation, settlement, and agent workspace authority are out of scope.

## Hidden-feature dependencies by action

| ActionId | Exact prerequisite behavior/manifest |
|---|---|
| `project.review_policy.update` | 02A immutable identity/lineage plus refreshed REV-03P/AUTH-12D2; activated only by `WS-XINT-003-02B` |
| `project.revision_policy.update` | 02A immutable identity/lineage plus refreshed REV-03P/AUTH-12D2; activated only by `WS-XINT-003-02B` |
| `review.queue.read` | merged hidden REV-05 concealed current-work view |
| `review.claim` | merged hidden REV-05 queue admission and REV-06 atomic lease behavior |
| `review.release` | merged hidden REV-06 lease release behavior |
| `review.decline_preference` | merged hidden REV-06 preference behavior |
| `review.preference_expiry.run` | merged hidden REV-06 preference timer command |
| `review.lease_expiry.run` | merged hidden REV-06 lease timer command |
| `review.context.read` | merged hidden REV-07 context/packet membership plus XINT-002-07A packet materialization |
| `review.finding_evidence.ingest` | merged hidden REV-07 finding-slot behavior plus XINT-002-07A finding binding |
| `review.chain.read` | merged hidden REV-07 bounded chain behavior plus active context boundary |
| `review.decision` | merged hidden REV-08 decision kernel plus required CON flush-only participant |
| `review.finding_response_evidence.ingest` | merged hidden REV-09A obligation/preparation plus merged XINT-002-07B response evaluator |
| `review.queue.inspect` | merged hidden REV-11 bounded/redacted queue inspection |
| `review.lease.force_release` | merged hidden REV-11 force-release command |
| `review.queue.routing.override` | merged hidden REV-11 override command |
| `review.queue.routing.correct` | merged hidden REV-11 correction command |
| `review.queue.close` | merged hidden REV-11 close command |
| `review.revision_context.repair` | 08R registration plus merged hidden REV-11 covered-project repair command |
| `review.revision_obligation.close` | 08R registration plus merged hidden REV-11 obligation-close command |
| `review.revision_context.legacy_close` | 08R registration plus merged hidden REV-11 legacy-close command |
| `review.lifecycle.activation.manage` | 08R registration plus merged hidden REV-12A lifecycle controller |
| `review.reconcile.run` | merged hidden REV-11 invalidation and general reconciliation commands |
| `review.artifact_reference.reconcile` | merged hidden REV-12 artifact-reference command and typed ART repair port |
| `review.projection.rebuild` | merged hidden REV-12 derived-projection command |
| `artifact.review_packet.materialize` | XINT-002-07A after hidden ART packet behavior and REV active-lease manifest |
| `artifact.review_evidence.binding.create` | XINT-002-07A finding-slot behavior; XINT-002-07B response-slot behavior after hidden REV obligation/preparation |
| `artifact.submission_bundle.prepare` | XINT-002-05D after hidden REV human-revision preparation |
| `submission.create` | XINT-002-05D after a verified, consumable human-revision admission |
