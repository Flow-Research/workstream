"""Current task readers preserve pending identity and reject invented stages."""

from copy import deepcopy
import json

import pytest

from test_contributor_task_http import CONTRIBUTOR
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_manager_task_evidence_http import MANAGER_CONTEXT
from test_task_context_http import CONTEXT
from test_task_http_boundary import DETAIL, TASK


@pytest.mark.parametrize("command,original,nested", [
    (("task", "show", TASK), CONTRIBUTOR, False),
    (("task", "context", TASK), CONTEXT, True),
    (("project", "task", PROJECT, TASK), DETAIL, False),
    (("project", "task-context", PROJECT, TASK), MANAGER_CONTEXT, True),
])
def test_pending_task_projection_uses_exact_server_identity(cli, command, original, nested):
    with http_fixture() as (origin, response, _requests):
        for stage in ("receiving", "pre_checking", "finalization_pending", "operationally_stalled"):
            body = deepcopy(original)
            task = body["task"] if nested else body
            task["pending_submission_operation"] = {"operation_id": ACTOR, "processing_stage": stage}
            response["body"] = json.dumps(body).encode()
            result = cli(origin, TOKEN, *command, "-o", "json")
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == body
            displayed = cli(origin, TOKEN, *command)
            assert displayed.returncode == 0, displayed.stderr
            assert ACTOR in displayed.stdout and stage in displayed.stdout
        for invalid in (
            {"operation_id": "not-a-uuid", "processing_stage": "receiving"},
            {"operation_id": ACTOR, "processing_stage": "accepted"},
            {"operation_id": ACTOR, "processing_stage": "evaluation_running"},
        ):
            task["pending_submission_operation"] = invalid
            response["body"] = json.dumps(body).encode()
            assert_failure(cli(origin, TOKEN, *command, "-o", "json"), "invalid_api_response")
        task["pending_submission_operation"] = None
        response["body"] = json.dumps(body).encode()
        explicit_null = cli(origin, TOKEN, *command, "-o", "json")
        assert explicit_null.returncode == 0, explicit_null.stderr
        assert json.loads(explicit_null.stdout) == body
        del task["pending_submission_operation"]
        response["body"] = json.dumps(body).encode()
        assert_failure(cli(origin, TOKEN, *command, "-o", "json"), "invalid_api_response")
