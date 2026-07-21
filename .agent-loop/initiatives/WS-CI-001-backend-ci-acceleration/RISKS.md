# RISKS: WS-CI-001 - Backend CI Acceleration

| ID | Risk | Severity | Mitigation |
| --- | --- | ---: | --- |
| R1 | A test is omitted or duplicated | Critical | One ordinary pytest process discovers and executes the complete suite exactly once |
| R2 | Reset leaks data between tests | Critical | Truncate every mutable public table in one transaction before each database-backed test |
| R3 | Reset damages schema or migration evidence | Critical | Preserve `alembic_version` and actor migration evidence; run destructive migration proofs separately |
| R4 | Immutable triggers block reset or remain disabled | Critical | Disable only five reviewed truncate guards and re-enable them in the same transaction |
| R5 | Coverage thresholds are weakened | Critical | Preserve the exact 78/90 commands and workflow regression assertions |
| R6 | MinIO tests run without a real provider | High | Start one pinned MinIO service before the complete suite |
| R7 | The child hangs silently | High | Emit a secret-free heartbeat every 60 seconds and enforce a 20-minute child bound |
| R8 | PGlite diverges from production PostgreSQL | High | Keep asyncpg, locks, triggers, migrations, and concurrency proofs on real PostgreSQL |
| R9 | Parallel infrastructure returns without evidence | High | Regression-test that the workflow has one job and no matrix, shard tool, or fan-in artifacts |
| R10 | API drill state contaminates pytest | High | Run the API drill in a sequential isolated-runner invocation |
| R11 | Required check identity changes | Critical | Preserve the single `Backend / test` job and verify it in workflow tests |
| R12 | Fixture consolidation changes application behavior | High | Limit implementation to tests, runner supervision, workflow, and documentation |
| R13 | Mutable PostgreSQL tag changes CI behavior | High | Retain the reviewed digest-pinned PostgreSQL service image |
