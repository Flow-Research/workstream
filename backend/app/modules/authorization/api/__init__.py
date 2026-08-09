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
    "ResourceFacts",
    "ResourceValue",
    "action_id",
    "permission_id",
)
