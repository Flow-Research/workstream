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
    compile_external_checker_policy_bundle,
    validate_stored_external_post_policy,
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
    input_schema=None,
) -> ExternalCheckerRegistryEntry:
    changes = {"capability_id": capability_id}
    if configuration_schema is not None:
        changes["configuration_schema"] = configuration_schema
    if input_schema is not None:
        changes["input_schema"] = input_schema
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


@pytest.mark.parametrize("phase", ["pre", "post"])
@pytest.mark.parametrize("count", [0, 2])
def test_new_policy_requires_exactly_one_image_per_phase(phase, count):
    pre_entry = _entry("acme.safe_archive", "pre_submit")
    post_entry = _entry("acme.quality_review", "post_submit")
    members = {
        "pre": (_attachment(pre_entry, "archive"),),
        "post": (_attachment(post_entry, "quality"),),
    }
    entry = pre_entry if phase == "pre" else post_entry
    members[phase] = tuple(_attachment(entry, f"member_{i}") for i in range(count))
    with pytest.raises(ValueError):
        _request(**members)


@pytest.mark.asyncio
async def test_human_phase_attachments_resolve_exactly_one_registry_row_each():
    pre_entry = _entry("acme.safe_archive", "pre_submit")
    post_entry = _entry("acme.quality_review", "post_submit")
    registry = _Registry((pre_entry, post_entry))
    request = _request(
        pre=(_attachment(pre_entry, "archive"),),
        post=(_attachment(post_entry, "quality"),),
    )
    pre, post = await compile_external_checker_policies(request, registry)
    assert pre.workstream_default.checker_id == "workstream.default"
    assert [item.requirement_id for item in pre.entries] == ["archive"]
    assert [item.registry.registry_entry_id for item in pre.entries] == [pre_entry.registry_entry_id]
    assert [item.requirement_id for item in post.entries] == ["quality"]
    assert registry.calls == [
        (pre_entry.registry_entry_id, pre_entry.entry_digest),
        (post_entry.registry_entry_id, post_entry.entry_digest),
    ]


@pytest.mark.parametrize("keys", [("same", "same"), ("z", "a")])
def test_duplicate_or_unsorted_human_member_keys_are_rejected(keys):
    entry = _entry("acme.safe_archive", "pre_submit")
    with pytest.raises(ValueError, match="at most 1 item"):
        _request(pre=tuple(_attachment(entry, key) for key in keys),
                 post=(_attachment(_entry("acme.post", "post_submit"), "quality"),))


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
            _request(pre=(_attachment(pre_entry, "archive"),), post=(_attachment(post_entry, "quality"),)), missing,
        )
    with pytest.raises(ValueError, match="phase mismatch"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(post_entry, "archive"),), post=(_attachment(post_entry, "quality"),)), _Registry((post_entry,)),
        )
    wrong_digest = _attachment(pre_entry, "archive").model_copy(
        update={"registry_entry_digest": "sha256:" + "0" * 64}
    )
    with pytest.raises(ValueError, match="unavailable"):
        await compile_external_checker_policies(
            _request(pre=(wrong_digest,), post=(_attachment(post_entry, "quality"),)), _Registry((pre_entry,)),
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
    post = _entry("acme.post", "post_submit")
    pre, _ = await compile_external_checker_policies(
        _request(pre=(_attachment(entry, "archive", {"groups": ["a", "b"]}),), post=(_attachment(post, "quality"),)),
        _Registry((entry, post)),
    )
    assert pre.entries[0].configuration == {"groups": ["a", "b"]}
    with pytest.raises(ValueError, match="value is invalid"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(entry, "archive", {"groups": [1]}),), post=(_attachment(post, "quality"),)),
            _Registry((entry, post)),
        )


@pytest.mark.asyncio
async def test_model_profile_configuration_requires_exact_project_scope():
    pre = _entry("acme.pre", "pre_submit")
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
        _request(pre=(_attachment(pre, "archive"),), post=(_attachment(entry, "quality", config),)),
        _Registry((pre, entry)), project_id=project_id, profiles=profiles,
    )
    assert post.entries[0].configuration == config
    assert profiles.calls[0][1] == {"project_id": project_id}
    with pytest.raises(ValueError):
        await compile_external_checker_policies(
            _request(pre=(_attachment(pre, "archive"),), post=(_attachment(entry, "quality", config),)),
            _Registry((pre, entry)), project_id=new_record_id(), profiles=profiles,
        )
    with pytest.raises(ValueError):
        await compile_external_checker_policies(
            _request(pre=(_attachment(pre, "archive"),), post=(_attachment(entry, "quality", {"model_profile_id": config["model_profile_id"]}),)),
            _Registry((pre, entry)), project_id=project_id, profiles=profiles,
        )


@pytest.mark.asyncio
async def test_retained_pre_and_new_post_budgets_reject_unrunnable_images():
    from app.modules.checkers.api.external_policy import validate_stored_external_pre_policy

    pre_entry = _entry("acme.pre", "pre_submit", deadline_ms=3_600_000)
    post_entry = _entry("acme.post", "post_submit")
    pre, _ = await compile_external_checker_policies(
        _request(pre=(_attachment(pre_entry, "a"),), post=(_attachment(post_entry, "p"),)),
        _Registry((pre_entry, post_entry)),
    )
    # Retained multi-image evidence keeps its original aggregate budget guard.
    body = pre.model_dump(mode="json", exclude={"policy_sha256"})
    body["entries"].append(body["entries"][0] | {"requirement_id": "b"})
    with pytest.raises(ValueError, match="ART custody deadline"):
        validate_stored_external_pre_policy(body | {"policy_sha256": canonical_json_hash(body)})
    post = _entry("acme.post", "post_submit", deadline_ms=3_600_000)
    with pytest.raises(ValueError, match="durable worker deadline"):
        await compile_external_checker_policies(
            _request(pre=(_attachment(pre_entry, "a"),), post=(_attachment(post, "p"),)),
            _Registry((pre_entry, post)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 2])
async def test_historical_phase_cardinality_preserves_exact_locked_evidence(count):
    from app.modules.checkers.api.external_policy import validate_stored_external_pre_policy

    pre_entry = _entry("acme.pre", "pre_submit")
    post_entry = _entry("acme.post", "post_submit")
    pre, post = await compile_external_checker_policies(
        _request(pre=(_attachment(pre_entry, "a"),), post=(_attachment(post_entry, "p"),)),
        _Registry((pre_entry, post_entry)),
    )
    for policy, decode in ((pre, validate_stored_external_pre_policy),
                           (post, validate_stored_external_post_policy)):
        body = policy.model_dump(mode="json", exclude={"policy_sha256"})
        member = body["entries"][0]
        body["entries"] = [member | {"requirement_id": f"member_{i}"} for i in range(count)]
        retained = body | {"policy_sha256": canonical_json_hash(body)}
        assert decode(retained).model_dump(mode="json") == retained


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["pre", "post"])
@pytest.mark.parametrize("keys,reason", [(("a", "a"), "duplicated"), (("b", "a"), "not canonical")])
async def test_retained_policy_rejects_duplicate_or_reordered_members_even_with_matching_hash(phase, keys, reason):
    from app.modules.checkers.api.external_policy import validate_stored_external_pre_policy

    pre_entry = _entry("acme.pre", "pre_submit")
    post_entry = _entry("acme.post", "post_submit")
    pre, post = await compile_external_checker_policies(
        _request(pre=(_attachment(pre_entry, "a"),), post=(_attachment(post_entry, "p"),)),
        _Registry((pre_entry, post_entry)),
    )
    policy, decode = ((pre, validate_stored_external_pre_policy) if phase == "pre"
                      else (post, validate_stored_external_post_policy))
    body = policy.model_dump(mode="json", exclude={"policy_sha256"})
    body["entries"] = [body["entries"][0] | {"requirement_id": key} for key in keys]
    with pytest.raises(ValueError, match=reason):
        decode(body | {"policy_sha256": canonical_json_hash(body)})


def test_locked_default_refuses_substituted_behavior_digest():
    with pytest.raises(ValueError, match="behavior"):
        LockedWorkstreamDefault(behavior_sha256="sha256:" + "0" * 64)


def _forge_binding(configuration, *, declared=True, phase="post_submit", locator_declared=True):
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
    input_document = {"type": "object"}
    if locator_declared:
        input_document["properties"] = {
            "workstream_forge_facts_stage": {"type": "string", "const": "locate"},
        }
    input_schema = ExternalCheckerSchema(
        schema_id=POST_SUBMIT_INPUT_SCHEMA_ID, schema_version="v1",
        document=input_document, schema_sha256=external_checker_json_hash(input_document),
    )
    return LockedExternalCheckerBinding(
        requirement_id="harnessy.work_proof",
        stage=phase,
        registry=_entry("harnessy.work_proof", phase, configuration_schema=schema, input_schema=input_schema),
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

    assert budget(selected) - budget(plain) == (
        SELECTED_POST_FORGE_FACTS_BUDGET_MS
        + selected.registry.resources.deadline_ms
        + 60_000
    )


def test_retained_forge_policy_without_locator_declaration_preserves_locked_json_and_hash():
    binding = _forge_binding(_FORGE_SELECTION, locator_declared=False)
    body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [binding.model_dump(mode="json")],
    }
    original_digest = canonical_json_hash(body)
    retained = {**body, "policy_sha256": original_digest}

    restored = validate_stored_external_post_policy(retained)

    assert restored.model_dump(mode="json") == retained
    assert restored.policy_sha256 == original_digest
    assert restored.entries[0].registry.entry_digest == binding.registry.entry_digest
    assert selected_forge_facts(restored.entries[0].configuration, "post_submit") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("compiler", [
    compile_external_checker_policies,
    compile_external_checker_policy_bundle,
])
async def test_new_forge_binding_without_locator_declaration_cannot_compile(compiler):
    pre = _entry("acme.pre", "pre_submit")
    binding = _forge_binding(_FORGE_SELECTION, locator_declared=False)
    entry = binding.registry
    request = _request(pre=(_attachment(pre, "archive"),), post=(_attachment(entry, binding.requirement_id, _FORGE_SELECTION),))

    with pytest.raises(ExternalCheckerPolicyError, match="does not declare forge locator"):
        await compiler(request, _Registry((pre, entry)))


@pytest.mark.asyncio
async def test_new_forge_binding_with_locator_declaration_compiles_in_approval_bundle():
    pre = _entry("acme.pre", "pre_submit")
    binding = _forge_binding(_FORGE_SELECTION)
    entry = binding.registry
    request = _request(pre=(_attachment(pre, "archive"),), post=(_attachment(entry, binding.requirement_id, _FORGE_SELECTION),))

    policies = await compile_external_checker_policy_bundle(request, _Registry((pre, entry)))

    assert policies.post_submit.entries == (binding,)
    assert policies.post_submit.entries[0].registry.entry_digest == entry.entry_digest
