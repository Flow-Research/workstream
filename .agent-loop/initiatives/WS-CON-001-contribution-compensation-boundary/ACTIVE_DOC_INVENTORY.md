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
