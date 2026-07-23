# Workstream Repository Engineering Policy

## Project Identity

- Project name: Workstream
- Project type: backend-first task evaluation and contribution infrastructure
- Backend: Python, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic schemas
- Frontend: React, Vite, TypeScript
- Record database: Postgres
- File storage: AWS S3 in v0.1 production behind the provider-neutral artifact
  abstraction; MinIO proves the S3 protocol in local/CI, LocalStorage is
  development-only, and R2 plus Flow Node are deferred

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
| External authentication | `backend/app/adapters/auth`, `backend/app/api/deps/auth.py` | Verify external Flow tokens only; do not add Workstream login/password/session ownership or product roles to verified-token types. |
| Actors | `backend/app/modules/actors` | Own canonical ActorProfile and ActorIdentityLink persistence/resolution. |
| Authorization | `backend/app/modules/authorization` | Own grants, permission registry/evaluation, idempotency, invalidation, and authority decisions; routers map stable errors. |
| Project guide and policy context | `backend/app/modules/projects` | Guide and policy versions are explicit and locked before task/submission use. |
| Task lifecycle | `backend/app/modules/tasks` | State transitions are policy-driven and auditable. |
| Submission/checker lifecycle | `backend/app/modules/submissions`, `backend/app/modules/checkers` | Pre-submit blocking gates and post-submit checker records stay separate. |
| Persistence | `backend/app/db`, module models/repositories | Use async SQLAlchemy repositories and Alembic migrations. |
| CI/review gates | `.github/workflows`, `scripts/`, `.agent-loop/` | Gates may be strengthened; weakening requires explicit human approval. |
| Generated merge memory | `automation/loop-memory` | Trusted `main` automation owns a closed signed tree containing canonical state, ledger, manifest, loop/queue views, and compact initiative projections. Humans and agents do not edit it manually or trust isolated files without manifest/signature verification. Merge projections remain stopped/next-only until signed start events exist. |
| Explicit engineering starts | `.github/workflows/loop-memory-start.yml` | An authenticated dispatcher whose current GitHub repository permission meets `.agent-loop/policies/loop-memory-start-authorities.json` on trusted `main` may dispatch a signed start for a declared successor or exact reviewed contract; the orchestrator may dispatch after an explicit user instruction, but conversation is not canonical evidence. Cancellation retains a protected-environment reviewer distinct from the dispatcher. No automatic start is valid. |

Explicit starts are initiative-local: each initiative may have at most one
active planning or implementation chunk, while distinct initiatives may be
active concurrently. Local worktrees are execution isolation, not authority.

The sole first-contract admission is a planning-intake merge for an initiative
absent from signed history. It is a closed additive planning tree with canonical
`<initiative>-PLAN` identity, required review/check evidence, one reviewed
same-initiative implementation successor, and explicit-start true. It records a
trusted signed merge but no active chunk. It cannot change product, code,
workflows, scripts, policy, existing initiatives, or generated memory. It is not
an implementation-start substitute.

## Dependency Policy

- New production dependencies require explicit human approval.
- New dev dependencies require a clear reason and reviewer coverage when they affect CI, tests, lint, docs, or generated code.
- Do not replace locked stack choices without a new ADR and human approval.

## Agent Rules

- Follow the repository contribution entry path in `CONTRIBUTING.md`; it applies
  equally to humans and agents and does not change product Contributor authority.
- Keep PRs chunk-sized.
- Do not weaken CI, tests, docstring coverage, internal review evidence, or auth defaults.
- Do not use chat memory as the source of truth. Update docs, ADRs, templates, policies, or loop memory.
- Review and approve an implementation PR once. After merge, rely on the canonical automation branch; do not create a second PR or repeat reviewer fanout solely to restate merge metadata.
- After the 04B cutover, an implementation merge without an active signed start
  fails unless its exact identity is covered by a reviewed one-use root recovery.
  The only permanent no-predecessor admission is the closed first-planning merge
  above, which always remains stopped.
