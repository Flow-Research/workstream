# Risks: WS-XINT-003 REV-AUTH End-to-End Contract

| Risk | Severity | Control |
|---|---|---|
| Duplicate REV/AUTH policy writers | Critical | Reconcile REV-03P and AUTH-12D2 before runtime work; one persistence path. |
| Self-review or wrong-project review | Critical | Exact reviewer grant, contributor conflict check, project/task/submission binding, final revalidation. |
| Queue read becomes decision authority | Critical | Separate actions and progressively stronger queue, lease, packet, evidence, and decision contexts. |
| Stale/expired/revoked lease commits judgment | Critical | AUTH-first lock plus final lease/grant/actor/link recomposition and crossed races. |
| Reviewer receives generic artifact access | Critical | Exact packet manifest and fixed materializer action; no download permission. |
| Future evidence upload is accidentally treated as approved v0.1 authority | Critical | v0.1 uses REV-owned note/finding/response records only; upload and fixed ART binding actions remain future-intent-required and unavailable. |
| Partial Review/CON/Task state | Critical | One transaction, ordered flush-only CON participant, exhaustive fault injection. |
| Human revision bypasses findings/deadline/round | Critical | Exact obligation/preparation/predecessor locks and closed revision context. |
| Checker remediation is mistaken for human Review revision | Critical | Separate CheckerRun-rooted context and mutually exclusive persisted source. |
| Operator recovery broadens product authority | Critical | Distinct reason-bound actions, bounded reads, no decision/artifact authority. |
| Service identities collapse into a catch-all service | Critical | Closed enums, constraints, static matrices, provisioning, admission, all-pairs denial. |
| Serialized prepared authority is replayed by Celery | Critical | Opaque non-serializable handles and static payload scanners/tests. |
| Activation precedes hidden feature readiness | Critical | Planned-by-default catalogue and exact merged feature manifest gates. |
| Historical counts/contracts are treated as current | High | Derive parity from current migrations/catalogue at every chunk start. |
| One PR becomes unreviewable | High | Narrow activation waves and explicit allowed/not-allowed files per chunk. |
| Review-evidence binding is activated without an approved v0.1 upload lifecycle | Critical | Keep it planned/unavailable; packet-only 07A proceeds, and any evidence upload requires separate REV-owned intent. |
| Policy edits mutate active-guide history | Critical | Append-only versions, draft-only final PREP guard, and PostgreSQL update/delete refusal proof in chunk 02. |
| REV and AUTH wait on each other | Critical | Complete unavailable catalogue/principals in 02C and PREP contracts in 02D; only availability waits for REV implementation. |
| Bundled activation outruns one product behavior | Critical | Gate queue read, claim, release/decline, timers, context, decision, revision, and recovery against their exact REV child evidence. |
| AUTH activation accidentally releases a route | Critical | Keep REV lifecycle fence closed; only REV-13C registers product routers after integrated conformance. |
| Future evidence upload is swept into v0.1 | Critical | Distinct future-intent-required unavailable classification and explicit activation prohibition. |
