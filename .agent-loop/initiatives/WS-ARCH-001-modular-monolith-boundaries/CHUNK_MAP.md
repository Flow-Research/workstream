# Chunk Map: WS-ARCH-001 Modular Monolith Boundaries

| Chunk | Goal | Risk | State |
|---|---|---:|---|
| `WS-ARCH-001-01` | Canonical module map, exact general edge ledger, public-API validator, and CI foundation | L1 | Complete |
| `WS-ARCH-001-HK1` | Post-02B durable-state and local-worktree housekeeping | L2 | Merged PR #318; documentation and local operations only |
| `WS-ARCH-001-02` | Coordination record for the split submission preparation/consumption capability sequence | L1 | Split; non-executable parent |
| `WS-ARCH-001-02A` | TASKS task/assignment/predecessor and Submission public facts/ports | L1 | Merged PR #314 |
| `WS-ARCH-001-02B` | PROJECTS locked guide and submission-policy public facts/ports | L1 | Merged PR #315 |
| `WS-ARCH-001-02C` | CHECKERS effective pre-submit plan and bounded execution-result public facts/ports | L1 | Merged PR #320; no contributor preparation action or public route activated |
| `WS-ARCH-001-02D` | ART hidden preparation public API and private-edge migration | L1 | Complete; production remains deny-only |
| `WS-ARCH-001-02E` | ART ready-admission consumption and binding hidden module-level capability | L1 | Complete; production remains deny-only and route-unreachable |
| `WS-ARCH-001-02F` | TASK-owned immutable Submission command and hidden composed transaction | L1 | Complete; production remains deny-only and route-unreachable |
| `WS-ARCH-001-02G` | AUTH contributor preparation activation after the complete hidden path | L1 | Complete |
| `WS-ARCH-001-02H` | AUTH human/fixed-service consumption activation | L1 | Complete; public route remains unchanged |
| `WS-ARCH-001-02I` | Admission-only public API/dispatch cutover and complete legacy removal | L1 | Deferred after 02H plus split 03/04/05 remediation, revision, checker-output and REV admission prerequisites |
| `WS-ARCH-001-PLAN2` | Current-main reconciliation around canonical Submission-to-`allow_review` | L1 | Planning contract complete; implementation sequencing remains planned |
| `WS-ARCH-001-PLAN3` | ContributionPolicy registration, behavior, activation, guide/task lineage and clean legacy-removal sequencing | L1 | Planned; planning correction only and no runtime |
| `WS-ARCH-001-PLAN4` | Delivery-coupled technical-debt retirement policy and current-main baseline | L1 | Planned; planning only and no unrelated v0.1 delivery block |
| `WS-ARCH-001-CP01` | Combined AUTH registration planning parent | L1 | Planned split into CP01A/CP01B; non-executable |
| `WS-ARCH-001-CP01A` | AUTH adapter-binding unavailable registration | L1 | Complete; four actions remain planned/unavailable |
| `WS-ARCH-001-CP01B` | AUTH ContributionPolicy unavailable registration | L1 | Complete; five actions remain planned/unavailable |
| `WS-ARCH-001-CP01C` | AUTH adapter-binding fact correction | L1 | Complete; corrects unavailable facts before CON behavior |
| `WS-ARCH-001-CP02` | CON hidden adapter-binding behavior | L1 | Complete; route-unreachable and deny-default while actions remain unavailable |
| `WS-ARCH-001-CP03` | Adapter-binding activation coordination parent | L1 | Planned split into CP03A/CP03B; non-executable |
| `WS-ARCH-001-CP03A` | Closed adapter target identity and PROJECTS/ACTORS owner eligibility | L1 | Merged through PR #340; actions remain unavailable |
| `WS-ARCH-001-CP03B` | AUTH exact Finance Authority adapter-binding activation | L1 | Complete; four exact hidden actions active through public ports, with private wiring confined to the AUTH adapter root |
| `WS-ARCH-001-CP04` | CON hidden ContributionPolicy behavior | L1 | Proposed skeleton after merged CP03B evidence |
| `WS-ARCH-001-CP05` | AUTH exact ContributionPolicy activation | L1 | Proposed skeleton after CP04 evidence |
| `WS-ARCH-001-CP06` | CON guide-activation/revision policy-validation port | L1 | Proposed skeleton after CP05 |
| `WS-ARCH-001-CP07` | PROJECT guide-bound ContributionPolicyVersion persistence | L1 | Proposed skeleton after CP06 |
| `WS-ARCH-001-CP08` | TASK/Assignment/Submission policy-lineage schema and public facts | L1 | Proposed foundation after CP07; no commands |
| `WS-ARCH-001-CP09` | Clean retired guide-bound economic path removal | L1 | Proposed after ARCH-03C activates the replacement; split if discovery requires |
| `WS-ARCH-001-03` | PROJECT/TASK readiness coordination parent | L1 | Split; non-executable parent |
| `WS-ARCH-001-03A` | PROJECT current approved unified-generation public facts | L1 | Planned after AUTH-12H, CP07, and CP08; may reuse CP07 public guide fact but cannot duplicate its write |
| `WS-ARCH-001-03B` | TASK readiness, claim, assignment and locked-context public commands/facts | L1 | Sole behavior owner after 03A and CP08; consumes CP08 fields/facts to write Task -> Assignment -> Submission lineage |
| `WS-ARCH-001-03C` | AUTH-13 task/assignment activation and integrated readiness proof | L1 | Planned after 03A/03B and CP08; activates replacement before CP09 removes the retired path |
| `WS-ARCH-001-04` | Canonical post-submit checker coordination parent | L1 | Split; non-executable parent |
| `WS-ARCH-001-04A` | CHECKER post-submit plan/run/final-result public contract | L1 | Planned skeleton after POL-07 and 03C |
| `WS-ARCH-001-04B` | ART exact verified Submission materialization | L1 | Planned skeleton after 04A and merged 02H |
| `WS-ARCH-001-04C` | CHECKER hidden durable current output and supersession behavior | L1 | Planned skeleton after 04A/04B; production remains deny-only |
| `WS-ARCH-001-04D` | XINT-06B exact fixed-service post-submit activation | L1 | Planned skeleton after 04B/04C evidence |
| `WS-ARCH-001-04E` | TASK automatic dispatch/current routing integration and canonical `allow_review` manifest | L1 | Planned skeleton after 04D |
| `WS-ARCH-001-04F` | Contributor-readable checker remediation for final non-reviewable checker outcomes | L1 | Planned skeleton after 04E; required before public 02I, not before REV begins from `allow_review` |
| `WS-ARCH-001-05` | REV/CON admission, inherited reviewer-policy lineage, packet, claim, decision and revision coordination parent | L1 | Independent schema/packet foundations may proceed; live admission/claim waits for canonical `allow_review` and exact AUTH gates; review claim copies the admitted Submission's immutable attempt version and only verifies upstream Task/Assignment equality, with no CON lookup; must split before implementation |
| `WS-ARCH-001-06` | Mandatory atomic Review/FinalAcceptance/TASK/CON contribution-and-award coordination | L1 | Non-executable placeholder; CON-03C/07 must precede first Review commit; requires a split contract |
| `WS-ARCH-001-07` | Supporting-module repairs and empty-ledger closure | L1 | Non-executable placeholder; requires a split contract |

Parent chunks 02-06 are coordination contracts, not permission to combine an
entire product milestone into one PR. Each is split further when its exact
feature contract crosses more than one reviewable mutation boundary. The
02A-02I sequence is the executable split of parent 02, subject to plan review
and human approval.

CP04-CP09 and chunks 03A-04F are non-executable planning skeletons. Before implementation,
each must be replaced with a current-main contract that names exact allowed and
not-allowed files, migration head, runnable commands, reviewers, and the public
types it extends. Their sequencing is approved here; their current text does
not authorize code changes. CP03 is split/non-executable; CP03A and CP03B are
the current-main executable exceptions and authorize only their ordered exact
implementations after these contracts merge.

PLAN4 does not insert a new prerequisite into the product sequence. Each
current or future delivery chunk applies its no-new-debt and touched-debt rules
within the capability it already owns. WS-ARCH-001-07 is refreshed and split
only for stranded debt after remaining v0.1 delivery boundaries are known.
