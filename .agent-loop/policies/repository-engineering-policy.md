# Workstream Repository Engineering Policy

## Project Identity

- Backend: Python, FastAPI, SQLAlchemy 2.x async, Alembic, and Pydantic.
- Frontend: React, Vite, and TypeScript.
- Record database: PostgreSQL.
- Hosted artifact storage: AWS S3 behind `ArtifactStore`; MinIO proves the
  protocol locally and in CI.

## Contribution Authority

GitHub repository permissions and branch protection govern contribution
authority. Plans, contracts, review evidence, and `.agent-loop/` records
preserve engineering context and rationale.

## Engineering Loop

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

- Keep changes small and explain scope and non-goals.
- Use a plan and chunk contract when complexity or risk warrants them.
- Run relevant tests, lint, type checks, and coverage checks.
- Use internal reviewers for high-risk security, authorization, payment,
  architecture, workflow, or product-lifecycle changes.
- Different initiatives may proceed concurrently.
- Explicit human approval is required before merge.

## Core Boundaries

| Boundary | Owner | Rule |
|---|---|---|
| External authentication | `backend/app/adapters/auth`, `backend/app/api/deps/auth.py` | Verify external Flow tokens only; do not add Workstream-owned passwords or primary sessions. |
| Actors | `backend/app/modules/actors` | Own canonical actor profiles and identity links. |
| Authorization | `backend/app/modules/authorization` | Own grants, permissions, evaluation, invalidation, and authority decisions. |
| Project guides | `backend/app/modules/projects` | Guide and policy versions are explicit and locked before downstream use. |
| Task lifecycle | `backend/app/modules/tasks` | State transitions are policy-driven and auditable. |
| Submission/checker lifecycle | `backend/app/modules/submissions`, `backend/app/modules/checkers` | Pre-submit gates and post-submit checker records remain separate. |
| Persistence | `backend/app/db`, module repositories | Use async SQLAlchemy and Alembic migrations. |
| CI | `.github/workflows` | CI validates code quality and tests; it does not grant permission to contribute. |

## Dependency Policy

- Production dependencies require explicit human approval.
- Development dependencies require a clear reason.
- Do not replace locked stack choices without an ADR and human approval.
