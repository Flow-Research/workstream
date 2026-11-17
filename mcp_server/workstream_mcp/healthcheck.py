"""Private process readiness: API reachability, metadata and closed MCP access."""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main() -> None:
    resource = os.environ["WORKSTREAM_MCP_RESOURCE_URL"]
    issuer = os.environ["WORKSTREAM_MCP_TOKEN_ISSUER"]
    # The hosted profile fixes both loopback listeners; no credentials are used.
    with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=2):  # noqa: S310
        pass
    with urlopen(  # noqa: S310
        "http://127.0.0.1:8080/.well-known/oauth-protected-resource/mcp", timeout=2,
    ) as response:
        metadata = json.loads(response.read(8193))
    if metadata.get("resource") != resource or metadata.get("authorization_servers") != [issuer]:
        raise RuntimeError("MCP metadata is inconsistent")
    try:
        with urlopen(Request("http://127.0.0.1:8080/mcp", data=b"{}"), timeout=2):  # noqa: S310
            raise RuntimeError("MCP accepts unauthenticated requests")
    except HTTPError as error:
        challenge = error.headers.get("WWW-Authenticate", "")
        if error.code != 401 or "resource_metadata=" not in challenge:
            raise RuntimeError("MCP authentication challenge is unavailable") from None


if __name__ == "__main__":
    main()
