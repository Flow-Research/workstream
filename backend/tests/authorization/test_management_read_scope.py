"""Closed project-wide read evaluator and adapter proof; PostgreSQL custody is separate."""

import base64
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.core.identifiers import new_record_id
from app.modules.authorization.api.management_reads import (
    ProjectManagementReadCursorInvalid, ProjectManagementReadPosition, ProjectManagementReadRequest,
    ProjectManagementReadUnavailable,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID, PROJECT_GUIDE_READ_ACTIONS, PROJECT_MANAGEMENT_READ_ACTIONS, PROJECT_WORK_READ_ACTIONS,
    ActionId, PermissionId,
)
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.domain.management_reads import (
    MANAGEMENT_RESOURCE_BY_ACTION, ProjectManagementReadResourceContext, management_read_denial,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.management_read import ProjectManagementReadAuthorization
from app.modules.authorization.policy import permissions_for
from app.modules.authorization.schemas import AdminRole
from tests.authorization.test_contribution_read_scope import Grants as ContributionGrants, principal

SECRET = SecretStr(base64.b64encode(bytes(range(32))).decode())


class Grants(ContributionGrants):
    """Stored grants as ``(role, scope)`` pairs; scope is the project, ``system`` or ``foreign``."""

    def __init__(self, context, *grants):
        super().__init__(context)
        self.grants = grants
        self.finance_grant_id = new_record_id()

    async def find_effective_grant(self, actor_id, permission, **filters):
        assert actor_id == self.context.actor_profile_id and filters["for_update"] is True
        exact = filters.get("exact_project_scope", False)
        self.calls.append((permission, filters["allowed_roles"], exact))
        for role, scope in self.grants:
            if (role in filters["allowed_roles"] and permission in permissions_for(role)
                    and (scope == filters["scope_project_id"] or scope == "system" and not exact)):
                grant_id = self.finance_grant_id if exact else self.grant_id
                return type("Grant", (), {"id": str(grant_id)})()
        return None

    async def lock_project(self, project_id):
        assert project_id == self.project_id
        self.calls.append("project")
        return type("Project", (), {"id": str(project_id), "status": "archived"})()


def resource_for(repository, action, **changes):
    member = action in {ActionId.PROJECT_GUIDE_READ, ActionId.PROJECT_GUIDE_ACTIVATION_READINESS_READ,
                        ActionId.PROJECT_GUIDE_DOCUMENT_READ}
    values = dict(
        resource_type=MANAGEMENT_RESOURCE_BY_ACTION[action],
        resource_id=new_record_id() if member else repository.project_id,
        scope_project_id=repository.project_id, actor_profile_id=repository.context.actor_profile_id,
        request_digest="sha256:" + "a" * 64,
    ) | changes
    return ProjectManagementReadResourceContext(**values)


async def evaluate(repository, action, resource=None):
    return await management_read_denial(
        ACTION_BY_ID[action], resource or resource_for(repository, action), repository.context, repository,
        AuthorizationService._locked_human_context, AuthorizationService._lifecycle_denial,
    )


def test_actions_map_to_their_documented_permissions_and_resources():
    assert len(PROJECT_MANAGEMENT_READ_ACTIONS) == len(MANAGEMENT_RESOURCE_BY_ACTION) == 10
    assert set(MANAGEMENT_RESOURCE_BY_ACTION) == PROJECT_MANAGEMENT_READ_ACTIONS
    assert {ACTION_BY_ID[a].permission_id for a in PROJECT_GUIDE_READ_ACTIONS} == {PermissionId.PROJECT_GUIDE_MANAGE}
    assert {ACTION_BY_ID[a].permission_id for a in PROJECT_WORK_READ_ACTIONS} == {PermissionId.PROJECT_TASK_MANAGE}
    assert ACTION_BY_ID[ActionId.CONTRIBUTION_POLICY_LIST].permission_id is PermissionId.COMPENSATION_POLICY_MANAGE


MANAGER_ACTIONS = sorted(PROJECT_GUIDE_READ_ACTIONS | PROJECT_WORK_READ_ACTIONS)


@pytest.mark.parametrize("action", sorted(PROJECT_MANAGEMENT_READ_ACTIONS))
@pytest.mark.parametrize("role,scope", [
    (AdminRole.PROJECT_MANAGER, "system"), (AdminRole.PROJECT_MANAGER, "project"),
    (AdminRole.PROJECT_MANAGER, "foreign"), (AdminRole.FINANCE_AUTHORITY, "system"),
    (AdminRole.FINANCE_AUTHORITY, "project"), (AdminRole.FINANCE_AUTHORITY, "foreign"),
    (AdminRole.OPERATOR, "system"), (AdminRole.AUDIT_AUTHORITY, "project"),
    (AdminRole.ACCESS_ADMINISTRATOR, "system"),
])
async def test_only_a_covering_manager_or_finance_grant_allows(action, role, scope):
    repository = Grants(principal())
    repository.grants = ((role, repository.project_id if scope == "project" else scope),)
    expected_role = (AdminRole.FINANCE_AUTHORITY if action is ActionId.CONTRIBUTION_POLICY_LIST
                     else AdminRole.PROJECT_MANAGER)
    allowed = role is expected_role and scope != "foreign"
    result = await evaluate(repository, action)
    assert repository.calls[0] == "actor"
    assert repository.calls[1] == (ACTION_BY_ID[action].permission_id, frozenset({expected_role}), False)
    if allowed:
        assert result[0] is None
        assert result[2:5] == (MatchedAuthorityKind.ADMIN_ROLE_GRANT, repository.grant_id, repository.project_id)
        assert repository.calls[-1] == "project"
    else:
        assert result[0] is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        assert "project" not in repository.calls


async def test_contributor_or_no_grant_and_inactive_actor_are_denied():
    repository = Grants(principal())
    result = await evaluate(repository, ActionId.PROJECT_SUBMISSION_LIST)
    assert result[0] is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))
    repository.suspended = True
    result = await evaluate(repository, ActionId.PROJECT_SUMMARY_READ)
    assert result[0] is AuthorizationDenialCode.ACTOR_SUSPENDED
    assert repository.calls == ["actor"]


async def test_missing_project_after_a_system_grant_is_not_found():
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))

    async def absent(project_id):
        repository.calls.append("project")

    repository.lock_project = absent
    result = await evaluate(repository, ActionId.PROJECT_GUIDE_LIST)
    assert result[0] is AuthorizationDenialCode.RESOURCE_NOT_FOUND


async def test_mismatched_resource_actor_or_project_is_refused_before_authority_queries():
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))
    action = ActionId.PROJECT_SUBMISSION_LIST
    for resource in (
        resource_for(repository, action, actor_profile_id=new_record_id()),
        resource_for(repository, action, resource_type="project_guide_collection"),
        resource_for(repository, ActionId.PROJECT_GUIDE_READ),
    ):
        result = await evaluate(repository, action, resource)
        assert result[0] is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    assert repository.calls == []
    with pytest.raises(ValueError, match="differs from its project"):
        resource_for(repository, action, resource_id=new_record_id())


class Kernel:
    def __init__(self, repository):
        self.repository, self.required = repository, []

    async def require(self, action, resource):
        result = await management_read_denial(
            ACTION_BY_ID[action], resource, self.repository.context, self.repository,
            AuthorizationService._locked_human_context, AuthorizationService._lifecycle_denial,
        )
        self.required.append((action, resource, result[0]))
        if result[0] is not None:
            raise PermissionError(result[0])
        # The kernel digests the resource the evaluator returns.
        self.recorded = result[6]
        return SimpleNamespace(resource_context_digest=authorization_resource_digest(result[6]))


def request_for(repository, action, *, query=(), cursor=None):
    return ProjectManagementReadRequest(
        action=action.value, actor_profile_id=repository.context.actor_profile_id,
        project_id=repository.project_id, resource_id=repository.project_id, query=query,
        presented_cursor=cursor,
    )


@pytest.mark.parametrize("finance,visible", [(None, False), ("system", False), ("project", True)])
async def test_award_totals_need_an_exact_project_finance_grant(finance, visible):
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))
    if finance is not None:
        repository.grants += ((AdminRole.FINANCE_AUTHORITY,
                               repository.project_id if finance == "project" else finance),)
    kernel = Kernel(repository)
    adapter = ProjectManagementReadAuthorization(kernel, None)
    grant = await adapter.authorize(request_for(repository, ActionId.PROJECT_SUMMARY_READ))
    assert grant.project_id == repository.project_id and grant.position is None
    assert grant.award_totals_visible is visible
    # The evaluator locks actor, the Project Manager grant, the exact-project
    # Finance grant, then Project, and records the Finance grant it disclosed.
    assert repository.calls == [
        "actor", (PermissionId.PROJECT_TASK_MANAGE, frozenset({AdminRole.PROJECT_MANAGER}), False),
        (PermissionId.COMPENSATION_AWARD_READ, frozenset({AdminRole.FINANCE_AUTHORITY}), True), "project",
    ]
    assert kernel.recorded.award_totals_grant_id == (repository.finance_grant_id if visible else None)


async def test_the_recorded_summary_decision_differs_when_totals_are_disclosed():
    digests = {}
    for finance in (None, "project"):
        repository = Grants(principal())
        repository.grants = ((AdminRole.PROJECT_MANAGER, repository.project_id),)
        if finance:
            repository.grants += ((AdminRole.FINANCE_AUTHORITY, repository.project_id),)
        resource = resource_for(repository, ActionId.PROJECT_SUMMARY_READ)
        result = await evaluate(repository, ActionId.PROJECT_SUMMARY_READ, resource)
        assert result[0] is None and result[3] == repository.grant_id
        digests[finance] = (authorization_resource_digest(resource), authorization_resource_digest(result[6]))
    withheld_sent, withheld_recorded = digests[None]
    disclosed_sent, disclosed_recorded = digests["project"]
    assert withheld_recorded == withheld_sent
    assert disclosed_recorded != disclosed_sent


async def test_a_caller_cannot_claim_an_award_disclosure():
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))
    resource = resource_for(repository, ActionId.PROJECT_SUMMARY_READ, award_totals_grant_id=new_record_id())
    result = await evaluate(repository, ActionId.PROJECT_SUMMARY_READ, resource)
    assert result[0] is AuthorizationDenialCode.RESOURCE_GUARD_DENIED and repository.calls == []
    with pytest.raises(ValueError, match="only the project summary"):
        resource_for(repository, ActionId.PROJECT_SUBMISSION_LIST, award_totals_grant_id=new_record_id())


async def test_other_reads_never_disclose_award_totals():
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"),
                        (AdminRole.FINANCE_AUTHORITY, "system"))
    repository.grants += ((AdminRole.FINANCE_AUTHORITY, repository.project_id),)
    kernel = Kernel(repository)
    adapter = ProjectManagementReadAuthorization(kernel, SECRET)
    grant = await adapter.authorize(request_for(repository, ActionId.PROJECT_ASSIGNMENT_LIST))
    assert grant.award_totals_visible is False and kernel.recorded.award_totals_grant_id is None
    assert all(call[0] is not PermissionId.COMPENSATION_AWARD_READ for call in repository.calls[1:-1])


async def test_cursor_is_bound_to_the_exact_query_and_checked_after_authority():
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))
    kernel = Kernel(repository)
    adapter = ProjectManagementReadAuthorization(kernel, SECRET)
    action = ActionId.PROJECT_SUBMISSION_LIST
    position = ProjectManagementReadPosition(datetime(2026, 1, 1, tzinfo=UTC), new_record_id())
    cursor = adapter.encode(request_for(repository, action, query=(("status", "accepted"),)), position)
    grant = await adapter.authorize(request_for(repository, action, query=(("status", "accepted"),), cursor=cursor))
    assert grant.position == position
    with pytest.raises(ProjectManagementReadCursorInvalid):
        await adapter.authorize(request_for(repository, action, query=(("status", "rejected"),), cursor=cursor))
    assert kernel.required[-1][2] is None
    digests = {resource.request_digest for _, resource, _ in kernel.required}
    assert len(digests) == 2


async def test_paged_reads_need_the_cursor_secret_before_any_decision():
    repository = Grants(principal(), (AdminRole.PROJECT_MANAGER, "system"))
    kernel = Kernel(repository)
    adapter = ProjectManagementReadAuthorization(kernel, None)
    with pytest.raises(ProjectManagementReadUnavailable):
        await adapter.authorize(request_for(repository, ActionId.PROJECT_GUIDE_LIST))
    assert kernel.required == []


def test_unpaged_reads_reject_a_cursor_and_requests_stay_canonical():
    repository = Grants(principal())
    with pytest.raises(ValueError):
        request_for(repository, ActionId.PROJECT_SUMMARY_READ, cursor="abc")
    with pytest.raises(ValueError):
        request_for(repository, ActionId.PROJECT_SUBMISSION_LIST, query=(("status", "a"), ("status", "b")))
    with pytest.raises(ValueError):
        ProjectManagementReadRequest(
            action="project.read", actor_profile_id=repository.context.actor_profile_id,
            project_id=repository.project_id, resource_id=repository.project_id, query=(),
        )
