# Current Workstream v0.1 Status

This is the capability ledger for current v0.1 development. It records what is
implemented on `main`, what is being integrated, and what remains before the
v0.1 lifecycle is proven. It intentionally contains no delivery calendar.

Implementation claims must be supported by code, migrations, tests, and merged
history. A plan, contract, draft pull request, or historical specification is
not evidence that behavior is live.

## v0.1 Release Boundary

The target remains:

```text
Project Guide
-> Task
-> Submission Packet
-> Automated Checks
-> Human Review
-> Revision when required
-> Contribution Records
-> Conditional Compensation Award / Fulfillment
-> Reputation Signals
```

The release bar is one secured, observable, end-to-end lifecycle using the
locked backend and storage architecture. Marketplace expansion, blockchain
settlement, external source adapters, automated routing, and agent workspaces
remain outside v0.1.

## Implemented On `main`

### Platform foundation

- FastAPI backend, SQLAlchemy async persistence, Alembic migrations, and
  PostgreSQL record storage.
- Async checker and project-setup execution with Celery and Redis where durable
  retries and isolation are required.
- Provider-neutral immutable artifact storage with MinIO protocol proof for
  local development and CI, plus bounded private processing scratch.
- External integrations composed through the typed ADR 0014 adapter boundary.

### Identity and authorization

- External Flow-token verification with issuer boundaries and request context.
- Canonical actors, identity links, actor lifecycle controls, and human lineage.
- Closed permission/action catalogues, deny-by-default authorization, bootstrap
  administrator grants, fixed-service identities, and runtime admission.
- Project-role grants, administrative APIs, authority evidence, idempotency,
  and PostgreSQL-backed rate controls.
- Project setup and project mutation/read authorization foundations used by the
  current guide integration work.

### Project, task, submission, and checker foundations

- Project guides, task queue records, task lifecycle guards, work context, and
  contributor submission requirements.
- Versioned submission packets with evidence references, locked context,
  finalization, and contributor privacy boundaries.
- Typed checker contracts, registry and runner behavior, durable checker
  records, pre-submit checks, and the automatic pre-review gate.
- Trusted retry, supersession, audit evidence, and real API contract drills for
  the implemented lifecycle.

### Guide-source and artifact processing

- Immutable source snapshots, source-media classification, typed extraction
  boundaries, and persisted extraction results.
- PDF, DOCX, and XLSX extraction with bounded input handling and OOXML security
  controls.
- Image metadata handling and persisted guide-sufficiency evidence.
- Guide materialization from persisted artifact-processing evidence.

## Integration In Progress

The following areas have merged planning, contracts, or partial foundations,
but are not all complete as one production path:

- authoritative project-guide binding and read activation across ART and AUTH;
- reviewed cross-initiative contracts connecting artifact custody with
  authorization-owned project guide reads;
- review-policy persistence and activation across REV and AUTH;
- review queue, reviewer assignment/claim, immutable decisions, and revision
  replay on the canonical authorization boundary;
- atomic review-to-contribution and conditional compensation integration.

Open pull requests are the authoritative view of the exact code currently under
review. Their presence does not change the implemented-on-`main` list above.

## Remaining v0.1 Capability Milestones

1. Complete the production guide binding/read path and prove its authorization,
   custody, lineage, and stale-generation behavior.
2. Complete review and revision persistence, queueing, access, decisions,
   findings, replay, and operational recovery.
3. Create immutable contributor and reviewer contribution records from the
   accepted review lifecycle.
4. Complete contribution-policy evaluation, conditional compensation awards,
   fulfillment, idempotency, reconciliation, and audit behavior without making
   settlement a prerequisite.
5. Preserve authoritative contribution evidence for future reputation
   projections; reputation projection remains deferred from the v0.1 runtime.
6. Prove the complete v0.1 lifecycle through real API, database, durable-job,
   storage, security, and operational recovery tests.
7. Add the React/Vite/TypeScript product surfaces only against stable and tested
   backend contracts.
8. Run a real internal pilot and close findings without weakening lifecycle,
   authorization, storage, or evidence guarantees.

These are dependency-ordered capability milestones, not a schedule. Distinct
initiatives may proceed concurrently when their contracts and integration
boundaries do not conflict.

## How To Read Repository Status

- **Implemented:** code and required evidence are merged on `main`.
- **In progress:** a bounded branch or pull request exists; behavior is not yet
  part of `main`.
- **Planned:** an accepted specification or initiative describes future work;
  behavior is unavailable until implemented and merged.
- **Historical:** the document records prior intent or evidence and does not
  control current work.

Use [CONTRIBUTING.md](../CONTRIBUTING.md) to start work and the
[Historical Planning Index](historical_planning.md) when investigating earlier
decisions.
