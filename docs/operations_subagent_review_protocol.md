# Independent Review Protocol

Workstream planning and major system changes receive multiple review perspectives before being treated as ready.

Implementation and specification chunks must run internal reviewer agents before PR review. The PR must include changed internal review evidence in either `docs/internal_reviews/*.md` or `.agent-loop/initiatives/<initiative>/reviews/*-internal-review-evidence.md`, and CI runs `scripts/check_internal_review_evidence.py` to block missing or incomplete evidence.

External review responses are separate artifacts. CodeRabbit, GitHub checks, and human PR review responses belong in `.agent-loop/initiatives/<initiative>/reviews/*-external-review-response.md`; those files do not replace internal reviewer evidence.

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
- worker and reviewer workflow
- checker policy
- revision replay
- payment/reputation consistency
- auditability

The Product/Ops reviewer is first-class. Do not collapse this track into QA or docs when a chunk affects operator, worker, reviewer, revision, payment, reputation, or audit workflows.

### Risk Reviewer

Focus:

- privacy
- copied data risk
- payment disputes
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

No implementation or specification chunk is marked ready, pushed for PR review, or reported complete until required reviewer tracks have run, valid findings are fixed or documented, and every reviewer-agent session is closed.

Codex must not merge a PR unless the user explicitly approves that specific PR for merge.

## Task Readiness Gate

Before a task moves from `SCREENING` to `READY`, run the same review pattern at task scale:

- product/ops pass: task is worth doing and payment policy is clear
- guide pass: task follows the active project guide
- checker pass: required automated checks exist for the task type
- reviewer pass: acceptance criteria are reviewable
- adversarial pass: identify how the task could be gamed, faked, or disputed

The release decision is recorded as a status snapshot, not only discussed in chat.
