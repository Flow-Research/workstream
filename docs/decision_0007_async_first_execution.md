# ADR 0007: Execution Is Async-First

## Status

Accepted

## Context

Workstream will run checks, submissions, reviews, revision loops, compensation
fulfillment reconciliation, notifications, and audit writes.

Some of these operations are quick request/response work. Others are long-running jobs that must not block API requests.

## Decision

Workstream is async-first.

FastAPI route handlers, service calls, database access, storage access, checker orchestration, and audit writes use async boundaries where I/O is involved.

Long-running checker, project setup, and background work must not block
request/response paths.

Celery is the v0.1 durable worker boundary for Workstream product jobs.
FastAPI background tasks are not used for project setup automation, checker
execution, or other product lifecycle work. An equivalent durable worker may
replace Celery later only with an ADR-level reason.

## Consequences

Positive:

- API responsiveness does not depend on checker duration
- checker runs can produce durable running/completed state
- the system has a clear durable-worker boundary instead of request-owned jobs
- synchronous-first shortcuts are rejected by architecture, not debated per chunk

Tradeoff:

- services must be designed around async database and I/O APIs from the start
- durable job infrastructure is part of local development and production-like execution
