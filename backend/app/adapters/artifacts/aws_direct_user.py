"""Isolated private-file IAM user credentials for native S3."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import stat

from aiobotocore.config import AioConfig
from aiobotocore.credentials import AioCredentials
from aiobotocore.session import AioSession

from app.core.config import ARTIFACT_DIRECT_USER_IDENTITY_TIMEOUT_SECONDS, Settings
from app.interfaces.artifacts import ArtifactConfigurationError


DIRECT_USER_METHOD = "workstream-aws-access-key"
_MAXIMUM_KEY_FILE_BYTES = 4096
_ACCESS_KEY_ID = re.compile(r"[A-Z0-9]{16,128}\Z")
_SECRET_ACCESS_KEY = re.compile(r"[A-Za-z0-9/+=]{1,128}\Z")


def _read_key_file(path: Path) -> tuple[str, str] | None:
    """Read one closed, private keypair without retaining file or parse errors."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o400
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
            ):
                return None
            raw = os.pread(descriptor, _MAXIMUM_KEY_FILE_BYTES + 1, 0)
        finally:
            os.close(descriptor)
        if len(raw) > _MAXIMUM_KEY_FILE_BYTES:
            return None
        pairs = json.loads(raw, object_pairs_hook=list)
        if (
            type(pairs) is not list
            or len(pairs) != 2
            or any(type(pair) is not tuple for pair in pairs)
        ):
            return None
        keys = dict(pairs)
        if set(keys) != {"access_key_id", "secret_access_key"}:
            return None
        access_key = keys["access_key_id"]
        secret_key = keys["secret_access_key"]
        if (
            type(access_key) is not str or _ACCESS_KEY_ID.fullmatch(access_key) is None
            or type(secret_key) is not str or _SECRET_ACCESS_KEY.fullmatch(secret_key) is None
        ):
            return None
        return access_key, secret_key
    except (OSError, ValueError, RecursionError):
        return None


class DirectIamUserCredentialProvider:
    """Prove the exact source user before handing the SDK its keypair."""

    METHOD = DIRECT_USER_METHOD

    def __init__(self, settings: Settings, session: AioSession) -> None:
        path = settings.artifact_s3_direct_user_credential_file
        expected_arn = settings.artifact_s3_runtime_user_arn
        region = settings.artifact_s3_region
        if path is None or not path.is_absolute() or expected_arn is None or region is None:
            raise ArtifactConfigurationError("direct IAM user credentials are not configured")
        self._path = path
        self._expected_arn = expected_arn
        self._region = region
        self._session = session
        self._client_config = AioConfig(
            connect_timeout=min(settings.artifact_s3_connect_timeout_seconds, 5.0),
            read_timeout=min(settings.artifact_s3_read_timeout_seconds, 5.0),
            retries={"total_max_attempts": 1, "mode": "standard"},
            proxies={},
        )

    async def load(self) -> AioCredentials:
        """Reject unavailable, disabled or substituted keys before any S3 client exists."""
        credentials = await self._verified_credentials()
        if credentials is None:
            raise ArtifactConfigurationError("direct IAM user credentials could not be verified")
        return credentials

    async def _verified_credentials(self) -> AioCredentials | None:
        keys = _read_key_file(self._path)
        if keys is None:
            return None
        access_key, secret_key = keys
        matched = False
        try:
            async with asyncio.timeout(ARTIFACT_DIRECT_USER_IDENTITY_TIMEOUT_SECONDS):
                async with self._session.create_client(
                    "sts",
                    region_name=self._region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    verify=True,
                    config=self._client_config,
                ) as client:
                    response = await client.get_caller_identity()
            matched = (
                response.get("Arn") == self._expected_arn
                and response.get("Account") == self._expected_arn.split(":", 5)[4]
            )
        except Exception:
            pass
        if matched:
            return AioCredentials(access_key, secret_key, method=self.METHOD)
        return None
