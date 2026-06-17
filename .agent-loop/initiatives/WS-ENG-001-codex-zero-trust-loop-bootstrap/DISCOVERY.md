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
