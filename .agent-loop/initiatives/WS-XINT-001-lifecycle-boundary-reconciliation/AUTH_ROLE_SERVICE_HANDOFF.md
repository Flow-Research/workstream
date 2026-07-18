# AUTH Project-Role And Service-Runtime Handoff

## Purpose

This is the one canonical handoff that AUTH, ART, REV, and CON must read before
amending their own plans. It reconciles project contributor grants and fixed
service runtime admission without starting or implementing another initiative.

Together with ADR 0015, this handoff supersedes conflicting combined-role or
service-admission wording in active owner plans. An owner must reconcile its
intent, decisions, plan, chunk contracts, conformance proof, and public spec
before starting affected runtime work; stale owner wording is not an alternate
contract.

PR #132's AUTH-09A foundation remains valid: a service `ActorProfile` carries
one immutable `service_identity`, its `ActorIdentityLink` binds the verified
issuer subject, and one closed static matrix maps that identity to exact
ActionIds. This handoff adds the missing runtime-admission boundary and corrects
the older combined contributor-role model.

## Independent project contributor grants

The v0.1 persisted project roles are exactly:

```text
submitter
reviewer
adjudicator
```

There is no `both` value. A human may hold all three active ProjectRoleGrant
rows for the same project. Revoking any one row has no effect on the other rows
or on any `AdminRoleGrant`.

The adjudicator grant is part of the closed project-role model now, but it
provides only the minimal exact-project visibility defined by AUTH-11 until
WS-REV later defines and AUTH activates explicit adjudication actions. Merely
holding the grant cannot submit, review, override, or adjudicate. This shared
minimal `project.read` projection is resource visibility, not an adjudication
operation or an adjudication authority candidate.

The database invariant is one active row per exact role:

```sql
create unique index ...
on project_role_grants (actor_profile_id, project_id, role)
where status = 'active';
```

Grant issue creates only the requested role. It never revokes or replaces a
different role. Duplicate active issue conflicts. Regrant after revocation
creates a new immutable row. Revocation targets one exact grant ID.

The active model removes cross-role replacement, `replaced_grant_id`, and
`ProjectRoleGrantReplaced`. Qualification evidence is role-specific: each grant
references a snapshot bound to the same actor profile, project, and requested
role. Skills or reputation may inform the snapshot but never create authority.

The change is a clean cut. Previously merged migrations remain immutable, but
the AUTH-10 migration replaces the current Python/PostgreSQL validators so new
evidence accepts only `submitter`, `reviewer`, or `adjudicator`. Because no ProjectRoleGrant
runtime has shipped, it must fail closed on unexpected combined-role or
replacement evidence rather than add compatibility aliases or silently convert
it. After AUTH-09A owns migration `0023`, AUTH-10 owns the next migration,
`0024`; later reserved migration numbers move consistently.

## Role-specific invalidation

`ProjectRoleGrantRevoked` records the immutable grant, actor, project, and exact
role. Its linked invalidation obligation keeps the grant and cause-event
references; it does not duplicate or reinterpret product state.

```text
submitter revoked
  -> AUTH-13 task-assignment reconciliation

reviewer revoked
  -> WS-REV review-lease, preference, and queue reconciliation

adjudicator revoked
  -> WS-REV adjudication-assignment reconciliation when that lifecycle is enabled

AdminRoleGrant revoked
  -> no ProjectRoleGrant is removed
```

AUTH records authority loss and the durable obligation. The owning product
consumer changes assignment or review state. Actor/profile or identity-link
reactivation never restores a revoked grant. Every sensitive action still
reloads the exact active grant inside its committing transaction; invalidation
is not an authorization cache.

## Fixed service runtime admission

AUTH must add a bounded `WS-AUTH-001-09E` contract after controlled service
provisioning and before any fixed service executes a protected Workstream
command:

```text
verified service token
-> exact active ActorIdentityLink
-> exact active service ActorProfile
-> immutable fixed service_identity
-> exact static service-action matrix row
-> typed service AuthorizationContext
-> canonical feature ResourceContext and guards
-> authorization decision
```

The service path never enters human first-access provisioning, contributor
grant evaluation, administrative grant evaluation, or human self-profile
actions. Unknown subjects, missing profiles/links, inactive state, identity
mismatch, actions outside the exact matrix row, and planned actions all deny.
Sensitive mutations revalidate the profile, link, fixed identity, matrix row,
action availability, and feature facts inside the committing transaction.

AUTH-09E activates no ART, REV, CON, project, task, or checker operation. The
feature owner still supplies hidden behavior, canonical resource facts, guards,
surface declarations, and transaction proof; AUTH later activates that exact
action. Missing provisioned service rows deny service requests but do not stop
the application from starting, because Workstream must remain available for an
Access Administrator to provision them.

The static matrix is typed code, not a service-grant table. A new runtime
service identity requires an approved owning-feature specification, one new
closed `ServiceIdentity`, an exact static action row, database constraint
migration, action ownership, explicit provisioning, and negative cross-service
tests. No shared catch-all service identity, dynamic service grants, or shared permission
union is permitted. An external provider needs a Workstream service
`ActorProfile` only when it calls a protected Workstream command; Workstream
calling that provider through an adapter does not create a provider actor.

Known future identities must still be proposed by their owning feature rather
than pre-created here. Expected boundaries include project setup, pre-review
checker execution, authority-invalidation reconciliation, review preference
expiry, review lease expiry, review reconciliation, review projection rebuild,
contribution-event processing, compensation-delivery reconciliation, and
shared outbox dispatch when it invokes protected Workstream commands. They must
not collapse into one shared service identity.

## Owner responses

### AUTH

- Add a superseding decision for independent `submitter`, `reviewer`, and
  `adjudicator` grants; preserve D11's `Contributor` umbrella term.
- Add a superseding decision stating that the service-ActorProfile decision
  replaces only D7's conflicting “not a normal ActorProfile” clause; explicit
  system authority and no human grants remain mandatory.
- Add AUTH-09E and make feature service-action consumption depend on it.
- Reconcile AUTH-10 through AUTH-16, typed schemas, active audit validation,
  idempotency, conformance, migration custody, and role-specific invalidation.

### REV

- Replace reviewer-or-combined grant checks with one exact active `reviewer`
  grant and preserve no-self-review guards.
- Consume reviewer revocation without mutating submitter authority.
- Preserve the independent adjudicator grant while keeping every adjudication
  action unavailable until a separate reviewed lifecycle contract exists.
- Use fixed service admission for timer, reconciliation, expiry, and projection
  commands; never fabricate a human reviewer or Operator.

### ART

- Require AUTH-09E service admission before protected verifier, scheduler,
  resolver, binding, materializer, guide-reader, or checker-output commands.
- Keep ART resource composition, lifecycle guards, execution fencing, and
  provider mechanics ART-owned; never resolve issuer subjects or grants.

### CON

- Require the independent `submitter` grant wherever contribution setup relies
  on the upstream task-claim authority chain.
- Use fixed service admission for outbox, fulfillment, reconciliation, and
  projection commands that call protected Workstream actions.
- Do not create project roles, service identities, or authority fallbacks.

## Release proof

The final AUTH proof must show one ActorProfile holding separate submitter,
reviewer, and adjudicator grants; independent revocation in every direction;
unaffected admin authority; no administrative substitution for contributor
actions; no submit/review/adjudication capability from the wrong grant;
same-token revocation; service/human path isolation; exact cross-service denial;
and transaction-time revalidation.

This handoff changes no runtime and starts no downstream chunk.
