from __future__ import annotations

import json

import pytest

from workstream_mcp import schemas


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"output_schema": {"type": "object"}}, {"type": "object"}),
        ({"outputSchema": {"type": "string"}}, {"type": "string"}),
        ({"schema": {"type": "array"}}, {"type": "array"}),
        (
            {"components": {"schemas": {"ActorProfileSelfResponse": {"type": "boolean"}}}},
            {"type": "boolean"},
        ),
        ({"type": "object"}, {"type": "object"}),
        (
            {
                "operation": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Profile"}
                                }
                            }
                        }
                    }
                },
                "components": {"schemas": {"Profile": {"type": "object"}}},
            },
            {"type": "object"},
        ),
    ],
)
def test_selected_schema_supports_reviewed_contract_shapes(
    document: dict[str, object], expected: dict[str, object]
) -> None:
    assert schemas._selected_schema(document) == expected  # noqa: SLF001


def test_selected_schema_rejects_unusable_document() -> None:
    with pytest.raises(schemas.ContractError):
        schemas._selected_schema({})  # noqa: SLF001


def test_profile_schema_and_validator_are_cached_and_valid() -> None:
    schemas.profile_output_schema.cache_clear()
    schemas.profile_output_validator.cache_clear()
    schema = schemas.profile_output_schema()
    assert schema["title"] == "ActorProfileSelfResponse"
    assert schemas.profile_output_schema() is schema
    assert schemas.profile_output_validator() is schemas.profile_output_validator()


def test_invalid_packaged_document_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    schemas.profile_output_schema.cache_clear()

    class BrokenResource:
        def read_text(self, *, encoding: str) -> str:
            assert encoding == "utf-8"
            return json.dumps({"schema": {"not": "a valid schema node"}})

    class BrokenFiles:
        def joinpath(self, _: str) -> BrokenResource:
            return BrokenResource()

    monkeypatch.setattr(schemas, "files", lambda _: BrokenFiles())
    with pytest.raises(schemas.ContractError):
        schemas.profile_output_schema()
    schemas.profile_output_schema.cache_clear()
