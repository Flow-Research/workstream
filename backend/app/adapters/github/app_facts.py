"""GitHub provider of the forge facts capability, read as a GitHub App.

It reads one pull request's proof facts with bounded retries and maps them
into the forge-neutral ``workstream.forge_change_facts.v1`` value.

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
from app.interfaces.forge_facts import (
    FORGE_FACTS_CAPABILITY_KEY,
    GITHUB_FORGE,
    ForgeActorFact,
    ForgeChangeFacts,
    ForgeChangeNotEligibleError,
    ForgeChangeNotFoundError,
    ForgeChangedFileFact,
    ForgeFactsAccessDeniedError,
    ForgeFactsIncompleteError,
    is_forge_origin,
    ForgeFactsInconsistentError,
    ForgeFactsProtocolError,
    ForgeFactsUnavailableError,
    ForgeJudgedResultFact,
    ForgeRequiredCheckFact,
    ForgeRequiredChecksNotConfiguredError,
    ForgeResponseDigest,
    ForgeReviewFact,
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
# GitHub owner logins are at most 39 characters; repository names at most 100.
_GITHUB_REPOSITORY_PATTERN = r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}"
_GITHUB_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$"
)
_GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?")
# Reviewers whose write access is read: those approving the head commit.
MAXIMUM_PERMISSION_READS = 20
_WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})
# Whole facts reads attempted when the pull request moves during a read.
FACTS_CONSISTENCY_ATTEMPTS = 3
_BOUND_PULL_FIELDS = (
    "head_sha",
    "merged",
    "landed_commit_sha",
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
_IDENTITY = ExternalServiceAdapterIdentity(FORGE_FACTS_CAPABILITY_KEY, GITHUB_FORGE)
# GitHub change listings return at most this many files per pull request.
GITHUB_MAXIMUM_LISTED_FILES = 3000


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


def github_web_origin(api_base_url: str) -> str:
    """Return the web origin for a GitHub API base URL.

    ``https://api.github.com`` serves ``https://github.com``; a GitHub
    Enterprise Server API (``https://host/api/v3``) serves ``https://host``.
    """
    parsed = urlsplit(api_base_url)
    netloc = parsed.netloc.lower()
    if netloc == "api.github.com":
        return "https://github.com"
    return f"{parsed.scheme.lower()}://{netloc}"


def is_github_repository(value: object) -> bool:
    """Return whether ``value`` is a GitHub ``owner/name`` repository path."""
    return isinstance(value, str) and value.isascii() and bool(
        _GITHUB_REPOSITORY.fullmatch(value)
    )


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
        "_web_origin",
        "_change_url",
        "_actions_run_url",
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
        self._web_origin = github_web_origin(configuration.api_base_url)
        # Facts name an https instance origin; any other origin could never
        # produce valid facts, so refuse it here rather than on every read.
        if not is_forge_origin(self._web_origin):
            raise ExternalServiceConfigurationError(_IDENTITY)
        origin = re.escape(self._web_origin)
        self._change_url = re.compile(
            rf"{origin}/({_GITHUB_REPOSITORY_PATTERN})/pull/([1-9][0-9]{{0,9}})"
        )
        self._actions_run_url = re.compile(
            rf"{origin}/({_GITHUB_REPOSITORY_PATTERN})"
            r"/actions/runs/([1-9][0-9]{0,18})(?:/job/[1-9][0-9]{0,18})?"
        )

    def __repr__(self) -> str:
        """Show only the non-secret App id."""
        return f"GitHubAppFactsAdapter(app_id={self._configuration.app_id})"

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the fixed GitHub App facts provider identity."""
        return _IDENTITY

    @property
    def forge_origin(self) -> str:
        """Return the GitHub web origin this App reads, e.g. https://github.com."""
        return self._web_origin

    def parse_change_url(self, value: object) -> tuple[str, int] | None:
        """Parse ``{origin}/{owner}/{name}/pull/{number}`` in ASCII, nothing else.

        No port other than the origin's, user information, query, fragment,
        trailing slash, percent encoding or backslash is accepted.
        """
        if not isinstance(value, str) or not value.isascii():
            return None
        match = self._change_url.fullmatch(value)
        if match is None or not is_github_repository(match.group(1)):
            return None
        return match.group(1), int(match.group(2))

    async def fetch_change_facts(
        self,
        *,
        repository: str,
        change_number: int,
        base_branch: str,
    ) -> ForgeChangeFacts:
        """Read the pull request, base-branch required checks and head-SHA results."""
        if (
            not is_github_repository(repository)
            or type(change_number) is not int
            or change_number < 1
            or type(base_branch) is not str
            or not base_branch
        ):
            raise ExternalServiceConfigurationError(_IDENTITY)
        seconds = self._configuration.total_deadline_seconds
        deadline = _Deadline(seconds, self._monotonic)
        # Per-request timeouts do not bound the whole read: a slow response body
        # can outlast them. The outer timeout is the absolute limit, and facts
        # completed after the deadline are discarded rather than returned.
        try:
            async with asyncio.timeout(seconds), httpx.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": "workstream-github-facts",
                },
            ) as client:
                for _attempt in range(FACTS_CONSISTENCY_ATTEMPTS):
                    digests: list[ForgeResponseDigest] = []
                    session = _FactsSession(self, client, repository, deadline, digests)
                    facts = await self._read_consistent_facts(
                        session, repository, change_number, base_branch, digests
                    )
                    if facts is not None:
                        if deadline.remaining() <= 0:
                            raise ForgeFactsUnavailableError(_IDENTITY)
                        return facts
        except TimeoutError:
            raise ForgeFactsUnavailableError(_IDENTITY) from None
        # An exhausted deadline already raised ForgeFactsUnavailableError from
        # the next request, so reaching here means the state kept moving.
        raise ForgeFactsInconsistentError(_IDENTITY)

    async def _read_consistent_facts(
        self,
        session: _FactsSession,
        repository: str,
        pull_request_number: int,
        base_branch: str,
        digests: list[ForgeResponseDigest],
    ) -> ForgeChangeFacts | None:
        """Read every fact once, bracketed by two pull-request reads.

        Reviews and files are listed by pull request number, not by commit, and
        protection can change between calls. The final pull-request read must
        repeat the first one exactly (head SHA, merged flag, merge commit SHA,
        base branch, state, changed-file count), so every fact belongs to one
        pull-request state. Returns None when the state moved.
        """
        # A repository outside the App's installation answers 404 like a
        # missing pull request; reading it first keeps that a configuration
        # failure rather than a contributor's missing change.
        await session.read_json(
            "repository", f"/repos/{repository}", not_found=ForgeFactsAccessDeniedError
        )
        pull_path = f"/repos/{repository}/pulls/{pull_request_number}"
        pull = await session.read_json(
            "pull_request", pull_path, not_found=ForgeChangeNotFoundError
        )
        pull_facts = self._pull_request_facts(pull, repository, pull_request_number)
        if pull_facts["base_ref"] != base_branch:
            raise ForgeChangeNotEligibleError(_IDENTITY)
        required = _required_checks(
            await session.read_json(
                "required_status_checks",
                f"/repos/{repository}/branches/"
                f"{quote(pull_facts['base_ref'], safe='')}"
                "/protection/required_status_checks",
                not_found=ForgeRequiredChecksNotConfiguredError,
            )
        )
        head_sha = pull_facts["head_sha"]
        changed_files_count = pull_facts["changed_files_count"]
        if changed_files_count > GITHUB_MAXIMUM_LISTED_FILES:
            raise ForgeChangeNotEligibleError(_IDENTITY)
        # Anyone may review or run checks on a change; more than the bounded
        # listing is a property of the change, so it is ineligible, not an outage.
        reviews = await session.read_pages(
            "reviews",
            f"{pull_path}/reviews",
            item_key=None,
            over_limit=ForgeChangeNotEligibleError,
        )
        # GitHub lists reviews oldest first; sort by id so the order is explicit.
        try:
            reviews.sort(key=lambda item: item["id"])
        except (KeyError, TypeError):
            raise ForgeFactsProtocolError(_IDENTITY) from None
        write_access = await _reviewer_write_access(session, repository, reviews, head_sha)
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
            over_limit=ForgeChangeNotEligibleError,
        )
        statuses = await session.read_pages(
            "commit_status",
            f"/repos/{repository}/commits/{head_sha}/status",
            item_key="statuses",
            require_sha=head_sha,
            over_limit=ForgeChangeNotEligibleError,
        )
        final = self._pull_request_facts(
            await session.read_json(
                "pull_request_final", pull_path, not_found=ForgeChangeNotFoundError
            ),
            repository,
            pull_request_number,
        )
        if any(final[key] != pull_facts[key] for key in _BOUND_PULL_FIELDS):
            return None
        if len(files) != changed_files_count:
            raise ForgeFactsIncompleteError(_IDENTITY)
        if any(run.get("head_sha") != head_sha for run in check_runs):
            raise ForgeFactsProtocolError(_IDENTITY)
        try:
            return ForgeChangeFacts(
                forge=GITHUB_FORGE,
                forge_origin=self._web_origin,
                repository=pull_facts["repository"],
                change_number=pull_request_number,
                change_url=pull_facts["change_url"],
                state=pull_facts["state"],
                merged=pull_facts["merged"],
                landed_commit_sha=pull_facts["landed_commit_sha"],
                base_ref=pull_facts["base_ref"],
                head_sha=head_sha,
                author=_actor(pull_facts["author"]),
                reviews=tuple(_review(item, write_access) for item in reviews),
                changed_files_count=changed_files_count,
                changed_files=tuple(
                    ForgeChangedFileFact(
                        path=item["filename"],
                        previous_path=item.get("previous_filename"),
                        status=item["status"],
                    )
                    for item in files
                ),
                required_checks=tuple(
                    _required_check_fact(
                        name,
                        app_id,
                        check_runs,
                        statuses,
                        head_sha,
                        pull_facts["repository"],
                        self._web_origin,
                        self._actions_run_url,
                    )
                    for name, app_id in required
                ),
                fetched_at=datetime.fromtimestamp(self._wall_clock(), UTC),
                responses=tuple(digests),
            )
        except (ValidationError, KeyError, TypeError):
            raise ForgeFactsProtocolError(_IDENTITY) from None

    # -- credentials -------------------------------------------------------

    def _pull_request_facts(self, body: object, repository: str, number: int) -> dict[str, Any]:
        """Translate one pull request read with this instance's web origin."""
        return _pull_request_facts(body, repository, number, self._web_origin)

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
                    raise ForgeFactsProtocolError(_IDENTITY)
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
                raise ForgeFactsProtocolError(_IDENTITY)
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
        digests: list[ForgeResponseDigest],
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
            not_found=ForgeFactsAccessDeniedError,
            installation=False,
            # GitHub refuses a token for a repository outside the installation.
            unprocessable=ForgeFactsAccessDeniedError,
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
        over_limit: type[Exception] = ForgeFactsProtocolError,
    ) -> list[dict]:
        """Follow same-origin ``next`` links for a bounded number of pages.

        ``item_key`` names the list inside an object body; None means the body
        itself is the list. More pages than ``maximum_pages`` raise
        ``over_limit``.
        ``require_sha`` requires each page body's ``sha`` to equal that commit.
        """
        url = self._url(path) + f"?per_page={PAGE_SIZE}"
        items: list[dict] = []
        for page in range(1, maximum_pages + 1):
            response = await self._installation_get(url, not_found=ForgeFactsProtocolError)
            self._record(f"{label}.page.{page}", response)
            body = _json(response)
            if require_sha is not None and (
                not isinstance(body, dict) or body.get("sha") != require_sha
            ):
                raise ForgeFactsProtocolError(_IDENTITY)
            if item_key is None:
                page_items = body
            else:
                page_items = body.get(item_key) if isinstance(body, dict) else None
            if not isinstance(page_items, list) or not all(
                isinstance(item, dict) for item in page_items
            ):
                raise ForgeFactsProtocolError(_IDENTITY)
            items.extend(page_items)
            try:
                next_url = response.links.get("next", {}).get("url")
            except ValueError:
                raise ForgeFactsProtocolError(_IDENTITY) from None
            if next_url is None:
                return items
            parsed = urlsplit(next_url)
            if (parsed.scheme, parsed.netloc) != self._adapter._api_origin:
                raise ForgeFactsProtocolError(_IDENTITY)
            url = next_url
        raise over_limit(_IDENTITY)

    def _record(self, label: str, response: httpx.Response) -> None:
        """Keep the SHA-256 of one raw facts response body."""
        digest = hashlib.sha256(response.content).hexdigest()
        self._digests.append(ForgeResponseDigest(request=label, sha256=f"sha256:{digest}"))

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
            raise ForgeFactsAccessDeniedError(_IDENTITY) from None

    async def _send(
        self,
        method: str,
        url: str,
        *,
        authorization: Callable[[], str],
        json_body: dict[str, Any] | None,
        not_found: type[Exception],
        installation: bool,
        unprocessable: type[Exception] = ForgeFactsProtocolError,
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
            except (httpx.HTTPError, httpx.InvalidURL):
                raise ForgeFactsProtocolError(_IDENTITY) from None
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            if response is not None:
                status = response.status_code
                if 200 <= status < 300:
                    return response
                if status == 404:
                    raise not_found(_IDENTITY) from None
                if status == 422:
                    raise unprocessable(_IDENTITY) from None
                if status == 401:
                    if installation:
                        raise _TokenRejected()
                    raise ForgeFactsAccessDeniedError(_IDENTITY) from None
                rate_limit_delay = _rate_limit_delay(response, self._adapter._wall_clock())
                if status in {403, 429} and rate_limit_delay is not None:
                    delay = max(delay, rate_limit_delay)
                elif status == 403:
                    raise ForgeFactsAccessDeniedError(_IDENTITY) from None
                elif status != 408 and status < 500:
                    raise ForgeFactsProtocolError(_IDENTITY) from None
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
        raise ForgeFactsUnavailableError(_IDENTITY) from None


class _TokenRejected(Exception):
    """Internal signal that GitHub rejected an installation token."""


def _json(response: httpx.Response) -> object:
    """Parse a JSON body or fail as a protocol error."""
    try:
        return response.json()
    except ValueError:
        raise ForgeFactsProtocolError(_IDENTITY) from None


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


def _pull_request_facts(
    body: object, repository: str, number: int, web_origin: str
) -> dict[str, Any]:
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
            "landed_commit_sha": body["merge_commit_sha"] if merged is True else None,
            "base_ref": base["ref"],
            "head_sha": head["sha"],
            "change_url": f"{web_origin}/{full_name}/pull/{number}",
            "author": body["user"],
            "changed_files_count": body["changed_files"],
        }
        valid = (
            body["number"] == number
            and isinstance(full_name, str)
            and body["html_url"] == values["change_url"]
            and full_name.casefold() == repository.casefold()
            and isinstance(values["base_ref"], str)
            and isinstance(values["head_sha"], str)
            and type(values["changed_files_count"]) is int
            and values["changed_files_count"] >= 0
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ForgeFactsProtocolError(_IDENTITY) from None
    return values


def _required_checks(body: object) -> tuple[tuple[str, int | None], ...]:
    """Return required (context, app id) pairs from ``checks`` and ``contexts``.

    ``checks`` entries carry an optional App restriction; a name only in
    ``contexts`` accepts any source. No required check fails closed.
    """
    if not isinstance(body, dict):
        raise ForgeFactsProtocolError(_IDENTITY)
    checks = body.get("checks", [])
    contexts = body.get("contexts", [])
    if not isinstance(checks, list) or not isinstance(contexts, list):
        raise ForgeFactsProtocolError(_IDENTITY)
    required: dict[str, int | None] = {}
    for item in checks:
        context = item.get("context") if isinstance(item, dict) else None
        app_id = item.get("app_id") if isinstance(item, dict) else None
        if not isinstance(context, str) or not context:
            raise ForgeFactsProtocolError(_IDENTITY)
        if app_id is not None and (type(app_id) is not int or app_id < 1):
            # GitHub reports -1 or null for "any source".
            app_id = None
        required[context] = app_id
    for context in contexts:
        if not isinstance(context, str) or not context:
            raise ForgeFactsProtocolError(_IDENTITY)
        required.setdefault(context, None)
    if not required:
        raise ForgeRequiredChecksNotConfiguredError(_IDENTITY)
    return tuple(sorted(required.items()))


def _latest(items: list[dict]) -> dict | None:
    """Return the most recent item by GitHub id; re-runs get higher ids."""
    if any(type(item.get("id")) is not int for item in items):
        raise ForgeFactsProtocolError(_IDENTITY)
    return max(items, key=lambda item: item["id"], default=None)


def _workflow_run_id(run: dict, repository: str, run_url: re.Pattern[str]) -> int | None:
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
    match = run_url.fullmatch(details_url)
    if match is None or match.group(1).casefold() != repository.casefold():
        return None
    return int(match.group(2))


_ACTOR_KINDS = {"User": "user", "Bot": "bot"}
_REVIEW_STATES = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes_requested",
    "DISMISSED": "dismissed",
    "COMMENTED": "commented",
    "PENDING": "pending",
}


def _actor(body: object) -> ForgeActorFact:
    """Translate one GitHub user object; types other than User and Bot are ``other``."""
    if not isinstance(body, dict) or not isinstance(body["type"], str):
        raise ForgeFactsProtocolError(_IDENTITY)
    return ForgeActorFact(
        login=body["login"], id=body["id"], kind=_ACTOR_KINDS.get(body["type"], "other")
    )


class _NotCollaborator(Exception):
    """Internal signal that GitHub has no permission record for a reviewer."""


async def _reviewer_write_access(
    session: _FactsSession, repository: str, reviews: list[dict], head_sha: str
) -> dict[int, bool]:
    """Read write access for reviewers who approved ``head_sha``.

    Other reviewers' access is not read and is reported as unknown. A reviewer
    without a permission record, or whose record names another account, has
    no write access; neither does an approving account that is not a user,
    whose permission is never read. More approving users than the bound make
    the change ineligible.
    """
    reviewer_ids: dict[int, str] = {}
    access: dict[int, bool] = {}
    for item in reviews:
        user = item.get("user")
        if (
            item.get("state") == "APPROVED"
            and item.get("commit_id") == head_sha
            and isinstance(user, dict)
            and type(user.get("id")) is int
            and isinstance(user.get("login"), str)
        ):
            if user.get("type") == "User":
                reviewer_ids[user["id"]] = user["login"]
            else:
                access[user["id"]] = False
    if len(reviewer_ids) > MAXIMUM_PERMISSION_READS:
        raise ForgeChangeNotEligibleError(_IDENTITY)
    for user_id, login in reviewer_ids.items():
        if not _GITHUB_LOGIN.fullmatch(login):
            access[user_id] = False
            continue
        try:
            body = await session.read_json(
                "reviewer_permission",
                f"/repos/{repository}/collaborators/{login}/permission",
                not_found=_NotCollaborator,
            )
        except _NotCollaborator:
            access[user_id] = False
            continue
        if not isinstance(body, dict) or not isinstance(body.get("user"), dict):
            raise ForgeFactsProtocolError(_IDENTITY)
        access[user_id] = (
            body["user"].get("id") == user_id and body.get("permission") in _WRITE_PERMISSIONS
        )
    return access


def _review(body: dict, write_access: dict[int, bool]) -> ForgeReviewFact:
    """Translate one review; GitHub reports a deleted reviewer as null."""
    user = body.get("user")
    if not isinstance(body.get("state"), str) or type(body.get("id")) is not int:
        raise ForgeFactsProtocolError(_IDENTITY)
    reviewer = None if user is None else _actor(user)
    return ForgeReviewFact(
        id=str(body["id"]),
        reviewer=reviewer,
        reviewer_write_access=None if reviewer is None else write_access.get(reviewer.id),
        state=_REVIEW_STATES.get(body["state"], "other"),
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
    web_origin: str,
    run_url: re.Pattern[str],
) -> ForgeRequiredCheckFact:
    """Judge only the latest check run and latest status for one required check.

    A re-run supersedes an earlier attempt with the same name. When both a check
    run and a commit status exist for the name, both latest results must succeed.
    Each judged result records its producer (``github_app:<id>``); commit
    statuses have none.
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
    workflow_run_id = None
    if run is not None:
        check_run_head_sha = run.get("head_sha")
        workflow_run_id = _workflow_run_id(run, repository, run_url)
        app = run.get("app")
        check_run_app_id = app.get("id") if isinstance(app, dict) else None
        if check_run_app_id is not None and type(check_run_app_id) is not int:
            raise ForgeFactsProtocolError(_IDENTITY)
        if run.get("status") != "completed":
            observed.append("pending")
        else:
            conclusion = run.get("conclusion")
            if conclusion not in _CHECK_RUN_CONCLUSIONS:
                raise ForgeFactsProtocolError(_IDENTITY)
            observed.append(conclusion)
    status_judged = False
    if app_id is None:
        # Commit statuses carry no App identity, so they satisfy only
        # requirements that accept any source.
        status = _latest([item for item in statuses if item.get("context") == name])
        if status is not None:
            state = status.get("state")
            if state not in _STATUS_STATES:
                raise ForgeFactsProtocolError(_IDENTITY)
            observed.append(state)
            status_judged = True
    conclusion = (
        "missing"
        if not observed
        else next((value for value in observed if value != "success"), "success")
    )
    judged = []
    if run is not None:
        judged.append(
            ForgeJudgedResultFact(
                producer=None if check_run_app_id is None else f"github_app:{check_run_app_id}",
                sha=check_run_head_sha,
            )
        )
    if status_judged:
        # Commit statuses carry no producer identity.
        judged.append(ForgeJudgedResultFact(producer=None, sha=head_sha))
    return ForgeRequiredCheckFact(
        name=name,
        conclusion=conclusion,
        required_producer=None if app_id is None else f"github_app:{app_id}",
        judged=tuple(judged),
        run_url=(
            None
            if workflow_run_id is None
            else f"{web_origin}/{repository}/actions/runs/{workflow_run_id}"
        ),
    )
