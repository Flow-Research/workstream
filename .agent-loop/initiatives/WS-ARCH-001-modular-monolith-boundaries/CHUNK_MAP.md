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
| `WS-ARCH-001-02G` | AUTH contributor preparation activation after the complete hidden path | L1 | Next durable boundary |
| `WS-ARCH-001-02H` | AUTH human/fixed-service consumption activation | L1 | Proposed after 02G |
| `WS-ARCH-001-02I` | Admission-only public API/dispatch cutover and complete legacy removal | L1 | Deferred after 02H plus split 03/04/05 remediation, revision, checker-output and REV admission prerequisites |
| `WS-ARCH-001-03` | PROJECT/TASK guide, locked-context, task and assignment capability repairs | L1 | Non-executable placeholder; requires a split contract |
| `WS-ARCH-001-04` | ART/CHECKER materialization, run and result capability repairs | L1 | Non-executable placeholder; requires a split contract |
| `WS-ARCH-001-05` | ART/TASK/REV reviewer packet and revision capability repairs | L1 | Non-executable placeholder; requires a split contract |
| `WS-ARCH-001-06` | REV/CON/COMP accepted-work and award handoff capability repairs | L1 | Non-executable placeholder; requires a split contract |
| `WS-ARCH-001-07` | Supporting-module repairs and empty-ledger closure | L1 | Non-executable placeholder; requires a split contract |

Parent chunks 02-06 are coordination contracts, not permission to combine an
entire product milestone into one PR. Each is split further when its exact
feature contract crosses more than one reviewable mutation boundary. The
02A-02I sequence is the executable split of parent 02, subject to plan review
and human approval.
