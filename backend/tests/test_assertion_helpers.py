"""Tests for shared security-sensitive assertion helpers."""

from pydantic import SecretStr
import pytest
from types import SimpleNamespace

from tests.assertion_helpers import assert_secret_not_retained


def test_secret_str_rejects_embedded_forbidden_value() -> None:
    """Reject a forbidden value even when wrapped by other secret text."""
    with pytest.raises(AssertionError):
        assert_secret_not_retained(SecretStr("prefix-forbidden-suffix"), "forbidden")


@pytest.mark.parametrize(
    "value",
    [b"prefix-forbidden-suffix", bytearray(b"forbidden"), memoryview(b"forbidden")],
)
def test_byte_buffers_reject_embedded_forbidden_value(value: object) -> None:
    """Reject a forbidden value retained in any supported byte buffer."""
    with pytest.raises(AssertionError):
        assert_secret_not_retained(value, "forbidden")


def test_public_object_state_rejects_nested_forbidden_value() -> None:
    """Reject a forbidden value reachable through public object state."""
    value = SimpleNamespace(payload={"body": b"prefix-forbidden-suffix"})

    with pytest.raises(AssertionError):
        assert_secret_not_retained(value, "forbidden")
