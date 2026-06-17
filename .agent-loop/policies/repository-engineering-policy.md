# Workstream Repository Engineering Policy

## Project Identity

- Project name: Workstream
- Project type: backend-first task evaluation and contribution infrastructure
- Backend: Python, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic schemas
- Frontend: React, Vite, TypeScript
- Record database: Postgres
- File storage: local filesystem only behind an R2/S3-compatible abstraction

## Setup Commands

```bash
docker compose up -d postgres

cd backend
python -m pip install -e ".[dev]"
alembic upgrade head
ruff check app tests scripts
docstr-coverage --config .docstr.yaml
pytest -q
```

## Core Boundaries

| Boundary | Owner | Rule |
|---|---|---|
| Auth | `backend/app/adapters/auth`, `backend/app/api/deps.py` | Verify external Flow tokens only; do not add Workstream login/password/session ownership. |
| Permissions | `backend/app/core/permissions.py`, module services | Role and object checks stay in services; routers map errors. |
| Project guide and policy context | `backend/app/modules/projects` | Guide and policy versions are explicit and locked before task/submission use. |
| Task lifecycle | `backend/app/modules/tasks` | State transitions are policy-driven and auditable. |
| Submission/checker lifecycle | `backend/app/modules/submissions`, `backend/app/modules/checkers` | Pre-submit blocking gates and post-submit checker records stay separate. |
| Persistence | `backend/app/db`, module models/repositories | Use async SQLAlchemy repositories and Alembic migrations. |
| CI/review gates | `.github/workflows`, `scripts/`, `.agent-loop/` | Gates may be strengthened; weakening requires explicit human approval. |

## Dependency Policy

- New production dependencies require explicit human approval.
- New dev dependencies require a clear reason and reviewer coverage when they affect CI, tests, lint, docs, or generated code.
- Do not replace locked stack choices without a new ADR and human approval.

## Agent Rules

- Keep PRs chunk-sized.
- Do not weaken CI, tests, docstring coverage, internal review evidence, or auth defaults.
- Do not use chat memory as the source of truth. Update docs, ADRs, templates, policies, or loop memory.
