# Project Guide Template

## Project Name

`<name>`

## Purpose

Describe what this project produces and why it matters.

## Task Types

- `<task type>`

## Task Examples Supplied With This Guide

Declare the complete document list when creating the guide, and provide at
least one nonblank task example in the request's
`task_examples` list. A starting idea or short description is enough; title and
labels are optional. Examples need not repeat this guide's deliverables or
acceptance criteria. Workstream stores the list with guide metadata in PostgreSQL
and supplies all examples to the setup agent alongside the uploaded guide files.
Uploaded guide files are stored in ArtifactStore/S3. Examples do not create
Workstream Tasks or select one assignment. The agent proposes project-wide
policy from the guide and the examples together.

The list accepts 1–100 examples, each with up to 65,536 content characters, an
optional title of up to 500 characters, and up to 20 labels of 1–100 characters
each. The full canonical UTF-8 JSON list must fit within 128 KiB. Examples are
immutable for that guide version; a correction uses a new guide version.

```json
{
  "version": "initial",
  "task_examples": [
    {"content": "Repair intermittent memory faults in the claims processing service."}
  ],
  "documents": [
    {"label": "project-guide.pdf", "media_type": "application/pdf"}
  ]
}
```

The response returns each document ID and the waiting setup ID. Upload each
original as a binary body to its project/guide/document content endpoint with
the declared `Content-Type` and a UUID `Idempotency-Key`. Setup starts when every
declared original has committed bytes. There is no separate source-snapshot
creation step.

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

ReviewPolicy setting: `human_review_required: true` (default). False may
be configured in draft; guide activation requires supported post-submission
checks providing the required acceptance evidence and an available, proven
automated acceptance path. This is
guide-bound policy configuration, not permission granted by writing this
template. False produces no reviewer contribution; adjudication is not part
of this v0.1 setting.
Set `requires_second_review: false`; this is the only supported v0.1 value and
does not create a second review or adjudication path.

Accepted work must be specific, auditable, and aligned with this guide. Avoid broad statements like "good quality" unless they are backed by concrete criteria.

Define what unacceptable work means for this project, including copied work, generic generated output, unverifiable evidence, missing source attribution, and unsafe handling of confidential data.

## Task Instructions

Define exactly what the submitter must do, step by step.

## Output Requirements

Describe the output form in human-readable language. The enforced artifact list, hash rules, storage rules, and forbidden artifact rules live in the approved `SubmissionArtifactPolicy`.

## Acceptance Criteria

Define the mandatory project-level acceptance requirements as measurable criteria
for accepted work. Tasks follow these requirements under their locked guide and
policies; they do not have to repeat them in task-local criteria.

## Rejection Criteria

Define disqualifying conditions and what fails automatically or normally leads to rejection.

## Reviewer Rubric

Define how reviewers evaluate quality. Contributors see the same rubric they submit against.

## Forbidden Actions And Artifacts

Define prohibited behavior, tools, copied material, generated artifacts, confidential data, or evidence patterns in human-readable language. Enforced artifact restrictions live in the approved `SubmissionArtifactPolicy`.

## Required Task Fields

- title
- description
- required output
- skill tags
- task type
- estimated time when known
- deadline

Task-local `acceptance_criteria` is optional and may be omitted or null, including
during import, screening and release. When supplied, it must satisfy the task
field type and length limits. Its absence does not remove the mandatory
guide-level acceptance requirements above.

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
- ProjectGuideCompilation and exact immutable result/component lineage:
- Immutable setup finalization reference:
- GuideSufficiencyReport:
- SubmissionArtifactPolicy:
- EffectiveProjectSubmissionArtifactPolicy hash:
- project PreSubmitCheckerPolicy compiled bundle hash:
- PostSubmitCheckerPolicy:
- ReviewPolicy:
- RevisionPolicy:
- ContributionPolicy and exact guide-bound published version:

At new activation, validate the expected version against the active policy's
current published selector. After binding, later policy publication does not
replace this guide/attempt lineage. Approval and correction records link to the
finalized compilation; they never rewrite its receipt.

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
- exhaustion behavior: failure on the final permitted attempt immediately
  retains rejection and exhaustion evidence, closes the assignment as
  `revision_exhausted`, and returns the task to `ready` atomically without
  another preparation or window, a synthetic Review, or economic facts
- reviewer reassignment rule:

Revision-policy activation and task screening require an explicit integer
maximum revision count `N >= 0` and positive deadline hours. Each assignment
starts at round 0 with its own allowance. A committed `needs_revision` with
another revision remaining freezes the next preparation from the failed
attempt's locked policy, with either a running PostgreSQL deadline or a paused
remaining allowance while setup is blocked. Only immutable resubmission ends
that opportunity; upload, replay and repair preserve its clock. Expiry retains
rejection evidence, releases the assignment, and returns the task to `ready`.
Checker revision implements this policy; #554 owns future human decision
integration under the same intended rules.

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
publishes `ContributionPolicyVersion` independently. Guide activation binds one
version; task readiness locks it, `TaskAssignment` copies it, Submission stamps
the attempt value, and `ReviewLease` copies that stamp. After checker or human
`needs_revision`, complete-context preparation may
atomically rebase the continuing Task and TaskAssignment for the next attempt;
prior Submissions, ReviewLeases, contributions, and awards remain immutable.

## Lessons Learned

Keep this section updated as the project runs.

Each repeated issue becomes a guide update, checker update, review policy update,
revision policy update, contribution policy update, template update, or
reviewer training note.

## Checker Coverage And Engineering Handoff

Describe required outcomes in the guide; the PM need not label checks PRE or POST
or design their implementations. Setup reads the assigned guide documents and
task examples and proposes source-cited check specifications. It does not see
the checker registry, image choices or runtime profiles. Each proposed PRE or
POST check explains its stage and gives inputs, steps, pass/fail findings and
positive and negative implementation test examples. Missing guide information
can block a proposal; a missing implementation alone cannot.

The canonical compilation stores the proposal for PM and engineering review.
Engineering implements, tests, pushes to ECR and registers chosen external
images. An authorized Project Manager then attaches explicit
`pre_submit_attachments` and `post_submit_attachments` lists with exact image
identities and non-secret configuration during approval. Empty lists are valid
intent when no project image is required. Image attachments are phase choices,
not one-to-one matches to setup suggestions; one image may cover several checks
and a phase may use several images. The Workstream PRE default remains separate.
Registration after proposal does not change its hash or require another setup
run. Approval locks exact image digest and configuration. Suggestions never
register, execute or activate checks. Optional/configurable automatic setup is
deferred; manager feedback for improving setup remains deferred.
