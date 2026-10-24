"""GitHub App adapter that reads pull-request proof facts with bounded retries.

Credential custody: the RSA private key is held only as a parsed key object,
and installation tokens only inside ``_InstallationToken``. Neither is placed in
an exception, log record, representation or returned fact. Every adapter error
is raised ``from None`` so that no HTTP exception carrying request headers is
chained to it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import logging
import re
import time
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import SecretStr, ValidationError

from app.interfaces.external_services import (
    ExternalServiceAdapterIdentity,
    ExternalServiceConfigurationError,
)
from app.interfaces.github_facts import (
    GITHUB_APP_PROVIDER_KEY,
    GITHUB_FACTS_CAPABILITY_KEY,
    GitHubFactsAccessDeniedError,
    GitHubFactsProtocolError,
    GitHubFactsUnavailableError,
    GITHUB_MAXIMUM_LISTED_FILES,
    GitHubActorFact,
    GitHubChangedFileFact,
    GitHubFactsIncompleteError,
    GitHubFactsInconsistentError,
    GitHubPullRequestFacts,
    GitHubPullRequestNotFoundError,
    GitHubRequiredCheckFact,
    GitHubReviewFact,
    GitHubRequiredChecksNotConfiguredError,
    GitHubResponseDigest,
    is_github_repository,
)

logger = logging.getLogger(__name__)

GITHUB_API_VERSION = "2022-11-28"
MAXIMUM_PAGES = 10
PAGE_SIZE = 100
MAXIMUM_PRIVATE_KEY_BYTES = 16_384
# GitHub accepts App JWTs for at most ten minutes; backdate for clock drift.
JWT_BACKDATE_SECONDS = 60
JWT_LIFETIME_SECONDS = 540
# Refresh an installation token this long before GitHub's stated expiry.
TOKEN_REFRESH_MARGIN_SECONDS = 300
INITIAL_BACKOFF_SECONDS = 0.5
GITHUB_ACTIONS_APP_ID = 15368
_ACTIONS_DETAILS_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})"
    r"/actions/runs/([1-9][0-9]{0,18})(?:/job/[1-9][0-9]{0,18})?"
)
# Whole facts reads attempted when the pull request moves during a read.
FACTS_CONSISTENCY_ATTEMPTS = 3
_BOUND_PULL_FIELDS = (
    "head_sha",
    "merged",
    "merge_commit_sha",
    "base_ref",
    "state",
    "changed_files_count",
)
_CHECK_RUN_CONCLUSIONS = frozenset(
    {
        "success",
        "failure",
        "neutral",
        "cancelled",
        "skipped",
        "timed_out",
        "action_required",
        "stale",
    }
)
_STATUS_STATES = frozenset({"success", "failure", "error", "pending"})
_IDENTITY = ExternalServiceAdapterIdentity(GITHUB_FACTS_CAPABILITY_KEY, GITHUB_APP_PROVIDER_KEY)


class _InstallationToken:
    """Installation access token whose value never appears in a representation."""

    __slots__ = ("_value", "refresh_at")

    def __init__(self, value: str, refresh_at: float) -> None:
        self._value = value
        self.refresh_at = refresh_at

    def header(self) -> str:
        """Return the Authorization header value for one GitHub request."""
        return f"Bearer {self._value}"

    def __repr__(self) -> str:
        """Redact the token value."""
        return "_InstallationToken(<redacted>)"


@dataclass(frozen=True, slots=True)
class GitHubAppFactsConfiguration:
    """Validated non-secret adapter limits and endpoints."""

    app_id: int
    installation_id: int | None
    api_base_url: str
    request_timeout_seconds: float
    total_deadline_seconds: float
    maximum_attempts: int


def load_github_app_private_key(secret: SecretStr) -> RSAPrivateKey:
    """Parse one bounded PEM RSA key without exposing its bytes."""
    key: object = None
    try:
        data = secret.get_secret_value().encode("ascii")
        if len(data) <= MAXIMUM_PRIVATE_KEY_BYTES:
            key = load_pem_private_key(data, password=None)
    except (UnicodeEncodeError, ValueError, TypeError):
        key = None
    data = b""
    if not isinstance(key, RSAPrivateKey):
        raise ExternalServiceConfigurationError(_IDENTITY) from None
    return key


class _Deadline:
    """Monotonic budget shared by every request and retry of one facts read."""

    def __init__(self, seconds: float, monotonic: Callable[[], float]) -> None:
        self._monotonic = monotonic
        self._expires_at = monotonic() + seconds

    def remaining(self) -> float:
        """Return the seconds left in this budget."""
        return self._expires_at - self._monotonic()


class GitHubAppFactsAdapter:
    """Read one pull request's merge and required-check facts as a GitHub App."""

    __slots__ = (
        "_configuration",
        "_private_key",
        "_transport",
        "_wall_clock",
        "_monotonic",
        "_sleep",
        "_tokens",
        "_installations",
        "_token_lock",
        "_api_origin",
    )

    def __init__(
        self,
        configuration: GitHubAppFactsConfiguration,
        private_key: RSAPrivateKey,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(private_key, RSAPrivateKey):
            raise ExternalServiceConfigurationError(_IDENTITY)
        self._configuration = configuration
        self._private_key = private_key
        self._transport = transport
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._tokens: dict[str, _InstallationToken] = {}
        self._installations: dict[str, int] = {}
        self._token_lock = asyncio.Lock()
        parsed = urlsplit(configuration.api_base_url)
        self._api_origin = (parsed.scheme, parsed.netloc)

    def __repr__(self) -> str:
        """Show only the non-secret App id."""
        return f"GitHubAppFactsAdapter(app_id={self._configuration.app_id})"

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the fixed GitHub App facts provider identity."""
        return _IDENTITY

    async def fetch_pull_request_facts(
        self,
        *,
        repository: str,
        pull_request_number: int,
    ) -> GitHubPullRequestFacts:
        """Read the pull request, base-branch required checks and head-SHA results."""
        if (
            not is_github_repository(repository)
            or type(pull_request_number) is not int
            or pull_request_number < 1
        ):
            raise ExternalServiceConfigurationError(_IDENTITY)
        deadline = _Deadline(self._configuration.total_deadline_seconds, self._monotonic)
        async with httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=False,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "workstream-github-facts",
            },
        ) as client:
            for _attempt in range(FACTS_CONSISTENCY_ATTEMPTS):
                digests: list[GitHubResponseDigest] = []
                session = _FactsSession(self, client, repository, deadline, digests)
                facts = await self._read_consistent_facts(
                    session, repository, pull_request_number, digests
                )
                if facts is not None:
                    return facts
        # An exhausted deadline already raised GitHubFactsUnavailableError from
        # the next request, so reaching here means the state kept moving.
        raise GitHubFactsInconsistentError(_IDENTITY)

    async def _read_consistent_facts(
        self,
        session: _FactsSession,
        repository: str,
        pull_request_number: int,
        digests: list[GitHubResponseDigest],
    ) -> GitHubPullRequestFacts | None:
        """Read every fact once, bracketed by two pull-request reads.

        Reviews and files are listed by pull request number, not by commit, and
        protection can change between calls. The final pull-request read must
        repeat the first one exactly (head SHA, merged flag, merge commit SHA,
        base branch, state, changed-file count), so every fact belongs to one
        pull-request state. Returns None when the state moved.
        """
        pull_path = f"/repos/{repository}/pulls/{pull_request_number}"
        pull = await session.read_json(
            "pull_request", pull_path, not_found=GitHubPullRequestNotFoundError
        )
        pull_facts = _pull_request_facts(pull, repository, pull_request_number)
        required = _required_checks(
            await session.read_json(
                "required_status_checks",
                f"/repos/{repository}/branches/"
                f"{quote(pull_facts['base_ref'], safe='')}"
                "/protection/required_status_checks",
                not_found=GitHubRequiredChecksNotConfiguredError,
            )
        )
        head_sha = pull_facts["head_sha"]
        changed_files_count = pull_facts["changed_files_count"]
        if changed_files_count > GITHUB_MAXIMUM_LISTED_FILES:
            raise GitHubFactsIncompleteError(_IDENTITY)
        reviews = await session.read_pages(
            "reviews", f"{pull_path}/reviews", item_key=None
        )
        files = await session.read_pages(
            "files",
            f"{pull_path}/files",
            item_key=None,
            maximum_pages=GITHUB_MAXIMUM_LISTED_FILES // PAGE_SIZE,
        )
        check_runs = await session.read_pages(
            "check_runs",
            f"/repos/{repository}/commits/{head_sha}/check-runs",
            item_key="check_runs",
        )
        statuses = await session.read_pages(
            "commit_status",
            f"/repos/{repository}/commits/{head_sha}/status",
            item_key="statuses",
            require_sha=head_sha,
        )
        final = _pull_request_facts(
            await session.read_json(
                "pull_request_final", pull_path, not_found=GitHubPullRequestNotFoundError
            ),
            repository,
            pull_request_number,
        )
        if any(final[key] != pull_facts[key] for key in _BOUND_PULL_FIELDS):
            return None
        if len(files) != changed_files_count:
            raise GitHubFactsIncompleteError(_IDENTITY)
        if any(run.get("head_sha") != head_sha for run in check_runs):
            raise GitHubFactsProtocolError(_IDENTITY)
        try:
            return GitHubPullRequestFacts(
                repository=pull_facts["repository"],
                pull_request_number=pull_request_number,
                html_url=pull_facts["html_url"],
                state=pull_facts["state"],
                merged=pull_facts["merged"],
                merge_commit_sha=pull_facts["merge_commit_sha"],
                base_ref=pull_facts["base_ref"],
                head_sha=head_sha,
                author=_actor(pull_facts["author"]),
                reviews=tuple(_review(item) for item in reviews),
                changed_files_count=changed_files_count,
                changed_files=tuple(
                    GitHubChangedFileFact(
                        filename=item["filename"],
                        previous_filename=item.get("previous_filename"),
                        status=item["status"],
                    )
                    for item in files
                ),
                required_checks=tuple(
                    _required_check_fact(
                        name, app_id, check_runs, statuses, head_sha, pull_facts["repository"]
                    )
                    for name, app_id in required
                ),
                fetched_at=datetime.fromtimestamp(self._wall_clock(), UTC),
                responses=tuple(digests),
            )
        except (ValidationError, KeyError, TypeError):
            raise GitHubFactsProtocolError(_IDENTITY) from None

    # -- credentials -------------------------------------------------------

    def _app_jwt(self) -> str:
        """Sign a short-lived RS256 App JWT; it authenticates only token exchange."""
        now = int(self._wall_clock())
        return jwt.encode(
            {
                "iat": now - JWT_BACKDATE_SECONDS,
                "exp": now + JWT_LIFETIME_SECONDS,
                "iss": str(self._configuration.app_id),
            },
            self._private_key,
            algorithm="RS256",
        )

    def _cached_token(self, repository: str) -> _InstallationToken | None:
        """Return a repository-scoped token that is not yet due for refresh."""
        token = self._tokens.get(repository.casefold())
        if token is None or self._wall_clock() >= token.refresh_at:
            return None
        return token

    def _forget_token(self, repository: str) -> None:
        """Drop a token that GitHub rejected."""
        self._tokens.pop(repository.casefold(), None)

    async def _installation_token(self, session: _FactsSession) -> _InstallationToken:
        """Return a cached repository-scoped token or exchange a fresh App JWT."""
        repository = session.repository
        async with self._token_lock:
            token = self._cached_token(repository)
            if token is not None:
                return token
            installation_id = self._configuration.installation_id
            if installation_id is None:
                installation_id = self._installations.get(repository.casefold())
            if installation_id is None:
                body = await session.app_json(
                    "GET", f"/repos/{repository}/installation", self._app_jwt()
                )
                installation_id = body.get("id") if isinstance(body, dict) else None
                if type(installation_id) is not int or installation_id < 1:
                    raise GitHubFactsProtocolError(_IDENTITY)
                self._installations[repository.casefold()] = installation_id
            body = await session.app_json(
                "POST",
                f"/app/installations/{installation_id}/access_tokens",
                self._app_jwt(),
                json_body={"repositories": [repository.split("/", 1)[1]]},
            )
            value = body.get("token") if isinstance(body, dict) else None
            expires_at = body.get("expires_at") if isinstance(body, dict) else None
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            except ValueError:
                expiry = None
            if (
                not isinstance(value, str)
                or not value
                or any(character.isspace() for character in value)
                or expiry is None
                or expiry.tzinfo is None
            ):
                raise GitHubFactsProtocolError(_IDENTITY)
            token = _InstallationToken(
                value, expiry.timestamp() - TOKEN_REFRESH_MARGIN_SECONDS
            )
            self._tokens[repository.casefold()] = token
            return token


class _FactsSession:
    """One bounded facts read: shared deadline, retries and response digests."""

    def __init__(
        self,
        adapter: GitHubAppFactsAdapter,
        client: httpx.AsyncClient,
        repository: str,
        deadline: _Deadline,
        digests: list[GitHubResponseDigest],
    ) -> None:
        self._adapter = adapter
        self._client = client
        self.repository = repository
        self._deadline = deadline
        self._digests = digests

    def _url(self, path: str) -> str:
        """Resolve an API path against the configured origin."""
        return self._adapter._configuration.api_base_url + path

    async def app_json(
        self,
        method: str,
        path: str,
        app_jwt: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> object:
        """Send one App-JWT request; its body may hold a token and is never hashed."""
        response = await self._send(
            method,
            self._url(path),
            authorization=lambda: f"Bearer {app_jwt}",
            json_body=json_body,
            not_found=GitHubFactsAccessDeniedError,
            installation=False,
        )
        return _json(response)

    async def read_json(
        self,
        label: str,
        path: str,
        *,
        not_found: type[Exception],
    ) -> object:
        """Read and hash one installation-token GET response."""
        response = await self._installation_get(self._url(path), not_found=not_found)
        self._record(label, response)
        return _json(response)

    async def read_pages(
        self,
        label: str,
        path: str,
        *,
        item_key: str | None,
        maximum_pages: int = MAXIMUM_PAGES,
        require_sha: str | None = None,
    ) -> list[dict]:
        """Follow same-origin ``next`` links for a bounded number of pages.

        ``item_key`` names the list inside an object body; None means the body
        itself is the list. More pages than ``maximum_pages`` fail closed.
        ``require_sha`` requires each page body's ``sha`` to equal that commit.
        """
        url = self._url(path) + f"?per_page={PAGE_SIZE}"
        items: list[dict] = []
        for page in range(1, maximum_pages + 1):
            response = await self._installation_get(url, not_found=GitHubFactsProtocolError)
            self._record(f"{label}.page.{page}", response)
            body = _json(response)
            if require_sha is not None and (
                not isinstance(body, dict) or body.get("sha") != require_sha
            ):
                raise GitHubFactsProtocolError(_IDENTITY)
            if item_key is None:
                page_items = body
            else:
                page_items = body.get(item_key) if isinstance(body, dict) else None
            if not isinstance(page_items, list) or not all(
                isinstance(item, dict) for item in page_items
            ):
                raise GitHubFactsProtocolError(_IDENTITY)
            items.extend(page_items)
            next_url = response.links.get("next", {}).get("url")
            if next_url is None:
                return items
            parsed = urlsplit(next_url)
            if (parsed.scheme, parsed.netloc) != self._adapter._api_origin:
                raise GitHubFactsProtocolError(_IDENTITY)
            url = next_url
        raise GitHubFactsProtocolError(_IDENTITY)

    def _record(self, label: str, response: httpx.Response) -> None:
        """Keep the SHA-256 of one raw facts response body."""
        digest = hashlib.sha256(response.content).hexdigest()
        self._digests.append(GitHubResponseDigest(request=label, sha256=f"sha256:{digest}"))

    async def _installation_get(
        self, url: str, *, not_found: type[Exception]
    ) -> httpx.Response:
        """GET with the installation token, refreshing a rejected token once."""
        token = await self._adapter._installation_token(self)
        try:
            return await self._send(
                "GET",
                url,
                authorization=token.header,
                json_body=None,
                not_found=not_found,
                installation=True,
            )
        except _TokenRejected:
            # A revoked or expired cached token gets one fresh exchange.
            self._adapter._forget_token(self.repository)
        token = await self._adapter._installation_token(self)
        try:
            return await self._send(
                "GET",
                url,
                authorization=token.header,
                json_body=None,
                not_found=not_found,
                installation=True,
            )
        except _TokenRejected:
            raise GitHubFactsAccessDeniedError(_IDENTITY) from None

    async def _send(
        self,
        method: str,
        url: str,
        *,
        authorization: Callable[[], str],
        json_body: dict[str, Any] | None,
        not_found: type[Exception],
        installation: bool,
    ) -> httpx.Response:
        """Send with bounded retries for transport errors, 5xx and rate limits."""
        configuration = self._adapter._configuration
        attempt = 0
        while True:
            attempt += 1
            remaining = self._deadline.remaining()
            if remaining <= 0:
                break
            timeout = min(configuration.request_timeout_seconds, remaining)
            response: httpx.Response | None = None
            try:
                response = await self._client.request(
                    method,
                    url,
                    json=json_body,
                    headers={"Authorization": authorization()},
                    timeout=timeout,
                )
            except httpx.TransportError:
                response = None
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            if response is not None:
                status = response.status_code
                if 200 <= status < 300:
                    return response
                if status == 404:
                    raise not_found(_IDENTITY) from None
                if status == 401:
                    if installation:
                        raise _TokenRejected()
                    raise GitHubFactsAccessDeniedError(_IDENTITY) from None
                rate_limit_delay = _rate_limit_delay(response, self._adapter._wall_clock())
                if status in {403, 429} and rate_limit_delay is not None:
                    delay = max(delay, rate_limit_delay)
                elif status == 403:
                    raise GitHubFactsAccessDeniedError(_IDENTITY) from None
                elif status != 408 and status < 500:
                    raise GitHubFactsProtocolError(_IDENTITY) from None
            logger.warning(
                "github_facts_request_retryable status=%s attempt=%s",
                None if response is None else response.status_code,
                attempt,
            )
            if (
                attempt >= configuration.maximum_attempts
                or delay >= self._deadline.remaining()
            ):
                break
            await self._adapter._sleep(delay)
        raise GitHubFactsUnavailableError(_IDENTITY) from None


class _TokenRejected(Exception):
    """Internal signal that GitHub rejected an installation token."""


def _json(response: httpx.Response) -> object:
    """Parse a JSON body or fail as a protocol error."""
    try:
        return response.json()
    except ValueError:
        raise GitHubFactsProtocolError(_IDENTITY) from None


def _rate_limit_delay(response: httpx.Response, now: float) -> float | None:
    """Return GitHub's requested wait for a primary or secondary rate limit."""
    retry_after = response.headers.get("retry-after")
    if retry_after is not None:
        try:
            return max(0.0, float(int(retry_after)))
        except ValueError:
            return None
    if response.headers.get("x-ratelimit-remaining") == "0":
        try:
            return max(0.0, float(int(response.headers["x-ratelimit-reset"])) - now)
        except (KeyError, ValueError):
            return None
    return None


def _pull_request_facts(body: object, repository: str, number: int) -> dict[str, Any]:
    """Extract the pull request fields and confirm it belongs to the repository."""
    try:
        if not isinstance(body, dict):
            raise TypeError
        base = body["base"]
        head = body["head"]
        full_name = base["repo"]["full_name"]
        merged = body["merged"]
        values = {
            "repository": full_name,
            "state": body["state"],
            "merged": merged,
            "merge_commit_sha": body["merge_commit_sha"] if merged is True else None,
            "base_ref": base["ref"],
            "head_sha": head["sha"],
            "html_url": body["html_url"],
            "author": body["user"],
            "changed_files_count": body["changed_files"],
        }
        valid = (
            body["number"] == number
            and isinstance(full_name, str)
            and full_name.casefold() == repository.casefold()
            and isinstance(values["base_ref"], str)
            and isinstance(values["head_sha"], str)
            and type(values["changed_files_count"]) is int
            and values["changed_files_count"] >= 0
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise GitHubFactsProtocolError(_IDENTITY) from None
    return values


def _required_checks(body: object) -> tuple[tuple[str, int | None], ...]:
    """Return required (context, app id) pairs from ``checks`` and ``contexts``.

    ``checks`` entries carry an optional App restriction; a name only in
    ``contexts`` accepts any source. No required check fails closed.
    """
    if not isinstance(body, dict):
        raise GitHubFactsProtocolError(_IDENTITY)
    checks = body.get("checks", [])
    contexts = body.get("contexts", [])
    if not isinstance(checks, list) or not isinstance(contexts, list):
        raise GitHubFactsProtocolError(_IDENTITY)
    required: dict[str, int | None] = {}
    for item in checks:
        context = item.get("context") if isinstance(item, dict) else None
        app_id = item.get("app_id") if isinstance(item, dict) else None
        if not isinstance(context, str) or not context:
            raise GitHubFactsProtocolError(_IDENTITY)
        if app_id is not None and (type(app_id) is not int or app_id < 1):
            # GitHub reports -1 or null for "any source".
            app_id = None
        required[context] = app_id
    for context in contexts:
        if not isinstance(context, str) or not context:
            raise GitHubFactsProtocolError(_IDENTITY)
        required.setdefault(context, None)
    if not required:
        raise GitHubRequiredChecksNotConfiguredError(_IDENTITY)
    return tuple(sorted(required.items()))


def _latest(items: list[dict]) -> dict | None:
    """Return the most recent item by GitHub id; re-runs get higher ids."""
    if any(type(item.get("id")) is not int for item in items):
        raise GitHubFactsProtocolError(_IDENTITY)
    return max(items, key=lambda item: item["id"], default=None)


def _workflow_run_id(run: dict, repository: str) -> int | None:
    """Return the Actions workflow run id from a GitHub Actions run's details URL.

    The App lacks Actions read permission, so the run id comes from GitHub's own
    ``details_url`` (``https://github.com/{repo}/actions/runs/{id}/job/{job}``),
    and only for the GitHub Actions App and this repository.
    """
    app = run.get("app")
    details_url = run.get("details_url")
    if not isinstance(app, dict) or app.get("id") != GITHUB_ACTIONS_APP_ID:
        return None
    if not isinstance(details_url, str):
        return None
    match = _ACTIONS_DETAILS_URL.fullmatch(details_url)
    if match is None or match.group(1).casefold() != repository.casefold():
        return None
    return int(match.group(2))


def _actor(body: object) -> GitHubActorFact:
    """Translate one GitHub user object."""
    if not isinstance(body, dict):
        raise GitHubFactsProtocolError(_IDENTITY)
    return GitHubActorFact(login=body["login"], id=body["id"], type=body["type"])


def _review(body: dict) -> GitHubReviewFact:
    """Translate one review; GitHub reports a deleted reviewer as null."""
    user = body.get("user")
    return GitHubReviewFact(
        id=body["id"],
        reviewer=None if user is None else _actor(user),
        state=body["state"],
        commit_id=body.get("commit_id"),
        submitted_at=body.get("submitted_at"),
    )


def _required_check_fact(
    name: str,
    app_id: int | None,
    check_runs: list[dict],
    statuses: list[dict],
    head_sha: str,
    repository: str,
) -> GitHubRequiredCheckFact:
    """Judge only the latest check run and latest status for one required check.

    A re-run supersedes an earlier attempt with the same name. When both a check
    run and a commit status exist for the name, both latest results must succeed.
    The fact records which App produced the judged run.
    """
    observed: list[str] = []
    runs = []
    for run in check_runs:
        app = run.get("app")
        run_app_id = app.get("id") if isinstance(app, dict) else None
        if run.get("name") == name and (app_id is None or run_app_id == app_id):
            runs.append(run)
    run = _latest(runs)
    check_run_app_id = None
    check_run_head_sha = None
    html_url = details_url = workflow_run_id = None
    if run is not None:
        check_run_head_sha = run.get("head_sha")
        html_url = run.get("html_url")
        details_url = run.get("details_url")
        workflow_run_id = _workflow_run_id(run, repository)
        app = run.get("app")
        check_run_app_id = app.get("id") if isinstance(app, dict) else None
        if check_run_app_id is not None and type(check_run_app_id) is not int:
            raise GitHubFactsProtocolError(_IDENTITY)
        if run.get("status") != "completed":
            observed.append("pending")
        else:
            conclusion = run.get("conclusion")
            if conclusion not in _CHECK_RUN_CONCLUSIONS:
                raise GitHubFactsProtocolError(_IDENTITY)
            observed.append(conclusion)
    status_judged = False
    if app_id is None:
        # Commit statuses carry no App identity, so they satisfy only
        # requirements that accept any source.
        status = _latest([item for item in statuses if item.get("context") == name])
        if status is not None:
            state = status.get("state")
            if state not in _STATUS_STATES:
                raise GitHubFactsProtocolError(_IDENTITY)
            observed.append(state)
            status_judged = True
    conclusion = (
        "missing"
        if not observed
        else next((value for value in observed if value != "success"), "success")
    )
    return GitHubRequiredCheckFact(
        name=name,
        app_id=app_id,
        app_bound=app_id is not None,
        conclusion=conclusion,
        check_run_app_id=check_run_app_id,
        check_run_head_sha=check_run_head_sha,
        check_run_html_url=html_url,
        check_run_details_url=details_url,
        workflow_run_id=workflow_run_id,
        commit_status_judged=status_judged,
        commit_status_sha=head_sha if status_judged else None,
    )
