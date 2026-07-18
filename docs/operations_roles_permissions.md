# Roles And Permissions

## Purpose

This is the canonical operator-facing role and permission matrix for the target
Workstream authorization service. ADR 0012 and
`docs/spec_authorization_service.md` define precedence and implementation
order. Until each WS-AUTH-001 cutover chunk merges, legacy runtime behavior is
current-code evidence, not authority for new design.

## Authentication Versus Authorization

The external Flow Identity Issuer owns login, token issuance, audience, subject
kind, and token signing. Workstream verifies those facts and resolves the
issuer/subject through a local identity link.

Workstream roles are local grants. Token role claims, coarse scopes, email,
display name, skills, reputation, and typed workflow profiles do not grant
product authority. Scopes are an outer request-class gate only.

## Administrative Grants

| Grant | Scope | Purpose |
|---|---|---|
| Access Administrator | system | Actor, identity-link, and administrative-grant management. AUTH owns the closed permission/action catalog and action availability. |
| Operator | system | Runtime observation, reconciliation, retry, and approved recovery against canonically resolved resources. |
| Project Manager | system or exact covered project | Project configuration, project tasks, guide/setup, submission/checker, review, and revision configuration, and contributor grants. |
| Finance Authority | system or exact covered project | Contribution policy, compensation-adapter binding, and fulfillment observation under WS-CON-001. |
| Audit Authority | system or exact covered project | Read-only evidence access and authorized export. |

Administrative grants do not imply contributor capability. Holding one does
not permit claiming tasks, submitting work, or recording review decisions.

## Contributor Grants

| Grant | Scope | Purpose |
|---|---|---|
| Submitter | exact project | Minimal project read, queue/claim/start under task guards, own submission creation/read. |
| Reviewer | exact project | Minimal project read and the planned server-selected current-work/claim/release/decision capabilities under exact review guards. |
| Adjudicator | exact project | Minimal project read only; v0.1 has no adjudication lifecycle or action. |

Contributor is the umbrella human product term. A contributor may hold
independent exact-project Submitter, Reviewer, and Adjudicator grants. Celery,
checker, setup, and background workers are internal services, not human product
roles.

## Capability Matrix

Legend: system means the grant must cover all Workstream; covered means system
or the exact project; own means record-level ownership still applies.

| Capability | Access Administrator | Operator | Project Manager | Finance Authority | Audit Authority | Submitter | Reviewer | Adjudicator |
|---|---|---|---|---|---|---|---|---|
| Self profile | inherited human | inherited human | inherited human | inherited human | inherited human | inherited human | inherited human | inherited human |
| Actor/link administration | system | no | no | no | minimal read covered | no | no | no |
| Administrative grants | system | no | no | no | history read covered | no | no | no |
| Project create | no | no | system only | no | no | no | no | no |
| Project read | authority-only | system operational | covered | covered finance projection | covered audit projection | exact project minimal | exact project minimal | exact project minimal |
| Project, guide, submission/checker, review, and revision configuration | no | recovery-only where registered | covered | no | no | no | no | no |
| Contribution policy and compensation-adapter binding | no | no | no | covered | no | no | no | no |
| Project contributor grants | no | no | covered | no | read covered | no | no | no |
| Task management | no | explicit recovery only | covered | no | read covered | no | no | no |
| Task queue/claim | no | operational projection only | management projection only | no | read covered | exact project under guards | no | no |
| Submission create/read | no | operational projection only | management projection only | no | read covered | own assignment | read-for-review only | no |
| Human review decision | no | no | no without reviewer grant | no | no | no | exact project under review guards | no |
| Adjudication action | no | no | no | no | no | no | no | unavailable in v0.1; future separate initiative |
| Compensation award read and delivery reconciliation | no | no | no | covered | read covered | no | no | no |
| Fulfillment result recording | no | no | no | no; authenticated WS-CON adapter callback only | read covered | no | no | no |
| Audit read/export | authority history system | operational system | project covered | finance covered | covered | own chain only | assigned chain only | no |

A contributor may hold Submitter, Reviewer, and Adjudicator capabilities
through three independent exact-project grants. No grant adds administrative
capability, and every ownership, assignment, no-self-review,
separation-of-duties, and lifecycle guard applies to the selected action.

Access Administrator's authority-only project view means the minimum resource
identity necessary to administer grants; it is not general project-management
visibility.

## Separation Rules

- No actor grants or revokes their own authority through an administrative
  operation.
- A submitter cannot be the sole reviewer of their own task/submission chain.
- Project Manager authority is limited to covered projects.
- Access Administrator cannot manage project work by that grant alone.
- Access Administrator cannot edit the closed permission/action catalog or
  change action availability by that grant alone; AUTH owns both contracts.
- Operator cannot issue grants, approve policy, record a review decision, or
  mutate immutable records by that grant alone.
- Finance Authority cannot create or alter review decisions or contribution
  records.
- Audit Authority is read-only.
- A service principal never receives a fabricated human administrative grant.

## Recovery Operations

Recovery is a separate, reasoned, audited path.

| Operation | Permission | Actor |
|---|---|---|
| Normal covered task/setup repair | `project.task.manage` | Covered Project Manager |
| Task start override | `operations.task.start_override` | Operator |
| Submission gate repair | `operations.submission_gate.repair` | Operator |
| Checker retry | `operations.checker.retry` | Operator |
| Review lease force release | `review.lease.force_release` | Operator under WS-REV-001 |
| Revision-context repair | `project.task.manage` via planned `review.revision_context.repair` | Covered Project Manager |
| Revision-obligation close | `project.task.manage` via planned `review.revision_obligation.close` | Covered Project Manager |
| Legacy revision close | `operations.reconcile.run` via planned `review.revision_context.legacy_close` | Operator |
| Lifecycle release control | `operations.reconcile.run` via planned `review.lifecycle.activation.manage` | Operator |

Every recovery mutation records the exact actor, matched grant/permission,
project/resource, reason, bounded before/after state, request/correlation IDs,
and immutable evidence. Recovery cannot erase checker results, rewrite
submissions, create review decisions, alter contribution history, or bypass
contribution award rules.

The review/revision rows above are contract declarations, not active runtime
capabilities. Their exact guards and release gates are defined in
`docs/spec_review_lifecycle.md`; no review route is exposed before REV-13.

## Provisioning And Revocation

The first Access Administrator is created once through a restricted local
management command, `python -m scripts.bootstrap_access_administrator`, using
an existing active human ActorProfile UUID and exactly one of `--dry-run` or
`--execute`. Later administrative and project grants use supported APIs
and require current authority, exact scope, target-state guards, reason where
required, idempotency, and append-only evidence.

Grant revocation, actor suspension/deactivation, and identity-link revocation
take effect on the next request. Sensitive mutations revalidate current
authority inside their database transaction. Revoked records remain history.

## Enforcement Location

Routers parse input and map stable errors. Application services load canonical
resources, compose `ResourceContext`, and call the single authorization
service. Repositories own persistence queries and do not evaluate permissions.

No protected operation may accept a request-body role/scope, token role, typed
workflow profile, or direct database edit as the caller's authority. An
administrative grant request carries the target grant's requested role and
scope as mutation data; Workstream still derives the caller's authority from
current canonical grants and resolves every project scope from its own records.
