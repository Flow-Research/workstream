"""Public raw ZIP intake, real POST routing and governed contribution evidence."""

import csv
import hashlib
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from task_work import create_claimed_task
from source_audit import audit_accepted_source

PILOT = Path(__file__).resolve().parents[3] / "pilots/terminal_systems/mvp"
PACKET = (
    "--summary",
    "Fixed incident summary",
    "--attestation",
    "I counted the supplied incident events and retained the input.",
)


def _package(client, kind):
    archive = client.directory / f"{kind}.zip"
    subprocess.run(
        [sys.executable, str(PILOT / "package.py"), kind, str(archive)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if archive.stat().st_size <= 0:
        raise AssertionError("pilot package is empty")
    return archive


def _command(task_id, assignment_id, archive, key):
    return (
        "task",
        "submit",
        task_id,
        "--assignment",
        assignment_id,
        *PACKET,
        "--file",
        str(archive),
        "--idempotency-key",
        key,
    )


def _progress(client, token, task_id, key, operation_id=None):
    by_key = client.call(
        token, "task", "submission-operation", task_id, "--idempotency-key", key
    )
    if operation_id is not None:
        by_id = client.call(
            token,
            "task",
            "submission-operation",
            task_id,
            "--operation-id",
            operation_id,
        )
        if by_key != by_id or by_id["operation_id"] != operation_id:
            raise AssertionError("key and operation reads differ")
    return by_key


def _wait_for_stage(client, token, task_id, key, receipt, expected_stage):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        observed = _progress(client, token, task_id, key, receipt["operation_id"])
        if observed["operationally_stalled"]:
            raise AssertionError("durable submission requires explicit recovery")
        if observed["processing_stage"] == expected_stage:
            if (
                observed["operation_state"] != "finalized"
                or not observed["submission_id"]
            ):
                raise AssertionError("governed outcome has no finalized Submission")
            return observed
        if observed["operation_state"] in {
            "rejected",
            "failed",
            "abandoned",
            "cancelled",
        }:
            raise AssertionError("accepted source failed before governed evaluation")
        if observed["processing_stage"] in {"accepted", "needs_revision", "rejected"}:
            raise AssertionError("submission reached a different governed outcome")
        time.sleep(1)
    raise AssertionError("durable evaluation did not reach its governed outcome")


def _submit(client, token, task_id, assignment_id, archive):
    key = str(uuid4())
    command = _command(task_id, assignment_id, archive, key)
    receipt = client.call(token, *command)
    if (
        receipt["status"] != "accepted"
        or receipt["processing_stage_at_acceptance"] != "finalization_pending"
    ):
        raise AssertionError("source command did not return T4 acceptance")
    replay = client.call(token, *command)
    if replay != (receipt | {"replayed": True}):
        raise AssertionError("exact source replay changed accepted command snapshot")
    progress = _progress(client, token, task_id, key, receipt["operation_id"])
    if progress["pre_submission_results"] != receipt["pre_submission_results"]:
        raise AssertionError("accepted feedback changed during operation observation")
    return key, receipt


def _pre_missing_has_no_submission(client, token, task_id, assignment_id):
    key = str(uuid4())
    command = _command(task_id, assignment_id, _package(client, "pre-missing"), key)
    failure = client.call(token, *command, expected_exit=1)
    if failure["error"]["code"] != "pre_submission_checker_failed":
        raise AssertionError("missing summary was not rejected by real PRE")
    observed = _progress(client, token, task_id, key)
    if (
        observed["operation_state"] != "rejected"
        or observed["processing_stage"] != "rejected"
        or observed["submission_id"] is not None
        or observed["next_action"] != "correct_and_submit_new_key"
    ):
        raise AssertionError("rejected PRE candidate created downstream work")
    if client.call(token, "me", "submissions", "--task", task_id)["items"]:
        raise AssertionError("rejected PRE candidate created a Submission")


def _incorrect_post_has_no_acceptance(client, tokens, project_id, previous_records):
    task_id, assignment_id = create_claimed_task(
        client, tokens, project_id, title="Reject incorrect incident counts"
    )
    archive = _package(client, "incorrect")
    key, receipt = _submit(client, tokens["alice"], task_id, assignment_id, archive)
    observed = _wait_for_stage(
        client, tokens["alice"], task_id, key, receipt, "needs_revision"
    )
    submission_id = observed["submission_id"]
    outcome = client.call(tokens["alice"], "submission", "show", submission_id)
    if outcome["status"] != "needs_revision":
        raise AssertionError("incorrect shaped summary bypassed governed revision")
    runs = client.call(tokens["alice"], "submission", "findings", submission_id)
    if len(runs["items"]) != 1 or not any(
        result["checker_name"] == "terminal.post.incident_summary_counts"
        and result["status"] == "failed"
        for result in runs["items"][0]["results"]
    ):
        raise AssertionError("incorrect counts lack real failed POST evidence")
    records = client.call(tokens["alice"], "contributions", "--project", project_id)[
        "items"
    ]
    if records != previous_records or any(
        item["task_id"] == task_id for item in records
    ):
        raise AssertionError("failed POST created acceptance, award or contribution")
    audit_accepted_source(
        receipt["operation_id"], submission_id, task_id, archive, accepted=False
    )


def observe_review_pending(client, tokens, project_id, task_id, assignment_id):
    """Prove the default human-review branch stops before final acceptance."""
    archive = client.directory / "correct.zip"
    if not archive.is_file():
        archive = _package(client, "correct")
    key, accepted = _submit(client, tokens["alice"], task_id, assignment_id, archive)
    observed = _wait_for_stage(
        client, tokens["alice"], task_id, key, accepted, "review_pending"
    )
    submission = client.call(
        tokens["alice"], "submission", "show", observed["submission_id"]
    )
    if submission["status"] != "review_pending":
        raise AssertionError("default review policy did not retain pending review")
    records = client.call(tokens["alice"], "contributions", "--project", project_id)[
        "items"
    ]
    if records:
        raise AssertionError("pending human review fabricated a contribution or award")
    audit_accepted_source(
        accepted["operation_id"],
        observed["submission_id"],
        task_id,
        archive,
        accepted=False,
    )
    return observed


def submit_and_observe(
    client, tokens, actors, project_id, task_id, assignment_id, grant
):
    token = tokens["alice"]
    _pre_missing_has_no_submission(client, token, task_id, assignment_id)
    archive = _package(client, "correct")
    archive_hash = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    key, accepted = _submit(client, token, task_id, assignment_id, archive)
    observed = _wait_for_stage(client, token, task_id, key, accepted, "accepted")
    receipt = {
        "submission_id": observed["submission_id"],
        "submission_version": int(observed["submission_version"]),
    }
    outcome = client.call(token, "submission", "show", receipt["submission_id"])
    retained = client.call(token, "me", "submissions", "--task", task_id)
    if retained["next_cursor"] is not None or len(retained["items"]) != 1:
        raise AssertionError("submission replay did not retain exactly one attempt")
    if (
        retained["items"][0]["submission_id"] != receipt["submission_id"]
        or outcome["id"] != receipt["submission_id"]
    ):
        raise AssertionError("retained submission differs from accepted operation")
    for field, value in {
        "task_id": task_id,
        "version": receipt["submission_version"],
        "status": "accepted",
    }.items():
        if retained["items"][0][field] != value or outcome[field] != value:
            raise AssertionError("retained submission differs from accepted operation")
    if retained["items"][0].get("artifact_hash") not in (None, archive_hash):
        raise AssertionError("retained submission differs from submitted ZIP")
    runs = client.call(token, "submission", "findings", receipt["submission_id"])
    if runs["next_cursor"] is not None or len(runs["items"]) != 1:
        raise AssertionError("expected one real post-submit checker run")
    run = runs["items"][0]
    for field, value in {
        "task_id": task_id,
        "submission_id": receipt["submission_id"],
        "submission_version": receipt["submission_version"],
        "status": "completed",
        "is_current_for_submission": True,
    }.items():
        if run[field] != value:
            raise AssertionError("checker run does not bind the accepted attempt")
    if not run["completed_at"] or not any(
        result["checker_name"] == "terminal.post.incident_summary_counts"
        and result["status"] == "passed"
        for result in run["results"]
    ):
        raise AssertionError("registered POST checker lacks passing evidence")
    if (
        client.call(
            token,
            "submission",
            "findings",
            receipt["submission_id"],
            "--run",
            run["id"],
        )
        != run
    ):
        raise AssertionError("exact checker run differs from listed evidence")
    records = client.call(token, "contributions", "--project", project_id)["items"]
    if len(records) != 1:
        raise AssertionError("expected exactly one unpaid submitter contribution")
    record = records[0]
    for field, value in {
        "task_id": task_id,
        "project_id": project_id,
        "submission_id": receipt["submission_id"],
        "contributor_id": actors["alice"],
        "source_task_assignment_id": assignment_id,
        "contribution_type": "accepted_submission",
        "awards": [],
        "source_review_id": None,
        "source_review_lease_id": None,
    }.items():
        if record[field] != value:
            raise AssertionError("contribution differs from the exercised attempt")
    if not record["source_final_acceptance_id"]:
        raise AssertionError("accepted contribution lacks final acceptance provenance")
    if record["artifact_hash"] != archive_hash:
        raise AssertionError("accepted contribution does not bind the original ZIP")
    exported = client.call(tokens["finance"], "project", "contributions", project_id)
    if exported["items"] != records:
        raise AssertionError("authorized project export differs from own evidence")
    destination = client.directory / "contributions.csv"
    saved = client.call(
        token, "contributions", "--project", project_id, "--csv", str(destination)
    )
    if saved != {"format": "csv", "saved": True}:
        raise AssertionError("CSV publication did not report success")
    with destination.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise AssertionError("CSV duplicated or lost the unpaid contribution")
    for field in (
        "contribution_id",
        "project_id",
        "task_id",
        "submission_id",
        "contributor_id",
        "source_final_acceptance_id",
        "source_task_assignment_id",
        "artifact_hash",
        "contribution_policy_version_id",
    ):
        if rows[0][field] != record[field]:
            raise AssertionError("CSV lineage differs from JSON evidence")
    audit_accepted_source(
        accepted["operation_id"],
        receipt["submission_id"],
        task_id,
        archive,
        accepted=True,
    )
    _incorrect_post_has_no_acceptance(client, tokens, project_id, records)
    client.call(token, "project", "show", project_id)
    client.write_and_replay(
        tokens["manager"],
        "project",
        "role-grant",
        "revoke",
        project_id,
        grant["id"],
        body={"reason": "Verify fresh authority after completed journey"},
    )
    denied = client.call(token, "project", "show", project_id, expected_exit=1)
    if denied["error"].get("status") != 404:
        raise AssertionError("revoked project grant still permits protected inspection")
    return receipt
