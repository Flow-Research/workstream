# WS-ARCH-001 — Current remaining change map

Use the [current dependency contract](PLAN.md#current-dependency-contract).
The [preserved map](../pre-cutover/CHUNK_MAP.md) retains the complete original
work accounting. Foundations through 02H and CP04B are complete; none restart.

| Boundary | Owner outcome | Risk | Current dependency |
|---|---|---|---|
| `WS-ARCH-001-02I` | Admission-only public API/dispatch cutover and removal of legacy route reachability; physical economic cleanup remains CP09 after zero consumers | L1 | Deferred after 02H plus split 03/04/05 remediation, revision, checker-output and REV admission prerequisites |
| [WS-ARCH-001-CP05](../WS-ARCH-001-CP05.md) | AUTH exact ContributionPolicy activation | L1 | Complete; exact policy authority delivered in PR #387 |
| [WS-ARCH-001-CP06](../WS-ARCH-001-CP06.md) | CON guide-activation/revision policy-validation port | L1 | Complete; explicit version/purpose validation and shared current resource fences |
| [WS-ARCH-001-CP07](../WS-ARCH-001-CP07.md) | PROJECTS hidden activation/binding and replacement readiness guard | L1 | Complete; AUTH-12H live manager authority delivered; ARCH-03A complete internal guide facts delivered; next CP08 lineage and minimal writers |
| [WS-ARCH-001-CP08](chunks/WS-ARCH-001-CP08-task-attempt-policy-lineage.md) | TASK/Assignment/Submission policy-lineage schema, public facts and minimal existing writers | L1 | Planned after ARCH-03A; schema and minimal writers change together |
| [WS-ARCH-001-CP09](chunks/WS-ARCH-001-CP09-legacy-economic-removal.md) | Physical retired economic-path cleanup coordination | L1 | Planned after all legacy consumers, including CHECKERS/public 02I, are replaced; not an allow_review dependency |
| [WS-ARCH-001-03A](chunks/WS-ARCH-001-03A-project-current-generation-api.md) | PROJECT current approved unified-generation public facts | L1 | Complete; one active/frozen context port reuses activation custody; CP08 next |
| [WS-ARCH-001-03B](chunks/WS-ARCH-001-03B-task-assignment-api.md) | TASK readiness, claim, assignment and locked-context public commands/facts | L1 | Planned after 03A and CP08; remaining queues, invalidation and broader projections; CP08 owns the minimal lineage writers |
| [WS-ARCH-001-03C](chunks/WS-ARCH-001-03C-auth-task-readiness.md) | Exact task/assignment action activation, routing and invalidation proof | L1 | Planned after 03A/03B, CP08 and AUTH-OUTBOX-02; replacement precedes physical cleanup |
| [WS-ARCH-001-04A](../WS-ARCH-001-04A.md) | CHECKER post-submit contract and registered evaluator conformance | L1 | Complete canonical catalogue, phase facts and structural conformance; consumed by delivered POL-04B and POL-07B |
| [WS-ARCH-001-04B](chunks/WS-ARCH-001-04B-art-post-submit-materialization.md) | ART exact verified Submission materialization | L1 | Planned after 04A, POL-07, 03C and merged 02H |
| [WS-ARCH-001-04B2](chunks/WS-ARCH-001-04B-art-post-submit-materialization.md#arch-04b2--separate-art-output-custody-child) | ART generated-output/log custody and verified binding | L1 | 04A public request/run facts plus merged ART foundations; no CHECKERS private lookup |
| [WS-ARCH-001-04C](chunks/WS-ARCH-001-04C-checker-current-result.md) | CHECKER hidden durable current output and supersession behavior | L1 | Planned after 04A/04B/04B2; production remains deny-only |
| [WS-ARCH-001-04D](chunks/WS-ARCH-001-04D-auth-post-submit-activation.md) | AUTH exact fixed-service post-submit activation (replaces XINT-06B) | L1 | Planned after 04B/04C evidence |
| [WS-ARCH-001-04E](chunks/WS-ARCH-001-04E-canonical-allow-review.md) | TASK current routing: true to canonical `allow_review`, false/pass to shared acceptance | L1 | Source 04E1A -> hidden handlers 04E1B -> AUTH 04E2 -> live 04E3, plus 04D/OUTBOX-02; false consumes shared REV/CON/fence proof and activation also requires 04F remediation |
| [WS-ARCH-001-04F](chunks/WS-ARCH-001-04F-checker-remediation.md) | Contributor-correctable checker failures and same-lineage admission-backed replacement Submission | L1 | Planned after 04E; replaces XINT-05C, required before public 02I, not before REV begins from `allow_review` |

CP09, 04E and 04F are coordination parents, not permission for multi-owner PRs.
Only CP09 and 04F are outside the `allow_review` critical path; 04E's children
deliver that boundary. Each remaining implementation
expands its current child contract into one existing-initiative change record
with exact paths, schema head, proof commands and impact-routed reviewers.
That expansion belongs to its implementation PR, not an extra approval loop.
No new product implementation starts automatically on merge of this plan.
