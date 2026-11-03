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
    async with proposal_case(clean_postgres_database, outcome=outcome) as (
        _, factory, command, actor, grant,
    ):
        package = await read_package(factory, command, actor, grant)
        original_digest = package.target.digest
        assert len(package.result.requirements) == 2
        assert package.target.result_schema_version == "project_guide_check_specification.v1"
        with pytest.raises(ValidationError):
            GuideProposalApproval(target=package.target, idempotency_key=uuid4())
        empty = GuideProposalApproval(
            target=package.target, pre_submit_attachments=(), post_submit_attachments=(),
            idempotency_key=uuid4(),
        )
        assert empty.pre_submit_attachments == ()
        entry = await _register_external_checker_fixture(factory, registry_spec("pre_submit"))
        after_publication = await read_package(factory, command, actor, grant)
        assert after_publication.target.digest == original_digest
        attachment = ExternalCheckerImageAttachment(
            requirement_id="human_project_pre_image",
            registry_entry_id=entry.registry_entry_id,
            registry_entry_digest=entry.entry_digest,
            configuration={},
        )
        command_key = uuid4()
        approval = GuideProposalApproval(
            target=after_publication.target,
            pre_submit_attachments=(attachment,), post_submit_attachments=(),
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
