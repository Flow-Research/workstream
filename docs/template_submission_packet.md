# Submission Packet Template

## Task

`<task id>`

## Worker

`<worker id>`

## Submission Version

Assigned by Workstream after blocking pre-submit checks pass. The worker does not provide this value.

## Summary

Briefly describe what was completed.

## Output

List files, links, packages, or deliverables.

## Provenance

- package hash:
- artifact hash manifest:
- generated at:

Workstream derives the locked project guide version, locked guide-source
snapshot id/hash, effective project submission artifact policy id/hash,
generated project pre-submit checker policy id/bundle hash, post-submit
checker policy context, review policy version, revision policy version, and
payment policy version from the task's locked context. The worker does not
provide those ids, versions, hashes, or internal policy bodies in the
submission packet.

Workstream runs pre-submit checks from the locked project pre-submit checker policy before creating the submission.
Preflight failures return `PreSubmitCheckResponse` with structured
pass/fail/warning details. Blocked submission-create attempts return
`pre_submission_checker_failed` with the same structured details, create no
submission row, no submission version, and no submission-created audit event,
and do not return review decision values: `accept`, `needs_revision`, or
`reject`.

## Artifact Hash Manifest

| Artifact | Hash | Size | Notes |
| --- | --- | ---: | --- |
| `<relative-artifact-path>` | `sha256:<64 lowercase hex>` | `<bytes>` | `<notes>` |

## Evidence

| Type | Label | URI Or Reference | Hash | Proves Which Artifact Or Claim |
| --- | --- | --- | --- | --- |
| `<type>` | `<label>` | `<local/s3/r2 object reference>` | `sha256:<64 lowercase hex>` | `<claim>` |

When relevant, include the command, environment, dataset/version, or generation settings that produced the evidence.

Workstream assigns evidence IDs at persistence time. Checker run IDs are created only after post-submit internal checks run.

## Draft Checker Notes

Any known worker-facing context that helps explain the packet. The worker does not provide checker outcomes, severities, policy versions, or pass/fail statuses.

## Revision Replay

Only required for resubmissions.

Workstream provides prior and next guide/policy context for the revision. The worker responds to the findings and changed requirements, but does not provide guide or policy versions manually.

| Prior Finding | Fix Summary | Evidence | Status |
| --- | --- | --- | --- |
| `<finding>` | `<fix>` | `<evidence>` | `closed` |

## Worker Attestation

I confirm this submission is original, complete, follows the locked project guide, and does not include prohibited confidential material, private source data, credentials, or copied platform artifacts.

I also confirm that any agent-assisted or tool-assisted work was reviewed by me before submission and that I am accountable for the submitted packet.
