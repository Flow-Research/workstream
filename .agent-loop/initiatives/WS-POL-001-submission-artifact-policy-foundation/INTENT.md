# INTENT: WS-POL-001 - Submission Artifact Policy Foundation

## Problem Being Solved

Workstream currently understands the product direction for submission intake,
but the backend still carries transitional fields such as `evidence_policy`,
`required_files`, `required_evidence`, and broad checker-policy version locking.
Those fields are old v0.1 construction state. They will be replaced, not kept
as compatibility aliases.

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

Project owner material
-> ProjectGuideSufficiencyAgent
-> SubmissionArtifactPolicyDerivationAgent
-> Workstream-derived ProjectSubmissionArtifactPolicy
-> approval by admin or project_manager

WorkstreamDefaultSubmissionArtifactPolicy
+ ProjectSubmissionArtifactPolicy
= EffectiveSubmissionArtifactPolicy

EffectiveSubmissionArtifactPolicy
-> persisted and locked PreSubmitCheckerPolicy
```

Project owners provide open-ended project material: markdown, URLs, full
documentation, examples, rubrics, repository docs, task instructions, domain
requirements, business terms, base payout or payment policy inputs, or any
other project-specific source material. Workstream must not force every project
into one fixed intake checklist. A project guide can be a URL to a complete
documentation set if that is the right form for the project.

All project-owner material is untrusted input. Guide text, imported docs, URLs,
repository docs, and examples cannot grant tool authority, override Workstream
policy, weaken default checks, or instruct internal agents to ignore their
system rules. Source references must be sanitized before persistence and fetched
only through approved adapters or allowlisted retrieval paths.

Workstream runs asynchronous internal analysis on that material. The
`ProjectGuideSufficiencyAgent` checks whether the guide is sufficient for
submitters, reviewers, and Workstream quality control. Blocking guide gaps stop
activation and create clarification requests back to the project owner. Warnings
remain visible to the Workstream `admin` or `project_manager` and must be
acknowledged before activation.

After sufficiency passes, the `SubmissionArtifactPolicyDerivationAgent` derives
the machine-readable project submission artifact policy. The project owner does
not approve this internal policy. A Workstream actor with the `admin` or
`project_manager` role approves the derived policy and activates the
guide-policy bundle. Workers submit draft packet fields. Workstream decides
required artifacts, evidence, hashes, storage reference rules, forbidden
artifacts, and blocking pre-submit feedback from the locked effective policy.

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
- `SubmissionArtifactPolicy` is Workstream-derived from project material and
  approved by `admin` or `project_manager`, not authored directly by the
  project owner.
- `GuideSufficiencyReport` is a first-class record tied to a project guide
  version.
- Workstream default submission artifact rules are defined in code.
- Project submission artifact policy cannot weaken Workstream defaults.
- Effective submission artifact policy is computed deterministically.
- Generated pre-submit checker policy is persisted and locked to the project
  guide version.
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

Pre-submit feedback is not review. A blocking pre-submit result is presented as
`pre_submission_checker_failed` with structured pass/fail/warning details. It
does not create a submission and must not use review decision values.

## Human Judgment Required

- Approve the chunk sequence before implementation.
- Confirm guide sufficiency severity names and report fields.
- Confirm persisted policy provenance field names.
- Confirm Chunk 1 remains records/contracts/activation guard only, not full
  agent execution.

## Initial Risk Class

L1 - policy engine, task lifecycle, audit, and submission data boundaries.
