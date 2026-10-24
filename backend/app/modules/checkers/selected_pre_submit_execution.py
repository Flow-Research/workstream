"""Selected default-plus-external PRE execution over one ART callback."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from app.interfaces.external_checker_execution import ExternalCheckerExecutionAdapter
from app.interfaces.external_services import (
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.modules.checkers.api.default_checker import WorkstreamDefaultCheckerInput, WorkstreamDefaultCheckerResult
from app.modules.checkers.api.external import (
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_request,
)
from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
from app.modules.checkers.api.materialization import PreSubmitMaterialView
from app.modules.checkers.api.selected_pre_submit import (
    ExternalPreSubmitIsolationFacts,
    ExternalPreSubmitMemberFacts,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitInfrastructureUnavailable,
)



def _input_body(
    *,
    requirement_id: str,
    identity: PreSubmitExternalCheckerIdentity,
    material: PreSubmitExternalCheckerMaterial,
    value: WorkstreamDefaultCheckerInput,
) -> dict[str, object]:
    """Build the one normalized public PRE image input from verified facts."""
    return {
        "schema_version": "workstream.external_checker_pre_submit_input.v1",
        "requirement_id": requirement_id,
        "project_id": str(identity.project_id),
        "task_id": str(identity.task_id),
        "assignment_id": str(identity.assignment_id),
        "archive_sha256": material.archive_sha256,
        "archive_byte_count": material.archive_byte_count,
        "semantic_manifest_sha256": material.semantic_manifest_sha256,
        "manifest": [asdict(item) for item in value.entries],
        "packet": {
            "summary": value.packet.summary,
            "contributor_attestation": value.packet.contributor_attestation,
        },
    }


class SelectedPreSubmitProcessor:
    """Run the default and every required locked external PRE image in order."""

    def __init__(
        self,
        *,
        policy: LockedExternalPreSubmitPolicy,
        default_input: WorkstreamDefaultCheckerInput,
        identity: PreSubmitExternalCheckerIdentity,
        material: PreSubmitExternalCheckerMaterial,
        execution: ExternalCheckerExecutionAdapter,
    ) -> None:
        self._policy, self._default_input = policy, default_input
        self._identity, self._material = identity, material
        self._execution = execution
        self._aborted = False
        self._active: asyncio.Task | None = None

    def abort(self) -> None:
        """Revoke callback access and cancel the active default/image invocation."""
        self._aborted = True
        if self._active is not None:
            self._active.cancel()

    async def process(
        self, material: PreSubmitMaterialView, default: WorkstreamDefaultCheckerResult,
    ) -> SelectedPreSubmitExecutionFacts:
        """Consume ART's verified export/default after confirmed intake cleanup."""
        try:
            if self._aborted:
                raise asyncio.CancelledError
            members: list[ExternalPreSubmitMemberFacts] = []
            if default.eligible:
                for order, binding in enumerate(self._policy.entries):
                    if self._aborted:
                        raise asyncio.CancelledError
                    input_value = _input_body(
                        requirement_id=binding.requirement_id,
                        identity=self._identity,
                        material=self._material,
                        value=self._default_input,
                    )
                    request = make_external_checker_execution_request(
                        registry=binding.registry,
                        identity=self._identity,
                        configuration=binding.configuration,
                        configuration_sha256=binding.configuration_sha256,
                        input=input_value,
                        input_sha256=external_checker_json_hash(input_value),
                        materials=(self._material,),
                    )
                    with material.external_checker_grant(request) as grant:
                        self._active = asyncio.create_task(
                            self._execution.execute(request, grant)
                        )
                        response = await self._active
                    result = response.result
                    if result.outcome == "infrastructure_failed":
                        raise SelectedPreSubmitInfrastructureUnavailable(
                            result.infrastructure_failure_code or "invalid_output"
                        )
                    if response.isolation is None:
                        raise SelectedPreSubmitInfrastructureUnavailable("invalid_output")
                    member = ExternalPreSubmitMemberFacts(
                        order=order,
                        requirement_id=binding.requirement_id,
                        registry_entry_id=binding.registry.registry_entry_id,
                        registry_entry_digest=binding.registry.entry_digest,
                        request_digest=request.request_digest,
                        result=result,
                        isolation=ExternalPreSubmitIsolationFacts(
                            **asdict(response.isolation)
                        ),
                    )
                    members.append(member)
                    if result.verdict == "failed":
                        break
            eligible = default.eligible and len(members) == len(self._policy.entries) and all(
                item.result.verdict == "passed" for item in members
            )
            return SelectedPreSubmitExecutionFacts(
                policy_sha256=self._policy.policy_sha256,
                workstream_default=default,
                required_external_count=len(self._policy.entries),
                external_members=tuple(members),
                eligible=eligible,
            )
        except ExternalServiceUnavailableError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable(
                "implementation_unavailable"
            ) from exc
        except ExternalServiceProtocolError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("invalid_output") from exc
        finally:
            self._active = None


__all__ = ("SelectedPreSubmitProcessor",)
