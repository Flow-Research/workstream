# Review Packet Template

> Planned contract; no review route is exposed before REV-13.

## Routing And Lease

- project ID:
- ReviewQueueEntry ID:
- ReviewLease ID:
- canonical reviewer ActorProfile ID:
- preferred/open routing reason:
- lease issued/expires at:
- conflict-of-interest attestation:
- contributor-reviewer pair risk:
- offline non-mutating quality sampling selected:
- quality sampling reason:

Quality sampling cannot delay or replace the Review decision, FinalAcceptance,
task effects, or contribution transaction.

## Exact Submission Packet

- task ID:
- TaskAssignment ID:
- Submission ID/version:
- predecessor Submission ID:
- admitting CheckerRun ID:
- ReviewPacketManifest ID:
- server-derived Submission artifact hash:
- ART binding IDs:

Artifact bytes are available only for this exact active-lease packet. History is
bounded metadata only.

## Stamped Context

- Project Guide ID/version/activation sequence:
- source snapshot reference:
- task-execution policy references:
- ReviewPolicy reference:
- RevisionPolicy reference:
- revision preparation ID/head/digest, when applicable:
- context outcome/direction/change summary, when applicable:

Use this stamped context. No guide rebase occurs during review.

## Decision

`accept | needs_revision | reject`

- immutable Review ID:
- predecessor Review ID:
- bounded summary:
- reject reason, required for reject:
- acceptance evidence, required for accept:

## Immutable Findings

| ReviewFinding ID | Kind | Area | Issue/Rationale | Required Change | Evidence Binding ID |
|---|---|---|---|---|---|
| `<uuid>` | `blocking` or `advisory` | `<area>` | `<issue>` | `<change or null>` | `<uuid or null>` |

`needs_revision` requires at least one blocking finding. Reject requires its
bounded reason; findings are optional when they add useful evidence.

## Prior Responses And Resolutions

| Prior Finding ID | SubmissionFindingResponse ID | Response Evidence | FindingResolution | Rationale |
|---|---|---|---|---|
| `<uuid>` | `<uuid>` | `<binding or null>` | `resolved`, `unresolved`, or `not_applicable` | `<rationale>` |

## Contribution Effects

Reviewer operation, required for every valid Review:

- ContributionRecord ID/type `completed_review`:
- source Review ID and ReviewLease ID:
- reviewer-frozen ContributionPolicyVersion:
- CompensationAward ID or explicit unpaid result:

Accept-only effects:

- FinalAcceptance ID:
- source Review ID and Submission ID:
- accepted submitter ActorProfile ID:
- recording reviewer ActorProfile ID:
- TaskAssignment completed:
- ContributionRecord ID/type `accepted_submission`:
- source FinalAcceptance ID and TaskAssignment ID:
- submitter-frozen ContributionPolicyVersion:
- CompensationAward ID or explicit unpaid result:

`needs_revision` and `reject` contain no FinalAcceptance or submitter
ContributionRecord.
