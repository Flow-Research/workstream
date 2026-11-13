"""Metadata proof for record identities; PostgreSQL guards require runtime proof too."""

from sqlalchemy import CheckConstraint, Uuid
from sqlalchemy.dialects import postgresql

from app.db import models  # noqa: F401 - load the complete owner graph
from app.db.base import Base


# These keys express business uniqueness, not generated record identities.
NATURAL_PRIMARY_KEYS = {
    "submission_source_capacity_profiles": ("namespace_id",),
    "submission_source_charges": ("operation_id",),
    "submission_source_upload_receipts": ("operation_id",),
    "submission_dispatches": ("submission_id",),
    "submission_binding_receipts": ("admission_id",),
    "review_packet_guide_items": ("packet_id", "source_item_id"),
    "authority_control": ("id",),
    "checker_submission_fences": ("submission_id",),
    "artifact_storage_namespaces": ("id",),
    "legacy_actor_identities": ("actor_id",),
    "iso_4217_currency_codes": ("code",),
    "api_rate_control_counters": ("control_scope", "key_digest"),
    "artifact_admission_scopes": ("scope_type", "scope_id"),
    "artifact_put_attempt_charges": ("attempt_id", "charge_id"),
    "guide_source_extraction_retry_budgets": ("binding_id",),
    "outbox_delivery_attempts": ("event_id", "claim_generation"),
    "project_compensation_units": ("project_id", "instrument_type", "unit_code"),
    "model_usage_budget_accounts": ("project_id",),
    "checker_model_invocation_grant_calls": ("grant_id", "call_index"),
}


def test_every_generated_primary_key_uses_native_uuid_and_v7_constraint():
    for table in Base.metadata.tables.values():
        keys = tuple(table.primary_key.columns)
        if table.name in NATURAL_PRIMARY_KEYS:
            assert tuple(column.name for column in keys) == NATURAL_PRIMARY_KEYS[table.name]
            continue
        assert len(keys) == 1, table.name
        key = keys[0]
        assert isinstance(key.type, Uuid) and key.type.native_uuid, table.name
        assert str(key.type.compile(dialect=postgresql.dialect())) == "UUID"
        constraints = {
            constraint.name: str(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert constraints[f"ck_{table.name}_{key.name}_uuid7"] == (
            f"(get_byte(uuid_send({key.name}), 6) >> 4) = 7 and "
            f"(get_byte(uuid_send({key.name}), 8) & 192) = 128"
        ), table.name


def test_every_relational_uuid_reference_uses_the_same_native_type():
    checked = 0
    for table in Base.metadata.tables.values():
        for reference in table.foreign_keys:
            if not isinstance(reference.column.type, Uuid):
                continue
            local = reference.parent.type
            assert isinstance(local, Uuid) and local.native_uuid, str(reference)
            assert local.as_uuid == reference.column.type.as_uuid, str(reference)
            checked += 1
    assert checked > 0


def test_task_assignee_relationship_uses_native_uuid():
    assigned_to = Base.metadata.tables["workstream_tasks"].c.assigned_to
    assert isinstance(assigned_to.type, Uuid) and assigned_to.type.native_uuid
    assert assigned_to.type.as_uuid is False
    assert str(assigned_to.type.compile(dialect=postgresql.dialect())) == "UUID"


def test_natural_key_classification_has_no_stale_table_exceptions():
    assert NATURAL_PRIMARY_KEYS.keys() <= Base.metadata.tables.keys()


def test_generated_non_primary_operation_identities_have_version_guards():
    owners = {
        "project_create_idempotency_records": "operation_id",
        "guide_mutation_idempotency_records": "operation_id",
        "guide_sufficiency_mutation_idempotency_records": "operation_id",
        "submission_policy_mutation_idempotency_records": "operation_id",
        "policy_mutation_idempotency_records": "operation_id",
        "project_guide_setup_finalizations": "operation_id",
        "project_guides": "activation_operation_id",
    }
    for owner, column in owners.items():
        table = Base.metadata.tables[owner]
        assert isinstance(table.c[column].type, Uuid)
        checks = {
            str(check.name): str(check.sqltext)
            for check in table.constraints
            if isinstance(check, CheckConstraint)
        }
        expression = checks[f"ck_{owner}_{column}_uuid7"]
        assert f"(get_byte(uuid_send({column}), 6) >> 4) = 7" in expression
        assert f"(get_byte(uuid_send({column}), 8) & 192) = 128" in expression
