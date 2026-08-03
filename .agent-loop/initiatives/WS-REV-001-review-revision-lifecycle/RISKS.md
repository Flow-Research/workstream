# Risks: WS-REV-001 Review And Revision Lifecycle

| ID | Risk | Severity | Mitigation |
|---|---|---:|---|
| R1 | REV implements missing AUTH, ART, TASK, CHECKER, or CON behavior | Critical | Typed ports only; owner evidence gate; architecture review on every integration child. |
| R2 | Historical planning is mistaken for live authority | High | PLAN4, live chunk map, and active spec control; historical files are explicitly non-executable. |
| R3 | Duplicate Submission identity or artifact store appears | Critical | Reuse existing Submission and ART ports; architecture scans prohibit replacements. |
| R4 | Queue/lease races create duplicate work or multiple leases | Critical | Partial uniqueness, database time, row locks, and two-order PostgreSQL races. |
| R5 | Self-review or stale authority commits | Critical | Exact AUTH 02D contracts, PREP revalidation, locked final facts, revocation races. |
| R6 | Reviewer queue leaks backlog or enables cherry-picking | High | Active lease/one server-selected offer/none; separate privileged inspection. |
| R7 | Artifact outage becomes contributor fault | Critical | No adverse transition; typed unavailable/integrity results; recovery audit. |
| R8 | Remote I/O occurs under decision locks | Critical | Materialize before/after transaction; canonical decision uses IDs/digests only. |
| R9 | Review or revision history is rewritten or forks | Critical | Append-only rows, predecessor uniqueness, non-branching episode heads, direct-SQL proof. |
| R10 | Checker remediation is confused with human revision | Critical | Source XOR, separate participants, no synthetic Review/finding/contribution. |
| R11 | Decision partially commits without contribution effects | Critical | First Review commit only in chunk 10 with mandatory CON participant and fault injection. |
| R12 | Submitter contribution is inferred directly from Review | Critical | Accept-only REV FinalAcceptance is the sole CON submitter source. |
| R13 | Contribution terms rebase with guide context | Critical | Assignment and lease freezes remain independent of guide/revision context. |
| R14 | Public routes expose incomplete lifecycle | Critical | Routes remain absent until 13C; AUTH activation is hidden proof, not product release. |
| R15 | Timers or recovery depend on background-job delivery | High | Database-time truth, lazy recovery, idempotent sweeps, reconciliation. |
| R16 | Cross-domain lock order deadlocks | Critical | Command-specific published order, stable ID sorting, both-order tests. |
| R17 | Projection becomes canonical or blocks Review | High | Shared outbox, post-commit deterministic projection, rebuildable state. |
| R18 | Review text or identifiers leak through logs/metrics | High | Bounded audit fields, redaction, no bytes/digests/provider locators in metrics. |
| R19 | Far-future contracts freeze stale filenames/migrations | High | Skeletons only; exact contract refreshed at each start from current main. |
| R20 | Human revision limit/deadline semantics are guessed | Critical | Explicit human decision before 09A1; no inference from checker retries or SLA. |
| R21 | Full local testing consumes excessive time/resources | Medium | Focused local proof only; GitHub Actions runs full suite and coverage. |
| R22 | REV creates leases before CON's canonical policy-version target exists | Critical | 03A2 is gated on merged CON-03B and requires a non-null immutable FK; no placeholder policy model or nullable retrofit. |
| R23 | REV packet semantics and ART packet materialization form a circular dependency | Critical | ART first publishes a contract-only membership port with no REV runtime dependency; REV-03B owns the normalized manifest; ART-07A consumes the merged lease/manifest; REV-07A consumes ART materialization. |
| R24 | Hidden REV tests imply an unavailable AUTH action can succeed | Critical | Before XINT activation, prove feature rules and unavailable denial separately; positive PREP/evaluator proof belongs to the matching XINT activation. |
| R25 | A stale owner-plan status is mistaken for merged capability | Critical | Each consumer child verifies signed merge history and exact runtime symbols; REV documents and escalates owner gaps without editing their plans. |
