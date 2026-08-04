# Project Guide Template

## Project Name

`<name>`

## Purpose

Describe what this project produces and why it matters.

## Task Types

- `<task type>`

## Business Terms Summary

Describe compensation expectations in plain language when useful for project
context. Enforceable submitter/reviewer rules live in the independently
published ContributionPolicyVersion, not in the guide or project shell.

## Difficulty And Time Policy

- difficulty scale:
- estimated time policy:
- maximum active tasks per contributor:
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

Define how reviewers evaluate quality. Contributors see the same rubric they submit against.

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
- deadline

## Required Submission Fields

- summary
- exactly one outer ZIP containing every required output/evidence file
- evidence
- revision replay when applicable
- contributor attestation

Workstream generates the archive commitment and semantic submission-bundle
manifest, then assigns the submission version server-side after blocking
pre-submit checks pass. The contributor does not provide a manifest, submission
version, or guide/policy version.

## Submission Expectations Summary

Summarize what contributors must submit in plain language:

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
- ContributionPolicy and active published version:

ContributionPolicyVersion is the source of truth for exact
`accepted_submission` and `completed_review` compensated/unpaid rules and any
immutable money/project-points award definitions.

Each task later locks:

- GuideSourceSnapshot id/hash:
- EffectiveProjectSubmissionArtifactPolicy hash:
- generated project PreSubmitCheckerPolicy compiled bundle hash:

Artifact requirements shown to contributors are derived from the approved `SubmissionArtifactPolicy`. The guide may summarize those requirements, but the policy is the enforcement source.

Project owners provide open-ended guide material and business terms in plain
language. Workstream evaluates guide sufficiency, derives
`SubmissionArtifactPolicy` from that material, and an authorized covered
Project Manager approves the internal policy bundle
before guide activation.

## Known Checker Blind Spots

- `<blind spot>`:
  - manual reviewer instruction:
  - future checker candidate:

## Review Policy

- review preference window seconds (positive):
- review lease duration seconds (positive):
- maximum active review leases per reviewer: `1` (fixed in v0.1)
- self review allowed: `false` (fixed in v0.1)
- reject policy: `close_task` (fixed in v0.1)
- finding evidence requirement: `optional | required_for_blocking | required_for_all`

Allowed decisions:

- accept
- needs_revision
- reject

Needs revision requires:

- at least one unresolved blocking finding
- concrete issue and required fix per blocking finding
- optional advisory findings that do not block acceptance

Offline post-decision reviewer-quality sampling only:

- accepted sample rate:
- rejected sample rate:
- suspected copied or confidential material:
- high-value criterion defined by `ReviewPolicy`:
- reviewer conflict of interest:

These criteria select non-product quality analysis only. They do not delay Review,
FinalAcceptance, contribution creation, or task closure and do not create a
second decision, reputation mutation, or adjudication path.
- registered recovery operation used (permission, actor, reason, evidence):

## Revision Policy

Define:

- maximum revision rounds:
- revision deadline hours:
- allowed resubmission states:
- limit/deadline exhaustion behavior: block preparation and submission pending
  reason-bound covered-manager closure; never synthesize reject
- reviewer reassignment rule:

Revision-policy activation and task screening require positive limit and
deadline values. Exhaustion blocks further preparation and submission; it never
auto-rejects, auto-closes, or fabricates a human review decision.

## Acceptance Policy

Accepted work must:

- satisfy task requirements
- satisfy acceptance criteria
- pass blocking checks
- include evidence
- preserve one immutable response and later resolution for each required prior
  blocking finding

## Rejection Policy

Reject when:

- work violates the guide
- work is non-original
- work cannot be fixed by reasonable revision
- prohibited content or files are included
- evidence is fabricated or does not correspond to the submitted artifact
- contributor repeatedly resubmits without addressing prior findings

## Common Rejection Reasons

- missing evidence
- incomplete output
- ignored acceptance criteria
- failed required checker
- vague or unverifiable claims
- prohibited files
- low-quality generated artifacts banned by this guide
- copied confidential/source material

## Compensation Business Terms Reference

Record only project-owner-supplied business terms and their durable source:

- source reference:
- intended submitter terms:
- intended reviewer terms:
- intended instrument/unit:

This section is informational. It is not an active contribution award rule. Workstream
publishes `ContributionPolicyVersion` independently, and `TaskAssignment` and
`ReviewLease` freeze their applicable versions for the current attempt. After a
human `needs_revision`, complete-context preparation records and applies any
changed submitter ContributionPolicyVersion for the next attempt; each next
ReviewLease independently freezes the reviewer version then current.

## Lessons Learned

Keep this section updated as the project runs.

Each repeated issue becomes a guide update, checker update, review policy update,
revision policy update, contribution policy update, template update, or
reviewer training note.
