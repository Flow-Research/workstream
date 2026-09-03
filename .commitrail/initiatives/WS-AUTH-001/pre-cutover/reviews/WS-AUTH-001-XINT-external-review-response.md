# WS-AUTH-001-XINT External Review Response

Reviewed repair SHA: `c4c4f2e63ab47c204b394e1825a54987765581cb`
Reviewed at: `2026-07-17T06:08:00Z`

## GitHub Actions

Agent Gates runs `29557932996` and `29558017415` failed on the earlier PR head
because the merge intent named AUTH-09A even though trusted `main` contains no
exact AUTH-09A chunk contract. Repair `223a15b` changed the schema-v2 successor
to null, leaving the next runtime priority at the human work queue. Replacement
Agent Gates run `29558216518` passed all 80 gate tests.

Backend runs `29557932993` and `29558216526` both passed. The latter passed the
internal-review evidence gate, lint, docstring coverage, isolated database
runner, repository-wide coverage suite, all focused coverage ratchets, and the
real API contract drill. This external repair changes no backend, workflow,
dependency, test, or coverage configuration.

## CodeRabbit Findings

| Finding | Disposition | Evidence |
|---|---|---|
| Scope service-matrix proof to service actions | Fixed | AUTH-16 now requires exact approved membership for fixed-service actions and proves human-only actions have no membership. |
| Bind PREP to actor/request identity | Fixed | `PreparedAuthorizationHandle` matches session, ActionId, actor-ref kind/ref, idempotency key, and canonical request digest before feature mutation; substitution/replay tests are mandatory. |
| Replace the existing Pydantic `AuthorityClaimHandle` in runtime | Not applied | The comment conflated the current internal idempotency-reservation proof with the future PREP capability. The plan now names a distinct non-Pydantic `PreparedAuthorizationHandle`; runtime remains outside this planning-only PR. |
| Allocate blocked cross-initiative migration heads only when executable | Fixed | The plan forbids reservation or allocation while blocked and allocates from trusted main only when the complete feature contract becomes executable. |
| Clarify independent exact-project grant wording | Fixed | Plan and AUTH-10 goal now state independent contributor grants scoped to the exact project. |
| Prevent PR #131 from becoming a Markdown heading | Fixed | STATUS keeps `PR #131` in prose on the preceding line. |
| Name AUTH-10 clean-cut parity sources | Fixed | STATUS names typed ProjectRole, audit/idempotency contracts, and the PostgreSQL validators recreated by migration 0022. |
| Prevent PR #139 from becoming a Markdown heading | Fixed | WORK_QUEUE keeps `PR #139` in prose on the preceding line. |
| Align migration 0024 refusal semantics | Fixed | The specification and AUTH-10 contract share the normative sentence requiring upgrade refusal and prohibiting conversion or deletion of obsolete evidence. |

## Review Result

Exact-head senior engineering, architecture, reuse/dedup, QA/test, product/ops,
security/auth, CI integrity, and docs review passed. Reviewers agreed that
changing the current runtime `AuthorityClaimHandle` would be scope creep and a
contract conflation, not a valid repair for this planning PR.

## CodeRabbit Pre-Merge Warning

The PR-description warning was valid and is addressed. PR #140 now contains the
repository trust-bundle sections, and CodeRabbit's current Description check
passes. Replacement checks remain required after the repair head is pushed.

## Remaining Gate

Internal evidence must be rebound to the final reviewed response head, then
GitHub Actions and CodeRabbit must rerun. Explicit human approval remains the
only merge authority; this response starts no AUTH runtime chunk.
