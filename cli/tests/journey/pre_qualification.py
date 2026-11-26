"""Exact source-first PRE fault/isolation evidence for the maintained CLI journey."""

import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

INFRASTRUCTURE_FAILURE = "submission_infrastructure_unavailable"
WRAPPER = (
    Path(__file__).resolve().parents[3]
    / "external_checkers/workstream-checker-service/tests/smol_fixture/runtime_wrapper.py"
)


async def _terminal(
    environment, operation_id, task_id, assignment_id, archive, *, timeout
):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.modules.checkers.api.selected_pre_submit import (
        SelectedPreSubmitTerminalFacts,
    )
    from run_isolated_tests import _minio_client
    from runtime import PRE_QUALIFICATION_DEADLINE_MS
    from source_audit import _COUNTS

    url = environment["WORKSTREAM_DATABASE_URL"]
    assert urlsplit(url).path.lstrip("/").startswith("workstream_test_")
    parameters = {"operation_id": operation_id, "task_id": task_id}
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            row = (
                (
                    await connection.execute(
                        text("""
                    SELECT o.state, o.task_id::text, o.assignment_id::text,
                        o.object_ref, o.raw_sha256, o.raw_byte_count,
                        o.provider_generation, o.sealed_upload_fence,
                        o.finalization_event_id, charge.state AS charge_state,
                        charge.accounted_bytes, selected.terminal_json,
                        selected.terminal_digest, selected.eligible,
                        selected.execute_evidence_id, selected.finalize_evidence_id
                    FROM submission_intake_operations AS o
                    JOIN submission_source_charges AS charge ON charge.operation_id = o.id
                    JOIN selected_pre_submit_runs AS selected ON selected.source_operation_id = o.id
                    WHERE o.id = CAST(:operation_id AS uuid)
                    """),
                        parameters,
                    )
                )
                .mappings()
                .one()
            )
            if timeout:
                for query in _COUNTS.values():
                    assert await connection.scalar(text(query), parameters) == 0
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM task_revision_preparations WHERE task_id = CAST(:task_id AS uuid)"
                        ),
                        parameters,
                    )
                    == 0
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM submission_intake_operations WHERE task_id = CAST(:task_id AS uuid)"
                        ),
                        parameters,
                    )
                    == 1
                )
    finally:
        await engine.dispose()

    data = archive.read_bytes()
    raw_digest = "sha256:" + sha256(data).hexdigest()
    assert (row["task_id"], row["assignment_id"]) == (task_id, assignment_id)
    assert (row["raw_sha256"], row["raw_byte_count"]) == (raw_digest, len(data))
    assert (row["charge_state"], row["accounted_bytes"]) == ("sealed", len(data))
    assert row["execute_evidence_id"] and row["finalize_evidence_id"]
    terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(
        row["terminal_json"], source_contracts=selected_pre_submit_source_contracts()
    )
    assert terminal.terminal_digest == row["terminal_digest"]
    reservation = terminal.lease.reservation
    source = reservation.source
    invocation = terminal.invocation_receipt
    assert invocation and invocation.operation == "execute_pre"
    assert invocation.runtime.provider == "smolvm"
    assert invocation.cleanup.disposition == "destroyed"
    assert str(source.location.operation_id) == operation_id
    assert str(reservation.assignment_id) == assignment_id
    assert source.location.object_ref == row["object_ref"]
    assert source.raw_sha256 == raw_digest and source.raw_byte_count == len(data)
    assert source.provider_generation == row["provider_generation"]
    assert source.sealed_upload_fence == row["sealed_upload_fence"]
    assert (
        invocation.invocation.image_digest
        == environment["WORKSTREAM_CLI_JOURNEY_PRE_QUALIFICATION_IMAGE_DIGEST"]
    )
    assert (
        reservation.policy.entries[0].registry.resources.deadline_ms
        == PRE_QUALIFICATION_DEADLINE_MS
    )
    if timeout:
        assert row["state"] == "failed" and row["finalization_event_id"] is None
        assert row["eligible"] is None and terminal.execution is None
        assert terminal.outcome == "infrastructure_failed"
        assert terminal.infrastructure_failure_code == "implementation_unavailable"
        assert invocation.outcome == "infrastructure_failure"
        assert invocation.timings_ms.execution >= PRE_QUALIFICATION_DEADLINE_MS
        # The real source remains charged during the configured reclamation grace.
        async with _minio_client(
            environment["WORKSTREAM_TEST_MINIO_ENDPOINT"]
        ) as client:
            observed = await client.head_object(
                Bucket=environment["WORKSTREAM_TEST_MINIO_BUCKET"],
                Key=f"{environment['WORKSTREAM_TEST_MINIO_PREFIX']}/{row['object_ref']}",
                VersionId=source.provider_generation,
            )
        assert observed["VersionId"] == source.provider_generation
        assert observed["ContentLength"] == len(data)
    else:
        assert row["state"] == "finalized" and row["finalization_event_id"]
        assert terminal.outcome == "completed" and invocation.outcome == "completed"
        assert terminal.execution and terminal.execution.eligible
        assert row["eligible"] is True
        assert len(terminal.execution.external_members) == 1
        assert terminal.execution.external_members[0].result.verdict == "passed"

    return {
        "source_operation_id": operation_id,
        "raw_sha256": raw_digest,
        "terminal_sha256": row["terminal_digest"],
        "invocation": invocation.canonical_body(),
    }


def qualify(client, token, task_id, assignment_id, environment):
    """Exercise a real selected timeout and one successful source fence probe."""
    from source_audit import audit_accepted_source
    from submission_work import (
        _assignment_status,
        _command,
        _package,
        _progress,
        _submit,
        _wait_for_stage,
    )

    if not __debug__:
        raise RuntimeError("PRE qualification requires Python assertions")
    if client.evidence is None:
        raise RuntimeError(
            "PRE qualification requires a private journey evidence directory"
        )
    good = _package(client, "correct")
    timed = client.directory / "qualification-timeout.zip"
    timed.write_bytes(good.read_bytes())
    marker = ZipInfo("pre-qualification-timeout.txt", date_time=(2020, 1, 1, 0, 0, 0))
    marker.external_attr = 0o100644 << 16
    with ZipFile(timed, "a") as archive:
        archive.writestr(marker, b"selected PRE deadline fixture\n")
    key = str(uuid4())
    arguments = _command(task_id, assignment_id, timed, key)
    first = client.call(token, *arguments, expected_exit=1)
    assert first["error"]["code"] == INFRASTRUCTURE_FAILURE
    assert client.call(token, *arguments, expected_exit=1) == first
    observed = _progress(client, token, task_id, key)
    assert observed["operation_state"] == observed["processing_stage"] == "failed"
    assert observed["failure_code"] == INFRASTRUCTURE_FAILURE
    assert observed["next_action"] == "retry_new_key_after_terminal"
    assert observed["pre_submission_results"] == []
    assert observed["submission_id"] is None
    status = _assignment_status(client, token, task_id, assignment_id)
    assert (
        status["current_status"] == "in_progress"
        and status["assignment"]["revision"] is None
    )
    timeout = asyncio.run(
        _terminal(
            environment,
            observed["operation_id"],
            task_id,
            assignment_id,
            timed,
            timeout=True,
        )
    )

    accepted_key, receipt = _submit(client, token, task_id, assignment_id, good)
    finalized = _wait_for_stage(
        client, token, task_id, accepted_key, receipt, "accepted"
    )
    assert finalized["submission_version"] == 1
    audit_accepted_source(
        receipt["operation_id"],
        finalized["submission_id"],
        task_id,
        good,
        accepted=True,
    )
    isolation = asyncio.run(
        _terminal(
            environment,
            receipt["operation_id"],
            task_id,
            assignment_id,
            good,
            timeout=False,
        )
    )
    with (client.evidence.parent / "pre-qualification-client.json").open(
        "x", encoding="utf-8"
    ) as stream:
        Path(stream.name).chmod(0o600)
        json.dump(
            {
                "assignment_id": assignment_id,
                "timeout": timeout,
                "isolation": isolation,
            },
            stream,
        )


def verify_native_trace(evidence, trace):
    """Bind the trusted guest's classified stage exit to both committed receipts."""
    wrapper_digest = "sha256:" + sha256(WRAPPER.read_bytes()).hexdigest()
    seen = set()
    for name, outcome, exit_code, expired in (
        ("timeout", "infrastructure_failure", 125, True),
        ("isolation", "completed", 0, False),
    ):
        invocation = evidence[name]["invocation"]
        lease = invocation["provider_invocation_id"]
        if (
            lease in seen
            or invocation["cleanup"]["obligation_id"] != lease
            or invocation["cleanup"]["disposition"] != "destroyed"
            or invocation["operation"] != "execute_pre"
            or invocation["outcome"] != outcome
            or invocation["runtime"]["binary_sha256"] != wrapper_digest
        ):
            raise AssertionError(f"{name} has no exact destroyed PRE invocation")
        seen.add(lease)
        rows = [row for row in trace if row["name"] == lease]
        operations = [row["operation"] for row in rows]
        if (
            operations[:4] != ["create", "start", "exec", "pre_exit"]
            or set(operations[4:]) != {"delete"}
            or rows[3]["exit_code"] != exit_code
            or rows[3]["project_deadline_exceeded"] is not expired
        ):
            raise AssertionError(
                f"{name} did not have the expected native stage and cleanup trace"
            )


def main():
    parser = argparse.ArgumentParser(description=verify_native_trace.__doc__)
    parser.add_argument("client_evidence", type=Path)
    parser.add_argument("native_trace", type=Path)
    arguments = parser.parse_args()
    for path in (arguments.client_evidence, arguments.native_trace):
        if not path.is_file() or path.stat().st_size > 256 * 1024:
            parser.error("PRE qualification evidence must be a bounded regular file")
    verify_native_trace(
        json.loads(arguments.client_evidence.read_bytes()),
        [json.loads(line) for line in arguments.native_trace.read_bytes().splitlines()],
    )
    print(json.dumps({"timeout": "verified", "isolation": "verified"}))


if __name__ == "__main__":
    main()
