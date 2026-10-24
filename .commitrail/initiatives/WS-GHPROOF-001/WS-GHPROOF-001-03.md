# WS-GHPROOF-001-03 — Harnessy proof checker compares proofs with GitHub facts

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: The networkless, post-submission `harnessy.work_proof` checker passes a proof only when it matches WorkStream-supplied `workstream.github_facts.v1` facts and the integrity rules of owner decision 20, failing closed on missing configuration or facts, with one finding per mismatch and a v2 registry body that validates its configuration.

## Intent

A hand-written `proof.json` passes today. Once WorkStream supplies GitHub facts
(chunk 04), this checker makes a faked or unreviewed proof fail, while the
checker stays networkless and credential-free. Verification integrity is
non-negotiable (owner decision 20, 24 October 2026): fail closed and trust
nothing the contributor could produce.

## Current behavior

- `external_checkers/harnessy_proof/checker.py` checks only proof shape and
  ignores the request `configuration` and `input`.
- `external_checkers/harnessy_proof/publish_local.py` publishes PRE and POST
  bodies with `{"type": "object"}` configuration and input schemas, default
  version `v1`.
- `docs/engineering/local-agent-loop.md` documents shape checking only.

## Bounded change

### Allowed

- `external_checkers/harnessy_proof/checker.py`, `publish_local.py` (standard
  library only).
- `backend/tests/checkers/external/test_harnessy_proof_checker.py` (already in
  the lane catalogue).
- `docs/engineering/local-agent-loop.md` publishing, registration and checker
  sections; the two agent-loop mentions in `docs/roadmap_status.md`.

### Not allowed

- Backend runtime, POST wiring, the GitHub adapter (chunk 02), checker network
  access, the checker service, ART custody, or Harnessy's proof format.

## Design and decisions

- **One fail-closed mode (security review, fail-open finding).** The binding
  configuration must name `github_repository` and `base_branch`; a missing,
  empty or invalid configuration is `github.configuration`. Facts must be
  present (`github.facts_missing`) and have the exact v1 shape
  (`github.facts_invalid`). There is no shape-only pass. The local agent loop
  does not need one: until chunk 04 supplies facts every evaluation fails with
  `facts_missing`, which the runbook states. Workstream keeps no compatibility
  mode.
- **Post-submission only.** PRE checking never has facts, so `publish_local.py`
  writes only `registry-post.json`; the runbook registers POST only.
- **Input shape.** WorkStream places chunk 02's
  `GitHubPullRequestFacts.model_dump(mode="json")` in the request `input` under
  `github_facts`, so the request digest binds it. The fields are
  `schema_version`, `repository`, `pull_request_number`, `html_url`, `state`,
  `merged`, `merge_commit_sha` (null unless merged), `base_ref`, `head_sha`,
  `author`, `reviews`, `changed_files_count`, `changed_files`,
  `required_checks` (`name`, `app_id`, `app_bound`, `conclusion`,
  `check_run_app_id`, `check_run_head_sha`, `check_run_html_url`,
  `check_run_details_url`, `workflow_run_id`, `commit_status_judged`,
  `commit_status_sha`), `fetched_at` and `responses`. Required-check entries
  must have exactly these keys.
- **One canonical identity (security review, parser differential).** The
  checker parses no URL. `pr_url` must equal
  `https://github.com/{facts.repository}/pull/{facts.pull_request_number}`
  exactly, and GitHub's `html_url` must equal the same string; otherwise
  `github.pr_url`. Comparison is case-sensitive against the repository name
  GitHub returns, so a trailing slash, query, fragment, port, user information,
  percent encoding, backslash or non-ASCII character fails. `ci_run_url` must
  equal `https://github.com/{repository}/actions/runs/{id}` (the canonical form,
  without `/job/{id}`) for the `workflow_run_id` of at least one judged required
  check; otherwise `github.ci_run`. The fetcher (chunk 04) takes the
  pull-request number from chunk 02's single `parse_pull_request_url`, and this
  checker re-asserts equality, so the two cannot disagree.
- **Commit binding (security review, time-of-check).** A required-check entry
  whose `check_run_head_sha` or `commit_status_sha` names a commit other than
  `head_sha` fails as `github.facts_binding`. Reviews keep their own
  `commit_id`: a review of an earlier commit is normal history, so it is not a
  failure, but only reviews of `head_sha` can approve.
- **Comparisons.** `repository` (case-insensitive against configuration),
  `base_branch`, `merged`, `merge_commit_sha` (lower-cased proof SHA) and one
  `required_check` per non-success check. The proof's own `schema`,
  `commit_sha`, `ci_conclusion` and `merged` claims keep their rules. The former
  "any `https://github.com/` URL" rules for `pr_url` and `ci_run_url` are
  replaced by the exact-equality rules.
- **Integrity rules (owner decision 20).** `unbound_required_check` (a
  requirement accepting any source; config `allow_unbound_required_checks`,
  default false); `protected_path_changed` (one finding listing up to five paths
  that match `.github/**`, `**/CODEOWNERS`, `.gitlab-ci.yml`, `.circleci/**` or
  configured `protected_paths`, checking both names of a rename; it states that
  the work requires explicit human acceptance and cannot be auto-accepted);
  `independent_approval_missing` (fewer than `required_independent_approvals`,
  default 1, reviewers whose latest `APPROVED`/`CHANGES_REQUESTED`/`DISMISSED`
  review by id approves the head SHA, excluding the author by id or login and
  every non-`User` account; comments do not cancel an approval). When all
  qualifying approvals come from `operator_logins`, the checker adds code
  `harnessy.operator_approved` at level `warning`, which does not fail the
  verdict. `warning` rather than the lower `info` is used because contributor
  and history reads count only blocking, warning and coverage findings, so an
  `info` finding would be invisible.
- **Registry schemas.** The POST `configuration_schema` requires both keys,
  allows only the integrity options, and bounds them. The POST `input_schema`
  constrains `github_facts.schema_version`; a missing facts object reaches the
  checker as `facts_missing`. `publish_local.py` defaults to capability version
  `v2` because `v1` is immutable and both behavior and schemas changed.
- Rejected: a shape-only mode, PRE registration, URL parsing in the checker,
  a second ART mount for facts (owner decision), and requiring `github_facts`
  in the input schema (that would turn a missing fact into a request contract
  error instead of a clear finding).

## Acceptance criteria

- [x] A proof matching the facts passes; missing or invalid configuration and
  missing or malformed facts never pass.
- [x] Each mismatch reports its finding: repository, base branch, merged, merge
  commit SHA, each non-success required check, and commit binding.
- [x] Every rejected `pr_url` variant, a differing `html_url`, and every
  `ci_run_url` that is not a judged required workflow run fail.
- [x] Each integrity rule has its own finding and edge-case tests: stale
  approval on an old commit, approval then changes requested or dismissed, bot
  approval, author self-approval, rename into or out of `.github`, unbound
  check, and operator-only approval.
- [x] The published v2 body is post-submission only and validates through
  `ExternalCheckerRegistrySpec`, accepting and rejecting configuration and
  input as documented.

## Risk and review routing

- Risk class: L1, it changes acceptance evidence for automatic FinalAcceptance
  once wired.
- Required reviewers: security, QA, documentation.
- Human review focus: the finding set, failing closed everywhere, strict
  `success` for required checks, and `warning` for operator-only approval.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Rules and result contract | `pytest tests/checkers/external/test_harnessy_proof_checker.py` | 116 passed | Facts agreement with chunk 02 was checked in a scratch run against that branch, not by a committed cross-branch test; chunk 04 should add one |
| Every fail-closed branch rejects | `coverage run` with `branch = true`, `patch = subprocess`, `include = */harnessy_proof/checker.py`, then `coverage combine` and `coverage report -m` | 100% line and branch on `checker.py` (before: 96%) | The isolated `python -I` entrypoint is measured through coverage's subprocess patch |
| Lint | `ruff check` on the test module and `external_checkers/harnessy_proof/` | Pass | — |
| Docs | Markdown link and stale wording checks | Pass | — |

The image was not rebuilt or run: Docker was out of scope for this change.

## Review findings

- Coverage review found a defect: a `proof.json` directory in the submitted
  archive made `read_proof` raise `IsADirectoryError`, crashing the checker
  instead of reporting `harnessy.proof.missing`. `read_proof` now checks the
  file type on the raw descriptor before wrapping it; directory and FIFO
  regressions cover it.
- Security review, fail-open integrity check: removed the shape-only pass and
  the facts-without-configuration path.
- Security review, parser differential: replaced URL parsing with exact
  equality to canonical URLs built from the facts, and bound `ci_run_url` to a
  judged required workflow run.
- Security review, time-of-check binding: added the commit-binding finding.

## Reconciliation

- Current-source reconciliation: based on WS-GHPROOF-001-01 over `main` after
  PR #674; independent of chunk 02.
- Roadmap: the agent-loop entries now state that the checker compares proofs
  with GitHub facts and that FinalAcceptance through it also waits for facts
  wiring (chunk 04).
- Next usable boundary: chunk 04 POST wiring.
- Remaining risks: until chunk 04, every evaluation with this checker fails
  with `facts_missing`.
