# Garden engineering — Workstream project guide

## Purpose

Improve the Garden workspace through small, reviewable engineering contributions.
The Workstream task describes the requested change. This guide defines the shared
engineering and submission requirements. Claiming a task starts your assignment.
Keep one accountable Workstream contributor for that assignment, including when
they use an agent to help.

Garden's code lives in `Flow-Research/garden`. Workstream owns the assignment,
locked project rules, immutable submission and contribution outcome. GitHub hosts
the code and its current-head CI evidence, plus review evidence when the locked checker
configuration requires it. A GitHub issue is not required: the Project Manager can create the task directly in Workstream.

## Engineering rules

Start from current `dev`. Read the task, Garden's `CONTRIBUTING.md`,
`.agents/skills/contribute/SKILL.md`, `docs/guides/maintain/maintain-garden.md`,
the relevant source and its existing tests before editing. Keep the change scoped
to the task and preserve existing behavior outside it. Update shared schemas before their consumers. Add meaningful
regression coverage for behavior changes and update affected documentation.
Never commit credentials, private customer data, local resource overlays, build
caches or generated dependency directories. Preserve license and attribution
notices; Garden contributions use its AGPL-3.0-only license.

Use Garden's documented frozen dependency installation and run the checks relevant
to the change. CONTRIBUTING lists `pnpm format`, `pnpm lint`, `pnpm typecheck`,
`pnpm test`, `pnpm build` and `pnpm verify:deploy-config`; documentation changes
also run `pnpm verify:docs`. The full test suite needs Docker for PostgreSQL
Testcontainers. CI also verifies generated design tokens, connector coverage and committed Worker types, and runs a separate
migration check/application job. Do not alter CI or generated files merely to
make this documentation task pass. Connector changes additionally follow the
connector contribution guide and its verification, typecheck and test commands. Task instructions may
require a more focused reproducer, but cannot waive required repository CI.

Security-sensitive changes require the appropriate repository owners. Report
vulnerabilities through Garden's security policy, not in public proof files.
The first drill tasks deliberately avoid auth, secrets, deployment and CI changes.

## Associate your pull request with the task

After claiming the task, copy its actual Workstream task UUID. Before the final
GitHub checks and any required review, put this line in the final trailer block
of the PR's head commit message, separated from the message body by a blank line:

```text
Workstream-Task: <actual lowercase Workstream task UUID>
```

There must be exactly one occurrence of that reserved trailer. Do not put it in
a quote, example, PR description alone, or in the uploaded JSON instead. Changing
the commit message changes the head commit: rerun checks and obtain fresh review
if the locked configuration requires it.

The external Garden checker compares the immutable PR head's marker with the
trusted task ID supplied by Workstream. This establishes the PR's declared task
association; it establishes reviewed association only when reviews are required
and verified. It does not establish that a GitHub username is the
same identity as the Workstream contributor. The submitting contributor remains
accountable for the submission; do not submit another person's work as your own.

## Check the Garden change

Open a focused PR targeting `dev` in `Flow-Research/garden`. Explain what changed,
why it fulfills the task, and the checks performed. Required CI checks must pass
on the final head with their trusted producer. The PR may remain open: Garden
POST verifies the current PR head and does not require a GitHub merge.

For this test drill, the PM explicitly selects
`required_independent_approvals=0` in the Garden POST attachment. No independent
GitHub human review is required by that checker configuration. Omitting the
setting still requires one independent current-head human approval; positive
values keep the corresponding review requirement. The shared Harnessy checker
continues to require at least one and retains its landed-work requirement.
This setting creates no approval or reviewer facts.

Workstream's separate ReviewPolicy remains `human_review_required=false` for the
approved drill. Passing required POST checks invokes the existing authorized
FinalAcceptance operation without a Workstream Review or reviewer contribution.
The default-true Workstream human-review branch remains supported. Neither the
GitHub approval count nor this guide changes that policy automatically.

## Submit one small ZIP

Place one UTF-8 JSON file named `proof.json` directly at the ZIP root, with no
enclosing directory. The first drill needs no source checkout, patch, screenshots,
tokens or test logs in the ZIP. Additional evidence is required only if a later
locked guide and its checker explicitly define it.

```json
{
  "schema": "garden.work.proof.v1",
  "pr_url": "https://github.com/Flow-Research/garden/pull/123",
  "commit_sha": "<full current PR head SHA>",
  "ci_run_url": "https://github.com/Flow-Research/garden/actions/runs/456",
  "ci_conclusion": "success"
}
```

Those example numbers and the SHA placeholder are not usable evidence. Replace
them with the actual PR, its current head commit and successful required CI run.
`commit_sha` must identify the same PR head used for checks and the task
trailer. The schema identifier is Garden's external proof format.

The file must be a JSON object no larger than 64 KiB. For this first drill the
archive contains exactly that one regular file, at most 64 KiB expanded in total
and at most 128 KiB for the entire ZIP including its metadata. The fields above are claims,
not authority. Workstream supplies verified artifact bytes and scoped GitHub
facts to the external checker. The checker compares repository, base branch, PR,
current head, CI run/checks, the configured review requirement and task
association. A client writing `"ci_conclusion": "success"` cannot establish a passing check.

## What PRE and POST mean

Workstream first applies its ZIP safety/custody checks in bounded private scratch.
Garden's external PRE checks the proof file's bounded structure and claim format.
It does not contact GitHub or assert that the PR passed review. Required intake
failure returns actionable feedback without creating a Submission.

After successful intake and verified immutable storage, Workstream creates the
Submission. The external POST checker uses authorized, bounded forge facts to
verify the claims and head-commit task association, including human approvals
only when the locked count is positive. It does not receive GitHub
credentials or unrestricted networking. Missing/contradictory evidence is distinct
from an infrastructure problem retrieving facts. Workstream applies the locked
policy to the result; the checker itself cannot accept a task or pay anyone.

## Source baseline and changes

This is guide `garden-engineering-drill-3`, reconciled against Garden `dev`
commit `458833c297382e679a9de3c4539b3c51239aac0d`: README, CONTRIBUTING,
`docs/tutorials/get-started.md`, `docs/guides/develop/fix-setup-problems.md`,
`docs/guides/maintain/maintain-garden.md`, `.agents/skills/contribute/SKILL.md`,
`compose.dev.yaml`, CI and code ownership rules. Garden's default branch is
`main`; engineering contributions target `dev`. The POST binding therefore uses
`base_branch=dev`. A later promotion to `main` is separate release work.

This version uses current-head proof and the explicit zero-approval test choice;
it requires a new guide, separate PRE/POST approvals with Garden capability `v3`,
and a newly claimed task. Earlier guide/task/image records retain their exact
rules and evidence; do not reinterpret an old assignment under this version.
The PM must reconcile later source changes before activating another version.
