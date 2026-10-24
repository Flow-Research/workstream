"""Public guide input, worker output, separate approvals and policy publication."""

from dataclasses import dataclass
import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import text

from app.modules.authorization.api import ActorIdentityFacts
from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor
from experiments.pilot04_external_checker_runtime.guide_evidence import verify_source_commitment
from experiments.pilot04_external_checker_runtime.guide_polling import wait_for_guide_read
from experiments.pilot04_external_checker_runtime.guide_inputs import (
    guide_bytes, TASK_EXAMPLES, CORRECTION_REASON,
)


@dataclass(frozen=True)
class PublicGuideSource:
    project_id: UUID
    guide_id: UUID
    manager: ActorIdentityFacts
    activation: dict
    evidence: dict


async def _public_policy_settings(client, root, token, human_review_required, call):
    for kind, body in (
        ("review", {"human_review_required": human_review_required,
                    "review_preference_window_seconds": 3600,
                    "review_lease_duration_seconds": 1800,
                    "allowed_decisions": ["accept", "needs_revision", "reject"]}),
        ("revision", {"max_revision_rounds": 2, "revision_deadline_hours": 48,
                      "allowed_resubmission_states": ["needs_revision"]}),
    ):
        headers = {"Idempotency-Key": str(uuid4()), "If-Match": '"no-current-policy"'}
        result = await call(client, "PUT", root + f"/{kind}-policy", token, 200,
                            headers=headers, json=body)
        replay = await call(client, "PUT", root + f"/{kind}-policy", token, 200,
                            headers=headers, json=body)
        if replay != result:
            raise AssertionError("public policy configuration replay changed")
        await call(client, "PUT", root + f"/{kind}-policy", token, 409,
                   headers={**headers, "Idempotency-Key": str(uuid4())}, json=body)


async def _finance_policy(client, factory, project_id, token_for, compensated, call):
    finance, _ = await seed_review_actor(factory, project_id, role="finance_authority")
    token = token_for(finance)
    definitions = []
    if compensated:
        from app.modules.authorization.runtime import (
            HumanAuthorizationContext, ActorKind, ActorStatus, IdentityLinkStatus,
        )
        from tests.projects.guide_activation.compensation_fixtures import create_binding
        context = HumanAuthorizationContext(
            actor_profile_id=finance.actor_profile_id, actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE, identity_link_id=finance.identity_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(), correlation_id=uuid4(),
        )
        binding = await create_binding(
            factory, SimpleNamespace(project=project_id, context=context),
            instrument_type="project_points",
        )
        definitions = [{"instrument_type": "project_points", "unit_code": "PTS",
                        "quantity": "7", "adapter_binding_id": str(binding)}]
    root = f"/api/v1/projects/{project_id}/contribution-policies"
    created = await call(client, "POST", root + "/drafts", token, 201,
                         headers={"Idempotency-Key": str(uuid4())},
                         json={"name": "Public guide journey rules"})
    version = root + f"/{created['contribution_policy_id']}/versions/{created['contribution_policy_version_id']}"
    rules = [{"contribution_type": kind,
              "compensation_mode": "compensated" if definitions else "unpaid",
              "definitions": definitions}
             for kind in ("accepted_submission", "completed_review")]
    await call(client, "PUT", version, token, 200,
               headers={"Idempotency-Key": str(uuid4())}, json={"rules": rules})
    headers = {"Idempotency-Key": str(uuid4())}
    published = await call(client, "POST", version + "/publication", token, 200,
                           headers=headers, json={})
    replay = await call(client, "POST", version + "/publication", token, 200,
                        headers=headers, json={})
    if published != replay:
        raise AssertionError("Finance publication replay changed")
    return published


async def _correct_public_proposal(client, compilation_root, package, token, call):
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"target": package["target"], "reason": CORRECTION_REASON}
    receipt = await call(client, "POST", compilation_root + "/corrections", token, 201,
                         headers=headers, json=body)
    replay = await call(client, "POST", compilation_root + "/corrections", token, 201,
                        headers=headers, json=body)
    if replay != receipt:
        raise AssertionError("correction replay created another successor")
    dispatch = compilation_root + f"/corrections/{receipt['operation_id']}/dispatch"
    await call(client, "POST", dispatch, token, 202)
    return receipt


async def _approve_policies(client, compilation_root, token, call):
    package = await call(client, "GET", compilation_root + "/proposal", token, 200)
    if package["artifact_policy_status"] != "draft" or package["current_approval_operation_id"]:
        raise AssertionError("setup approved a policy without a manager decision")
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"target": package["target"], "acknowledged_warning_hashes": package["warning_hashes"]}
    approved = await call(client, "POST", compilation_root + "/pre-submission-approval",
                          token, 200, headers=headers, json=body)
    replay = await call(client, "POST", compilation_root + "/pre-submission-approval",
                        token, 200, headers=headers, json=body)
    if replay != approved:
        raise AssertionError("PRE approval replay changed receipt")
    package = await wait_for_guide_read(client, compilation_root + "/proposal", token,
                               lambda v: v["post_submit_policy_id"] is not None, call)
    post_root = compilation_root + f"/post-submission-policies/{package['post_submit_policy_id']}"
    post = await call(client, "GET", post_root, token, 200)
    if post["lifecycle_status"] != "compiled" or post["approval_operation_id"]:
        raise AssertionError("PRE approval silently approved POST")
    headers = {"Idempotency-Key": str(uuid4())}
    approved_post = await call(client, "POST", post_root + "/approval", token, 200,
                               headers=headers, json={"target": post["target"]})
    replay_post = await call(client, "POST", post_root + "/approval", token, 200,
                             headers=headers, json={"target": post["target"]})
    if replay_post != approved_post:
        raise AssertionError("POST approval replay changed receipt")
    return await call(client, "GET", post_root, token, 200)


async def _source_evidence(factory, guide, setup, package, original):
    expected_examples = [x.model_dump(mode="json") for x in validate_task_examples(TASK_EXAMPLES)]
    examples_hash = task_examples_hash(validate_task_examples(TASK_EXAMPLES))
    async with factory() as session:
        source = (await session.execute(text(
            "SELECT g.task_examples,g.task_examples_hash,s.manifest_json,s.bundle_hash "
            "FROM project_guides g JOIN guide_source_snapshots s ON s.guide_id=g.id "
            "WHERE g.id=:guide AND s.id=:source"
        ), {"guide": guide["id"], "source": setup["source_snapshot_id"]})).one()
        attempt = (await session.execute(text(
            "SELECT a.id,a.canonical_input_hash,a.source_snapshot_hash,a.source_snapshot_id,"
            "a.guide_material_hash,a.status,c.canonical_input_hash AS compiled_input_hash "
            "FROM project_guide_compilation_attempts a "
            "JOIN project_guide_compilations c ON c.id=a.persisted_compilation_id AND c.attempt_id=a.id "
            "WHERE a.setup_run_id=:setup"
        ), {"setup": setup["id"]})).one()
        accesses = (await session.execute(text(
            "SELECT i.source_snapshot_id,d.sha256,d.manifest_sha256,d.access_method,d.operation "
            "FROM project_guide_document_accesses d "
            "JOIN guide_source_snapshot_items i ON i.id=d.source_item_id "
            "WHERE d.attempt_id=:attempt"
        ), {"attempt": attempt.id})).mappings().all()
    verify_source_commitment(
        source._mapping, attempt._mapping, examples=expected_examples,
        examples_hash=examples_hash, source_hash=package["target"]["source_snapshot_hash"],
        source_id=setup["source_snapshot_id"], accesses=accesses,
        original_sha256="sha256:" + hashlib.sha256(original).hexdigest(),
    )
    return {"guide_id": guide["id"], "setup_run_id": setup["id"],
            "setup_generation": setup["setup_generation"],
            "source_snapshot_id": setup["source_snapshot_id"],
            "source_snapshot_hash": source.bundle_hash,
            "task_examples_hash": examples_hash,
            "canonical_input_hash": attempt.canonical_input_hash,
            "uploaded_sha256": "sha256:" + hashlib.sha256(original).hexdigest()}


async def public_guide_setup(client, factory, human_review_required, call, token_for, *, pre_requirements=1):
    original = guide_bytes(pre_requirements)
    manager, _ = await seed_review_actor(factory, None, scope="system")
    token = token_for(manager)
    project = await call(client, "POST", "/api/v1/projects", token, 201,
                         headers={"Idempotency-Key": str(uuid4())},
                         json={"name": "Connected guide journey", "slug": "journey-" + uuid4().hex})
    await seed_review_actor(factory, UUID(project["id"]), actor=manager)
    root = f"/api/v1/projects/{project['id']}/guides"
    body = {"version": "initial", "change_summary": "Original sample worker guide",
            "task_examples": TASK_EXAMPLES,
            "documents": [{"label": "guide.md", "media_type": "text/markdown"}]}
    headers = {"Idempotency-Key": str(uuid4())}
    guide = await call(client, "POST", root, token, 201, headers=headers, json=body)
    replay = await call(client, "POST", root, token, 201, headers=headers, json=body)
    if replay != guide:
        raise AssertionError("guide creation replay changed source")
    root += "/" + guide["id"]
    await _public_policy_settings(client, root, token, human_review_required, call)
    upload = root + f"/documents/{guide['documents'][0]['document_id']}/content"
    await call(client, "POST", upload, token, 202,
               headers={"Idempotency-Key": str(uuid4()), "Content-Type": "text/markdown"},
               content=original)
    setup = await wait_for_guide_read(client, root + "/setup-runs/latest", token,
                             lambda v: v["status"] == "policy_draft_ready", call)
    compilation_root = root + f"/compilations/{setup['finalized_compilation_id']}"
    initial = await call(client, "GET", compilation_root + "/proposal", token, 200)
    initial_setup = setup
    if human_review_required:
        correction = await _correct_public_proposal(client, compilation_root, initial, token, call)
        setup = await wait_for_guide_read(client, root + "/setup-runs/latest", token,
            lambda v: v["status"] == "policy_draft_ready"
            and v["setup_generation"] == initial_setup["setup_generation"] + 1, call)
        if (setup["source_snapshot_id"] != initial_setup["source_snapshot_id"]
                or setup["predecessor_compilation_id"] != initial_setup["finalized_compilation_id"]
                or setup["correction_operation_id"] != correction["operation_id"]):
            raise AssertionError("correction successor lost original source or predecessor")
        retained = await call(client, "GET", compilation_root + "/proposal", token, 200)
        if retained["current"] or retained["result"] != initial["result"]:
            raise AssertionError("correction changed or retained current predecessor")
        await call(client, "POST", compilation_root + "/pre-submission-approval", token, 409,
                   headers={"Idempotency-Key": str(uuid4())},
                   json={"target": initial["target"],
                         "acknowledged_warning_hashes": initial["warning_hashes"]})
        compilation_root = root + f"/compilations/{setup['finalized_compilation_id']}"
    await _finance_policy(client, factory, UUID(project["id"]), token_for,
                          not human_review_required, call)
    post = await _approve_policies(client, compilation_root, token, call)
    context = post["activation_context"]
    activation = {"target": post["target"], **{field: context[field] for field in (
        "post_approval_operation_id", "post_approval_output_digest", "guide_mutation_generation",
        "review", "revision", "expected_previous_active_guide_id", "expected_previous_active_guide_generation",
    )}, **context["contribution"]}
    evidence = await _source_evidence(factory, guide, setup, post["proposal"], original)
    target, upstream = post["target"], post["target"]["upstream"]
    evidence["locked_context"] = {
        "locked_guide_version": guide["version"],
        "locked_guide_source_snapshot_id": setup["source_snapshot_id"],
        "locked_guide_source_snapshot_hash": target["proposal"]["source_snapshot_hash"],
        "locked_effective_project_submission_artifact_policy_id": upstream["effective_policy_id"],
        "locked_effective_project_submission_artifact_policy_hash": upstream["effective_policy_hash"],
        "locked_pre_submit_checker_policy_id": upstream["pre_submit_policy_id"],
        "locked_pre_submit_checker_bundle_hash": upstream["pre_submit_bundle_hash"],
        "locked_post_submit_checker_policy_id": target["policy_id"],
        "locked_post_submit_checker_policy_hash": target["policy_hash"],
        **{f"locked_{kind}_policy_{field}": context[kind][source_field]
           for kind in ("review", "revision")
           for field, source_field in (("id", "policy_id"), ("generation", "generation"),
                                       ("hash", "policy_hash"))},
    }
    return PublicGuideSource(UUID(project["id"]), UUID(guide["id"]), manager, activation, evidence)
