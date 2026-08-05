# WS-QUAL-001-04P PR Trust Bundle

## Chunk

`WS-QUAL-001-04P` — Protected Mutation Dependency Authority.

## Goal

Establish a protected-main mutation-tool dependency authority before 04M so
untrusted PR-head code cannot select its own toolchain.

## Human-approved intent

The user explicitly instructed the orchestrator to start this prerequisite.
04M is not started by this PR.

## What changed

- Added a small source authority pinning `mutmut==3.7.0` and backend-aligned
  pytest, Coverage, and Packaging versions.
- Added the generated complete 20-package SHA-256 manifest.
- Updated QUAL sequencing and the 04M contract to consume only the protected
  base-revision manifest.

## Why it changed

Hashes verify downloaded bytes but do not make PR-selected packages trusted.
The approved package/version/hash set must exist on protected `main` before the
04M branch can use it.

## Design chosen

`scripts/mutation-requirements.in` is the human-reviewed source list;
`scripts/mutation-requirements.txt` is the complete generated install authority.
04M reads the protected base copy and installs with `pip --require-hashes`; it
cannot modify either file.

## Alternatives rejected

- Let 04M create its own hashed lock: PR code would still choose the packages.
- Add mutmut to production or ordinary backend dev dependencies: unnecessary
  coupling and lock churn.
- Prebuilt image now: more infrastructure than this bounded prerequisite needs.

## Scope control

Only the two authority files and QUAL planning/review records change. No
workflow, Backend runtime, test, lockfile, or coverage policy changes.

## Product behavior

None.

## Acceptance criteria proof

- Engine: `mutmut==3.7.0`.
- Complete closure: 20 exact pins, all SHA-256 hashed.
- Backend-aligned overlap: all nine shared packages match `backend/uv.lock`.
- Python 3.12 hash-checked dry run: passed.
- Python 3.11 compatible hashed wheel resolution: 20/20 passed.

## Tests/checks run

- Clean Python 3.12 `pip --dry-run --require-hashes`.
- Python 3.11 cross-platform `pip download --require-hashes`.
- Static exact-pin/hash/index validation.
- Markdown links and all stale-document scans.
- 10 lightweight Agent Gates.
- `git diff --check`.

## Test delta

No test changed, skipped, removed, or weakened.

## CI integrity

No workflow, lane, runner, coverage command, dependency installation path, or
threshold changed.

## Reviewer results

Security, CI integrity, reuse/dedup, and docs pass after aligning the sole
shared transitive mismatch. See `WS-QUAL-001-04P-internal-review-evidence.md`.

## External review

Three valid CodeRabbit findings were fixed and verified. See
`WS-QUAL-001-04P-external-review-response.md`. Agent Gates passed on the prior
head; exact rebased-head GitHub checks rerun after push.

## Remaining risks

04M must still prove mutmut behavior, target selection, result evidence, and
hosted runtime. This manifest does not authorize or execute mutation testing.

## Follow-up work

After this PR merges, 04M still requires a separate human instruction.

## Human review focus

Confirm package selection, exact hashes, backend version alignment, and the
protected-base consumption boundary.

## Human merge ownership

Only the user may approve and merge this PR.
