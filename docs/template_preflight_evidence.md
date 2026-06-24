# Review Readiness Evidence Template

This template is for post-submit review readiness evidence after a submission exists and checker runs have produced durable records.

It is not the pre-submit intake contract. Pre-submit intake is generated from the project `PreSubmitCheckerPolicy` and blocks submission creation before a submission id, evidence id, or checker run id exists.

## Task

`<task id>`

## Submission

`<submission id / version>`

## Locked Project Guide Version

`<guide version>`

## Locked Post-Submit Checker Policy Version

`<post-submit checker policy version>`

These values come from Workstream's task context and checker run records. They are not worker-provided submission fields.

## Readiness Summary

State what was checked before review.

## Checks Run

| Check | Result | Checker Run ID | Evidence ID | Evidence |
| --- | --- | --- | --- | --- |
| `<checker>` | `<passed/warning/failed>` | `<checker run id>` | `<evidence id>` | `<log/hash/reference>` |

## Package Evidence

- package path or URI:
- package hash:
- artifact count:
- required files present:
- artifact hash manifest:
- evidence ids bound to artifact hashes:

## Review Readiness

Confirm:

- task guide is attached
- acceptance criteria exist
- output package exists
- evidence exists
- evidence ids exist
- blocking checker failures are closed or overridden
- revision replay exists when required

## Known Warnings

List non-blocking warnings reviewers see.
