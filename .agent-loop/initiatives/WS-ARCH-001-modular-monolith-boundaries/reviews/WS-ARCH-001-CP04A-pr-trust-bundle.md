# WS-ARCH-001-CP04A Contract-Correction Trust Bundle

## Intent and scope

Make the CP04A executable contract safe to implement under the repository's
atomic semantic-review protocol. This PR changes planning and state projection
documents only. It does not implement or activate ContributionPolicy behavior.

## Design corrections

- COMPENSATION constructs its public adapter-binding lookup through its
  same-owner adapter root.
- `CompensationInstrumentType` has one explicit future public home:
  `app.modules.compensation.api.instruments`.
- Every material behavior, failure, forbidden effect, structural constraint,
  and coverage requirement has an independent owner/proof/custody row.
- Migration custody names the exact current successor while prohibiting a
  compatibility branch if current main changes.

## Runtime impact

None. CP04A remains planned, route-unreachable, and unimplemented. All five
ContributionPolicy AUTH actions remain planned and unavailable.

## Verification custody

- Local deterministic gates own diff, Markdown, stale wording, state
  projection, atomic chunk-state, and current AUTH registration proof.
- Future focused tests own each named CP04A behavior. One coverage collection
  followed by separate per-surface reports owns the at-least-90-percent
  changed-application-surface requirement; schema tests own Alembic/metadata
  parity.
- Hosted PostgreSQL lanes own concurrency and direct database negative proof.
- The hosted aggregate independently owns the unchanged repository-wide
  78-percent coverage baseline.

## Review status

The original `965ef61e` review is historical after external corrections.
Architecture, security, product/operations, QA, test-delta, and CI-integrity
review all passed on corrective code/content head `77f615f8`. This trust-bundle
metadata update requires a final exact-head closure replay before merge
readiness is claimed. CodeRabbit skip or rate limiting is never represented as
approval.

## Human review focus

Confirm the dedicated public enum home, absence of private composition paths,
atomic criterion-to-proof rows, separate focused/global coverage custody, and
continued absence of runtime activation.
