"""Real CLI intake, durable evaluation and unpaid contribution observation."""

import csv
import hashlib
import json
import subprocess
import time
from uuid import uuid4
from zipfile import ZipFile


def submit_and_observe(
    client, tokens, actors, project_id, task_id, assignment_id, grant
):
    token = tokens["alice"]
    packet = (
        "--assignment",
        assignment_id,
        "--summary",
        "Local declared-proof format exercise",
        "--attestation",
        "These are illustrative format claims, not verified remote work.",
    )
    rejected = client.directory / "rejected.zip"
    with ZipFile(rejected, "x") as bundle:
        bundle.writestr("proof.json", "{}")
    failure = client.call(
        token,
        "task",
        "prepare",
        task_id,
        *packet,
        "--file",
        str(rejected),
        "--idempotency-key",
        str(uuid4()),
        expected_exit=1,
    )
    if failure["error"]["code"] != "pre_submission_checker_failed":
        raise AssertionError("invalid declared proof was not rejected by intake")
    # Exact task-history resolution requires an existing Submission. The self
    # collection supports an empty result and is the appropriate absence proof.
    if client.call(token, "me", "submissions", "--task", task_id)["items"]:
        raise AssertionError("rejected candidate created a submission")
    archive = client.directory / "submission.zip"
    with ZipFile(archive, "x") as bundle:
        bundle.writestr(
            "proof.json",
            json.dumps(
                {
                    "schema": "harnessy.work.proof.v1",
                    "commit_sha": "a" * 40,
                    "pr_url": "https://github.com/example/format-exercise/pull/1",
                    "ci_run_url": "https://github.com/example/format-exercise/actions/runs/1",
                    "ci_conclusion": "success",
                    "merged": True,
                }
            ),
        )
    archive_hash = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    command = (
        "task",
        "prepare",
        task_id,
        *packet,
        "--file",
        str(archive),
        "--idempotency-key",
        str(uuid4()),
    )
    first = client.call(token, *command)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        page = client.call(token, "task", "preparations", task_id)
        matching = [
            item for item in page["items"] if item["archive_sha256"] == archive_hash
        ]
        if len(matching) > 1:
            raise AssertionError("one preparation request produced duplicate runs")
        if matching and matching[0]["state"] == "ready":
            ready = matching[0]
            break
        if matching and matching[0]["state"] in {
            "checks_failed",
            "infrastructure_failed",
            "stale",
        }:
            raise AssertionError("real intake failed; no substitution permitted")
        time.sleep(1)
    else:
        raise AssertionError("real intake did not reach ready admission")
    replay = client.call(token, *command)
    if (
        replay["put_attempt_id"] != first["put_attempt_id"]
        or replay["admission_id"] != ready["admission_id"]
        or replay["replayed"] is not True
    ):
        raise AssertionError("exact preparation replay changed custody")
    submit = ("task", "submit", task_id, *packet, "--admission", ready["admission_id"])
    receipt = client.call(token, *submit)
    if client.call(token, *submit) != receipt:
        raise AssertionError("exact submission replay changed receipt")
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        outcome = client.call(token, "submission", "show", receipt["submission_id"])
        if outcome["status"] == "accepted":
            break
        if outcome["status"] in {"rejected", "needs_revision"}:
            raise AssertionError(
                "real checker did not reach the expected acceptance branch"
            )
        time.sleep(1)
    else:
        # Capture the public failure state before the isolated runtime is torn
        # down. These reads never repair/retry work or turn the timeout into a
        # pass; one failed diagnostic must not hide the original failure.
        for diagnostic_token, arguments in (
            (token, ("submission", "findings", receipt["submission_id"])),
            (
                tokens["operator"],
                ("operations", "checker", "retry-sources", project_id),
            ),
            (
                tokens["operator"],
                ("operations", "delivery", "list", project_id),
            ),
        ):
            try:
                client.call(diagnostic_token, *arguments)
            except (AssertionError, subprocess.TimeoutExpired, OSError, ValueError):
                # The client retains redacted execution metadata and private
                # receipts when available. Do not print arbitrary server text.
                print("Evaluation diagnostic unavailable: " + arguments[1])
        raise AssertionError("durable evaluation did not reach acceptance")
    retained = client.call(token, "me", "submissions", "--task", task_id)
    if retained["next_cursor"] is not None or len(retained["items"]) != 1:
        raise AssertionError("submission replay did not retain exactly one attempt")
    if (
        retained["items"][0]["submission_id"] != receipt["submission_id"]
        or outcome["id"] != receipt["submission_id"]
    ):
        raise AssertionError("retained submission differs from accepted receipt")
    for field, value in {
        "task_id": task_id,
        "version": receipt["submission_version"],
        "status": "accepted",
    }.items():
        if retained["items"][0][field] != value or outcome[field] != value:
            raise AssertionError("retained submission differs from accepted receipt")
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
        # Public findings name the manager-selected requirement, independently
        # of the setup suggestion ID and registry capability.
        result["checker_name"] == "project.proof_post" and result["status"] == "passed"
        for result in run["results"]
    ):
        raise AssertionError("registered checker has no completed passing evidence")
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
