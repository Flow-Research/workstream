"""Strict request, result, and hashing contracts for fixed guide parsing."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from workstream_external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterError,
    ExternalServiceAdapterIdentity,
)
from app.interfaces.guide_document_tools import GuideDocumentMediaType, GuideTextLocator


GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY = "guide_document_parser"
GUIDE_DOCUMENT_PARSER_PROVIDER_KEY = "unix_socket"
GUIDE_DOCUMENT_PARSER_PROTOCOL = "workstream.guide_document_parser.v1"
MAXIMUM_SOURCE_BYTES = 64 * 1024 * 1024
MAXIMUM_EXTRACTED_CHARACTERS = 4 * 1024 * 1024
MAXIMUM_RESULT_CHARACTERS = 65_536
MAXIMUM_LOCATORS = 512
MAXIMUM_SEARCH_QUERY_CHARACTERS = 512
MAXIMUM_REQUEST_METADATA_BYTES = 8 * 1024
MAXIMUM_RESPONSE_BYTES = 512 * 1024

GuideDocumentParserOperation = Literal["read", "search"]
GuideDocumentParserRejectionReason = Literal[
    "document_encrypted",
    "document_limit_exceeded",
    "document_malformed",
    "document_unsupported",
]

_PARSER_BUILD_MANIFEST = {
    "domain": "workstream.guide-document-parser-build.v1",
    "parser": "workstream_fixed_guide_parser",
    "version": "1",
    "pypdf": "6.21.2",
    "defusedxml": "0.7.1",
}


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(payload).hexdigest()}"


FIXED_PARSER_BUILD_DIGEST = _canonical_hash(_PARSER_BUILD_MANIFEST)


class GuideDocumentParserRequest(BaseModel):
    """One source-bound read/search request with no custody or path selector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_byte_count: StrictInt = Field(gt=0, le=MAXIMUM_SOURCE_BYTES)
    media_type: GuideDocumentMediaType
    operation: GuideDocumentParserOperation
    offset: StrictInt = Field(default=0, ge=0, le=MAXIMUM_EXTRACTED_CHARACTERS)
    limit: StrictInt = Field(gt=0, le=MAXIMUM_RESULT_CHARACTERS)
    query: str | None = Field(
        default=None, min_length=1, max_length=MAXIMUM_SEARCH_QUERY_CHARACTERS
    )

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        """Keep read and literal-search arguments closed and unambiguous."""
        if self.operation == "read":
            if self.query is not None:
                raise ValueError("read requests cannot contain a query")
        elif self.query is None or self.limit > MAXIMUM_LOCATORS:
            raise ValueError("search requests require a query and bounded match limit")
        return self

    @property
    def request_hash(self) -> str:
        """Bind source identity, media type, operation, and all paging arguments."""
        return _canonical_hash(
            {
                "domain": "workstream.guide-document-parser-request.v1",
                **self.model_dump(mode="json"),
            }
        )


class GuideDocumentParserResponse(BaseModel):
    """Strict parser output with complete request/source/build bindings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    request_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_byte_count: StrictInt = Field(gt=0, le=MAXIMUM_SOURCE_BYTES)
    media_type: GuideDocumentMediaType
    operation: GuideDocumentParserOperation
    parser_build_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    text: str = Field(max_length=MAXIMUM_RESULT_CHARACTERS)
    locators: tuple[GuideTextLocator, ...] = Field(max_length=MAXIMUM_LOCATORS)
    next_offset: StrictInt | None = Field(default=None, ge=0, le=MAXIMUM_EXTRACTED_CHARACTERS)
    total_characters: StrictInt = Field(ge=0, le=MAXIMUM_EXTRACTED_CHARACTERS)

    def response_hash_payload(self) -> dict[str, object]:
        """Return the canonical response body covered by ``response_hash``."""
        body = self.model_dump(mode="json")
        body.pop("response_hash")
        return {"domain": "workstream.guide-document-parser-response.v1", **body}

    def validate_against(self, request: GuideDocumentParserRequest) -> None:
        """Reject any reply not produced for this exact request and parser build."""
        locator_ranges = tuple((locator.start, locator.end) for locator in self.locators)
        locators_are_ordered = all(
            start < end and (index == 0 or self.locators[index - 1].end <= start)
            for index, (start, end) in enumerate(locator_ranges)
        )
        if (
            self.request_id != request.request_id
            or self.request_hash != request.request_hash
            or self.source_sha256 != request.source_sha256
            or self.source_byte_count != request.source_byte_count
            or self.media_type != request.media_type
            or self.operation != request.operation
            or self.parser_build_digest != FIXED_PARSER_BUILD_DIGEST
            or self.response_hash != _canonical_hash(self.response_hash_payload())
            or any(
                locator.end > len(self.text) or locator.start > locator.end
                for locator in self.locators
            )
            or not locators_are_ordered
            or (self.next_offset is not None and self.next_offset > self.total_characters)
        ):
            raise ValueError("guide parser response binding is invalid")
        if request.operation == "read":
            consumed_to = request.offset + len(self.text)
            if (
                len(self.text) > request.limit
                or (request.offset >= self.total_characters and (self.text or self.locators))
                or (self.next_offset is not None and self.next_offset != consumed_to)
                or (self.next_offset is None and consumed_to < self.total_characters)
            ):
                raise ValueError("guide parser read response is invalid")
        else:
            assert request.query is not None
            folded_query = request.query.casefold()
            if (
                len(self.locators) > request.limit
                or bool(self.text) != bool(self.locators)
                or any(
                    folded_query not in self.text[locator.start : locator.end].casefold()
                    for locator in self.locators
                )
                or (
                    self.next_offset is not None
                    and not request.offset < self.next_offset <= self.total_characters
                )
            ):
                raise ValueError("guide parser search response is invalid")

    @classmethod
    def create(
        cls,
        *,
        request: GuideDocumentParserRequest,
        text: str,
        locators: tuple[GuideTextLocator, ...],
        next_offset: int | None,
        total_characters: int,
    ) -> GuideDocumentParserResponse:
        """Construct and hash one successful fixed-parser response."""
        unsealed = {
            "request_id": request.request_id,
            "request_hash": request.request_hash,
            "source_sha256": request.source_sha256,
            "source_byte_count": request.source_byte_count,
            "media_type": request.media_type,
            "operation": request.operation,
            "parser_build_digest": FIXED_PARSER_BUILD_DIGEST,
            "text": text,
            "locators": locators,
            "next_offset": next_offset,
            "total_characters": total_characters,
        }
        response_hash = _canonical_hash(
            GuideDocumentParserResponse(
                **unsealed,
                response_hash="sha256:" + "0" * 64,
            ).response_hash_payload()
        )
        candidate = GuideDocumentParserResponse(
            **unsealed,
            response_hash=response_hash,
        )
        candidate.validate_against(request)
        return candidate


class GuideDocumentParserRejectedError(ExternalServiceAdapterError):
    """A valid fixed parser deterministically rejected the supplied document."""

    code = "guide_document_parser_rejected"
    category = "document"

    def __init__(
        self,
        identity: ExternalServiceAdapterIdentity,
        reason: GuideDocumentParserRejectionReason,
    ) -> None:
        self.reason = reason
        super().__init__(identity)


class GuideDocumentParserAdapter(ExternalServiceAdapter, Protocol):
    """Typed lower-level parser capability; it grants no document authority."""

    async def parse(
        self,
        request: GuideDocumentParserRequest,
        source: bytes,
    ) -> GuideDocumentParserResponse: ...


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
    "MAXIMUM_EXTRACTED_CHARACTERS",
    "MAXIMUM_LOCATORS",
    "MAXIMUM_REQUEST_METADATA_BYTES",
    "MAXIMUM_RESPONSE_BYTES",
    "MAXIMUM_RESULT_CHARACTERS",
    "MAXIMUM_SEARCH_QUERY_CHARACTERS",
    "MAXIMUM_SOURCE_BYTES",
)
