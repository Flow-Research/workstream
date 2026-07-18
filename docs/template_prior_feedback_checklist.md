# Prior Feedback Checklist Template

> Planned immutable response/resolution contract; not a mutable closure list.

## Review Episode

- task ID:
- prior Submission ID:
- originating Review ID:
- preparation head ID/digest:

## Required Responses

| ReviewFinding ID | Kind | Required Change | SubmissionFindingResponse | Evidence Binding |
|---|---|---|---|---|
| `<uuid>` | `blocking` or `advisory` | `<change>` | `<response>` | `<uuid or null>` |

Every unresolved blocking finding requires exactly one response. Advisory
responses are optional unless locked policy says otherwise.

## Later Review Resolutions

| ReviewFinding ID | FindingResolution | Rationale | Evidence Binding |
|---|---|---|---|
| `<uuid>` | `resolved`, `unresolved`, or `not_applicable` | `<rationale>` | `<uuid or null>` |
