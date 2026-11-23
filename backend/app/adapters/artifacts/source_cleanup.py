"""Private deletion capabilities, kept off the upload/read ArtifactStore port."""
from app.adapters.artifacts.local_submission_source import LocalSubmissionSource
from workstream_external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.api.submission_cleanup import SUBMISSION_SOURCE_CLEANUP_CAPABILITY, SubmissionSourceRemoval


class LocalSubmissionSourceCleanup:
    """Separate composition-owned capability over the pinned Local namespace."""

    def __init__(self, store):
        """Bind cleanup to the local namespace and its source primitives."""
        self._store = store
        self._source = LocalSubmissionSource(store)

    @property
    def identity(self):
        """Advertise the separate source-cleanup capability and adapter name."""
        return ExternalServiceAdapterIdentity(SUBMISSION_SOURCE_CLEANUP_CAPABILITY, "local")

    def close(self):
        """Release the cleanup store resources."""
        self._store.close()

    async def remove(self, source, upload):
        """Delete exact sealed bytes and observe object and part absence."""
        await self._store._source_io(self._source.delete_sealed, source, upload)
        # The shared operation lock drains Local writers. Retained seal/upload
        # metadata prevent subsequent begin/part/complete from reopening the key.
        parts_absent = await self._store.source_upload_parts_absent(upload)
        absent = await self._store.observe_sealed_source(source) is None
        return SubmissionSourceRemoval(source, absent, True, parts_absent)


class S3SubmissionSourceCleanup:
    """Exact-version capability over a separately credentialed cleanup store.

    Construction belongs to the cleanup composition root; never pass the upload
    store here. Native AWS remains subject to the source capability proof gate.
    """

    def __init__(self, cleanup_store):
        """Bind the separately credentialed cleanup store supplied by composition."""
        self._store = cleanup_store

    @property
    def identity(self):
        """Advertise the separate source-cleanup capability and adapter name."""
        return ExternalServiceAdapterIdentity(SUBMISSION_SOURCE_CLEANUP_CAPABILITY, "s3_compatible")

    def close(self):
        """Release the cleanup store resources."""
        self._store.close()

    async def _absent(self, source):
        """Prove exact-version absence without treating bucket loss or denial as cleanup."""
        from botocore.exceptions import ClientError
        from app.interfaces.artifacts import ArtifactProviderOperationEvidence

        async with self._store._source_client(source.location, ArtifactProviderOperationEvidence()) as client:
            try:
                response = await client.head_object(
                    Bucket=self._store._bucket, Key=self._store._source_key(source.location),
                    VersionId=source.provider_generation,
                )
            except ClientError as error:
                # A missing bucket or a denied observation is never source
                # absence. Do not use the general reader's broader missing map.
                if (error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404
                        and error.response.get("Error", {}).get("Code") in {"NoSuchKey", "NoSuchVersion"}):
                    return True
                if (error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404
                        and error.response.get("Error", {}).get("Code") == "404"):
                    # HEAD may omit an XML error body. Require an independent
                    # successful bucket observation before accepting that code.
                    await client.head_bucket(Bucket=self._store._bucket)
                    return True
                raise
        self._store._check_source_response(source, response)
        return False

    async def remove(self, source, upload):
        """Delete only the sealed version and retain unresolved handle or version obligations."""
        from app.interfaces.artifacts import ArtifactOperationConflictError, ArtifactProviderOperationEvidence
        from app.modules.artifacts.api.submission_intake import SealedSubmissionSource, SubmissionSourceUpload

        source = SealedSubmissionSource.model_validate(source)
        upload = SubmissionSourceUpload.model_validate(upload)
        if (upload.intent.location != source.location
                or upload.intent.upload_fence != source.sealed_upload_fence):
            raise ArtifactOperationConflictError("source cleanup upload identity mismatch")
        # Sealed custody records successful completion of this exact upload.
        # NoSuchUpload proves its handle cannot accept a late part or completion;
        # an empty live handle or any other discovered handle is unresolved.
        parts_absent = await self._store.source_upload_parts_absent(upload)
        handles = await self._store.discover_source_uploads(upload.intent)
        if not parts_absent or handles:
            return SubmissionSourceRemoval(source, False, False, parts_absent)
        if not await self._absent(source):
            async with self._store._source_client(source.location, ArtifactProviderOperationEvidence()) as client:
                await client.delete_object(
                    Bucket=self._store._bucket, Key=self._store._source_key(source.location),
                    VersionId=source.provider_generation,
                )
        # A successful delete response is not the confirmation observation.
        absent = await self._absent(source)
        parts_absent = await self._store.source_upload_parts_absent(upload)
        handles = await self._store.discover_source_uploads(upload.intent)
        # Any additional generation or delete marker remains an operation-owned
        # reconciliation obligation. Removing our exact version cannot release
        # its charge while other bytes at the same managed key are unexplained.
        async with self._store._source_client(source.location, ArtifactProviderOperationEvidence()) as client:
            versions = await client.list_object_versions(
                Bucket=self._store._bucket, Prefix=self._store._source_key(source.location), MaxKeys=1,
            )
        versions_absent = (versions.get("IsTruncated") is False
                           and versions.get("Versions", []) == []
                           and versions.get("DeleteMarkers", []) == [])
        return SubmissionSourceRemoval(source, absent, parts_absent and not handles and versions_absent, parts_absent)
