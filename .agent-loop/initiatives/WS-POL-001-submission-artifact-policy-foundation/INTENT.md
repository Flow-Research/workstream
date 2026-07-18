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
-> Workstream-derived SubmissionArtifactPolicy
-> approval by admin or project_manager

WorkstreamDefaultSubmissionArtifactPolicy
+ SubmissionArtifactPolicy
= EffectiveProjectSubmissionArtifactPolicy

EffectiveProjectSubmissionArtifactPolicy
-> trusted Workstream checker compiler
-> persisted project PreSubmitCheckerPolicy

Task
-> locks guide snapshot
-> locks effective project submission artifact policy hash
-> locks PreSubmitCheckerPolicy compiled bundle hash
```

Project owners provide open-ended project material: markdown, URLs, full
documentation, examples, rubrics, repository docs, task instructions, domain
requirements, compensation business terms, or any other project-specific
source material. Compensation business terms are untrusted
owner input; an authorized Finance Authority publishes the independent
`ContributionPolicyVersion`, not project creation. Workstream must not force every
project into one fixed intake checklist. A project guide can be a URL to a
complete documentation set if that is the right form for the project.

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
not approve this internal policy. A
Workstream actor with the `admin` or `project_manager` role approves the
derived policy and activates the guide-policy bundle. Workers submit draft
packet fields. Workstream decides required artifacts, evidence, hashes, storage
reference rules, forbidden artifacts, and blocking pre-submit feedback from the
locked effective policy and compiled project checker bundle.

The derivation agent produces a constrained artifact-intake contract. Workstream
builds and validates the checker specification from that contract, then
compiles deterministic checker logic. Runtime submission evaluation is performed
by the locked checker bundle, not by an agent.

Every task under the same active project guide version reuses that guide
version's compiled project checker bundle. A task locks the policy/checker
context that governs it; it does not get a freshly derived policy or freshly
compiled checker. If the sufficiency agent finds that the guide does not cover
the project's task set, activation is blocked and the guide is improved or the
work is split into another project/guide. Small task-specific values are
constrained parameters fed into the same locked checker bundle, not new checker
generation.

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
- `GuideSourceSnapshot` is a first-class immutable record for the exact guide
  material bundle Workstream evaluated.
- `GuideSufficiencyReport` is a first-class record tied to a guide source
  snapshot.
- Workstream default submission artifact rules are defined in code.
- Project submission artifact policy cannot weaken Workstream defaults.
- Effective project submission artifact policy is computed deterministically.
- Generated pre-submit checker policy is persisted at project scope and tasks
  lock its compiled bundle hash during screening before entering `READY`.
- Workstream's trusted compiler produces the project pre-submit checker
  policy from approved checker primitives, not by unrestricted generated code.
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

Pre-submit feedback is not review. Preflight failures return
`PreSubmitCheckResponse` with structured pass/fail/warning details. A blocked
submission-create attempt returns `pre_submission_checker_failed` with those
details. It does not create a submission and must not use review decision
values.

## Human Judgment Required

- Approve the chunk sequence before implementation.
- Confirm guide sufficiency severity names and report fields.
- Confirm persisted policy provenance field names.
- Confirm Chunk 1 remains records/contracts/activation guard only, not full
  agent execution.

## Initial Risk Class

L1 - policy engine, task lifecycle, audit, and submission data boundaries.
