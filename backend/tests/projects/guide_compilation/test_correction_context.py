"""Correction prompts materialize exactly the already-committed prior proposal."""

import hashlib
import json
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import (
    ProjectGuideCompilationContext,
    ProjectGuideCorrectionFeedback,
    canonical_project_guide_compilation_context_bytes,
    project_guide_compilation_prompt_bytes,
)
from tests.projects.guide_compilation.helpers import context, generated_result, ids


def correction_context():
    """Build a server-verified correction with distinct retained proposal content."""
    predecessor = generated_result().model_copy(
        update={"setup_notes": ("Preserve this coverage.",)}
    )
    return ProjectGuideCompilationContext.model_validate(
        {
            **context(ids()).model_dump(),
            "correction_feedback": ProjectGuideCorrectionFeedback(
                operation_id=uuid4(),
                predecessor_compilation_id=uuid4(),
                predecessor_result_hash=canonical_json_hash(predecessor.model_dump(mode="json")),
                target_digest="sha256:" + "a" * 64,
                reason="Clarify one requirement.",
            ),
            "correction_predecessor": predecessor,
        }
    )


def test_correction_materializes_exact_predecessor_without_changing_retained_identity():
    """Retained identities commit the body through the existing feedback result hash."""
    compilation = correction_context()
    historical = compilation.model_dump(mode="json", exclude={"correction_predecessor"})
    canonical = canonical_project_guide_compilation_context_bytes(compilation)
    assert json.loads(canonical) == historical
    assert "sha256:" + hashlib.sha256(canonical).hexdigest() == canonical_json_hash(historical)
    prompt = json.loads(project_guide_compilation_prompt_bytes(compilation))
    assert set(prompt) == {"material", "task_examples"}
    assert "correction_predecessor" not in prompt
    assert "correction_feedback" not in prompt
    assert canonical_json_hash(compilation.correction_predecessor.model_dump(mode="json")) == (
        compilation.correction_feedback.predecessor_result_hash
    )


@pytest.mark.parametrize("change", ["missing_predecessor", "missing_feedback", "substitution"])
@pytest.mark.parametrize(
    "serialize",
    [canonical_project_guide_compilation_context_bytes, project_guide_compilation_prompt_bytes],
)
def test_correction_rejects_uncommitted_material_even_after_unvalidated_copy(change, serialize):
    """Alternate internal callers cannot bypass the commitment with model_copy."""
    compilation = correction_context()
    if change == "missing_predecessor":
        updates = {"correction_predecessor": None}
    elif change == "missing_feedback":
        updates = {"correction_feedback": None}
    else:
        updates = {"correction_predecessor": generated_result()}
    with pytest.raises(ValueError, match="correction"):
        serialize(compilation.model_copy(update=updates))
    with pytest.raises(ValueError, match="correction"):
        ProjectGuideCompilationContext.model_validate({**compilation.model_dump(), **updates})


@pytest.mark.parametrize("no_inference", [False, True])
def test_context_prompt_bound_applies_only_when_inference_will_run(no_inference):
    """Manager-authored rules keep their own document bound without a hosted prompt."""
    from types import SimpleNamespace
    from app.modules.projects.guide_compilation.context import compilation_context_from_material
    from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError
    from tests.projects.guide_compilation.helpers import (
        TASK_EXAMPLE_MANIFEST,
        TASK_EXAMPLES,
        manager_runtime_configuration,
        runtime_configuration,
    )

    configuration = manager_runtime_configuration() if no_inference else runtime_configuration()
    limit = len(project_guide_compilation_prompt_bytes(context(ids(), configuration=configuration))) - 1
    configuration = configuration.model_copy(update={"maximum_manifest_bytes": limit})
    original = context(ids(), configuration=configuration)
    material = original.material
    guide = SimpleNamespace(
        id=str(material.guide_id),
        project_id=str(material.project_id),
        version=material.guide_version,
        task_examples=TASK_EXAMPLES,
        task_examples_hash=TASK_EXAMPLE_MANIFEST["task_examples_hash"],
    )
    snapshot = SimpleNamespace(
        id=str(material.source_snapshot_id),
        bundle_hash=material.source_snapshot_hash,
        manifest_json=TASK_EXAMPLE_MANIFEST,
    )
    arguments = dict(
        guide=guide,
        snapshot=snapshot,
        loaded=material,
        setup_run_id=original.setup_run_id,
        setup_generation=original.setup_generation,
        runtime_configuration=configuration,
    )
    assert len(project_guide_compilation_prompt_bytes(original)) > limit
    if no_inference:
        assert compilation_context_from_material(**arguments) == original
    else:
        with pytest.raises(GuideCompilationIntegrityError, match="context exceeds"):
            compilation_context_from_material(**arguments)
