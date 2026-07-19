"""Shared deep assertions for security-sensitive test object graphs."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import SecretStr, ValidationError


def assert_secret_not_retained(
    value: object,
    secret: str,
    seen: set[int] | None = None,
    *,
    traceback_module_prefixes: tuple[str, ...] = (),
) -> None:
    """Assert a secret is unreachable through selected error state."""
    if seen is None:
        seen = set()
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, str):
        assert secret not in value
    elif isinstance(value, (bytes, bytearray, memoryview)):
        assert secret.encode("utf-8") not in bytes(value)
    elif isinstance(value, SecretStr):
        assert secret not in value.get_secret_value()
    elif isinstance(value, BaseException):
        if isinstance(value, ValidationError):
            assert_secret_not_retained(
                value.errors(),
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
        for related in (value.args, vars(value), value.__cause__, value.__context__):
            assert_secret_not_retained(
                related,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
        traceback = value.__traceback__
        while traceback is not None:
            module_name = str(traceback.tb_frame.f_globals.get("__name__", ""))
            if module_name.startswith(traceback_module_prefixes):
                assert_secret_not_retained(
                    dict(traceback.tb_frame.f_locals),
                    secret,
                    seen,
                    traceback_module_prefixes=traceback_module_prefixes,
                )
            traceback = traceback.tb_next
    elif isinstance(value, Mapping):
        for key, item in value.items():
            assert_secret_not_retained(
                key,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
            assert_secret_not_retained(
                item,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
    elif isinstance(getattr(value, "__dict__", None), Mapping):
        assert_secret_not_retained(
            vars(value),
            secret,
            seen,
            traceback_module_prefixes=traceback_module_prefixes,
        )
        private = getattr(value, "__pydantic_private__", None)
        if isinstance(private, Mapping):
            assert_secret_not_retained(
                private,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
    elif isinstance(getattr(value, "__pydantic_private__", None), Mapping):
        assert_secret_not_retained(
            getattr(value, "__pydantic_private__"),
            secret,
            seen,
            traceback_module_prefixes=traceback_module_prefixes,
        )
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            assert_secret_not_retained(
                item,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
