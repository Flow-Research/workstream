# AUTH <-> REV Handoff

## Boundary

AUTH owns review ActionId registration, PermissionId mapping, activation custody,
human/project grants, the typed static service-action matrix, evaluator
dispatch, matched authority, prepared mutation handles, decision evidence, and
availability. REV owns review resource loading, lifecycle guards, hidden
behavior, and product state transitions.

Human review authority comes from one exact active `reviewer`
ProjectRoleGrant. A human who also submits holds a separate `submitter` grant;
an adjudicator grant is a third independent row. There is no combined role, and
revoking any one grant leaves the others intact. Adjudication actions remain
unavailable until WS-REV defines their lifecycle and AUTH activates them.

## Required choreography

```text
AUTH registers planned review action and typed context
-> required CON participant or ART capability merges hidden
-> REV implements hidden review behavior and canonical resource composition
-> AUTH integrates evaluator and activates exact action
-> REV joint release gate exposes the surface
```

REV must not require an active action before building the hidden behavior that
AUTH needs to evaluate. Test fakes may exercise the hidden domain boundary, but
the real kernel must continue returning `action_unavailable` until activation.

## Reads and mutations

Read actions use request-scoped `AuthorizationService.require()` against
REV-composed typed facts and bounded concealment. Mutation actions use AUTH's
prepared protocol: AUTH locks authority first; REV locks queue/lease/review/task
rows; REV recomposes final facts; AUTH evaluates once; REV and typed participants
flush; the route commits once.

REV never imports AUTH models/repositories, reads grants, selects raw
PermissionIds, supplies candidate roles, constructs action strings, or commits
authorization independently. AUTH never imports REV repositories or mutates
review lifecycle rows.

## Activation custody correction

Current review actions assigned to `REV_05`, `REV_06`, `REV_07`, `REV_08`,
`REV_09A`, `REV_11`, and `REV_12` require the same custody decision as ART. The
AUTH/REV owner must publish a complete mapping from every current and approved
additive review ActionId to one exact AUTH activation chunk while preserving all
PermissionId mappings. Partial transfer or dual writers are forbidden.

At minimum the mapping must cover queue read/inspect, claim/release/decline,
preference and lease expiry, context/chain reads, finding and response evidence,
decision, force release, queue override/correction/close, reconciliation,
artifact-reference reconciliation, and projection rebuild. The four proposed
additive REV ActionIds are exact and are not registered on trusted `main`:

- `review.revision_context.repair` -> `project.task.manage`;
- `review.revision_context.legacy_close` -> `operations.reconcile.run`;
- `review.revision_obligation.close` -> `project.task.manage`;
- `review.lifecycle.activation.manage` -> `operations.reconcile.run`.

They remain out of runtime scope until a separate AUTH registration contract is
approved and merged. Exact current-action counts must be derived from the merged
catalogue at implementation time; the four proposed additions must not be
silently counted as registered actions.

Review evidence binding also requires the separately registered
`artifact.review_evidence.binding.create` service action defined by the ART/REV
handoff. It is not a review-human authority alias and does not broaden any
reviewer grant.

## Service actions

Timer, reconciliation, artifact-reference, projection, and release-control jobs
use fixed AUTH service identities admitted through AUTH-09E and exact static
matrix rows. They never use a human
reviewer or Operator identity by convention. AUTH activation remains separate
from REV job leases, queue claims, and execution fencing.

## AUTH owner response

AUTH must create bounded registration/transfer/activation chunks, supply the
prepared protocol and exact evaluator contracts, and prove active-action parity
against merged REV behavior.

## REV owner response

REV must repair feature-activation wording, identify every canonical typed
resource fact and transaction-local guard, build hidden behavior, and publish
an activation manifest without changing AUTH availability. It must also
consume reviewer-grant invalidation without mutating submitter/adjudicator
authority and later consume adjudicator invalidation only when the separately
approved adjudication lifecycle is enabled.

This handoff changes no runtime and starts no downstream chunk.
