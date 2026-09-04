# WS-ARCH-001-02H Consumption Activation Evidence

## Activated authority

- Human `submission.create` is active only for the exact human contributor
  holding an active submitter project-role grant.
- Fixed-service `artifact.submission.binding.create` is active only for
  `workstream.artifact.binding` through the existing static service matrix.
- No new action, permission, service identity, route, or persistence schema is
  introduced.

## Exact human facts

TASK passes its already-locked immutable submission context into final AUTH
consumption. AUTH binds the decision to the actor, project, task, assignment,
admission, predecessor identity/version, Submission identity/version, lifecycle
kind/status, guide/source snapshot, effective artifact policy, and pre-submit
checker policy. AUTH independently locks the actor, identity link, and active
submitter project-role grant.

## Exact fixed-service facts

ART binds the fixed-service decision to the admission, evidence set, actor and
identity link attribution, project, task, assignment, predecessor, Submission,
guide/source/policy lineage, semantic manifest, immutable content digest and
size, and `submission_bundle_original` logical role.

## Transaction and denial

Both decisions use the existing opaque process-local PREP protocol in the one
02F root transaction. Handles remain non-copyable, non-serializable,
session-bound, transaction-bound, action-bound, resource-bound, and single-use.
Authorization evidence is written by AUTH in that transaction. Any human or
service denial, cancellation, persistence failure, or transaction rollback
rolls back the provisional Submission, binding, admission transition, and
authorization evidence together. The public Submission route remains
unchanged.
