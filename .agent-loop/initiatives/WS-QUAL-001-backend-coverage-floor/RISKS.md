# Risks: WS-QUAL-001 Backend Coverage Floor

| Risk | Control |
|---|---|
| Tests chase lines instead of behavior | Require meaningful outcome assertions and QA/product review |
| Coverage is inflated by exclusions | Measure all `backend/app` modules; prohibit omit lists and coverage pragmas |
| Shared Postgres state corrupts evidence | One provisioner owns a strictly named local database, cleanup, and migration-head evidence |
| Giant PR becomes unreviewable | Split project, task/checker, and residual coverage into bounded chunks |
| Threshold is silently weakened later | CI-integrity review and PR template; floor can only stay level or rise |
| Tests over-mock persistence and workers | Require focused integration proof for repository, queue, and audit outcomes |
| Coverage tracing makes the suite too slow | Profile fixtures separately; never trade correctness or isolation for speed |
| A test exposes a production bug | Stop and create a separately scoped corrective chunk |
| Credentials leak through commands/evidence | Accept admin DSN only from environment; record only database name and redact URLs |
| Ratchet is lowered with its own checker | Compare configuration/evidence to merge base and require CI-integrity review |
