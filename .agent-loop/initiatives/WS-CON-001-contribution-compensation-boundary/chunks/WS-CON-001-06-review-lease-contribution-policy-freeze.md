# Chunk Contract: WS-CON-001-06 - Planned Retirement Of Review-Claim Policy Lookup

## Goal

Plan retirement of the former claim-time reviewer policy lookup; it is not executable.
ReviewLease copies the exact `Submission.contribution_policy_version_id`
carried through canonical `allow_review`. Task and assignment values are only
upstream equality/provenance checks. CON performs no policy selection during
review claim.

## Replacement contract

- `WS-CON-001-05A` owns the one upstream guide-activation validation port and
  persistence contract.
- `WS-ARCH-001-03B` owns task readiness and assignment inheritance.
- Submission creation stamps the assignment's attempt version and canonical
  `allow_review` preserves that immutable Submission lineage.
- REV claim copies the Submission identifier, verifies upstream lineage for
  equality, and writes it to
  `ReviewLease.reviewer_contribution_policy_version_id` in the REV-owned
  transaction.
- The same immutable version supplies distinct `accepted_submission` and
  `completed_review` rules. Publishing a newer version affects only newly
  prepared tasks.

No runtime files, migration, port, action, or merge intent may be created from
this superseded contract.

## Merge state

- Outcome on merge: `planned`
