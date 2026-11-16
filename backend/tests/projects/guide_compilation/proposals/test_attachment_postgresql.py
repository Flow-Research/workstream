"""Register project images after setup and attach them through the human approval."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external_policy import ExternalCheckerImageAttachment
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalError
from app.modules.projects.guide_compilation.models import ProjectGuideProposalApproval

from .pg_support import proposal_case, read_package
from .test_postgresql import approve


async def test_later_publication_and_one_human_image_cover_independent_suggestions(
    clean_postgres_database,
):
    from tests.checkers.external.support import registry_spec
    from tests.projects.guide_activation.source_fixtures import _register_external_checker_fixture
    from tests.projects.guide_compilation.helpers import generated_result

    suggestion = generated_result().requirements[0]
    outcome = generated_result().model_copy(update={
        "requirements": (
            suggestion,
            suggestion.model_copy(update={"suggestion_id": "another_suggestion"}),
        ),
    })
    async with proposal_case(clean_postgres_database, outcome=outcome,
                             pre_submit_registry_spec=None, post_submit_registry_spec=None) as (
        _, factory, command, actor, grant,
    ):
        package = await read_package(factory, command, actor, grant)
        original_digest = package.target.digest
        assert len(package.result.requirements) == 2
        assert package.target.result_schema_version == "project_guide_check_specification.v1"
        with pytest.raises(ValidationError):
            GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        with pytest.raises(ValidationError):
            GuideProposalApproval(
                target=package.target, pre_submit_attachments=(), post_submit_attachments=(),
                idempotency_key=uuid4(),
            )
        entry = await _register_external_checker_fixture(factory, registry_spec("pre_submit"))
        post_entry = await _register_external_checker_fixture(factory, registry_spec("post_submit"))
        after_publication = await read_package(factory, command, actor, grant)
        assert after_publication.target.digest == original_digest
        attachment = ExternalCheckerImageAttachment(
            requirement_id="human_project_pre_image",
            registry_entry_id=entry.registry_entry_id,
            registry_entry_digest=entry.entry_digest,
            configuration={},
        )
        post_attachment = ExternalCheckerImageAttachment(
            requirement_id="human_project_post_image",
            registry_entry_id=post_entry.registry_entry_id,
            registry_entry_digest=post_entry.entry_digest, configuration={},
        )
        command_key = uuid4()
        approval = GuideProposalApproval(
            target=after_publication.target,
            pre_submit_attachments=(attachment,), post_submit_attachments=(post_attachment,),
            idempotency_key=command_key,
        )
        receipt = await approve(factory, command, actor, grant, approval)
        assert await approve(factory, command, actor, grant, approval) == receipt
        async with factory() as session:
            operation = await session.get(ProjectGuideProposalApproval, receipt.operation_id)
            assert operation.request_json == approval.model_dump(mode="json")
            assert operation.request_digest == canonical_json_hash(operation.request_json)
            assert [item["requirement_id"] for item in operation.effective_pre_submit_plan["pre_submit"]["entries"]] == [
                "human_project_pre_image"
            ]
        with pytest.raises(GuideProposalError, match="operation_conflict"):
            await approve(
                factory, command, actor, grant,
                approval.model_copy(update={"pre_submit_attachments": (
                    attachment.model_copy(update={"requirement_id": "another_human_image"}),
                )}),
            )


async def test_sql_new_approval_cannot_bypass_exact_phase_cardinality(clean_postgres_database):
    """Rehashed request/plan edits cannot insert a new zero/multiple-image approval."""
    import copy
    import json
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.core.identifiers import new_record_id

    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        approval = GuideProposalApproval(
            target=package.target, idempotency_key=uuid4(),
            pre_submit_attachments=values["pre_submit_attachments"],
            post_submit_attachments=values["post_submit_attachments"],
            acknowledged_warning_hashes=package.warning_hashes,
        )
        receipt = await approve(factory, command, actor, grant, approval)
        async with factory() as session:
            original = json.loads(await session.scalar(text(
                "SELECT to_jsonb(a)::text FROM project_guide_proposal_approvals a WHERE operation_id=:id"
            ), {"id": receipt.operation_id}))
        for phase in ("pre_submit", "post_submit"):
            for surface in ("request", "plan", "both"):
                for count in (0, 2, None, "object"):
                    candidate = copy.deepcopy(original)
                    candidate["operation_id"] = str(new_record_id())
                    request, plan = candidate["request_json"], candidate["effective_pre_submit_plan"]
                    attachment = request[phase + "_attachments"][0]
                    member = plan[phase]["entries"][0]
                    if surface in ("request", "both"):
                        request[phase + "_attachments"] = (
                            None if count is None else {} if count == "object" else
                            [attachment | {"requirement_id": f"member_{i}"} for i in range(count)]
                        )
                    if surface in ("plan", "both"):
                        plan[phase]["entries"] = (
                            None if count is None else {} if count == "object" else
                            [member | {"requirement_id": f"member_{i}"} for i in range(count)]
                        )
                    plan[phase]["policy_sha256"] = canonical_json_hash(
                        {key: value for key, value in plan[phase].items() if key != "policy_sha256"})
                    plan["policies_sha256"] = canonical_json_hash(
                        {key: value for key, value in plan.items() if key != "policies_sha256"})
                    candidate["request_digest"] = canonical_json_hash(request)
                    candidate["effective_pre_submit_plan_hash"] = plan["policies_sha256"]
                    with pytest.raises(DBAPIError, match="guide approval requires one PRE and one POST image"):
                        async with factory() as session, session.begin():
                            await session.execute(text(
                                "INSERT INTO project_guide_proposal_approvals "
                                "SELECT (jsonb_populate_record(NULL::project_guide_proposal_approvals,CAST(:body AS jsonb))).*"
                            ), {"body": json.dumps(candidate)})
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM project_guide_proposal_approvals")) == 1
            stored = json.loads(await session.scalar(text(
                "SELECT to_jsonb(a)::text FROM project_guide_proposal_approvals a WHERE operation_id=:id"
            ), {"id": receipt.operation_id}))
            assert stored == original
