# WS-AUTH-001-11C2 External Review Response

## Comments addressed

- Centralized the active-guide administrative role allowlist so kernel
  enforcement and actor-context projection cannot drift.
- Required `guide_status == "active"` in the strict effective-policy resource
  context itself, in addition to the composer's active-guide selection.
- Extracted the common locked effective-policy chain predicate used by the
  standalone policy reads and active-guide composition.
- Removed the unused by-id guide-source snapshot lock helper; the active path
  continues to lock the latest exact snapshot and its ordered items.
- Extracted the response fields shared by lifecycle activation and the
  non-compensation active-guide administrative projection.

## Comments deferred

None. All five CodeRabbit nitpicks were valid, in scope, and addressed.

## Human decisions needed

None. Human merge approval remains required for PR #221.

## Commands rerun

- Ruff over the authorization and project modules plus focused tests.
- Focused 11C2 context, composer, canonical-readiness, and projection tests.
- Markdown links, stale wording, stale authorization docs, lightweight gates,
  and `git diff --check`.
- Hosted Backend and Agent Gates are required again on the final repair head.

## Remaining risks

- No known CodeRabbit finding remains. The final head must repeat hosted
  semantic lanes, API E2E, repository coverage, authorization coverage,
  project-composer coverage, exact-tree custody, and external review.
