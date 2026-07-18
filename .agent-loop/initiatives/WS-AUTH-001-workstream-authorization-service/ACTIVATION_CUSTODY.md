# Activation Custody: WS-AUTH-001

## Authority

This plan applies the merged `WS-XINT-001` handoffs to AUTH. It distinguishes:

- feature/resource ownership: ART, REV, CON, project, task, submission, or
  checker code owns facts, guards, state, and hidden behavior;
- activation custody: one exact AUTH chunk owns `ActionOwner`, evaluator
  integration, and the `planned` to `active` transition; and
- transaction ownership: the request route or service command owns one commit
  after AUTH and all feature participants have staged their evidence and state.

Feature chunks never change availability. AUTH never invents feature facts or
performs feature lifecycle mutations.

## Catalogue baselines

Trusted entry `main` after PR #140 contains 74 PermissionIds and 57 ActionIds:
nine active and 48 planned. AUTH-09A adds zero permissions and eight planned
actor/link/service actions, producing 74 PermissionIds and 65 ActionIds: nine
active and 56 planned. Of those planned rows, the same 25 ART actions and 19 REV
actions still carry historical feature-chunk owner values. The two later
custody-transfer chunks change only those owner values; their entry counts,
mappings, and availability must remain identical.

## ART custody transfer

| AUTH activation chunk | Exact planned ActionIds |
|---|---|
| `WS-AUTH-001-ART-02D-INTERNAL` | `artifact.verification.execute`, `artifact.pending_work.scan`, `artifact.put_attempt.resolve` |
| `WS-AUTH-001-ART-02D-OPERATOR` | `artifact.binding.read`, `artifact.replica.read`, `artifact.receipt.read`, `artifact.verification_job.read`, `artifact.verification_job.retry`, `artifact.recovery_attempt.read`, `artifact.audit.read`, `operations.artifact_storage_admission.read` |
| `WS-AUTH-001-ART-03` | `artifact.guide_source.ingest`, `artifact.guide_source.read`, `artifact.guide_source.binding.create` |
| `WS-AUTH-001-ART-04A` | `artifact.upload_session.create`, `artifact.upload_session.read`, `artifact.upload_item.write`, `artifact.upload_session.seal`, `artifact.upload_session.cancel`, `artifact.upload_session.expire` |
| `WS-AUTH-001-ART-04B` | `artifact.pre_submit.checker_input.materialize` |
| `WS-AUTH-001-ART-05` | `artifact.submission.binding.create` |
| `WS-AUTH-001-ART-06A` | `artifact.post_submit.checker_input.materialize` |
| `WS-AUTH-001-ART-06B` | `artifact.checker_output.write`, `artifact.checker_output.binding.create` |

`WS-AUTH-001-ART-CUSTODY` performs the atomic 25-row transfer to eight exact AUTH
groups and removes the seven historical ART owner enum values. It adds no migration because owner and
availability are typed metadata, while PostgreSQL preserves the exact
ActionId-to-PermissionId set.

## REV custody transfer

| AUTH activation chunk | Exact planned ActionIds |
|---|---|
| `WS-AUTH-001-REV-05` | `review.queue.read`, `review.queue.inspect` |
| `WS-AUTH-001-REV-06` | `review.claim`, `review.release`, `review.decline_preference`, `review.preference_expiry.run`, `review.lease_expiry.run` |
| `WS-AUTH-001-REV-07` | `review.context.read`, `review.chain.read`, `review.finding_evidence.ingest` |
| `WS-AUTH-001-REV-08` | `review.decision` |
| `WS-AUTH-001-REV-09A` | `review.finding_response_evidence.ingest` |
| `WS-AUTH-001-REV-11` | `review.lease.force_release`, `review.queue.routing.override`, `review.queue.routing.correct`, `review.queue.close`, `review.reconcile.run` |
| `WS-AUTH-001-REV-12` | `review.artifact_reference.reconcile`, `review.projection.rebuild` |

`WS-AUTH-001-REV-CUSTODY` performs the atomic 19-row transfer and removes the
seven historical REV owner enum values. It changes no mapping or availability
and adds no migration.

## Additive registration gates

The following values are approved boundary proposals, not registered runtime
actions on trusted `main`:

| Registration chunk | Future activation chunk | Proposed ActionId -> PermissionId |
|---|---|---|
| `WS-AUTH-001-REV-REG` | `WS-AUTH-001-REV-LIFECYCLE` | `review.revision_context.repair` -> `project.task.manage`; `review.revision_context.legacy_close` -> `operations.reconcile.run`; `review.revision_obligation.close` -> `project.task.manage`; `review.lifecycle.activation.manage` -> `operations.reconcile.run` |
| `WS-AUTH-001-ART-REV-EVIDENCE-REG` | `WS-AUTH-001-ART-REV-EVIDENCE` | `artifact.review_evidence.binding.create` -> `artifact.binding.create` |

These are declared future registration gates, not executable chunk contracts.
Neither may receive a full contract or start until the owning feature publishes exact
principal class, typed resource context, canonical facts, guards, surfaces,
transaction revalidation, and hidden behavior dependencies. AUTH must not invent
those contracts. Registration is availability-neutral and requires typed plus
PostgreSQL audit mapping parity. Migration numbers are allocated from trusted
`main` when each registration contract becomes executable; they are not
reserved ahead of an incomplete feature contract. Each registration migration
takes a writer-blocking downgrade lock and refuses without mutation when any
decision, audit, idempotency, or linked evidence references an added ActionId.
Its proof includes populated refusal, empty safe downgrade, re-upgrade, and
fresh replay.

Counts are derived from trusted `main` when a gate executes. REV registration
adds exactly four planned actions and zero active actions; evidence registration
adds exactly one planned action and zero active actions, in either order.
PermissionIds remain 74. The evidence-binding
registration also adds that exact action to the existing
`workstream.artifact.binding` static row, increasing matrix membership from 11
to 12 without adding an identity or database grant.

## Prepared mutation prerequisite

`WS-AUTH-001-PREP` adds a session-bound, action-bound, opaque, single-use,
nonserializable prepared authority handle:

```text
AUTH locks canonical current authority
-> feature locks its records
-> feature recomposes final typed facts
-> AUTH evaluates exactly once and stages decision evidence
-> feature participants flush
-> route or service command commits once
```

Reads retain `AuthorizationService.require()`. Mutations must not evaluate
against stale pre-lock facts or let dependency teardown commit shared state.

## Activation gate

Every activation chunk requires an immutable merged feature SHA and exact
manifest containing its action list, resource composer, facts, guards, primary
surface declarations, transaction owner, revalidation proof, and real-kernel
`action_unavailable` proof before activation. The AUTH chunk then integrates
only those evaluators, changes only those actions to active, proves the exact
availability delta, and preserves all unrelated rows.

An activation entry in this map is a non-executable placeholder until that
manifest exists. Its later preimplementation contract must enumerate exact
allowed feature files, route/command and transaction tests, generated manifest
delta, allow/deny/revalidation/rollback matrix, PostgreSQL concurrency cases,
focused coverage commands for every changed subsystem at 90 percent or higher,
and the full backend suite preserving the global 78 percent floor. Generic “as
applicable” proof or AUTH-only tests cannot authorize activation.

`WS-AUTH-001-ART-02D-INTERNAL` requires the exact merged ART-02C2 verification,
resolution, and scanner behavior plus ART-02C3 recovery/fencing foundations and
any ART-02D resource-composer dependency. ART-02D does not own the internal
behavior. Within `WS-AUTH-001-ART-02D-OPERATOR`,
`artifact.verification_job.retry` requires its own evaluator, guards, behavior
tests, and explicit availability assertion; passing the seven read/status cases
does not authorize retry.

Service actions additionally require a previously reviewed exact fixed-service
identity and matrix extension plus controlled provisioning and AUTH-09E
admission. REV must publish exact timer, expiry, reconciliation, projection,
artifact-reference, and release-control service manifests before AUTH creates
those identity-specific extension contracts. No catch-all review service is
pre-created.

`review.decision` additionally requires the merged flush-only CON participant
and one rollback-safe REV+CON transaction. Review-evidence binding additionally
requires ART and REV to define the in-process/service boundary, two independent
authorization decisions and evidence records, exact lock order, and one
transaction owner. Human authority cannot be silently converted into service
authority.

## Sequencing

```text
WS-AUTH-001-XINT planning reconciliation
-> repair and re-review PR #132 / AUTH-09A on trusted main
-> AUTH-09B -> 09C -> 09D -> 09E
-> WS-AUTH-001-ART-CUSTODY
-> WS-AUTH-001-REV-CUSTODY
-> WS-AUTH-001-PREP
-> AUTH-10 through AUTH-15 core cutovers
-> feature-gated registration and activation chunks as their manifests merge
-> AUTH-16 aggregate conformance and live proof
```

Only one WS-AUTH implementation chunk is active at a time. ART, REV, and CON
may build hidden behavior in their own worktrees while real actions remain
planned, but each merged AUTH activation must converge from current trusted
`main` and pass its own human checkpoint.
