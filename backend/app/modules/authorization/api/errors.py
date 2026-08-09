"""Stable fail-closed errors exposed by the authorization boundary."""


class AuthorizationBoundaryError(RuntimeError):
    """Base error that reveals no private evaluator or persistence detail."""


class AuthorizationDenied(AuthorizationBoundaryError):
    """The requested action is not authorized for the exact supplied facts."""


class PreparedAuthorizationInvalid(AuthorizationBoundaryError):
    """A prepared capability is stale, forged, copied, replayed, or mismatched."""


class AuthorizationUnavailable(AuthorizationBoundaryError):
    """The authorization boundary cannot safely make or persist a decision."""
