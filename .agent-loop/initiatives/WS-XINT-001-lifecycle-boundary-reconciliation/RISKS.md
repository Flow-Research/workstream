# Risks: WS-XINT-001 Lifecycle Boundary Reconciliation

| Risk | Impact | Mitigation | Proof |
|---|---|---|---|
| Partial ART owner transfer | Dual or missing activation custody | Transfer all 25 mappings atomically and remove unused feature owner enums | Closed typed/SQL parity |
| Action active before behavior | Authorization allows an unimplemented or fallback path | Registration -> hidden behavior -> AUTH activation | Startup and end-to-end parity |
| Feature code manufactures authority | Cross-project or service escalation | AUTH-only grants, static service-action matrix, evaluators, and activation | Architecture/security negative tests |
| Circular activation dependency | Neither AUTH nor feature behavior can land safely | Hidden behavior runs under fakes while real action remains planned | Planned-action denial tests |
| Cross-domain deadlock | Review/contribution transactions stall or partially mutate | AUTH-first lock order and caller-owned commit | Concurrency and rollback tests |
| Provider I/O inside transaction | Long locks and irrecoverable partial effects | Durable work staged before post-commit execution | Failure/cancellation tests |
| Mandatory CON artifact projection | Contributions fail for unrelated storage projection | Remove ART from core contribution transaction | Atomic Review/CON tests with no ART call |
| Review artifact over-disclosure | Reviewer sees unrelated bytes | Active-lease exact packet membership and typed ART ports | Cross-task/project/version denial tests |
| Parallel branch drift | Agents implement different contracts | Merge one immutable coordination PR before owner amendments | Exact merged-SHA handoff references |
| Combined contributor role couples authority | Revoking review also removes submitter or adjudicator access, or forces replacement semantics | Independent submitter/reviewer/adjudicator grants and role-specific invalidation | Partial-unique, regrant, and independent-revocation proof |
| Adjudicator grant becomes implicit adjudication authority | AUTH invents review behavior without a REV lifecycle | Persist the independent grant but keep adjudication actions unavailable until WS-REV and AUTH activation | Closed role/action matrices and denial proof |
| Service tokens enter human authorization | Internal workload gains human grants or first-access behavior | Dedicated fixed service admission and exact static action matrix | Human/service isolation and cross-service denial tests |
