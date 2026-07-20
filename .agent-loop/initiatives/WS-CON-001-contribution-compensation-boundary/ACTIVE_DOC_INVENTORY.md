# Active Documentation Inventory: WS-CON-001-01

## Purpose

This inventory records the active-document scope reviewed before implementing
the canonical specification and ADR. It separates target architecture from
historical/current-runtime documentation so this specification chunk does not
pretend the legacy runtime migration has already occurred.

## Direct chunk changes

| File | Reason |
|---|---|
| `docs/spec_contribution_compensation.md` | New canonical target specification. |
| `docs/decision_0016_contribution_compensation_boundary.md` | New architecture decision. |
| `README.md` | One canonical specification link, ADR link, and precedence note. |
| `docs/architecture_data_model.md` | Canonicalize the TaskAssignment heading, correct FinalAcceptance aliases to merged REV-owned names, and mirror fixed-point/receipt data-minimization rules. |
| `.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**` | Chunk status, evidence, review, and trust artifacts. |
| `.agent-loop/merge-intents/WS-CON-001-01.json` | Immutable same-initiative successor declaration. |

## Current-main reconciliation

Before the PR human checkpoint, AUTH-09B PR #143 merged as trusted main
`053242b`. The canonical specification and active CON planning/handoff artifacts
therefore adopt the 74-permission/65-action/10-active/55-planned baseline and
the controlled `actor.service.provision` route. Historical review artifacts
retain their exact earlier SHAs and observations. No AUTH runtime file is
changed by this CON reconciliation.

Before CON-02A review, trusted main advanced through ART PR #141 and AUTH-09C
PR #146 to `0ffdabf`. The live catalogue is now
74-permission/65-action/12-active/53-planned because AUTH-09C activates only
`actor.profile.read` and `actor.identity_link.read`; it adds no CON/outbox
identifier or migration. Historical CON-01 evidence above remains exact.
Trusted main then advanced to `b2b9016` through REV-01 PR #145, which publishes
the canonical review specification without changing the backend migration head
or the CON-02A outbox boundary.
REV-02 PR #147 then advanced trusted main to `f18b620` with planning-only chunk
decomposition and no backend, migration, or 02A boundary change.
AUTH-09D-A PR #148 then advanced trusted main to `99ae4c96`, activated only
three actor-profile lifecycle actions, and added AUTH-owned
`0026_actor_profile_lifecycle`. CON-02A therefore rebases its linear migration
to `0027_shared_transactional_outbox`; the merge adds no CON/outbox action,
permission, evaluator, service identity, or runtime admission.
REV PLAN2 PR #150 then advanced trusted main to `983b9e53` with a
planning/specification-only runtime-readiness refresh. It preserves the
FinalAcceptance-sourced submitter contribution, reviewer contribution on all
three decisions, REV-owned single commit, and shared outbox staging. Its split
future REV child gates are reconciled in CON planning; it changes no backend,
migration, AUTH catalogue, or CON-02A implementation.
ART-02B1 PR #151 then advanced trusted main to `1b5422fc` with the
S3-compatible ArtifactStore adapter, real MinIO integration, inactive AWS
profile support, dependency pins, CI changes, and substantial tests. It adds no
migration or outbox seam and does not change CON-02A behavior, but it requires
fresh repository-wide evidence on the combined tree.
AUTH-09D-B PR #152 then advanced trusted main to `93dd3924`, activating only
identity-link revoke/reactivate and expanding AUTH lifecycle proof. It adds no
migration, CON/task-claim identifier, fixed-service admission, or outbox seam;
at that historical point the contributor foundation and AUTH-09E remained
later gates.
Contributor-foundation PR #153 then advanced trusted main to `8d5eb15b`. It
clean-cuts TaskAssignment and Submission attribution to canonical human
`contributor_id`, adds writer revalidation, and owns
`0027_contributor_foundation`. It adds no CON/outbox identifier, service
admission, dispatcher, review lifecycle, or authority change. CON-02A is now
the linear `0028_shared_transactional_outbox` child; AUTH-09E remains a later
gate.
ART-02C1 PR #154 then advanced trusted main to `44f2467c`. It owns
`0028_artifact_admission` and adds durable artifact-admission and prepared-put
state without changing the generic outbox boundary. CON-02A is therefore the
linear `0029_shared_transactional_outbox` child; ART remains absent from the
outbox append path.

## Inspected and already aligned

The following active documents already describe ContributionPolicy,
FinalAcceptance, contribution lineage, no core ART call, and the no-adjudication
shipping boundary consistently enough that this chunk does not rewrite them:

- `docs/glossary.md`
- `docs/architecture_lockdown.md`
- `docs/architecture_lifecycle_state_machine.md`
- `docs/architecture_system_architecture.md`
- `docs/operations_operator_workflow.md`
- `docs/operations_reviewer_workflow.md`
- `docs/operations_payment_reputation.md`
- `docs/operations_queue_policy.md`
- `docs/product_first_user_flows.md`
- `docs/template_project_guide.md`
- `docs/template_review_packet.md`
- `docs/template_submission_packet.md`
- `docs/template_task.md`

## Historical/current-runtime documents intentionally unchanged

Older implementation chunk specifications and roadmaps still mention the
retired guide-bound economic aggregate or its locked version fields because
those fields remain in the current backend. They are subordinate to the new
target specification but remain accurate implementation history until
CON-05A/05B. This chunk does not rewrite them:

- `docs/spec_chunk_3_project_guide_foundation.md`
- `docs/spec_chunk_4_task_queue_assignment.md`
- `docs/spec_chunk_5_submission_packet_foundation.md`
- `docs/spec_chunk_6_checker_contract_records.md`
- `docs/spec_chunk_9_pre_review_gate.md`
- `docs/spec_week2_checker_framework.md`
- `docs/roadmap_week1_backend_plan.md`
- `docs/roadmap_30_day_master_plan.md`
- `docs/roadmap_day_by_day_execution_plan.md`

Keeping these files unchanged also avoids an unauthorized roadmap/export
change. CON-05A/05B own the semantic and physical cleanup plus the final
stale-consumer scan.

## Immutable archival inputs

All `docs/reference_specs/**` files remain archival inputs. This chunk does not
edit, rename, restore, or stage them and preserves the user's pre-existing
reference-PDF deletion state.
