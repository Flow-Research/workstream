# Revision Replay Template

> Planned contract; unavailable until REV/AUTH release gates complete.

## Episode

- task ID:
- originating `needs_revision` Review ID:
- prior Submission ID/version:
- source TaskAssignment ID:
- target TaskAssignment ID:

## Revision Context Preparation

| Field | Value |
|---|---|
| preparation ID | `<uuid>` |
| preparation sequence | `<integer>` |
| predecessor preparation ID | `<uuid or null>` |
| current head ID | `<uuid>` |
| context digest | `<sha256>` |
| outcome | `kept`, `rebased`, or `blocked` |
| direction | `forward`, `backward`, or `null` |
| prior guide ID/version/activation sequence | `<values>` |
| next guide ID/version/activation sequence | `<values>` |
| frozen source snapshot and task-execution policies | `<bounded references>` |
| change summary | `<contributor-visible summary>` |
| audit event ID | `<uuid>` |

The reviewer consumes the context stamped on the revised Submission and does
not perform a separate rebase. ContributionPolicyVersion is not part of this
preparation.

## Immutable Finding Responses

Every unresolved blocking finding requires one SubmissionFindingResponse.

| ReviewFinding ID | Kind | Required Change | Response Text | Finalized Evidence Binding ID |
|---|---|---|---|---|
| `<uuid>` | `blocking` or `advisory` | `<required change>` | `<what changed or bounded rebuttal>` | `<uuid or null>` |

## Later Immutable Resolutions

Completed by the later Review without editing the finding or response.

| ReviewFinding ID | Revised Submission ID | Result | Rationale | Evidence Binding ID |
|---|---|---|---|---|
| `<uuid>` | `<uuid>` | `resolved`, `unresolved`, or `not_applicable` | `<bounded rationale>` | `<uuid or null>` |

## Checker Readmission

- revised Submission ID/version:
- acknowledged preparation head/digest:
- current CheckerRun ID:
- routing outcome:
- preferred prior reviewer ID:
