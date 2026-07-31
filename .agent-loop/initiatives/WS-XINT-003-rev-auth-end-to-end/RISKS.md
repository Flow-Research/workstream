# Risks: WS-XINT-003 REV-AUTH End-to-End Contract

| Risk | Severity | Control |
|---|---|---|
| Duplicate REV/AUTH policy writers | Critical | Reconcile REV-03P and AUTH-12D2 before runtime work; one persistence path. |
| Self-review or wrong-project review | Critical | Exact reviewer grant, contributor conflict check, project/task/submission binding, final revalidation. |
| Queue read becomes decision authority | Critical | Separate actions and progressively stronger queue, lease, packet, evidence, and decision contexts. |
| Stale/expired/revoked lease commits judgment | Critical | AUTH-first lock plus final lease/grant/actor/link recomposition and crossed races. |
| Reviewer receives generic artifact access | Critical | Exact packet manifest and fixed materializer action; no download permission. |
| Evidence bytes are bound under human authority | Critical | Separate human ingest and fixed ART binding capabilities committed with exact evidence lineage. |
| Partial Review/CON/Task state | Critical | One transaction, ordered flush-only CON participant, exhaustive fault injection. |
| Human revision bypasses findings/deadline/round | Critical | Exact obligation/preparation/predecessor locks and closed revision context. |
| Checker remediation is mistaken for human Review revision | Critical | Separate CheckerRun-rooted context and mutually exclusive persisted source. |
| Operator recovery broadens product authority | Critical | Distinct reason-bound actions, bounded reads, no decision/artifact authority. |
| Service identities collapse into a catch-all service | Critical | Closed enums, constraints, static matrices, provisioning, admission, all-pairs denial. |
| Serialized prepared authority is replayed by Celery | Critical | Opaque non-serializable handles and static payload scanners/tests. |
| Activation precedes hidden feature readiness | Critical | Planned-by-default catalogue and exact merged feature manifest gates. |
| Historical counts/contracts are treated as current | High | Derive parity from current migrations/catalogue at every chunk start. |
| One PR becomes unreviewable | High | Narrow activation waves and explicit allowed/not-allowed files per chunk. |
