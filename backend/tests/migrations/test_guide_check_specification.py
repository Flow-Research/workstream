"""Current specification migration preserves old attempts and rejects new old-format writes."""

import asyncio
import json
from uuid import uuid4

from alembic import command
import asyncpg
import pytest

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config
from tests.projects.guide_compilation.helpers import (
    SHA256, context, manager_runtime_configuration, seed_database,
)

pytestmark = pytest.mark.postgres_schema_contract


@pytest.mark.asyncio
async def test_guide_specification_migration_custody(postgres_database_url, migration_lock, monkeypatch):
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    get_settings.cache_clear()
    with migration_lock():
        await _drop_test_database_schema(postgres_database_url)
        await asyncio.to_thread(command.upgrade, _config(), "0065_claim_starts_work")
        ids = await seed_database(postgres_database_url, generations=2)
        config = manager_runtime_configuration()
        material = context(ids, configuration=config).material
        connection = await asyncpg.connect(postgres_database_url.replace("+asyncpg", ""))
        old_id = new_record_id()
        old_columns = (
            "id,project_id,guide_id,guide_version,source_snapshot_id,source_snapshot_hash,"
            "setup_run_id,setup_generation,canonical_input_hash,guide_material_hash,"
            "pre_catalogue_id,pre_catalogue_version,pre_catalogue_schema_version,"
            "pre_catalogue_manifest_hash,post_catalogue_id,post_catalogue_version,"
            "post_catalogue_schema_version,post_catalogue_manifest_hash,agent_identity,"
            "agent_version,instruction_version,runtime_configuration,runtime_configuration_hash,"
            "provider_idempotency_key,status,provider_uncertain_at"
        )
        old_values = (
            old_id, ids["project"], ids["guide"], "v1", ids["snapshot"], SHA256,
            ids["setup_1"], 1, SHA256, material.sha256,
            "workstream.external_checker_capabilities", "v1",
            "external_checker_capabilities.v1", SHA256,
            "workstream.external_checker_capabilities", "v1",
            "external_checker_capabilities.v1", SHA256,
            "project-guide-compilation-agent-v1", "v1", "v1",
            json.dumps(config.model_dump(mode="json")), config.sha256, uuid4(),
            "compilation_provider_uncertain",
        )
        try:
            placeholders = ",".join("$" + str(n) for n in range(1, len(old_values) + 1))
            await connection.execute(
                f"insert into public.project_guide_compilation_attempts({old_columns}) "
                f"values({placeholders},now())", *old_values,
            )
            original = await connection.fetchval(
                "select to_jsonb(a) from public.project_guide_compilation_attempts a "
                "where id=$1", old_id,
            )
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0066_guide_check_specification")
        connection = await asyncpg.connect(postgres_database_url.replace("+asyncpg", ""))
        try:
            request_column = await connection.fetchrow(
                "select data_type,is_nullable from information_schema.columns "
                "where table_schema='public' and table_name='project_guide_proposal_approvals' "
                "and column_name='request_json'"
            )
            assert dict(request_column) == {"data_type": "jsonb", "is_nullable": "YES"}
            retained = await connection.fetchval(
                "select to_jsonb(a)-'result_schema_version' "
                "from public.project_guide_compilation_attempts a where id=$1", old_id,
            )
            assert retained == original
            with pytest.raises((asyncpg.RaiseError, asyncpg.CheckViolationError)):
                await connection.execute(
                    "update public.project_guide_compilation_attempts "
                    "set status='compilation_reserved',provider_uncertain_at=null where id=$1",
                    old_id,
                )
            current_columns = (
                "id,project_id,guide_id,guide_version,source_snapshot_id,source_snapshot_hash,"
                "setup_run_id,setup_generation,canonical_input_hash,guide_material_hash,"
                "agent_identity,agent_version,instruction_version,result_schema_version,"
                "runtime_configuration,runtime_configuration_hash,provider_idempotency_key,status"
            )
            current_values = (
                new_record_id(), ids["project"], ids["guide"], "v1", ids["snapshot"],
                SHA256, ids["setup_2"], 2, SHA256, material.sha256,
                "project-guide-compilation-agent-v1", "v1", "v1",
                "project_guide_check_specification.v1",
                json.dumps(config.model_dump(mode="json")), config.sha256, uuid4(),
                "compilation_reserved",
            )
            placeholders = ",".join("$" + str(n) for n in range(1, len(current_values) + 1))
            sql = (
                f"insert into public.project_guide_compilation_attempts({current_columns}) "
                f"values({placeholders})"
            )
            await connection.execute(sql, *current_values)
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    sql, *(current_values[:13] + (None,) + current_values[14:])
                )
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    "insert into public.project_guide_proposal_approvals "
                    "(operation_id,target_json,request_json) values($1,$2::json,null)",
                    new_record_id(), json.dumps({"result_schema_version": "old"}),
                )
            empty_request = {
                "target": {}, "acknowledged_warning_hashes": [],
                "expected_previous_approval_operation_id": None,
                "expected_previous_approval_output_digest": None,
                "idempotency_key": str(new_record_id()),
                "pre_submit_attachments": [], "post_submit_attachments": [],
            }
            empty_plan = {
                "pre_submit": {"entries": []}, "post_submit": {"entries": []},
            }
            await connection.fetchval(
                "select public.guide_approval_attachments_valid($1::jsonb,$2::jsonb)",
                json.dumps(empty_request), json.dumps(empty_plan),
            )
            invalid_request = empty_request | {"pre_submit_attachments": None}
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.fetchval(
                    "select public.guide_approval_attachments_valid($1::jsonb,$2::jsonb)",
                    json.dumps(invalid_request), json.dumps(empty_plan),
                )
            image_id = str(new_record_id())
            attachment = {
                "requirement_id": "project.pre.quality", "registry_entry_id": image_id,
                "registry_entry_digest": SHA256, "configuration": {},
            }
            entry = {
                "requirement_id": attachment["requirement_id"], "stage": "pre_submit",
                "registry": {
                    "registry_entry_id": image_id, "entry_digest": SHA256,
                    "resources": {"deadline_ms": 1000},
                },
                "configuration": {}, "configuration_sha256": canonical_json_hash({}),
            }
            selected = empty_request | {"pre_submit_attachments": [attachment]}
            locked = empty_plan | {"pre_submit": {"entries": [entry]}}
            check = "select public.guide_approval_attachments_valid($1::jsonb,$2::jsonb)"
            assert await connection.fetchval(check, json.dumps(selected), json.dumps(locked))
            for bad_request, bad_plan in (
                (selected | {"unexpected": True}, locked),
                (selected | {"pre_submit_attachments": [attachment, attachment]}, locked),
                (selected, empty_plan),
                (selected, empty_plan | {"pre_submit": {"entries": [entry, entry]}}),
                (selected, empty_plan | {"pre_submit": {"entries": [entry | {"stage": "post_submit"}]}}),
                (selected | {"pre_submit_attachments": [attachment | {"configuration": {"x": 1}}]}, locked),
                (selected | {"pre_submit_attachments": [attachment | {"registry_entry_digest": canonical_json_hash({})}]}, locked),
                (selected | {"pre_submit_attachments": [attachment | {"requirement_id": "workstream.default"}]}, locked),
                (selected, empty_plan | {"pre_submit": {"entries": [
                    entry | {"registry": entry["registry"] | {"resources": {"deadline_ms": 7_200_000}}}
                ]}}),
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await connection.fetchval(check, json.dumps(bad_request), json.dumps(bad_plan))
        finally:
            await connection.close()
    get_settings.cache_clear()
