"""Explicit semantic ownership and deterministic node-partition catalogue."""

from dataclasses import dataclass

ADMIN_RUNNER_MODULE = "tests/test_isolated_database_runner.py"
SCHEMA_MODULE = "tests/test_alembic.py"
PARTITIONED_SHARED_LANES = ("shared_foundations_a", "shared_foundations_b")
PARTITIONED_PROJECT_LANES = ("project_lifecycle_a", "project_lifecycle_b")
PARTITIONED_TASK_LANES = ("task_lifecycle_a", "task_lifecycle_b")


@dataclass(frozen=True)
class TestLane:
    """One dependency-oriented test process."""

    name: str
    modules: tuple[str, ...]
    requires_postgres: bool = True


SHARED_FOUNDATION_MODULES = (
    "tests/test_actor_legacy_classification.py",
    "tests/test_agent_runtime.py",
    "tests/test_api_contract_e2e.py",
    "tests/test_api_controls.py",
    "tests/test_app.py",
    "tests/test_artifact_architecture.py",
    "tests/architecture/test_authorization_boundary.py",
    "tests/architecture/test_module_boundaries.py",
    "tests/architecture/test_cp04a_file_structure.py",
    "tests/architecture/test_test_structure_boundary.py",
    "tests/test_artifact_authorization.py",
    "tests/test_artifact_internal_authorization.py",
    "tests/test_artifact_cleanup_wiring.py",
    "tests/test_checker_materialization.py",
    "tests/test_artifact_preparation.py",
    "tests/test_artifact_store_conformance.py",
    "tests/test_artifact_verification.py",
    "tests/test_artifacts.py",
    "tests/test_assertion_helpers.py",
    "tests/test_aws_credential_isolation.py",
    "tests/test_ci_test_lanes.py",
    "tests/test_ci_lane_catalogue.py",
    "tests/test_config.py",
    "tests/test_compensation.py",
    "tests/compensation/test_adapter_binding_api.py",
    "tests/compensation/test_adapter_binding_authorization_failures.py",
    "tests/compensation/test_adapter_binding_authorization_integration.py",
    "tests/compensation/test_adapter_binding_database_guards.py",
    "tests/compensation/test_adapter_binding_partition.py",
    "tests/compensation/test_adapter_binding_owner_fences.py",
    "tests/compensation/test_adapter_binding_persistence.py",
    "tests/compensation/test_adapter_binding_recovery.py",
    "tests/compensation/test_adapter_binding_service.py",
    "tests/test_contributions.py",
    "tests/contributions/test_policy_authorization_atomicity.py",
    "tests/contributions/test_cp04b_file_structure.py",
    "tests/contributions/test_cp04b_contract_projection.py",
    "tests/contributions/test_policy_draft_concurrency.py",
    "tests/contributions/test_policy_draft_create.py",
    "tests/contributions/test_policy_draft_resources.py",
    "tests/contributions/test_policy_draft_rules.py",
    "tests/contributions/test_policy_draft_update.py",
    "tests/contributions/test_policy_event_postgresql.py",
    "tests/contributions/test_policy_integration_postgresql.py",
    "tests/contributions/test_policy_lifecycle_postgresql.py",
    "tests/contributions/test_policy_negative_scope.py",
    "tests/contributions/test_policy_operation_recovery.py",
    "tests/contributions/test_policy_owner_ports.py",
    "tests/contributions/test_policy_publication_auth_parity.py",
    "tests/contributions/test_policy_publication_authorization.py",
    "tests/contributions/test_policy_publication_concurrency.py",
    "tests/contributions/test_policy_publication_cross_project_postgresql.py",
    "tests/contributions/test_policy_publication_recovery.py",
    "tests/contributions/test_policy_publish.py",
    "tests/contributions/test_policy_read.py",
    "tests/contributions/test_policy_retire.py",
    "tests/contributions/test_policy_routes_absent.py",
    "tests/test_coverage_contract.py",
    "tests/test_external_service_adapters.py",
    "tests/test_guide_artifacts.py",
    "tests/test_guide_bindings.py",
    "tests/test_guide_setup.py",
    "tests/test_guide_formats.py",
    "tests/test_guide_extraction.py",
    "tests/test_guide_images.py",
    "tests/test_guide_xlsx.py",
    "tests/test_guide_docx.py",
    "tests/test_guide_extractor_dependencies.py",
    "tests/test_guide_ooxml.py",
    "tests/test_guide_pdf.py",
    "tests/test_guide_pptx.py",
    "tests/test_local_artifact_store.py",
    "tests/test_merge_test_lane_evidence.py",
    "tests/migrations/test_compensation_adapter_identity.py",
    "tests/test_mutation_policy.py",
    "tests/test_s3_artifact_store.py",
    "tests/test_submission_archive.py",
    "tests/test_submission_change_gate.py",
    "tests/test_submission_manifest.py",
    "tests/test_test_lane_evidence.py",
    "tests/test_actors.py",
    "tests/actors/test_compensation_adapter_eligibility.py",
    "tests/test_api_rate_controls.py",
    "tests/test_audit.py",
    "tests/test_auth.py",
    "tests/test_authorization.py",
    "tests/authorization/guide_compilation/test_adapter_contract.py",
    "tests/authorization/guide_compilation/test_domain_contract.py",
    "tests/authorization/guide_compilation/test_migration_contract.py",
    "tests/authorization/guide_compilation_projections/test_adapter_consumption.py",
    "tests/authorization/guide_compilation_projections/test_composition.py",
    "tests/authorization/guide_compilation_projections/test_policy_and_replay.py",
    "tests/authorization/guide_compilation_projections/test_replay_guards.py",
    "tests/authorization/guide_compilation_projections/test_resource_context.py",
    "tests/authorization/test_fixed_service_action_context.py",
    "tests/authorization/test_adapter_binding_authorization.py",
    "tests/authorization/test_adapter_binding_registration.py",
    "tests/authorization/test_contribution_policy_registration.py",
    "tests/test_behavior_ownership.py",
    "tests/test_artifact_admission.py",
    "tests/test_submission_bundle_admission.py",
    "tests/test_submission_preparation_adapter.py",
    "tests/test_submission_preparation_authorization.py",
    "tests/test_submission_composition.py",
    "tests/test_artifact_bindings.py",
    "tests/test_artifact_bindings_db.py",
    "tests/test_pre_submit_evidence_relock.py",
    "tests/test_artifact_operator_api.py",
    "tests/test_artifact_recovery.py",
    "tests/test_db_session.py",
    "tests/test_outbox.py",
    "tests/test_policy_identity_lineage.py",
    "tests/test_project_policy_mutations.py",
    "tests/projects/test_compensation_binding_eligibility.py",
    "tests/test_review_authorization_contracts.py",
)

PROJECT_MODULES = (
    "tests/projects/guide_compilation/test_authorized_concurrency_postgresql.py",
    "tests/projects/guide_compilation/test_authorized_execution_service.py",
    "tests/projects/guide_compilation/test_authorized_recovery_postgresql.py",
    "tests/projects/guide_compilation/test_authorized_request_service.py",
    "tests/projects/guide_compilation/test_contracts.py",
    "tests/projects/guide_compilation/test_context_builder.py",
    "tests/projects/guide_compilation/test_database_guards.py",
    "tests/projects/guide_compilation/test_durable_dispatch_handoff.py",
    "tests/projects/guide_compilation/test_hidden_call_graph.py",
    "tests/projects/guide_compilation/test_hidden_orchestrator.py",
    "tests/projects/guide_compilation/test_hidden_orchestrator_postgresql.py",
    "tests/projects/guide_compilation/test_migration_authorized_persistence.py",
    "tests/projects/guide_compilation/test_migration_contract.py",
    "tests/projects/guide_compilation/test_public_authorization.py",
    "tests/projects/guide_compilation/test_projection_call_graph.py",
    "tests/projects/guide_compilation/test_projection_contracts.py",
    "tests/projects/guide_compilation/test_projection_migration.py",
    "tests/projects/guide_compilation/test_projection_policy.py",
    "tests/projects/guide_compilation/test_projection_postgresql.py",
    "tests/projects/guide_compilation/test_projection_authorization_postgresql.py",
    "tests/projects/guide_compilation/test_projection_service.py",
    "tests/projects/guide_compilation/test_request_operation_postgresql.py",
    "tests/projects/guide_compilation/test_repository_attempts.py",
    "tests/projects/guide_compilation/test_repository_persistence.py",
    "tests/projects/test_locked_policy_context.py",
    "tests/projects/test_locked_policy_contract.py",
    "tests/projects/test_activation_readiness.py",
    "tests/projects/test_policy_read_composition.py",
    "tests/projects/test_active_guide_read_composition.py",
    "tests/projects/test_diagnostic_read_composition.py",
    "tests/projects/test_diagnostic_read_rejections.py",
    "tests/projects/test_retired_submission_derivation_route.py",
    "tests/test_projects.py",
)

TASK_MODULES = (
    "tests/test_checker_catalogue.py",
    "tests/test_checkers.py",
    "tests/test_default_pre_submit_execution.py",
    "tests/test_effective_pre_submit_execution.py",
    "tests/test_project_guide_compilation_contracts.py",
    "tests/test_review_queue_persistence.py",
    "tests/test_review_lease_persistence.py",
    "tests/test_tasks.py",
)


PARTITION_GROUPS = (
    (PARTITIONED_SHARED_LANES, SHARED_FOUNDATION_MODULES),
    (PARTITIONED_PROJECT_LANES, PROJECT_MODULES),
    (PARTITIONED_TASK_LANES, TASK_MODULES),
)
PARTITION_LANES_BY_MODULE = {
    module: names for names, modules in PARTITION_GROUPS for module in modules
}

LANES = (
    *(TestLane(name, SHARED_FOUNDATION_MODULES) for name in PARTITIONED_SHARED_LANES),
    TestLane(
        "schema_contracts", (SCHEMA_MODULE, "tests/test_database_reset.py", ADMIN_RUNNER_MODULE)
    ),
    *(TestLane(name, PROJECT_MODULES) for name in PARTITIONED_PROJECT_LANES),
    *(TestLane(name, TASK_MODULES) for name in PARTITIONED_TASK_LANES),
)
