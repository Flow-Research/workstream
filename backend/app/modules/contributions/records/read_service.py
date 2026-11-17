"""One authorized canonical evidence projection shared by JSON and CSV."""

from datetime import UTC, datetime

from pydantic import ValidationError

from app.modules.actors.api.contribution_labels import (
    ContributionActorLabel, ContributionActorLabelPort,
)
from app.modules.compensation.api.award_reads import ContributionAwardReadPort
from app.modules.compensation.api.awards import CompensationAwardFacts
from app.modules.contributions.api.records import (
    ContributionAwardView, ContributionExportAtCapacity, ContributionExportResponse,
    ContributionExportTooLarge, ContributionExportUnavailable, InvalidContributionCursor,
    ContributionReadAuthorizationPort,
    ContributionReadRequest, ContributionRecordView,
)
from app.core.financial_wire import format_award_quantity
from app.modules.contributions.api.source_reads import (
    ContributionAcceptanceSourceFacts, ContributionAcceptanceSourceReadPort,
    ContributionTaskSourceFacts, ContributionTaskSourceReadPort,
)
from app.modules.contributions.records.read_facts import (
    ContributionReadFacts, ContributionReadRepositoryPort,
)


def _index_exact(rows, key, expected):
    """Require every selected owner identity exactly once, with no extra disclosure."""
    result = {}
    for row in rows:
        identity = key(row)
        if identity in result or identity not in expected:
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        result[identity] = row
    if set(result) != expected:
        raise ContributionExportUnavailable("Contribution evidence unavailable")
    return result


class ContributionReadService:
    """Read existing owners only; the request composition owns snapshot and commit."""

    def __init__(
        self, *, authorization: ContributionReadAuthorizationPort,
        records: ContributionReadRepositoryPort, awards: ContributionAwardReadPort,
        acceptances: ContributionAcceptanceSourceReadPort, tasks: ContributionTaskSourceReadPort,
        actors: ContributionActorLabelPort,
    ) -> None:
        """Require explicit authority and bounded owner ports; no allow fallback exists."""
        self._authorization, self._records, self._awards = authorization, records, awards
        self._acceptances, self._tasks, self._actors = acceptances, tasks, actors

    async def read(self, request: ContributionReadRequest) -> ContributionExportResponse:
        """Authorize before loading any facts and reject incomplete/crossed owner replies."""
        request = ContributionReadRequest.model_validate(request)
        await self._authorization.authorize(request)
        try:
            page = await self._records.read(request)
            records = tuple(ContributionReadFacts.model_validate(row) for row in page.records)
            if len(records) > request.limit or (
                page.next_cursor is not None and len(records) != request.limit
            ):
                raise ContributionExportUnavailable("Contribution evidence unavailable")
            for record in records:
                self._require_selected(record, request)
            record_ids = {record.id for record in records}
            if len(record_ids) != len(records):
                raise ContributionExportUnavailable("Contribution evidence unavailable")
            awards = tuple(CompensationAwardFacts.model_validate(row) for row in
                           await self._awards.read_contribution_awards(tuple(record_ids)))
            by_record = {record_id: [] for record_id in record_ids}
            for award in awards:
                if award.contribution_record_id not in by_record:
                    raise ContributionExportUnavailable("Contribution evidence unavailable")
                by_record[award.contribution_record_id].append(award)
            task_ids = {(record.project_id, record.task_id, record.submission_id) for record in records}
            tasks = _index_exact(
                (ContributionTaskSourceFacts.model_validate(row) for row in
                 await self._tasks.read_contribution_tasks(tuple(task_ids))),
                lambda row: (row.project_id, row.task_id, row.submission_id), task_ids,
            )
            actor_ids = {record.contributor_id for record in records}
            actors = _index_exact(
                (ContributionActorLabel.model_validate(row) for row in
                 await self._actors.read_contribution_labels(tuple(actor_ids))),
                lambda row: row.actor_profile_id, actor_ids,
            )
            acceptance_ids = {(record.project_id, record.source_final_acceptance_id)
                              for record in records if record.source_final_acceptance_id is not None}
            acceptances = _index_exact(
                (ContributionAcceptanceSourceFacts.model_validate(row) for row in
                 await self._acceptances.read_final_acceptances(tuple(acceptance_ids))),
                lambda row: (row.project_id, row.id), acceptance_ids,
            )
            items = tuple(self._view(
                record, by_record[record.id], tasks[(record.project_id, record.task_id, record.submission_id)],
                actors[record.contributor_id],
                acceptances.get((record.project_id, record.source_final_acceptance_id)),
            ) for record in records)
            return ContributionExportResponse(
                exported_at=datetime.now(UTC), items=items, next_cursor=page.next_cursor,
            )
        except (ContributionExportTooLarge, InvalidContributionCursor, ContributionExportAtCapacity):
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContributionExportUnavailable("Contribution evidence unavailable") from exc

    @staticmethod
    def _require_selected(record, request) -> None:
        """A faulty loader cannot expand actor/project/type/time selection."""
        if (
            request.audience == "self" and record.contributor_id != request.actor_profile_id
            or request.project_id is not None and record.project_id != request.project_id
            or request.contribution_type is not None and record.contribution_type != request.contribution_type
            or request.recorded_from is not None and record.recorded_at < request.recorded_from
            or request.recorded_before is not None and record.recorded_at >= request.recorded_before
        ):
            raise ContributionExportUnavailable("Contribution evidence unavailable")

    @staticmethod
    def _view(record, awards, task, actor, acceptance) -> ContributionRecordView:
        """Validate complete frozen economic equality and actual acceptance lineage."""
        if record.contribution_type == "accepted_submission" and (
            record.task_size != task.task_size
            or record.contribution_policy_version_id != task.contribution_policy_version_id
            or {d.id for d in record.award_definitions} != (
                {task.contribution_award_definition_id} if task.contribution_award_definition_id else set()
            )
        ):
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        definitions = {definition.id: definition for definition in record.award_definitions}
        if len(awards) != len(definitions) or {award.award_definition_id for award in awards} != set(definitions):
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        for award in awards:
            definition = definitions[award.award_definition_id]
            if (award.project_id, award.contributor_id, award.contribution_policy_version_id,
                award.instrument_type.value, award.unit_code, award.quantity) != (
                record.project_id, record.contributor_id, record.contribution_policy_version_id,
                definition.instrument, definition.unit, definition.quantity,
            ):
                raise ContributionExportUnavailable("Contribution evidence unavailable")
        if acceptance is not None and (
            acceptance.task_id, acceptance.submission_id, acceptance.accepted_submitter_id
        ) != (record.task_id, record.submission_id, record.contributor_id):
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        return ContributionRecordView(
            contribution_id=record.id, project_id=record.project_id, task_id=record.task_id,
            submission_id=record.submission_id, task_size=record.task_size, contributor_id=record.contributor_id,
            contributor_display_name=actor.display_name, contribution_type=record.contribution_type,
            source_review_id=record.source_review_id, source_review_lease_id=record.source_review_lease_id,
            source_final_acceptance_id=record.source_final_acceptance_id,
            source_task_assignment_id=record.source_task_assignment_id,
            artifact_hash=record.artifact_hash,
            contribution_policy_version_id=record.contribution_policy_version_id,
            policy_version_number=record.policy_version_number, recorded_at=record.recorded_at,
            accepted_at=None if acceptance is None else acceptance.accepted_at,
            acceptance_source=None if acceptance is None else acceptance.acceptance_source,
            acceptance_review_id=None if acceptance is None else acceptance.source_review_id,
            acceptance_routing_manifest_id=(None if acceptance is None
                                            else acceptance.source_routing_manifest_id),
            task_title=task.title, source_type=task.source_type, source_ref=task.source_ref,
            external_task_id=task.external_task_id,
            awards=tuple(ContributionAwardView(
                award_id=award.id, award_definition_id=award.award_definition_id,
                instrument=award.instrument_type.value, unit=award.unit_code,
                quantity=format_award_quantity(award.quantity),
            ) for award in sorted(awards, key=lambda row: row.instrument_type.value)),
        )
