# Chunk Contract: WS-ARCH-001-03A PROJECT Current Generation API

Status: non-executable planning skeleton after AUTH-12H; POL-08 cleanup remains
later. Risk: L1. Outcome: PROJECTS exposes immutable current approved unified
guide, its exact guide-bound ContributionPolicyVersion, setup, pre-submit and
post-submit identities/hashes through its public API.

Allowed: `backend/app/modules/projects/api/**`, the smallest PROJECTS-owned
repository/service extraction, focused PROJECT tests, boundary ledgers, and
this initiative's evidence/status. Not allowed: TASK/ART/CHECKER/REV behavior,
AUTH activation, ORM leakage, compatibility aliases, or another inference
path.

Reuse the existing `CanonicalJsonObject` and
`ProjectLockedPolicyContextPort`; extend their public vocabulary unless a
reviewed current-main delta proves that a new type is necessary. Do not create
a parallel canonical-JSON, hash, locked-policy, or current-generation surface.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

Acceptance: one transaction-bound port returns only canonical immutable facts;
guide activation has validated and bound one same-project published, complete,
binding-valid immutable ContributionPolicyVersion as
`ProjectGuide.contribution_policy_version_id`; stale, mixed-generation,
incomplete, unapproved or superseded chains deny;
all touched private edges shrink. Verify focused PROJECT tests, PostgreSQL
locking/race tests, boundary validators, Ruff and hosted coverage. Required
reviews: architecture, security, product/ops, QA, senior, reuse and test delta.

## Merge state

- Outcome on merge: `planned`
