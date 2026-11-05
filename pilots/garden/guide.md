# Garden engineering — Workstream project guide

## Purpose

Improve the Garden workspace through small, reviewable engineering contributions.
The Workstream task describes the requested change. This guide defines the shared
engineering and submission requirements. Claiming a task starts your assignment.
Keep one accountable Workstream contributor for that assignment, including when
they use an agent to help.

Garden's code lives in `Flow-Research/garden`. Workstream owns the assignment,
locked project rules, immutable submission and contribution outcome. GitHub hosts
the code and its independent review/CI evidence. A GitHub issue is not required:
the Project Manager can create the task directly in Workstream.

## Engineering rules

Start from current `dev`. Read the task, Garden's `CONTRIBUTING.md`,
`.agents/skills/contribute/SKILL.md`, `docs/development/maintainer-workflow.md`,
the relevant source and its existing tests before editing. Keep the change scoped to the task and preserve existing
behavior outside it. Update shared schemas before their consumers. Add meaningful
regression coverage for behavior changes and update affected documentation.
Never commit credentials, private customer data, local resource overlays, build
caches or generated dependency directories. Preserve license and attribution
notices; Garden contributions use its AGPL-3.0-only license.

Use Garden's documented frozen dependency installation and run the checks relevant
to the change. CONTRIBUTING lists `pnpm format`, `pnpm lint`, `pnpm typecheck`,
`pnpm test`, `pnpm build` and `pnpm verify:deploy-config`; the full test suite
needs Docker for PostgreSQL Testcontainers. CI also verifies generated design
tokens, connector coverage and committed Worker types, and runs a separate
migration check/application job. Do not alter CI or generated files merely to
make this documentation task pass. Connector changes additionally follow the connector contribution
guide and its verification, typecheck and test commands. Task instructions may
require a more focused reproducer, but cannot waive required repository CI.

Security-sensitive changes require the appropriate repository owners. Report
vulnerabilities through Garden's security policy, not in public proof files.
The first drill tasks deliberately avoid auth, secrets, deployment and CI changes.

## Associate your pull request with the task

After claiming the task, copy its actual Workstream task UUID. Before the final
GitHub checks and review, put this line in the final trailer block of the PR's
head commit message, separated from the message body by a blank line:

```text
Workstream-Task: <actual lowercase Workstream task UUID>
```

There must be exactly one occurrence of that reserved trailer. Do not put it in
a quote, example, PR description alone, or in the uploaded JSON instead. Changing
the commit message changes the head commit: rerun checks and obtain fresh review.

The external Garden checker compares the immutable reviewed head's marker with
the trusted task ID supplied by Workstream. This establishes the PR's declared,
reviewed task association. It does not establish that a GitHub username is the
same identity as the Workstream contributor. The submitting contributor remains
accountable for the submission; do not submit another person's work as your own.

## Review and merge the Garden change

Open a focused PR targeting `dev` in `Flow-Research/garden`. Explain what changed,
why it fulfills the task, and the checks performed. Obtain independent current-head
human approval with the repository authority required by the checker and Garden's
own rules. Required CI checks must pass on that head with their trusted producer.
Resolve the repository's review requirements and have an authorized maintainer
merge the PR. Workstream does not grant permission to merge Garden code.

For this project, that GitHub review supplies substantive engineering review.
The pilot can therefore use `human_review_required=false` in Workstream after
the PM approves that policy: successful required POST evidence then invokes
Workstream's shared authorized acceptance. It does not fabricate a Workstream
Review or reviewer contribution. The default human-review-required branch remains
available; this guide does not change that default by itself.

## Submit one small ZIP

Place one UTF-8 JSON file named `proof.json` directly at the ZIP root, with no
enclosing directory. The first drill needs no source checkout, patch, screenshots,
tokens or test logs in the ZIP. Additional evidence is required only if a later
locked guide and its checker explicitly define it.

```json
{
  "schema": "harnessy.work.proof.v1",
  "pr_url": "https://github.com/Flow-Research/garden/pull/123",
  "commit_sha": "<full landed commit SHA>",
  "ci_run_url": "https://github.com/Flow-Research/garden/actions/runs/456",
  "ci_conclusion": "success",
  "merged": true
}
```

Those example numbers and the SHA placeholder are not usable evidence. Replace
them with the actual merged PR, landed commit and successful required CI run.
`commit_sha` identifies the landed merge/squash/rebase result; the reviewed PR
head used for checks and the task trailer can be a different SHA. The schema
identifier is the existing external proof format, not an internal agent version.

The file must be a JSON object no larger than 64 KiB. For this first drill the
archive contains exactly that one regular file, at most 64 KiB expanded in total
and at most 128 KiB for the entire ZIP including its metadata. The fields above are claims,
not authority. Workstream supplies verified artifact bytes and scoped GitHub
facts to the external checker. The checker compares repository, base branch, PR,
landed commit, CI run/checks, independent review and task association. A client
writing `"merged": true` or `"ci_conclusion": "success"` cannot establish either.

## What PRE and POST mean

Workstream first applies its ZIP safety/custody checks in bounded private scratch.
Garden's external PRE checks the proof file's bounded structure and claim format.
It does not contact GitHub or assert that the PR passed review. Required intake
failure returns actionable feedback without creating a Submission.

After successful intake and verified immutable storage, Workstream creates the
Submission. The external POST checker uses authorized, bounded forge facts to
verify the claims and reviewed task association. It does not receive GitHub
credentials or unrestricted networking. Missing/contradictory evidence is distinct
from an infrastructure problem retrieving facts. Workstream applies the locked
policy to the result; the checker itself cannot accept a task or pay anyone.

## Source baseline and changes

This guide was reconciled against Garden `dev` commit
`c61609fc4170ea76238b1fb53b1c00177448dad5`: README, CONTRIBUTING,
`docs/development/onboarding.md`, `docs/development/maintainer-workflow.md`,
`.agents/skills/contribute/SKILL.md`, `compose.dev.yaml`, the CI workflow and
code ownership rules. This replaces the original `main` preparation baseline
`6526cfdbcaf4e1cf4fe58120896243eb82e6f614`. Garden's default branch is `main`,
but its contribution workflow targets `dev`; merged PR #261 confirms that path.
The locked POST binding must therefore use `base_branch=dev`, not the default
branch. A later promotion from `dev` to `main` is separate Garden release work.
The PM must reconcile later repository changes before activating
a new guide version. Existing claimed tasks keep their locked Workstream policies;
do not silently change their requirements because a repository document changed.
