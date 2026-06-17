# AGENTS.md

This repository is for Workstream, Flow's task evaluation and contribution infrastructure.

## Core Definition

Workstream manages project guides, task queues, submission packets, automated checks, reviewer routing, evaluation sprints, revision loops, contribution records, payment status, and reputation signals.

Workstream is how Flow measures, certifies, and coordinates useful human-agent work.

## Working Rules

- Keep wording consistent with `README.md`, `docs/glossary.md`, and `docs/architecture_lockdown.md`.
- Treat this repository's engineering loop as a Codex-native zero-trust loop:
  `Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Memory Update -> Stop`.
- Keep the engineering loop separate from the Workstream product lifecycle. Workstream product review decisions remain `accept`, `needs_revision`, and `reject`; internal engineering reviewer findings are process evidence, not product decisions.
- Codex-discoverable repository skills live under `.agents/skills/`.
- Codex custom reviewer agents live under `.codex/agents/`.
- Durable engineering memory, initiative plans, chunk contracts, policies, evidence, and review logs live under `.agent-loop/`.
- Do not add Claude-specific files unless the user explicitly asks for cross-tool support.
- Do not use old names such as "task-production control plane" or "Garden roadmap".
- Spreadsheet exports live locally under ignored `sheets/`; do not commit them.
- Do not add extra sheets to local `sheets/workstream_roadmap.xlsx`; the workbook must contain one sheet only: `WorkStream RoadMap`.
- Treat local `sheets/workstream_roadmap.xlsx` as the primary spreadsheet export. The CSV is fallback only.
- If updating the roadmap, update both local XLSX and CSV exports.
- Do not import XLSX into Google Sheets with "replace spreadsheet"; use a temporary sheet and copy only the roadmap tab.
- Prefer evidence-backed docs over vague product claims.
- For workflow states, persisted tokens, API enum values, roles, and lifecycle names, prefer subsystem- or actor-specific names over vague labels. If the naming has product or security impact and the user is unavailable, run the required internal reviewer tracks before locking it.
- Keep v0.1 focused on project guide -> task -> submission -> checks -> review -> revision -> contribution/payment/reputation records.
- Review decision stored values are only accept, needs_revision, or reject.
- Frontend is locked as React + Vite + TypeScript.
- Backend API is locked as Python with FastAPI.
- ORM, migrations, and API schemas are locked as SQLAlchemy 2.x async + Alembic + Pydantic schemas.
- Workstream verifies external Flow authentication tokens; do not add Workstream-owned login, signup, password reset, password storage, or primary auth sessions.
- Week 1 implementation is backend-first; do not start frontend work until backend contracts and lifecycle guards are stable.
- Execution is async-first; do not document synchronous-first checkers or jobs.
- FastAPI background tasks are acceptable for simple local v0.1 jobs; use Celery or equivalent durable workers when retries, scheduling, isolation, or distributed execution are needed.
- Postgres is the record database.
- Local filesystem storage is acceptable only behind an object-storage abstraction compatible with R2/S3-style storage.
- Do not expand into blockchain settlement, marketplace, external source adapters, automated routing, or agent workspace until the internal loop is proven.
- Every non-trivial task starts with the smallest applicable loop artifact: an initiative plan for large work, or a chunk contract for bounded work.
- Do not implement a chunk until its allowed files, not-allowed changes, acceptance criteria, risk class, verification commands, and required reviewers are explicit.
- Do not begin the next chunk automatically after finishing the current chunk.
- Every implementation or specification chunk must receive internal sub-agent review before external PR review is treated as sufficient.
- Required internal reviewer tracks are senior engineering, QA/test, security/auth, and product/ops unless the chunk is explicitly unrelated to that track.
- For architecture, CI/workflow, docs, or reuse-sensitive chunks, add the matching reviewer track from `.codex/agents/`.
- Do not report a chunk complete while reviewer agents are still running. Wait for them, address valid findings, and close any open sub-agent sessions.
- CodeRabbit, CI, and GitHub review are external checks. They supplement internal reviewer agents; they do not replace them.
- Do not open, push, or ask for review on a PR until required internal reviewer tracks have run for the chunk, all valid findings are addressed or documented, and no sub-agent sessions remain open.
- Do not merge a PR unless the user explicitly approves that specific PR for merge.

## Done Criteria

Before reporting completion:

- run a stale wording scan
- check markdown links
- verify the local XLSX has one sheet only when local sheet exports are present
- verify the current Workstream definition appears in README and local sheet exports when local sheet exports are present
- update related docs/templates and local sheet exports together when the roadmap changes
- run required internal sub-agent reviewers for the chunk and resolve or explicitly document every valid finding
- confirm no sub-agent sessions remain open
- update `.agent-loop/` initiative status, review log, and memory when the chunk materially changes the engineering process
