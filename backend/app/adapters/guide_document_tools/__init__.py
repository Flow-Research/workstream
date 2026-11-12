"""Typed composition for the fixed guide-document parser capability."""

from __future__ import annotations

from pathlib import Path

from workstream_external_services import ExternalServiceAdapterFactory

from .client import (
    PARSER_SOCKET_GID,
    PARSER_SOCKET_MODE,
    PARSER_SOCKET_UID,
    UnixSocketGuideDocumentParserAdapter,
)
from .contracts import (
    FIXED_PARSER_BUILD_DIGEST,
    GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
    GUIDE_DOCUMENT_PARSER_PROTOCOL,
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentMediaType,
    GuideDocumentParserAdapter,
    GuideDocumentParserOperation,
    GuideDocumentParserRejectedError,
    GuideDocumentParserRejectionReason,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
)


def guide_document_parser_factory(
    *,
    socket_path: Path,
    timeout_seconds: float,
    expected_socket_uid: int = PARSER_SOCKET_UID,
    expected_socket_gid: int = PARSER_SOCKET_GID,
) -> ExternalServiceAdapterFactory[UnixSocketGuideDocumentParserAdapter]:
    """Register the sole fixed parser provider in its typed capability factory."""
    factory = ExternalServiceAdapterFactory[UnixSocketGuideDocumentParserAdapter](
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY
    )
    factory.register(
        GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
        lambda: UnixSocketGuideDocumentParserAdapter(
            socket_path=socket_path,
            timeout_seconds=timeout_seconds,
            expected_socket_uid=expected_socket_uid,
            expected_socket_gid=expected_socket_gid,
        ),
    )
    return factory


__all__ = (
    "FIXED_PARSER_BUILD_DIGEST",
    "GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY",
    "GUIDE_DOCUMENT_PARSER_PROTOCOL",
    "GUIDE_DOCUMENT_PARSER_PROVIDER_KEY",
    "GuideDocumentMediaType",
    "GuideDocumentParserAdapter",
    "GuideDocumentParserOperation",
    "GuideDocumentParserRejectedError",
    "GuideDocumentParserRejectionReason",
    "GuideDocumentParserRequest",
    "GuideDocumentParserResponse",
    "PARSER_SOCKET_GID",
    "PARSER_SOCKET_MODE",
    "PARSER_SOCKET_UID",
    "UnixSocketGuideDocumentParserAdapter",
    "guide_document_parser_factory",
)
