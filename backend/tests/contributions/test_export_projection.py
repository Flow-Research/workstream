"""Owner-port projection proof; real authority/snapshot proof remains integration work."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.identifiers import new_record_id
from app.modules.actors.api.contribution_labels import ContributionActorLabel
from app.modules.compensation.api.awards import CompensationAwardFacts
from app.modules.compensation.api.instruments import CompensationInstrumentType
from app.modules.contributions.api.records import (
    ContributionExportTooLarge, ContributionExportUnavailable, ContributionReadRequest,
    InvalidContributionCursor,
)
from app.modules.contributions.records.pagination import (
    ContributionExportCursorCodec, contribution_export_query_digest,
)
from app.modules.contributions.records.read_facts import (
    ContributionReadFacts, ContributionReadPage, FrozenContributionAward,
)
from app.modules.contributions.records.read_repository import ContributionReadRepository
from app.modules.contributions.records.read_service import ContributionReadService
from app.modules.contributions.api.source_reads import (
    ContributionAcceptanceSourceFacts, ContributionTaskSourceFacts,
)

TIME = datetime(2026, 10, 10, tzinfo=UTC)


def test_export_cursor_round_trip_tamper_and_query_binding():
    codec = ContributionExportCursorCodec(bytes(range(32)))
    selected = ContributionReadRequest(
        audience="project", actor_profile_id=new_record_id(), project_id=new_record_id(),
        contribution_type="completed_review", recorded_from=TIME - timedelta(days=1),
        recorded_before=TIME + timedelta(days=1), limit=17,
    )
    digest = contribution_export_query_digest(selected)
    snapshot = new_record_id()
    expiry = TIME + timedelta(hours=1)
    cursor = codec.encode(
        query_digest=digest, snapshot_id=snapshot, next_offset=17, expires_at=expiry,
    )
    assert len(cursor) <= 512
    position = codec.decode(cursor, query_digest=digest)
    assert (position.snapshot_id, position.next_offset, position.expires_at) == (
        snapshot, 17, expiry,
    )

    middle = len(cursor) // 2
    tampered = cursor[:middle] + ("A" if cursor[middle] != "A" else "B") + cursor[middle + 1:]
    for invalid, query_digest in (
        ("", digest), ("=", digest), ("x" * 513, digest), (cursor + "=", digest),
        (tampered, digest), (cursor, "sha256:" + "f" * 64),
    ):
        with pytest.raises(InvalidContributionCursor, match="invalid contribution cursor"):
            codec.decode(invalid, query_digest=query_digest)

    for changed in (
        {"actor_profile_id": new_record_id()}, {"project_id": new_record_id()},
        {"output_format": "csv"}, {"contribution_type": "accepted_submission"},
        {"recorded_from": TIME}, {"recorded_before": TIME + timedelta(days=2)},
        {"limit": 18},
    ):
        assert contribution_export_query_digest(selected.model_copy(update=changed)) != digest


@pytest.mark.parametrize("member_count,refused", [(1001, False), (100_001, True)])
async def test_repository_materializes_supported_membership_and_refuses_excess(
    member_count, refused,
):
    member_ids = tuple(new_record_id() for _ in range(member_count))

    class ScalarResult:
        def all(self):
            return member_ids

    class SelectionSession:
        async def scalars(self, statement):
            assert statement._limit_clause.value == 100_001
            return ScalarResult()

    class SelectionRepository(ContributionReadRepository):
        allocated = None

        async def _allocate_snapshot(self, actor_profile_id, digest, selected):
            self.allocated = selected
            return SimpleNamespace(id=new_record_id(), expires_at=TIME + timedelta(hours=1))

        async def _load_records(self, request, ids):
            return ids

    selected = ContributionReadRequest(
        audience="self", actor_profile_id=new_record_id(), limit=1000,
    )
    codec = ContributionExportCursorCodec(bytes(range(32)))
    repository = SelectionRepository(SelectionSession(), cursor_codec=codec, tasks=None)
    digest = contribution_export_query_digest(selected)
    if refused:
        with pytest.raises(ContributionExportTooLarge, match="100000"):
            await repository._first_page(selected, digest)
        assert repository.allocated is None
        return
    page = await repository._first_page(selected, digest)
    assert page.records == member_ids[:1000]
    assert repository.allocated == member_ids
    assert page.next_cursor is not None
    position = codec.decode(page.next_cursor, query_digest=digest)
    assert position.next_offset == 1000


def facts(*, compensated=False):
    project, task, actor, submission, policy, acceptance = (new_record_id() for _ in range(6))
    definition = FrozenContributionAward(id=new_record_id(), instrument="money", unit="USD",
                                          quantity=Decimal("123.456789012345678901"))
    record = ContributionReadFacts(
        id=new_record_id(), project_id=project, task_id=task, submission_id=submission,
        contributor_id=actor, contribution_type="accepted_submission", source_review_id=None,
        source_review_lease_id=None, source_final_acceptance_id=acceptance,
        source_task_assignment_id=new_record_id(), artifact_hash="sha256:" + "a" * 64,
        contribution_policy_version_id=policy, recorded_at=TIME, policy_version_number=1,
        task_size="medium",
        compensation_mode="compensated" if compensated else "unpaid",
        award_definitions=(definition,) if compensated else (),
    )
    awards = () if not compensated else (CompensationAwardFacts(
        id=new_record_id(), project_id=project, contribution_record_id=record.id,
        contributor_id=actor, contribution_policy_version_id=policy,
        award_definition_id=definition.id, adapter_binding_id=new_record_id(),
        instrument_type=CompensationInstrumentType.MONEY, unit_code="USD",
        quantity=definition.quantity, created_at=TIME, correlation_id=new_record_id(),
    ),)
    return SimpleNamespace(
        record=record, awards=awards,
        task=ContributionTaskSourceFacts(project_id=project, task_id=task, submission_id=submission,
                                       task_size="medium", contribution_policy_version_id=policy,
                                       contribution_award_definition_id=definition.id if compensated else None, title="Task",
                                       source_type="manual", source_ref=None, external_task_id=None),
        actor=ContributionActorLabel(actor_profile_id=actor, display_name="Ada"),
        acceptance=ContributionAcceptanceSourceFacts(
            id=acceptance, project_id=project, task_id=task, submission_id=submission,
            acceptance_source="task_post_submit_route", accepted_submitter_id=actor,
            accepted_at=TIME, source_review_id=None, source_routing_manifest_id=new_record_id(),
        ),
    )


class Ports:
    def __init__(self, value):
        self.value, self.authorized = value, False

    async def authorize(self, request):
        self.authorized = True

    async def read(self, request):
        assert self.authorized, "owner load preceded authority"
        return ContributionReadPage((self.value.record,), None)

    async def read_contribution_awards(self, selected):
        assert selected == (self.value.record.id,)
        return self.value.awards

    async def read_contribution_tasks(self, selected):
        assert selected == ((self.value.record.project_id, self.value.record.task_id, self.value.record.submission_id),)
        return (self.value.task,)

    async def read_contribution_labels(self, selected):
        assert selected == (self.value.record.contributor_id,)
        return (self.value.actor,)

    async def read_final_acceptances(self, selected):
        assert selected == ((self.value.record.project_id, self.value.record.source_final_acceptance_id),)
        return (self.value.acceptance,)


def service(ports):
    return ContributionReadService(authorization=ports, records=ports, awards=ports,
                                   acceptances=ports, tasks=ports, actors=ports)


def request(value):
    return ContributionReadRequest(audience="self", actor_profile_id=value.record.contributor_id)


@pytest.mark.parametrize("compensated", [False, True])
async def test_projection_preserves_source_and_exact_unpaid_or_money_set(compensated):
    value = facts(compensated=compensated)
    response = await service(Ports(value)).read(request(value))
    item, = response.items
    assert item.source_final_acceptance_id == value.acceptance.id
    assert item.acceptance_routing_manifest_id == value.acceptance.source_routing_manifest_id
    assert item.accepted_at == value.acceptance.accepted_at
    assert item.recorded_at == value.record.recorded_at
    assert [award.quantity for award in item.awards] == [format(award.quantity, "f") for award in value.awards]
    assert "adapter_binding_id" not in item.model_dump(mode="json")


@pytest.mark.parametrize("field", ["project_id", "contributor_id", "contribution_policy_version_id", "unit_code", "quantity", "award_definition_id"])
async def test_crossed_award_lineage_or_rounded_amount_cannot_be_exported(field):
    value = facts(compensated=True)
    changed = {"unit_code": "EUR", "quantity": Decimal("123.46")}.get(field, new_record_id())
    value.awards = (value.awards[0].model_copy(update={field: changed}),)
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))


async def test_missing_award_or_foreign_contributor_loader_result_is_unavailable():
    value = facts(compensated=True)
    value.awards = ()
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))
    value = facts()
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(ContributionReadRequest(
            audience="self", actor_profile_id=new_record_id(),
        ))


async def test_crossed_source_time_or_task_projection_cannot_change_identity():
    value = facts()
    value.acceptance = value.acceptance.model_copy(update={"submission_id": new_record_id()})
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))
    value = facts()
    value.task = value.task.model_copy(update={"project_id": new_record_id()})
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))


async def test_explicit_over_limit_refusal_is_not_reclassified_as_unavailability():
    value = facts()

    class TooLarge(Ports):
        async def read(self, request):
            assert self.authorized
            raise ContributionExportTooLarge("narrow the filters")

        async def read_contribution_awards(self, selected):
            pytest.fail("over-limit response loaded award data")

    with pytest.raises(ContributionExportTooLarge, match="narrow"):
        await service(TooLarge(value)).read(request(value))


async def test_faulty_over_limit_loader_cannot_start_owner_projections():
    value = facts()

    class OverLimit(Ports):
        async def read(self, request):
            assert self.authorized
            return ContributionReadPage(tuple(
                self.value.record.model_copy(update={"id": new_record_id()})
                for _ in range(1001)
            ), None)

        async def read_contribution_awards(self, selected):
            pytest.fail("over-limit loader started owner projections")

    with pytest.raises(ContributionExportUnavailable):
        await service(OverLimit(value)).read(request(value))


async def test_faulty_partial_page_cannot_publish_a_continuation():
    value = facts()

    class PartialCursor(Ports):
        async def read(self, selected):
            assert self.authorized and selected.limit == 2
            return ContributionReadPage((self.value.record,), "invalid-partial-cursor")

        async def read_contribution_awards(self, selected):
            pytest.fail("partial continuation started owner projections")

    selected = request(value).model_copy(update={"limit": 2})
    with pytest.raises(ContributionExportUnavailable):
        await service(PartialCursor(value)).read(selected)


async def test_1001_canonical_shaped_items_cross_page_boundary_without_owner_expansion():
    """Pure owner-port proof; PostgreSQL source membership is covered separately."""
    base = facts()
    entries = []
    for _ in range(1001):
        identity, task_id, submission_id, acceptance_id = (new_record_id() for _ in range(4))
        record = base.record.model_copy(update={
            "id": identity, "task_id": task_id, "submission_id": submission_id,
            "source_final_acceptance_id": acceptance_id,
        })
        task = base.task.model_copy(update={"task_id": task_id, "submission_id": submission_id})
        acceptance = base.acceptance.model_copy(update={
            "id": acceptance_id, "task_id": task_id, "submission_id": submission_id,
        })
        entries.append((record, task, acceptance))
    entries.sort(key=lambda entry: (entry[0].recorded_at, entry[0].id))

    class PagedPorts(Ports):
        def __init__(self):
            super().__init__(base)
            self.authorizations = 0

        async def authorize(self, selected):
            self.authorizations += 1
            assert selected.actor_profile_id == base.record.contributor_id

        async def read(self, selected):
            assert self.authorizations
            assert selected.limit == 1000
            if selected.cursor is None:
                return ContributionReadPage(tuple(entry[0] for entry in entries[:1000]), "second-page")
            assert selected.cursor == "second-page"
            return ContributionReadPage((entries[1000][0],), None)

        async def read_contribution_awards(self, selected):
            assert len(selected) <= 1000
            return ()

        async def read_contribution_tasks(self, selected):
            assert len(selected) <= 1000
            by_id = {entry[1].task_id: entry[1] for entry in entries}
            return tuple(by_id[task_id] for _, task_id, _ in selected)

        async def read_contribution_labels(self, selected):
            assert selected == (base.record.contributor_id,)
            return (base.actor,)

        async def read_final_acceptances(self, selected):
            assert len(selected) <= 1000
            by_id = {entry[2].id: entry[2] for entry in entries}
            return tuple(by_id[acceptance_id] for _, acceptance_id in selected)

    ports = PagedPorts()
    first = await service(ports).read(ContributionReadRequest(
        audience="self", actor_profile_id=base.record.contributor_id, limit=1000,
    ))
    second = await service(ports).read(ContributionReadRequest(
        audience="self", actor_profile_id=base.record.contributor_id,
        limit=1000, cursor=first.next_cursor,
    ))
    actual = first.items + second.items
    assert len(first.items) == 1000 and len(second.items) == 1
    assert second.next_cursor is None and ports.authorizations == 2
    assert [item.contribution_id for item in actual] == [entry[0].id for entry in entries]
    assert len({item.contribution_id for item in actual}) == 1001
    assert all(item.awards == () for item in actual)


async def test_completed_review_retains_its_source_without_an_acceptance_time():
    value = facts()
    review_id, lease_id = new_record_id(), new_record_id()
    value.record = value.record.model_copy(update={
        "contribution_type": "completed_review", "task_size": None, "source_review_id": review_id,
        "source_review_lease_id": lease_id, "source_final_acceptance_id": None,
        "source_task_assignment_id": None,
    })

    class ReviewPorts(Ports):
        async def read_final_acceptances(self, selected):
            assert selected == ()
            return ()

    response = await service(ReviewPorts(value)).read(request(value))
    item, = response.items
    assert (item.source_review_id, item.source_review_lease_id) == (review_id, lease_id)
    assert item.recorded_at == TIME
    assert item.accepted_at is item.acceptance_source is None
    assert item.acceptance_review_id is item.acceptance_routing_manifest_id is None


@pytest.mark.parametrize("instrument", ["money", "project_points"])
async def test_selected_instrument_retains_original_identity(instrument):
    value = facts(compensated=True)
    if instrument == "project_points":
        definition = FrozenContributionAward(id=new_record_id(), instrument="project_points",
                                              unit="FLOW", quantity=Decimal("12345"))
        value.record = value.record.model_copy(update={"award_definitions": (definition,)})
        value.awards = (value.awards[0].model_copy(update={
            "id": new_record_id(), "award_definition_id": definition.id,
            "instrument_type": CompensationInstrumentType.PROJECT_POINTS,
            "unit_code": "FLOW", "quantity": definition.quantity,
        }),)
        value.task = value.task.model_copy(update={"contribution_award_definition_id": definition.id})
    response = await service(Ports(value)).read(request(value))
    (item,) = response.items
    (stored,) = value.awards
    (award,) = item.awards
    assert (award.award_id,award.award_definition_id,award.quantity) == (
        stored.id,stored.award_definition_id,format(stored.quantity,"f"))


async def test_human_acceptance_review_reference_does_not_replace_contribution_source():
    value = facts()
    review_id = new_record_id()
    value.acceptance = value.acceptance.model_copy(update={
        "acceptance_source": "human_review", "source_review_id": review_id,
        "source_routing_manifest_id": None,
    })
    response = await service(Ports(value)).read(request(value))
    item, = response.items
    assert item.contribution_type == "accepted_submission"
    assert item.acceptance_review_id == review_id
    assert item.source_review_id is item.source_review_lease_id is None
    assert item.source_final_acceptance_id == value.acceptance.id
