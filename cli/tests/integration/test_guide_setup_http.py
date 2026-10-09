"""Built-process setup observations through the one existing public GET."""

from copy import deepcopy
import json
from urllib.parse import quote

from test_contributor_task_mutations import canonical_error
from test_guide_create_http import GUIDE, SETUP
from test_http_boundary import (
    ACTOR,
    PROFILE,
    PROJECT,
    TOKEN,
    assert_failure,
    http_fixture,
)

UUID = "018f0ebc-7966-7e8d-bc4d-1cae1e00000a"
DEFAULT_NULL = (
    "finalized_compilation_id",
    "correction_operation_id",
    "predecessor_compilation_id",
)
UUID_FIELDS = (
    "id",
    "project_id",
    "guide_id",
    "source_snapshot_id",
    "created_by",
    *DEFAULT_NULL,
    "output_sufficiency_report_id",
    "output_submission_artifact_policy_id",
    "error_artifact_incident_id",
)
TIME_FIELDS = (
    "created_at",
    "updated_at",
    "documents_ready_at",
    "started_at",
    "finished_at",
)
REQUIRED_NONNULL = (
    "id",
    "project_id",
    "guide_id",
    "guide_version",
    "source_snapshot_id",
    "setup_generation",
    "status",
    "current_step",
    "created_by",
    "created_at",
    "updated_at",
)


def setup():
    return {
        "id": SETUP,
        "project_id": PROJECT,
        "guide_id": GUIDE,
        "guide_version": "guide é\n\x1b[31m",
        "source_snapshot_id": UUID,
        "setup_generation": 1,
        **dict.fromkeys(DEFAULT_NULL),
        "celery_task_id": None,
        "documents_ready_at": None,
        "status": "awaiting_documents",
        "current_step": "document_intake",
        "output_sufficiency_report_id": None,
        "output_submission_artifact_policy_id": None,
        "error_code": None,
        "error_artifact_incident_id": None,
        "error_summary": None,
        "created_by": ACTOR,
        "created_at": PROFILE["created_at"],
        "updated_at": PROFILE["updated_at"],
        "started_at": None,
        "finished_at": None,
    }


def invoke(cli, origin, project=PROJECT, guide=GUIDE, *, output="json", token=TOKEN):
    return cli(origin, token, "-o", output, "project", "guide", "setup", project, guide)


def test_guide_setup_preserves_selectors_complete_json_and_safe_text(cli):
    with http_fixture() as (origin, response, requests):
        value = setup()
        for status in (
            "awaiting_documents",
            "provider_outcome_unresolved",
            "compilation_invalid_terminal",
            "completed",
        ):
            value["status"] = status
            if status != "awaiting_documents":
                value |= {
                    "celery_task_id": "guide-compile:" + SETUP + ":1",
                    "documents_ready_at": PROFILE["created_at"],
                    "started_at": PROFILE["created_at"],
                    "error_summary": "Diagnostic é\n\x1b[32m\u202e",
                    "error_code": "provider_outcome_unresolved",
                    "error_artifact_incident_id": UUID,
                }
            if status == "completed":
                value |= dict.fromkeys(DEFAULT_NULL, UUID)
                value |= {
                    "output_sufficiency_report_id": UUID,
                    "output_submission_artifact_policy_id": UUID,
                    "finished_at": PROFILE["updated_at"],
                }
            response["body"] = json.dumps(value, ensure_ascii=False, indent=2).encode()
            for spell in (
                lambda x: x,
                lambda x: x.replace("-", ""),
                lambda x: "{" + x + "}",
                lambda x: "urn:uuid:" + x,
            ):
                project, guide = spell(PROJECT), spell(GUIDE)
                result = invoke(cli, origin, project, guide)
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert result.stdout.strip().encode() == response["body"]
                assert requests[-1] == (
                    "GET",
                    f"/api/v1/projects/{quote(project, safe=':')}/guides/{quote(guide, safe=':')}/setup-runs/latest",
                    "Bearer " + TOKEN,
                )
            text = invoke(cli, origin, output="text")
            assert text.returncode == 0 and text.stderr == "", text.stderr
            assert text.stdout.startswith("Latest setup (not approval or activation): ")
            assert text.stdout.count("\n") == 1
            assert "\x1b" not in text.stdout and "\u202e" not in text.stdout
            for name in value:
                assert f'"{name}"' in text.stdout
        assert len(requests) == 20  # One read each, no readiness polling/preflight.
        assert response["commands"] == [] and response["updates"] == []


def test_guide_setup_nullable_defaults_and_backend_integer_range(cli):
    with http_fixture() as (origin, response, _requests):
        for generation in (1, 9223372036854775807, 9223372036854775808):
            value = setup() | {"setup_generation": generation}
            for key in DEFAULT_NULL:
                del value[key]
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == value
            text = invoke(cli, origin, output="text")
            assert text.returncode == 0 and str(generation) in text.stdout
        for invalid in ('"1"', "1.5", "1e2", "true", "[]", "{}"):
            response["body"] = (
                json.dumps(setup())
                .replace('"setup_generation": 1', '"setup_generation": ' + invalid)
                .encode()
            )
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_guide_setup_rejects_required_nulls_missing_and_unknown_fields(cli):
    value = setup()
    with http_fixture() as (origin, response, _requests):
        for name in REQUIRED_NONNULL:
            response["body"] = json.dumps(value | {name: None}).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for name in value.keys() - set(DEFAULT_NULL):
            missing = deepcopy(value)
            del missing[name]
            response["body"] = json.dumps(missing).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for body in (
            json.dumps(value | {"provider_secret": "must-not-be-output"}),
            json.dumps(value)[:-1] + ', "status": "approved"}',
            "null",
            "[]",
        ):
            response["body"] = body.encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_guide_setup_rejects_malformed_and_substituted_identity(cli):
    with http_fixture() as (origin, response, _requests):
        for name in UUID_FIELDS:
            response["body"] = json.dumps(setup() | {name: "not-uuid"}).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for name in ("project_id", "guide_id"):
            response["body"] = json.dumps(setup() | {name: UUID}).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for name in TIME_FIELDS:
            response["body"] = json.dumps(setup() | {name: "not-time"}).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for name in (
            "guide_version",
            "status",
            "current_step",
            "celery_task_id",
            "error_code",
            "error_summary",
        ):
            response["body"] = json.dumps(setup() | {name: {"invalid": True}}).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_guide_setup_invalid_selectors_send_no_request(cli):
    with http_fixture() as (origin, _response, requests):
        for project, guide in (
            ("../other", GUIDE),
            (PROJECT, "../other"),
            ("", GUIDE),
            (PROJECT, "x" * 101),
        ):
            assert_failure(invoke(cli, origin, project, guide), "invalid_arguments", 2)
        assert requests == []


def test_guide_setup_bounds_denials_redirects_and_credential_metadata(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(
            setup() | {"error_summary": "x" * (64 * 1024)}
        ).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")
        response["headers"]["Content-Type"] = "text/plain"
        response["body"] = json.dumps(setup()).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")
        response["headers"]["Content-Type"] = "application/json"
        response["status"] = 404
        response["body"] = json.dumps(canonical_error("not_found")).encode()
        denied = invoke(cli, origin)
        assert_failure(denied, "not_found")
        assert json.loads(denied.stderr)["error"]["status"] == 404
        assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
        response["body"] = json.dumps(canonical_error("credential_canary_AAA")).encode()
        assert_failure(invoke(cli, origin, token="credential_canary_AAA"), "api_error")
        response["status"] = 302
        response["headers"]["Location"] = origin + "/credential-sink"
        response["body"] = b""
        count = len(requests)
        assert_failure(invoke(cli, origin), "redirect_refused")
        assert len(requests) == count + 1
        assert not any(request[1] == "/credential-sink" for request in requests)
