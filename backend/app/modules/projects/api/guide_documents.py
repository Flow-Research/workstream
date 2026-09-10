"""Content-free guide manifests and attempt-scoped document/runtime capabilities."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Literal, Protocol
from uuid import UUID
import hashlib

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.core.hashing import canonical_json_hash

GuideDocumentMediaType = Literal[
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]
DOCUMENT_EXTENSIONS: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}


def guide_document_handle(run_id: UUID, source_item_id: UUID, ingest_id: UUID) -> UUID:
    """Derive the sole run-scoped opaque selector, mirrored by the SQL custody guard."""
    payload = f"workstream.guide-document-handle.v1:{run_id}:{source_item_id}:{ingest_id}"
    return UUID(bytes=hashlib.sha256(payload.encode("ascii")).digest()[:16])


class GuideDocumentVersion(BaseModel):
    """Exact committed original; metadata never grants access to its stored bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_item_id: UUID
    ingest_id: UUID
    item_order: StrictInt = Field(ge=0)
    put_attempt_id: UUID
    content_id: UUID
    replica_id: UUID
    storage_namespace_id: str = Field(min_length=1, max_length=20)
    namespace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: StrictInt = Field(gt=0)
    media_type: GuideDocumentMediaType

    @property
    def filename(self) -> str:
        """Generate the workspace name without source-controlled path components."""
        return f"{self.source_item_id}.{DOCUMENT_EXTENSIONS[self.media_type]}"


class GuideDocumentManifest(BaseModel):
    """One immutable metadata snapshot, with no extracted text or storage coordinates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    guide_id: UUID
    guide_version: str = Field(min_length=1, max_length=50)
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    setup_run_id: UUID
    setup_generation: StrictInt = Field(ge=1)
    documents: tuple[GuideDocumentVersion, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_documents(self) -> GuideDocumentManifest:
        """Require unique source/version ownership and canonical source order."""
        for attribute in ("source_item_id", "ingest_id", "item_order", "put_attempt_id"):
            values = [getattr(item, attribute) for item in self.documents]
            if len(values) != len(set(values)):
                raise ValueError("guide manifest document identity is duplicated")
        if tuple(sorted(self.documents, key=lambda item: item.item_order)) != self.documents:
            raise ValueError("guide manifest documents are not in source order")
        return self

    @property
    def sha256(self) -> str:
        """Bind exact original metadata and execution lineage without source bodies."""
        return canonical_json_hash(self.model_dump(mode="json"))

    def handle_for(self, document: GuideDocumentVersion) -> str:
        """Mint an opaque selector meaningful only inside this run's exact grant."""
        if document not in self.documents:
            raise ValueError("document is not assigned to this manifest")
        return str(guide_document_handle(self.setup_run_id, document.source_item_id, document.ingest_id))

    def agent_projection(self) -> dict[str, object]:
        """Expose version references and handles, excluding server storage identities."""
        return {
            "manifest_sha256": self.sha256,
            "documents": [
                {
                    "handle": self.handle_for(item),
                    "source_item_id": str(item.source_item_id),
                    "document_version_id": str(item.ingest_id),
                    "sha256": item.sha256,
                    "byte_count": item.byte_count,
                    "media_type": item.media_type,
                    "filename": item.filename,
                }
                for item in self.documents
            ],
        }


@dataclass(frozen=True, slots=True)
class GuideDocumentManifestRequest:
    """Exact current generation requested from the ART metadata owner."""

    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    project_setup_run_id: UUID
    setup_generation: int


class GuideDocumentManifestPort(Protocol):
    """Load only complete committed-document metadata for one setup generation."""

    async def load(self, request: GuideDocumentManifestRequest) -> GuideDocumentManifest: ...


class GuideDocumentUnavailable(RuntimeError):
    """Bounded source failure; never include storage references or source content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class OpenGuideDocument:
    """Scratch-owned, fully checksum-verified bytes valid only inside the open scope."""

    document: GuideDocumentVersion
    reader: BinaryIO


class GuideDocumentGrant(Protocol):
    """Already-fenced exact-file capability, revalidated on every tool access."""

    def open(self, handle: str) -> AbstractAsyncContextManager[OpenGuideDocument]: ...

    async def close(self) -> None: ...


ProviderResourceKind = Literal["container", "file", "attachment"]


@dataclass(frozen=True, slots=True)
class GuideRuntimeResource:
    """One recorded provider resource owned by the already-fenced attempt."""

    allocation_id: UUID
    kind: ProviderResourceKind
    provider_id: str
    parent_provider_id: str | None
    document_handle: str | None
    expires_at: datetime


class GuideRuntimeCleanupCustody(Protocol):
    """Exact recorded-resource cleanup; no source bytes or inference authority."""

    async def cleanup_resources(self) -> tuple[GuideRuntimeResource, ...]: ...

    async def record_deleted(self, allocation_id: UUID) -> None: ...

    async def record_cleanup_failed(self, allocation_id: UUID) -> None: ...


class GuideRuntimeResourceCustody(GuideRuntimeCleanupCustody, Protocol):
    """Attempt-owned allocation and exact-ID cleanup authority, without ORM coupling."""

    async def begin_allocation(
        self,
        *,
        kind: ProviderResourceKind,
        document_handle: str | None,
        parent_provider_id: str | None,
        expires_at: datetime,
        source_file_allocation_id: UUID | None = None,
        container_allocation_id: UUID | None = None,
    ) -> UUID: ...

    async def record_allocated(self, allocation_id: UUID, provider_id: str) -> None: ...

    async def record_uncertain(self, allocation_id: UUID) -> None: ...

    async def record_document_open(self, handle: str) -> None: ...

    async def opened_handles(self) -> frozenset[str]: ...



@dataclass(frozen=True, slots=True)
class GuideRuntimeCapabilities:
    """Non-serializable execution capabilities issued only after the dispatch fence."""

    documents: GuideDocumentGrant
    resources: GuideRuntimeResourceCustody


class GuideDocumentAccessFactory(Protocol):
    """ART composition opens an exact fenced grant with owned scratch lifecycle."""

    def __call__(self, attempt_id: UUID, manifest: GuideDocumentManifest,
                 configuration) -> AbstractAsyncContextManager[GuideDocumentGrant]: ...


@dataclass(frozen=True, slots=True)
class ProjectGuideDocumentSource:
    """One locked source item and its immutable committed-ingest identity."""

    source_item_id: UUID
    ingest_id: UUID
    item_order: int
    sha256: str
    byte_count: int
    media_type: str


@dataclass(frozen=True, slots=True)
class ProjectGuideDocumentLineage:
    """Current draft guide generation required by the document provider."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    documents: tuple[ProjectGuideDocumentSource, ...]


class ProjectGuideDocumentScopePort(Protocol):
    """PROJECTS scope locks live until the composition-owned transaction ends."""

    async def lock_manifest_source(self, request: GuideDocumentManifestRequest) -> ProjectGuideDocumentLineage: ...

    async def lock_access_attempt(self, attempt_id: UUID, manifest: GuideDocumentManifest) -> None: ...
