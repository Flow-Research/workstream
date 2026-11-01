# WS-GHPROOF-001 — Forge proof facts for the Harnessy proof checker

- Disposition: Planned
- Intent: make a faked Harnessy `proof.json` fail post-submission work
  evaluation. WorkStream reads the change (pull or merge request), merge and
  required-check facts from the forge (the git host) with a read-only
  credential, outside the checker sandbox, and the networkless
  `harnessy.work_proof` checker compares the proof with those facts.
- Current change: [WS-GHPROOF-001-04](WS-GHPROOF-001-04.md) makes the facts
  capability forge-neutral and wires it into POST evaluation.
- Product behavior changed: Yes, for POST bindings that select forge facts.
- Integrity: see [Integrity requirements](#integrity-requirements); every layer
  fails closed.

The initiative ID keeps its original name; its scope is forge-neutral.

## Problem

`external_checkers/harnessy_proof/checker.py` used to check only the shape of
the claims in `proof.json`. It runs with `--network none`
(`external_checkers/workstream-checker-service`), so it cannot confirm any
claim itself. A hand-written proof passed. With `human_review_required=false`,
that proof reaches automatic FinalAcceptance. This is acceptable only while one
operator builds every proof from `gh` and `git`; it must close before points
carry money or other operators' agents submit.

Opening the checker network is rejected: no-network execution is a guarantee
the checker service owns for every project, and a forge credential must never
enter a container that runs submitted material.

## Design

1. The locked checker binding `configuration` selects forge facts and names
   the forge, its instance origin, the repository and the base branch, for
   example `{"workstream_forge_facts_version": "v1", "forge": "github",
   "forge_origin": "https://github.com", "repository":
   "Flow-Research/harnessy-v2", "base_branch": "dev"}`.
   The registry `configuration_schema` must declare the selection key. It is
   not a project setting.
2. A typed `ForgeFactsAdapter` port (ADR 0014, capability `forge_facts`, one
   provider per forge, provider key = forge name) reads, for one change: state,
   merged flag, landed commit, base branch and head commit; author; reviews
   (oldest first, with each head-commit approver's write access);
   changed files; and each required check of the base branch with the results
   judged for the head commit and who produced them. It returns one immutable
   `workstream.forge_change_facts.v1` value with the fetch time and the SHA-256
   of every forge response body read. GitHub, read as a GitHub App, is the only
   provider.
3. "CI passed" means every check required by the base branch's protection has
   conclusion `success` for the change's head commit, resting on at least one
   judged result.
4. The facts reach the checker in the request `input` under `forge_facts`, so
   the request digest binds them. They are not a second ART mount.
5. `harnessy.work_proof` has one fail-closed mode. Its configuration must
   select facts and name the forge, instance origin, repository and base
   branch, and facts must
   be present; otherwise it fails. It reports one error finding for each
   mismatch. It builds no URL: `pr_url` must equal the facts' `change_url`,
   and `ci_run_url` must equal a required check's `run_url`.
6. One canonical change identity: chunk 04 takes the change number from the
   provider's own `parse_change_url`, reads only the configured instance and
   repository, and the checker re-asserts exact equality of the claimed URL
   and instance origin with the facts. Every fact is bound to one change state
   (`head_sha`, `landed_commit_sha`).

## Forge neutrality (owner decision 21, 28 October 2026)

Git work will not always run through GitHub; GitLab, Forgejo or another forge
may follow. The capability, facts, configuration and checker use forge-neutral
names now, before anything ships, so nothing needs migrating. Only the GitHub
provider is built. Facts name the forge instance (`forge_origin`), so GitHub
Enterprise or a self-hosted GitLab or Forgejo is distinct from the public
host; repository paths may have more than two segments (GitLab subgroups);
review and producer ids are opaque. Each provider reports only what its forge
can prove: a fact it cannot prove is null (a review without a commit, a result
without a producer, a reviewer's write access), and the checker fails closed
on it, so the integrity layers below
hold on every forge. Provider-specific settings (the GitHub App id, key and
time limits) keep provider names. Harnessy's proof format is unchanged here;
a forge-neutral proof is Harnessy's follow-up.

## Chunk map

| Chunk | Outcome | Depends on |
|---|---|---|
| 01 | This initiative record | None |
| 02 | Facts port and GitHub App adapter (integrity layer 1 facts), registered per ADR 0014 and not yet called by a production path | 01 |
| 03 | `harnessy.work_proof` comparison mode and integrity layers 2 to 5, configuration schema and checker version, on forge-neutral facts | 01 |
| 04 | Forge-neutral port (replacing chunk 02's GitHub-named port), selected POST wiring inside the existing outbox evaluation handler for bindings that select forge facts, facts-unavailable as infrastructure failure, an absolute time limit on the read | 02, 03, PR #677 |
| 05 | Durable ART custody of the facts as a `service_identity` checker-run binding; integrity layer 8 | 04, PRs #676 and #677 |
| 06 | Hosted secret configuration and an end-to-end drill against a fake forge, covering every integrity layer | 04, 05 |
| 07 | Lifecycle: route protected-path changes to explicit human acceptance instead of failing them; integrity layers 6 and 7 | 04 |

Chunks 02 and 03 are independent of each other. Each chunk is one pull request
with one change record. Until chunk 07, a protected-path change fails its check
rather than waiting for human acceptance: it still cannot be auto-accepted.

## Integrity requirements

Owner decision of 24 October 2026 (tracker decision 20): verification integrity
is non-negotiable and is Flow's key selling point. Every layer fails closed and
trusts nothing the contributor could produce. Missing facts never pass.

| Layer | Requirement | Chunk |
|---|---|---|
| 1 | Facts come only from the forge through WorkStream's read-only credential, never from the submission. The reader stays factual: it reports the change, its author, all reviews, all changed files, and each required check with the producer of each judged result. It makes no policy decision. If the forge reports more changed files than it can list, the read fails as incomplete. | 02, 04 |
| 2 | Every required check must be bound to a producer, and every judged result must come from it. A requirement that accepts any source is an error unless the locked configuration explicitly allows it. | 03 |
| 3 | A change to CI or repository configuration (`.github/**`, `.gitlab/**`, `.gitlab-ci.yml`, `.forgejo/**`, `.gitea/**`, `.woodpecker/**`, `.woodpecker.yml`, `.woodpecker.yaml`, `**/CODEOWNERS`, `.circleci/**`, plus configured paths; renames count on both names) cannot be auto-accepted and requires explicit human acceptance. | 03, routing in 07 |
| 4 | At least one independent approval on the final head commit: an `approved` latest decisive review (by list position) by a reviewer of kind `user` whom the forge proves has write access and who is not the author. A later `changes_requested` or `dismissed` review by the same reviewer cancels the approval; an approval of an earlier commit, or one the forge cannot bind to a commit, does not count. | 03 |
| 5 | Approval only by configured operator logins is reported as a non-blocking finding: the work may earn points but may not be paid in money until an independent reviewer confirms it. | 03 |
| 6 | A claim that contradicts the forge is "suspected misreporting", distinct from a failed check. After one flag (configurable) the contributor account is paused from claiming, and administrators are alerted. | 07 |
| 7 | A failed check gives a clear reason and may be resubmitted without penalty. An administrator override is recorded as a human override, never as a pass. | 07 |
| 8 | Certificates and contribution evidence carry the SHA-256 of the facts they relied on. | 05 and contribution evidence work |

Deferred GitHub-side hardening (Julian, 24 October 2026): code-owner review for
`.github/`, dismissing stale approvals on new pushes, and requiring approval of
the last push are not yet enabled on the Flow repositories. Layers 3 and 4
compensate for them in WorkStream. Today all 22 required checks of
`Flow-Research/harnessy-v2` branch `dev` are bound to the GitHub Actions App
(id 15368), and the agents' App lacks the `workflows` permission, so agents
cannot edit workflow files directly.

## Owner decisions (2026-10-24)

The project owner agreed these refinements to the step-9 design on 24 October
2026. They replace that design where they differ; decision 21 (above) renamed
them to forge-neutral terms:

- The fetch runs inside the existing outbox evaluation handler path
  (`SelectedPostSubmitProcessor` in
  `backend/app/modules/checkers/selected_post_submit_execution.py`), only for
  checkers whose locked binding configuration selects forge facts. No new
  pre-evaluation job or state is added.
- The forge, repository and base branch are named in the checker binding's
  locked `configuration`, not by a project setting.
- "CI passed" uses the base branch's required checks. For GitHub these are the
  classic branch-protection contexts and checks; check runs and commit
  statuses both count.
- Facts reach the checker in the request `input`, bound by its digest. Durable
  ART custody as a `service_identity` checker-run binding is a later chunk.
- When the forge is unavailable, the provider retries a bounded number of times
  within an absolute time limit that the selected POST budget reserves, then
  raises a typed facts-unavailable error. Missing facts never pass. Chunk 04
  maps the error to an infrastructure failure so that an Operator retry can
  follow.
- Forge credentials never appear in logs, exceptions, representations, facts,
  checker input or submissions.

## Security notes

- The GitHub App is read-only. Pull requests, checks, commit statuses and
  metadata need read access. Reading classic branch protection needs the
  repository administration read permission. The App also reads approving
  reviewers' repository permission; chunk 06 confirms the minimum permission
  set, including that read, before hosted use.
- Installation tokens are requested per repository and cached in process until
  shortly before expiry. Only response bodies of facts requests are hashed;
  token responses are never hashed or stored.
- The adapter follows pagination links only to the configured API origin, so a
  response cannot redirect the credential to another host.
- WorkStream reads facts only for the repository the locked configuration
  names; a claim naming another repository yields no facts and fails.
- The checker stays networkless and credential-free. It receives facts only.

## Non-goals

- No checker network access, forge webhooks, repository rulesets, project
  repository settings, or human-review replacement.
- No forge provider other than GitHub until one is needed (ADR 0014 adds it as
  one more registered provider).
- No confirmation of who wrote the code. The check confirms that the paid work
  was merged into the agreed repository with its required checks passing.
- No change to Harnessy's proof format.

## Remaining risk

Until chunk 06 configures hosted credentials, only a stack with GitHub App
settings reads facts; without them, a binding that selects forge facts fails
as an infrastructure error and never passes. Until chunk 07, protected-path
changes fail rather than wait for human acceptance.
