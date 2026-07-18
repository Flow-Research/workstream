# Risks: WS-ART-001 S3-Compatible Object Storage Amendment

| Risk | Severity | Mitigation |
|---|---:|---|
| Existing key overwritten by concurrent upload or adapter regression | Critical | Content-addressed key, conditional no-overwrite write, bucket-policy deny when `If-None-Match` is absent, S3-required `*` header value, concurrency tests, and live unconditional-overwrite denial proving original bytes unchanged. |
| First writer poisons a known digest key | Critical | Every source is server-hashed in bounded scratch before provider I/O; the port accepts only a sealed committed source; cross-project adversarial tests prove no client-selected digest can choose a key. |
| Provider acknowledgement accepted without exact bytes | Critical | Independent complete-object read/hash before bindability. |
| Multipart semantics diverge across providers | High | v0.1 uses conditional single-request put with a 512 MiB hard limit; multipart is deferred. |
| ETag or provider metadata mistaken for Workstream SHA-256 | Critical | Workstream computes SHA-256; ETag and custom metadata are never authoritative. |
| S3 credential becomes product authority | Critical | Authorization Service decision precedes every product action; credential is transport only. |
| Secret retained in settings errors/logs/jobs | Critical | Secret-safe settings boundary, redaction/object-graph tests, no credential persistence. |
| Wrong AWS credential source is accepted | Critical | Production selects one allowlisted workload-identity method, verifies the resolved method, and rejects explicit or unselected ambient credential sources before provider I/O. |
| Public bucket leaks evidence | Critical | AWS deployment proof checks Block Public Access, policy/ACL state, and anonymous-read denial. |
| Unapproved AWS principal reaches private evidence | Critical | Exact runtime/readiness/negative/bootstrap matrix, bucket-policy deny for non-runtime object principals, internal/external IAM evaluation, and anonymous/same-account/same-organization/external negative proof. |
| Runtime credential can destroy evidence | Critical | Exact bucket/prefix/action scope; denied delete/copy/admin/lifecycle/public-access actions; negative tests. Bucket-list authority is read-only and cannot mutate evidence. |
| Compromised runtime credential enumerates artifact hashes | High | AWS requires bucket-level `s3:ListBucket` for missing `HeadObject` to return 404. Production uses a dedicated Workstream bucket whose keys contain only opaque SHA-256 values, the port/application exposes no list operation, and the exact action/resource plus live missing-key proof are activation gates. |
| Product code bypasses artifact admission through the raw port or broad orchestration injection | Critical | Only internal artifact-storage orchestration receives writable ArtifactStore; static architecture tests reject raw-port imports, broad orchestrator injection, and put/observe calls outside that module. |
| Deployment silently reads or writes another storage namespace | Critical | One singleton namespace row is atomically claimed or validated before I/O; replicas and put attempts bind its fingerprint, and mismatch requires a maintenance migration. |
| Provider acknowledgement is lost before a replica exists | Critical | Transaction A persists a fenced `ArtifactPutAttempt`; a scanner resolves it through read-only observation and full hash without replaying a write. |
| AWS configuration becomes active without live proof | Critical | Separate caller-ARN-bound readiness/runtime/negative probe records feed a credential-free coordinator; startup and every I/O require an exact activation refreshed every 5 minutes and expiring within 15 minutes. MinIO proof cannot create it. |
| AWS operation outlives its activation proof | Critical | Admission requires remaining activation TTL to cover the total I/O deadline plus persistence/clock margins, and the terminal transaction rechecks the same unexpired activation. |
| Registered permission is mistaken for executable artifact authority | Critical | AUTH registration remains planned; ART supplies hidden canonical resources, guards, surfaces, tests, and terminal revalidation; AUTH alone integrates the evaluator and activates the exact action afterward. |
| ART and AUTH both claim activation custody | Critical | `WS-AUTH-001-ART-CUSTODY` transfers all 25 current ART mappings to eight closed AUTH custodians, preserves mappings and availability, removes unused ART owner enums, and rejects partial or dual ownership through parity tests. |
| Broker publication failure strands verification/recovery | High | Periodic PostgreSQL scanner with bounded SLA and duplicate-safe publication. |
| Duplicate/stale Celery execution writes terminal state | Critical | PostgreSQL clock, fresh executor UUID, generation fencing, and zero-row stale finalization rollback. |
| Slow progressive read outlives execution lease | High | End-to-end verification deadline shorter than lease by a persistence margin. |
| Concurrent prepared artifacts exhaust worker disk | High | Full-max pre-reservation, dedicated quota, cross-process ledger, bounded concurrency, free-space floor, and deadline-before-TTL cleanup. |
| Any guide, contributor, or checker producer creates unbounded retained bytes | Critical | One generic admission service atomically caps cumulative unique provisional/completed bytes at every applicable task, producer, project, and deployment scope before provider I/O; only authoritative absence releases a provisional charge. |
| Operators cannot diagnose or expand exhausted storage capacity | High | Bounded admission-usage API, scope metrics/alerts, and a configuration-driven expansion/rollback runbook; no charge deletion or database editing. |
| Expired upload sessions retain open-session capacity forever | High | PostgreSQL-clock periodic Celery expiry plus lazy expiry before admission perform one atomic terminal transition and release the session slot exactly once. |
| Recovery replay or ancestor reuse creates multiple jobs | High | Canonical request digest plus a lifetime unique source-job constraint return original IDs on exact replay, reject different-key/concurrent reuse, and require chain progression through the immediate retry job. |
| Operator cannot observe retry completion | High | Authorized recovery-attempt GET includes immutable source-job and current retry-job status plus audit IDs. |
| Storage failure becomes contributor failure or review decision | Critical | Stable infrastructure errors; no accept/needs_revision/reject, contribution, payment, or reputation effect. |
| Pre-submit outage strands or duplicates a contributor attempt | High | Bounded Workstream retry, stable 503, sealed unconsumed artifact set, exact request-digest idempotency, and contributor continuation without manager/operator approval. |
| Pre-existing lifecycle rule deletes evidence | Critical | Read-only AWS lifecycle inspection blocks activation for any deletion/expiration rule intersecting the completed-object prefix. |
| Local adapter reaches production | High | Closed backend enum and production startup rejection. |
| MinIO proof is mistaken for AWS readiness | High | Shared conformance runs on LocalStorage/MinIO, while AWS has a separate private-bucket, workload-identity, lifecycle, and anonymous-read live proof. |
| Flow Node remains a hidden v0.1 dependency | High | Separate deferred initiative and stale-contract gate. |
| R2 remains a hidden v0.1 dependency | High | No active R2 chunk/configuration/runtime path; stale-contract gate rejects reintroduction outside a separately approved initiative. |
| Route tests overclaim fleet atomicity | Medium | Per-image proof only; deployment barrier documented separately. |
| Large chunks become unreviewable | High | Preparation, v2 cutover, provider profiles, verification, recovery, upload/sealing, pre-submit admission, checker input, and checker output/routing are separate checkpoints with explicit allowed files and stop conditions. |
