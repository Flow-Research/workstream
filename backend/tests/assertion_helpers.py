"""Shared deep assertions for security-sensitive test object graphs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass

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
        assert not str.__contains__(value, secret)
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
    elif issubclass(type(value), dict):
        # Snapshot before recursive inspection: traversing nested framework state
        # can lazily import modules and mutate a module-globals dictionary.
        for key, item in tuple(dict.items(value)):
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
    elif isinstance(value, Mapping):
        try:
            items = tuple(value.items())
        except Exception:
            state = getattr(value, "__dict__", None)
            assert isinstance(state, dict), "mapping state could not be inspected"
            assert_secret_not_retained(
                state,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
            return
        for key, item in items:
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
    elif isinstance(value, list):
        for item in list.__iter__(value):
            assert_secret_not_retained(
                item,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
    elif isinstance(value, tuple):
        for item in tuple.__iter__(value):
            assert_secret_not_retained(
                item,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
    elif isinstance(value, set):
        for item in set.__iter__(value):
            assert_secret_not_retained(
                item,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
    elif isinstance(value, frozenset):
        for item in frozenset.__iter__(value):
            assert_secret_not_retained(
                item,
                secret,
                seen,
                traceback_module_prefixes=traceback_module_prefixes,
            )
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            assert_secret_not_retained(
                object.__getattribute__(value, field.name),
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
