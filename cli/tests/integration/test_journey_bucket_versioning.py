"""Source uploads require versioning on the launcher-owned isolated bucket."""

from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "journey/runtime.py"
SPEC = importlib.util.spec_from_file_location("journey_runtime_bucket", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SUFFIX = "a1b2c3d4e5f6"
BUCKET = f"workstream-ci-cli-full-journey-{SUFFIX}"
ENVIRONMENT = {
    "WORKSTREAM_TEST_MINIO_BUCKET": BUCKET,
    "WORKSTREAM_TEST_MINIO_PREFIX": f"ci/cli_full_journey/{SUFFIX}",
    "WORKSTREAM_TEST_MINIO_ENDPOINT": "http://127.0.0.1:59044",
}


class VersioningClient:
    def __init__(self, status="Enabled"):
        self.status = status
        self.calls = []

    async def put_bucket_versioning(self, **arguments):
        self.calls.append(("put", arguments))

    async def get_bucket_versioning(self, **arguments):
        self.calls.append(("get", arguments))
        return {"Status": self.status}


def factory_for(client):
    @asynccontextmanager
    async def factory(endpoint):
        assert endpoint == ENVIRONMENT["WORKSTREAM_TEST_MINIO_ENDPOINT"]
        yield client

    return factory


@pytest.mark.parametrize("lane", ["cli_full_journey", "guide_journey"])
def test_journey_enables_and_reads_back_exact_owned_source_bucket(lane):
    client = VersioningClient()
    bucket = f"workstream-ci-{lane.replace('_', '-')}-{SUFFIX}"
    MODULE.prepare_versioned_source_bucket(
        ENVIRONMENT | {"WORKSTREAM_TEST_MINIO_BUCKET": bucket,
                       "WORKSTREAM_TEST_MINIO_PREFIX": f"ci/{lane}/{SUFFIX}"},
        lane=lane, client_factory=factory_for(client),
    )
    assert client.calls == [
        ("put", {"Bucket": bucket, "VersioningConfiguration": {"Status": "Enabled"}}),
        ("get", {"Bucket": bucket}),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"WORKSTREAM_TEST_MINIO_BUCKET": "workstream-artifacts"},
        {"WORKSTREAM_TEST_MINIO_BUCKET": f"workstream-ci-guide-journey-{SUFFIX}",
         "WORKSTREAM_TEST_MINIO_PREFIX": f"ci/guide_journey/{SUFFIX}"},
        {"WORKSTREAM_TEST_MINIO_PREFIX": "ci/cli_full_journey/other"},
    ],
)
def test_journey_refuses_foreign_bucket_before_provider_call(change):
    client = VersioningClient()
    with pytest.raises(RuntimeError, match="runner-owned"):
        MODULE.prepare_versioned_source_bucket(
            ENVIRONMENT | change, client_factory=factory_for(client)
        )
    assert client.calls == []


def test_journey_refuses_missing_versioning_after_readback():
    client = VersioningClient(status=None)
    with pytest.raises(RuntimeError, match="versioning"):
        MODULE.prepare_versioned_source_bucket(
            ENVIRONMENT, client_factory=factory_for(client)
        )
    assert [name for name, _ in client.calls] == ["put", "get"]
