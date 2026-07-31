"""Shared database error inspection helpers."""

from sqlalchemy.exc import IntegrityError


def integrity_constraint_name(exc: IntegrityError) -> str | None:
    """Resolve a violated constraint across supported PostgreSQL drivers."""
    original = exc.orig
    return (
        getattr(getattr(original, "__cause__", None), "constraint_name", None)
        or getattr(original, "constraint_name", None)
        or getattr(getattr(original, "diag", None), "constraint_name", None)
    )
