"""Neutral contributor packet facts used by the selected PRE flow."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.hashing import canonical_json_hash


ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES = frozenset({"local", "s3"})


@dataclass(frozen=True, slots=True)
class SubmissionPacketView:
    """Bounded optional text accompanying server-owned verified ZIP facts."""

    summary: str | None = None
    contributor_attestation: str | None = None

    def __post_init__(self) -> None:
        if self.summary is None and self.contributor_attestation is None:
            return
        for value in (self.summary, self.contributor_attestation):
            if type(value) is not str or len(value.encode("utf-8")) > 64 * 1024:
                raise ValueError("submission packet text is invalid")

    def canonical_body(self) -> dict[str, str]:
        """Read retired text only from retained checker evidence."""
        if self.summary is None or self.contributor_attestation is None:
            return {}
        return {"summary": self.summary, "contributor_attestation": self.contributor_attestation}

    @property
    def sha256(self) -> str:
        """Commit to the same exact text at preparation and Submission creation."""
        return canonical_json_hash(self.canonical_body())


__all__ = ("ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES", "SubmissionPacketView")
