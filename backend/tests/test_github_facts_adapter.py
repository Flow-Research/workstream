"""GitHub App facts adapter: facts, bounded retries and credential custody."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import logging
import time
import traceback
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from pydantic import SecretStr, ValidationError

from app.adapters.github import forge_facts_adapter_factory
from app.adapters.github.app_facts import (
    GitHubAppFactsAdapter,
    GitHubAppFactsConfiguration,
    github_web_origin,
    load_github_app_private_key,
    _InstallationToken,
)
from app.core.config import Settings
from app.interfaces.external_services import (
    ExternalServiceAdapterError,
    ExternalServiceConfigurationError,
)
from app.interfaces.forge_facts import (
    ForgeFactsAccessDeniedError,
    ForgeFactsIncompleteError,
    ForgeFactsInconsistentError,
    ForgeFactsProtocolError,
    ForgeFactsUnavailableError,
    ForgeChangeFacts,
    ForgeChangeNotEligibleError,
    ForgeChangeNotFoundError,
    ForgeJudgedResultFact,
    ForgeRequiredChecksNotConfiguredError,
)

API = "https://api.github.com"
REPOSITORY = "acme/widgets"
HEAD_SHA = "a" * 40
MERGE_SHA = "b" * 40
TOKEN = "ghs_installationTokenSecretValue0001"
SECOND_TOKEN = "ghs_installationTokenSecretValue0002"
NOW = 1_800_000_000.0
APP_ID = 4242

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
PEM_BODY_LINE = PRIVATE_PEM.splitlines()[1]
# Throwaway key generated per test run; no real key exists in the repository.


def _pull(**changes: object) -> dict:
    body = {
        "number": 12,
        "state": "closed",
        "merged": True,
        "merge_commit_sha": MERGE_SHA,
        "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
        "head": {"sha": HEAD_SHA},
        "html_url": f"https://github.com/{REPOSITORY}/pull/12",
        "user": {"login": "agent-bot", "id": 501, "type": "Bot"},
        "changed_files": 2,
    }
    body.update(changes)
    return body


RUN_DETAILS_URL = f"https://github.com/{REPOSITORY}/actions/runs/345/job/678"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/345"
REVIEWS = [
    {
        "id": 61,
        "user": {"login": "reviewer", "id": 7, "type": "User"},
        "state": "APPROVED",
        "commit_id": HEAD_SHA,
        "submitted_at": "2027-01-15T07:00:00Z",
    },
    {
        "id": 62,
        "user": None,
        "state": "COMMENTED",
        "commit_id": MERGE_SHA,
        "submitted_at": "2027-01-15T07:30:00Z",
    },
]
FILES = [
    {"filename": "src/app.py", "status": "modified"},
    {"filename": ".github/workflows/ci.yml", "previous_filename": "ci.yml", "status": "renamed"},
]


class FakeGitHub:
    """Route-table GitHub fake that records every request it receives."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: dict[str, bytes] = {}
        self.tokens = [TOKEN, SECOND_TOKEN]
        self.routes: dict[tuple[str, str], list] = {}
        # A GitHub Enterprise Server API lives under a path such as /api/v3.
        self.prefix = ""
        self.route("GET", f"/repos/{REPOSITORY}/installation", {"id": 77})
        self.route("POST", "/app/installations/77/access_tokens", self._token)
        self.route("GET", f"/repos/{REPOSITORY}", {"full_name": REPOSITORY})
        self.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull())
        self.route("GET", f"/repos/{REPOSITORY}/pulls/12/reviews", REVIEWS)
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/collaborators/reviewer/permission",
            {"permission": "write", "user": {"login": "reviewer", "id": 7}},
        )
        self.route("GET", f"/repos/{REPOSITORY}/pulls/12/files", FILES)
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
            {
                "strict": True,
                "contexts": ["backend", "lint"],
                "checks": [
                    {"context": "backend", "app_id": 15368},
                    {"context": "lint", "app_id": None},
                ],
            },
        )
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
            {
                "total_count": 1,
                "check_runs": [
                    {
                        "id": 10,
                        "html_url": f"https://github.com/{REPOSITORY}/runs/10",
                        "details_url": RUN_DETAILS_URL,
                        "name": "backend",
                        "head_sha": HEAD_SHA, "status": "completed",
                        "conclusion": "success",
                        "app": {"id": 15368},
                    }
                ],
            },
        )
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
            {"sha": HEAD_SHA, "state": "success", "statuses": [{"id": 21, "context": "lint", "state": "success"}]},
        )

    def route(self, method: str, path: str, *responses: object) -> None:
        """Queue responses; the last one repeats once the queue is exhausted."""
        self.routes[(method, path)] = list(responses)

    def _token(self, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"token": self.tokens.pop(0), "expires_at": "2027-01-15T09:00:00Z"},
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get((request.method, request.url.path.removeprefix(self.prefix)))
        if queue is None:
            return httpx.Response(404, json={"message": "Not Found"})
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            response = item(request)
        elif isinstance(item, httpx.Response):
            response = item
        else:
            response = httpx.Response(200, json=item)
        self.bodies[str(request.url)] = response.content
        return response

    def secrets(self) -> list[str]:
        """Every credential the adapter sent, plus the issued tokens."""
        sent = [
            request.headers["authorization"].removeprefix("Bearer ")
            for request in self.requests
            if "authorization" in request.headers
        ]
        return [*sent, TOKEN, SECOND_TOKEN, PEM_BODY_LINE]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _adapter(
    fake: FakeGitHub,
    clock: Clock | None = None,
    *,
    installation_id: int | None = None,
    deadline: float = 45.0,
    attempts: int = 3,
    api: str = API,
) -> GitHubAppFactsAdapter:
    clock = clock or Clock()
    return GitHubAppFactsAdapter(
        GitHubAppFactsConfiguration(
            app_id=APP_ID,
            installation_id=installation_id,
            api_base_url=api,
            request_timeout_seconds=10.0,
            total_deadline_seconds=deadline,
            maximum_attempts=attempts,
        ),
        PRIVATE_KEY,
        transport=httpx.MockTransport(fake.handler),
        wall_clock=lambda: NOW,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


async def _fetch(adapter: GitHubAppFactsAdapter) -> ForgeChangeFacts:
    return await adapter.fetch_change_facts(
        repository=REPOSITORY, change_number=12, base_branch="main"
    )


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


async def test_happy_path_returns_facts_with_response_digests() -> None:
    fake = FakeGitHub()
    facts = await _fetch(_adapter(fake))

    assert facts.model_dump(mode="json") == {
        "schema_version": "workstream.forge_change_facts.v1",
        "forge": "github",
        "forge_origin": "https://github.com",
        "repository": REPOSITORY,
        "change_number": 12,
        "change_url": f"https://github.com/{REPOSITORY}/pull/12",
        "state": "closed",
        "merged": True,
        "landed_commit_sha": MERGE_SHA,
        "base_ref": "main",
        "head_sha": HEAD_SHA,
        "author": {"login": "agent-bot", "id": 501, "kind": "bot"},
        "reviews": [
            {
                "id": "61",
                "reviewer": {"login": "reviewer", "id": 7, "kind": "user"},
                "reviewer_write_access": True,
                "state": "approved",
                "commit_id": HEAD_SHA,
                "submitted_at": "2027-01-15T07:00:00Z",
            },
            {
                "id": "62",
                "reviewer": None,
                "reviewer_write_access": None,
                "state": "commented",
                "commit_id": MERGE_SHA,
                "submitted_at": "2027-01-15T07:30:00Z",
            },
        ],
        "changed_files_count": 2,
        "changed_files": [
            {"path": "src/app.py", "previous_path": None, "status": "modified"},
            {
                "path": ".github/workflows/ci.yml",
                "previous_path": "ci.yml",
                "status": "renamed",
            },
        ],
        "required_checks": [
            {
                "name": "backend",
                "conclusion": "success",
                "required_producer": "github_app:15368",
                "judged": [{"producer": "github_app:15368", "sha": HEAD_SHA}],
                "run_url": f"https://github.com/{REPOSITORY}/actions/runs/345",
            },
            {
                "name": "lint",
                "conclusion": "success",
                "required_producer": None,
                "judged": [{"producer": None, "sha": HEAD_SHA}],
                "run_url": None,
            },
        ],
        "fetched_at": "2027-01-15T08:00:00Z",
        "responses": [
            {
                "request": "repository",
                "sha256": _sha(fake.bodies[f"{API}/repos/{REPOSITORY}"]),
            },
            {
                "request": "pull_request",
                "sha256": _sha(fake.bodies[f"{API}/repos/{REPOSITORY}/pulls/12"]),
            },
            {
                "request": "required_status_checks",
                "sha256": _sha(
                    fake.bodies[
                        f"{API}/repos/{REPOSITORY}/branches/main/protection/"
                        "required_status_checks"
                    ]
                ),
            },
            {
                "request": "reviews.page.1",
                "sha256": _sha(
                    fake.bodies[f"{API}/repos/{REPOSITORY}/pulls/12/reviews?per_page=100"]
                ),
            },
            {
                "request": "reviewer_permission",
                "sha256": _sha(
                    fake.bodies[
                        f"{API}/repos/{REPOSITORY}/collaborators/reviewer/permission"
                    ]
                ),
            },
            {
                "request": "files.page.1",
                "sha256": _sha(
                    fake.bodies[f"{API}/repos/{REPOSITORY}/pulls/12/files?per_page=100"]
                ),
            },
            {
                "request": "check_runs.page.1",
                "sha256": _sha(
                    fake.bodies[
                        f"{API}/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs?per_page=100"
                    ]
                ),
            },
            {
                "request": "commit_status.page.1",
                "sha256": _sha(
                    fake.bodies[f"{API}/repos/{REPOSITORY}/commits/{HEAD_SHA}/status?per_page=100"]
                ),
            },
            {
                "request": "pull_request_final",
                "sha256": _sha(fake.bodies[f"{API}/repos/{REPOSITORY}/pulls/12"]),
            },
        ],
    }
    lookup, exchange, *facts_requests = fake.requests
    claims = jwt.decode(
        lookup.headers["authorization"].removeprefix("Bearer "),
        PRIVATE_KEY.public_key(),
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims == {"iss": str(APP_ID), "iat": int(NOW) - 60, "exp": int(NOW) + 540}
    assert json.loads(exchange.content) == {"repositories": ["widgets"]}
    assert {request.headers["authorization"] for request in facts_requests} == {
        f"Bearer {TOKEN}"
    }
    assert all(request.headers["x-github-api-version"] for request in fake.requests)


async def test_installation_token_is_cached_per_repository_until_refresh() -> None:
    fake = FakeGitHub()
    adapter = _adapter(fake, installation_id=77)
    await _fetch(adapter)
    await _fetch(adapter)

    paths = [request.url.path for request in fake.requests]
    assert paths.count("/app/installations/77/access_tokens") == 1
    assert f"/repos/{REPOSITORY}/installation" not in paths


async def test_pagination_follows_same_origin_next_links() -> None:
    fake = FakeGitHub()
    runs_path = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs"
    page_two = f"{API}{runs_path}?per_page=100&page=2"
    fake.route(
        "GET",
        runs_path,
        httpx.Response(
            200,
            json={
                "check_runs": [
                    {"id": 4, "name": "other", "head_sha": HEAD_SHA, "status": "completed", "conclusion": "failure"}
                ]
            },
            headers={"link": f'<{page_two}>; rel="next"'},
        ),
        {
            "check_runs": [
                {
                    "id": 11,
                    "name": "backend",
                    "head_sha": HEAD_SHA, "status": "completed",
                    "conclusion": "failure",
                    "app": {"id": 15368},
                }
            ]
        },
    )
    facts = await _fetch(_adapter(fake))

    assert facts.required_checks[0].conclusion == "failure"
    assert [item.request for item in facts.responses][6:8] == [
        "check_runs.page.1",
        "check_runs.page.2",
    ]


async def test_pagination_refuses_a_foreign_origin_link() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        httpx.Response(
            200,
            json={"check_runs": []},
            headers={"link": '<https://attacker.test/collect?page=2>; rel="next"'},
        ),
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))
    assert all(request.url.host == "api.github.com" for request in fake.requests)


async def test_required_check_conclusions_fail_closed() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {"contexts": ["backend", "lint", "docs", "e2e", "wrong-app"], "checks": []},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {
            "check_runs": [
                {"id": 1, "name": "backend", "head_sha": HEAD_SHA, "status": "completed", "conclusion": "success"},
                {"id": 2, "name": "e2e", "head_sha": HEAD_SHA, "status": "in_progress", "conclusion": None},
                {"id": 3, "name": "wrong-app", "head_sha": HEAD_SHA, "status": "completed", "conclusion": "skipped"},
            ]
        },
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {
            "sha": HEAD_SHA, "statuses": [
                {"id": 23, "context": "backend", "state": "failure"},
                {"id": 24, "context": "lint", "state": "error"},
            ]
        },
    )
    facts = await _fetch(_adapter(fake))

    assert {item.name: item.conclusion for item in facts.required_checks} == {
        "backend": "failure",
        "docs": "missing",
        "e2e": "pending",
        "lint": "error",
        "wrong-app": "skipped",
    }


@pytest.mark.parametrize(
    ("older", "newer", "expected"),
    [("failure", "success", "success"), ("success", "failure", "failure")],
    ids=("rerun-passed", "rerun-failed"),
)
async def test_only_the_latest_rerun_of_a_required_check_counts(
    older: str, newer: str, expected: str
) -> None:
    fake = FakeGitHub()
    runs_path = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs"
    run = {"name": "backend", "head_sha": HEAD_SHA, "status": "completed", "app": {"id": 15368}}
    # The newer run is on the first page and the older on the second, so
    # response order cannot decide the result.
    fake.route(
        "GET",
        runs_path,
        httpx.Response(
            200,
            json={"check_runs": [{**run, "id": 900, "conclusion": newer}]},
            headers={"link": f'<{API}{runs_path}?per_page=100&page=2>; rel="next"'},
        ),
        {"check_runs": [{**run, "id": 899, "conclusion": older}]},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {
            "sha": HEAD_SHA, "statuses": [
                {"id": 31, "context": "lint", "state": "failure"},
                {"id": 32, "context": "lint", "state": "success"},
            ]
        },
    )
    facts = await _fetch(_adapter(fake))
    assert {item.name: item.conclusion for item in facts.required_checks} == {
        "backend": expected,
        "lint": "success",
    }


async def test_required_checks_are_the_union_of_checks_and_contexts() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {
            "contexts": ["backend", "docs"],
            "checks": [{"context": "backend", "app_id": 15368}, {"context": "lint", "app_id": -1}],
        },
    )
    facts = await _fetch(_adapter(fake))
    assert [
        (item.name, item.required_producer, item.conclusion) for item in facts.required_checks
    ] == [
        ("backend", "github_app:15368", "success"),
        ("docs", None, "missing"),
        ("lint", None, "success"),
    ]


async def test_app_restricted_check_ignores_other_apps_and_statuses() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {
            "check_runs": [
                {
                    "id": 12,
                    "name": "backend",
                    "head_sha": HEAD_SHA, "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 999},
                }
            ]
        },
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {"sha": HEAD_SHA, "statuses": [{"id": 22, "context": "backend", "state": "success"}, {"id": 21, "context": "lint", "state": "success"}]},
    )
    facts = await _fetch(_adapter(fake))
    assert facts.required_checks[0].conclusion == "missing"


async def test_unmerged_pull_request_reports_no_merge_commit() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(state="open", merged=False))
    facts = await _fetch(_adapter(fake))
    assert (facts.state, facts.merged, facts.landed_commit_sha) == ("open", False, None)


@pytest.mark.parametrize(
    "protection",
    [
        httpx.Response(404, json={"message": "Branch not protected"}),
        {"contexts": [], "checks": []},
    ],
    ids=("not-protected", "no-required-checks"),
)
async def test_missing_required_checks_fail_closed(protection: object) -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        protection,
    )
    with pytest.raises(ForgeRequiredChecksNotConfiguredError) as caught:
        await _fetch(_adapter(fake))
    assert caught.value.retryable is False


async def test_unknown_pull_request_is_not_found() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(404))
    with pytest.raises(ForgeChangeNotFoundError):
        await _fetch(_adapter(fake))


async def test_pull_request_from_another_repository_is_rejected() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        _pull(base={"ref": "main", "repo": {"full_name": "acme/other"}}),
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_server_error_is_retried_then_succeeds() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        httpx.Response(502),
        httpx.ConnectError("connection refused"),
        _pull(),
    )
    facts = await _fetch(_adapter(fake, clock))
    assert facts.merged is True
    assert clock.sleeps == [0.5, 1.0]


async def test_retries_exhausted_raise_facts_unavailable() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(503))
    with pytest.raises(ForgeFactsUnavailableError) as caught:
        await _fetch(_adapter(fake, clock))
    pulls = [r for r in fake.requests if r.url.path.endswith("/pulls/12")]
    assert len(pulls) == 3
    assert clock.sleeps == [0.5, 1.0]
    assert caught.value.retryable is True


async def test_total_deadline_bounds_retries() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(500))
    with pytest.raises(ForgeFactsUnavailableError):
        await _fetch(_adapter(fake, clock, deadline=1.0, attempts=5))
    assert sum(clock.sleeps) < 1.0


async def test_rate_limit_waits_for_reset_within_the_deadline() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(NOW) + 7)},
        ),
        httpx.Response(429, headers={"retry-after": "3"}),
        _pull(),
    )
    facts = await _fetch(_adapter(fake, clock))
    assert facts.merged is True
    assert clock.sleeps == [7.0, 3.0]


async def test_rate_limit_beyond_the_deadline_fails_without_waiting() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        httpx.Response(429, headers={"retry-after": "3600"}),
    )
    with pytest.raises(ForgeFactsUnavailableError):
        await _fetch(_adapter(fake, clock))
    assert clock.sleeps == []


async def test_forbidden_without_rate_limit_is_access_denied() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        httpx.Response(403, json={"message": "Resource not accessible by integration"}),
    )
    with pytest.raises(ForgeFactsAccessDeniedError):
        await _fetch(_adapter(fake))


async def test_rejected_cached_token_is_refreshed_once() -> None:
    fake = FakeGitHub()
    adapter = _adapter(fake, installation_id=77)
    await _fetch(adapter)
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(401), _pull())
    await _fetch(adapter)
    exchanges = [r for r in fake.requests if r.url.path.endswith("/access_tokens")]
    assert len(exchanges) == 2
    assert fake.requests[-1].headers["authorization"] == f"Bearer {SECOND_TOKEN}"


@pytest.mark.parametrize(
    ("repository", "number"),
    [("acme", 12), ("acme/../x", 12), ("acme/widgets/extra", 12), (REPOSITORY, 0)],
)
async def test_invalid_request_is_refused_before_any_network_call(
    repository: str, number: int
) -> None:
    fake = FakeGitHub()
    with pytest.raises(ExternalServiceConfigurationError):
        await _adapter(fake).fetch_change_facts(
            repository=repository, change_number=number, base_branch="main"
        )
    assert fake.requests == []


def _assert_secret_free(text: str, secrets: list[str]) -> None:
    for secret in secrets:
        assert secret not in text


@pytest.mark.parametrize(
    "failure",
    ["unavailable", "access_denied", "not_found", "protocol", "token_exchange_denied"],
)
async def test_credentials_never_reach_errors_logs_or_reprs(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeGitHub()
    pulls = f"/repos/{REPOSITORY}/pulls/12"
    if failure == "unavailable":
        fake.route("GET", pulls, httpx.ConnectError(f"refused Bearer {TOKEN}"))
    elif failure == "access_denied":
        fake.route("GET", pulls, httpx.Response(401))
    elif failure == "not_found":
        fake.route("GET", pulls, httpx.Response(404))
    elif failure == "protocol":
        fake.route("GET", pulls, httpx.Response(200, content=f"not json {TOKEN}".encode()))
    else:
        fake.route("POST", "/app/installations/77/access_tokens", httpx.Response(403))
    adapter = _adapter(fake)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ExternalServiceAdapterError) as caught:
        await _fetch(adapter)

    error = caught.value
    rendered = "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__suppress_context__ is True
    log_text = "\n".join(
        f"{record.getMessage()} {record.args!r} {record.__dict__!r}" for record in caplog.records
    )
    secrets = fake.secrets()
    assert len(secrets) > 3
    for text in (str(error), repr(error), rendered, log_text, repr(adapter)):
        _assert_secret_free(text, secrets)


async def test_successful_facts_and_token_holder_are_secret_free(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeGitHub()
    caplog.set_level(logging.DEBUG)
    adapter = _adapter(fake)
    facts = await _fetch(adapter)
    secrets = fake.secrets()
    texts = [
        facts.model_dump_json(),
        repr(facts),
        repr(adapter),
        repr(_InstallationToken(TOKEN, NOW)),
        "\n".join(record.getMessage() for record in caplog.records),
    ]
    for text in texts:
        _assert_secret_free(text, secrets)


def _settings(**values: object) -> Settings:
    configured: dict[str, object] = {
        "environment": "test",
        "github_app_id": APP_ID,
        "github_app_private_key": PRIVATE_PEM,
        "github_api_base_url": API,
    }
    configured.update(values)
    return Settings(_env_file=None, **configured)


async def test_factory_registers_github_as_a_forge_provider() -> None:
    fake = FakeGitHub()
    factory = forge_facts_adapter_factory(
        _settings(github_app_installation_id=77),
        transport=httpx.MockTransport(fake.handler),
    )
    adapter = factory.create("github")
    assert (adapter.identity.capability_key, adapter.identity.provider_key) == (
        "forge_facts",
        "github",
    )
    facts = await _fetch(adapter)
    assert facts.repository == REPOSITORY


def test_factory_refuses_missing_or_unusable_credentials() -> None:
    unconfigured = Settings(_env_file=None, environment="test")
    with pytest.raises(ExternalServiceConfigurationError):
        forge_facts_adapter_factory(unconfigured).create("github")
    unusable = "-----BEGIN PRIVATE KEY-----\nnot-a-key\n-----END PRIVATE KEY-----\n"
    with pytest.raises(ExternalServiceConfigurationError) as caught:
        forge_facts_adapter_factory(_settings(github_app_private_key=unusable)).create(
            "github"
        )
    assert caught.value.__cause__ is None


def test_private_key_setting_is_redacted_and_accepts_escaped_newlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    assert settings.github_app_private_key is not None
    assert settings.github_app_private_key.get_secret_value() == PRIVATE_PEM
    for text in (repr(settings), str(settings.model_dump()), settings.model_dump_json()):
        assert PEM_BODY_LINE not in text
    monkeypatch.setenv("WORKSTREAM_GITHUB_APP_PRIVATE_KEY", PRIVATE_PEM.replace("\n", "\\n"))
    from_environment = Settings(_env_file=None, environment="test", github_app_id=APP_ID)
    assert from_environment.github_app_private_key is not None
    assert from_environment.github_app_private_key.get_secret_value() == PRIVATE_PEM


def test_invalid_private_key_setting_error_omits_the_value() -> None:
    bogus = "not-a-pem-secret-value-0123456789"
    with pytest.raises(ValueError) as caught:
        _settings(github_app_private_key=bogus)
    assert bogus not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "values",
    [
        {"github_app_private_key": None},
        {"github_app_id": None},
        {"github_api_base_url": "http://api.github.example"},
        {"github_api_base_url": "https://user:pass@api.github.com"},
        {"github_api_base_url": "https://api.github.com/"},
        {"github_api_base_url": "http://127.0.0.1:8080", "environment": "production"},
        {"github_facts_total_deadline_seconds": 5.0},
        {"github_facts_total_deadline_seconds": 121.0},
    ],
)
def test_settings_reject_incomplete_or_unsafe_configuration(values: dict) -> None:
    with pytest.raises(ValueError):
        _settings(**values)


def test_settings_accept_loopback_http_only_for_local_and_test() -> None:
    settings = _settings(github_api_base_url="http://127.0.0.1:8080")
    assert settings.github_api_base_url == "http://127.0.0.1:8080"


async def test_reviews_and_files_paginate_and_reviews_are_returned_unfiltered() -> None:
    fake = FakeGitHub()
    reviews_path = f"/repos/{REPOSITORY}/pulls/12/reviews"
    files_path = f"/repos/{REPOSITORY}/pulls/12/files"
    fake.route(
        "GET",
        reviews_path,
        httpx.Response(
            200,
            json=[REVIEWS[0]],
            headers={"link": f'<{API}{reviews_path}?per_page=100&page=2>; rel="next"'},
        ),
        [{**REVIEWS[0], "id": 63, "state": "CHANGES_REQUESTED"}],
    )
    page_one = [{"filename": f"f{index}.py", "status": "added"} for index in range(100)]
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(changed_files=101))
    fake.route(
        "GET",
        files_path,
        httpx.Response(
            200,
            json=page_one,
            headers={"link": f'<{API}{files_path}?per_page=100&page=2>; rel="next"'},
        ),
        [{"filename": "last.py", "status": "added"}],
    )
    facts = await _fetch(_adapter(fake))
    assert [(item.id, item.state) for item in facts.reviews] == [
        ("61", "approved"),
        ("63", "changes_requested"),
    ]
    assert len(facts.changed_files) == facts.changed_files_count == 101
    assert [item.request for item in facts.responses][3:8] == [
        "reviews.page.1",
        "reviews.page.2",
        "reviewer_permission",
        "files.page.1",
        "files.page.2",
    ]


async def test_more_changed_files_than_github_can_list_is_not_eligible() -> None:
    # A permanent property of the change, not an outage: no facts, so the
    # checker fails the proof instead of an Operator retrying forever.
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(changed_files=3001))
    with pytest.raises(ForgeChangeNotEligibleError):
        await _fetch(_adapter(fake))
    assert not any(request.url.path.endswith("/files") for request in fake.requests)


async def test_changed_file_listing_shorter_than_reported_fails_closed() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(changed_files=3))
    with pytest.raises(ForgeFactsIncompleteError):
        await _fetch(_adapter(fake))


async def test_check_run_app_and_status_source_are_recorded() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {"contexts": ["lint"], "checks": []},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {
            "check_runs": [
                {
                    "id": 5,
                    "name": "lint",
                    "head_sha": HEAD_SHA, "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 777},
                }
            ]
        },
    )
    fake.route("GET", f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status", {"sha": HEAD_SHA, "statuses": []})
    facts = await _fetch(_adapter(fake))
    check = facts.required_checks[0]
    assert (check.required_producer, check.judged) == (
        None,
        (ForgeJudgedResultFact(producer="github_app:777", sha=HEAD_SHA),),
    )


def _pull_reads(fake: FakeGitHub) -> int:
    return sum(1 for r in fake.requests if r.url.path == f"/repos/{REPOSITORY}/pulls/12")


async def test_pull_request_moving_once_is_reread_and_bound_to_one_state() -> None:
    fake = FakeGitHub()
    moved = _pull(head={"sha": "c" * 40})
    # The first whole read ends on a moved head; the second sees one state.
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(), moved, _pull())
    facts = await _fetch(_adapter(fake))
    assert facts.head_sha == HEAD_SHA
    assert _pull_reads(fake) == 4
    labels = [item.request for item in facts.responses]
    assert labels[:2] == ["repository", "pull_request"]
    assert labels[-1] == "pull_request_final"
    assert labels.count("pull_request") == 1


async def test_head_that_keeps_moving_fails_closed_as_inconsistent() -> None:
    fake = FakeGitHub()
    shas = [f"{index:x}" * 40 for index in range(1, 8)]
    for sha in shas:
        fake.route("GET", f"/repos/{REPOSITORY}/commits/{sha}/check-runs", {"check_runs": []})
        fake.route("GET", f"/repos/{REPOSITORY}/commits/{sha}/status", {"sha": sha, "statuses": []})
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", *(_pull(head={"sha": sha}) for sha in shas))
    with pytest.raises(ForgeFactsInconsistentError) as caught:
        await _fetch(_adapter(fake))
    assert caught.value.retryable is True
    assert _pull_reads(fake) == 6


async def test_merged_flag_flipping_during_the_read_is_inconsistent() -> None:
    fake = FakeGitHub()
    open_pull = _pull(state="open", merged=False)
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        open_pull, _pull(), open_pull, _pull(), open_pull, _pull(),
    )
    with pytest.raises(ForgeFactsInconsistentError):
        await _fetch(_adapter(fake))


async def test_check_run_for_another_commit_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {"check_runs": [{"id": 9, "name": "backend", "head_sha": "c" * 40,
                         "status": "completed", "conclusion": "success",
                         "app": {"id": 15368}}]},
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_combined_status_for_another_commit_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {"sha": "c" * 40, "statuses": []},
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


@pytest.mark.parametrize(
    ("app_id", "details_url", "expected"),
    [
        (15368, RUN_DETAILS_URL, RUN_URL),
        (15368, RUN_URL, RUN_URL),
        (999, RUN_DETAILS_URL, None),
        (15368, "https://github.com/acme/other/actions/runs/345/job/1", None),
        (15368, f"https://example.test/{REPOSITORY}/actions/runs/345", None),
        (15368, None, None),
    ],
    ids=("actions-job", "actions-run", "other-app", "other-repo", "other-host", "none"),
)
async def test_run_url_comes_only_from_actions_runs_of_this_repository(
    app_id: int, details_url: str | None, expected: str | None
) -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {"contexts": [], "checks": [{"context": "backend", "app_id": app_id}]},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {"check_runs": [{"id": 9, "name": "backend", "head_sha": HEAD_SHA,
                         "status": "completed", "conclusion": "success",
                         "details_url": details_url, "app": {"id": app_id}}]},
    )
    facts = await _fetch(_adapter(fake))
    assert facts.required_checks[0].run_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/widgets/pull/12/",
        "https://github.com/acme/widgets/pull/12?x=1",
        "https://github.com/acme/widgets/pull/12#top",
        "https://github.com:443/acme/widgets/pull/12",
        "https://user@github.com/acme/widgets/pull/12",
        "https://github.com/acme/widgets/pull/%31%32",
        "https://github.com/acme\\widgets/pull/12",
        "https://github.com/acme/widgets/pull/012",
        "https://github.com/acme/widgéts/pull/12",
        "http://github.com/acme/widgets/pull/12",
        "https://github.com/acme/widgets/pulls/12",
        "https://github.com/acme/../pull/12",
        12,
    ],
)
def test_pull_request_url_parser_rejects_noncanonical_forms(url: object) -> None:
    assert _adapter(FakeGitHub()).parse_change_url(url) is None


def test_pull_request_url_parser_returns_repository_and_number() -> None:
    assert _adapter(FakeGitHub()).parse_change_url(
        "https://github.com/Acme/widgets.v2/pull/12"
    ) == ("Acme/widgets.v2", 12)



# Fail-closed branches: each malformed or hostile response is rejected ---------

PROTECTION = f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks"
RUNS = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs"
STATUS = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status"
EC_KEY = ec.generate_private_key(ec.SECP256R1())


def test_private_key_loader_rejects_oversized_and_non_rsa_keys() -> None:
    oversized = PRIVATE_PEM + "\n" + "A" * 20_000
    ec_pem = EC_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    for value in (oversized, ec_pem, "é" * 10):
        with pytest.raises(ExternalServiceConfigurationError) as caught:
            load_github_app_private_key(SecretStr(value))
        assert caught.value.__cause__ is None
    with pytest.raises(ExternalServiceConfigurationError):
        GitHubAppFactsAdapter(
            GitHubAppFactsConfiguration(
                app_id=APP_ID,
                installation_id=None,
                api_base_url=API,
                request_timeout_seconds=10.0,
                total_deadline_seconds=45.0,
                maximum_attempts=3,
            ),
            EC_KEY,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "lookup",
    [{}, {"id": "77"}, {"id": 0}, []],
    ids=("no-id", "string-id", "zero-id", "not-object"),
)
async def test_unusable_installation_lookup_is_a_protocol_error(lookup: object) -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/installation", lookup)
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


@pytest.mark.parametrize(
    "token_body",
    [
        {"token": TOKEN, "expires_at": "later"},
        {"token": TOKEN, "expires_at": "2027-01-15T09:00:00"},
        {"token": TOKEN},
        {"token": "", "expires_at": "2027-01-15T09:00:00Z"},
        {"token": "ghs_bad token", "expires_at": "2027-01-15T09:00:00Z"},
        {"token": 5, "expires_at": "2027-01-15T09:00:00Z"},
        [],
    ],
    ids=("bad-expiry", "naive-expiry", "no-expiry", "empty", "whitespace", "non-string", "list"),
)
async def test_unusable_token_exchange_is_a_protocol_error(token_body: object) -> None:
    fake = FakeGitHub()
    fake.route(
        "POST",
        "/app/installations/77/access_tokens",
        httpx.Response(201, json=token_body),
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))
    assert not any(r.url.path.endswith("/pulls/12") for r in fake.requests)


async def test_app_jwt_rejected_is_access_denied() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/installation", httpx.Response(401))
    with pytest.raises(ForgeFactsAccessDeniedError):
        await _fetch(_adapter(fake))


async def test_unexpected_client_error_is_a_protocol_error_without_retry() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(422))
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake, clock))
    assert clock.sleeps == []


@pytest.mark.parametrize(
    "headers",
    [
        {"retry-after": "soon"},
        {"x-ratelimit-remaining": "0"},
        {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "tomorrow"},
    ],
    ids=("bad-retry-after", "no-reset", "bad-reset"),
)
async def test_forbidden_with_unusable_rate_limit_headers_is_access_denied(
    headers: dict,
) -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(403, headers=headers))
    with pytest.raises(ForgeFactsAccessDeniedError):
        await _fetch(_adapter(fake, clock))
    assert clock.sleeps == []


async def test_deadline_spent_by_one_slow_response_stops_further_requests() -> None:
    fake = FakeGitHub()
    clock = Clock()

    def slow_pull(_request: httpx.Request) -> httpx.Response:
        clock.now += 60.0
        return httpx.Response(200, json=_pull())

    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", slow_pull)
    with pytest.raises(ForgeFactsUnavailableError):
        await _fetch(_adapter(fake, clock, deadline=45.0))
    assert not any(r.url.path == PROTECTION for r in fake.requests)


async def test_facts_completed_after_the_deadline_are_discarded() -> None:
    fake = FakeGitHub()
    clock = Clock()
    reads = []

    def pull(_request: httpx.Request) -> httpx.Response:
        reads.append(clock.now)
        if len(reads) == 2:
            clock.now += 60.0  # the final consistency re-read returns late
        return httpx.Response(200, json=_pull())

    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", pull)
    with pytest.raises(ForgeFactsUnavailableError):
        await _fetch(_adapter(fake, clock, deadline=45.0))
    assert len(reads) == 2


async def test_total_deadline_is_absolute_when_github_stalls() -> None:
    fake = FakeGitHub()

    async def stalled(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{REPOSITORY}/pulls/12":
            await asyncio.sleep(30)
        return fake.handler(request)

    adapter = GitHubAppFactsAdapter(
        GitHubAppFactsConfiguration(
            app_id=APP_ID,
            installation_id=None,
            api_base_url=API,
            request_timeout_seconds=10.0,
            total_deadline_seconds=0.05,
            maximum_attempts=3,
        ),
        PRIVATE_KEY,
        transport=httpx.MockTransport(stalled),
        wall_clock=lambda: NOW,
    )
    started = time.monotonic()
    with pytest.raises(ForgeFactsUnavailableError):
        await _fetch(adapter)
    assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    "pull",
    [
        [],
        {k: v for k, v in _pull().items() if k != "base"},
        _pull(head={"sha": None}),
        _pull(changed_files="2"),
        _pull(changed_files=-1),
        _pull(number=13),
        _pull(user=None),
        _pull(user={"login": "agent-bot", "id": 501}),
        _pull(merged=True, merge_commit_sha="not-a-sha"),
        _pull(state="draft"),
    ],
    ids=(
        "not-object",
        "no-base",
        "null-head",
        "string-file-count",
        "negative-file-count",
        "other-number",
        "null-author",
        "author-without-type",
        "bad-merge-sha",
        "unknown-state",
    ),
)
async def test_malformed_pull_request_is_a_protocol_error(pull: object) -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", pull)
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


@pytest.mark.parametrize(
    "protection",
    [
        [],
        {"checks": "backend", "contexts": []},
        {"checks": [], "contexts": "backend"},
        {"checks": [{"app_id": 1}], "contexts": []},
        {"checks": [{"context": "", "app_id": 1}], "contexts": []},
        {"checks": ["backend"], "contexts": []},
        {"checks": [], "contexts": [7]},
    ],
    ids=(
        "not-object",
        "checks-not-list",
        "contexts-not-list",
        "check-without-context",
        "empty-context",
        "check-not-object",
        "context-not-string",
    ),
)
async def test_malformed_branch_protection_is_a_protocol_error(protection: object) -> None:
    fake = FakeGitHub()
    fake.route("GET", PROTECTION, protection)
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (RUNS, {"check_runs": "backend"}),
        (RUNS, {"check_runs": ["backend"]}),
        (RUNS, []),
        (f"/repos/{REPOSITORY}/pulls/12/reviews", {"reviews": []}),
        (STATUS, {"sha": HEAD_SHA, "statuses": None}),
    ],
    ids=("runs-not-list", "run-not-object", "runs-body-list", "reviews-object", "statuses-null"),
)
async def test_malformed_listing_page_is_a_protocol_error(path: str, body: object) -> None:
    fake = FakeGitHub()
    fake.route("GET", path, body)
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_review_listing_longer_than_the_page_bound_is_not_eligible() -> None:
    # Anyone can flood a change with reviews: no facts, never an endless retry.
    fake = FakeGitHub()
    reviews = f"/repos/{REPOSITORY}/pulls/12/reviews"
    fake.route(
        "GET",
        reviews,
        httpx.Response(
            200,
            json=[REVIEWS[0]],
            headers={"link": f'<{API}{reviews}?per_page=100&page=99>; rel="next"'},
        ),
    )
    with pytest.raises(ForgeChangeNotEligibleError):
        await _fetch(_adapter(fake))
    assert sum(r.url.path == reviews for r in fake.requests) == 10


@pytest.mark.parametrize(
    ("runs", "statuses"),
    [
        ([{"name": "lint", "head_sha": HEAD_SHA, "status": "completed",
           "conclusion": "success"}], []),
        ([{"id": "5", "name": "lint", "head_sha": HEAD_SHA, "status": "completed",
           "conclusion": "success"}], []),
        ([{"id": 5, "name": "lint", "head_sha": HEAD_SHA, "status": "completed",
           "conclusion": "success", "app": {"id": "15368"}}], []),
        ([{"id": 5, "name": "lint", "head_sha": HEAD_SHA, "status": "completed",
           "conclusion": "exploded"}], []),
        ([], [{"id": 1, "context": "lint", "state": "green"}]),
        ([], [{"context": "lint", "state": "success"}]),
    ],
    ids=(
        "run-without-id",
        "run-string-id",
        "run-string-app-id",
        "unknown-conclusion",
        "unknown-status-state",
        "status-without-id",
    ),
)
async def test_malformed_check_result_is_a_protocol_error(runs: list, statuses: list) -> None:
    fake = FakeGitHub()
    fake.route("GET", PROTECTION, {"contexts": ["lint"], "checks": []})
    fake.route("GET", RUNS, {"check_runs": runs})
    fake.route("GET", STATUS, {"sha": HEAD_SHA, "statuses": statuses})
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_malformed_review_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12/reviews",
        [{**REVIEWS[0], "commit_id": "not-a-sha"}],
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


def test_facts_model_rejects_a_noncanonical_repository() -> None:
    facts = ForgeChangeFacts.model_validate(
        {
            "forge": "github",
            "forge_origin": "https://github.com",
            "repository": REPOSITORY,
            "change_number": 12,
            "change_url": f"https://github.com/{REPOSITORY}/pull/12",
            "state": "closed",
            "merged": True,
            "landed_commit_sha": MERGE_SHA,
            "base_ref": "main",
            "head_sha": HEAD_SHA,
            "author": {"login": "a", "id": 1, "kind": "user"},
            "reviews": [],
            "changed_files_count": 0,
            "changed_files": [],
            "required_checks": [
                {
                    "name": "backend",
                    "conclusion": "success",
                    "required_producer": "github_app:1",
                    "judged": [{"producer": "github_app:1", "sha": HEAD_SHA}],
                    "run_url": None,
                }
            ],
            "fetched_at": "2027-01-15T08:00:00Z",
            "responses": [{"request": "pull_request", "sha256": "sha256:" + "0" * 64}],
        }
    )
    for repository in ("acme", "acme/..", "acme//widgets", "acme/" + "w" * 251):
        with pytest.raises(ValidationError):
            ForgeChangeFacts.model_validate(
                {**facts.model_dump(), "repository": repository}
            )


async def test_github_accounts_and_review_states_map_to_neutral_values() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        _pull(user={"login": "acme-org", "id": 900, "type": "Organization"}),
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12/reviews",
        [
            {**REVIEWS[0], "id": 70, "state": "DISMISSED"},
            {**REVIEWS[0], "id": 71, "state": "SOMETHING_NEW"},
            {**REVIEWS[0], "id": 72, "user": {"login": "ghost", "id": 9, "type": "Mannequin"}},
        ],
    )
    facts = await _fetch(_adapter(fake))
    assert facts.author.kind == "other"
    assert [(item.id, item.state) for item in facts.reviews] == [
        ("70", "dismissed"),
        ("71", "other"),
        ("72", "approved"),
    ]
    assert facts.reviews[2].reviewer.kind == "other"
    # Only reviewers approving the head commit are asked about write access.
    assert facts.reviews[2].reviewer_write_access is False
    assert facts.reviews[0].reviewer_write_access is None


async def test_pull_request_url_other_than_the_canonical_change_url_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        _pull(html_url=f"https://github.com/{REPOSITORY}/pull/12/"),
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_check_run_and_commit_status_are_both_judged_for_an_unbound_check() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {"contexts": ["lint"], "checks": []},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {"check_runs": [{"id": 5, "name": "lint", "head_sha": HEAD_SHA,
                         "status": "completed", "conclusion": "success",
                         "app": {"id": 15368}}]},
    )
    facts = await _fetch(_adapter(fake))
    assert facts.required_checks[0].judged == (
        ForgeJudgedResultFact(producer="github_app:15368", sha=HEAD_SHA),
        ForgeJudgedResultFact(producer=None, sha=HEAD_SHA),
    )


def test_facts_model_binds_the_file_count_and_accepts_sha256_object_names() -> None:
    base = {
        "forge": "github",
        "forge_origin": "https://github.com",
        "repository": REPOSITORY,
        "change_number": 12,
        "change_url": f"https://github.com/{REPOSITORY}/pull/12",
        "state": "open",
        "merged": False,
        "landed_commit_sha": None,
        "base_ref": "main",
        "head_sha": "c" * 64,
        "author": {"login": "a", "id": 1, "kind": "user"},
        "reviews": [],
        "changed_files_count": 0,
        "changed_files": [],
        "required_checks": [
            {"name": "ci", "conclusion": "pending", "required_producer": None,
             "judged": [], "run_url": None}
        ],
        "fetched_at": "2027-01-15T08:00:00Z",
        "responses": [{"request": "pull_request", "sha256": "sha256:" + "0" * 64}],
    }
    assert ForgeChangeFacts.model_validate(base).head_sha == "c" * 64
    with pytest.raises(ValidationError):
        ForgeChangeFacts.model_validate({**base, "changed_files_count": 1})
    with pytest.raises(ValidationError):
        ForgeChangeFacts.model_validate({**base, "forge": "gitlab"})
    unjudged = {**base["required_checks"][0], "conclusion": "success"}
    with pytest.raises(ValidationError):
        ForgeChangeFacts.model_validate({**base, "required_checks": [unjudged]})


# Revision 2: forge instance, reviewer write access, eligibility -----------------


@pytest.mark.parametrize(
    ("api", "origin"),
    [
        ("https://api.github.com", "https://github.com"),
        ("https://ghe.example/api/v3", "https://ghe.example"),
        ("https://ghe.example:8443/api/v3", "https://ghe.example:8443"),
    ],
)
def test_web_origin_follows_the_configured_api(api: str, origin: str) -> None:
    assert github_web_origin(api) == origin


async def test_enterprise_instance_names_its_own_origin_in_every_url() -> None:
    fake = FakeGitHub()
    fake.prefix = "/api/v3"
    origin = "https://ghe.example"
    fake.route(
        "GET", f"/repos/{REPOSITORY}/pulls/12", _pull(html_url=f"{origin}/{REPOSITORY}/pull/12")
    )
    check_runs = fake.routes[("GET", f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs")][0]
    check_runs["check_runs"][0]["details_url"] = f"{origin}/{REPOSITORY}/actions/runs/345/job/678"
    adapter = _adapter(fake, api=f"{origin}/api/v3")

    facts = await _fetch(adapter)

    assert adapter.forge_origin == facts.forge_origin == origin
    assert facts.change_url == f"{origin}/{REPOSITORY}/pull/12"
    assert facts.required_checks[0].run_url == f"{origin}/{REPOSITORY}/actions/runs/345"
    assert adapter.parse_change_url(f"{origin}/{REPOSITORY}/pull/12") == (REPOSITORY, 12)
    assert adapter.parse_change_url(f"https://github.com/{REPOSITORY}/pull/12") is None


async def test_github_com_pull_request_url_on_an_enterprise_instance_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.prefix = "/api/v3"
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake, api="https://ghe.example/api/v3"))


async def test_change_into_another_base_branch_is_not_eligible() -> None:
    fake = FakeGitHub()
    with pytest.raises(ForgeChangeNotEligibleError):
        await _adapter(fake).fetch_change_facts(
            repository=REPOSITORY, change_number=12, base_branch="dev"
        )
    assert not any("/protection/" in request.url.path for request in fake.requests)


async def test_repository_the_app_cannot_read_is_access_denied_not_a_missing_change() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}", httpx.Response(404, json={}))
    with pytest.raises(ForgeFactsAccessDeniedError):
        await _fetch(_adapter(fake))
    assert not any(request.url.path.endswith("/pulls/12") for request in fake.requests)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"permission": "admin", "user": {"login": "reviewer", "id": 7}}, True),
        ({"permission": "maintain", "user": {"login": "reviewer", "id": 7}}, True),
        ({"permission": "read", "user": {"login": "reviewer", "id": 7}}, False),
        ({"permission": "triage", "user": {"login": "reviewer", "id": 7}}, False),
        ({"permission": "none", "user": {"login": "reviewer", "id": 7}}, False),
        # The login now names another account: never this reviewer's access.
        ({"permission": "write", "user": {"login": "reviewer", "id": 8}}, False),
        (httpx.Response(404, json={}), False),
    ],
    ids=("admin", "maintain", "read", "triage", "none", "renamed", "not-collaborator"),
)
async def test_only_current_write_access_is_reported_for_an_approving_reviewer(
    response: object, expected: bool
) -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/collaborators/reviewer/permission", response)
    facts = await _fetch(_adapter(fake))
    assert facts.reviews[0].reviewer_write_access is expected


async def test_write_access_is_read_only_for_approvals_of_the_head_commit() -> None:
    fake = FakeGitHub()
    reviewer = {"login": "other", "id": 8, "type": "User"}
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12/reviews",
        [
            {**REVIEWS[0], "id": 1, "user": reviewer, "commit_id": MERGE_SHA},
            {**REVIEWS[0], "id": 2, "user": reviewer, "state": "COMMENTED"},
        ],
    )
    facts = await _fetch(_adapter(fake))
    assert [item.reviewer_write_access for item in facts.reviews] == [None, None]
    assert not any("/collaborators/" in request.url.path for request in fake.requests)


async def test_malformed_permission_response_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET", f"/repos/{REPOSITORY}/collaborators/reviewer/permission", {"permission": "write"}
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_more_approving_users_than_the_bound_is_not_eligible() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12/reviews",
        [
            {**REVIEWS[0], "id": index, "user": {"login": f"r{index}", "id": index, "type": "User"}}
            for index in range(1, 22)
        ],
    )
    with pytest.raises(ForgeChangeNotEligibleError):
        await _fetch(_adapter(fake))


async def test_reviews_are_reported_oldest_first_by_github_id() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12/reviews",
        [
            {**REVIEWS[0], "id": 100, "state": "CHANGES_REQUESTED"},
            {**REVIEWS[0], "id": 70},
        ],
    )
    facts = await _fetch(_adapter(fake))
    assert [(item.id, item.state) for item in facts.reviews] == [
        ("70", "approved"),
        ("100", "changes_requested"),
    ]


async def test_review_without_an_integer_id_is_a_protocol_error() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET", f"/repos/{REPOSITORY}/pulls/12/reviews", [{**REVIEWS[0], "id": "61"}]
    )
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


@pytest.mark.parametrize(
    "error",
    [httpx.DecodingError("bad body"), httpx.TooManyRedirects("loop"), httpx.InvalidURL("bad")],
    ids=("decoding", "redirects", "invalid-url"),
)
async def test_non_transport_http_client_errors_are_protocol_errors(error: Exception) -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", error)
    with pytest.raises(ForgeFactsProtocolError):
        await _fetch(_adapter(fake))


@pytest.mark.parametrize(
    ("changes", "valid"),
    [
        ({}, True),
        ({"merged": True, "state": "open"}, False),
        ({"merged": True, "landed_commit_sha": None}, False),
        ({"merged": False, "state": "open"}, False),
        ({"forge_origin": "https://github.com/"}, False),
        ({"forge_origin": "http://github.com"}, False),
        ({"repository": "group/subgroup/project"}, True),
    ],
)
def test_facts_model_binds_landed_commit_and_forge_origin(changes: dict, valid: bool) -> None:
    body = {
        "forge": "github",
        "forge_origin": "https://github.com",
        "repository": REPOSITORY,
        "change_number": 12,
        "change_url": f"https://github.com/{REPOSITORY}/pull/12",
        "state": "closed",
        "merged": True,
        "landed_commit_sha": MERGE_SHA,
        "base_ref": "main",
        "head_sha": HEAD_SHA,
        "author": {"login": "a", "id": 1, "kind": "user"},
        "reviews": [],
        "changed_files_count": 0,
        "changed_files": [],
        "required_checks": [
            {"name": "ci", "conclusion": "pending", "required_producer": None,
             "judged": [], "run_url": None}
        ],
        "fetched_at": "2027-01-15T08:00:00Z",
        "responses": [{"request": "pull_request", "sha256": "sha256:" + "0" * 64}],
        **changes,
    }
    if valid:
        ForgeChangeFacts.model_validate(body)
    else:
        with pytest.raises(ValidationError):
            ForgeChangeFacts.model_validate(body)


def _proof_checker():
    """Load the networkless checker the way its own tests do."""
    root = Path(__file__).parents[2] / "external_checkers" / "harnessy_proof"
    spec = importlib.util.spec_from_file_location("harnessy_proof_checker", root / "checker.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "variant", ["merged", "open", "enterprise"], ids=("merged", "open", "enterprise")
)
async def test_provider_facts_satisfy_the_checker_facts_contract(variant: str) -> None:
    # The two sides of decision 21 share one contract; drift fails here.
    fake = FakeGitHub()
    api = API
    if variant == "open":
        fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(state="open", merged=False))
    if variant == "enterprise":
        fake.prefix, api = "/api/v3", "https://ghe.example/api/v3"
        fake.route(
            "GET",
            f"/repos/{REPOSITORY}/pulls/12",
            _pull(html_url=f"https://ghe.example/{REPOSITORY}/pull/12"),
        )
    facts = (await _fetch(_adapter(fake, api=api))).model_dump(mode="json")

    checker = _proof_checker()
    assert checker.valid_facts(facts)
    assert checker.qualifying_approvals(facts) == ["reviewer"]


async def test_approving_bot_has_no_write_access_and_is_never_looked_up() -> None:
    fake = FakeGitHub()
    bot = {"login": "copilot[bot]", "id": 99, "type": "Bot"}
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12/reviews",
        [REVIEWS[0], {**REVIEWS[0], "id": 63, "user": bot}],
    )
    facts = await _fetch(_adapter(fake))
    assert [item.reviewer_write_access for item in facts.reviews] == [True, False]
    assert not any("copilot" in request.url.path for request in fake.requests)


async def test_check_run_listing_longer_than_the_page_bound_is_not_eligible() -> None:
    fake = FakeGitHub()
    runs = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs"
    fake.route(
        "GET",
        runs,
        httpx.Response(
            200,
            json={"check_runs": []},
            headers={"link": f'<{API}{runs}?per_page=100&page=99>; rel="next"'},
        ),
    )
    with pytest.raises(ForgeChangeNotEligibleError):
        await _fetch(_adapter(fake))


async def test_token_refused_for_a_repository_outside_the_installation_is_access_denied() -> None:
    fake = FakeGitHub()
    fake.route(
        "POST", "/app/installations/77/access_tokens", httpx.Response(422, json={})
    )
    with pytest.raises(ForgeFactsAccessDeniedError):
        await _fetch(_adapter(fake))


def test_api_without_an_https_web_origin_is_refused_when_configured() -> None:
    with pytest.raises(ExternalServiceConfigurationError):
        _adapter(FakeGitHub(), api="http://127.0.0.1:8080")


def test_enterprise_web_origin_is_lowercased() -> None:
    adapter = _adapter(FakeGitHub(), api="https://GHE.Example/api/v3")
    assert adapter.forge_origin == "https://ghe.example"
