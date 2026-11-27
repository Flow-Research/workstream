"""Public CLI task release, assignment and locked-original download."""

import hashlib
from uuid import uuid4

from public_setup import TASK


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


def _release_task(client, tokens, project_id, *, title: str):
    task = client.write_and_replay(
        tokens["manager"],
        "project",
        "task",
        "create",
        project_id,
        body={
            "title": title,
            "description": TASK,
            "task_type": "evaluation",
            "difficulty": "medium",
            "skill_tags": ["analysis"],
            "estimated_time_minutes": 10,
            "acceptance_criteria": "The fixed incident input and exact per-service counts pass POST.",
            "rejection_criteria": "Required files are missing or counts are incorrect.",
        },
    )
    task_id = task["id"]
    for action in ("screen", "release"):
        replay_transition(
            client, tokens["manager"], "project", "task", action, project_id, task_id
        )
    return task_id


def _claim_task(client, token, task_id):
    claimed = replay_transition(client, token, "task", "claim", task_id)
    if claimed["task"]["status"] != "in_progress":
        raise AssertionError("claim did not immediately start work")
    return claimed["assignment"]["id"]


def create_claimed_task(client, tokens, project_id, *, title: str):
    """Reuse the public manager and contributor lifecycle for each real output."""
    task_id = _release_task(client, tokens, project_id, title=title)
    return task_id, _claim_task(client, tokens["alice"], task_id)


def _verified_guide(client, tokens, command, directory):
    guide = client.call(tokens["alice"], *command)
    denied = client.call(tokens["bob"], *command, expected_exit=1)
    if denied["error"].get("status") != 404:
        raise AssertionError(
            "foreign-project contributor did not receive concealed guide denial"
        )
    destination = client.directory / directory
    destination.mkdir(mode=0o700)
    downloaded = client.call(tokens["alice"], *command, "--download", str(destination))
    if downloaded != guide or len(guide["documents"]) != 2:
        raise AssertionError("guide listing changed during download")
    actual = sorted(
        ("sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)
        for path in destination.iterdir()
    )
    expected = sorted(
        (item["sha256"], item["byte_count"]) for item in guide["documents"]
    )
    if actual != expected:
        raise AssertionError(
            "downloaded originals differ from the exact public manifest"
        )
    return guide


def _guide_identity(manifest):
    # Each shipped client already validates read_reference against its own route.
    return manifest | {
        "documents": [
            {key: value for key, value in document.items() if key != "read_reference"}
            for document in manifest["documents"]
        ]
    }


def claim_and_read(client, tokens, actors, project_id, guide_id):
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
    approved = _verified_guide(
        client,
        tokens,
        ("project", "guide", "approved", project_id),
        "approved-guide",
    )
    if (approved["project_id"], approved["guide_id"]) != (project_id, guide_id):
        raise AssertionError(
            "approved contributor guide differs from the activated project guide"
        )
    task_id = _release_task(
        client, tokens, project_id, title="Summarize the fixed incident events"
    )
    before_claim = _verified_guide(
        client, tokens, ("task", "guide", task_id), "locked-guide"
    )
    if _guide_identity(before_claim) != _guide_identity(approved):
        raise AssertionError("released task did not lock the exact approved guide")
    assignment_id = _claim_task(client, tokens["alice"], task_id)
    if client.call(tokens["alice"], "task", "guide", task_id) != before_claim:
        raise AssertionError("claim changed the locked guide manifest")
    return task_id, assignment_id, grant
