"""Exact POST archive provenance, excluding provider coordinates and read authority."""
from pydantic import model_serializer, model_validator

from app.modules.checkers.api.canonical_values import CheckerValue, ResourceId, Sha256, VersionNumber


class PostSubmitArtifactCustody(CheckerValue):
    """One accepted source or retained verified-put witness, never a mixed lineage."""

    verification_receipt_id: ResourceId | None = None
    verification_job_id: ResourceId | None = None
    verification_generation: VersionNumber | None = None
    source_operation_id: ResourceId | None = None
    accepted_source_sha256: Sha256 | None = None
    acceptance_receipt_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def exact_custody(self):
        verified = (self.verification_receipt_id, self.verification_job_id, self.verification_generation)
        source = (self.source_operation_id, self.accepted_source_sha256, self.acceptance_receipt_sha256)
        if not ((all(v is not None for v in verified) and all(v is None for v in source))
                or (all(v is None for v in verified) and all(v is not None for v in source))):
            raise ValueError("POST material requires one complete custody witness")
        return self

    @model_serializer(mode="wrap")
    def retained_custody_shape(self, handler):
        """Keep retained canonical evidence byte-for-byte free of new null fields."""
        body = handler(self)
        absent = ("source_operation_id", "accepted_source_sha256", "acceptance_receipt_sha256")
        if self.source_operation_id is not None:
            absent = ("verification_receipt_id", "verification_job_id", "verification_generation")
        for field in absent:
            body.pop(field, None)
        return body
