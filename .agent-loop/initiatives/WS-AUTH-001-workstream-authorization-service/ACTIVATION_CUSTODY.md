# Activation Custody: WS-AUTH-001

The final v0.1 ART catalogue reconciliation, PREP extension, and activation
waves are superseded prospectively by
`../WS-XINT-002-art-auth-end-to-end/`. The counts immediately below are the
trusted pre-reconciliation entry evidence; at its merge, WS-XINT-002-01
replaced them with the then-live 71/78/22/56 catalogue recorded in the ART
custody section without changing runtime availability. Subsequent AUTH chunks
have advanced the current catalogue to 71/96/43/53.
The pre-reconciliation baseline is trusted `main` commit
`2fb322bd2249a5fe9d3fa706dc63f033074e38ce`: 76 PermissionIds, 81 ActionIds,
22 active actions, and 59 planned actions. Older counts below are explicitly
historical snapshots at their named commits, not the WS-XINT-002 entry state.

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

| AUTH activation chunk | Exact ActionIds and current availability |
|---|---|
| `WS-AUTH-001-ART-02D-INTERNAL` | Active: `artifact.verification.execute`, `artifact.pending_work.scan`, `artifact.put_attempt.resolve` |
| `WS-AUTH-001-ART-02D-OPERATOR` | Planned: `artifact.binding.read`, `artifact.replica.read`, `artifact.receipt.read`, `artifact.verification_job.read`, `artifact.verification_job.retry`, `artifact.recovery_attempt.read`, `artifact.audit.read`, `operations.artifact_storage_admission.read` |
| `WS-XINT-002-04B` | Active: `artifact.guide_source.read`, `artifact.guide_source.binding.create` |
| `WS-XINT-002-04A` | Active: `artifact.guide_source.ingest` |
| `WS-XINT-002-05A` | Active: `artifact.submission_bundle.prepare`; registry custody remains historical while replacement implementation chunk WS-ARCH-001-02G supplies the executable PREP boundary |
| `WS-XINT-002-06A` | Active: `artifact.pre_submit.checker_input.materialize` |
| `WS-AUTH-001-ART-05` | Planned: `artifact.submission.binding.create`; registry custody is retained while replacement implementation chunk WS-ARCH-001-02H performs activation |
| `WS-XINT-002-06B` | Planned: `artifact.post_submit.checker_input.materialize`, `artifact.checker_output.write`, `artifact.checker_output.binding.create` |
| `WS-XINT-002-07A` | Planned: `artifact.review_packet.materialize` only |
| Future REV-owned activation, not approved for v0.1 | Planned/unavailable: `artifact.review_evidence.binding.create` |

Runtime owner `WS-XINT-002-07` retains catalogue custody. The only approved
v0.1 availability transition is 07A packet materialization. Evidence binding
remains planned and unavailable pending a separate REV-owned intent.

`WS-AUTH-001-ART-CUSTODY` historically transferred 25 rows. WS-XINT-002-01
reconciles the live catalogue by removing the six unused multi-step upload rows
and registering three end-to-end bundle/review rows. The resulting 22 rows have
exact action cardinalities `3/8/2/1/1/1/1/3/1/1` in the table order above. The
`OPERATOR` suffix denotes only future activation custody; it grants no Operator
entitlement. Fifteen actions remain planned after the three ART foundation
service actions, `artifact.guide_source.ingest`, the two fixed-service guide
binding/read actions, and `artifact.submission_bundle.prepare` activate. The independently
gated `artifact.verification_job.retry`
remains planned and
cannot be activated by read/status proof. The historical transfer added no
migration because owner and availability are typed metadata. WS-XINT-002-01
reconciles PostgreSQL parity through migration `0036`. The current catalogue
has 73 PermissionIds, 102 ActionIds, 55 active actions, and 47 planned actions,
with fourteen fixed-service identities and twenty-two matrix memberships.

## REV custody transfer

The canonical current planning table is
[`WS-XINT-003/ACTION_CUSTODY.md`](../WS-XINT-003-rev-auth-end-to-end/ACTION_CUSTODY.md).
It supersedes the historical placeholder grouping below for future planning,
while leaving runtime `ActionOwner`, permission, mapping, and availability
unchanged until each exact XINT-003 activation wave.

| AUTH activation chunk | Exact planned ActionIds |
|---|---|
| `WS-AUTH-001-REV-05` | `review.queue.read`, `review.queue.inspect` |
| `WS-AUTH-001-REV-06` | `review.claim`, `review.release`, `review.decline_preference`, `review.preference_expiry.run`, `review.lease_expiry.run` |
| `WS-AUTH-001-REV-07` | `review.context.read`, `review.chain.read`, `review.finding_evidence.ingest` |
| `WS-AUTH-001-REV-08` | `review.decision` |
| `WS-AUTH-001-REV-09A` | `review.finding_response_evidence.ingest` |
| `WS-AUTH-001-REV-11` | `review.lease.force_release`, `review.queue.routing.override`, `review.queue.routing.correct`, `review.queue.close`, `review.reconcile.run` |
| `WS-AUTH-001-REV-12` | `review.artifact_reference.reconcile`, `review.projection.rebuild` |
| `WS-XINT-003-08A` | `review.revision_context.repair`, `review.revision_obligation.close`, `review.revision_context.legacy_close` |
| `WS-XINT-003-08B` | `review.lifecycle.activation.manage` |

`WS-AUTH-001-REV-CUSTODY` atomically transfers these 19 rows with exact owner
cardinalities `2/5/3/1/1/5/2` in the table order above. The seven historical
REV runtime owner values remain registered for those actions until their exact
activation waves replace them. It changes no mapping or availability and
adds no migration. All 19 actions remain planned and unavailable; these AUTH
custodian labels grant no reviewer, Operator, or service authority. The four
approved lifecycle actions remain planned and unavailable, and PREP remains separately
human-gated.

The front-loaded readiness waves are:

| XINT-003 wave | AUTH-only result |
|---|---|
| `WS-XINT-003-02C` | Complete unavailable REV catalogue, four additive actions, six exact fixed-service identities, static matrix, and database parity |
| `WS-XINT-003-02D` | Complete typed fail-closed REV PREP/read integration contracts; no lifecycle behavior or availability change |

The exact activation-wave replacement is:

| XINT-003 wave | Registered planned REV ActionIds |
|---|---|
| `WS-XINT-003-03A` | `review.queue.read` |
| `WS-XINT-003-03B` | `review.claim` |
| `WS-XINT-003-03C` | `review.release`, `review.decline_preference` |
| `WS-XINT-003-03D` | `review.preference_expiry.run`, `review.lease_expiry.run` |
| `WS-XINT-003-04` | `review.context.read`, `review.chain.read` |
| `WS-XINT-003-06` | `review.decision` |
| `WS-XINT-003-07` | No availability change; extend the already XINT-002-owned preparation/Submission evaluators with the closed human-review revision context |
| `WS-XINT-003-08A` | `review.queue.inspect`, `review.lease.force_release`, `review.queue.routing.override`, `review.queue.routing.correct`, `review.queue.close`, `review.revision_context.repair`, `review.revision_obligation.close`, `review.revision_context.legacy_close` |
| `WS-XINT-003-08B` | `review.reconcile.run`, `review.artifact_reference.reconcile`, `review.projection.rebuild`, `review.lifecycle.activation.manage` |

Evidence-upload actions remain future-intent-required and unavailable; they are
not activated by 04 or 07. XINT-002-owned ART actions and shared submission
actions are excluded.

## Front-loaded additive registration

The following values are registered planned runtime actions, not active
authority:

| Registration chunk | Future activation chunk | Proposed ActionId -> PermissionId |
|---|---|---|
| `WS-XINT-003-02C` | `WS-XINT-003-08A` / `WS-XINT-003-08B` | `review.revision_context.repair` -> `project.task.manage`; `review.revision_context.legacy_close` -> `operations.reconcile.run`; `review.revision_obligation.close` -> `project.task.manage`; `review.lifecycle.activation.manage` -> `operations.reconcile.run` |

`WS-XINT-003-02C` is the executable availability-neutral AUTH readiness chunk:
it registers these four actions and the exact fixed-service identities/matrix
before REV lifecycle implementation. `WS-XINT-003-02D` then publishes the
closed identifier/digest-based PREP/read contracts. Neither chunk loads or
implements REV lifecycle state, and the real kernel continues to deny every
unavailable action. REV later supplies canonical facts, guards, loaders,
composers, transaction revalidation, and hidden behavior; matching XINT waves
activate only after that integrated proof.

Registration requires typed plus PostgreSQL audit mapping parity. The migration
number is allocated from trusted `main` when 02C starts. The registration migration
takes a writer-blocking downgrade lock and refuses without mutation when any
decision, audit, idempotency, or linked evidence references an added ActionId.
Its proof includes populated refusal, empty safe downgrade, re-upgrade, and
fresh replay.

Counts are derived from trusted `main` when a gate executes. REV registration
adds exactly four planned actions and zero active actions. WS-XINT-002-01
registers review-evidence binding under runtime owner `WS-XINT-002-07`; planned
and unavailable. It may remain named in the closed
`workstream.artifact.binding` static matrix, but 07A does not activate or extend
it. Any activation requires a separate approved REV-owned intent.

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

Service actions use the exact fixed-service identities and closed matrix
installed unavailable by 02C plus controlled canonical admission. REV does not
need to publish hidden job behavior before those fail-closed identity contracts
exist. REV later publishes exact timer, expiry, reconciliation, projection,
artifact-reference, and release-control manifests before the matching action
can become active. No catch-all review service exists.

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

For ART dependencies, replace the generic final two steps with the exact
WS-XINT-002 sequence: complete registration, prepared feature boundaries,
fixed internal services, guide, submission, checker, review artifact access, and
end-to-end conformance. AUTH-14 and AUTH-15 are not alternate activation paths.

Only one WS-AUTH implementation chunk is active at a time. ART, REV, and CON
may build hidden behavior in their own worktrees while real actions remain
planned, but each merged AUTH activation must converge from current trusted
`main` and pass its own human checkpoint.
