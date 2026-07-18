# PR Trust Bundle: WS-ENG-001-02

## Chunk

`WS-ENG-001-02` - Automated Post-Merge Memory

Merge intent: `.agent-loop/merge-intents/WS-ENG-001-02.json`

## Goal

Remove the second manual post-merge memory PR and repeated reviewer fanout while
preserving protected-main approval and fail-closed lifecycle authority.

## Human-Approved Intent

The user explicitly requested this workflow repair after observing that normal
implementation PR review was followed by hours of redundant post-merge memory
review. The approved boundary is the chunk contract in this initiative.

## What Changed

- Added trusted-main automation that writes only signed generated state to
  `automation/loop-memory`.
- Added immutable reviewed-head merge intents, first-parent reconciliation,
  deterministic rendering, an append-only hash-chained ledger, signing,
  freshness verification, and hostile-state rebuild.
- Updated Agent Gates, PR templates, policy, memory skill, and operations docs.
- Strengthened live main and generated-branch protections.

## Why It Changed

The prior loop treated deterministic bookkeeping as another engineering chunk,
causing a second PR and repeated internal review after the actual change had
already been reviewed and merged.

## Design Chosen

Implementation PRs retain normal human and internal review. After merge, a
trusted default-branch workflow derives bounded state from GitHub merge facts
and an immutable intent file, authenticates generated files, and appends them to
an isolated branch. No bot PR, approval, merge, or write to `main` exists.

## Alternatives Rejected

- Direct writes to `main`: rejected because they bypass the human checkpoint.
- Mutable PR-body markers: rejected because authority could change after review.
- `workflow_dispatch`: rejected because callers can select branch workflow code.
- Exclusive deploy-key writer: unavailable because organization policy disables
  deploy keys; signed state plus protected-main freshness is used instead.
- Another post-merge PR: rejected because it recreates the process defect.

## Scope Control

Only the chunk's allowed engineering-loop, workflow, script, test, template,
policy, signing-public-key, and documentation paths changed. No backend,
frontend, database, authentication runtime, authorization runtime, artifact
runtime, or coverage threshold changed.

## Product Behavior

- [x] No Workstream product behavior changed.

## Acceptance Criteria Proof

- [x] Empty and established state reconcile every first-parent commit.
- [x] Replay is idempotent and older commits cannot replace current state.
- [x] Lifecycle intent is immutable and bound to the reviewed final head.
- [x] Generated JSON, Markdown, ledger, and signature agree exactly.
- [x] Invalid, stale, malformed, symlinked, or directory-backed state rebuilds.
- [x] Workflow code is trusted-main only and pushes only the generated branch.
- [x] Existing implementation review, test, coverage, and merge gates remain.

## Tests And Checks

The plain runner and pytest each pass 63 tests. Branch coverage is 90.79 percent
for the updater and 94.41 percent for the independent checker. Compilation,
YAML parsing, stale scans, Markdown links, loop state, and diff checks pass.

## Test Delta

Behavior tests cover immutable metadata, pagination, GitHub payload failures,
check reruns, real no-ff bootstrap history, idempotency, direct successors,
full-ledger mutation/deletion/schema corruption, exact render drift, signed
successors, stale signed replay, invalid UTF-8/nested data, hostile directories,
symlinks, CLI behavior, and workflow write confinement. No tests were removed,
skipped, or weakened.

## CI Integrity

- [x] Coverage thresholds unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence disabled

## External Review

External review response:
`.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/reviews/WS-ENG-001-02-external-review-response.md`

GitHub checks and CodeRabbit are pending completion on PR #122.

## Reviewer Results

Reviewed code SHA: `501890305167223fd50d42484adc75c6fae99bd2`

Reviewed at: `2026-07-15T00:17:05Z`

All required senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test-delta tracks passed after
valid findings were repaired.

## Remaining Risks

The first live Loop Memory run is pending merge. Signing-key rotation requires a
reviewed public-key and repository-secret update. GitHub Backend supplies the
full repository test evidence because no backend runtime changed locally.

## Human Review Focus

- Confirm `main` is never a workflow push target.
- Confirm existing branch state is authenticated before `current_sha` is used.
- Confirm final verification binds the protected-main target.
- Confirm malformed state is rebuilt only at fixed generated paths.
- Confirm the generated-output review exception cannot cover implementation,
  workflow, generator, policy, or hand-edited memory changes.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] I explicitly approve this specific PR for merge.
