"""Shareable originals and illustrative tasks for the connected public drill."""

TASK_EXAMPLES = [
    {"title": "Repair the sample worker", "labels": ["python", "debugging"],
     "content": "Repair the sample worker's incorrect result aggregation and explain the change."},
    {"content": "Investigate a second sample worker that returns duplicate results."},
]
GUIDE_BYTES = b"""# Sample worker repair project

Investigate and repair the assigned sample worker. Submit one ZIP containing
`task.toml` and `evidence/results`. Explain the work in the submission summary
and confirm rights_confirmed in the attestation. Individual files must be at
most 1000000 bytes and the package at most 5000000 bytes.

The project intake image checks the package's project-specific rules. The
post-submit image checks the supplied evidence. The sample image has bounded
fixture markers for negative trials; it does not claim general code judging.
Project managers separately approve the proposed pre- and post-submit rules.
The locked review policy determines whether passing work needs human review.
"""
CORRECTION_REASON = "Confirm that both task examples use the same project artifact and evidence rules."


def guide_bytes(pre_requirements: int = 1) -> bytes:
    """Three explicit recorded guide variants, selected by immutable source bytes."""
    if pre_requirements not in (0, 1, 2):
        raise ValueError("unsupported recorded PRE requirement count")
    if pre_requirements == 1:
        return GUIDE_BYTES
    return GUIDE_BYTES + (
        f"\nRecorded intake variant: {pre_requirements} project PRE requirements.\n"
        "Workstream default intake remains required.\n"
        + ("Two project requirements use distinct ordered IDs; the rejection marker applies only to the first.\n"
           if pre_requirements == 2 else "No project PRE image is required.\n")
    ).encode()
