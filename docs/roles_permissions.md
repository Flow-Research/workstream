# Roles And Permissions

This supporting note points to the canonical operator matrix in
`docs/operations_roles_permissions.md`, ADR 0012, and
`docs/spec_authorization_service.md`.

## Canonical Roles

Administrative grants:

- Access Administrator
- Operator
- Project Manager
- Finance Authority
- Audit Authority

Exact-project contributor grants:

- Submitter
- Reviewer
- Adjudicator

The external Flow token identifies a subject and supplies verified coarse
scope; it does not assign these roles. Workstream stores grants locally and
evaluates them against canonical resources and lifecycle guards.

Contributor is the umbrella human product term. Independent exact-project
Submitter, Reviewer, and Adjudicator grants determine candidate authority; one
actor may hold all three rows. The adjudicator grant creates no adjudication
capability in v0.1. A future separately approved initiative must define that
lifecycle before AUTH registers or activates exact adjudication actions. Celery,
checker, setup, and background workers are
internal services, not human product roles. Administrative grants alone never
authorize submission, review, or adjudication.

## Independence

- No actor administratively grants or revokes their own authority.
- A submitter cannot be the sole reviewer for their own work.
- Review decisions remain `accept`, `needs_revision`, or `reject` and require an
  exact active project reviewer grant, canonical human `ActorProfile.id`, and
  all review lifecycle guards. No other grant substitutes.
- Finance Authority cannot change review decisions or contribution records.
- Audit Authority cannot mutate product state.

## Recovery

Normal project repair uses covered Project Manager permission
`project.task.manage`. The planned review/revision repair, obligation-close,
legacy-close, and lifecycle-control actions are unavailable until their owning
hidden behavior, AUTH activation, and REV-13 release. Existing Operator recovery
is limited to the registered
permissions `operations.task.start_override`,
`operations.submission_gate.repair`, `operations.checker.retry`, and the
WS-REV-owned `review.lease.force_release`.

Recovery requires exact resource scope, a reason, matched grant/permission, and
append-only evidence. It does not erase prior evidence or bypass immutable
submission, review, contribution, or contribution award rules.

The complete planned review contract is `docs/spec_review_lifecycle.md`.
