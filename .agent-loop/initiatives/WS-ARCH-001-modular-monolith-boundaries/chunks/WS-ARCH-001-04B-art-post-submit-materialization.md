# Chunk Contract: WS-ARCH-001-04B ART Post-Submit Materialization

Status: non-executable planning skeleton after 04A and merged 02H. Risk: L1.
Outcome: ART can hiddenly
materialize the exact verified bytes bound to one immutable Submission for the
fixed post-submit checker service.

Allowed: ART public API and owner-local materialization/binding code, fixed
adapter composition, focused ART tests, boundary ledgers and evidence/status.
Not allowed: checker policy/result ownership, TASK mutation, REV packet access,
generic download authority, Celery handle serialization or public routes.

Acceptance: authority and materialization bind project/task/Submission,
admission, binding/content/replica, digest/size and approved generation;
denial precedes provider/scratch access; stale/replaced/cross-resource/replayed
requests fail closed. Verify Local/MinIO protocol tests, scratch cleanup,
PostgreSQL races, boundary validators, Ruff and hosted coverage. Required
reviews: architecture, security, ART/product ops, QA, senior and CI.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.
