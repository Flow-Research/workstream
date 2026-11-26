"""Exact source-first PRE fault/isolation evidence for the maintained CLI journey."""

import argparse
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import time
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

INFRASTRUCTURE_FAILURE = "submission_infrastructure_unavailable"
WRAPPER = (
    Path(__file__).resolve().parents[3]
    / "external_checkers/workstream-checker-service/tests/smol_fixture/runtime_wrapper.py"
)


async def _terminal(
    environment,
    operation_id,
    task_id,
    assignment_id,
    archive,
    *,
    failed,
    cleanup="destroyed",
    expected_operations=1,
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
            if failed:
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
                    == expected_operations
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
    assert invocation.cleanup.disposition == cleanup
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
    if failed:
        assert row["state"] == "failed" and row["finalization_event_id"] is None
        assert row["eligible"] is None and terminal.execution is None
        assert terminal.outcome == "infrastructure_failed"
        assert terminal.infrastructure_failure_code == "implementation_unavailable"
        assert invocation.outcome == "infrastructure_failure"
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


def _verify_failure_replay(first, replay):
    def stable(response):
        error = response["error"].copy()
        error.pop("correlation_id", None)
        return response | {"error": error}

    assert first["error"]["code"] == INFRASTRUCTURE_FAILURE
    assert first["error"]["status"] == 503
    assert stable(first) == stable(replay)


def qualify(client, token, task_id, assignment_id, environment):
    """Exercise one closed current-source native qualification selection."""
    mode = environment.get(
        "WORKSTREAM_CLI_JOURNEY_PRE_QUALIFICATION_MODE", "deadline_isolation"
    )
    if mode == "failure_cleanup":
        return _qualify_failure_cleanup(
            client, token, task_id, assignment_id, environment
        )
    if mode != "deadline_isolation":
        raise RuntimeError("unknown PRE qualification selection")
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
    replay = client.call(token, *arguments, expected_exit=1)
    _verify_failure_replay(first, replay)
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
            failed=True,
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
            failed=False,
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


def _qualify_failure_cleanup(client, token, task_id, assignment_id, environment):
    """Prove failed guests, then accept one result with unresolved VM deletion."""
    from source_audit import audit_accepted_source
    from submission_work import (
        _assignment_status,
        _command,
        _package,
        _progress,
        _submit,
        _wait_for_stage,
    )

    if not __debug__ or client.evidence is None:
        raise RuntimeError("PRE qualification requires private Python assertions")
    good = _package(client, "correct")
    failures = {}
    for name in ("memory", "crash", "output"):
        archive_path = client.directory / f"qualification-{name}.zip"
        archive_path.write_bytes(good.read_bytes())
        marker = ZipInfo(
            f"pre-qualification-{name}.txt", date_time=(2020, 1, 1, 0, 0, 0)
        )
        marker.external_attr = 0o100644 << 16
        with ZipFile(archive_path, "a") as archive:
            archive.writestr(marker, f"selected PRE {name} fixture\n".encode())
        key = str(uuid4())
        arguments = _command(task_id, assignment_id, archive_path, key)
        first = client.call(token, *arguments, expected_exit=1)
        replay = client.call(token, *arguments, expected_exit=1)
        _verify_failure_replay(first, replay)
        observed = _progress(client, token, task_id, key)
        assert observed["operation_state"] == observed["processing_stage"] == "failed"
        assert observed["failure_code"] == INFRASTRUCTURE_FAILURE
        assert observed["next_action"] == "retry_new_key_after_terminal"
        assert observed["pre_submission_results"] == []
        assert observed["submission_id"] is None
        status = _assignment_status(client, token, task_id, assignment_id)
        assert status["current_status"] == "in_progress"
        assert status["assignment"]["revision"] is None
        failures[name] = asyncio.run(
            _terminal(
                environment,
                observed["operation_id"],
                task_id,
                assignment_id,
                archive_path,
                failed=True,
                expected_operations=len(failures) + 1,
            )
        )

    key, receipt = _submit(client, token, task_id, assignment_id, good)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        observed = _progress(client, token, task_id, key, receipt["operation_id"])
        if observed["operation_state"] == "finalized":
            break
        if observed["operation_state"] in {"failed", "abandoned", "cancelled"}:
            raise AssertionError("completed PRE did not reach durable T5")
        time.sleep(1)
    else:
        raise AssertionError("completed PRE did not reach durable T5")
    assert observed["submission_id"] and observed["submission_version"] == 1
    assert observed["processing_stage"] in {"evaluation_pending", "evaluation_running"}
    audit_accepted_source(
        receipt["operation_id"],
        observed["submission_id"],
        task_id,
        good,
        accepted=False,
    )
    pending = asyncio.run(
        _terminal(
            environment,
            receipt["operation_id"],
            task_id,
            assignment_id,
            good,
            failed=False,
            cleanup="pending",
        )
    )
    handoff = {
        "schema_version": "workstream.pre_qualification_restore.v1",
        "nonce": str(uuid4()),
        "source_operation_id": receipt["operation_id"],
        "submission_id": observed["submission_id"],
        "provider_invocation_id": pending["invocation"]["provider_invocation_id"],
        "terminal_sha256": pending["terminal_sha256"],
    }
    handoff_path = client.evidence.parent / "pre-qualification-pending.json"
    with handoff_path.open("x", encoding="utf-8") as stream:
        handoff_path.chmod(0o600)
        json.dump(handoff, stream)
        stream.flush()
        os.fsync(stream.fileno())
    _await_reconciled(client.evidence.parent, handoff)
    accepted = _wait_for_stage(client, token, task_id, key, receipt, "accepted")
    assert accepted["submission_id"] == observed["submission_id"]
    audit_accepted_source(
        receipt["operation_id"],
        accepted["submission_id"],
        task_id,
        good,
        accepted=True,
    )
    destination = client.evidence.parent / "pre-qualification-client.json"
    with destination.open("x", encoding="utf-8") as stream:
        destination.chmod(0o600)
        json.dump(
            {
                "mode": "failure_cleanup",
                "assignment_id": assignment_id,
                "failures": failures,
                "pending": pending,
                "submission_id": observed["submission_id"],
                "accepted_submission_id": accepted["submission_id"],
            },
            stream,
        )


def _await_reconciled(directory, handoff):
    """Keep the isolated public client alive until this lease is reconciled."""
    path = directory / "pre-qualification-reconciled.json"
    deadline = time.monotonic() + 300
    expected = handoff | {"owned_resources_empty": True, "test_service_ready": True}
    while time.monotonic() < deadline:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            time.sleep(0.5)
            continue
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            valid = (
                stat.S_ISREG(metadata.st_mode)
                and stat.S_IMODE(metadata.st_mode) == 0o600
                and metadata.st_uid == os.geteuid()
                and metadata.st_nlink == 1
                and 0 < metadata.st_size <= 4096
                and json.loads(stream.read(4097)) == expected
            )
        if not valid:
            raise AssertionError("PRE cleanup reconciliation receipt differs")
        return
    raise AssertionError("PRE cleanup reconciliation was not acknowledged")


def verify_native_trace(evidence, trace):
    """Bind the trusted guest's classified stage exit to both committed receipts."""
    if evidence.get("mode") == "failure_cleanup":
        return _verify_failure_cleanup_trace(evidence, trace)
    if evidence.get("mode") not in {None, "deadline_isolation"}:
        raise AssertionError("unknown PRE qualification evidence selection")
    wrapper_digest = "sha256:" + sha256(WRAPPER.read_bytes()).hexdigest()
    leases = []
    for name, outcome, exit_code, expired in (
        ("timeout", "infrastructure_failure", 125, True),
        ("isolation", "completed", 0, False),
    ):
        invocation = evidence[name]["invocation"]
        lease = invocation["provider_invocation_id"]
        if (
            lease in leases
            or invocation["cleanup"]["obligation_id"] != lease
            or invocation["cleanup"]["disposition"] != "destroyed"
            or invocation["operation"] != "execute_pre"
            or invocation["outcome"] != outcome
            or invocation["runtime"]["binary_sha256"] != wrapper_digest
        ):
            raise AssertionError(f"{name} has no exact destroyed PRE invocation")
        leases.append(lease)
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
        if name == "isolation":
            prior_resources = rows[0].get("prior_resources")
            if type(prior_resources) is not list or leases[0] in prior_resources:
                raise AssertionError(
                    "timeout VM resources remained at isolation create"
                )

    executions = [row for row in trace if row["operation"] == "exec"]
    if (
        any(type(row.get("source_pre")) is not bool for row in executions)
        or [row["name"] for row in executions if row["source_pre"]] != leases
    ):
        raise AssertionError(
            "native trace contains a different set of source-first PRE executions"
        )


def _verify_failure_cleanup_trace(evidence, trace):
    """Bind three guest failures and one exact unsettled delete to current PRE leases."""
    wrapper_digest = "sha256:" + sha256(WRAPPER.read_bytes()).hexdigest()
    leases = []
    for name in ("memory", "crash", "output", "pending"):
        item = evidence["pending"] if name == "pending" else evidence["failures"][name]
        invocation = item["invocation"]
        lease = invocation["provider_invocation_id"]
        expected_outcome = (
            "completed" if name == "pending" else "infrastructure_failure"
        )
        expected_cleanup = "pending" if name == "pending" else "destroyed"
        if (
            lease in leases
            or invocation["operation"] != "execute_pre"
            or invocation["outcome"] != expected_outcome
            or invocation["cleanup"]["obligation_id"] != lease
            or invocation["cleanup"]["disposition"] != expected_cleanup
            or invocation["runtime"]["binary_sha256"] != wrapper_digest
        ):
            raise AssertionError(f"{name} has no exact PRE invocation")
        rows = [row for row in trace if row["name"] == lease]
        operations = [row["operation"] for row in rows]
        if (
            operations[:4] != ["create", "start", "exec", "pre_exit"]
            or not operations[4:]
            or set(operations[4:]) != {"delete"}
            or rows[2].get("source_pre") is not True
            or any(prior in rows[0].get("prior_resources", []) for prior in leases)
            or rows[3]["project_deadline_exceeded"] is not False
            or rows[3].get("guest_limit_unenforced") is not False
        ):
            raise AssertionError(f"{name} lacks exact native execution and cleanup")
        if name == "pending":
            if rows[3]["exit_code"] != 0:
                raise AssertionError("pending cleanup did not follow a completed guest")
        elif rows[3]["exit_code"] == 0:
            raise AssertionError(f"{name} native failure differs")
        leases.append(lease)
    executions = [row for row in trace if row["operation"] == "exec"]
    if (
        any(type(row.get("source_pre")) is not bool for row in executions)
        or [row["name"] for row in executions if row["source_pre"]] != leases
    ):
        raise AssertionError("native trace contains a different PRE execution")


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
    print(
        json.dumps(
            {
                "selection": json.loads(arguments.client_evidence.read_bytes()).get(
                    "mode", "deadline_isolation"
                ),
                "native_trace": "verified",
            }
        )
    )


if __name__ == "__main__":
    main()
