"""Dependency-free deterministic identity for one project setup generation."""

from uuid import NAMESPACE_URL, uuid5


def project_guide_compilation_task_id(setup_run_id: str, setup_generation: int) -> str:
    """Return the stable broker/execution id for one setup generation."""
    return str(
        uuid5(
            NAMESPACE_URL,
            f"workstream.project_setup.guide_sufficiency:{setup_run_id}:{setup_generation}",
        )
    )
