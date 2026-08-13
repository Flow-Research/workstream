# Chunk Contract: WS-CON-001-06 - Planned Retirement Of Review-Claim Policy Lookup

## Goal

Plan retirement of the former claim-time reviewer policy lookup; it is not executable.
ReviewLease inherits the exact ContributionPolicyVersion already locked to the
task and carried through assignment, Submission and canonical `allow_review`.
CON performs no policy selection during review claim.

## Replacement contract

- `WS-CON-001-05A` owns the one upstream guide-activation validation port and
  persistence contract.
- `WS-ARCH-001-03B` owns task readiness and assignment inheritance.
- canonical `allow_review` preserves the task/assignment version lineage.
- REV claim verifies that lineage and writes the same identifier to
  `ReviewLease.reviewer_contribution_policy_version_id` in the REV-owned
  transaction.
- The same immutable version supplies distinct `accepted_submission` and
  `completed_review` rules. Publishing a newer version affects only newly
  prepared tasks.

No runtime files, migration, port, action, or merge intent may be created from
this superseded contract.

## Merge state

- Outcome on merge: `planned`
