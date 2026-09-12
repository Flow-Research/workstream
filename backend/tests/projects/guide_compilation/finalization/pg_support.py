"""Session-bound test authority stages actual evidence with strict replay validation."""

from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.authorization.api import (
    AuthorizationDenied,
    FINALIZATION_ACTION,
    FINALIZATION_PERMISSION,
    FINALIZATION_RESOURCE,
    FINALIZATION_SERVICE,
    PreparedSetupFinalization,
    ProjectSetupFinalizationAuthorityReceipt,
    setup_finalization_authority_digest,
)
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from ..helpers import context, seed_database
from .pg_prerequisites import compilation_and_projections


class DatabasePrepared(PreparedSetupFinalization):
    """Enforce handle lifetime and bind a real stored decision to all final facts."""

    def __init__(self, port):
        self.port = port
        self.session = port.session
        self.root = self.session.get_transaction()
        self.closed = False
        self.used = False

    def require_open(self):
        if (
            self.closed
            or self.used
            or self.session.get_transaction() is not self.root
            or self.session.in_nested_transaction()
        ):
            raise AuthorizationDenied("invalid prepared binding")
        self.used = True

    async def consume_new(self, facts):
        self.require_open()
        if (
            facts.project_id != self.port.locator.project_id
            or facts.operation_id != self.port.locator.operation_id
        ):
            raise AuthorizationDenied("finalization locator mismatch")
        self.port.events.append("consume")
        if self.port.on_consume:
            await self.port.on_consume()
        digest = setup_finalization_authority_digest(facts, self.port.actor, self.port.link)
        decision = uuid4()
        await self.session.execute(
            text(
                "insert into audit_events(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
                "permission_id,action_id,reason,project_id,resource_type,resource_id,after_facts) values"
                "(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',:actor,'[]'::json,'{}'::json,"
                "'local_authority',false,'{}'::json,'authority',1,'actor_profile',:operation,:correlation,:permission,"
                ":action,'authorization_evaluation',:project,:resource,:resource_id,"
                "jsonb_build_object('allowed',true,'resource_context_digest',cast(:digest as text))::json)"
            ),
            dict(
                id=str(decision),
                actor=str(self.port.actor),
                operation=str(facts.operation_id),
                correlation=str(facts.correlation_id),
                permission=FINALIZATION_PERMISSION,
                action=FINALIZATION_ACTION,
                project=str(facts.project_id),
                resource=FINALIZATION_RESOURCE,
                resource_id=str(facts.finalization_id),
                digest=digest,
            ),
        )
        self.port.last_facts = facts
        return ProjectSetupFinalizationAuthorityReceipt(
            decision_event_id=decision,
            actor_profile_id=self.port.actor,
            identity_link_id=self.port.link,
            service_identity=FINALIZATION_SERVICE,
            action_id=FINALIZATION_ACTION,
            permission_id=FINALIZATION_PERMISSION,
            scope_project_id=facts.project_id,
            resource_type=FINALIZATION_RESOURCE,
            resource_id=facts.finalization_id,
            resource_context_digest=digest,
        )

    async def validate_replay(self, facts, stored_decision_id):
        self.require_open()
        if (
            facts.project_id != self.port.locator.project_id
            or facts.operation_id != self.port.locator.operation_id
        ):
            raise AuthorizationDenied("finalization locator mismatch")
        self.port.events.append("replay")
        digest = setup_finalization_authority_digest(facts, self.port.actor, self.port.link)
        event = (
            (
                await self.session.execute(
                    text("select * from audit_events where id=:id"), {"id": str(stored_decision_id)}
                )
            )
            .mappings()
            .one_or_none()
        )
        expected = dict(
            actor_id=str(self.port.actor),
            event_domain="authority",
            event_type="SensitiveAuthorizationAllowed",
            actor_ref_kind="actor_profile",
            action_id=FINALIZATION_ACTION,
            permission_id=FINALIZATION_PERMISSION,
            project_id=str(facts.project_id),
            resource_type=FINALIZATION_RESOURCE,
            resource_id=str(facts.finalization_id),
            request_id=facts.operation_id,
            correlation_id=facts.correlation_id,
            denial_code=None,
        )
        if (
            event is None
            or any(event[key] != value for key, value in expected.items())
            or event["after_facts"] != {"allowed": True, "resource_context_digest": digest}
        ):
            raise AuthorizationDenied("stored evidence mismatch")


class DatabaseAuthorization:
    """Only test-issued authority; never installed in production composition."""

    def __init__(self, session, values, *, events=None, on_consume=None):
        self.session = session
        self.actor, self.link = values["actor"], values["link"]
        self.events = events if events is not None else []
        self.on_consume = on_consume
        self.handles = []
        self.last_facts = None

    @asynccontextmanager
    async def prepare_setup_finalization(self, locator):
        current = await self.session.scalar(
            text(
                "select count(*) from actor_profiles a join actor_identity_links l on l.actor_profile_id=a.id "
                "where a.id=:actor and l.id=:link and a.actor_kind='service' and a.status='active' "
                "and a.service_identity='workstream.project.setup' and l.subject_kind='service' "
                "and l.status='active'"
            ),
            {"actor": str(self.actor), "link": str(self.link)},
        )
        if current != 1:
            raise AuthorizationDenied("current service unavailable")
        self.events.append("prepare")
        self.locator = locator
        handle = DatabasePrepared(self)
        self.handles.append(handle)
        try:
            yield handle
        finally:
            handle.closed = True
            self.events.append("close")


@asynccontextmanager
async def database_case(url, *, classification="draft_ready", project=True, guide_version="v1", outcome=None):
    values = await seed_database(url, guide_version=guide_version)
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        command = await compilation_and_projections(
            url, factory, values, classification=classification, project=project,
            compilation_context=context(values, guide_version=guide_version),
            outcome=outcome
        )
        yield values, factory, command
    finally:
        await engine.dispose()


async def finalize(factory, values, command, *, events=None):
    try:
        async with factory() as session, session.begin():
            authority = DatabaseAuthorization(session, values, events=events)
            return await GuideCompilationFinalizationService(session, authority).finalize(command)
    except ProjectGuideSetupFinalizationError as exc:
        # Preserve public failure semantics while exposing unexpected fixture SQL errors.
        raise exc from exc.__context__


async def stored_state(factory, command):
    async with factory() as session:
        setup = (
            (
                await session.execute(
                    text("select * from project_setup_runs where id=:id"),
                    {"id": str(command.setup_run_id)},
                )
            )
            .mappings()
            .one()
        )
        receipt = (
            (
                await session.execute(
                    text("select * from project_guide_setup_finalizations where setup_run_id=:id"),
                    {"id": str(command.setup_run_id)},
                )
            )
            .mappings()
            .one_or_none()
        )
        evidence = await session.scalar(
            text("select count(*) from audit_events where action_id='project.setup_run.update'")
        )
        return dict(setup), dict(receipt) if receipt else None, evidence
