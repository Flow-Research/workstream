"""Sealed process-local custody for one checked submission continuation."""

from __future__ import annotations

from typing import final
from uuid import UUID

from app.modules.artifacts.pre_submit_evidence import PreSubmitPassCapability
from app.modules.artifacts.sources import CommittedArtifactSource, PreparedArtifact


@final
class SubmissionBundlePreparedCustody:
    """Unforgeable join of live prepared bytes and their fresh pass capability."""

    __slots__ = ("_capability", "_prepared")

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("submission bundle custody requires live prepared work")

    @classmethod
    def _from_live_preparation(
        cls,
        *,
        prepared: PreparedArtifact,
        capability: PreSubmitPassCapability,
    ) -> SubmissionBundlePreparedCustody:
        if (
            type(prepared) is not PreparedArtifact
            or type(capability) is not PreSubmitPassCapability
        ):
            raise TypeError("submission bundle custody requires live prepared work")
        capability._assert_live_prepared_custody(
            prepared_generation_id=prepared.generation_id,
            archive_sha256=prepared.commitment.sha256,
        )
        custody = object.__new__(cls)
        custody._prepared = prepared
        custody._capability = capability
        return custody

    @property
    def prepared_generation_id(self) -> UUID:
        return self._prepared.generation_id

    @property
    def pass_capability(self) -> PreSubmitPassCapability:
        return self._capability

    @property
    def source(self) -> CommittedArtifactSource:
        return self._prepared.committed_source
