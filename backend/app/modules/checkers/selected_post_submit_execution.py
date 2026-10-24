"""Selected external POST execution inside one verified ART callback."""

from __future__ import annotations

from dataclasses import asdict

from app.interfaces.external_checker_execution import ExternalCheckerExecutionAdapter
from app.interfaces.external_services import (
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.modules.checkers.api.external import (
    PostSubmitExternalCheckerIdentity,
    external_checker_json_hash,
    make_external_checker_execution_request,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalPostSubmitPolicy, selected_evaluation_context_roles,
)
from app.modules.checkers.api.selected_post_submit import (
    ExternalPostSubmitIsolationFacts,
    ExternalPostSubmitMemberFacts,
    ExternalPostSubmitInputReceipt,
    SelectedPostSubmitExecutionFacts,
    SelectedPostSubmitInfrastructureUnavailable,
)


def _input_body(*, requirement_id, identity, material, entries) -> dict[str, object]:
    """Build one normalized POST input from actual Submission and ART custody."""
    return {
        "schema_version": "workstream.external_checker_post_submit_input.v1",
        "requirement_id": requirement_id,
        "project_id": str(identity.project_id),
        "task_id": str(identity.task_id),
        "assignment_id": str(identity.assignment_id),
        "submission_id": str(identity.submission_id),
        "submission_version": identity.submission_version,
        "content_sha256": material.content_sha256,
        "byte_count": material.byte_count,
        "semantic_manifest_sha256": material.semantic_manifest_sha256,
        "manifest": [asdict(item) for item in entries],
    }


class SelectedPostSubmitProcessor:
    """Run every locked POST image and return evidence without acceptance authority."""

    def __init__(
        self,
        *,
        policy: LockedExternalPostSubmitPolicy,
        identity: PostSubmitExternalCheckerIdentity,
        execution: ExternalCheckerExecutionAdapter,
    ) -> None:
        self._policy = policy
        self._identity = identity
        self._execution = execution

    async def evaluate(self, _request, material_view) -> SelectedPostSubmitExecutionFacts:
        """Execute in policy order while ART owns actual verified POST material."""
        material = material_view.external_checker_material
        members: list[ExternalPostSubmitMemberFacts] = []
        try:
            for order, binding in enumerate(self._policy.entries):
                input_value = _input_body(
                    requirement_id=binding.requirement_id,
                    identity=self._identity,
                    material=material,
                    entries=material_view.entries,
                )
                context, materials = None, (material,)
                if selected_evaluation_context_roles(binding.configuration, binding.stage) is not None:
                    context, materials = material_view.evaluation_material(binding)
                    input_value["evaluation_context"] = context.model_dump(mode="json")
                request = make_external_checker_execution_request(
                    registry=binding.registry,
                    identity=self._identity,
                    configuration=binding.configuration,
                    configuration_sha256=binding.configuration_sha256,
                    input=input_value,
                    input_sha256=external_checker_json_hash(input_value),
                    materials=materials,
                )
                with material_view.external_checker_grant(request) as grant:
                    response = await self._execution.execute(request, grant)
                result = response.result
                if result.outcome == "infrastructure_failed":
                    raise SelectedPostSubmitInfrastructureUnavailable(
                        result.infrastructure_failure_code or "invalid_output"
                    )
                if response.isolation is None:
                    raise SelectedPostSubmitInfrastructureUnavailable("invalid_output")
                members.append(
                    ExternalPostSubmitMemberFacts(
                        order=order,
                        requirement_id=binding.requirement_id,
                        registry_entry_id=binding.registry.registry_entry_id,
                        registry_entry_digest=binding.registry.entry_digest,
                        request_digest=request.request_digest,
                        result=result,
                        isolation=ExternalPostSubmitIsolationFacts(
                            **asdict(response.isolation)
                        ),
                        input_receipt=ExternalPostSubmitInputReceipt(
                            configuration_sha256=binding.configuration_sha256,
                            input_sha256=request.input_sha256,
                            evaluation_context_sha256=external_checker_json_hash(
                                context.model_dump(mode="json")
                            ),
                            materials=materials,
                        ) if context is not None else None,
                    )
                )
        except ExternalServiceUnavailableError as exc:
            raise SelectedPostSubmitInfrastructureUnavailable(
                "implementation_unavailable"
            ) from exc
        except ExternalServiceProtocolError as exc:
            raise SelectedPostSubmitInfrastructureUnavailable("invalid_output") from exc
        return SelectedPostSubmitExecutionFacts(
            policy_sha256=self._policy.policy_sha256,
            required_external_count=len(self._policy.entries),
            external_members=tuple(members),
        )


__all__ = ("SelectedPostSubmitProcessor",)
