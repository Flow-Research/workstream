"""Typed, forge-neutral change-request facts capability for proof comparison.

A forge is a git host such as GitHub, GitLab or Forgejo; a change is a pull or
merge request. A trusted WorkStream owner reads these facts outside the checker
sandbox through one provider per forge. The networkless checker receives them
as request input and compares them with the contributor's claims. The facts
never contain a credential.

Each provider reports only what its forge can prove. A fact a forge cannot
prove is null (a review without a commit, a check result without a producer),
and the checker fails closed on it. GitHub is the only provider today
(owner decision 21, 28 October 2026).
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated, Literal, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.interfaces.external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterError,
    ExternalServiceConfigurationError,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)


FORGE_FACTS_CAPABILITY_KEY = "forge_facts"
FORGE_FACTS_SCHEMA_VERSION = "workstream.forge_change_facts.v1"
GITHUB_FORGE = "github"
Forge = Literal["github"]
SUPPORTED_FORGES: tuple[str, ...] = (GITHUB_FORGE,)
# The absolute upper bound of one facts read; provider settings stay within it
# and the selected POST budget reserves it for each binding that reads facts.
FORGE_FACTS_MAXIMUM_READ_SECONDS = 120
FORGE_FACTS_MAXIMUM_READ_MS = FORGE_FACTS_MAXIMUM_READ_SECONDS * 1000

# A repository is a path of segments, as on every forge (GitLab allows
# subgroups); each provider enforces its own stricter grammar.
_REPOSITORY_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+$")
# The web origin of one forge instance: https, host and optional port only.
_FORGE_ORIGIN = re.compile(r"^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?$")

# SHA-1 (40) or SHA-256 (64) object names, lowercase.
GitSha = Annotated[StrictStr, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
# Check conclusions, plus two derived values: ``pending`` (not completed) and
# ``missing`` (no matching result).
ForgeCheckConclusion = Literal[
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
ForgeReviewState = Literal[
    "approved", "changes_requested", "dismissed", "commented", "pending", "other"
]


def is_repository_path(value: object) -> bool:
    """Return whether a value is a forge-neutral repository path."""
    return (
        isinstance(value, str)
        and len(value) <= 255
        and _REPOSITORY_PATH.fullmatch(value) is not None
        and all(segment not in {".", ".."} for segment in value.split("/"))
    )


def is_forge_origin(value: object) -> bool:
    """Return whether a value is one forge instance's https web origin."""
    return isinstance(value, str) and _FORGE_ORIGIN.fullmatch(value) is not None


class _FactsValue(BaseModel):
    """Strict immutable facts value."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class ForgeActorFact(_FactsValue):
    """One forge account; ``kind`` is ``user``, ``bot`` or ``other``."""

    login: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    id: Annotated[StrictInt, Field(ge=1)]
    kind: Literal["user", "bot", "other"]


class ForgeReviewFact(_FactsValue):
    """One submitted review, unfiltered; reviews are listed oldest first.

    ``id`` is opaque. ``reviewer`` is null when the forge no longer has the
    account; ``commit_id`` is null when the forge cannot bind the review to a
    commit; ``reviewer_write_access`` says whether the reviewer can merge into
    the repository, and is null when the forge cannot prove it. Policy, such as
    taking each reviewer's latest review, belongs to the consumer.
    """

    id: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    reviewer: ForgeActorFact | None
    reviewer_write_access: StrictBool | None
    state: ForgeReviewState
    commit_id: GitSha | None
    submitted_at: datetime | None


class ForgeChangedFileFact(_FactsValue):
    """One changed file; ``previous_path`` is set for renames."""

    path: Annotated[StrictStr, Field(min_length=1, max_length=4096)]
    previous_path: Annotated[StrictStr, Field(min_length=1, max_length=4096)] | None
    status: Annotated[StrictStr, Field(min_length=1, max_length=50)]


class ForgeJudgedResultFact(_FactsValue):
    """One result judged for a required check.

    ``producer`` names who produced it, such as ``github_app:15368``, and is null
    when the forge gives no producer identity. ``sha`` is the commit the forge
    reports for the result.
    """

    producer: Annotated[StrictStr, Field(min_length=1, max_length=255)] | None
    sha: GitSha | None


class ForgeRequiredCheckFact(_FactsValue):
    """One check required by base-branch protection and its head-commit result.

    ``required_producer`` is the producer the requirement is bound to, or null
    when the requirement accepts any source. ``run_url`` is the forge's canonical
    URL of the CI run that produced the judged result, when the forge proves it.
    """

    name: Annotated[StrictStr, Field(min_length=1, max_length=255)]
    conclusion: ForgeCheckConclusion
    required_producer: Annotated[StrictStr, Field(min_length=1, max_length=255)] | None
    judged: tuple[ForgeJudgedResultFact, ...]
    run_url: Annotated[StrictStr, Field(max_length=2048)] | None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """A success must rest on at least one judged result."""
        if self.conclusion == "success" and not self.judged:
            raise ValueError("a successful required check has no judged result")
        return self


class ForgeResponseDigest(_FactsValue):
    """SHA-256 of one raw forge response body that produced these facts."""

    request: Annotated[StrictStr, Field(pattern=r"^[a-z_]+(?:\.page\.[1-9][0-9]*)?$")]
    sha256: Sha256


class ForgeChangeFacts(_FactsValue):
    """Immutable ``workstream.forge_change_facts.v1`` value for one change.

    ``forge_origin`` names the forge instance. ``change_number`` is the
    per-repository number (GitLab's iid). ``landed_commit_sha`` is the commit
    the change landed as on the base branch (merge, squash or rebase result),
    present exactly when the change is merged. ``head_sha`` and
    ``landed_commit_sha`` are the single change state every other fact was
    bound to: a provider re-reads the change after all other reads and discards
    the read if that state moved. Serialize with ``model_dump(mode="json")`` to
    place the value in checker request input.
    """

    schema_version: Literal["workstream.forge_change_facts.v1"] = FORGE_FACTS_SCHEMA_VERSION
    forge: Forge
    forge_origin: Annotated[StrictStr, Field(max_length=300)]
    repository: Annotated[StrictStr, Field(min_length=1, max_length=255)]
    change_number: Annotated[StrictInt, Field(ge=1)]
    change_url: Annotated[StrictStr, Field(min_length=1, max_length=2048)]
    state: Literal["open", "closed"]
    merged: StrictBool
    landed_commit_sha: GitSha | None
    base_ref: Annotated[StrictStr, Field(min_length=1, max_length=255)]
    head_sha: GitSha
    author: ForgeActorFact
    reviews: tuple[ForgeReviewFact, ...]
    changed_files_count: Annotated[StrictInt, Field(ge=0)]
    changed_files: tuple[ForgeChangedFileFact, ...]
    required_checks: tuple[ForgeRequiredCheckFact, ...] = Field(min_length=1)
    fetched_at: datetime
    responses: tuple[ForgeResponseDigest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_facts(self) -> Self:
        """Bind the listing to its count, the change to one merge state."""
        if self.changed_files_count != len(self.changed_files):
            raise ValueError("changed file count differs from the listed files")
        if not is_repository_path(self.repository) or not is_forge_origin(self.forge_origin):
            raise ValueError("repository or forge origin is not canonical")
        if self.merged != (self.landed_commit_sha is not None) or (
            self.merged and self.state != "closed"
        ):
            raise ValueError("merged state and landed commit disagree")
        return self


class ForgeFactsUnavailableError(ExternalServiceUnavailableError):
    """The forge stayed unavailable or rate-limited within the bounded retry budget."""

    code = "forge_facts_unavailable"


class ForgeFactsAccessDeniedError(ExternalServiceConfigurationError):
    """The forge credential, installation or permission is not usable."""

    code = "forge_facts_access_denied"


class ForgeRequiredChecksNotConfiguredError(ExternalServiceConfigurationError):
    """The base branch has no required checks.

    Without required checks, "CI passed" has no meaning, so facts fail closed.
    """

    code = "forge_required_checks_not_configured"


class ForgeChangeNotFoundError(ExternalServiceAdapterError):
    """The repository has no change with the requested number."""

    code = "forge_change_not_found"
    category = "not_found"


class ForgeFactsProtocolError(ExternalServiceProtocolError):
    """The forge returned a response outside the supported facts protocol."""

    code = "forge_facts_protocol_invalid"


class ForgeFactsInconsistentError(ExternalServiceUnavailableError):
    """The change kept moving while facts were read, within the deadline.

    Retryable: a later read may observe one stable state.
    """

    code = "forge_facts_inconsistent"


class ForgeFactsIncompleteError(ForgeFactsProtocolError):
    """The forge listed fewer items than it reported, so the facts would be partial."""

    code = "forge_facts_incomplete"


class ForgeChangeNotEligibleError(ExternalServiceAdapterError):
    """The change cannot be proven as claimed work for this binding.

    It targets another base branch than the locked configuration names, or it
    is larger than the forge can list. No facts are read; the checker fails.
    """

    code = "forge_change_not_eligible"
    category = "not_found"


class ForgeFactsAdapter(ExternalServiceAdapter, Protocol):
    """Read verified facts about one change with a read-only credential.

    One provider serves one forge instance, named by ``forge_origin``. It owns
    its forge's URL and repository grammar.
    """

    @property
    def forge_origin(self) -> str:
        """Return the web origin of the forge instance this provider reads."""

    def parse_change_url(self, value: object) -> tuple[str, int] | None:
        """Return (repository, number) from one canonical change URL, or None.

        This is the single parser for a claimed change URL. The checker
        re-asserts exact equality of the claim with the facts' ``change_url``,
        so the reader and the checker cannot disagree.
        """

    async def fetch_change_facts(
        self,
        *,
        repository: str,
        change_number: int,
        base_branch: str,
    ) -> ForgeChangeFacts:
        """Return facts, or raise a secret-free ``ExternalServiceAdapterError``.

        A change whose base is not ``base_branch`` raises
        ``ForgeChangeNotEligibleError`` before protection is read.
        """
