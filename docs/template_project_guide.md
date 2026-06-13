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

Define the required format, files, fields, package structure, and paste-ready or upload-ready standard.

## Acceptance Criteria

Define measurable criteria for accepted work.

## Rejection Criteria

Define disqualifying conditions and what fails automatically or normally leads to rejection.

## Reviewer Rubric

Define how reviewers evaluate quality. Workers see the same rubric they submit against.

## Forbidden Actions And Artifacts

Define prohibited behavior, files, tools, copied material, generated artifacts, confidential data, or evidence patterns.

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
- artifact hashes where possible

## Evidence Policy

Define acceptable evidence:

- required logs:
- required screenshots:
- required package hashes:
- required test/check outputs:
- external links allowed:
- evidence that is not sufficient:

Evidence must prove the submitted version, not an earlier local draft.

## Checker Policy

Required checkers:

- check_acceptance_criteria_present
- check_policy_context_present
- check_submission_packet
- check_evidence_present
- check_evidence_integrity
- check_required_files
- check_forbidden_files
- check_confidentiality_attestation
- check_low_quality_generated_artifacts

Blocking severities:

- high

Project-specific checkers:

- `<checker name>`:
  - severity:
  - blocks review:
  - failure message:

Known checker blind spots:

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
