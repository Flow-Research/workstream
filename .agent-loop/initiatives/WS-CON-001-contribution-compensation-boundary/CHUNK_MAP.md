# Chunk Map: WS-CON-001 Contribution And Compensation

Each implementation chunk is independently bounded and reviewed. Current
status comes from merged code/tests and `docs/roadmap_status.md`; historical
signed-loop records do not make behavior live.

## Completed

| Chunk | Outcome | Status |
|---|---|---|
| `PLAN`-`PLAN3` | Original boundary and cross-initiative planning | Historical planning |
| `01` | Canonical specification and ADR 0016 | Merged PR #144 |
| `02A` | Shared transactional outbox persistence/append | Merged PR #155; migration 0029 |
| `03A` | Adapter-binding persistence | Merged PR #267; migration 0053 |
| `03B` | Contribution-policy persistence | Merged PR #274; migration 0055 |
| `PLAN5` | Complete-context human needs-revision rebase reconciliation | Merged PR #270 |

## Current reconciliation

| Chunk | Goal | Risk | Status |
|---|---|---:|---|
| `PLAN4` | Reconcile current main, ART/AUTH/REV changes, open PRs, and end-to-end order | L1 | Merged PR #261 |
| `PLAN5` | Reconcile complete-context human needs-revision rebase across guide, policy, REV, and CON contracts | L1 | Merged PR #270; no runtime |

## Core runtime chunks

| Chunk | Goal | Entry gate | Status |
|---|---|---|---|
| `03B` | Contribution-policy persistence | 03A | Merged PR #274; REV-03A2 FK is unblocked |
| `02C` | Shared lifecycle-audit participant | PLAN4; current AuditEvent contract | Implementation and deterministic proof complete; required postimplementation review pending; independent of dispatcher; required before REV-04B |
| `04A` | Hidden adapter-binding service | 03A + exact AUTH registration/PREP contract | Blocked on AUTH registration |
| `04B` | Hidden contribution-policy service | 03B + 04A + exact AUTH registration/PREP contract | Blocked on AUTH registration |
| `05A` | Legacy semantic cutover + initial TaskAssignment policy freeze and guarded human-revision rebase support | 04B + task/assignment/revision authority contract + row-classification decision | Proposed |
| `05B` | Legacy economic schema removal | 05A zero-consumer proof | Proposed |
| `06` | Reviewer policy lookup/freeze participant | 05B + REV lease contract/caller facts | Proposed; CON never owns lease |
| `03C` | ContributionRecord/CompensationAward persistence | 03B + merged REV Review/ReviewLease/FinalAcceptance targets | Proposed after REV-04B |
| `03D` | Delivery/receipt/status persistence | 03C | Proposed |
| `07` | Atomic flush-only review contribution/award participant | 03C/03D + 05A + 06 + stable REV revision lineage | Proposed; consumed by REV-10 |
| `02B` | Generic outbox dispatcher/recovery | AUTH dispatcher identity/action/matrix/context/PREP registration | Blocked on AUTH; required later, not before 03A/03B |
| `08A` | Outbound compensation delivery | 03D + 07 + 02B + 04A/04B + independent delivery authority | Proposed |
| `08R` | Bound callback rate control | 08A | Proposed |
| `08B` | Inbound fulfillment callback | 08R + independent callback authority/fence | Proposed |
| `10A` | Contribution/award product reads | 08B + exact AUTH read contracts | Proposed |
| `10B` | Operations requests/reads/drain observation | 10A | Proposed |
| `10C` | Reconciliation/projection executors | 10B + exact executor identities/actions | Proposed |
| `11` | Hidden release readiness and dependency manifest | 10C + REV/ART/AUTH integration gates | Proposed |

Deferred optional work:

| Chunk | Goal | Status |
|---|---|---|
| `09A` | Contribution evidence projection write | Deferred; requires new current ART/AUTH contract |
| `09B` | Authorized evidence read | Deferred after 09A; replacement contract required |

## Dependency view

```text
PLAN4
  -> 03A -> 03B ---------------------------> REV-03A2
                  -> 04A -> 04B -> 05A -> 05B
  -> 02C ----------------------------------> REV-04B

REV-04B + 03B -> 03C -> 03D
05B + REV lease/caller facts -> 06
REV revision lineage + 03C/03D + 05A + 06 -> 07 -> REV-10

AUTH dispatcher registration -> 02B
03D + 07 + 02B + 04A/04B -> 08A -> 08R -> 08B -> 10A -> 10B -> 10C -> 11
```

ART-03C is merged baseline evidence. Remaining ART submission/reviewer custody
and REV-03A1 may progress concurrently in their own branches; any open PRs are
integration input, not merged gates.

## Review requirements

All CON runtime chunks require senior engineering, QA/test, security/auth,
product/ops, architecture, docs, reuse/dedup, and test-delta review. Add CI
integrity for workflows, dependencies, test configuration, coverage, or
distributed-lane changes.

## Stop

CON-02C stops at its PR checkpoint. Do not begin another CON chunk
automatically. Binding creation/lifecycle behavior remains deferred and
existing ART/REV identities do not substitute for the future AUTH-approved
compensation adapter contract.
