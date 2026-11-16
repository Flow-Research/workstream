"""ART's pure validation implementation for the CHECKERS consumer port."""

import json

from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.api.submission_intake import SealedSubmissionSource
from app.modules.artifacts.api.submission_manifest import validate_submission_manifest
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.api.source_contracts import SubmissionArchiveLimitsView, SelectedPreSubmitSourceContracts


class ArtifactPreSubmitSourceContracts(SelectedPreSubmitSourceContracts):
    """Retain one canonical source, limits and manifest validator."""

    def parse_source(self, body: object) -> SealedSubmissionSource:
        value = SealedSubmissionSource.model_validate_json(json.dumps(body, allow_nan=False))
        if value.model_dump(mode="json") != body:
            raise ValueError("selected PRE source is not canonical")
        return value

    def require_source(self, source: object) -> SealedSubmissionSource:
        if type(source) is not SealedSubmissionSource:
            raise ValueError("selected PRE source type is invalid")
        return SealedSubmissionSource.model_validate(source)

    def parse_limits(self, body: object) -> SubmissionArchiveLimits:
        if type(body) is not dict:
            raise ValueError("selected PRE archive limits are invalid")
        try:
            limits = SubmissionArchiveLimits(**body)
        except TypeError as exc:
            raise ValueError("selected PRE archive limits are invalid") from exc
        if limits.canonical_body() != body:
            raise ValueError("selected PRE archive limits are not canonical")
        return limits

    def require_limits(self, limits: object) -> SubmissionArchiveLimits:
        if type(limits) is not SubmissionArchiveLimits:
            raise ValueError("selected PRE archive limits type is invalid")
        return self.parse_limits(limits.canonical_body())

    def validate_manifest(
        self, body: object, *, sha256: str, limits: SubmissionArchiveLimitsView,
    ) -> tuple[SubmissionMaterialEntry, ...]:
        inspection = validate_submission_manifest(
            body, sha256=sha256, limits=self.require_limits(limits),
        )
        return tuple(SubmissionMaterialEntry(
            entry.normalized_path, entry.entry_type.value, entry.byte_count,
            entry.sha256, entry.executable,
        ) for entry in inspection.entries)
