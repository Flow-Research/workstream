from __future__ import annotations

import uvicorn

from workstream_mcp.config import Settings
from workstream_mcp.server import create_app


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="info",
        limit_concurrency=settings.max_in_flight + 8,
        timeout_keep_alive=settings.keep_alive_seconds,
        server_header=False,
    )


if __name__ == "__main__":
    main()
