"""Formula-safe UTF-8 CSV over the same complete evidence view as JSON."""

import csv
from datetime import UTC, datetime
from io import StringIO

from app.modules.contributions.api.records import ContributionExportResponse

CSV_COLUMNS = (
    "contribution_id", "award_id", "project_id", "task_id", "task_size", "external_task_id",
    "source_type", "source_ref", "task_title", "submission_id", "contributor_id",
    "contributor_display_name", "contribution_type", "recorded_at", "accepted_at",
    "acceptance_source", "acceptance_review_id", "acceptance_routing_manifest_id",
    "source_final_acceptance_id", "source_review_id",
    "source_review_lease_id", "source_task_assignment_id", "artifact_hash",
    "contribution_policy_version_id", "policy_version_number", "award_definition_id",
    "instrument", "unit", "quantity",
)
_UNTRUSTED_COLUMNS = frozenset({
    "external_task_id", "source_type", "source_ref", "task_title",
    "contributor_display_name", "unit",
})


def formula_safe_text(value: str) -> str:
    """Prefix formula-like text, including whitespace-prefixed spreadsheet triggers."""
    candidate = value.lstrip()
    if value.startswith(("\t", "\r", "\n")) or candidate.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")):
        return "'" + value
    return value


def _cell(value: object) -> str:
    """Serialize immutable identities and UTC times without numeric conversion."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return str(value)


def contribution_csv(response: ContributionExportResponse) -> bytes:
    """Flatten contribution/award identities and keep a row for an empty award set."""
    response = ContributionExportResponse.model_validate(response)
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for item in response.items:
        record = item.model_dump(exclude={"awards"})
        for award in item.awards or (None,):
            row = record | ({} if award is None else award.model_dump())
            cells = {column: _cell(row.get(column)) for column in CSV_COLUMNS}
            for column in _UNTRUSTED_COLUMNS:
                cells[column] = formula_safe_text(cells[column])
            writer.writerow(cells)
    return stream.getvalue().encode("utf-8")
