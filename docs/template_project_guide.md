# Project Guide Template

## Project Name

`<name>`

## Purpose

Describe what this project produces and why it matters.

## Task Types

- `<task type>`

## Base Amount

- currency:
- base amount:
- payout type:
- payout rule:

## Difficulty And Time Policy

- difficulty scale:
- estimated time policy:
- maximum active tasks per worker:
- review SLA:

## Guide Versioning

- guide version:
- effective date:
- approver:
- change summary:

Tasks must attach a locked guide version. Later guide edits do not silently change active tasks.

## Quality Bar

Define what accepted work means for this project.

Accepted work must be specific, auditable, and aligned with this guide. Avoid broad statements like "good quality" unless they are backed by concrete criteria.

Define what unacceptable work means for this project, including copied work, generic generated output, unverifiable evidence, missing source attribution, and unsafe handling of confidential data.

## Task Instructions

Define exactly what the submitter must do, step by step.

## Output Requirements

Describe the output form in human-readable language. The enforced artifact list, hash rules, storage rules, and forbidden artifact rules live in the approved `SubmissionArtifactPolicy`.

## Acceptance Criteria

Define measurable criteria for accepted work.

## Rejection Criteria

Define disqualifying conditions and what fails automatically or normally leads to rejection.

## Reviewer Rubric

Define how reviewers evaluate quality. Workers see the same rubric they submit against.

## Forbidden Actions And Artifacts

Define prohibited behavior, tools, copied material, generated artifacts, confidential data, or evidence patterns in human-readable language. Enforced artifact restrictions live in the approved `SubmissionArtifactPolicy`.

## Required Task Fields

- title
- description
- acceptance criteria
- required output
- skill tags
- task type
- estimated time when known
- base amount
- payout type
- deadline

## Required Submission Fields

- summary
- output files or package
- evidence
- revision replay when applicable
- worker attestation
- artifact hash manifest

Workstream assigns submission version server-side after blocking pre-submit checks pass. The worker does not provide a submission version or any guide/policy version.

## Submission Expectations Summary

Summarize what workers must submit in plain language:

- required artifacts:
- required evidence references:
- required package or archive:
- required logs:
- evidence that is not sufficient:

This section is a human-readable summary. The enforcement source is the approved `SubmissionArtifactPolicy`.

## Linked Policy Context

Every active guide version must have:

- GuideSourceSnapshot:
- GuideSufficiencyReport:
- SubmissionArtifactPolicy:
- EffectiveProjectSubmissionArtifactPolicy hash:
- project PreSubmitCheckerPolicy compiled bundle hash:
- PostSubmitCheckerPolicy:
- ReviewPolicy:
- RevisionPolicy:
- PaymentPolicy:

Each task later locks:

- GuideSourceSnapshot id/hash:
- EffectiveProjectSubmissionArtifactPolicy hash:
- generated project PreSubmitCheckerPolicy compiled bundle hash:

Artifact requirements shown to workers are derived from the approved `SubmissionArtifactPolicy`. The guide may summarize those requirements, but the policy is the enforcement source.

Project owners provide open-ended guide material and business terms in plain
language. Workstream evaluates guide sufficiency, derives
`ProjectSubmissionArtifactPolicy` from that material, and a Workstream actor
with the `admin` or `project_manager` role approves the internal policy bundle
before guide activation.

## Known Checker Blind Spots

- `<blind spot>`:
  - manual reviewer instruction:
  - future checker candidate:

## Review Policy

Allowed decisions:

- accept
- needs_revision
- reject

Needs revision requires:

- concrete findings
- required fix per finding
- severity per finding

Second-review sampling:

- accepted:
- rejected:
- high-value tasks:

Mandatory second review:

- suspected copied or confidential material:
- payment above threshold:
- reviewer conflict of interest:
- admin override used:

## Revision Policy

Define:

- maximum revision rounds:
- revision deadline hours:
- allowed resubmission states:
- auto-reject after revision limit:
- missed deadline behavior:
- reviewer reassignment rule:
- payment effect during revision:

## Acceptance Policy

Accepted work must:

- satisfy task requirements
- satisfy acceptance criteria
- pass blocking checks
- include evidence
- close prior revision findings

## Rejection Policy

Reject when:

- work violates the guide
- work is non-original
- work cannot be fixed by reasonable revision
- prohibited content or files are included
- evidence is fabricated or does not correspond to the submitted artifact
- worker repeatedly resubmits without addressing prior findings

## Common Rejection Reasons

- missing evidence
- incomplete output
- ignored acceptance criteria
- failed required checker
- vague or unverifiable claims
- prohibited files
- low-quality generated artifacts banned by this guide
- copied confidential/source material

## Payment Dispute Policy

Define:

- when accepted work becomes payable:
- who can open a payment dispute:
- evidence required for dispute:
- dispute review owner:
- payment hold rule:
- final decision authority:

## Lessons Learned

Keep this section updated as the project runs.

Each repeated issue becomes a guide update, checker update, review policy update, revision policy update, payment policy update, template update, or reviewer training note.
