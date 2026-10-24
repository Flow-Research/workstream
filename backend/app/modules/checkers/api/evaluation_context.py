"""Image-safe revision facts selected by an approved POST configuration."""

import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.modules.checkers.api.canonical_values import (
    ByteCount,
    CheckerValue,
    ResourceId,
    Sha256,
    VersionNumber,
)
from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    PostSubmitExternalCheckerMaterial,
)
from app.modules.checkers.api.external_policy import validated_evaluation_context_roles
from app.modules.checkers.api.revision_feedback import RevisionFeedback


class PostSubmitRevisionEvaluation(CheckerValue):
    """Detached source-completion evidence; CHECKERS grants no TASK mutation authority."""

    project_id: ResourceId
    task_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    checker_run_id: ResourceId
    evaluation_request_id: ResourceId
    evaluation_request_digest: Sha256
    evaluation_generation: VersionNumber
    result_id: ResourceId
    result_digest: Sha256
    completion_event_id: ResourceId
    routing_recommendation: Literal["needs_revision"]


class PostSubmitRevisionSource(CheckerValue):
    """Image-safe projection of the consumed preparation and its immutable source."""

    preparation_id: ResourceId
    preparation_sha256: Sha256
    routing_manifest_id: ResourceId
    revision_round: Annotated[int, Field(strict=True, ge=0)]
    evaluation: PostSubmitRevisionEvaluation


class PostSubmitEvaluationPredecessor(CheckerValue):
    """Exact prior work identity without contributor or storage-provider coordinates."""

    submission_id: ResourceId
    submission_version: VersionNumber
    content_sha256: Sha256
    byte_count: ByteCount
    semantic_manifest_sha256: Sha256


class PostSubmitEvaluationContext(CheckerValue):
    """Explicit initial/revision context; selection never grants material authority."""

    schema_version: Literal["workstream.post_submit_evaluation_context.v1"] = (
        "workstream.post_submit_evaluation_context.v1"
    )
    kind: Literal["initial", "checker_remediation"]
    source: PostSubmitRevisionSource | None
    predecessor: PostSubmitEvaluationPredecessor | None
    feedback: RevisionFeedback | None

    @model_validator(mode="after")
    def exact_source(self) -> Self:
        """Bind optional feedback to the same retained result as the predecessor."""
        if self.kind == "initial":
            if self.source is not None or self.predecessor is not None or self.feedback is not None:
                raise ValueError("initial context cannot contain previous work")
            return self
        if self.source is None or self.predecessor is None:
            raise ValueError("revision context requires its exact source")
        evaluation = self.source.evaluation
        if (
            evaluation.submission_id != self.predecessor.submission_id
            or evaluation.submission_version != self.predecessor.submission_version
            or evaluation.routing_recommendation != "needs_revision"
        ):
            raise ValueError("revision predecessor differs from its source")
        if self.feedback is not None:
            feedback = self.feedback.source
            reference = feedback.result
            if (
                feedback.project_id,
                feedback.task_id,
                feedback.submission_id,
                feedback.submission_version,
                feedback.completion_event_id,
            ) != (
                evaluation.project_id,
                evaluation.task_id,
                evaluation.submission_id,
                evaluation.submission_version,
                evaluation.completion_event_id,
            ) or (
                reference.attempt_id,
                reference.request_id,
                reference.request_digest,
                reference.evaluation_generation,
                reference.result_id,
                reference.result_digest,
            ) != (
                evaluation.checker_run_id,
                evaluation.evaluation_request_id,
                evaluation.evaluation_request_digest,
                evaluation.evaluation_generation,
                evaluation.result_id,
                evaluation.result_digest,
            ):
                raise ValueError("revision feedback differs from its source")
        return self


class PostSubmitPredecessorCustody(PostSubmitEvaluationPredecessor):
    """Verified prior ART custody retained with the exact input authority receipt."""

    admission_id: ResourceId
    binding_id: ResourceId
    content_id: ResourceId
    replica_id: ResourceId
    evidence_id: ResourceId
    verification_receipt_id: ResourceId
    verification_job_id: ResourceId
    verification_generation: VersionNumber
    namespace_fingerprint: Sha256
    semantic_manifest_id: ResourceId


class PostSubmitInputContextCustody(CheckerValue):
    """Detached selected context; current archive custody keeps its existing shape."""

    evaluation_context: PostSubmitEvaluationContext
    predecessor: PostSubmitPredecessorCustody | None

    @model_validator(mode="after")
    def exact_prior(self) -> Self:
        """Retain only the prior archive named by the verified source context."""
        context = self.evaluation_context
        if self.predecessor is not None and (
            context.predecessor is None
            or any(getattr(self.predecessor, name) != getattr(context.predecessor, name)
                   for name in PostSubmitEvaluationPredecessor.model_fields)
        ):
            raise ValueError("input context prior custody differs")
        return self


def validate_input_context_custody(request, custody: PostSubmitInputContextCustody | None) -> None:
    """Require exactly the context and byte roles selected by the locked policy."""
    selections = tuple(validated_evaluation_context_roles(binding.configuration, binding.registry)
                       for binding in request.policy.entries)
    if (custody is not None) != any(item is not None for item in selections):
        raise ValueError("materialization context selection differs")
    if custody is None:
        return
    context = custody.evaluation_context
    if context.kind == "initial":
        if custody.predecessor is not None:
            raise ValueError("initial materialization cannot include prior material")
        return
    prior, source = context.predecessor, context.source.evaluation
    roles = {role for selection in selections if selection is not None for role in selection}
    if (
        source.project_id != request.project_id
        or source.task_id != request.task_id
        or prior.submission_id == request.submission_id
        or prior.submission_version + 1 != request.submission_version
        or (context.feedback is not None) != ("predecessor_findings" in roles)
        or context.feedback is not None and context.feedback.source.assignment_id != request.assignment_id
        or (custody.predecessor is not None) != ("predecessor_submission_archive" in roles)
    ):
        raise ValueError("materialization revision context differs")


def validate_post_evaluation_materials(request) -> PostSubmitEvaluationContext | None:
    """Close requested roles against typed context after schema/hash validation."""
    selected = validated_evaluation_context_roles(request.configuration, request.registry)
    raw = request.input.get("evaluation_context")
    if selected is None:
        if "evaluation_context" in request.input:
            raise ExternalCheckerContractError("evaluation context was not selected")
        context = None
    else:
        if raw is None:
            raise ExternalCheckerContractError("selected evaluation context is absent")
        context = PostSubmitEvaluationContext.model_validate_json(json.dumps(raw))
    identity = request.identity
    expected_roles = ("submission_archive",)
    if context is not None and context.kind == "checker_remediation":
        source, prior = context.source.evaluation, context.predecessor
        if (
            source.project_id != identity.project_id
            or source.task_id != identity.task_id
            or prior.submission_id == identity.submission_id
            or prior.submission_version + 1 != identity.submission_version
            or (context.feedback is not None) != ("predecessor_findings" in selected)
            or context.feedback is not None
            and context.feedback.source.assignment_id != identity.assignment_id
        ):
            raise ExternalCheckerContractError("revision context differs from current execution")
        if "predecessor_submission_archive" in selected:
            expected_roles += ("predecessor_submission_archive",)
    if tuple(material.role for material in request.materials) != expected_roles:
        raise ExternalCheckerContractError("external checker material roles differ from selection")
    for material in request.materials:
        if not isinstance(material, PostSubmitExternalCheckerMaterial):
            raise ExternalCheckerContractError("external checker material phase mismatch")
        if material.role == "submission_archive":
            if (material.submission_id, material.submission_version) != (
                identity.submission_id,
                identity.submission_version,
            ):
                raise ExternalCheckerContractError(
                    "external checker submission material identity mismatch"
                )
        else:
            prior = context.predecessor
            if any(
                getattr(material, name) != getattr(prior, name) for name in type(prior).model_fields
            ):
                raise ExternalCheckerContractError(
                    "external checker predecessor material identity mismatch"
                )
    return context
