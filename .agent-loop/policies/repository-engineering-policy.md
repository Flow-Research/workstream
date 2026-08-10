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
| Projects | `backend/app/modules/projects` | Own projects, Project Guides, guide compilation, locked project policies, and setup generations. |
| Tasks and Submissions | `backend/app/modules/tasks` | Own tasks, assignments, claims, immutable Submissions, predecessor chains, and their auditable lifecycle. A revision is another immutable Submission. |
| Artifacts | `backend/app/modules/artifacts` | Own byte identity, archive safety, manifests, storage, verification, admissions, bindings, and controlled materialization. |
| Checkers | `backend/app/modules/checkers` | Own checker runs, results, and blocking outcomes; pre-submit and post-submit phases remain distinct. |
| Reviews | `backend/app/modules/reviews` | Own review queue and lease, exact packet reference, `accept|needs_revision|reject`, note/findings, and FinalAcceptance source state on accept only. |
| Contributions | `backend/app/modules/contributions` | Own immutable reviewer `completed_review` and submitter `accepted_submission` ContributionRecords and their exact provenance. |
| Compensation | `backend/app/modules/compensation` | Own conditional award and fulfillment status without redefining contribution truth. |
| Audit | `backend/app/modules/audit` | Own append-only audit evidence. |
| Outbox | `backend/app/modules/outbox` | Own reliable internal/domain-event delivery. |
| API controls | `backend/app/modules/api_controls` | Own API rate and operational controls, not product lifecycle decisions. |
| Persistence | `backend/app/db`, module repositories | Use async SQLAlchemy and Alembic migrations. |
| CI | `.github/workflows` | CI validates code quality and tests; it does not grant permission to contribute. |

Cross-module runtime imports use only the target module's typed `api` package.
Public APIs expose immutable facts, commands/results, stable errors, opaque
capabilities, and Protocol ports—not ORM models, repositories, sessions, or
concrete services. The application composition root alone wires concrete
cross-module implementations.

The canonical registry and temporary exact private-edge recovery rules live in
`architecture-boundaries.md`. CI rejects unknown modules, new or expanded
private edges, public API private leaks, cyclic public dependencies, and any
divergence from the sole WS-AUTH-003 AUTH ledger.

## Dependency Policy

- Production dependencies require explicit human approval.
- Development dependencies require a clear reason.
- Do not replace locked stack choices without an ADR and human approval.
