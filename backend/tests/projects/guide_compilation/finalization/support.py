"""Strict service fixtures; database and authorization effects remain observable."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.modules.authorization.api import (
    AuthorizationDenied,
    FINALIZATION_ACTION,
    FINALIZATION_PERMISSION,
    FINALIZATION_RESOURCE,
    FINALIZATION_SERVICE,
    PreparedSetupFinalization,
    ProjectSetupFinalizationAuthorityReceipt,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_identity,
    setup_finalization_authority_digest,
)
from app.modules.projects.api import ProjectGuideSetupFinalizationCommand
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from app.modules.projects.guide_compilation.custody_payloads import policy_digest, report_digest
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from app.modules.projects.guide_compilation.finalization_payloads import (
    LockedFinalization,
    compose_facts,
    diagnostic_step,
    require_source_shape,
)
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from ..helpers import result

NOW = datetime(2026, 9, 7, tzinfo=UTC)


def source_view(classification="draft_ready"):
    """Build one complete valid view with an independently observed effect recorder."""
    project, guide, snapshot, setup, attempt, compilation, actor, link, request = [
        uuid4() for _ in range(9)
    ]
    outcome = result()
    if classification == "guide_blocked":
        outcome = outcome.model_copy(
            update={
                "status": classification,
                "findings": (outcome.findings[0].model_copy(update={"severity": "blocking_gap"}),),
                "submission_artifact_policy": None,
                "requirements": (),
                "pre_submit_bindings": (),
                "post_submit_bindings": (),
                "capability_suggestions": (),
            }
        )
    elif classification == "draft_ready_with_warnings":
        outcome = outcome.model_copy(
            update={
                "status": classification,
                "findings": (outcome.findings[0].model_copy(update={"severity": "warning"}),),
            }
        )
    accepted = accepted_compilation_result(outcome)
    lineage = dict(
        project_id=str(project),
        guide_id=str(guide),
        guide_version="v1",
        source_snapshot_id=str(snapshot),
        source_snapshot_hash="sha256:" + "a" * 64,
        setup_run_id=str(setup),
        setup_generation=1,
    )
    c = SimpleNamespace(
        **lineage,
        id=compilation,
        attempt_id=attempt,
        canonical_input_hash="sha256:" + "b" * 64,
        result_hash=accepted.result_hash,
        canonical_result=accepted.canonical_result,
        component_hashes=accepted.component_hashes.model_dump(),
    )
    a = SimpleNamespace(
        **lineage,
        id=attempt,
        status="compilation_persisted",
        persisted_compilation_id=compilation,
        canonical_input_hash=c.canonical_input_hash,
        provider_idempotency_key=uuid4(),
        guide_material_hash="sha256:" + "c" * 64,
    )
    q = SimpleNamespace(**lineage, attempt_id=attempt, operation_id=request)
    g = SimpleNamespace(id=str(guide), project_id=str(project), version="v1", status="draft")
    snap = SimpleNamespace(
        id=str(snapshot),
        project_id=str(project),
        guide_id=str(guide),
        guide_version="v1",
        bundle_hash=lineage["source_snapshot_hash"],
    )
    state = {column.name: None for column in ProjectSetupRun.__table__.columns}
    state.update({key: value for key, value in lineage.items() if key != "setup_run_id"})
    state.update(
        id=str(setup),
        status="queued",
        current_step="queued",
        created_by="fixture",
        created_at=NOW,
        updated_at=NOW,
        documents_ready_at=NOW,
        celery_task_id=project_guide_compilation_task_id(str(setup), 1),
    )
    s = SimpleNamespace(**state)
    empty = LockedFinalization(a, q, g, snap, s, c, True, (), None, None)
    return projected_view(empty, lineage, outcome, actor, link)


def projected_view(empty, lineage, outcome, actor, link):
    """Build existing output custody around the independently prepared source view."""
    c, a, s = empty.compilation, empty.attempt, empty.setup
    classification = outcome.status
    attempt, compilation, request = a.id, c.id, empty.request.operation_id
    setup = UUID(s.id)
    digest = require_source_shape(empty)
    operations = []
    for component, factory in (
        ("guide_sufficiency", guide_sufficiency_projection_identity),
        ("submission_artifact_policy", artifact_policy_projection_identity),
    ):
        identity = factory(attempt_id=attempt, actor_profile_id=actor, identity_link_id=link)
        operations.append(
            SimpleNamespace(
                **lineage,
                component=component,
                operation_id=identity.operation_id,
                correlation_id=identity.correlation_id,
                output_id=identity.output_id,
                actor_profile_id=str(actor),
                identity_link_id=str(link),
                compilation_id=compilation,
                attempt_id=attempt,
                request_operation_id=request,
                provider_idempotency_key=a.provider_idempotency_key,
                celery_task_id=s.celery_task_id,
                source_state_digest=digest,
                result_hash=c.result_hash,
                result_schema_version=outcome.schema_version,
                compilation_agent_name=outcome.agent_name,
                compilation_agent_version=outcome.agent_version,
                component_hash=c.component_hashes[
                    "sufficiency_hash"
                    if component == "guide_sufficiency"
                    else "artifact_policy_hash"
                ],
            )
        )
    sufficient, policy = operations
    output_lineage = {
        key: value
        for key, value in lineage.items()
        if key not in {"setup_run_id", "setup_generation"}
    }
    report = SimpleNamespace(
        **output_lineage,
        id=str(sufficient.output_id),
        status={
            "draft_ready": "passed",
            "guide_blocked": "blocked",
            "draft_ready_with_warnings": "passed_with_warnings",
        }[classification],
        findings=[x.model_dump(mode="json") for x in outcome.findings],
        summary=None,
        agent_name="ProjectGuideCompilationProjection",
        agent_version="v1",
        project_setup_run_id=str(setup),
        setup_generation=1,
        agent_material_sha256=a.guide_material_hash,
        agent_material_byte_count=20,
        created_by=str(actor),
    )
    sufficient.report_id = report.id
    sufficient.policy_id = sufficient.prior_operation_id = sufficient.prior_output_id = (
        sufficient.prior_output_digest
    ) = None
    sufficient.output_digest = report_digest(report)
    policy_row = SimpleNamespace(
        **output_lineage,
        id=str(policy.output_id),
        lifecycle_status="draft",
        policy_version="unified-fixture",
        policy_body={"required_artifacts": []},
        policy_hash="sha256:" + "d" * 64,
        derivation_source="unified_compilation",
        source_material_refs=[],
        derivation_agent_name=report.agent_name,
        derivation_agent_version="v1",
        created_by=str(actor),
        change_summary=None,
    )
    policy.policy_id = policy_row.id
    policy.report_id = None
    policy.prior_operation_id = sufficient.operation_id
    policy.prior_output_id = sufficient.output_id
    policy.prior_output_digest = sufficient.output_digest
    policy.output_digest = policy_digest(policy_row)
    return replace(
        empty,
        operations=tuple(operations[:1] if classification == "guide_blocked" else operations),
        report=report,
        policy=None if classification == "guide_blocked" else policy_row,
    )


class Session:
    """Minimal root-transaction identity with no implicit commit or pending writes."""

    def __init__(self):
        self.active = True
        self.nested = False
        self.new = set()
        self.dirty = set()
        self.deleted = set()
        self.root = object()
        self.commits = 0

    def in_transaction(self):
        return self.active

    def in_nested_transaction(self):
        return self.nested


class Repository:
    """Record service calls; database persistence has separate PostgreSQL proof."""

    def __init__(self, view):
        self.view = view
        self.rows = ()
        self.calls = []
        self.failure = None
        self.after_lock = None

    async def finalization_attempt_id(self, command):
        self.calls.append("lookup")
        return self.view.attempt.id

    async def lock_finalization(self, *_args):
        self.calls.append("lock")
        if self.failure:
            raise self.failure
        if self.after_lock:
            self.after_lock()
        return self.view

    async def finalization_receipts(self, *_args):
        self.calls.append("receipts")
        return self.rows

    async def persist_finalization(self, row, setup):
        self.calls.append("persist")
        row.created_at = NOW
        self.rows = (row,)
        setup.status = row.setup_outcome
        setup.current_step = diagnostic_step(row.setup_outcome)
        setup.output_sufficiency_report_id = row.sufficiency_report_id
        setup.output_submission_artifact_policy_id = row.artifact_policy_id
        setup.finished_at = NOW


class Prepared(PreparedSetupFinalization):
    """Strict fake with single use, root/session binding, and complete expected facts."""

    def __init__(self, port):
        self.port = port
        self.root = port.session.root
        self.closed = False
        self.used = False

    def require_open(self):
        if (
            self.closed
            or self.used
            or not self.port.session.active
            or self.port.session.root is not self.root
        ):
            raise AuthorizationDenied("prepared binding invalid")

    async def consume_new(self, facts):
        self.require_open()
        self.used = True
        self.port.events.append("consume")
        self.port.observed_product_calls = tuple(self.port.repository.calls)
        if self.port.consume_error:
            raise self.port.consume_error
        if facts != self.port.expected:
            raise AuthorizationDenied("exact facts mismatch")
        receipt = ProjectSetupFinalizationAuthorityReceipt(
            decision_event_id=self.port.decision,
            actor_profile_id=self.port.actor,
            identity_link_id=self.port.link,
            service_identity=FINALIZATION_SERVICE,
            action_id=FINALIZATION_ACTION,
            permission_id=FINALIZATION_PERMISSION,
            scope_project_id=facts.project_id,
            resource_type=FINALIZATION_RESOURCE,
            resource_id=facts.finalization_id,
            resource_context_digest=setup_finalization_authority_digest(
                facts, self.port.actor, self.port.link
            ),
        )
        return self.port.receipt_transform(receipt) if self.port.receipt_transform else receipt

    async def validate_replay(self, facts, stored_decision_id):
        self.require_open()
        self.used = True
        self.port.events.append("replay")
        if self.port.replay_error:
            raise self.port.replay_error
        if facts != self.port.expected or stored_decision_id != self.port.decision:
            raise AuthorizationDenied("stored authority facts mismatch")


class Authorization:
    """Own prepared lifecycle in finally, including close failures."""

    def __init__(self, session, repository):
        self.session = session
        self.repository = repository
        self.expected = compose_facts(repository.view, require_source_shape(repository.view))
        self.actor, self.link, self.decision = uuid4(), uuid4(), uuid4()
        self.events = []
        self.handles = []
        self.consume_error = self.replay_error = self.close_error = None
        self.receipt_transform = None
        self.observed_product_calls = ()

    @asynccontextmanager
    async def prepare_setup_finalization(self, locator):
        if (
            locator.project_id != self.expected.project_id
            or locator.operation_id != self.expected.operation_id
        ):
            raise AuthorizationDenied("wrong locator")
        self.events.append("prepare")
        handle = Prepared(self)
        self.handles.append(handle)
        try:
            yield handle
        finally:
            handle.closed = True
            self.events.append("close")
            if self.close_error:
                raise self.close_error


def scenario(classification="draft_ready"):
    """Wire a real finalizer to explicit transaction, repository and AUTH seams."""
    view = source_view(classification)
    session = Session()
    repo = Repository(view)
    auth = Authorization(session, repo)
    service = GuideCompilationFinalizationService(session, auth)
    service._repository = repo
    command = ProjectGuideSetupFinalizationCommand(
        project_id=UUID(view.guide.project_id),
        guide_id=UUID(view.guide.id),
        setup_run_id=UUID(view.setup.id),
        setup_generation=1,
        compilation_id=view.compilation.id,
    )
    return SimpleNamespace(
        view=view, session=session, repo=repo, auth=auth, service=service, command=command
    )
