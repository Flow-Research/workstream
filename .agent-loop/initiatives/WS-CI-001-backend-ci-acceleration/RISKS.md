# RISKS: WS-CI-001 - Backend CI Acceleration

| ID | Risk | Severity | Mitigation |
|---|---|---:|---|
| R1 | A test is omitted or duplicated | Critical | Filesystem modules plus stable preflight cardinality signatures and exact same-process collection/completion validation |
| R2 | Coverage is combined from incomplete, foreign, or altered evidence | Critical | Bind fixed artifacts and coverage SHA-256 to checked-out tree, shard ID, schema, and manifest digest |
| R3 | Upstream failure is hidden by dependency skipping | Critical | Always-run final check explicitly validates every dependency result |
| R4 | Shards interfere through shared database state | Critical | One isolated migrated database and role per shard process |
| R5 | Coverage thresholds are weakened | Critical | Preserve exact 78/90 commands and add workflow regression assertions |
| R6 | MinIO tests run without a real provider | High | Start pinned MinIO in all shards initially or prove a safe module map before narrowing |
| R7 | One large module controls wall time | Medium | Measure hosted shard duration; consider reviewed node-level split only later |
| R8 | Parallel jobs cost more runner minutes | Medium | Begin with four shards and compare aggregate minutes with PR #161 |
| R9 | Artifact names collide | High | Per-commit/per-shard names and strict unique-set fan-in |
| R10 | Untrusted paths reach shell execution | High | Canonical path validation and argument-array execution in repository script |
| R11 | Required check identity changes | Critical | Preserve final Backend `test` job and verify in workflow tests/GitHub PR |
| R12 | Plan scope expands into path-based skipping | High | Defer routing to separately approved 02 contract |
| R13 | Mutable PostgreSQL tag changes CI behavior | High | Replace `postgres:16` with a reviewed digest pin in 01 |
| R14 | Parameter display values change across pytest processes | Critical | Execute whole modules; compare exact collection/completion within one process and bind only stable test-base cardinalities across processes |
