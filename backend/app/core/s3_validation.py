"""Canonical non-secret S3 namespace validation shared by configuration layers."""

from __future__ import annotations

from collections.abc import Mapping
import ipaddress
import re
from urllib.parse import urlsplit


_S3_REGION = re.compile(r"^[a-z]{2,4}(?:-[a-z0-9]+)+-[0-9]+$")
_S3_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_S3_BUCKET_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_S3_RESERVED_PREFIXES = ("xn--", "sthree-", "amzn-s3-demo-")
_S3_RESERVED_SUFFIXES = (
    "-s3alias",
    "--ol-s3",
    ".mrap",
    "--x-s3",
    "--table-s3",
    "-an",
)
_S3_PREFIX_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def is_canonical_s3_region(value: object) -> bool:
    """Return whether one region is bounded and canonical."""
    return (
        isinstance(value, str)
        and len(value) <= 63
        and _S3_REGION.fullmatch(value) is not None
    )


def is_canonical_s3_bucket(value: object) -> bool:
    """Return whether one global general-purpose bucket is DNS-compatible."""
    if not isinstance(value, str) or _S3_BUCKET.fullmatch(value) is None:
        return False
    return (
        ".." not in value
        and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", value) is None
        and all(_S3_BUCKET_LABEL.fullmatch(label) is not None for label in value.split("."))
        and not value.startswith(_S3_RESERVED_PREFIXES)
        and not value.endswith(_S3_RESERVED_SUFFIXES)
    )


def is_canonical_s3_prefix(value: object) -> bool:
    """Return whether one private object prefix has canonical path segments."""
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    return all(
        _S3_PREFIX_SEGMENT.fullmatch(segment) is not None
        for segment in value.split("/")
    )


def canonical_minio_endpoint(value: object) -> str:
    """Return one normalized noncredentialed HTTP(S) MinIO origin."""
    missing = value is None or value == ""
    endpoint = _try_canonical_minio_endpoint(value)
    del value
    if endpoint is None:
        if missing:
            raise ValueError("MinIO artifact storage requires an endpoint") from None
        raise ValueError("MinIO artifact storage endpoint is invalid") from None
    return endpoint


def _try_canonical_minio_endpoint(value: object) -> str | None:
    """Normalize one endpoint without retaining invalid input in an exception."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname.endswith(".")
    ):
        return None
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    if ":" in hostname:
        try:
            hostname = ipaddress.IPv6Address(hostname).compressed
        except ipaddress.AddressValueError:
            return None
        hostname = f"[{hostname}]"
    if port is not None and port != {"http": 80, "https": 443}[scheme]:
        hostname = f"{hostname}:{port}"
    return f"{scheme}://{hostname}"


def validate_s3_namespace_descriptor(
    provider_profile: str,
    descriptor: Mapping[str, str],
) -> None:
    """Reject malformed values in one closed S3 namespace descriptor."""
    if descriptor.get("addressing_style") not in {"path", "virtual"}:
        raise ValueError("artifact S3 addressing style is invalid")
    if not is_canonical_s3_bucket(descriptor.get("bucket")):
        raise ValueError("artifact S3 bucket is invalid")
    if not is_canonical_s3_prefix(descriptor.get("private_prefix")):
        raise ValueError("artifact S3 private prefix is invalid")
    if not is_canonical_s3_region(descriptor.get("region")):
        raise ValueError("artifact S3 region is invalid")
    endpoint_identity = descriptor.get("endpoint_identity")
    if provider_profile == "minio-v1":
        if not isinstance(endpoint_identity, str) or _SHA256.fullmatch(endpoint_identity) is None:
            raise ValueError("artifact MinIO endpoint identity is invalid")
    elif provider_profile == "aws-s3-v1":
        if endpoint_identity is not None:
            raise ValueError("artifact AWS namespace endpoint identity is forbidden")
    else:
        raise ValueError("artifact S3 provider profile is invalid")
