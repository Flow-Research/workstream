from __future__ import annotations

import re
from typing import Protocol

_BEARER = re.compile(r"^Bearer [A-Za-z0-9\-._~+/]+=*$", re.ASCII | re.IGNORECASE)
_SAFE_CORRELATION = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    re.ASCII,
)


class HeaderCollection(Protocol):
    def getlist(self, key: str) -> list[str]: ...


class CredentialError(ValueError):
    """A request did not contain exactly one transport-safe bearer."""


def request_bearer(headers: HeaderCollection) -> str:
    values = headers.getlist("authorization")
    if len(values) != 1 or not _BEARER.fullmatch(values[0]):
        raise CredentialError("one well-formed bearer is required")
    return values[0]


def request_correlation_id(headers: HeaderCollection) -> str | None:
    values = headers.getlist("x-correlation-id")
    if not values:
        values = headers.getlist("x-request-id")
    if len(values) == 1 and _SAFE_CORRELATION.fullmatch(values[0]):
        return values[0]
    return None
