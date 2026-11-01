"""Public CLI task release, assignment and locked-original download."""

import hashlib
from uuid import uuid4


def replay_transition(client, token, *arguments):
    command = (
        *arguments,
        "--idempotency-key",
        str(uuid4()),
        "--reason",
        "Isolated public CLI journey",
    )
    first = client.call(token, *command)
    if client.call(token, *command) != first:
        raise AssertionError("task transition replay changed its receipt")
    return first


def issue_submitter(client, manager, actor_id, project_id):
    qualification = {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    }
    return client.write_and_replay(
        manager,
        "project",
        "role-grant",
        "issue",
        project_id,
        body={
            "target_actor_profile_id": actor_id,
            "role": "submitter",
            "qualification": {
                "skills_snapshot": qualification,
                "reputation_snapshot": qualification,
                "prior_project_work_refs": [],
                "external_expertise_refs": [],
            },
            "reason": "Isolated CLI contract exercise; no external qualification claim",
        },
    )


def claim_and_read(client, tokens, actors, project_id):
    grant = issue_submitter(client, tokens["manager"], actors["alice"], project_id)
    other = client.call(
        tokens["manager"],
        "project",
        "create",
        "--name",
        "Isolated other project",
        "--slug",
        "cli-other-" + uuid4().hex,
        "--idempotency-key",
        str(uuid4()),
    )
    issue_submitter(client, tokens["manager"], actors["bob"], other["id"])
    if client.call(tokens["bob"], "project", "show", other["id"])["id"] != other["id"]:
        raise AssertionError("foreign-project contributor setup failed")
    task = client.write_and_replay(
        tokens["manager"],
        "project",
        "task",
        "create",
        project_id,
        body={
            "title": "Validate declared proof fields",
            "description": "Prepare proof.json using the locked guide format.",
            "task_type": "evaluation",
            "difficulty": "medium",
            "skill_tags": ["analysis"],
            "estimated_time_minutes": 10,
            "acceptance_criteria": "All declared proof fields pass the registered checker.",
            "rejection_criteria": "Required proof fields are missing or invalid.",
        },
    )
    task_id = task["id"]
    for action in ("screen", "release"):
        replay_transition(
            client, tokens["manager"], "project", "task", action, project_id, task_id
        )
    claimed = replay_transition(client, tokens["alice"], "task", "claim", task_id)
    if claimed["task"]["status"] != "in_progress":
        raise AssertionError("claim did not immediately start work")
    documents = client.call(tokens["alice"], "task", "guide", task_id)
    denied = client.call(tokens["bob"], "task", "guide", task_id, expected_exit=1)
    if denied["error"].get("status") != 404:
        raise AssertionError("unassigned actor did not receive concealed guide denial")
    destination = client.directory / "locked-guide"
    destination.mkdir(mode=0o700)
    downloaded = client.call(
        tokens["alice"], "task", "guide", task_id, "--download", str(destination)
    )
    if downloaded != documents or len(documents) != 2:
        raise AssertionError("locked guide listing changed during download")
    actual = sorted(
        ("sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)
        for path in destination.iterdir()
    )
    expected = sorted((item["sha256"], item["byte_count"]) for item in documents)
    if actual != expected:
        raise AssertionError(
            "downloaded originals differ from the locked public manifest"
        )
    return task_id, claimed["assignment"]["id"], grant
