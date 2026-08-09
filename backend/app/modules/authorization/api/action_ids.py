"""Stable opaque identifiers accepted by the public authorization boundary."""

from __future__ import annotations

from typing import NewType


ActionId = NewType("ActionId", str)
PermissionId = NewType("PermissionId", str)


def action_id(value: str) -> ActionId:
    """Create a non-empty action identifier without importing the catalogue."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("action identifier must not be empty")
    return ActionId(normalized)


def permission_id(value: str) -> PermissionId:
    """Create a non-empty permission identifier without importing the catalogue."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("permission identifier must not be empty")
    return PermissionId(normalized)
