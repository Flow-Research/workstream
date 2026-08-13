# Risks: WS-CON-001 Contribution And Compensation

| Risk | Impact | Mitigation |
|---|---|---|
| Old status is treated as current behavior | Duplicate or misordered work | PLAN4 binds current code, migration head, capability ledger, and PR state; dated evidence stays historical. |
| Dispatcher blocks independent policy work | REV lease persistence remains unnecessarily blocked | Move 03A/03B ahead of 02B; defer dispatcher until its actual consumers and AUTH contract. |
| CON invents AUTH identifiers or authority | Privilege escalation and dual authorization paths | AUTH exclusively registers contexts, actions, identities, matrices, evaluators, PREP, and activation. |
| REV/CON ownership blurs at policy inheritance | CON could own ReviewLease or REV could select contribution policy | CON validates once at guide activation; TASK locks and carries the version; REV alone verifies, writes, and transitions its lease. |
| ART/provider work enters review transaction | Availability coupling and broken atomicity | REV supplies stable artifact identity/hash; CON performs zero provider or ART calls. |
| Human revision mixes new guide/policies with stale contribution terms or rewrites completed awards | Incoherent contributor obligations and corrupted economic history | One task-owned complete-context preparation keeps/rebases/blocks atomically; only the next-attempt TaskAssignment selector changes; completed lease/contribution/award history remains immutable. |
| Planning evidence is treated as runtime | Wrong migration or dependency assumptions | Treat ART #249 as merged ART runtime and REV #258 as merged planning evidence only; refresh main before every implementation. |
| Migration collision with ART/REV | Broken linear history | Allocate only from the then-current Alembic head; no number is reserved in planning. |
| Legacy economic rows are guessed | Corrupted award policy lineage | Require explicit deterministic classification or fail closed before 05A/05B. |
| Dispatcher authority leaks to handlers | Cross-feature service privilege | Dispatcher owns mechanics only; every protected handler has independent identity/action/context. |
| Optional evidence becomes core availability dependency | ART outage blocks contribution truth | Keep 09A/09B deferred and PostgreSQL reads authoritative. |
| Provider receipt leaks secrets | Security/privacy incident | Persist only bounded non-sensitive receipt facts; explicitly deny provider bodies, secrets, tokens, signatures, URLs, PII, balances, ledgers, settlement data, and digests derived from any forbidden input. |
| Review decision and contribution partially commit | Canonical truth divergence | REV owns one transaction and commit; CON participants flush only with fault-injection proof. |
