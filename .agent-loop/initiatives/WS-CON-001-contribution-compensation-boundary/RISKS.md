# Risks: WS-CON-001 Contribution And Compensation

| Risk | Impact | Mitigation |
|---|---|---|
| Old status is treated as current behavior | Duplicate or misordered work | PLAN4 binds current code, migration head, capability ledger, and PR state; dated evidence stays historical. |
| Dispatcher blocks independent policy work | REV lease persistence remains unnecessarily blocked | Move 03A/03B ahead of 02B; defer dispatcher until its actual consumers and AUTH contract. |
| CON invents AUTH identifiers or authority | Privilege escalation and dual authorization paths | AUTH exclusively registers contexts, actions, identities, matrices, evaluators, PREP, and activation. |
| REV/CON ownership blurs at policy freeze | CON could own ReviewLease or REV could own contribution policy | CON returns a policy-version lookup result; REV alone writes and transitions its lease. |
| ART/provider work enters review transaction | Availability coupling and broken atomicity | REV supplies stable artifact identity/hash; CON performs zero provider or ART calls. |
| Open PR is treated as merged | Wrong migration or dependency assumptions | Treat ART #249 as open until merged; treat REV #258 as merged planning evidence only; refresh main before every implementation. |
| Migration collision with ART/REV | Broken linear history | Allocate only from the then-current Alembic head; no number is reserved in planning. |
| Legacy economic rows are guessed | Corrupted award policy lineage | Require explicit deterministic classification or fail closed before 05A/05B. |
| Dispatcher authority leaks to handlers | Cross-feature service privilege | Dispatcher owns mechanics only; every protected handler has independent identity/action/context. |
| Optional evidence becomes core availability dependency | ART outage blocks contribution truth | Keep 09A/09B deferred and PostgreSQL reads authoritative. |
| Provider receipt leaks secrets | Security/privacy incident | Persist only bounded non-sensitive receipt facts; explicitly deny provider bodies, secrets, tokens, signatures, URLs, PII, balances, ledgers, settlement data, and digests derived from any forbidden input. |
| Review decision and contribution partially commit | Canonical truth divergence | REV owns one transaction and commit; CON participants flush only with fault-injection proof. |
