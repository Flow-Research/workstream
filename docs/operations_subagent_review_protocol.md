# Independent Review Protocol

Workstream planning and major system changes receive multiple review perspectives before being treated as ready.

Use internal reviewer agents for high-risk or broad implementation and specification changes. Record material findings in the PR or a durable review note when that context will help later contributors. Internal review improves confidence; it is not a repository authorization system and CI does not require a separate evidence file.

CodeRabbit, GitHub checks, human review, and internal reviewers provide complementary evidence. Material external findings may be summarized in the PR or a durable review note.

The Codex-native reviewer definitions live under `.codex/agents/`. Reusable reviewer workflows live under `.agents/skills/`. Durable initiative plans, chunk contracts, policies, and review logs live under `.agent-loop/`.

The engineering review protocol is separate from Workstream product review. Product review decisions stored by Workstream remain only `accept`, `needs_revision`, and `reject`.

## Review Roles

### Senior Engineering Reviewer

Focus:

- architecture consistency
- code boundaries
- naming clarity
- lifecycle and data-model invariants
- implementation risk

### QA/Test Reviewer

Focus:

- test coverage
- real API and persistence behavior
- stale wording scans
- regression risk
- CI coverage

### Security/Auth Reviewer

Focus:

- auth boundary
- redaction and visibility
- sensitive metadata exposure
- audit integrity
- permission risks

### Product/Ops Reviewer

Focus:

- daily project manager workflow
- contributor and reviewer workflow
- checker policy
- revision replay
- compensation/reputation consistency
- auditability

The Product/Ops reviewer is first-class. Do not collapse this track into QA or
docs when a chunk affects operator, contributor, reviewer, revision,
compensation, reputation, or audit workflows.

### Risk Reviewer

Focus:

- privacy
- copied data risk
- compensation disputes
- reviewer abuse
- fake evidence
- low-quality generated artifacts
- scope creep

## Required Output

Each review produces concise findings:

```text
severity:
file:
finding:
suggested_change:
```

Severity:

- `critical`: must fix before using the plan
- `high`: fix before implementation
- `medium`: fix during iteration
- `low`: note or polish

## Rule

Do not report high-risk work complete while requested reviewers are still running. Address valid findings, close reviewer sessions, and keep the human merge decision explicit.

Codex must not merge a PR unless the user explicitly approves that specific PR for merge.

## Task Readiness Gate

Before a task moves from `SCREENING` to `READY`, run the same review pattern at task scale:

- product/ops pass: task is worth doing and the project has explicit submitter
  and reviewer contribution award rules before assignment/lease creation
- guide pass: task follows the active project guide
- checker pass: required automated checks exist for the task type
- reviewer pass: acceptance criteria are reviewable
- adversarial pass: identify how the task could be gamed, faked, or disputed

The release decision is recorded as a status snapshot, not only discussed in chat.
