# WS-ARCH-001-02A TASK Public Capability Manifest

## Public package

`backend/app/modules/tasks/api` exposes only dependency-safe immutable contracts:

- `TaskSubmissionContextRequest` — exact task, assignment, contributor, and
  nullable predecessor selectors;
- `TaskLockedProjectContextReferences` — the immutable project, guide,
  snapshot, effective-policy, and pre-submit-policy references copied onto the
  TASK row; these are selectors for the future PROJECT capability, not PROJECT
  policy bodies or canonical PROJECT facts;
- `SubmissionPredecessorFacts` — immediate immutable Submission ID and version;
- `TaskSubmissionContextFacts` — exact task/assignment/contributor status,
  initial-or-revision kind, predecessor, and locked reference selectors;
- `TaskSubmissionContextPort` — transaction-bound lock/reload capability;
- `TaskSubmissionContextKind` — closed `initial | revision` context alias;
- `TaskSubmissionContextStatus` — closed `in_progress | needs_revision` status
  alias;
- `TaskSubmissionContextFailure` — closed stable failure-code alias;
- `TaskSubmissionContextUnavailable` — stable bounded failure with
  `task_submission_context_invalid` or
  `task_submission_predecessor_changed`.

The public package imports no ORM model, repository, SQLAlchemy session,
PROJECT, CHECKER, ACTOR, ART, or mutable mapping.

## Owner-local implementation

`TaskRepository.lock_submission_context(...)` implements the structural port
inside TASKS. Its lock order is:

1. exact task;
2. exact assignment;
3. latest Submission for the task.

It validates active assignment ownership, assigned contributor, allowed task
state, complete locked reference selectors, the exact latest predecessor, and
the predecessor's contributor lineage.
No ACTOR, PROJECT, CHECKER, or ART row is read. An initial context requires no
existing Submission and a null predecessor selector. A revision context is
available only in `needs_revision` and requires the exact latest Submission ID,
version, and contributor; every crossed state fails closed.

## Boundary disposition

This chunk adds no cross-module edge and changes no live route, schema,
Submission persistence, authorization availability, or ART behavior. The
legacy mixed `tasks.pre_submit_context` path remains frozen until 02B and 02C
provide the PROJECT and CHECKER public capabilities; 02D then migrates ART
consumers and removes the relevant private TASK edges. Unrelated frozen TASK
debt is unchanged.

This evidence describes the implementation branch only. On merge, 02A becomes
complete and 02B becomes the next eligible implementation chunk; the global
initiative ledger must not claim that state before the human merge decision.

## Deterministic proof

- public API boundary validation rejects private re-exports;
- focused initial, revision, stale-predecessor, and immutable-contract tests;
- PostgreSQL-backed initial/revision state-matrix coverage, including missing,
  stale, crossed-state, and cross-contributor predecessor failures;
- a two-session PostgreSQL race proving concurrent context observation blocks
  behind the canonical TASK-first lock;
- 100 percent focused coverage for `app.modules.tasks.api`;
- protected-base module-boundary validation;
- Ruff, Markdown link, and diff checks.

The dependency-free focused suite passes locally. The PostgreSQL cases are
part of the required hosted Backend/Agent Gates because this worktree has no
`WORKSTREAM_TEST_DATABASE_URL`; the chunk verification command fails fast when
that required database URL is absent.
