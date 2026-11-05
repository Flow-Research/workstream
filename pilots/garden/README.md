# Garden engineering drill

This directory defines a small real project drill, not evidence that it has
already passed. The [project guide](guide.md) describes the contributor contract;
the task definitions will be created as native Workstream tasks. Garden's code
and independent review stay in GitHub. No issue-sync integration is required.

The intended sequence is:

1. PM creates the guide with documents and task examples. Upload alone runs no
   inference. PM either explicitly requests assistance or supplies the documented
   provider-free rules input, then reviews requirements and approves separate
   pinned PRE/POST bindings and the project's activation.
2. PM creates a bounded task. Contributor claims it and implements the change.
3. Garden maintainer reviews and merges the exact task-associated PR with required
   CI. This is a real human action, not something a drill script may fabricate.
4. Contributor uploads the root `proof.json` ZIP. Exercise missing/malformed PRE
   input, valid intake, a controlled POST rejection and a real successful proof.
5. Inspect immutable artifact/Submission, retained checker evidence, governed
   acceptance and exact submitter ContributionRecord through public APIs and
   durable workers. Retry the same operation and verify no duplicate effects.

The external image implementation belongs under
`external_checkers/garden_proof/`. The generic GitHub facts adapter only retrieves
scoped facts; Garden's image interprets the proof and task trailer. Image tags are
not policy identities: registration and approvals must select the published
immutable image digest and matching schemas/capabilities.

Use [guide-request.json](guide-request.json) for guide metadata and its two task
examples. Upload [guide.md](guide.md) and [manager-rules.md](manager-rules.md) as
their declared originals for the provider-free path. The latter is intentionally
the complete JSON rules object in a `text/markdown` original, matching the current
PM-authored input contract; do not wrap it in a Markdown code fence. Then call
the explicit requirements compilation operation. For optional AI assistance,
declare/upload the guide alone and explicitly request setup; the task examples
remain the same. Neither upload invokes a model on its own.

[tasks.json](tasks.json) contains two individual manual-task request bodies.
Submit each through the existing project task API after activation; this array
is a local preparation file, not a new bulk-import API.

After writing the real claims to `proof.json` in a clean working directory,
package just that file:

```sh
python3 -m zipfile -c proof.zip proof.json
python3 -m zipfile -l proof.zip
```

The listed member must be the root `proof.json`. Follow the
[image instructions](../../external_checkers/garden_proof/README.md) for local
qualification and separate PRE/POST configuration; local qualification does not
register or approve a production image.

## Engineering branch and source evidence

Garden's default branch is `main`; its active contribution target is `dev`.
Read-only inspection of `dev` at
[`c61609fc4170ea76238b1fb53b1c00177448dad5`](https://github.com/Flow-Research/garden/tree/c61609fc4170ea76238b1fb53b1c00177448dad5)
found that the maintainer workflow and contribution skill both require starting
from and targeting `dev`. [Merged PR #261](https://github.com/Flow-Research/garden/pull/261)
has base `dev` and landed at that SHA. CI covers PRs into both `dev` and `main`;
that does not make `main` the engineering target. Lock the POST configuration to
`base_branch=dev` and obtain fresh review/checks on the actual task head.

At that SHA, README's PostgreSQL troubleshooting paragraph still tells readers
to override only `DATABASE_URL`; onboarding's matching paragraph requires both
the URL and `compose.dev.yaml` mapping. Compose maps host `55432` to container
`5432`. The first task therefore remains a useful documentation repair on `dev`,
rather than replaying a fix already delivered. This read-only source check does
not establish required-check protection, an eligible review or a completed drill.

## Initial task candidates

**First drill: fix local PostgreSQL port-conflict instructions.** Rechecked on
`dev` at `c61609fc4170ea76238b1fb53b1c00177448dad5`, README still says to override
only `DATABASE_URL` when host port
55432 is occupied. Onboarding correctly requires changing both that URL and the
`compose.dev.yaml` host mapping. Update the README to describe the matching changes,
keep container port 5432 distinct from the chosen host port, and link onboarding.
Do not change deployed configuration or delete existing database volumes.

**Second drill: document the Garden Workstream contribution handoff.** Once the
first guide and checker contract are approved, add a short Garden contributor
page describing claim, task trailer, review/merge, proof ZIP and how to interpret
PRE versus POST feedback. Link it from CONTRIBUTING without replacing ordinary
GitHub contribution instructions. Examples must contain obvious placeholders,
never copied private tokens or a claim that a sample PR is real accepted work.

Both are genuine small documentation contributions. Recheck current Garden `dev`
before creating tasks; if another contributor already fixed the issue, select a
new useful change rather than replaying completed work. Open UI/auth issues are
not automatically part of this drill.

## Evidence boundaries

Prepare the [read-only GitHub App](github-app.md) before the hosted POST drill.
Local fixture success does not establish its installation or permissions.

Local fixtures and controlled forge responses can prove negative cases and image
composition. Only a real authorized GitHub PR plus the public Workstream journey
proves the hosted success path. Report these separately, with exact source/image
digests and no credentials or private evidence bodies in this repository.

No real task IDs, PR numbers, image digests or successful run receipts are asserted
by these preparation documents. Record them after the corresponding real actions.
