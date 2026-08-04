# Risks: WS-QUAL-001 Current-Main Coverage Closure

| Risk | Consequence | Control |
|---|---|---|
| Coverage-only tests | Higher percentage without stronger behavior proof | Require observable outcomes and QA/test-delta review |
| More database/HTTP tests | Backend CI becomes slower | Prefer pure/use-case/adapter-contract tests unless the real boundary is essential |
| Concurrent denominator growth | Candidate falls below 90 before floor merge | Remeasure current main and require >=90.25% headroom before 04R |
| Threshold bundled with tests | Harder diagnosis and pressure to bargain | Keep the 90-percent switch in separate chunk 04R |
| Production defect discovered | QUAL scope expands into product repair | Stop and hand defect to owning initiative |
| Historical parser revival | Reintroduces complexity and maintenance burden | Mark 01B2 and old replacements superseded |
| File exclusion or pragma | False global measurement | Preserve complete app inventory and existing stale/coverage guards |
| Duplicate invariant tests | Slower suite and ambiguous ownership | Map each new test to its owning layer and review existing proof first |

No secret, credential, deployment, payment, or production-data access is needed.
