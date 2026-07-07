# Loop State

## Current State

- Active initiative: `WS-POL-001` - Submission Artifact Policy Foundation
- Active planning chunk: none
- Active implementation chunk: `WS-POL-001-12`
- Branch: `codex/ws-pol-001-12-project-setup-policy-visibility`
- Status: `WS-POL-001-12` is implemented in PR #76 on branch
  `codex/ws-pol-001-12-project-setup-policy-visibility`. Internal review is
  complete, CodeRabbit feedback is being addressed in a follow-up commit, and
  the chunk is waiting for human merge review after external-review fixes are
  verified.
- Last merged implementation SHA: `0729531`
- Last merge commit: `5cec0e0`
- Current gate: verify CodeRabbit fixes on PR #76, update trust evidence, then
  wait for explicit human merge approval.
- Next chunk: inactive until `WS-POL-001-12` receives human review and merge.

## Operating Rule

Workstream engineering chunks move through:

```text
Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Memory Update -> Stop
```

The merged `WS-POL-001-03` chunk moved task readiness and submission creation
onto the locked project guide-source snapshot, effective project submission
artifact policy, and compiled project `PreSubmitCheckerPolicy` bundle. It did
not implement frontend behavior, payment, reputation, settlement, blockchain
integrations, post-submit policy splitting, or revision resubmission drill
behavior.

The merged `WS-POL-001-08` chunk corrected the project setup orchestration path:
normal guide/source capture starts the pre-submit setup pipeline automatically
through Celery. It did not redesign post-submit policy, review, revision,
payment, reputation, blockchain integrations, frontend behavior, or task
submission runtime.

The merged `WS-POL-001-09` chunk was a corrective hardening chunk for the
project setup runtime boundary. It removed the production fixture adapter and
did not change task, checker, post-submit, review, revision, payment,
reputation, blockchain, frontend, or object-storage behavior.

The merged `WS-POL-001-10` chunk was a corrective hardening chunk for the
pre-submit live API drill. It fixed guide-version conflict mapping,
guide-create source snapshot capture, active-guide checker summary visibility,
worker self-profile onboarding, and failed pre-submit audit evidence. It did
not change post-submit policy, review, revision, payment, reputation,
blockchain, frontend, or agent-runtime behavior.

## Last Review State

- Last completed initiative: `WS-ENG-001` Codex zero-trust engineering loop bootstrap.
- PR #23 merged into `main` on 2026-06-20.
- PR #24 updated post-merge loop memory on `main`.
- PR #25 added Terminal Benchmark example material under `examples/`.
- PR #26 approved and merged WS-POL-001 planning into `main` on 2026-06-27.
- PR #27 updated WS-POL post-merge memory on `main`.
- PR #28 implemented `WS-POL-001-01` and was merged into `main`.
- PR #61 implemented `WS-POL-001-02` and was merged into `main`.
- PR #63 implemented `WS-POL-001-03` from `codex/ws-pol-001-03-task-locked-context` and was merged into `main` on 2026-07-03.
- Internal review evidence for `WS-POL-001-03` is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-03-internal-review-evidence.md`.
- PR trust bundle for `WS-POL-001-03` is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-03-pr-trust-bundle.md`.
- External review response for `WS-POL-001-03` is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-03-external-review-response.md`.
- `WS-POL-001-04` started on branch `codex/ws-pol-001-04-post-submit-policy` after the user's explicit start signal.
- `WS-POL-001-04` internal reviewer fanout completed with no open sub-agent sessions.
- `WS-POL-001-04` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-04-internal-review-evidence.md`.
- `WS-POL-001-04` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-04-pr-trust-bundle.md`.
- `WS-POL-001-04` external review response is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-04-external-review-response.md`.
- `WS-POL-001-04` merged to `main` before `WS-POL-001-05` started.
- `WS-POL-001-05` started on branch `codex/ws-pol-001-05-revision-resubmission` after the user's explicit start signal.
- `WS-POL-001-05` reviewed implementation SHA: `5019afc57e7c6f5f7488f26a05b11c65a33e9f18`.
- `WS-POL-001-05` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-internal-review-evidence.md`.
- `WS-POL-001-05` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-pr-trust-bundle.md`.
- `WS-POL-001-05` external review response is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-external-review-response.md`.
- PR #66 merged into `main` as `b20988ba79626e1edbc03953aba60f54f2fc94ab`.
- `WS-POL-001-06` started on branch `codex/ws-pol-001-06-terminal-benchmark-drill`
  after the user's explicit start signal.
- `WS-POL-001-06` real Terminal Benchmark manual HTTP drill passed against a
  local Termius reviewer fixture; committed evidence uses placeholder fixture
  paths and local IDs only.
- `WS-POL-001-06` live drill exposed and fixed an OpenAI Agents SDK adapter
  strict-schema issue for the policy derivation result's open `policy_body`.
- `WS-POL-001-06` follow-up cleanup removed stale project-owned payment fields
  and removed construction-state guide checklist fields, preserved server-written activation
  provenance on reads, added fail-closed migration behavior for old
  guide-source snapshots, and aligned active docs around `PaymentPolicy` as the
  payment-term authority.
- `WS-POL-001-06` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-internal-review-evidence.md`.
- `WS-POL-001-06` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-pr-trust-bundle.md`.
- PR #67 merged into `main` as `3cce92c`.
- `WS-POL-001-07` started on branch `codex/ws-pol-001-07-task-contract-cleanup`
  after the user's explicit start signal.
- PR #68 merged into `main` as `3dc6a95`.
- `WS-POL-001-08` started on branch `codex/ws-pol-001-08-celery-project-setup`
  after the user's explicit correction that project setup must run
  automatically from guide/source capture through Celery.
- `WS-POL-001-08` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-internal-review-evidence.md`.
- `WS-POL-001-08` external review response is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-external-review-response.md`.
- `WS-POL-001-08` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-pr-trust-bundle.md`.
- PR #69 merged into `main` as `aea7024`.
- `WS-POL-001-09` started on branch `codex/ws-pol-001-09-openai-agent-sdk-only`
  after the user's explicit correction to remove the production fixture runtime.
- `WS-POL-001-09` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-internal-review-evidence.md`.
- `WS-POL-001-09` external review response is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-external-review-response.md`.
- `WS-POL-001-09` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-pr-trust-bundle.md`.
- PR #71 merged into `main` as `8a524de`.
- `WS-POL-001-10` started after the user's explicit start signal for the first
  five pre-submit hardening fixes from the live API drill.
- PR #72 merged into `main` as `1bbde47`.
- `WS-POL-001-11` merged through PR #74 as `5cec0e0`; it added local
  Workstream actor identity and actor profile registries for verified Flow
  actors before the next Terminal Benchmark live API drill.
- `WS-POL-001-11` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-11-internal-review-evidence.md`.
- `WS-POL-001-11` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-11-pr-trust-bundle.md`.
