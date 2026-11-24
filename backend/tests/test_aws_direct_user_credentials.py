"""File and exact IAM-user custody for direct native AWS credentials."""

from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError

from app.adapters.artifacts import s3_compatible
from app.adapters.artifacts.aws_direct_user import DIRECT_USER_METHOD
from app.core.config import Settings
from app.interfaces.artifacts import ArtifactConfigurationError
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.assertion_helpers import assert_secret_not_retained


USER_ARN = "arn:aws:iam::123456789012:user/workstream-artifacts"
ACCESS_KEY_ID = "AKIA0000000000000001"
SECRET_KEY = "secretkeycanary0000000000000000000000000"


def direct_user_settings(tmp_path: Path, **overrides: object) -> Settings:
    path = tmp_path / "aws-access-key.json"
    if not path.exists():
        path.write_text(json.dumps({"access_key_id": ACCESS_KEY_ID, "secret_access_key": SECRET_KEY}))
        path.chmod(0o400)
    values = {
        **artifact_admission_limit_settings(),
        "environment": "production",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "aws_s3",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_bucket": "workstream-artifacts-test",
        "artifact_s3_credential_mode": "aws_access_key",
        "artifact_s3_runtime_user_arn": USER_ARN,
        "artifact_s3_direct_user_credential_file": path,
    }
    return Settings(**(values | overrides))


@pytest.mark.parametrize("overrides", [
    {"artifact_s3_runtime_user_arn": "arn:aws:iam::123456789012:role/production"},
    {"artifact_s3_runtime_user_arn": "arn:aws:iam::123456789012:root"},
    {"artifact_s3_direct_user_credential_file": "relative/keys.json"},
    {"artifact_s3_aws_workload_identity_method": "iam-role"},
])
def test_direct_user_configuration_rejects_inexact_sources(tmp_path, overrides):
    with pytest.raises(ValueError):
        direct_user_settings(tmp_path, **overrides)


@pytest.mark.parametrize("ambient", [
    "AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_EC2_METADATA_V1_DISABLED", "AWS_ENDPOINT_URL_STS",
])
def test_direct_user_rejects_ambient_credentials_before_sdk_creation(tmp_path, monkeypatch, ambient):
    settings = direct_user_settings(tmp_path)
    monkeypatch.setattr(s3_compatible, "AioSession", lambda: pytest.fail("AWS SDK was constructed"))
    with pytest.raises(ArtifactConfigurationError):
        s3_compatible.create_isolated_aws_credential_session(
            settings, environ={"HOME": str(tmp_path), ambient: "unexpected"},
        )


@pytest.mark.parametrize("failure", ["missing", "symlink", "mode", "malformed", "session-token"])
@pytest.mark.asyncio
async def test_direct_user_rejects_unsafe_key_file_before_network(tmp_path, failure):
    settings = direct_user_settings(tmp_path)
    file = settings.artifact_s3_direct_user_credential_file
    assert file is not None
    if failure == "missing":
        file.unlink()
    elif failure == "symlink":
        target = tmp_path / "other.json"
        file.rename(target)
        file.symlink_to(target)
    elif failure == "mode":
        file.chmod(0o644)
    else:
        file.chmod(0o600)
        file.write_text(
            f'{{"secret_access_key":"{SECRET_KEY}"' if failure == "malformed" else json.dumps({
                "access_key_id": ACCESS_KEY_ID, "secret_access_key": SECRET_KEY, "session_token": "token",
            })
        )
        file.chmod(0o400)
    session = s3_compatible.create_isolated_aws_credential_session(settings, environ={"HOME": str(tmp_path)})
    session.create_client = lambda *_args, **_kwargs: pytest.fail("unsafe key reached AWS")
    with pytest.raises(ArtifactConfigurationError) as error:
        await session.get_credentials()
    assert_secret_not_retained(error.value, SECRET_KEY, traceback_module_prefixes=("app.adapters",))


@pytest.mark.parametrize("identity", ["exact", "foreign", "disabled"])
@pytest.mark.asyncio
async def test_direct_user_checks_identity_with_explicit_keys(tmp_path, identity):
    settings = direct_user_settings(tmp_path)
    session = s3_compatible.create_isolated_aws_credential_session(settings, environ={"HOME": str(tmp_path)})
    providers = session.get_component("credential_provider").providers
    assert len(providers) == 1 and providers[0].METHOD == DIRECT_USER_METHOD
    sts = AsyncMock(return_value={"Arn": USER_ARN if identity == "exact" else USER_ARN + "-other", "Account": "123456789012"})
    if identity == "disabled":
        sts.side_effect = ClientError(
            {"Error": {"Code": "InvalidClientTokenId", "Message": SECRET_KEY}}, "GetCallerIdentity",
        )

    @asynccontextmanager
    async def client(service_name, **kwargs):
        assert service_name == "sts"
        assert kwargs["verify"] is True and kwargs["config"].proxies == {}
        assert kwargs["aws_access_key_id"] == ACCESS_KEY_ID
        assert kwargs["aws_secret_access_key"] == SECRET_KEY
        assert "aws_session_token" not in kwargs
        yield SimpleNamespace(get_caller_identity=sts)

    session.create_client = client
    if identity == "exact":
        credentials = await session.get_credentials()
        value = await credentials.get_frozen_credentials()
        assert (value.access_key, value.secret_key, value.token) == (ACCESS_KEY_ID, SECRET_KEY, None)
    else:
        with pytest.raises(ArtifactConfigurationError) as error:
            await session.get_credentials()
        assert_secret_not_retained(error.value, SECRET_KEY, traceback_module_prefixes=("app.adapters",))
    sts.assert_awaited_once_with()
