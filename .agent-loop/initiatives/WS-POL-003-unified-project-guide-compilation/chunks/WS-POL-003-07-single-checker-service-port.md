# Chunk Contract: WS-POL-003-07 - Single Checker Service Port

Status: Proposed after 06. Risk: L1.

## Goal

Provide one internal typed checker service port with exactly two complete
phase commands:

- `evaluate_pre_submission(...)`, invoked once by artifact-flow orchestration
  while exact material is sealed in `ArtifactScratchManager` custody;
- `evaluate_post_submission(...)`, invoked once by artifact-flow orchestration
  after exact verified content is durably stored, bound, and attached to the
  Submission lineage.

Each command invokes the complete canonical phase executor and returns one
typed result. The pre command is a facade over ART-04B1-04B3's existing
effective-plan execution; it does not reimplement or rerun ART entries. The
post command invokes the durable CHECKER executor. Artifact-flow callers never
select or call individual platform/project checkers.

## Allowed files

Checker interfaces/service/composition, project policy plan adapters, typed ART
material/result interfaces only, focused checker/project tests, and WS-POL-003
docs.

## Not allowed

ART scratch/storage/provider/binding/lifecycle changes, public contributor
checker routes, caller-selected checker names, per-checker endpoints, dynamic
plugins, arbitrary code/network execution, or prepared handles in payloads.

## Acceptance

- The service exposes exactly one pre and one post command and no generic
  `run_checker(name, ...)` product boundary.
- Pre composes mandatory ART platform entries with exact task-locked project
  pre-submit entries through ART-04B1-04B3 and evaluates them once against one
  sealed scratch generation.
- Post composes durable defaults with exact task-locked project post-submit
  entries and evaluates them against one verified stored/bound content lineage.
- Both commands bind exact project/task/assignment, guide/policy, artifact,
  manifest, generation, attempt, action, service identity, and transaction
  facts; stale/replay/cross-phase/cross-resource calls fail closed.
- The port requires a deterministic attempt identity and idempotent replay
  semantics so later ART/XINT orchestration and bounded repair can converge;
  this chunk does not alter or claim those external call sites.
- ART's pre-submit attempt/result/evidence repository is the only pre writer;
  CHECKER's durable repository is the only post writer. The facade returns the
  canonical result/reference and cannot persist partial or duplicate member
  results.
- One bounded phase result contains every platform/project member with exact
  definition/version/policy trace; infrastructure failure is never contributor
  blame or a review decision.

## Verification and review

All-pairs phase/identity/resource denial, exact-once composition, no-individual-
dispatch reachability, timeout/cancellation, deterministic attempt replay,
scratch and stored-content contract parity, and 90% changed-subsystem coverage.
Required reviewers: all L1 tracks. Human focus: the port permits one complete
call per phase and cannot select individual checkers.
