"""Closed Workstream identities for internal service ActorProfiles."""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class ServiceIdentity(StrEnum):
    """Stable local names for the fixed v0.1 internal service principals."""

    ARTIFACT_VERIFIER = "workstream.artifact.verifier"
    ARTIFACT_PUT_RESOLVER = "workstream.artifact.put_resolver"
    ARTIFACT_SCHEDULER = "workstream.artifact.scheduler"
    ARTIFACT_BINDING = "workstream.artifact.binding"
    ARTIFACT_GUIDE_READER = "workstream.artifact.guide_reader"
    ARTIFACT_MATERIALIZER = "workstream.artifact.materializer"
    ARTIFACT_CHECKER_OUTPUT = "workstream.artifact.checker_output"


SERVICE_IDENTITIES = frozenset(ServiceIdentity)
SERVICE_IDENTITY_VALUES = tuple(identity.value for identity in ServiceIdentity)
