# Workstream Documentation

This index lists the main Workstream documents. Start with the
[README](../README.md) if you are new to Workstream.

## Start Here

- [Protocol and Implementation](protocol-and-implementation.md)
- [Developer Setup](engineering/developer-setup.md)
- [Workstream Technical Reference](workstream_reference.md)
- [Contribution Guide](../CONTRIBUTING.md)
- [v0.1 Roadmap And Capability Status](roadmap_status.md)
- [Product Principles](product_principles.md)
- [Product Brief](product_brief.md)
- [Architecture Lockdown](architecture_lockdown.md)
- [System Architecture](architecture_system_architecture.md)
- [Glossary](glossary.md)

## Product And Operations Documentation

- [Product Principles](product_principles.md)
- [Product Brief](product_brief.md)
- [First User Flows](product_first_user_flows.md)
- [Architecture Diagrams](diagrams/README.md)
- [System Architecture](architecture_system_architecture.md)
- [Data Model](architecture_data_model.md)
- [Lifecycle State Machine](architecture_lifecycle_state_machine.md)
- [Project Guides and Policy Approval](spec_project_guides.md)
- [Tasks and Assignments](spec_task_assignment.md)
- [Submission Execution](spec_submission_execution.md)
- [Remote MCP Submission Upload Authorization — Planned](spec_mcp_submission_upload.md)
- [Checker Framework](architecture_checker_framework.md)
- [Operator Workflow](operations_operator_workflow.md)
- [Project Operating Manual](operations_project_operating_manual.md)
- [Queue Policy](operations_queue_policy.md)
- [Workspace And Packet Convention](operations_workspace_packet_convention.md)
- [Reviewer Workflow](operations_reviewer_workflow.md)
- [Revision Replay](operations_revision_replay.md)
- [Review And Revision Lifecycle](spec_review_lifecycle.md)
- [Roles And Permissions](operations_roles_permissions.md)
- [Authorization Service](spec_authorization_service.md)
- [Immutable Artifact Storage](spec_artifact_storage_service.md)
- [Contribution And Compensation](spec_contribution_compensation.md)
- [Authorization Operations](operations_authorization_service.md)
- [Compensation And Reputation](operations_payment_reputation.md)
- [Risk Register](risk_register.md)
- [Process Pattern Baseline](process_pattern_baseline.md)
- [Glossary](glossary.md)

## Engineering and deployment

- [Hosted deployment](../deploy/hosted/README.md)
- [Flow Identity accounts, API login and OAuth](../deploy/identity/README.md)
- [MCP server](../mcp_server/README.md) and [CLI](../cli/README.md)
- [Architecture boundary enforcement](engineering/repository_architecture_boundaries.md)
- [Guide checker specifications](engineering/guide-checker-specification.md)
- [Checker image development](engineering/checker-images.md)
- [Observability](engineering/observability.md)
- [External API qualification](engineering/external-api-drill.md)
- [CLI release qualification](engineering/cli-release.md)
- [Local environment](engineering/local-pilot.md) and [agent loop](engineering/local-agent-loop.md)
- [Engineering records](engineering/commitrail.md)
- [Reviewer selection](../.ci/reviewer-evidence/REVIEWER_MATRIX.md)

## Templates

- [Project Guide Template](template_project_guide.md)
- [Submission Artifact Policy Template](template_submission_artifact_policy.md)
- [Checker Policy Template](template_checker_policy.md)
- [Task Template](template_task.md)
- [Review Readiness Evidence Template](template_preflight_evidence.md)
- [Submission Packet Template](template_submission_packet.md)
- [Review Packet Template](template_review_packet.md)
- [Task Status Template](template_task_status.md)
- [Prior Feedback Checklist Template](template_prior_feedback_checklist.md)

## Decisions

- [ADR 0001: Core Scope](decision_0001_core_scope.md)
- [ADR 0002: Database Ledger Before Blockchain Settlement](decision_0002_db_first_not_blockchain_first.md)
- [ADR 0003: Project Guides Are First-Class](decision_0003_project_guides_are_first_class.md)
- [ADR 0004: v0.1 Implementation Stack Is Locked](decision_0004_v0_1_stack_is_locked.md)
- [ADR 0005: Postgres Is The Record Database](decision_0005_postgres_is_the_record_database.md)
- [ADR 0006: Workstream Verifies External Flow Auth](decision_0006_external_flow_auth_boundary.md)
- [ADR 0007: Execution Is Async-First](decision_0007_async_first_execution.md)
- [ADR 0008: Files Use An Object-Storage Abstraction](decision_0008_object_storage_abstraction.md)
- [ADR 0009: Review Decisions Are Canonical](decision_0009_review_decisions_are_canonical.md)
- [ADR 0010: Revision Rebase Uses The Complete Active Project Context](decision_0010_revision_context_rebase.md)
- [ADR 0011: Submission Artifact Policy Drives Pre-Submit Intake](decision_0011_submission_artifact_policy_drives_pre_submit.md)
- [ADR 0012: Workstream Owns Product Authorization](decision_0012_workstream_authorization_service.md)
- [ADR 0013: Immutable Artifact Storage Boundary](decision_0013_immutable_artifact_storage_boundary.md)
- [ADR 0014: External Services Use One Adapter Convention](decision_0014_external_service_adapter_convention.md)
- [ADR 0015: Project Contributor Roles Are Independent](decision_0015_project_contributor_roles_are_independent.md)
- [ADR 0016: Contribution Recognition Precedes External Fulfillment](decision_0016_contribution_compensation_boundary.md)

## Historical sources

Superseded implementation plans and drill reports are available through
[Git history](historical_planning.md), not maintained as parallel specifications.
Imported source specifications remain under `reference_specs/` because preserved
Commitrail records bind those exact inputs; they do not override current contracts.
