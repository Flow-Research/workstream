"""Sealed byte-source values for provider-neutral artifact preparation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, final

from app.core.cancellation import await_completion_preserving_cancellation


_COMMITTED_SOURCE_SEAL = object()


class _PreparedArtifactOwner(Protocol):
    """Private lifecycle operations retained by one preparation service."""

    def open_committed_stream(
        self,
        binding: object,
        commitment: ArtifactCommitment,
    ) -> AsyncIterator[bytes]:
        """Open the one second-pass stream bound to a preparation."""

    async def release_prepared_artifact(self, binding: object) -> None:
        """Release one preparation and its scratch reservation."""

    def claim_prepared_commitment(self, binding: object) -> ArtifactCommitment:
        """Claim the server-computed commitment for one registered binding."""

    def validates_committed_source(
        self,
        binding: object,
        commitment: ArtifactCommitment,
        source: CommittedArtifactSource,
    ) -> bool:
        """Return whether this exact binding and commitment remain service-owned."""

    def register_committed_source(
        self,
        binding: object,
        source: CommittedArtifactSource,
    ) -> None:
        """Bind the exact service-minted source identity once."""


@final
@dataclass(frozen=True, slots=True)
class ArtifactCommitment:
    """Server-computed immutable identity for exact artifact bytes."""

    sha256: str
    byte_count: int
    media_type: str

    def __post_init__(self) -> None:
        """Reject noncanonical commitment facts."""
        self.validate_sha256(self.sha256)
        self.validate_byte_count(self.byte_count)
        self.validate_media_type(self.media_type)

    @staticmethod
    def validate_sha256(sha256: str) -> None:
        """Require one canonical lower-case SHA-256 commitment."""
        if (
            not isinstance(sha256, str)
            or len(sha256) != 71
            or not sha256.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in sha256[7:])
        ):
            raise ValueError("artifact commitment digest is invalid")

    @staticmethod
    def validate_byte_count(byte_count: int) -> None:
        """Require one exact nonnegative byte count."""
        if type(byte_count) is not int or byte_count < 0:
            raise ValueError("artifact commitment byte count is invalid")

    @staticmethod
    def validate_media_type(media_type: str) -> None:
        """Require one bounded printable media type."""
        if (
            not isinstance(media_type, str)
            or not media_type
            or len(media_type) > 255
            or any(ord(character) < 32 or ord(character) == 127 for character in media_type)
        ):
            raise ValueError("artifact commitment media type is invalid")


@final
class CommittedArtifactSource:
    """One server commitment inseparably bound to its second-pass stream."""

    __slots__ = ("_binding", "_commitment", "_owner", "_seal")

    def __init__(self, *_: object, **__: object) -> None:
        """Reject all direct construction."""
        raise TypeError("CommittedArtifactSource can only be created by artifact preparation")

    @property
    def commitment(self) -> ArtifactCommitment:
        """Return the server-computed commitment bound to this stream."""
        self._assert_sealed()
        return self._commitment

    def stream(self) -> AsyncIterator[bytes]:
        """Open the single bounded second-pass stream."""
        self._assert_sealed()
        return self._owner.open_committed_stream(self._binding, self._commitment)

    def _assert_sealed(self) -> None:
        """Require this source to remain bound to its minting preparation service."""
        from app.modules.artifacts.preparation import (
            ArtifactPreparationService,
            ArtifactScratchIntegrityError,
        )

        owner = getattr(self, "_owner", None)
        if (
            getattr(self, "_seal", None) is not _COMMITTED_SOURCE_SEAL
            or type(owner) is not ArtifactPreparationService
            or not owner.validates_committed_source(self._binding, self._commitment, self)
        ):
            raise ArtifactScratchIntegrityError("committed artifact source is unavailable")

    def __repr__(self) -> str:
        """Avoid exposing scratch identifiers or paths."""
        return f"CommittedArtifactSource(commitment={self.commitment!r})"


@final
class PreparedArtifact:
    """Lifecycle owner for one prepared source and its scratch reservation."""

    __slots__ = ("_binding", "_closed", "_committed_source", "_owner")

    def __init__(self, *_: object, **__: object) -> None:
        """Reject all direct construction."""
        raise TypeError("PreparedArtifact can only be created by artifact preparation")

    @classmethod
    def _from_preparation_service(
        cls,
        *,
        owner: _PreparedArtifactOwner,
        binding: object,
    ) -> PreparedArtifact:
        """Mint a handle only from a live registered preparation service."""
        from app.modules.artifacts.preparation import ArtifactPreparationService

        if type(owner) is not ArtifactPreparationService:
            raise TypeError("PreparedArtifact can only be created by artifact preparation")
        commitment = owner.claim_prepared_commitment(binding)
        prepared = object.__new__(cls)
        prepared._owner = owner
        prepared._binding = binding
        prepared._closed = False
        source = object.__new__(CommittedArtifactSource)
        source._owner = owner
        source._binding = binding
        source._commitment = commitment
        source._seal = _COMMITTED_SOURCE_SEAL
        owner.register_committed_source(binding, source)
        prepared._committed_source = source
        return prepared

    @property
    def commitment(self) -> ArtifactCommitment:
        """Return the server-computed commitment."""
        return self._committed_source.commitment

    @property
    def committed_source(self) -> CommittedArtifactSource:
        """Return the sealed commitment and second-pass stream pair."""
        if self._closed:
            raise RuntimeError("prepared artifact is closed")
        return self._committed_source

    async def close(self) -> None:
        """Release scratch state exactly once."""
        if self._closed:
            return
        cleanup = asyncio.create_task(self._owner.release_prepared_artifact(self._binding))
        try:
            await await_completion_preserving_cancellation(cleanup)
        except asyncio.CancelledError:
            if cleanup.done() and not cleanup.cancelled() and cleanup.exception() is None:
                self._closed = True
            raise
        else:
            self._closed = True

    async def __aenter__(self) -> CommittedArtifactSource:
        """Enter the bounded provider-I/O lifetime."""
        return self.committed_source

    async def __aexit__(self, *_: object) -> None:
        """Release scratch state after provider I/O."""
        await self.close()

    def __repr__(self) -> str:
        """Avoid exposing scratch identifiers or paths."""
        return f"PreparedArtifact(commitment={self.commitment!r}, closed={self._closed!r})"
