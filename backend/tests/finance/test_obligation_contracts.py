"""Both public owners reject ambiguous or altered financial source evidence."""

import json
from pathlib import Path

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.compensation.api.fulfillment_contracts import decode_obligation as compensation
from app.modules.finance.api.fulfillment_contracts import decode_obligation as finance

FIXTURES = Path(__file__).parents[2] / "app/modules/finance/contracts/fixtures"


@pytest.fixture(params=[compensation, finance], ids=["compensation", "finance"])
def decode(request):
    return request.param


def vector():
    return json.loads((FIXTURES / "obligation-points.json").read_text())


def encode(value):
    return json.dumps(value).encode()


def resign(value):
    keys = (
        "award_id project_id contribution_record_id contributor_id "
        "contribution_policy_version_id award_definition_id adapter_binding_id "
        "instrument_type unit_code quantity awarded_at correlation_id"
    ).split()
    value["source_award_digest"] = canonical_json_hash({key: value[key] for key in keys})
    value["obligation_digest"] = canonical_json_hash(
        {key: item for key, item in value.items() if key != "obligation_digest"}
    )
    return encode(value)


def test_known_vector(decode):
    assert decode(encode(vector())) == vector()


@pytest.mark.parametrize(
    "fixture",
    sorted([*FIXTURES.glob("obligation-*.json"), *FIXTURES.glob("invalid-obligation-*.json")]),
    ids=lambda p: p.name,
)
def test_portable_fixture_corpus(decode, fixture):
    if fixture.name.startswith("invalid-"):
        with pytest.raises(ValueError):
            decode(fixture.read_bytes())
    else:
        assert decode(fixture.read_bytes()) == json.loads(fixture.read_bytes())


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b"null",
        b"1",
        b"\xff",
        b"{}" + b" " * 65535,
        b'{"award_id":1,"award_id":2}',
        b'{"nested":{"x":1,"x":2}}',
        b'{"amount":NaN}',
        b'{"amount":Infinity}',
        b"{",
    ],
)
def test_raw_wire_rejected(decode, body):
    with pytest.raises(ValueError):
        decode(body)


def test_changed_quantity_with_original_digests_rejected(decode):
    with pytest.raises(ValueError, match="digest mismatch"):
        decode(encode(vector() | {"quantity": "11"}))


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "10.0"},
        {"quantity": 10},
        {"quantity": "0"},
        {"quantity": "1e1"},
        {"quantity": "-1"},
        {"quantity": "1.5"},
        {"quantity": "100000000000000000000"},
        {"quantity": "0.0000000000000000001"},
        {"awarded_at": "2026-11-12T05:00:00Z"},
        {"awarded_at": "2026-02-30T05:00:00.000000Z"},
        {"award_id": "019A78B0-0000-7000-8000-000000000011"},
        {"task_size": None},
        {"review_id": "019a78b0-0000-7000-8000-000000000008"},
        {"contract_version": True},
        {"contract_version": 1.0},
        {"route_key": "finance..primary"},
        {"bank_account": "forbidden"},
    ],
)
def test_invalid_source_rejected_even_with_recomputed_digests(decode, change):
    with pytest.raises(ValueError):
        decode(resign(vector() | change))


def test_explicit_null_field_cannot_be_omitted(decode):
    value = vector()
    del value["review_id"]
    with pytest.raises(ValueError):
        decode(encode(value))


@pytest.mark.parametrize(
    "change",
    [
        {"instrument_type": "money", "unit_code": "NGN", "quantity": "2000.01"},
        {
            "contribution_type": "completed_review",
            "task_size": None,
            "final_acceptance_id": None,
            "review_id": "019a78b0-0000-7000-8000-000000000008",
        },
    ],
)
def test_valid_alternative_sources(decode, change):
    value = vector() | change
    assert decode(resign(value)) == value
