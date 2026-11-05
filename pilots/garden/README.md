# Garden engineering drill

This directory defines a small real project drill, not evidence that it has
already passed. The [project guide](guide.md) describes the contributor contract;
the task definitions will be created as native Workstream tasks. Garden's code
and merge/CI evidence stay in GitHub. This version-2 test explicitly requires
zero independent GitHub approvals; omitting the Garden POST setting still
requires one. This is not a general no-review default. No issue-sync integration is required.

The intended sequence is:

1. PM creates the guide with documents and task examples. Upload alone runs no
   inference. PM either explicitly requests assistance or supplies the documented
   provider-free rules input, then reviews requirements and approves separate
   pinned PRE/POST bindings and the project's activation.
2. PM creates a bounded task. Contributor claims it and implements the change.
3. Required trusted CI passes and an authorized Garden maintainer actually merges
   the task-associated PR. This test selects `required_independent_approvals=0`;
   it does not require an independent GitHub review or invent one. An open PR
   still fails the real-merge check.
4. Contributor uploads the root `proof.json` ZIP. Exercise missing/malformed PRE
   input, valid intake, a controlled POST rejection and a real successful proof.
5. Inspect immutable artifact/Submission, retained checker evidence, governed
   acceptance and exact submitter ContributionRecord through public APIs and
   durable workers. Retry the same operation and verify no duplicate effects.

Use a new guide `garden-engineering-drill-2`, newly approved Garden capability
`v2` PRE/POST bindings, and a new task locked to that guide. Previously activated
guides, claimed tasks, image registrations and evidence remain retained under
their original rules. This is a replacement policy version, not another runtime
implementation or a rewrite of the earlier assignment.

[Garden PR #287](https://github.com/Flow-Research/garden/pull/287) must remain open
as the user requested. Preserve its original commit and existing task history.
Do not assert that its head already identifies a newly claimed task: any later
marker update must use the actual new UUID before final checks and any required
review. No accepted work or contribution is established while it remains open.

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

The rules cite the exact SHA-256 of this `guide.md` original; the manager-authored
runtime also cites the rules original itself. This gives the ready proposal
coverage of both uploaded documents. If the guide changes, update those rule
citations to its new digest before creating and uploading a new guide version.
Do not edit retained originals or rely on an empty citation list: reading a
document alone does not establish the required source coverage.

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
[`458833c297382e679a9de3c4539b3c51239aac0d`](https://github.com/Flow-Research/garden/tree/458833c297382e679a9de3c4539b3c51239aac0d)
confirmed the current contribution/development documentation paths. CI covers
PRs into both `dev` and `main`; that does not make `main` the engineering target.
Lock the POST configuration to `base_branch=dev` and explicitly set
`required_independent_approvals=0` for this test. Positive counts require the
corresponding eligible current-head approvals; omission requires one. Shared
Harnessy retains its minimum of one.

At that SHA, README's PostgreSQL troubleshooting paragraph still tells readers
to override only `DATABASE_URL`. `docs/guides/develop/fix-setup-problems.md`
correctly requires both the URL and `compose.dev.yaml` mapping. Compose maps host
`55432` to container `5432`. The README repair therefore remains needed on `dev`;
the pending work is not a completed contribution. The old onboarding page is now
`docs/tutorials/get-started.md`, and maintainer workflow is
`docs/guides/maintain/maintain-garden.md`.

## Initial task candidates

**First drill: fix local PostgreSQL port-conflict instructions.** Recheck the
current `dev` README against `docs/guides/develop/fix-setup-problems.md`; update
README with matching host mapping and `DATABASE_URL` instructions and a link to
that page. Keep container port `5432` distinct from the chosen host port. Preserve
pending PR #287 and leave it open; do not delete database volumes or change
configuration. Use the actual newly claimed task's marker only after that task
exists. Run applicable checks including `pnpm verify:docs`.

**Second drill: document the Garden Workstream contribution handoff.** After the
guide and checker policy are approved, a small contributor page can explain
claim, head trailer, configured GitHub approval count, required CI/merge, proof
ZIP and PRE versus POST feedback. Preserve ordinary GitHub contributions and use
obvious placeholders, never credentials or fabricated accepted work. This is an
optional later task, not a reason to create another PR for the current test.

Recheck current `dev` before creating tasks. If the requested work has already
landed, do not recycle it as a new contribution. Existing assignments keep their
locked rules; a new guide does not relabel their work or evidence.

## Confirmed points policy preparation

The revised drill awards **100 project points per accepted submission**. Before
locking the new task, configure the authorized project-points unit and binding;
Finance must publish the ContributionPolicy with `accepted_submission` set to those
100 points and `completed_review` unpaid. Select that exact published policy
through the existing guide/task binding flow. This is separate Finance policy,
not setup-agent output or a change to the uploaded guide/rules. This preparation
does not establish that the unit, binding or policy is provisioned or deployed.

Verify that passing required checks commits the exact 100-point award, submitter
ContributionRecord and FinalAcceptance atomically. Rejected work must create no
award; exact replay must create no duplicate award or contribution. An earned
project-points award is not cash, a wallet balance or proof of fulfillment.
Garden PR #287 remains open; this policy preparation establishes no acceptance.

## Evidence boundaries

Prepare the [read-only GitHub App](github-app.md) before the hosted POST drill.
Local fixture success does not establish its installation or permissions.

Local fixtures and controlled forge responses can prove negative cases and image
composition. Only a real authorized GitHub PR plus the public Workstream journey
proves the hosted success path. Report these separately, with exact source/image
digests and no credentials or private evidence bodies in this repository.

The new zero-approval guide/image/task sequence remains separate from earlier
hosted setup and claim evidence. PR #287 is referenced as retained open work,
not a passed proof. Record actual new identities and outcomes only after they
exist; source fixtures and controlled facts cannot establish acceptance.
