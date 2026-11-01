# WS-GHPROOF-001-04 — Forge-neutral facts read in POST evaluation

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: For a selected POST binding that opts into forge facts, WorkStream reads the claimed change's `workstream.forge_change_facts.v1` facts from the configured forge instance and repository through the forge facts port and places them in the checker request input; forge failures end as recoverable infrastructure failures and never pass. The port is forge-neutral, with GitHub as its only provider.

## Intent

Chunk 03 made the checker compare proofs with facts, but no production path
supplied them, so every evaluation failed with `facts_missing`. This change
supplies them. Owner decision 21 (28 October 2026) also requires that
WorkStream not be coupled to GitHub: chunk 02's GitHub-named port is replaced
by a forge-neutral one before any caller depends on it.

## Current behavior

- `app/interfaces/github_facts.py` defines a GitHub-specific port and
  `workstream.github_facts.v1` value; nothing calls it.
- `SelectedPostSubmitProcessor` never reads facts.
- The GitHub adapter's per-request timeouts did not bound a whole read: a slow
  response could run past `github_facts_total_deadline_seconds`, and facts
  finished after the deadline were still returned (Codex review finding on
  PR #682).

## Bounded change

### Allowed

- `backend/app/interfaces/forge_facts.py` (replaces `github_facts.py`).
- `backend/app/adapters/github/` (maps GitHub into the neutral facts; absolute
  time limit), `backend/app/adapters/checkers/__init__.py` and
  `backend/app/adapters/tasks/__init__.py` (composition).
- `backend/app/modules/checkers/api/external_policy.py`,
  `selected_post_submit_execution.py`, `execution.py`.
- The facts read reserved in guide proposal budgets and instructions
  (`app/interfaces/project_agents.py`, `app/core/project_guide_instructions.py`)
  and the settings bound in `app/core/config.py`.
- Tests: `test_github_facts_adapter.py`, `checkers/external/test_policy.py`,
  `checkers/external/test_selected_post_submit.py`,
  `projects/guide_compilation/test_check_specifications.py`.
- Ownership catalogue entries for the renamed port; `.env.example`; the
  runbook, roadmap and initiative records.

### Not allowed

- Checker network access, the checker service, ART custody of facts (05),
  hosted credentials (06), lifecycle routing, account pausing or overrides
  (07), Harnessy's proof format, a second forge provider.

## Design and decisions

- **Forge-neutral port (decision 21).** Capability `forge_facts`; provider key
  is the forge name (`github`). `ForgeChangeFacts` carries `forge`,
  `forge_origin` (the web origin of the forge instance, so GitHub Enterprise
  or a self-hosted GitLab is a different instance), `repository` (neutral path
  grammar: two or more segments, so GitLab subgroups fit), `change_number` (the
  per-repository number, GitLab's iid), `change_url`, the change state,
  `landed_commit_sha` (the commit the change landed as; present exactly when
  merged, and merged implies closed), author, reviews, changed files
  (`path`, `previous_path`), and required checks with `required_producer`,
  `judged` results (`producer`, `sha`) and `run_url`. Reviews are listed oldest
  first, their ids are opaque strings, and each carries `reviewer_write_access`.
  A provider that cannot prove a fact reports null, and the checker fails
  closed on it. A `success` with no judged result is invalid. Commit names may
  be SHA-1 or SHA-256.
- **GitHub provider.** All GitHub grammar lives in the provider: its
  `parse_change_url` accepts only `{origin}/{owner}/{name}/pull/{number}`; App
  ids become `github_app:<id>`; the web origin follows the API URL
  (`https://github.com` for `api.github.com`, the Enterprise host otherwise);
  `html_url` must equal the canonical change URL; run URLs use the same origin.
  For each user who approved the head commit (at most 20) it reads the
  reviewer's current repository permission; `admin`, `maintain` and `write`
  count, a missing record or one naming another account does not, an
  approving bot or other non-user account has none and is never looked up,
  and other reviewers' access is reported as unknown. Because anyone can
  review or run checks on a change, more approving users, reviews, check runs
  or statuses than the provider lists make the change ineligible (no facts,
  the proof fails) rather than an outage an Operator would retry forever. A
  token GitHub refuses for the repository is an access failure, and a
  provider whose web origin is not https is refused when it is configured. It reads the
  repository first, so a repository outside the App's installation is an
  access failure rather than a contributor's missing change. Settings keep
  GitHub names because they configure the GitHub provider.
- **Selection.** A binding selects facts with `workstream_forge_facts_version:
  "v1"`, a supported `forge`, an https `forge_origin`, a `repository` path and
  a `base_branch`, validated when the binding is locked; the published
  configuration schema must declare the selection key, as for evaluation
  context (#677). PRE bindings cannot select it.
- **Which change.** The worker resolves the provider for the selected forge and
  requires its `forge_origin` to equal the selection's. It reads `proof.json`
  (at most 64 KiB, listed as a file in the verified manifest) and its `pr_url`,
  parses it with the provider's `parse_change_url`, and reads facts only when
  the repository equals the configured one (case-insensitively), always naming
  the configured repository and base branch. Any of these yields no facts, and
  the checker fails the proof: a missing, oversized or malformed `proof.json`
  (the checker reports `missing`, `too_large` or `invalid_json`); a claim
  without a usable `pr_url` or naming another repository, a change the forge
  does not have, a change into another base branch, more files, reviews or
  checks than the forge lists, or facts too large for the 1 MiB checker input
  (the checker reports `facts_missing`). A listing shorter than the change's
  reported file count is an incomplete read (`invalid_output`), not an
  ineligible change. Integrity errors reading the verified file propagate.
- **Failures.** Unavailable or inconsistent forge reads, credential or
  permission refusal, an unreadable repository, missing required checks, an
  unconfigured or unknown provider, a provider for another instance, and no
  resolver all end as `implementation_unavailable`; protocol and incomplete
  reads (including non-transport HTTP client errors) as `invalid_output`. Both
  are infrastructure failures an Operator can retry; the checker never runs,
  so nothing passes.
- **Time.** The provider wraps the whole read in an absolute timeout and
  discards facts completed after its deadline. One constant,
  `FORGE_FACTS_MAXIMUM_READ_SECONDS` (120), bounds the provider setting; the
  selected POST budget and guide proposal budgets reserve it per binding that
  selects facts, and the guide instructions say so.
- **Composition.** A lazy resolver from the forge facts factory is a required
  argument of the delivery and reconciliation executors; a provider is
  constructed only when a binding selects it. Each evaluation builds its own
  provider, because evaluations may run on separate event loops.
- Rejected: keeping GitHub names with a later rename (decision 21), a
  compatibility alias for `github_facts`, a project-level repository setting,
  reading facts for the repository named in the claim, a GitHub URL grammar in
  the neutral port, ordering reviews by id, sharing one provider across
  evaluations.

## Acceptance criteria

- [x] Selected facts reach the checker request input under `forge_facts`, and
  the request input digest binds them; each selecting binding reads its own.
- [x] Unusable claims (no proof, a non-file proof, invalid JSON, deep nesting,
  non-object, no URL, another repository, a trailing slash, another forge's
  URL) read no facts; an unselected binding never calls the resolver.
- [x] Every forge failure class, an unconfigured provider and a provider for
  another instance map to their infrastructure code and the checker does not
  run; a missing or ineligible change reads no facts.
- [x] Selection is rejected for wrong version, unsupported forge, invalid
  origin, repository or branch, PRE phase, or an undeclared schema key; the
  selected POST budget and guide proposal budgets reserve the facts read.
- [x] The GitHub provider emits neutral facts, including the instance origin
  (public and Enterprise), account kinds, review order and states, reviewer
  write access, both judged results of an unbound check and the canonical run
  URL, and rejects a non-canonical pull request URL.
- [x] Facts the provider emits satisfy the checker's own facts validation
  (contract test against `external_checkers/harnessy_proof/checker.py`).
- [x] A stalled or late read raises facts-unavailable; both regressions fail
  on the previous adapter.

## Risk and review routing

- Risk class: L1. It supplies the evidence automatic FinalAcceptance relies on.
- Required reviewers: security, architecture, QA. Internal security and
  architecture reviews ran on 28 October 2026; their findings are fixed here
  or listed under remaining risks.
- Human review focus: which instance and repository are read, reviewer write
  access, every failure ending as infrastructure and never as a pass, the
  neutral facts shape, and the budget.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Adapter, contract, policy, processor and guide budget behavior | `pytest tests/test_github_facts_adapter.py tests/checkers/external/test_policy.py tests/checkers/external/test_selected_post_submit.py tests/projects/guide_compilation/test_check_specifications.py` (macOS, Python 3.12, outside the Linux lockfile) | 165, 31 and 35 passed; guide specifications pass; the 2 database-backed processor tests need CI | Database-backed and Linux-only suites run in CI |
| No regression in checker suites | `pytest tests/checkers/` on this branch and on `origin/main` | This branch's failures are a subset of main's (environment only: Postgres and Linux sockets) | CI is authoritative |
| Ownership partition | `behavior_ownership.py validate --trusted-revision origin/main`; `pytest tests/test_behavior_ownership.py tests/test_ci_lane_catalogue.py tests/test_ci_test_lanes.py` | Pass; 244 passed | — |
| Deadline regressions are discriminating | New deadline tests against the previous adapter | Both fail | — |
| Lint | `ruff check` on changed Python files | Pass | — |

## Reconciliation

- Builds on chunk 03 (PR #683), reworked to the same neutral contract
  (revision 2 of 28 October 2026 on both sides).
- Roadmap: the agent-loop entries now say POST evaluation reads forge facts;
  hosted credentials, custody and guide bindings remain.
- Next usable boundary: chunk 05 (durable custody) and chunk 06 (hosted
  credentials and end-to-end drill).
- Remaining risks:
  - Until chunk 07, a protected-path change fails instead of waiting for human
    acceptance.
  - Harnessy's proof still names `pr_url`.
  - The same merged change can be claimed by more than one submission; chunk
    05 or 07 must bind a change to one submission.
  - Required checks come from classic branch protection only; checks required
    by repository rulesets are not seen. Chunk 06 confirms the Flow
    repositories use classic protection.
  - Write access is read at evaluation time, not at review time.
  - A provider whose web origin is not https is refused when it is
    configured, so a local drill needs a TLS fake forge (chunk 06).
  - Each evaluation mints its own installation token.
  - A listing within its page bound can still be too slow for the read
    deadline; that ends as a retryable infrastructure failure.
  - Reviews are ordered by GitHub review id (creation order). A pending
    review created before an approval but submitted after it sorts first;
    GitHub allows one pending review per user, so the window is narrow.
  - With a fixed installation id, the token request names the repository
    without its owner; chunk 06 checks the installation account.
