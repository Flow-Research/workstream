# WS-GHPROOF-001 — GitHub proof facts for the Harnessy proof checker

- Disposition: Planned
- Intent: make a faked Harnessy `proof.json` fail post-submission work
  evaluation. WorkStream reads the pull request, merge and required-check facts
  from GitHub with a read-only GitHub App, outside the checker sandbox, and the
  networkless `harnessy.work_proof` checker compares the proof with those facts.
- Current change: [WS-GHPROOF-001-01](WS-GHPROOF-001-01.md) records the plan.
- Product behavior changed: No
- Integrity: see [Integrity requirements](#integrity-requirements); every layer
  fails closed.

## Problem

`external_checkers/harnessy_proof/checker.py` checks only the shape of the
claims in `proof.json`: a 40-character commit SHA, `https://github.com/` URLs,
`ci_conclusion: "success"` and `merged: true`. It runs with `--network none`
(`external_checkers/workstream-checker-service`), so it cannot confirm any claim.
A hand-written proof passes. With `human_review_required=false`, that proof
reaches automatic FinalAcceptance. This is acceptable only while one operator
builds every proof from `gh` and `git`; it must close before points carry money
or other operators' agents submit.

Opening the checker network is rejected: no-network execution is a guarantee
the checker service owns for every project, and a GitHub credential must never
enter a container that runs submitted material.

## Design

1. The locked checker binding `configuration` names the GitHub repository and
   base branch, for example
   `{"github_repository": "Flow-Research/harnessy-v2", "base_branch": "main"}`.
   The registry `configuration_schema` validates it. It is not a project setting.
2. A typed `GitHubFactsAdapter` port (ADR 0014) authenticates as a GitHub App
   installation and reads, for one pull request: state, `merged`,
   `merge_commit_sha`, base branch and head SHA; the classic branch-protection
   required status checks of that base branch; and the check runs and commit
   statuses of the head SHA. It returns one immutable `workstream.github_facts.v1`
   value with the fetch time and the SHA-256 of every GitHub response body read.
3. "CI passed" means every check required by the base branch's protection has
   conclusion `success` for the pull request's head SHA. Check runs and commit
   statuses both count.
4. The facts reach the checker in the request `input` (stdin), so the request
   digest binds them. They are not a second ART mount.
5. `harnessy.work_proof` has one fail-closed mode. Its configuration must name
   the repository and base branch, and facts must be present; otherwise it
   fails. It reports one error finding for each mismatch: repository, base
   branch, merged flag, merge commit SHA, each required check that is missing or
   not `success`, and the integrity rules below. It parses no URL: `pr_url` and
   `ci_run_url` must equal canonical URLs built from the facts.
6. One canonical pull-request identity: chunk 04 takes the pull-request number
   from the single shared parser `parse_pull_request_url` (chunk 02), and the
   checker re-asserts exact equality of the claimed URL with the facts, so the
   fetcher and the checker cannot disagree. Every fact is bound to one
   pull-request state (`head_sha`, `merge_commit_sha`).

## Chunk map

| Chunk | Outcome | Depends on |
|---|---|---|
| 01 | This initiative record | None |
| 02 | GitHub facts port and GitHub App adapter (integrity layer 1 facts: pull request, author, reviews, changed files, required checks with their producing App), registered per ADR 0014 and not yet called by a production path | 01 |
| 03 | `harnessy.work_proof` comparison mode and integrity layers 2 to 5, configuration schema and checker version | 01 |
| 04 | Selected POST wiring: fetch facts inside the existing outbox evaluation handler for bindings whose locked configuration selects GitHub facts, taking the pull-request number only from `parse_pull_request_url`; map facts-unavailable to an infrastructure failure; route protected-path changes to human acceptance; integrity layers 6 and 7 | 02, 03, PR #677 |
| 05 | Durable ART custody of the facts as a `service_identity` checker-run binding; integrity layer 8 | 04, PRs #676 and #677 |
| 06 | Hosted secret configuration and an end-to-end drill against a fake GitHub, covering every integrity layer | 04, 05 |

Chunks 02 and 03 are independent of each other. Each chunk is one pull request
with one change record.

## Integrity requirements

Owner decision of 24 October 2026 (tracker decision 20): verification integrity
is non-negotiable and is Flow's key selling point. Every layer fails closed and
trusts nothing the contributor could produce. Missing facts never pass.

| Layer | Requirement | Chunk |
|---|---|---|
| 1 | Facts come only from GitHub through WorkStream's read-only App, never from the submission. The reader stays factual: it reports the pull request, its author, all reviews, all changed files, and each required check with the App that produced the judged result. It makes no policy decision. If GitHub reports more changed files than it can list, the read fails as incomplete. | 02 |
| 2 | Every required check must be bound to a producing App. A requirement that accepts any source (including commit statuses, which carry no App identity) is an error unless the locked configuration explicitly allows it. | 03 |
| 3 | A change to CI or repository configuration (`.github/**`, `**/CODEOWNERS`, `.gitlab-ci.yml`, `.circleci/**`, plus configured paths; renames count on both names) cannot be auto-accepted and requires explicit human acceptance. | 03, routing in 04 |
| 4 | At least one independent approval on the final head commit: an `APPROVED` latest review by a reviewer who is neither the author nor a Bot. A later `CHANGES_REQUESTED` or `DISMISSED` review by the same reviewer cancels the approval; an approval of an earlier commit does not count. | 03 |
| 5 | Approval only by configured operator logins is reported as a non-blocking finding: the work may earn points but may not be paid in money until an independent reviewer confirms it. | 03 |
| 6 | A claim that contradicts GitHub is "suspected misreporting", distinct from a failed check. After one flag (configurable) the contributor account is paused from claiming, and administrators are alerted. | 04 and lifecycle work |
| 7 | A failed check gives a clear reason and may be resubmitted without penalty. An administrator override is recorded as a human override, never as a pass. | 04 and lifecycle work |
| 8 | Certificates and contribution evidence carry the SHA-256 of the facts they relied on. | 05 and contribution evidence work |

Deferred GitHub-side hardening (Julian, 24 October 2026): code-owner review for
`.github/`, dismissing stale approvals on new pushes, and requiring approval of
the last push are not yet enabled on the Flow repositories. Layers 3 and 4
compensate for them in WorkStream. Today all 22 required checks of
`Flow-Research/harnessy-v2` branch `dev` are bound to the GitHub Actions App
(id 15368), and the agents' App lacks the `workflows` permission, so agents
cannot edit workflow files directly.

## Owner decisions (2026-10-24)

The project owner agreed these refinements to the
step-9 design on 24 October 2026. They replace that design where they differ:

- The fetch runs inside the existing outbox evaluation handler path
  (`SelectedPostSubmitProcessor` in
  `backend/app/modules/checkers/selected_post_submit_execution.py`), only for
  checkers whose locked binding configuration selects GitHub facts. No new
  pre-evaluation job or state is added. Chunk 04 builds on PR #677's
  `workstream_evaluation_context_roles`.
- The repository and base branch are named in the checker binding's locked
  `configuration` and validated by the registry `configuration_schema`, not by
  a project setting.
- "CI passed" uses the classic branch-protection required checks (contexts and
  checks) of the base branch. Check runs and commit statuses both count.
- Facts reach the checker in the request `input`, bound by its digest. Durable
  ART custody as a `service_identity` checker-run binding is a later chunk.
- When GitHub is unavailable, the adapter retries a bounded number of times
  within the selected POST handler time budget
  (`SELECTED_POST_HANDLER_TIMEOUT_SECONDS`), then raises a typed
  facts-unavailable error. Missing facts never pass. Chunk 04 maps the error to
  an infrastructure failure so that an Operator retry can follow.
- The GitHub App private key and installation token never appear in logs,
  exceptions, representations, facts, checker input or submissions.

## Security notes

- The GitHub App is read-only. Pull requests, checks, commit statuses and
  metadata need read access. Reading classic branch protection needs the
  repository administration read permission; chunk 06 confirms the minimum
  permission set before hosted use.
- Installation tokens are requested per repository and cached in process until
  shortly before expiry. Only response bodies of facts requests are hashed;
  token responses are never hashed or stored.
- The adapter follows pagination links only to the configured API origin, so a
  response cannot redirect the credential to another host.
- The checker stays networkless and credential-free. It receives facts only.

## Non-goals

- No checker network access, GitHub webhooks, repository rulesets, project
  repository settings, or human-review replacement.
- No confirmation of who wrote the code. The check confirms that the paid work
  was merged into the agreed repository with its required checks passing.
- No change to Harnessy's proof format.

## Remaining risk

Until chunk 04 merges, no production path fetches facts, and the local agent
loop keeps its shape-only trust limit.
