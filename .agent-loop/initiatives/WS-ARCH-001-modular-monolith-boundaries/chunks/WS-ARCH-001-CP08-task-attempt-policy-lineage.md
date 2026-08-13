# Chunk Contract: WS-ARCH-001-CP08 — Task Attempt Policy Lineage Foundation

Status: proposed non-executable skeleton after CP07. Risk: L1.

TASKS adds its public immutable facts and persistence constraints for
`WorkstreamTask.locked_contribution_policy_version_id`,
`TaskAssignment.submitter_contribution_policy_version_id`, and
`Submission.contribution_policy_version_id`. It adds no readiness, claim,
assignment-creation, Submission-creation, or revision command behavior.

ARCH-03B remains the sole behavior owner: readiness writes the Task lock, claim
copies it to TaskAssignment, and Submission creation stamps the assignment's
attempt version. Ordinary claim performs no CON lookup. ReviewLease later
copies only the Submission stamp. Human `needs_revision` remains the sole
controlled same-Task/TaskAssignment rebase boundary for the next attempt.

This chunk owns only TASK aggregate schema, repository persistence, immutable
public facts, and constraint tests;
it imports no PROJECTS, CON, AUTH, ART, CHECKERS, or REV internals.

## Merge state

- Outcome on merge: `planned`
