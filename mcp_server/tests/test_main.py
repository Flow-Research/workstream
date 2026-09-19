from __future__ import annotations

from typing import Any

from workstream_mcp import __main__


def test_main_loads_settings_and_starts_hardened_uvicorn(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class Settings:
        host = "127.0.0.1"
        port = 8090
        max_in_flight = 4
        keep_alive_seconds = 3

        @classmethod
        def from_env(cls) -> Settings:
            return cls()

    monkeypatch.setattr(__main__, "Settings", Settings)
    monkeypatch.setattr(__main__, "create_app", lambda settings: ("app", settings))
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: captured.update(app=app, **kwargs))
    __main__.main()
    app, passed_settings = captured.pop("app")
    assert app == "app"
    assert isinstance(passed_settings, Settings)
    assert captured == {
        "host": "127.0.0.1",
        "port": 8090,
        "access_log": False,
        "log_level": "info",
        "limit_concurrency": 12,
        "timeout_keep_alive": 3,
        "server_header": False,
    }
