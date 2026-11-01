"""Selected external POST execution inside one verified ART callback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
import json

from app.interfaces.external_checker_execution import ExternalCheckerExecutionAdapter
from app.interfaces.external_services import (
    ExternalServiceConfigurationError,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.interfaces.forge_facts import (
    ForgeChangeNotEligibleError,
    ForgeChangeNotFoundError,
    ForgeFactsAdapter,
)
from app.modules.checkers.api.external import (
    PostSubmitExternalCheckerIdentity,
    external_checker_input_fits,
    external_checker_json_hash,
    make_external_checker_execution_request,
)
from app.modules.checkers.api.external_policy import (
    ForgeFactsSelection,
    LockedExternalPostSubmitPolicy,
    selected_evaluation_context_roles,
    selected_forge_facts,
)
from app.modules.checkers.api.selected_post_submit import (
    ExternalPostSubmitIsolationFacts,
    ExternalPostSubmitMemberFacts,
    ExternalPostSubmitInputReceipt,
    SelectedPostSubmitExecutionFacts,
    SelectedPostSubmitInfrastructureUnavailable,
)


# The Harnessy proof (``harnessy.work.proof.v1``) names the change whose facts
# are read in its ``pr_url`` claim.
PROOF_PATH = "proof.json"
PROOF_CHANGE_URL_KEY = "pr_url"
MAX_PROOF_BYTES = 65_536
FORGE_FACTS_INPUT_KEY = "forge_facts"
ForgeFactsResolver = Callable[[str], ForgeFactsAdapter]


def _claimed_change_number(
    material_view, selection: ForgeFactsSelection, adapter: ForgeFactsAdapter
) -> int | None:
    """Return the claimed change in the selected repository, or None.

    A missing, oversized or malformed claim, or one naming another repository,
    yields no facts; the checker then fails closed with its own finding. Facts
    are never read from a repository the locked configuration does not name.
    The provider parses its own forge's change URL.
    """
    entry = next((item for item in material_view.entries if item.normalized_path == PROOF_PATH), None)
    if entry is None or entry.entry_type != "file" or entry.byte_count > MAX_PROOF_BYTES:
        return None
    try:
        proof = json.loads(material_view.read_file(PROOF_PATH, maximum_bytes=MAX_PROOF_BYTES))
    except (ValueError, RecursionError):
        return None
    claimed = adapter.parse_change_url(
        proof.get(PROOF_CHANGE_URL_KEY) if isinstance(proof, dict) else None
    )
    if claimed is None or claimed[0].lower() != selection.repository.lower():
        return None
    return claimed[1]


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
        forge_facts: ForgeFactsResolver | None = None,
    ) -> None:
        self._policy = policy
        self._identity = identity
        self._execution = execution
        self._forge_facts = forge_facts

    async def _read_forge_facts(self, selection, material_view) -> dict[str, object] | None:
        """Read facts outside the checker sandbox; forge failures are infrastructure.

        The provider must serve the forge instance the binding names; a change
        the forge does not have, or one outside the selection, yields no facts.
        """
        if self._forge_facts is None:
            raise SelectedPostSubmitInfrastructureUnavailable("implementation_unavailable")
        try:
            adapter = self._forge_facts(selection.forge)
            if adapter.forge_origin != selection.forge_origin:
                raise SelectedPostSubmitInfrastructureUnavailable("implementation_unavailable")
            number = _claimed_change_number(material_view, selection, adapter)
            if number is None:
                return None
            facts = await adapter.fetch_change_facts(
                repository=selection.repository,
                change_number=number,
                base_branch=selection.base_branch,
            )
        except (ForgeChangeNotFoundError, ForgeChangeNotEligibleError):
            return None
        except ExternalServiceConfigurationError as exc:
            raise SelectedPostSubmitInfrastructureUnavailable(
                "implementation_unavailable"
            ) from exc
        return facts.model_dump(mode="json")

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
                selection = selected_forge_facts(binding.configuration, binding.stage)
                if selection is not None:
                    facts = await self._read_forge_facts(selection, material_view)
                    if facts is not None:
                        input_value[FORGE_FACTS_INPUT_KEY] = facts
                context, materials = None, (material,)
                if selected_evaluation_context_roles(binding.configuration, binding.stage) is not None:
                    context, materials = material_view.evaluation_material(binding)
                    input_value["evaluation_context"] = context.model_dump(mode="json")
                # Facts are bounded by the forge's listing, not by the checker's
                # input ceiling. Facts too large to carry are withheld, so the
                # checker fails the proof rather than the request being invalid.
                if FORGE_FACTS_INPUT_KEY in input_value and not external_checker_input_fits(
                    input_value
                ):
                    del input_value[FORGE_FACTS_INPUT_KEY]
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
