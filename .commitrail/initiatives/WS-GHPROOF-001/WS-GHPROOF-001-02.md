# WS-GHPROOF-001-02 — GitHub facts port and GitHub App adapter

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: WorkStream has a typed, secret-safe GitHub facts capability that reads one pull request's merge state, author, reviews, changed files and base-branch required-check results as a read-only GitHub App, registered per ADR 0014 and not yet called by a production path.

## Intent

Chunk 04 must read GitHub facts inside the selected POST evaluation handler.
This chunk provides the bounded, tested capability it will call, so the wiring
chunk adds no transport, credential or retry logic of its own.

## Current behavior

- No GitHub client, port or setting exists under `backend/app`.
- `backend/app/interfaces/external_services.py` defines the ADR 0014 adapter
  protocol, shared errors and `ExternalServiceAdapterFactory`.
- `SELECTED_POST_HANDLER_TIMEOUT_SECONDS` in
  `backend/app/modules/checkers/api/external_policy.py` is 3,520 seconds
  (3,400 s execution budget plus 60 s prelude and 60 s finalization margins).

## Bounded change

### Allowed

- `backend/app/interfaces/github_facts.py`: capability and provider keys, the
  frozen `workstream.github_facts.v1` model, typed errors and the
  `GitHubFactsAdapter` port.
- `backend/app/adapters/github/__init__.py` (composition root) and
  `backend/app/adapters/github/app_facts.py` (GitHub App provider).
- `backend/app/core/config.py` GitHub App settings, the private-key secret
  custody and their validators;
  commented examples in `backend/.env.example`.
- `backend/tests/test_github_facts_adapter.py`, its lane-catalogue entry and
  shared-family fingerprint, and the behavior-ownership partition additions.
- `backend/tests/test_artifact_architecture.py`: the GitHub adapter package
  is registered as one more approved external-service composition root.

### Not allowed

- Any production caller, POST wiring, ART custody, checker change, migration,
  API route or hosted secret configuration (chunks 03 to 06).

## Design and decisions

- **GitHub App.** The intended App is `flow-workstream-proof-reader` (App id
  5454828), installed on the Flow-Research repositories with read access to
  administration, checks, metadata, pull requests and statuses. Its private key
  stays in the operator's secret store; no key is committed, and tests generate
  a throwaway RSA key.
- **Authentication.** An RS256 App JWT (PyJWT, 60 s backdated, 9 min lifetime)
  is used only to look up the repository installation (unless
  `WORKSTREAM_GITHUB_APP_INSTALLATION_ID` is set) and to exchange an installation
  token scoped to that one repository. Tokens are cached per repository until
  five minutes before GitHub's `expires_at`. A 401 on a cached token forces one
  fresh exchange; a second 401 is access denied.
- **Requests.** `GET /repos/{r}/pulls/{n}`;
  `GET /repos/{r}/branches/{base}/protection/required_status_checks` for the
  pull request's actual base branch; then `check-runs` and the combined
  `status` for the head SHA, with `per_page=100` and `Link: rel="next"`
  pagination up to 10 pages. A next link to another origin is a protocol error,
  so a response cannot redirect the credential. Redirects are not followed.
- **Required checks.** The required set is the union of protection
  `checks[].context` (with its optional App id; `-1` or null means any source)
  and `contexts` (any source). A check restricted to an App matches only that
  App's check runs; an unrestricted check matches check runs and commit
  statuses by name.
- **Re-runs.** A head commit can carry several check runs with one name. A live
  read of Flow-Research/harnessy-v2 PR #169 found 47 runs for 24 names, where a
  failed first attempt was re-run successfully; judging any run per name gave a
  false failure. For each required check only the most recent check run
  (highest GitHub id) and the most recent commit status (highest id) count.
  When both exist, both must be `success`; otherwise the first non-success value
  is reported. No match is `missing`; an incomplete run is `pending`. `neutral`
  and `skipped` are not `success`.
- **Missing protection fails closed.** A 404 from the protection endpoint, or an
  empty required-check list, raises `GitHubRequiredChecksNotConfiguredError`
  (a non-retryable configuration error). Without required checks "CI passed"
  has no meaning, and retrying cannot fix it.
- **Errors.** Retries exhausted or a rate-limit wait beyond the deadline:
  `GitHubFactsUnavailableError` (retryable). Pull request 404:
  `GitHubPullRequestNotFoundError`. 401/403 without rate-limit headers, or an
  App not installed: `GitHubFactsAccessDeniedError`. Malformed bodies, another
  repository's pull request or other 4xx: `GitHubFactsProtocolError`. Chunk 04
  decides how each maps to an infrastructure failure or a checker finding.
- **Retry budget.** Transport errors, 408, 5xx and rate limits retry up to
  `WORKSTREAM_GITHUB_FACTS_MAXIMUM_ATTEMPTS` (default 3, max 5) per request,
  with 0.5 s exponential backoff, honoring `Retry-After` and
  `x-ratelimit-reset`. One facts read, all retries included, is bounded by
  `WORKSTREAM_GITHUB_FACTS_TOTAL_DEADLINE_SECONDS` (default 45 s, max 120 s),
  about 3% of the 3,520 s handler timeout at the maximum. Chunk 04 must place
  this budget inside the handler prelude or reserve it from the execution
  budget; the 60 s prelude margin alone is already partly used.
- **Credential custody.** The PEM key is the secret setting
  `WORKSTREAM_GITHUB_APP_PRIVATE_KEY`. Settings remove it from structured input
  before validation and hold it only as a private redacted `SecretStr`,
  following the `pagination_cursor_hmac_secret` custody path (direct, JSON,
  string and dotenv inputs; cleared on failure). It must be configured together
  with the App id. Single-line values with literal `\n` separators are
  accepted. The adapter parses it once (bounded to 16 KiB) and holds only an
  `RSAPrivateKey`. Tokens live
  only in `_InstallationToken`, whose representation is redacted. Every
  adapter error is raised `from None` and carries only its code. Retry logs
  carry only status and attempt. Token-exchange bodies are never hashed or
  returned; facts hold only GitHub data and response digests.
- **Integrity facts (owner decision 20, 2026-10-24).** The reader stays
  factual and makes no policy decision. It adds the pull request author
  (`login`, numeric `id`, `type` such as `User` or `Bot`); every submitted review
  from `GET /pulls/{n}/reviews` (review `id`, reviewer or null for a deleted
  account, `state`, `commit_id`, `submitted_at`), unfiltered, because choosing
  each reviewer's latest review is the checker's rule; and every changed file
  from `GET /pulls/{n}/files` (`filename`, `previous_filename` for renames,
  `status`). Both lists paginate with `per_page=100`; each page body is hashed.
- **Incomplete file lists fail closed.** GitHub lists at most 3,000 changed
  files. If the pull request's `changed_files` exceeds 3,000, or the listing
  length differs from it, the read raises `GitHubFactsIncompleteError` (a
  protocol error), so a protected-path rule can never miss a file.
- **One pull-request state (security review, time-of-check binding).** Facts
  come from several calls; reviews and files are listed by pull-request number,
  not by commit, and protection can change between calls, so one object could
  mix two states. After every other read the adapter re-reads the pull request
  (`pull_request_final`, hashed like the first read) and requires `head_sha`,
  `merged`, `merge_commit_sha`, `base_ref`, `state` and `changed_files` to equal
  the first read exactly. If they differ, it discards the whole read and starts
  again, up to three whole reads within the same deadline, then raises the
  retryable `GitHubFactsInconsistentError` (an availability error, so chunk 04
  maps it to an infrastructure failure). The changed-file listing must match
  the count both reads reported. Every check run returned for the head SHA
  must report that `head_sha`, and every combined-status page must report it as
  its `sha`; otherwise the read is a protocol error. The facts' `head_sha` and
  `merge_commit_sha` are the single state all facts were bound to; each
  required check records `check_run_head_sha` and `commit_status_sha` so the
  checker can verify the binding. Reviews keep their own `commit_id`; the
  checker counts only reviews of the head SHA.
- **One canonical pull-request identity (security review, parser
  differential).** The facts carry GitHub's own pull-request `html_url`. For the
  judged check run they carry `check_run_html_url`, `check_run_details_url` and
  `workflow_run_id`. The App has no Actions read permission, so the workflow run
  id is taken only from a GitHub Actions App (id 15368) `details_url` of the
  form `https://github.com/{repository}/actions/runs/{id}[/job/{job}]` for this
  repository; other producers give null. `parse_pull_request_url` in the port
  module is the single parser for a claimed pull-request URL: it accepts only
  ASCII `https://github.com/{owner}/{name}/pull/{number}`. Chunk 04 must take
  the pull-request number from this function, and the checker re-asserts exact
  equality of the claim with the facts, so fetcher and checker cannot disagree.
- **Check provenance.** Each required check also records `app_bound` (the
  requirement names an App), `check_run_app_id` (the App that produced the
  judged latest run, or null) and `commit_status_judged` (a commit status, which
  has no App identity, was judged). The schema id stays
  `workstream.github_facts.v1` because the shape is unreleased.
- **Facts.** `merge_commit_sha` is null unless merged, because GitHub reports a
  test-merge commit for open pull requests. `responses` lists the SHA-256 of
  each raw facts response body in request order.
- Rejected: following redirects or arbitrary `Link` origins; caching tokens
  across repositories; treating missing protection as "no checks required";
  logging response bodies.

## Acceptance criteria

- [x] Only the latest re-run per required check counts, in both directions,
  and the required set is the union of `checks` and `contexts`.
- [x] Author, all reviews (paginated, unfiltered) and all changed files
  (paginated) are returned and hashed; more files than GitHub can list, or a
  short listing, fails as incomplete.
- [x] A pull request that moves during a read is re-read and bound to one
  state; one that keeps moving, or whose merged flag flips, fails as
  inconsistent; check runs or statuses for another commit fail.
- [x] Facts carry the pull-request `html_url` and each judged run's URLs and
  workflow run id; the canonical URL parser rejects every non-canonical form.
- [x] Each required check records its App binding and the producing App or
  status source of the judged result.
- [x] Happy path returns the exact facts, response digests, a verifiable JWT
  and a repository-scoped token request.
- [x] Pagination is followed within the origin; a foreign link fails.
- [x] Missing protection, unknown pull request, wrong repository and access
  denial raise their typed errors.
- [x] 5xx and transport errors retry then succeed; exhausted retries and
  deadline-bounded rate limits raise `GitHubFactsUnavailableError`.
- [x] The key, JWT and tokens are absent from error strings, representations,
  rendered tracebacks, log records and facts.
- [x] The factory registers the sole `github_app` provider; incomplete or unsafe
  settings fail.

## Risk and review routing

- Risk class: L1, new external credential custody without a production caller.
  The App's administration read permission is needed for classic branch
  protection reads.
- Required reviewers: security, senior engineering, QA.
- Human review focus: the GitHub App permission set (classic branch protection
  reads need repository administration read), fail-closed missing protection,
  strict `success` versus GitHub's own acceptance of `neutral`/`skipped`, and
  the retry budget placement for chunk 04.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Adapter behavior and secret custody | `pytest tests/test_github_facts_adapter.py` | 122 passed | Uses `httpx.MockTransport`; the re-run rule comes from a separate live read, not from this suite |
| Every fail-closed branch rejects | `coverage run --branch --include='app/adapters/github/*,app/interfaces/github_facts.py' -m pytest tests/test_github_facts_adapter.py`; `coverage report -m` | 100% line and branch on `app_facts.py`, `github/__init__.py` and `github_facts.py` (before: 90% and 98%) | Coverage shows execution; each added test asserts the typed error or outcome |
| Re-run test detects order-based selection | Temporarily selecting the last listed run made both re-run cases fail | Detected | Manual negative control |
| Secret tests detect leaks | Temporarily unredacting the token repr, and logging the Authorization value, each made one test fail | Detected | Manual negative control |
| Lane catalogue, boundaries, ownership | `tests/test_ci_lane_catalogue.py`, `tests/architecture/test_module_boundaries.py`, `tests/test_behavior_ownership.py`, `scripts.behavior_ownership validate`, `module_boundaries`, `authorization_boundary`, `test_structure_boundary` | Pass | None |
| Settings | `tests/test_config.py` plus the new settings cases | Pass | None |
| Lint | `ruff check app tests scripts`; `docstr-coverage` | Pass (80.2%) | — |

These ran on macOS in a `uv pip` environment resolved from `pyproject.toml`,
because `uv.lock` supports Linux only. Hosted Backend CI owns the locked run.

## Review findings

- Coverage review: three unreachable branches were removed rather than kept as
  dead code: a deadline check between consistency attempts (the next request
  already fails with `GitHubFactsUnavailableError` once the deadline is spent),
  a full-URL branch in the API-path helper (only paths reach it), and the
  natural exit of the retry `for` loop (every exit is an explicit break).

## Reconciliation

- Current-source reconciliation: based on WS-GHPROOF-001-01 over `main` after
  PR #674.
- Roadmap: no impact. No production path calls the capability, so no
  capability, exposure or dependency on `main` changes.
- Next usable boundary: chunk 04 POST wiring after PR #677 and chunk 03.
- Remaining risks: live GitHub behavior is unproven until chunk 06.
