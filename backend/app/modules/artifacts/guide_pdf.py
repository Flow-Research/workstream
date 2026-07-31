"""Bounded canonical PDF extraction for the isolated guide worker."""

from __future__ import annotations

from io import BytesIO
import json
import re
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject


MAXIMUM_PDF_PAGES = 500
_MAXIMUM_INSPECTED_OBJECTS = 100_000
_INVALID_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_FORBIDDEN_KEYS = frozenset(
    {
        "/AA",
        "/A",
        "/AcroForm",
        "/AF",
        "/Collection",
        "/EmbeddedFiles",
        "/EF",
        "/FileAttachment",
        "/ImportData",
        "/JavaScript",
        "/JS",
        "/Launch",
        "/Movie",
        "/OpenAction",
        "/RichMedia",
        "/Screen",
        "/Sound",
        "/SubmitForm",
        "/URI",
        "/XFA",
    }
)
_FORBIDDEN_ACTIONS = frozenset(
    {"/GoToE", "/GoToR", "/ImportData", "/JavaScript", "/Launch", "/SubmitForm", "/URI"}
)
_FORBIDDEN_OBJECT_TYPES = frozenset(
    {"/3D", "/FileAttachment", "/Filespec", "/Movie", "/RichMedia", "/Screen", "/Sound", "/Widget"}
)


class PdfExtractionFailure(Exception):
    """Carry one bounded PDF-specific outcome to the extraction worker."""

    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _resolve(value: Any) -> Any:
    if isinstance(value, IndirectObject):
        return value.get_object()
    return value


def _reject_active_content(root: Any) -> None:
    """Reject interactive, executable, attached, or externally resolving objects."""
    pending = [root]
    visited: set[tuple[int, int] | int] = set()
    inspected = 0
    while pending:
        value = pending.pop()
        if isinstance(value, IndirectObject):
            identity: tuple[int, int] | int = (value.idnum, value.generation)
            if identity in visited:
                continue
            visited.add(identity)
            value = _resolve(value)
        elif isinstance(value, (DictionaryObject, ArrayObject)):
            identity = id(value)
            if identity in visited:
                continue
            visited.add(identity)
        else:
            continue
        inspected += 1
        if inspected > _MAXIMUM_INSPECTED_OBJECTS:
            raise PdfExtractionFailure("limit_exceeded", "pdf_object_limit")
        if isinstance(value, DictionaryObject):
            for key, child in value.items():
                key_text = str(key)
                if key_text in _FORBIDDEN_KEYS:
                    raise PdfExtractionFailure("malformed", "pdf_active_content")
                if key_text == "/S" and str(_resolve(child)) in _FORBIDDEN_ACTIONS:
                    raise PdfExtractionFailure("malformed", "pdf_active_content")
                if key_text in {"/Subtype", "/Type"} and str(_resolve(child)) in (
                    _FORBIDDEN_OBJECT_TYPES
                ):
                    raise PdfExtractionFailure("malformed", "pdf_active_content")
                pending.append(child)
        elif isinstance(value, ArrayObject):
            pending.extend(value)


def _canonical_page_text(value: str | None) -> str:
    text = "" if value is None else value
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if _INVALID_CONTROL.search(text):
        raise PdfExtractionFailure("malformed", "pdf_invalid_text")
    return text


def extract_pdf(payload: bytes) -> str:
    """Return deterministic page-separated JSON for one passive PDF."""
    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        if reader.is_encrypted:
            raise PdfExtractionFailure("malformed", "pdf_encrypted")
        page_count = len(reader.pages)
        if page_count > MAXIMUM_PDF_PAGES:
            raise PdfExtractionFailure("limit_exceeded", "pdf_page_limit")
        _reject_active_content(reader.root_object)
        pages = [_canonical_page_text(page.extract_text()) for page in reader.pages]
    except PdfExtractionFailure:
        raise
    except (PdfReadError, IndexError, KeyError, RecursionError, TypeError, ValueError) as exc:
        raise PdfExtractionFailure("malformed", "invalid_pdf") from exc
    return json.dumps({"pages": pages}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
