"""The sole dependency-free public interface of the authorization module."""

from .action_ids import ActionId, PermissionId, action_id, permission_id
from .decisions import AuthorizationDecision, DecisionOutcome
from .errors import (
    AuthorizationBoundaryError,
    AuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
)
from .facts import ActorIdentityFacts, ActorKind, JsonScalar, ResourceFacts, ResourceValue
from .ports import AuthorizationPort, PreparedAuthorizationPort, PreparedHandleT
from .project_guide_compilation import (
    ProjectGuideCompilationAuthorizationPort,
    ProjectGuideCompilationExecutePersistFacts,
    ProjectGuideCompilationExecutePreflightFacts,
    ProjectGuideCompilationRequestFacts,
    project_guide_compilation_execute_resource_digest,
    project_guide_compilation_facts_digest,
    project_guide_compilation_request_authority_digest,
    project_guide_compilation_request_resource_digest,
)

__all__ = (
    "ActionId",
    "ActorIdentityFacts",
    "ActorKind",
    "AuthorizationBoundaryError",
    "AuthorizationDecision",
    "AuthorizationDenied",
    "AuthorizationPort",
    "AuthorizationUnavailable",
    "DecisionOutcome",
    "JsonScalar",
    "PermissionId",
    "PreparedAuthorizationInvalid",
    "PreparedAuthorizationPort",
    "PreparedHandleT",
    "ProjectGuideCompilationAuthorizationPort",
    "ProjectGuideCompilationExecutePersistFacts",
    "ProjectGuideCompilationExecutePreflightFacts",
    "ProjectGuideCompilationRequestFacts",
    "project_guide_compilation_execute_resource_digest",
    "project_guide_compilation_facts_digest",
    "project_guide_compilation_request_authority_digest",
    "project_guide_compilation_request_resource_digest",
    "ResourceFacts",
    "ResourceValue",
    "action_id",
    "permission_id",
)
