# WS-GHPROOF-001-03 — Harnessy proof checker compares proofs with forge facts

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: The networkless, post-submission `harnessy.work_proof` checker passes a proof only when it matches WorkStream-supplied forge-neutral `workstream.forge_change_facts.v1` facts and the integrity rules of owner decisions 20 and 21, failing closed on missing configuration or facts, with one finding per mismatch and a v2 registry body that validates its configuration.

## Intent

A hand-written `proof.json` passes today. Once WorkStream supplies forge facts
(chunk 04), this checker makes a faked or unreviewed proof fail, while the
checker stays networkless and credential-free. Verification integrity is
non-negotiable (owner decision 20, 24 October 2026): fail closed and trust
nothing the contributor could produce. WorkStream must not be coupled to
GitHub (owner decision 21, 28 October 2026): the checker consumes
forge-neutral facts that any git host ("forge") provider can produce; only the
GitHub provider is built.

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
  configuration must set `workstream_forge_facts_version` to `v1` and name
  `forge` (`github` only today), `forge_origin`, `repository` and
  `base_branch`; anything
  missing, unknown or invalid is `forge.configuration`. Facts must be present
  (`forge.facts_missing`) and have the exact v1 shape (`forge.facts_invalid`).
  There is no shape-only pass: until chunk 04 supplies facts every evaluation
  fails with `facts_missing`, which the runbook states.
- **Post-submission only.** PRE checking never has facts, so `publish_local.py`
  writes only `registry-post.json`; the runbook registers POST only.
- **Forge-neutral input (owner decision 21).** WorkStream places
  `workstream.forge_change_facts.v1` in the request `input` under
  `forge_facts`, so the request digest binds it. Every object has exactly its
  specified keys: `forge`, `forge_origin` (the instance's https web origin),
  `repository` (neutral path grammar: two or more segments, GitLab subgroups
  allowed), `change_number` (per-repository number), `change_url`, `state`,
  `merged`, `landed_commit_sha` (the merge, squash or rebase result; present
  exactly when merged, and merged implies closed), `base_ref`, `head_sha`,
  `author` and reviewers as `{login, id, kind}`, reviews in chronological order
  with an opaque string `id` and `reviewer_write_access` (bool or null),
  lowercase review states, `changed_files` as `{path, previous_path, status}`, and
  `required_checks` as `{name, conclusion, required_producer, judged[{producer,
  sha}], run_url}`. Commit ids are 40 or 64 lowercase hexadecimal characters,
  and the proof's `commit_sha` claim accepts both lengths. What a provider
  cannot prove is null, and the rules treat null as not proven.
- **No URL construction (security review, parser differential).** The checker
  parses and builds no URL. `pr_url` must equal the facts' `change_url`
  exactly (`forge.change_url`), and `ci_run_url` must equal the `run_url` of at
  least one required check (`forge.ci_run`). Any trailing slash, query,
  fragment, port, user information, percent encoding, case or non-ASCII
  difference fails.
- **Commit binding (security review, time-of-check).** A judged result whose
  `sha` names a commit other than `head_sha` fails as `forge.facts_binding`.
  Reviews keep their own `commit_id`: a review of an earlier commit is normal
  history, but only reviews of `head_sha` can approve, and a null `commit_id`
  never approves.
- **Comparisons.** `forge` and `forge_origin` (exact) and `repository`
  (case-insensitive) against configuration as `forge.repository`,
  `base_branch`, `merged`, `landed_commit_sha` (lower-cased proof SHA) and one
  `required_check` per
  non-success check. The proof's own `schema`, `commit_sha`, `ci_conclusion`
  and `merged` claims keep their rules.
- **Integrity rules (owner decision 20).** `unbound_required_check` (null
  `required_producer`; config `allow_unbound_required_checks`, default false);
  `producer_mismatch` (a bound check with any judged result from a different or
  unknown producer; not suppressed by the unbound option);
  `protected_path_changed` (one finding listing up to five paths that match
  `.github/**`, `**/CODEOWNERS`, `.gitlab-ci.yml`, `.gitlab/**`,
  `.circleci/**`, `.forgejo/**`, `.gitea/**`, `.woodpecker/**`,
  `.woodpecker.yml`, `.woodpecker.yaml` or configured
  `protected_paths`, checking `path` and `previous_path`; it states that the
  work requires explicit human acceptance and cannot be auto-accepted);
  `independent_approval_missing` (fewer than `required_independent_approvals`,
  default 1, reviewers whose last `approved`/`changes_requested`/`dismissed`
  review by list position approves the head SHA, from a `user` account that is
  not the author by id or login and whose `reviewer_write_access` is `true`;
  review ids are never ordered). When all qualifying approvals come
  from `operator_logins`, the checker adds code `harnessy.operator_approved`
  at level `warning`, which does not fail the verdict; `info` would be
  invisible to contributor and history reads.
- **Registry schemas.** The POST `configuration_schema` requires the five
  binding keys (`workstream_forge_facts_version` const `v1`, `forge` enum
  `github`, `forge_origin` matching `^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$`,
  a repository in the neutral path grammar, `base_branch`), allows only the
  integrity options and bounds them. The POST `input_schema` constrains
  `forge_facts.schema_version`; a missing facts object reaches the checker as
  `facts_missing`. `publish_local.py` defaults to capability version `v2`,
  which has never been published.
- Rejected: a shape-only mode, PRE registration, URL parsing or building in the
  checker, `github_facts` aliases or a GitHub-specific facts schema (owner
  decision 21), a second ART mount for facts, and requiring `forge_facts` in
  the input schema (that would turn a missing fact into a request contract
  error instead of a clear finding).

## Acceptance criteria

- [x] A proof matching the facts passes, with 40- and 64-character commit ids;
  missing or invalid configuration (including a missing facts version or an
  unsupported forge) and missing or malformed facts never pass.
- [x] Each mismatch reports its finding: forge or repository, base branch,
  forge origin, merged, landed commit SHA, each non-success required check,
  and commit binding. Merged without a landed SHA, a landed SHA without merge,
  and merged but open are malformed facts.
- [x] Every `pr_url` not exactly equal to `change_url` and every `ci_run_url`
  that is not a required check's `run_url` fail; a non-GitHub change URL that
  the facts report passes, proving no URL is built.
- [x] Each integrity rule has its own finding and edge-case tests: stale
  approval, approval with null `commit_id`, approval then changes requested or
  dismissed, `bot` and `other` reviewer kinds, author self-approval, reviewer
  write access null or false, a later `changes_requested` whose id sorts lower,
  a non-string review id, each default protected path, rename into or out of
  `.github`, unbound check, producer mismatch, and operator-only approval.
- [x] A GitLab-style subgroup repository path is accepted by the checker and
  the published configuration schema.
- [x] The published v2 body is post-submission only and validates through
  `ExternalCheckerRegistrySpec`, accepting and rejecting configuration and
  input as documented.

## Risk and review routing

- Risk class: L1, it changes acceptance evidence for automatic FinalAcceptance
  once wired.
- Required reviewers: security, QA, documentation.
- Human review focus: the finding set, failing closed everywhere (including
  null facts), strict `success` for required checks, producer binding, and
  `warning` for operator-only approval.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Rules and result contract | `pytest tests/checkers/external/test_harnessy_proof_checker.py` | 219 passed | Agreement with the GitHub provider's neutral facts is proved when chunk 04 adds a cross-module test |
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
  equality; after owner decision 21 the checker builds no URL either and
  compares with the URLs the facts report.
- Security review, time-of-check binding: added the commit-binding finding.
- Security review of the forge-neutral contract (28 October): a contributor's
  second account without write access could count as the independent
  approval. Facts now carry `reviewer_write_access`, and only `true` counts.
- Architecture review of the forge-neutral contract (28 October): the format
  was still GitHub-shaped. Added `forge_origin`, renamed `merge_commit_sha` to
  `landed_commit_sha` with its invariants, made review ids opaque and ordered
  reviews by list position, replaced the GitHub `owner/name` repository grammar,
  and added Forgejo, Gitea, GitLab and Woodpecker CI paths to the protected
  defaults.

## Reconciliation

- Current-source reconciliation: based on WS-GHPROOF-001-01 over `main` after
  PR #674, merged with `main` after PR #677; reworked to the forge-neutral
  contract of owner decision 21.
- Roadmap: the agent-loop entries now state that the checker compares proofs
  with forge facts (GitHub today) and that FinalAcceptance through it also
  waits for facts wiring (chunk 04).
- Next usable boundary: chunk 04 POST wiring.
- Remaining risks: until chunk 04, every evaluation with this checker fails
  with `facts_missing`.
