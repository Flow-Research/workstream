"""Typed GitHub pull-request facts capability for proof comparison.

A trusted WorkStream owner reads these facts outside the checker sandbox. The
networkless checker receives them as request input and compares them with the
contributor's claims. The facts never contain a credential.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated, Literal, Protocol

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

from app.interfaces.external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterError,
    ExternalServiceConfigurationError,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)


GITHUB_FACTS_CAPABILITY_KEY = "github_facts"
GITHUB_APP_PROVIDER_KEY = "github_app"
GITHUB_FACTS_SCHEMA_VERSION = "workstream.github_facts.v1"

# GitHub owner logins are at most 39 characters; repository names at most 100.
_GITHUB_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$"
)

GitSha = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{40}$")]
Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
# Check-run conclusions and commit-status states, plus two derived values:
# ``pending`` (not completed) and ``missing`` (no matching check or status).
GitHubCheckConclusion = Literal[
    "success",
    "failure",
    "neutral",
    "cancelled",
    "skipped",
    "timed_out",
    "action_required",
    "stale",
    "error",
    "pending",
    "missing",
]


def is_github_repository(value: object) -> bool:
    """Return whether a value is one canonical ``owner/name`` repository."""
    return isinstance(value, str) and _GITHUB_REPOSITORY.fullmatch(value) is not None


_CANONICAL_PULL_REQUEST_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})"
    r"/pull/([1-9][0-9]{0,9})"
)


def parse_pull_request_url(value: object) -> tuple[str, int] | None:
    """Return (repository, number) from one canonical pull-request URL, or None.

    This is the single parser for a claimed pull-request URL. Only
    ``https://github.com/{owner}/{name}/pull/{number}`` in ASCII is accepted:
    no port, user information, query, fragment, trailing slash, percent
    encoding or backslash. The checker re-asserts exact equality of the claim
    with the facts, so the reader and the checker cannot disagree.
    """
    if not isinstance(value, str) or not value.isascii():
        return None
    match = _CANONICAL_PULL_REQUEST_URL.fullmatch(value)
    if match is None or not is_github_repository(match.group(1)):
        return None
    return match.group(1), int(match.group(2))


def _github_repository(value: str) -> str:
    """Validate one canonical repository name."""
    if not is_github_repository(value):
        raise ValueError("GitHub repository must be owner/name")
    return value


GitHubRepository = Annotated[StrictStr, AfterValidator(_github_repository)]


class _FactsValue(BaseModel):
    """Strict immutable facts value."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


# GitHub changed-file listings return at most this many files per pull request.
GITHUB_MAXIMUM_LISTED_FILES = 3000


class GitHubActorFact(_FactsValue):
    """One GitHub account as GitHub reports it (``type`` is e.g. User or Bot)."""

    login: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    id: Annotated[StrictInt, Field(ge=1)]
    type: Annotated[StrictStr, Field(min_length=1, max_length=50)]


class GitHubReviewFact(_FactsValue):
    """One submitted pull-request review, unfiltered.

    ``reviewer`` is null when GitHub no longer has the account. Policy, such as
    taking each reviewer's latest review, belongs to the consumer.
    """

    id: Annotated[StrictInt, Field(ge=1)]
    reviewer: GitHubActorFact | None
    state: Annotated[StrictStr, Field(min_length=1, max_length=50)]
    commit_id: GitSha | None
    submitted_at: datetime | None


class GitHubChangedFileFact(_FactsValue):
    """One changed file; ``previous_filename`` is set for renames."""

    filename: Annotated[StrictStr, Field(min_length=1, max_length=4096)]
    previous_filename: Annotated[StrictStr, Field(min_length=1, max_length=4096)] | None
    status: Annotated[StrictStr, Field(min_length=1, max_length=50)]


class GitHubRequiredCheckFact(_FactsValue):
    """One check required by base-branch protection and its head-SHA result.

    ``app_id`` is the requirement's App restriction and ``app_bound`` says
    whether one exists. ``check_run_app_id`` is the App that produced the judged
    latest check run (null when no run was judged) and ``check_run_head_sha`` the
    commit GitHub reports for that run. ``commit_status_judged`` is true when a
    commit status, which carries no App identity, was judged;
    ``commit_status_sha`` is the commit of that combined status.
    ``check_run_html_url`` and ``check_run_details_url`` are GitHub's URLs for the
    judged run, and ``workflow_run_id`` is the GitHub Actions workflow run that
    produced it, taken from a GitHub Actions ``details_url`` of this repository
    (null for other producers).
    """

    name: Annotated[StrictStr, Field(min_length=1, max_length=255)]
    app_id: StrictInt | None
    app_bound: StrictBool
    conclusion: GitHubCheckConclusion
    check_run_app_id: StrictInt | None
    check_run_head_sha: GitSha | None
    check_run_html_url: Annotated[StrictStr, Field(max_length=2048)] | None
    check_run_details_url: Annotated[StrictStr, Field(max_length=2048)] | None
    workflow_run_id: Annotated[StrictInt, Field(ge=1)] | None
    commit_status_judged: StrictBool
    commit_status_sha: GitSha | None


class GitHubResponseDigest(_FactsValue):
    """SHA-256 of one raw GitHub response body that produced these facts."""

    request: Annotated[StrictStr, Field(pattern=r"^[a-z_]+(?:\.page\.[1-9][0-9]*)?$")]
    sha256: Sha256


class GitHubPullRequestFacts(_FactsValue):
    """Immutable ``workstream.github_facts.v1`` value for one pull request.

    ``merge_commit_sha`` is null unless the pull request is merged, because
    GitHub reports a test-merge commit for open pull requests. ``head_sha`` and
    ``merge_commit_sha`` are the single pull-request state every other fact was
    bound to: the adapter re-reads the pull request after all other reads and
    discards the read if that state moved. Serialize with
    ``model_dump(mode="json")`` to place the value in checker request input.
    """

    schema_version: Literal["workstream.github_facts.v1"] = GITHUB_FACTS_SCHEMA_VERSION
    repository: GitHubRepository
    pull_request_number: Annotated[StrictInt, Field(ge=1)]
    html_url: Annotated[StrictStr, Field(min_length=1, max_length=2048)]
    state: Literal["open", "closed"]
    merged: StrictBool
    merge_commit_sha: GitSha | None
    base_ref: Annotated[StrictStr, Field(min_length=1, max_length=255)]
    head_sha: GitSha
    author: GitHubActorFact
    reviews: tuple[GitHubReviewFact, ...]
    changed_files_count: Annotated[StrictInt, Field(ge=0, le=GITHUB_MAXIMUM_LISTED_FILES)]
    changed_files: tuple[GitHubChangedFileFact, ...]
    required_checks: tuple[GitHubRequiredCheckFact, ...] = Field(min_length=1)
    fetched_at: datetime
    responses: tuple[GitHubResponseDigest, ...] = Field(min_length=1)


class GitHubFactsUnavailableError(ExternalServiceUnavailableError):
    """GitHub stayed unavailable or rate-limited within the bounded retry budget."""

    code = "github_facts_unavailable"


class GitHubFactsAccessDeniedError(ExternalServiceConfigurationError):
    """The GitHub App credential, installation or permission is not usable."""

    code = "github_facts_access_denied"


class GitHubRequiredChecksNotConfiguredError(ExternalServiceConfigurationError):
    """The base branch has no classic branch-protection required checks.

    Without required checks, "CI passed" has no meaning, so facts fail closed.
    """

    code = "github_required_checks_not_configured"


class GitHubPullRequestNotFoundError(ExternalServiceAdapterError):
    """The repository has no pull request with the requested number."""

    code = "github_pull_request_not_found"
    category = "not_found"


class GitHubFactsProtocolError(ExternalServiceProtocolError):
    """GitHub returned a response outside the supported facts protocol."""

    code = "github_facts_protocol_invalid"


class GitHubFactsInconsistentError(ExternalServiceUnavailableError):
    """The pull request kept changing while facts were read, within the deadline.

    Retryable: a later read may observe one stable state.
    """

    code = "github_facts_inconsistent"


class GitHubFactsIncompleteError(GitHubFactsProtocolError):
    """GitHub cannot list every changed file, so the facts would be partial."""

    code = "github_facts_incomplete"


class GitHubFactsAdapter(ExternalServiceAdapter, Protocol):
    """Read verified facts about one pull request with a read-only credential."""

    async def fetch_pull_request_facts(
        self,
        *,
        repository: str,
        pull_request_number: int,
    ) -> GitHubPullRequestFacts:
        """Return facts or raise a secret-free ``ExternalServiceAdapterError``."""
