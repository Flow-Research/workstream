"""Thin command invocation and capture of successful replay fixture facts."""

from types import SimpleNamespace

from app.modules.projects.schemas import (
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyReportCreate,
)
from projects.sufficiency_mutations import rows


def create_payload():
    return GuideSufficiencyReportCreate(
        source_snapshot_id=str(rows.SNAPSHOT),
        status="passed",
        findings=[],
        summary="Assessment",
    )


async def invoke(case, command):
    args = (case.resolved, case.prepared, rows.KEY, rows.PROJECT, rows.GUIDE)
    if command == "create":
        return await case.service.create_report(*args, create_payload())
    if command == "ack":
        return await case.service.acknowledge_warnings(
            *args,
            rows.REPORT,
            GuideSufficiencyAcknowledgement(acknowledgement_note="Understood"),
        )
    raise ValueError(command)


async def seed_replay(case, command):
    outcome = await invoke(case, command)
    values = dict(case.replay.reserve.await_args.kwargs)
    values["report_id"] = case.replay.complete.await_args.kwargs["report_id"]
    record = SimpleNamespace(
        **values,
        status="committed",
        response_json=outcome.response.model_dump(mode="json"),
    )
    case.replay.find.return_value = record
    for port in (case.replay, case.projects, case.prepared):
        for value in vars(port).values():
            value.reset_mock()
    return record
