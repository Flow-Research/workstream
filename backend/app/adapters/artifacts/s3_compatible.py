"""Private S3-protocol implementation of the immutable ArtifactStore v2 port."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
import datetime
import hashlib
import inspect
import json
import os
from pathlib import Path
import random
import re
from typing import Any

from aiobotocore.config import AioConfig
from aiobotocore.credentials import (
    AioAssumeRoleWithWebIdentityProvider,
    AioContainerProvider,
    AioCredentialResolver,
    AioInstanceMetadataProvider,
    AioRefreshableCredentials,
)
from aiobotocore.session import AioSession
from aiobotocore.utils import (
    AioContainerMetadataFetcher,
    AioInstanceMetadataFetcher,
    _RefCountedSession,
)
from botocore import UNSIGNED
from botocore.awsrequest import AWSRequest
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    CredentialRetrievalError,
    HTTPClientError,
    InvalidIMDSEndpointError,
    MetadataRetrievalError,
    ReadTimeoutError,
)
from botocore.utils import (
    BadIMDSRequestError,
    RETRYABLE_HTTP_ERRORS,
    get_current_datetime,
)

from app.adapters.artifacts.references import (
    artifact_provider_object_ref,
    parse_artifact_provider_object_ref,
)
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.core.s3_validation import (
    canonical_minio_endpoint,
    is_canonical_s3_bucket,
    is_canonical_s3_prefix,
    is_canonical_s3_region,
)
from app.interfaces.artifacts import (
    ARTIFACT_STORE_CAPABILITY_KEY,
    ArtifactByteRange,
    ArtifactConfigurationError,
    ArtifactInputMismatchError,
    ArtifactIntegrityError,
    ArtifactLimitExceededError,
    ArtifactObjectHead,
    ArtifactObjectMissingError,
    ArtifactOperationConflictError,
    ArtifactPutObservation,
    ArtifactPutResult,
    ArtifactRangeInvalidError,
    ArtifactStoreError,
    ArtifactStoreNamespaceClaim,
    ArtifactStoreNamespaceIdentity,
    ArtifactStoreUnavailableError,
    artifact_store_namespace_material,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource


_IDENTITY = ExternalServiceAdapterIdentity(ARTIFACT_STORE_CAPABILITY_KEY, "s3_compatible")
_CONTAINER_RELATIVE_URI = re.compile(
    r"^/v2/credentials/[A-Za-z0-9._-]{1,512}$"
)
_PRECONDITION_ERROR_CODES = frozenset(
    {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"}
)
_MISSING_ERROR_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
_FORBIDDEN_AWS_CREDENTIAL_ENVIRONMENT = frozenset(
    {
        "AWS_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_CONFIG_FILE",
        "AWS_CREDENTIAL_FILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_LOGIN_CACHE_DIRECTORY",
        "AWS_PROFILE",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECRET_KEY",
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
        "AWS_SHARED_CREDENTIALS_FILE",
        "BOTO_CONFIG",
    }
)


class _SanitizedContainerMetadataFetcher(AioContainerMetadataFetcher):
    """Fetch ECS credentials without SDK logging response or exception data."""

    async def _retrieve_credentials(
        self,
        full_url: str,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if extra_headers is not None:
            headers.update(extra_headers)
        failed = False
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                return await self._get_response(
                    full_url,
                    headers,
                    self.TIMEOUT_SECONDS,
                )
            except MetadataRetrievalError:
                if attempt + 1 >= self.RETRY_ATTEMPTS:
                    failed = True
                    break
                await self._sleep(self.SLEEP_TIME)
        if failed:
            raise MetadataRetrievalError(
                error_msg="container metadata request failed"
            ) from None
        raise MetadataRetrievalError(error_msg="container metadata request failed")

    async def _get_response(
        self,
        full_url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        try:
            async with self._session.acquire() as session:
                request = AWSRequest(method="GET", url=full_url, headers=dict(headers))
                response = await session.send(request.prepare())
                response_text = (await response.content).decode("utf-8")
                if response.status_code != 200:
                    raise MetadataRetrievalError(
                        error_msg="container metadata returned a non-200 response"
                    )
                try:
                    parsed = json.loads(response_text)
                except ValueError:
                    raise MetadataRetrievalError(
                        error_msg="container metadata returned invalid JSON"
                    ) from None
                if not isinstance(parsed, dict):
                    raise MetadataRetrievalError(
                        error_msg="container metadata returned an invalid document"
                    )
                return parsed
        except RETRYABLE_HTTP_ERRORS:
            raise MetadataRetrievalError(
                error_msg="container metadata request failed"
            ) from None


class _SanitizedInstanceMetadataFetcher(AioInstanceMetadataFetcher):
    """Fetch IMDSv2 credentials without SDK logging response or exception data."""

    async def _fetch_metadata_token(self) -> str | None:
        self._assert_enabled()
        url = self._construct_url(self._TOKEN_PATH)
        headers = {"x-aws-ec2-metadata-token-ttl-seconds": self._TOKEN_TTL}
        self._add_user_agent(headers)
        request = AWSRequest(method="PUT", url=url, headers=headers)
        async with self._session.acquire() as session:
            for _ in range(self._num_attempts):
                try:
                    response = await session.send(request.prepare())
                    if response.status_code == 200:
                        return await response.text
                    if response.status_code in (403, 404, 405):
                        return None
                    if response.status_code == 400:
                        raise BadIMDSRequestError(request)
                except ReadTimeoutError:
                    return None
                except RETRYABLE_HTTP_ERRORS:
                    continue
                except HTTPClientError as error:
                    nested_error = error.kwargs.get("error")
                    name_resolution_failed = (
                        nested_error
                        and getattr(nested_error, "errno", None) == 8
                    ) or str(getattr(nested_error, "os_error", None)) == (
                        "Domain name not found"
                    )
                    if name_resolution_failed:
                        raise InvalidIMDSEndpointError(
                            endpoint=url,
                            error=error,
                        ) from None
                    raise
        return None

    async def _get_request(
        self,
        url_path: str,
        retry_func: Any,
        token: str | None = None,
    ) -> object:
        self._assert_enabled()
        if not token:
            self._assert_v1_enabled()
        retry_func = retry_func or self._default_retry
        url = self._construct_url(url_path)
        headers: dict[str, str] = {}
        if token is not None:
            headers["x-aws-ec2-metadata-token"] = token
        self._add_user_agent(headers)
        async with self._session.acquire() as session:
            for _ in range(self._num_attempts):
                try:
                    request = AWSRequest(method="GET", url=url, headers=headers)
                    response = await session.send(request.prepare())
                    should_retry = retry_func(response)
                    if inspect.isawaitable(should_retry):
                        should_retry = await should_retry
                    if not should_retry:
                        return response
                except RETRYABLE_HTTP_ERRORS:
                    continue
        raise self._RETRIES_EXCEEDED_ERROR_CLS()

    async def _log_imds_response(
        self,
        response: object,
        reason_to_log: str,
        log_body: bool = False,
    ) -> None:
        return None

    async def retrieve_iam_role_credentials(self) -> dict[str, Any]:
        try:
            token = await self._fetch_metadata_token()
            role_name = await self._get_iam_role(token)
            credentials = await self._get_credentials(role_name, token)
            if not self._contains_all_credential_fields(credentials):
                return {}
            resolved = {
                "role_name": role_name,
                "access_key": credentials["AccessKeyId"],
                "secret_key": credentials["SecretAccessKey"],
                "token": credentials["Token"],
                "expiry_time": credentials["Expiration"],
            }
            self._evaluate_expiration(resolved)
            return resolved
        except (self._RETRIES_EXCEEDED_ERROR_CLS, BadIMDSRequestError):
            return {}

    def _evaluate_expiration(self, credentials: dict[str, Any]) -> None:
        expiration = credentials.get("expiry_time")
        if expiration is None:
            return
        try:
            parsed_expiration = datetime.datetime.strptime(
                expiration,
                "%Y-%m-%dT%H:%M:%SZ",
            )
        except (TypeError, ValueError):
            return
        refresh_interval = self._config.get(
            "ec2_credential_refresh_window",
            60 * 10,
        )
        refresh_offset = datetime.timedelta(
            seconds=refresh_interval + random.randint(120, 600)
        )
        current_time = get_current_datetime()
        if current_time >= parsed_expiration - refresh_offset:
            credentials["expiry_time"] = (current_time + refresh_offset).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )


class _SanitizedContainerProvider(AioContainerProvider):
    """Build ECS credentials without SDK exception logging."""

    def _create_fetcher(self, full_uri: str, *_args: object, **_kwargs: object) -> Any:
        async def fetch_credentials() -> dict[str, Any]:
            retrieval_failed = False
            try:
                headers = self._build_headers()
                response = await self._fetcher.retrieve_full_uri(
                    full_uri,
                    headers=headers,
                )
            except MetadataRetrievalError:
                retrieval_failed = True
                response = {}
            if retrieval_failed:
                raise CredentialRetrievalError(
                    provider=self.METHOD,
                    error_msg="container metadata request failed",
                ) from None
            return {
                "access_key": response["AccessKeyId"],
                "secret_key": response["SecretAccessKey"],
                "token": response["Token"],
                "expiry_time": response["Expiration"],
                "account_id": response.get("AccountId"),
            }

        return fetch_credentials


class _SanitizedInstanceMetadataProvider(AioInstanceMetadataProvider):
    """Build IMDS credentials without SDK response-derived logging."""

    async def load(self) -> object | None:
        metadata = await self._role_fetcher.retrieve_iam_role_credentials()
        if not metadata:
            return None
        return AioRefreshableCredentials.create_from_metadata(
            metadata,
            method=self.METHOD,
            refresh_using=self._role_fetcher.retrieve_iam_role_credentials,
        )
_FORBIDDEN_AWS_NETWORK_ENVIRONMENT = frozenset(
    {
        "AWS_CA_BUNDLE",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_STS",
        "AWS_STS_REGIONAL_ENDPOINTS",
        "AWS_USE_DUALSTACK_ENDPOINT",
        "AWS_USE_FIPS_ENDPOINT",
        "CURL_CA_BUNDLE",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
    }
)
_WEB_IDENTITY_SOURCE_ENVIRONMENT = frozenset(
    {"AWS_ROLE_ARN", "AWS_ROLE_SESSION_NAME", "AWS_WEB_IDENTITY_TOKEN_FILE"}
)
_CONTAINER_SOURCE_ENVIRONMENT = frozenset(
    {
        "AWS_CONTAINER_AUTHORIZATION_TOKEN",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    }
)
_IAM_ROLE_SOURCE_ENVIRONMENT = frozenset(
    {
        "AWS_EC2_METADATA_DISABLED",
        "AWS_EC2_METADATA_SERVICE_ENDPOINT",
        "AWS_EC2_METADATA_SERVICE_ENDPOINT_MODE",
        "AWS_EC2_METADATA_V1_DISABLED",
    }
)
_ALLOWED_AWS_ENVIRONMENT_BY_METHOD = {
    "assume-role-with-web-identity": _WEB_IDENTITY_SOURCE_ENVIRONMENT,
    "container-role": frozenset({"AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"}),
    "iam-role": frozenset({"AWS_EC2_METADATA_V1_DISABLED"}),
}
_AWS_SOURCE_ENVIRONMENT_BY_METHOD = {
    "assume-role-with-web-identity": _WEB_IDENTITY_SOURCE_ENVIRONMENT,
    "container-role": _CONTAINER_SOURCE_ENVIRONMENT,
    "iam-role": _IAM_ROLE_SOURCE_ENVIRONMENT,
}


class S3CompatibleArtifactStoreBootstrap:
    """Composition-only namespace lifecycle for one pinned S3 namespace."""

    def __init__(self, adapter: S3CompatibleArtifactStore) -> None:
        """Own one configured adapter before PostgreSQL namespace admission."""
        if type(adapter) is not S3CompatibleArtifactStore:
            raise ValueError("S3-compatible artifact bootstrap adapter is invalid")
        self._adapter = adapter

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the canonical artifact-store/S3 adapter identity."""
        return self._adapter.identity

    @property
    def namespace_identity(self) -> ArtifactStoreNamespaceIdentity:
        """Return the configured provider namespace identity."""
        return self._adapter._namespace_identity

    def initialize_after_namespace_claim(
        self,
        claim: ArtifactStoreNamespaceClaim,
    ) -> S3CompatibleArtifactStore:
        """Return the byte store only after exact namespace admission."""
        return self._adapter._initialize_after_namespace_claim(claim)

    def close(self) -> None:
        """Release this bootstrap and invalidate its adapter."""
        self._adapter.close()


class S3CompatibleArtifactStore:
    """Immutable S3-protocol byte provider for MinIO and later AWS activation."""

    def __init__(
        self,
        *,
        provider_profile: str,
        region: str,
        endpoint_url: str | None,
        bucket: str,
        private_prefix: str,
        addressing_style: str,
        session: AioSession,
        buffer_bytes: int,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
        operation_total_timeout_seconds: float,
        max_pool_connections: int,
    ) -> None:
        """Pin one validated namespace and one isolated SDK session."""
        if provider_profile not in {"minio", "aws_s3"}:
            raise ArtifactConfigurationError("S3 provider profile is invalid")
        if not is_canonical_s3_region(region):
            raise ArtifactConfigurationError("S3 region is invalid")
        if not is_canonical_s3_bucket(bucket):
            raise ArtifactConfigurationError("S3 bucket is invalid")
        if not is_canonical_s3_prefix(private_prefix):
            raise ArtifactConfigurationError("S3 private prefix is invalid")
        if addressing_style not in {"path", "virtual"}:
            raise ArtifactConfigurationError("S3 addressing style is invalid")
        if provider_profile == "minio":
            try:
                endpoint_url = canonical_minio_endpoint(endpoint_url)
            except ValueError as error:
                raise ArtifactConfigurationError(str(error)) from None
        elif endpoint_url is not None:
            raise ArtifactConfigurationError("native AWS S3 endpoint is invalid")
        if not isinstance(session, AioSession):
            raise ArtifactConfigurationError("S3 credential session is invalid")
        if type(buffer_bytes) is not int or not 1 <= buffer_bytes <= 1024 * 1024:
            raise ArtifactConfigurationError("S3 artifact buffer is invalid")
        if type(max_pool_connections) is not int or not 1 <= max_pool_connections <= 256:
            raise ArtifactConfigurationError("S3 connection pool is invalid")
        for value in (
            connect_timeout_seconds,
            read_timeout_seconds,
            write_timeout_seconds,
            pool_timeout_seconds,
            operation_total_timeout_seconds,
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ArtifactConfigurationError("S3 operation timeout is invalid")

        self._provider_profile = provider_profile
        self._region = region
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._private_prefix = private_prefix
        self._addressing_style = addressing_style
        self._session = session
        self._buffer_bytes = buffer_bytes
        self._write_timeout_seconds = float(write_timeout_seconds)
        self._pool_timeout_seconds = float(pool_timeout_seconds)
        self._operation_total_timeout_seconds = float(operation_total_timeout_seconds)
        self._client_config = AioConfig(
            connect_timeout=float(connect_timeout_seconds),
            read_timeout=float(read_timeout_seconds),
            max_pool_connections=max_pool_connections,
            proxies={},
            retries={"max_attempts": 1, "mode": "standard"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={
                "addressing_style": addressing_style,
                "payload_signing_enabled": False,
            },
        )
        self._initialized = False

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the canonical artifact-store/S3 adapter identity."""
        return _IDENTITY

    @property
    def _namespace_identity(self) -> ArtifactStoreNamespaceIdentity:
        """Return the canonical non-secret identity of this S3 namespace."""
        profile = "minio-v1" if self._provider_profile == "minio" else "aws-s3-v1"
        items = {
            "addressing_style": self._addressing_style,
            "bucket": self._bucket,
            "private_prefix": self._private_prefix,
            "region": self._region,
        }
        if self._provider_profile == "minio":
            items["endpoint_identity"] = canonical_json_hash(
                {"endpoint_url": self._endpoint_url}
            )
        return ArtifactStoreNamespaceIdentity(
            provider_profile=profile,
            descriptor_items=tuple(sorted(items.items())),
        )

    def _initialize_after_namespace_claim(
        self,
        claim: ArtifactStoreNamespaceClaim,
    ) -> S3CompatibleArtifactStore:
        """Enable provider operations only for the exact PostgreSQL claim."""
        if (
            type(claim) is not ArtifactStoreNamespaceClaim
            or claim.adapter_identity != self.identity
            or claim.namespace_identity != self._namespace_identity
            or claim.namespace_fingerprint != self._expected_namespace_fingerprint()
        ):
            self.close()
            raise ArtifactConfigurationError("artifact namespace claim does not match provider")
        if self._initialized:
            self.close()
            raise ArtifactConfigurationError("S3-compatible artifact storage is already initialized")
        self._initialized = True
        return self

    def _expected_namespace_fingerprint(self) -> str:
        """Return the shared fingerprint for this configured S3 namespace."""
        _, fingerprint = artifact_store_namespace_material(
            backend="s3_compatible",
            adapter_identity=self.identity,
            namespace_identity=self._namespace_identity,
        )
        return fingerprint

    def close(self) -> None:
        """Invalidate this configured adapter; clients are operation-scoped."""
        self._initialized = False

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        """Conditionally publish one sealed source or verify an exact replay."""
        self._require_initialized()
        if type(source) is not CommittedArtifactSource:
            raise ArtifactInputMismatchError("artifact source is not sealed")
        commitment = source.commitment
        if commitment.byte_count > HARD_MAXIMUM_ARTIFACT_BYTES:
            raise ArtifactLimitExceededError("artifact source exceeds provider limit")
        provider_object_ref = artifact_provider_object_ref(commitment)
        body = _CommittedSourceBody(source, self._buffer_bytes)
        try:
            if commitment.byte_count == 0:
                await body.validate_empty()
            request_body: object = b"" if commitment.byte_count == 0 else body
            async with asyncio.timeout(self._operation_total_timeout_seconds):
                async with asyncio.timeout(self._write_timeout_seconds):
                    async with self._client() as client:
                        await client.put_object(
                            Bucket=self._bucket,
                            Key=self._object_key(provider_object_ref),
                            Body=request_body,
                            ContentLength=commitment.byte_count,
                            ContentType=commitment.media_type,
                            IfNoneMatch="*",
                        )
            if not body.complete:
                raise ArtifactInputMismatchError(
                    "S3 provider did not consume the sealed artifact source"
                )
            return ArtifactPutResult(provider_object_ref, replayed=False)
        except ClientError as error:
            status = _provider_http_status(error)
            if status == 403:
                raise ArtifactStoreUnavailableError("S3 artifact operation failed") from None
            if (
                status in {409, 412}
                and _provider_error_code(error) in _PRECONDITION_ERROR_CODES
            ):
                await self._validate_replay_source(body)
                if await self._matches_commitment(provider_object_ref, commitment):
                    return ArtifactPutResult(provider_object_ref, replayed=True)
                raise ArtifactStoreUnavailableError("S3 artifact operation failed") from None
            raise ArtifactStoreUnavailableError("S3 artifact operation failed") from None
        except ArtifactStoreError:
            raise
        except (TimeoutError, BotoCoreError, OSError):
            await self._validate_replay_source(body)
            if await self._matches_commitment(provider_object_ref, commitment):
                return ArtifactPutResult(provider_object_ref, replayed=True)
            raise ArtifactStoreUnavailableError("S3 artifact operation failed") from None

    async def observe_put_result(
        self,
        commitment: ArtifactCommitment,
    ) -> ArtifactPutObservation:
        """Read and validate the deterministic committed object when present."""
        self._require_initialized()
        if type(commitment) is not ArtifactCommitment:
            raise ArtifactOperationConflictError("artifact commitment is invalid")
        provider_object_ref = artifact_provider_object_ref(commitment)
        observed = await self.head(provider_object_ref)
        if not observed.exists:
            return ArtifactPutObservation(provider_object_ref, committed=False)
        await self._verify_exact(provider_object_ref, commitment)
        return ArtifactPutObservation(provider_object_ref, committed=True)

    def open(
        self,
        provider_object_ref: str,
        byte_range: ArtifactByteRange | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream a full object or one bounded byte range."""
        self._require_initialized()
        parse_artifact_provider_object_ref(provider_object_ref)
        if byte_range is not None and type(byte_range) is not ArtifactByteRange:
            raise ArtifactOperationConflictError("artifact byte range is invalid")
        selected_range = byte_range or ArtifactByteRange()

        async def iterate() -> AsyncIterator[bytes]:
            """Hold the S3 response open while yielding exact bounded chunks."""
            head = await self.head(provider_object_ref)
            if not head.exists or head.byte_count is None:
                raise ArtifactObjectMissingError("artifact object is missing")
            if selected_range.offset > head.byte_count:
                raise ArtifactRangeInvalidError("artifact range starts past object end")
            expected = head.byte_count - selected_range.offset
            if selected_range.length is not None:
                expected = min(expected, selected_range.length)
            if expected == 0:
                return

            end = selected_range.offset + expected - 1
            request: dict[str, object] = {
                "Bucket": self._bucket,
                "Key": self._object_key(provider_object_ref),
            }
            if selected_range.offset or expected != head.byte_count:
                request["Range"] = f"bytes={selected_range.offset}-{end}"
            try:
                async with asyncio.timeout(self._operation_total_timeout_seconds):
                    async with self._client() as client:
                        response = await client.get_object(**request)
                        body = response["Body"]
                        observed = 0
                        async with body:
                            while True:
                                chunk = await body.read(
                                    min(self._buffer_bytes, expected - observed + 1)
                                )
                                if not chunk:
                                    break
                                if not isinstance(chunk, bytes):
                                    raise ArtifactIntegrityError(
                                        "S3 artifact read returned invalid bytes"
                                    )
                                observed += len(chunk)
                                if observed > expected:
                                    raise ArtifactIntegrityError(
                                        "S3 artifact read exceeded its bound"
                                    )
                                yield chunk
                        if observed != expected:
                            raise ArtifactIntegrityError("S3 artifact object was truncated")
            except ClientError as error:
                status = _provider_http_status(error)
                if status == 404 and _provider_error_code(error) in _MISSING_ERROR_CODES:
                    raise ArtifactObjectMissingError("artifact object is missing") from None
                raise ArtifactStoreUnavailableError("S3 artifact read failed") from None
            except ArtifactStoreError:
                raise
            except (TimeoutError, BotoCoreError, OSError):
                raise ArtifactStoreUnavailableError("S3 artifact read failed") from None

        return iterate()

    async def head(self, provider_object_ref: str) -> ArtifactObjectHead:
        """Return exact size or authoritative absence without provider details."""
        self._require_initialized()
        parse_artifact_provider_object_ref(provider_object_ref)
        try:
            async with asyncio.timeout(self._operation_total_timeout_seconds):
                async with self._client() as client:
                    response = await client.head_object(
                        Bucket=self._bucket,
                        Key=self._object_key(provider_object_ref),
                    )
            byte_count = response.get("ContentLength")
            if type(byte_count) is not int or byte_count < 0:
                raise ArtifactIntegrityError("S3 artifact head lacks exact size")
            return ArtifactObjectHead(
                provider_object_ref,
                exists=True,
                byte_count=byte_count,
            )
        except ClientError as error:
            status = _provider_http_status(error)
            if status == 404 and _provider_error_code(error) in _MISSING_ERROR_CODES:
                return ArtifactObjectHead(provider_object_ref, exists=False)
            raise ArtifactStoreUnavailableError("S3 artifact head failed") from None
        except ArtifactStoreError:
            raise
        except (TimeoutError, BotoCoreError, OSError):
            raise ArtifactStoreUnavailableError("S3 artifact head failed") from None

    async def _verify_exact(
        self,
        provider_object_ref: str,
        commitment: ArtifactCommitment,
    ) -> None:
        """Independently hash and count one complete provider object."""
        digest = hashlib.sha256()
        byte_count = 0
        async for chunk in self.open(provider_object_ref):
            digest.update(chunk)
            byte_count += len(chunk)
        if (
            byte_count != commitment.byte_count
            or f"sha256:{digest.hexdigest()}" != commitment.sha256
        ):
            raise ArtifactIntegrityError("S3 artifact object violates commitment")

    async def _matches_commitment(
        self,
        provider_object_ref: str,
        commitment: ArtifactCommitment,
    ) -> bool:
        """Resolve an uncertain write only from an independently verified object."""
        try:
            observed = await self.head(provider_object_ref)
            if not observed.exists:
                return False
            await self._verify_exact(provider_object_ref, commitment)
        except ArtifactObjectMissingError:
            return False
        return True

    async def _validate_replay_source(self, body: _CommittedSourceBody) -> None:
        """Finish validating the sealed source before accepting any replay."""
        try:
            async with asyncio.timeout(self._operation_total_timeout_seconds):
                await body.validate_complete()
        except TimeoutError:
            raise ArtifactStoreUnavailableError("S3 artifact operation failed") from None

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        """Create one bounded S3 client from the already-isolated session."""
        async with asyncio.timeout(self._pool_timeout_seconds):
            context = self._session.create_client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
                config=self._client_config,
            )
            client = await context.__aenter__()
        try:
            yield client
        finally:
            await context.__aexit__(None, None, None)

    def _require_initialized(self) -> None:
        """Reject all operations before exact namespace admission."""
        if not self._initialized:
            raise ArtifactConfigurationError("artifact store namespace is not initialized")

    def _object_key(self, provider_object_ref: str) -> str:
        """Apply only the configured private prefix to a digest-derived reference."""
        parse_artifact_provider_object_ref(provider_object_ref)
        return f"{self._private_prefix}/{provider_object_ref}"


class _CommittedSourceBody:
    """Single-use async request body that revalidates the sealed commitment."""

    def __init__(self, source: CommittedArtifactSource, buffer_bytes: int) -> None:
        """Bind one sealed source to one bounded second-pass request body."""
        self._source = source
        self._commitment = source.commitment
        self._buffer_bytes = buffer_bytes
        self._consumed = False
        self._complete = False
        self._iterator: AsyncIterator[bytes] | None = None
        self._source_cursor: memoryview | None = None
        self._pending = bytearray()
        self._digest = hashlib.sha256()
        self._byte_count = 0

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield bounded bytes while checking the exact digest and count."""
        if self._consumed:
            raise ArtifactInputMismatchError("artifact source stream was already consumed")
        self._consumed = True

        async def iterate() -> AsyncIterator[bytes]:
            """Yield the source until its commitment and EOF are proven."""
            while chunk := await self.read(self._buffer_bytes):
                yield chunk

        return iterate()

    @property
    def complete(self) -> bool:
        """Return whether the sealed second-pass stream was fully validated."""
        return self._complete

    async def read(self, amount: int | None = -1) -> bytes:
        """Return one bounded async file-like chunk for the pinned SDK."""
        if not self._consumed:
            self._consumed = True
        if self._complete:
            return b""
        requested = self._buffer_bytes if amount is None or amount < 0 else amount
        if requested == 0:
            return b""
        requested = min(requested, self._buffer_bytes)
        if self._iterator is None:
            self._iterator = self._source.stream()
        while len(self._pending) < requested:
            if self._source_cursor is None:
                try:
                    source_chunk = await anext(self._iterator)
                except StopAsyncIteration:
                    self._finish()
                    break
                if not isinstance(source_chunk, bytes):
                    raise ArtifactInputMismatchError("artifact source must yield bytes")
                self._source_cursor = memoryview(source_chunk)
                if not self._source_cursor:
                    self._source_cursor = None
                    continue
            needed = requested - len(self._pending)
            copied = min(needed, len(self._source_cursor))
            self._pending.extend(self._source_cursor[:copied])
            self._source_cursor = self._source_cursor[copied:] or None
        chunk = bytes(self._pending[:requested])
        del self._pending[:requested]
        self._byte_count += len(chunk)
        if self._byte_count > self._commitment.byte_count:
            raise ArtifactInputMismatchError("artifact source exceeds committed byte count")
        self._digest.update(chunk)
        if self._byte_count == self._commitment.byte_count and not self._pending:
            await self._require_source_exhausted()
        if not chunk and not self._complete:
            self._finish()
        return chunk

    async def validate_empty(self) -> None:
        """Validate a zero-byte source that the SDK need not consume."""
        if self._commitment.byte_count != 0:
            raise ArtifactInputMismatchError("artifact source is not empty")
        if await self.read(1) != b"" or not self._complete:
            raise ArtifactInputMismatchError("artifact source violates commitment")

    async def validate_complete(self) -> None:
        """Consume and validate every remaining sealed source byte."""
        while await self.read(self._buffer_bytes):
            pass
        if not self._complete:
            raise ArtifactInputMismatchError("artifact source violates commitment")

    async def _require_source_exhausted(self) -> None:
        """Prove EOF before returning the final committed byte to the SDK."""
        if self._source_cursor:
            raise ArtifactInputMismatchError(
                "artifact source exceeds committed byte count"
            )
        if self._iterator is None:
            self._iterator = self._source.stream()
        while True:
            try:
                extra = await anext(self._iterator)
            except StopAsyncIteration:
                self._finish()
                return
            if not isinstance(extra, bytes):
                raise ArtifactInputMismatchError("artifact source must yield bytes")
            if extra:
                raise ArtifactInputMismatchError(
                    "artifact source exceeds committed byte count"
                )

    def _finish(self) -> None:
        """Validate commitment only after every pending byte is consumed."""
        if self._pending:
            return
        if (
            self._byte_count != self._commitment.byte_count
            or f"sha256:{self._digest.hexdigest()}" != self._commitment.sha256
        ):
            raise ArtifactInputMismatchError("artifact source violates commitment")
        self._complete = True

def create_minio_artifact_store_bootstrap(
    settings: Settings,
) -> S3CompatibleArtifactStoreBootstrap:
    """Construct the only S3 runtime profile enabled by this chunk."""
    bootstrap, error_message = _try_create_minio_artifact_store_bootstrap(settings)
    if error_message is not None:
        del settings
        raise ArtifactConfigurationError(error_message) from None
    if bootstrap is None:
        del settings
        raise ArtifactConfigurationError("MinIO artifact configuration is invalid") from None
    return bootstrap


def _try_create_minio_artifact_store_bootstrap(
    settings: Settings,
) -> tuple[S3CompatibleArtifactStoreBootstrap | None, str | None]:
    """Build MinIO state without propagating a secret-bearing failure frame."""
    if settings.artifact_s3_provider_profile != "minio":
        return None, "MinIO artifact profile is not configured"
    access_key = settings.artifact_s3_access_key_id
    secret_key = settings.artifact_s3_secret_access_key
    if access_key is None or secret_key is None:
        return None, "MinIO artifact credentials are unavailable"
    try:
        session = AioSession()
        session.set_credentials(
            access_key.get_secret_value(),
            secret_key.get_secret_value(),
            settings.artifact_s3_session_token.get_secret_value()
            if settings.artifact_s3_session_token is not None
            else None,
        )
        bootstrap = S3CompatibleArtifactStoreBootstrap(
            S3CompatibleArtifactStore(
                provider_profile="minio",
                region=_required(settings.artifact_s3_region),
                endpoint_url=_required(settings.artifact_s3_endpoint_url),
                bucket=_required(settings.artifact_s3_bucket),
                private_prefix=settings.artifact_s3_private_prefix,
                addressing_style=settings.artifact_s3_addressing_style,
                session=session,
                buffer_bytes=settings.artifact_stream_buffer_bytes,
                connect_timeout_seconds=settings.artifact_s3_connect_timeout_seconds,
                read_timeout_seconds=settings.artifact_s3_read_timeout_seconds,
                write_timeout_seconds=settings.artifact_s3_write_timeout_seconds,
                pool_timeout_seconds=settings.artifact_s3_pool_timeout_seconds,
                operation_total_timeout_seconds=(
                    settings.artifact_s3_operation_total_timeout_seconds
                ),
                max_pool_connections=settings.artifact_s3_max_pool_connections,
            )
        )
    except ArtifactConfigurationError as error:
        return None, str(error)
    except Exception:
        return None, "MinIO artifact configuration is invalid"
    return bootstrap, None


def validate_aws_workload_identity_environment(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Reject every ambient or unselected AWS credential source without loading it."""
    if settings.artifact_s3_provider_profile != "aws_s3":
        raise ArtifactConfigurationError("native AWS S3 profile is not configured")
    selected = settings.artifact_s3_aws_workload_identity_method
    if selected is None:
        raise ArtifactConfigurationError("AWS workload identity method is unavailable")
    environment = os.environ if environ is None else environ
    if _FORBIDDEN_AWS_CREDENTIAL_ENVIRONMENT.intersection(environment):
        raise ArtifactConfigurationError("ambient AWS credential source is forbidden")
    if _FORBIDDEN_AWS_NETWORK_ENVIRONMENT.intersection(environment):
        raise ArtifactConfigurationError("ambient AWS network configuration is forbidden")
    if any(name.startswith("AWS_ENDPOINT_URL_") for name in environment):
        raise ArtifactConfigurationError("ambient AWS network configuration is forbidden")
    _reject_default_credential_files(environment)

    unselected = set().union(
        *(
            values
            for method, values in _AWS_SOURCE_ENVIRONMENT_BY_METHOD.items()
            if method != selected
        )
    )
    if unselected.intersection(environment):
        raise ArtifactConfigurationError("unselected AWS workload source is configured")
    if selected == "container-role":
        if "AWS_CONTAINER_CREDENTIALS_FULL_URI" in environment:
            raise ArtifactConfigurationError(
                "AWS container full credential URI is forbidden"
            )
        if {
            "AWS_CONTAINER_AUTHORIZATION_TOKEN",
            "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
        }.intersection(environment):
            raise ArtifactConfigurationError("AWS container identity token is forbidden")
    elif selected == "iam-role":
        if "AWS_EC2_METADATA_SERVICE_ENDPOINT" in environment:
            raise ArtifactConfigurationError("custom AWS metadata endpoint is forbidden")
        if "AWS_EC2_METADATA_SERVICE_ENDPOINT_MODE" in environment:
            raise ArtifactConfigurationError(
                "custom AWS metadata endpoint mode is forbidden"
            )
        if environment.get("AWS_EC2_METADATA_DISABLED", "false").lower() == "true":
            raise ArtifactConfigurationError("AWS instance identity metadata is disabled")

    allowed_environment = _ALLOWED_AWS_ENVIRONMENT_BY_METHOD[selected]
    unsupported_sdk_environment = {
        name
        for name in environment
        if (name.startswith("AWS_") or name.startswith("BOTOCORE_"))
        and name not in allowed_environment
    }
    if unsupported_sdk_environment:
        raise ArtifactConfigurationError(
            "unsupported AWS SDK environment configuration is forbidden"
        )

    if selected == "assume-role-with-web-identity":
        if not {"AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE"}.issubset(environment):
            raise ArtifactConfigurationError("AWS web identity configuration is incomplete")
        token_path = Path(environment["AWS_WEB_IDENTITY_TOKEN_FILE"])
        if not token_path.is_absolute() or not token_path.is_file():
            raise ArtifactConfigurationError("AWS web identity token path is invalid")
    elif selected == "container-role":
        relative_uri = environment.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
        if (
            not isinstance(relative_uri, str)
            or _CONTAINER_RELATIVE_URI.fullmatch(relative_uri) is None
        ):
            raise ArtifactConfigurationError("AWS container identity location is invalid")
    else:
        if environment.get("AWS_EC2_METADATA_V1_DISABLED", "false").lower() != "true":
            raise ArtifactConfigurationError("AWS instance identity requires IMDSv2")


def create_isolated_aws_workload_identity_session(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
) -> AioSession:
    """Build an inactive SDK session whose resolver contains one selected provider."""
    validate_aws_workload_identity_environment(settings, environ=environ)
    environment = os.environ if environ is None else environ
    selected = settings.artifact_s3_aws_workload_identity_method
    session = AioSession()
    if selected == "assume-role-with-web-identity":
        profile = {
            "role_arn": environment["AWS_ROLE_ARN"],
            "web_identity_token_file": environment["AWS_WEB_IDENTITY_TOKEN_FILE"],
        }
        role_session_name = environment.get("AWS_ROLE_SESSION_NAME")
        if role_session_name is not None:
            profile["role_session_name"] = role_session_name

        def create_isolated_sts_client(service_name: str, **_kwargs: object) -> object:
            """Create only the pinned no-proxy STS client for web identity."""
            if service_name != "sts":
                raise ArtifactConfigurationError("AWS web identity service is invalid")
            return session.create_client(
                "sts",
                region_name=_required(settings.artifact_s3_region),
                verify=True,
                config=AioConfig(
                    signature_version=UNSIGNED,
                    connect_timeout=settings.artifact_s3_connect_timeout_seconds,
                    read_timeout=settings.artifact_s3_read_timeout_seconds,
                    retries={"max_attempts": 1, "mode": "standard"},
                    proxies={},
                ),
            )

        provider = AioAssumeRoleWithWebIdentityProvider(
            load_config=lambda: {"profiles": {"workstream-isolated": profile}},
            client_creator=create_isolated_sts_client,
            profile_name="workstream-isolated",
            cache={},
            disable_env_vars=True,
        )
    elif selected == "container-role":
        provider = _SanitizedContainerProvider(
            environ={
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": environment[
                    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"
                ]
            }
        )
        provider._fetcher = _SanitizedContainerMetadataFetcher(
            session=_RefCountedSession(
                timeout=settings.artifact_s3_connect_timeout_seconds,
                proxies={},
            )
        )
    elif selected == "iam-role":
        provider = _SanitizedInstanceMetadataProvider(
            iam_role_fetcher=_SanitizedInstanceMetadataFetcher(
                timeout=settings.artifact_s3_connect_timeout_seconds,
                num_attempts=1,
                env=dict(environment),
                user_agent=session.user_agent(),
                config={
                    "ec2_metadata_v1_disabled": True,
                },
                session=_RefCountedSession(
                    timeout=settings.artifact_s3_connect_timeout_seconds,
                    proxies={},
                ),
            )
        )
    else:
        raise ArtifactConfigurationError("AWS workload identity method is unsupported")
    session.register_component("credential_provider", AioCredentialResolver([provider]))
    return session


async def resolve_isolated_aws_workload_credentials(
    session: AioSession,
    *,
    expected_method: str,
) -> object:
    """Resolve credentials and require the exact selected SDK method."""
    resolution_failed = False
    try:
        credentials = await session.get_credentials()
    except Exception:
        resolution_failed = True
        credentials = None
    if resolution_failed:
        raise ArtifactConfigurationError(
            "AWS workload identity credentials could not be resolved"
        ) from None
    if credentials is None or getattr(credentials, "method", None) != expected_method:
        raise ArtifactConfigurationError("AWS workload identity method did not match")
    materialization_failed = False
    try:
        await credentials.get_frozen_credentials()
    except Exception:
        materialization_failed = True
    if materialization_failed:
        del credentials
        raise ArtifactConfigurationError(
            "AWS workload identity credentials could not be resolved"
        ) from None
    return credentials


def _reject_default_credential_files(environ: Mapping[str, str]) -> None:
    """Fail on default shared/config/Boto files without reading their contents."""
    home = Path(environ.get("HOME", str(Path.home())))
    for path in (
        home / ".aws" / "credentials",
        home / ".aws" / "config",
        home / ".boto",
        Path("/etc/boto.cfg"),
    ):
        if path.exists():
            raise ArtifactConfigurationError("ambient AWS credential file is forbidden")


def _provider_error_code(error: ClientError) -> str:
    """Return one bounded provider status/code without retaining response details."""
    response = error.response if isinstance(error.response, dict) else {}
    provider_error = response.get("Error") if isinstance(response, dict) else None
    code = provider_error.get("Code") if isinstance(provider_error, dict) else None
    if isinstance(code, str) and code:
        return code
    metadata = response.get("ResponseMetadata") if isinstance(response, dict) else None
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return str(status) if type(status) is int else "unknown"


def _provider_http_status(error: ClientError) -> int | None:
    """Return the provider HTTP status independently from its error code."""
    response = error.response if isinstance(error.response, dict) else {}
    metadata = response.get("ResponseMetadata") if isinstance(response, dict) else None
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return status if type(status) is int else None


def _required(value: str | None) -> str:
    """Return one settings value already guaranteed by validation."""
    if not isinstance(value, str) or not value:
        raise ArtifactConfigurationError("S3-compatible artifact setting is unavailable")
    return value
