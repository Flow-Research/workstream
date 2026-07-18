# Task Template

## Title

`<task title>`

## Project

`<project name>`

## Source

- source type: `manual | markdown_import | csv_import`
- source reference:
- source payload hash:
- import batch id:

## Guide Version

`<guide version>`

## Status

`DRAFT`

## Difficulty

`<easy | medium | hard | expert>`

## Estimated Time

`<minutes>`

## Task Type

`<task type>`

## Skill Tags

- `<skill>`

## Description

Describe the work to be done.

## Output Notes

Describe task-specific work in human terms when the description needs more
detail. Machine-enforced required files, evidence, hashes, packaging, and
forbidden artifacts are defined by the active project
`SubmissionArtifactPolicy` and locked project `PreSubmitCheckerPolicy`, not by
task fields.

## Acceptance Criteria

- Criterion 1
- Criterion 2
- Criterion 3

## Rejection Criteria

- Criterion 1

## Submission Artifact Policy Context

These values are stamped from the active project policy bundle during
screening. Task creators do not provide submission artifact requirement fields
directly.

- guide source snapshot id:
- guide source snapshot hash:
- effective project submission artifact policy id:
- effective project submission artifact policy hash:
- project pre-submit checker policy id:
- project pre-submit checker bundle hash:

## Assignment Compensation Snapshot

These values are server-owned and appear only after TaskAssignment creation.
The TaskAssignment freezes the active published ContributionPolicyVersion; task
creators do not provide award fields directly.

- submitter contribution policy version id:
- contribution type: `accepted_submission`
- compensation mode: `compensated | unpaid`
- immutable award definitions when compensated:

## Deadline

`<date/time>`

## Notes

Any project-specific constraints.
