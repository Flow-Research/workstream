"""Human phase image attachments resolve to exact immutable checker custody."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry, ExternalCheckerRegistrySpec, ExternalCheckerResourceLimits,
    ExternalCheckerSchema, PRE_SUBMIT_INPUT_SCHEMA_ID, POST_SUBMIT_INPUT_SCHEMA_ID,
    RESULT_SCHEMA_ID,
    ExternalCheckerRegistryUnavailable, external_checker_json_hash,
)
from app.modules.checkers.api.external_policy import (
    FORGE_FACTS_VERSION_KEY, SELECTED_POST_FORGE_FACTS_BUDGET_MS,
    ExternalCheckerImageAttachment, ExternalCheckerPolicyCompileRequest,
    ExternalCheckerPolicyError, ForgeFactsSelection,
    LockedExternalCheckerBinding, LockedExternalPostSubmitPolicy,
    LockedWorkstreamDefault, compile_external_checker_policies, selected_forge_facts,
    selected_post_submit_execution_budget_ms,
)
from app.modules.model_usage.api import (
    ModelGenerationSettings, ModelPricing, ProjectModelProfile, ProjectModelProfileSpec,
)


def _schema(schema_id):
    document = {"type": "object"}
    return ExternalCheckerSchema(
        schema_id=schema_id, schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def registry_spec(phase):
    return ExternalCheckerRegistrySpec(
        capability_id="acme.safe_archive", capability_version="v1.2.3", phase=phase,
        image_digest="sha256:" + "a" * 64,
        configuration_schema=_schema("acme.configuration"),
        input_schema=_schema(PRE_SUBMIT_INPUT_SCHEMA_ID if phase == "pre_submit" else POST_SUBMIT_INPUT_SCHEMA_ID),
        output_schema=_schema(RESULT_SCHEMA_ID),
        resources=ExternalCheckerResourceLimits(
            cpu_millis=500, memory_bytes=128 * 1024 * 1024,
            deadline_ms=30_000, maximum_output_bytes=32_768,
        ),
    )


def _entry(
    capability_id: str,
    phase: str,
    configuration_schema=None,
    *,
    deadline_ms: int | None = None,
) -> ExternalCheckerRegistryEntry:
    changes = {"capability_id": capability_id}
    if configuration_schema is not None:
        changes["configuration_schema"] = configuration_schema
    spec = registry_spec(phase).model_copy(update=changes)
    if deadline_ms is not None:
        spec = spec.model_copy(
            update={"resources": spec.resources.model_copy(update={"deadline_ms": deadline_ms})}
        )
    # Revalidate after changing one digest-bound specification field.
    spec = type(spec).model_validate(spec.model_dump())
    return ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=new_record_id(),
        entry_digest=spec.spec_digest,
        registration_operation_id=uuid4(),
        registered_by_actor_profile_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        created_at=datetime.now(UTC),
    )


class _Registry:
    def __init__(self, entries):
        self.entries = {(entry.registry_entry_id, entry.entry_digest): entry for entry in entries}
        self.calls = []

    async def read_exact(self, registry_entry_id, entry_digest):
        self.calls.append((registry_entry_id, entry_digest))
        try:
            return self.entries[(registry_entry_id, entry_digest)]
        except KeyError as exc:
            raise ExternalCheckerRegistryUnavailable("selected entry unavailable") from exc


def _attachment(entry, requirement_id, configuration=None):
    return ExternalCheckerImageAttachment(
        requirement_id=requirement_id,
        registry_entry_id=entry.registry_entry_id,
        registry_entry_digest=entry.entry_digest,
        configuration={} if configuration is None else configuration,
    )


def _request(pre=(), post=()):
    return ExternalCheckerPolicyCompileRequest(
        pre_submit_attachments=pre, post_submit_attachments=post,
    )


class _Profiles:
    def __init__(self, profile):
        self.profile = profile
        self.calls = []

    async def read_exact(self, selector, **scope):
        self.calls.append((selector, scope))
        return self.profile


def _model_configuration_schema() -> ExternalCheckerSchema:
    document = {
        "type": "object",
        "properties": {
            "model_profile_id": {"type": "string"},
            "model_profile_version": {"type": "integer"},
            "model_profile_digest": {"type": "string"},
        },
        "required": [
            "model_profile_id",
            "model_profile_version",
            "model_profile_digest",
        ],
        "additionalProperties": False,
    }
    return ExternalCheckerSchema(
        schema_id="acme.model.configuration",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _model_profile(project_id, entry) -> ProjectModelProfile:
    profile_id = new_record_id()
    pricing = ModelPricing(
        pricing_policy_id=new_record_id(),
        pricing_policy_version=1,
        pricing_policy_digest=external_checker_json_hash({"pricing": "fixed"}),
        uncached_input_nanodollars_per_token=3,
        cached_input_nanodollars_per_token=1,
        output_nanodollars_per_token=7,
    )
    spec = ProjectModelProfileSpec(
        project_id=project_id,
        profile_version=1,
        provider="openai_responses",
        api="responses.v1",
        model_snapshot="gpt-example-2026-10-01",
        settings=ModelGenerationSettings(reasoning_effort="medium", text_verbosity="low"),
        maximum_request_bytes=10_000,
        maximum_output_bytes=4_000,
        maximum_response_bytes=30_000,
        maximum_input_tokens=100,
        maximum_output_tokens=50,
        maximum_calls=1,
        maximum_total_request_bytes=10_000,
        maximum_total_response_bytes=30_000,
        maximum_total_input_tokens=100,
        maximum_total_output_tokens=50,
        allowed_tools=(),
        maximum_tool_calls=0,
        maximum_tool_output_bytes=0,
        deadline_ms=30_000,
        pricing=pricing,
    )
    return ProjectModelProfile(
        operation_id=uuid4(),
        actor_profile_id=uuid4(),
        spec=spec,
        profile_digest=external_checker_json_hash(spec.model_dump(mode="json")),
        profile_id=profile_id,
        authorization_evidence_id=uuid4(),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_explicit_empty_attachments_compile_only_the_default_pre():
    registry = _Registry(())
    pre, post = await compile_external_checker_policies(_request(), registry)
    assert pre.workstream_default.checker_id == "workstream.default"
    assert pre.entries == () and post.entries == ()
    assert registry.calls == []


@pytest.mark.asyncio
async def test_human_phase_attachments_use_exact_registry_rows_and_allow_reused_image():
    pre_entry = _entry("acme.safe_archive", "pre_submit")
    post_entry = _entry("acme.quality_review", "post_submit")
    registry = _Registry((pre_entry, post_entry))
    request = _request(
        pre=(_attachment(pre_entry, "archive_a"), _attachment(pre_entry, "archive_b")),
        post=(_attachment(post_entry, "quality"),),
    )
    pre, post = await compile_external_checker_policies(request, registry)
    assert [item.requirement_id for item in pre.entries] == ["archive_a", "archive_b"]
    assert [item.registry.registry_entry_id for item in pre.entries] == [
        pre_entry.registry_entry_id, pre_entry.registry_entry_id,
    ]
    assert [item.requirement_id for item in post.entries] == ["quality"]
    assert registry.calls == [
        (pre_entry.registry_entry_id, pre_entry.entry_digest),
        (pre_entry.registry_entry_id, pre_entry.entry_digest),
        (post_entry.registry_entry_id, post_entry.entry_digest),
    ]


@pytest.mark.parametrize("keys", [("same", "same"), ("z", "a")])
def test_duplicate_or_unsorted_human_member_keys_are_rejected(keys):
    entry = _entry("acme.safe_archive", "pre_submit")
    with pytest.raises(ValueError, match="unique canonical"):
        _request(pre=tuple(_attachment(entry, key) for key in keys))


def test_platform_default_member_key_is_reserved():
    entry = _entry("acme.safe_archive", "pre_submit")
    with pytest.raises(ValueError, match="platform checker key"):
        _attachment(entry, "workstream.default")


@pytest.mark.asyncio
async def test_missing_digest_and_wrong_phase_fail_before_policy_creation():
    pre_entry = _entry("acme.safe_archive", "pre_submit")
    post_entry = _entry("acme.quality_review", "post_submit")
    missing = _Registry(())
    with pytest.raises(ValueError, match="unavailable"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(pre_entry, "archive"),)), missing,
        )
    with pytest.raises(ValueError, match="phase mismatch"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(post_entry, "archive"),)), _Registry((post_entry,)),
        )
    wrong_digest = _attachment(pre_entry, "archive").model_copy(
        update={"registry_entry_digest": "sha256:" + "0" * 64}
    )
    with pytest.raises(ValueError, match="unavailable"):
        await compile_external_checker_policies(
            _request(pre=(wrong_digest,)), _Registry((pre_entry,)),
        )


@pytest.mark.asyncio
async def test_configuration_is_schema_checked_and_exact_json_is_locked():
    document = {"type": "object", "properties": {"groups": {
        "type": "array", "items": {"type": "string"},
    }}, "required": ["groups"], "additionalProperties": False}
    schema = ExternalCheckerSchema(
        schema_id="acme.groups.configuration", schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    entry = _entry("acme.safe_archive", "pre_submit", schema)
    pre, _ = await compile_external_checker_policies(
        _request(pre=(_attachment(entry, "archive", {"groups": ["a", "b"]}),)),
        _Registry((entry,)),
    )
    assert pre.entries[0].configuration == {"groups": ["a", "b"]}
    with pytest.raises(ValueError, match="value is invalid"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(entry, "archive", {"groups": [1]}),)),
            _Registry((entry,)),
        )


@pytest.mark.asyncio
async def test_model_profile_configuration_requires_exact_project_scope():
    project_id = new_record_id()
    entry = _entry("acme.quality_review", "post_submit", _model_configuration_schema())
    profile = _model_profile(project_id, entry)
    config = {
        "model_profile_id": str(profile.profile_id),
        "model_profile_version": 1,
        "model_profile_digest": profile.profile_digest,
    }
    profiles = _Profiles(profile)
    _, post = await compile_external_checker_policies(
        _request(post=(_attachment(entry, "quality", config),)),
        _Registry((entry,)), project_id=project_id, profiles=profiles,
    )
    assert post.entries[0].configuration == config
    assert profiles.calls[0][1] == {"project_id": project_id}
    with pytest.raises(ValueError):
        await compile_external_checker_policies(
            _request(post=(_attachment(entry, "quality", config),)),
            _Registry((entry,)), project_id=new_record_id(), profiles=profiles,
        )
    with pytest.raises(ValueError):
        await compile_external_checker_policies(
            _request(post=(_attachment(entry, "quality", {"model_profile_id": config["model_profile_id"]}),)),
            _Registry((entry,)), project_id=project_id, profiles=profiles,
        )


@pytest.mark.asyncio
async def test_aggregate_pre_and_post_budgets_reject_unrunnable_images():
    pre_a = _entry("acme.a", "pre_submit", deadline_ms=3_600_000)
    pre_b = _entry("acme.b", "pre_submit", deadline_ms=3_600_000)
    with pytest.raises(ValueError, match="ART custody deadline"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(pre_a, "a"), _attachment(pre_b, "b"))),
            _Registry((pre_a, pre_b)),
        )
    post = _entry("acme.post", "post_submit", deadline_ms=3_600_000)
    with pytest.raises(ValueError, match="durable worker deadline"):
        await compile_external_checker_policies(
            _request(post=(_attachment(post, "p"),)), _Registry((post,)),
        )


def test_locked_default_refuses_substituted_behavior_digest():
    with pytest.raises(ValueError, match="behavior"):
        LockedWorkstreamDefault(behavior_sha256="sha256:" + "0" * 64)


def _forge_binding(configuration, *, declared=True, phase="post_submit"):
    """A binding over a published schema that does or does not declare forge facts."""
    properties = {
        "repository": {"type": "string"},
        "forge": {"type": "string"},
        "forge_origin": {"type": "string"},
    }
    if declared:
        properties[FORGE_FACTS_VERSION_KEY] = {"const": "v1"}
    document = {"type": "object", "properties": properties}
    schema = ExternalCheckerSchema(
        schema_id="harnessy_work_proof_config",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    return LockedExternalCheckerBinding(
        requirement_id="harnessy.work_proof",
        stage=phase,
        registry=_entry("harnessy.work_proof", phase, configuration_schema=schema),
        configuration=configuration,
        configuration_sha256=external_checker_json_hash(configuration),
    )


_FORGE_SELECTION = {
    FORGE_FACTS_VERSION_KEY: "v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "Flow-Research/harnessy-v2",
    "base_branch": "dev",
}


def test_forge_facts_are_selected_only_by_an_exact_declared_post_capability():
    binding = _forge_binding(_FORGE_SELECTION)
    assert selected_forge_facts(binding.configuration, binding.stage) == ForgeFactsSelection(
        forge="github",
        forge_origin="https://github.com",
        repository="Flow-Research/harnessy-v2",
        base_branch="dev",
    )
    # A neutral path may hold subgroups and a self-hosted instance with a port.
    assert selected_forge_facts(
        {
            **_FORGE_SELECTION,
            "forge_origin": "https://git.example.org:8443",
            "repository": "group/subgroup/project",
        },
        "post_submit",
    ) == ForgeFactsSelection(
        forge="github",
        forge_origin="https://git.example.org:8443",
        repository="group/subgroup/project",
        base_branch="dev",
    )
    assert selected_forge_facts({"repository": "a/b"}, "post_submit") is None
    with pytest.raises(ValueError, match="schema does not declare forge facts"):
        _forge_binding(_FORGE_SELECTION, declared=False)


@pytest.mark.parametrize(
    "changes",
    [
        {FORGE_FACTS_VERSION_KEY: "v2"},
        {"forge": "gitlab"},
        {"forge": None},
        {"repository": "Flow-Research"},
        {"repository": "https://github.com/Flow-Research/harnessy-v2"},
        {"repository": "Flow-Research/.."},
        {"repository": "a/" + "b" * 254},
        {"forge_origin": None},
        {"forge_origin": "http://github.com"},
        {"forge_origin": "https://github.com/"},
        {"forge_origin": "https://github.com/Flow-Research"},
        {"base_branch": ""},
        {"base_branch": 7},
    ],
)
def test_invalid_forge_facts_selection_never_reads_facts(changes):
    with pytest.raises(ExternalCheckerPolicyError, match="forge facts selection"):
        selected_forge_facts({**_FORGE_SELECTION, **changes}, "post_submit")


def test_pre_submit_cannot_select_forge_facts():
    with pytest.raises(ExternalCheckerPolicyError, match="forge facts selection"):
        selected_forge_facts(_FORGE_SELECTION, "pre_submit")


def test_selected_post_budget_reserves_the_forge_facts_read():
    plain, selected = _forge_binding({}), _forge_binding(_FORGE_SELECTION)

    def budget(binding):
        body = {
            "schema_version": "external_post_submit_policy.v1",
            "entries": [binding.model_dump(mode="json")],
        }
        return selected_post_submit_execution_budget_ms(
            LockedExternalPostSubmitPolicy(
                entries=(binding,), policy_sha256=canonical_json_hash(body)
            )
        )

    assert budget(selected) - budget(plain) == SELECTED_POST_FORGE_FACTS_BUDGET_MS
