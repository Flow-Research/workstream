# WS-ARCH-001-CP03A PR Trust Bundle

## Outcome

Add exactly one target-only service identity,
`workstream.compensation.adapter`, and real ACTORS/PROJECTS owner eligibility
for CP02 binding create/resume. Keep every adapter-binding action unavailable.

## Design

ACTORS owns the closed identity vocabulary and locks the exact active service
profile plus exact active service identity link. PROJECTS locks the exact
eligible project. CON continues consuming only injected public ports and owns
the rule that create/resume require both fences while suspend does not. AUTH
imports the public ACTORS vocabulary and treats a target-only identity without
a matrix row as permission-not-granted.

## Scope exclusions

No public route, evaluator, Finance Authority activation, service-action matrix
row for the adapter target, provider behavior, credential, ContributionPolicy,
award, fulfillment, callback, delivery, reconciliation, or reputation behavior
is added.

## Proof

Focused unit tests cover exact identities, concealed owner denials, matrix
separation, and kernel fail-closed behavior. Isolated PostgreSQL tests cover
migration acceptance/rejection and downgrade refusal, controlled provisioning
with zero grants, real project, profile, and identity-link fence retention for create/resume,
and denial before AUTH when ineligibility or revocation commits first. All new
tests belong to canonical semantic lanes. Repository boundary, structure,
stale-wording, link, chunk-state, and diff gates pass.

The full PostgreSQL suite and coverage run in GitHub Actions. No local full
suite is run on the user's slow machine.

## Human review focus

Confirm the new identity is a binding target only, has no service-action matrix
row, and cannot execute an action. Confirm ACTORS/PROJECTS retain their locks
through the caller-owned transaction and CP03B remains the only activation
successor. Only an authorized human may approve and merge this PR.
