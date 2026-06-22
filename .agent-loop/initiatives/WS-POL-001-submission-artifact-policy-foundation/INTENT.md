# INTENT: WS-POL-001 - Submission Artifact Policy Foundation

## Problem Being Solved

Workstream currently understands the product direction for submission intake, but
the backend still carries transitional fields such as `evidence_policy`,
`required_files`, `required_evidence`, and broad checker-policy version locking.

That is not strong enough for the system we are building. A project guide is
human-facing instruction. It can explain expectations, examples, rubric, and
quality bar, but it must not be the only source of truth for what a worker is
allowed to submit.

Submission intake needs a deterministic machine contract.

## Human-Level Goal

Make submission intake policy-driven:

```text
ProjectGuide = human-facing instructions
SubmissionArtifactPolicy = machine-readable intake contract

WorkstreamDefaultSubmissionArtifactPolicy
+ ProjectSubmissionArtifactPolicy
= EffectiveSubmissionArtifactPolicy

EffectiveSubmissionArtifactPolicy
-> generated PreSubmitCheckerPolicy
```

Workers submit draft packet fields. Workstream decides required artifacts,
evidence, hashes, storage reference rules, forbidden artifacts, and blocking
pre-submit feedback from the effective policy.

## Why Now

Week 1 and Week 2 established the core backend loop:

- project and guide foundation
- task queue and assignment
- submission packet foundation
- checker contracts and runner registry
- pre-review gate
- checker trial and real API drills

The next correctness gap is policy ownership. If we keep relying on task fields
and guide prose, different projects will drift and the pre-submit/post-submit
boundary will become confusing.

## Success State

After this initiative:

- `SubmissionArtifactPolicy` is a first-class backend object.
- Workstream default submission artifact rules are defined in code.
- Project submission artifact policy cannot weaken Workstream defaults.
- Effective submission artifact policy is computed deterministically.
- Generated pre-submit checker policy is derived from effective policy.
- Submission creation uses the generated pre-submit policy before a submission
  row is created.
- Post-submit/internal checker policy remains separate.
- Revision resubmission can run pre-submit feedback again without creating
  confusing internal worker states.

## Non-Goals

- No human review decision implementation.
- No payment, contribution, reputation, blockchain, x402, ERC-8004, or ERC-8183
  work.
- No frontend implementation.
- No object-storage implementation beyond preserving the storage abstraction
  boundary.
- No durable external checker worker infrastructure.
- No direct use of Terminal Benchmark example code in product runtime.

## Business/Product/Engineering Context

Workstream must be fair to workers and reliable for project managers. If a
submission requirement matters, it belongs in the approved guide and policy
context, not in Slack messages, hidden docs, or agent memory.

The worker should get deterministic pre-submit feedback before a submission is
created. Internal checker routing can be richer, but worker-facing outcomes stay
simple. Stored review decision values remain exactly `accept`,
`needs_revision`, and `reject`; display labels may render those as accepted,
needs revision, and rejected where appropriate.

## Human Judgment Required

- Approve the chunk sequence before implementation.
- Approve the exact Workstream default submission artifact rules.
- Approve naming for new persisted fields and policy version/hash fields.
- Approve any migration strategy that changes existing transitional fields.

## Initial Risk Class

L1 - policy engine, task lifecycle, audit, and submission data boundaries.
