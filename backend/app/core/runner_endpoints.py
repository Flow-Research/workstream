"""Strict operator configuration for the authenticated external runner endpoints."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints, model_validator


_DNS_NAME = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$"
RunnerName = Annotated[str, StringConstraints(min_length=1, max_length=253, pattern=_DNS_NAME)]
RunnerDigest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class ExternalRunnerEndpoint(BaseModel):
    """An address, exact certificate DNS identity and independently reviewed config."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host: RunnerName
    port: int = Field(ge=1, le=65_535)
    server_name: RunnerName
    config_sha256: RunnerDigest


class ExternalRunnerEndpoints(RootModel[Annotated[tuple[ExternalRunnerEndpoint, ...], Field(min_length=1, max_length=8)]]):
    """One bounded endpoint set, with no repeated route or TLS identity."""

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def distinct_endpoints(self) -> Self:
        if (
            len({(endpoint.host, endpoint.port) for endpoint in self.root}) != len(self.root)
            or len({endpoint.server_name for endpoint in self.root}) != len(self.root)
        ):
            raise ValueError("external runner endpoints must have distinct addresses and certificate names")
        return self
