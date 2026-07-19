"""Canonical provider-object references shared by artifact adapters."""

from __future__ import annotations

import re

from app.interfaces.artifacts import ArtifactOperationConflictError
from app.modules.artifacts.sources import ArtifactCommitment


_PROVIDER_OBJECT_REF = re.compile(r"^sha256/([0-9a-f]{2})/([0-9a-f]{62})$")


def artifact_provider_object_ref(commitment: ArtifactCommitment) -> str:
    """Derive one identity-free reference solely from a server commitment."""
    if type(commitment) is not ArtifactCommitment:
        raise ArtifactOperationConflictError("artifact commitment is invalid")
    digest_hex = commitment.sha256[7:]
    return f"sha256/{digest_hex[:2]}/{digest_hex[2:]}"


def parse_artifact_provider_object_ref(provider_object_ref: str) -> tuple[str, str]:
    """Return digest path parts after enforcing the canonical grammar."""
    if not isinstance(provider_object_ref, str):
        raise ArtifactOperationConflictError("artifact provider reference is invalid")
    matched = _PROVIDER_OBJECT_REF.fullmatch(provider_object_ref)
    if matched is None:
        raise ArtifactOperationConflictError("artifact provider reference is invalid")
    return matched.group(1), matched.group(2)
