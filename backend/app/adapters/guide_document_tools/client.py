"""Strict Unix-socket client for the fixed guide-document parser service."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import struct

from pydantic import ValidationError

from workstream_external_services import (
    ExternalServiceAdapterIdentity,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)

from .contracts import (
    GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
    GUIDE_DOCUMENT_PARSER_PROTOCOL,
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentParserRejectedError,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
    MAXIMUM_REQUEST_METADATA_BYTES,
    MAXIMUM_RESPONSE_BYTES,
)


PARSER_SOCKET_UID = 10_002
PARSER_SOCKET_GID = 10_001
PARSER_SOCKET_MODE = 0o660


class UnixSocketGuideDocumentParserAdapter:
    """Transmit verified bytes to the one fixed local parser provider."""

    def __init__(
        self,
        *,
        socket_path: Path,
        timeout_seconds: float,
        expected_socket_uid: int = PARSER_SOCKET_UID,
        expected_socket_gid: int = PARSER_SOCKET_GID,
    ) -> None:
        if (
            not socket_path.is_absolute()
            or type(timeout_seconds) is not float
            or not 0.1 <= timeout_seconds <= 60.0
            or type(expected_socket_uid) is not int
            or type(expected_socket_gid) is not int
            or expected_socket_uid < 0
            or expected_socket_gid < 0
        ):
            raise ValueError("guide parser service configuration is invalid")
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds
        self._expected_socket_uid = expected_socket_uid
        self._expected_socket_gid = expected_socket_gid
        self._identity = ExternalServiceAdapterIdentity(
            GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
            GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
        )

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        return self._identity

    async def parse(
        self,
        request: GuideDocumentParserRequest,
        source: bytes,
    ) -> GuideDocumentParserResponse:
        """Exchange one exact source frame and verify every returned binding."""
        try:
            checked = GuideDocumentParserRequest.model_validate(request)
            if type(source) is not bytes:
                raise ValueError("guide parser source must be exact bytes")
            if len(source) != checked.source_byte_count:
                raise ValueError("guide parser source length is inconsistent")
            if f"sha256:{sha256(source).hexdigest()}" != checked.source_sha256:
                raise ValueError("guide parser source hash is inconsistent")
            self._validate_socket()
            metadata = _json_bytes(
                {
                    "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
                    "operation": "parse",
                    "request": checked.model_dump(mode="json"),
                }
            )
            if len(metadata) > MAXIMUM_REQUEST_METADATA_BYTES:
                raise ValueError("guide parser request metadata is oversized")
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
                try:
                    writer.write(struct.pack(">I", len(metadata)))
                    writer.write(metadata)
                    writer.write(source)
                    await writer.drain()
                    raw = await _read_frame(reader, maximum=MAXIMUM_RESPONSE_BYTES)
                    if await reader.read(1):
                        raise ValueError("guide parser response has trailing bytes")
                finally:
                    writer.close()
                    await writer.wait_closed()
        except asyncio.CancelledError:
            raise
        except GuideDocumentParserRejectedError:
            raise
        except ExternalServiceProtocolError:
            raise
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as exc:
            raise ExternalServiceUnavailableError(self._identity) from exc
        except (TypeError, ValueError, ValidationError, UnicodeError, json.JSONDecodeError) as exc:
            raise ExternalServiceProtocolError(self._identity) from exc

        try:
            body = json.loads(raw)
            if (
                type(body) is not dict
                or body.get("protocol_version") != GUIDE_DOCUMENT_PARSER_PROTOCOL
            ):
                raise ValueError("guide parser response protocol is invalid")
            if body.get("status") == "rejected":
                if set(body) != {"protocol_version", "status", "reason"} or body["reason"] not in {
                    "document_encrypted",
                    "document_limit_exceeded",
                    "document_malformed",
                    "document_unsupported",
                }:
                    raise ValueError("guide parser rejection is invalid")
                raise GuideDocumentParserRejectedError(self._identity, body["reason"])
            if set(body) != {"protocol_version", "status", "result"} or body["status"] != "ok":
                raise ValueError("guide parser response shape is invalid")
            result = GuideDocumentParserResponse.model_validate(body["result"])
            result.validate_against(checked)
            return result
        except GuideDocumentParserRejectedError:
            raise
        except (TypeError, ValueError, ValidationError, UnicodeError, json.JSONDecodeError) as exc:
            raise ExternalServiceProtocolError(self._identity) from exc

    def _validate_socket(self) -> None:
        info = os.lstat(self._socket_path)
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != self._expected_socket_uid
            or info.st_gid != self._expected_socket_gid
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != PARSER_SOCKET_MODE
        ):
            raise ValueError("guide parser socket identity is invalid")


async def _read_frame(reader: asyncio.StreamReader, *, maximum: int) -> bytes:
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    if size == 0 or size > maximum:
        raise ValueError("guide parser response frame is invalid")
    return await reader.readexactly(size)


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "PARSER_SOCKET_GID",
    "PARSER_SOCKET_MODE",
    "PARSER_SOCKET_UID",
    "UnixSocketGuideDocumentParserAdapter",
)
