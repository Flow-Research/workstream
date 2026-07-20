# DISCOVERY: WS-ENG-001

## Current Repo State

- `AGENTS.md` already defines Workstream-specific rules, stack locks, internal
  reviewer requirements, and done criteria.
- `scripts/check_internal_review_evidence.py` already blocks PRs that touch
  engineering-loop, process, and implementation files without
  `docs/internal_reviews/*.md`.
- `.github/workflows/backend.yml` already runs the internal review evidence gate
  before backend install, lint, docstring coverage, tests, and Week 1 real API e2e.
- `.github/workflows/agent-gates.yml` is added as a process-only PR gate so loop,
  docs, and Codex-surface changes are checked even when backend CI is not the
  main changed surface.
- GitHub Actions are already pinned to commit SHAs for checkout and setup-python.
- `docs/operations_subagent_review_protocol.md` defines required reviewer
  perspectives, but it predates the Codex-native `.agents/skills` and
  `.codex/agents` structure.

## AZTLE Kit Findings

- The kit contains a strong loop model:
  `Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Review -> PR -> Human Checkpoint -> Memory Update -> Stop`.
- The kit includes both `.agent-loop/skills` and `.agents/skills`; Codex's
  documented repo skill path is `.agents/skills`.
- The kit includes `.codex/agents/*.toml` reviewer definitions that map well to
  Codex custom agents.
- The kit includes Claude-specific files that are not needed for Workstream now.
- The kit lacks a first-class Product/Ops reviewer, which Workstream requires.

## Existing Constraints To Preserve

- Backend remains Python/FastAPI.
- Frontend remains React/Vite/TypeScript.
- Postgres remains the record database.
- Workstream verifies external Flow auth and does not own primary auth sessions.
- Review decision stored values remain `accept`, `needs_revision`, and `reject`.
- Internal sub-agent review remains mandatory before a PR is treated as ready.
- CodeRabbit and CI supplement internal reviewers; they do not replace them.

## Risks

- Copying the kit blindly would introduce generic wording and non-Workstream
  assumptions.
- Duplicating skills in both `.agent-loop/skills` and `.agents/skills` would
  create drift.
- Adding CI without pinned actions would regress prior CI supply-chain hardening.
- Weak PR automation could accidentally imply Codex may merge without approval.

## 2026-07-20 Loop Projection Discovery

### Observations

- `.github/workflows/loop-memory.yml` stages only
  `.agent-loop/{STATE.json,LOOP_STATE.md,MERGE_LOG.jsonl,STATE.sig}`.
- `scripts/update_post_merge_memory.py` defines those same four paths and
  renders only `LOOP_STATE.md`.
- `scripts/check_loop_memory_state.py --state-root` validates `STATE.json`,
  `LOOP_STATE.md`, and `MERGE_LOG.jsonl`; the workflow verifies their signature.
  It does not validate `WORK_QUEUE.md` or initiative `STATUS.md` in that mode.
- Authored queue/status scanning occurs only without `--state-root`; authored
  checks and generated-state validation are distinct modes.
- Loop Memory run `29721110272` succeeded for AUTH-09E PR #157. Generated commit
  `a5b9bad3` correctly recorded 09E completion but did not touch the stale queue
  or AUTH status copies.

### Tests and gaps

- Existing tests cover intent validation, signed replay, hostile path types,
  corruption, escaping, workflow isolation, and protected-main freshness.
- No test requires a closed automation-branch file manifest.
- No projection reduces `MERGE_LOG.jsonl` to latest state per initiative.
- No generated queue/status is compared byte-for-byte with a renderer.
- No authenticated explicit-start event exists; merge output always reports no
  active planning or implementation chunk.

### Dependencies, risks, and unknowns

GitHub PR/check metadata, protected `main`, repository replay, the Actions-only
Ed25519 key, and merge-intent schema v2 are existing inputs. A single global
last-merge record cannot render all initiatives; the ledger must be reduced per
initiative. The automation branch currently has 626 tracked legacy files, so an
enumerated deletion list would be brittle and an in-place recursive cleanup
would be unsafe. A fresh deterministic Git tree can instead be built from an
empty temporary index and an empty generated-output directory, committed as a
normal child of the authenticated state-branch tip, and pushed fast-forward.
This omits legacy paths without traversing or deleting their worktree objects.
04B defers the start-event schema, actor/environment protection, and mandatory
cancel/correct semantics; none is required for 04A.
