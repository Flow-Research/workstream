"""Canonical task routes retain protected creation and no self-activation."""

from app.main import create_app


def test_task_public_surface_has_no_self_activation_and_one_admission_creation():
    schema = create_app().openapi()
    paths = schema["paths"]
    assert "/api/v1/workers/me/profile" not in paths
    assert "/api/v1/tasks/{task_id}/start" not in paths
    assert "/api/v1/operations/tasks/{task_id}/start" not in paths
    submissions = paths["/api/v1/tasks/{task_id}/submissions"]
    assert "get" in submissions and "post" in submissions
    creation = submissions["post"]
    assert creation["security"]
    assert creation["x-workstream-action-id"] == "submission.create"
    assert "201" in creation["responses"]
    assert creation["requestBody"]["required"] is True
    for path, method, action in (
        ("/api/v1/tasks/{task_id}/claim", "post", "task.claim"),
        ("/api/v1/tasks/{task_id}/work-context", "get", "task.work_context.read"),
        ("/api/v1/projects/{project_id}/tasks/{task_id}/work-context", "get", "project.task.work_context.read"),
    ):
        operation = paths[path][method]
        assert operation["security"]
        assert "200" in operation["responses"]
        assert operation["x-workstream-action-id"] == action
        assert all(parameter["schema"]["format"] == "uuid"
                   for parameter in operation["parameters"] if parameter["in"] == "path")
        if method == "post":
            keys = [parameter for parameter in operation["parameters"]
                    if parameter["in"] == "header" and parameter["name"] == "Idempotency-Key"]
            assert len(keys) == 1 and keys[0]["required"] is True
            assert keys[0]["schema"] == {"type": "string", "format": "uuid"}
    assert "LegacyWorkflowEligibilityActivationRequest" not in schema["components"]["schemas"]
    transition = schema["components"]["schemas"]["TaskTransitionRequest"]
    assert transition["additionalProperties"] is False
    reason_types = transition["properties"]["reason"]["anyOf"]
    assert next(item for item in reason_types if item["type"] == "string")["maxLength"] == 1000
