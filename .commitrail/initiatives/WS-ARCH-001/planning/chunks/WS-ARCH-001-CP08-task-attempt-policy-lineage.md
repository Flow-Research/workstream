# Chunk Contract: WS-ARCH-001-CP08 — Initial Attempt Policy Lineage

Status: planned after ARCH-03A. Risk: L1.

## Reconciled boundary

The user-approved [ARCH-03A reconciliation](../../WS-ARCH-001-03A.md) replaces
the former schema-only split. The old contract required lineage before claim
and Submission while prohibiting every writer of that lineage. ARCH-03A first
completes the existing PROJECTS active/frozen context port; CP08 then changes
schema and the minimal existing TASK writers together.

CP08 owns `WorkstreamTask.locked_contribution_policy_version_id`,
`TaskAssignment.submitter_contribution_policy_version_id`, and
`Submission.contribution_policy_version_id`, their immutable public facts,
relational constraints, and the canonical screening/claim/Submission copy paths.
It reuses `TaskService` screening/context locking, `AuthorizedTaskCommands.claim`,
`TaskSubmissionContextPort`, and `TaskSubmissionCreationService/build_submission`.
Replace affected obsolete private policy/payment context paths with the existing
PROJECTS port; no parallel command or compatibility branch.

Screening takes the complete active guide context once. This PROJECTS read
supplies exact custody, not readiness authority. Before initial lineage or a
screening/ready state is written, TASK must validate that installed CHECKERS
capabilities can execute both saved plans. Reuse
`EffectivePreSubmissionPlanningPort.compile_effective_plan` for pre-submit and
CHECKERS public `CompiledPostSubmitPolicy.validate_catalogue` for post-submit,
using the installed catalogue built from registered implementations at the
composition root. No new readiness workflow or parallel parser is needed. This validation performs no
checker execution or provider call. Fail before lineage, status, assignment or
audit writes. Keep historical reads independent of current availability; do not
make their success sufficient authority to advance new work.

Ready/claim validate the exact frozen context, not a current CON selector. Claim copies the task stamp;
Submission copies the exact active assignment stamp. Ordinary claim/Submission
perform no CON lookup. Keep authorization and atomic operation ownership intact.
ARCH-03B retains queues, invalidation and broader task projections; ARCH-03C
retains their later exact authorization/public cutover.

## Persistence and retained evidence

A draft task may lack a complete lock; new claimable tasks, assignments and
Submissions may not. Use same-project policy and stable Task/Assignment/contributor
keys. Bind new Submission stamps to exact assignment values at creation and make
them immutable. Do not FK a frozen Submission to a mutable current assignment
policy value, or force closed assignments to follow later task context.

Inventory the actual migration baseline. A current policy or present-day guide
binding is not proof of an old attempt. Any derivation needs exact immutable
original locked-context and CP07 receipt/temporal custody; otherwise refuse the
upgrade without modifying or deleting retained evidence. Do not add nullable
execution paths to keep incomplete earlier development code operational.

Human `needs_revision` remains the only future complete-context rebase boundary.
Its actual revision-preparation owner must replace existing Submission-to-mutable-
Task context FKs and supply authority/audit proof. CP08 may test only narrow
policy-selector schema capability while retaining prior Submission/closed
Assignment stamps; this is not proof of a complete authorized guide rebase.

## Verification and ownership

Before implementation enumerate exact files, constraints, migration head,
retained-data handling and affected consumers in the combined CP08 record.
Prove real screening/claim/Submission copy paths; missing/foreign/mismatched
lineage rejection; no CON lookup at claim/Submission; immutable prior evidence;
caller rollback; concurrency and migration preservation/refusal. Prove that a
catalogue rollout leaves frozen PROJECTS reads intact while screening/ready
refuses new work atomically for unavailable pre-submit or post-submit capabilities. Account for
Submission's current staged flush-before-artifact-linkage transaction when
designing immediate versus deferred constraints. Use a discriminating faulty
stamp mutation, not merely invalid fixtures rejected by earlier guards.

Required reviews: architecture/reuse, security, QA/test-delta, product/operations
and CI-integrity for migration/test registration. No new checker execution,
acceptance, compensation fulfillment, or revision operation belongs here.
