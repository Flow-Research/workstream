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
| `WS-ARCH-001-CP02` | Hidden adapter-binding lifecycle behavior | Complete on merge; actions remain unavailable |
| `WS-ARCH-001-CP03` | Adapter-binding activation parent | Split into CP03A/CP03B; non-executable |
| `WS-ARCH-001-CP03A` | Adapter target identity and owner eligibility | Executable contract complete on merge; actions remain unavailable |
| `WS-ARCH-001-CP03B` | Exact Finance Authority adapter-binding activation | Executable contract complete on merge; follows CP03A |
| `PLAN5` | Historical complete-context human needs-revision rebase reconciliation | Merged PR #270; continuing-TaskAssignment rebase retained, independent reviewer-selection wording superseded by current PLAN2 |

## Current reconciliation

| Chunk | Goal | Risk | Status |
|---|---|---:|---|
| `PLAN4` | Reconcile current main, ART/AUTH/REV changes, open PRs, and end-to-end order | L1 | Merged PR #261 |
| `PLAN5` | Reconcile complete-context human needs-revision rebase across guide, policy, REV, and CON contracts | L1 | Merged PR #270; historical baseline, current PLAN2 controls reviewer inheritance |

## Core runtime chunks

| Chunk | Goal | Entry gate | Status |
|---|---|---|---|
| `03B` | Contribution-policy persistence | 03A | Merged PR #274; REV-03A2 FK is unblocked |
| `02C` | Shared lifecycle-audit participant | PLAN4; current AuditEvent contract | Merged PR #277; independent of dispatcher; required before REV-04B |
| `04A` | Historical broad hidden adapter-binding contract | 03A + exact AUTH registration/PREP contract | Superseded by owner-separated ARCH CP01-CP03; callback authority is not a binding prerequisite |
| `04B` | Historical hidden contribution-policy contract | 03B + binding activation + exact AUTH registration/PREP contract | Superseded by ARCH CP04-CP05 |
| `WS-CON-001-05A` | Historical broad semantic cutover/validation/schema contract | unavailable behavior and cross-owner schema assumptions | Superseded by CP06 validation, CP07 PROJECT binding, CP08 TASK lineage, and CP09 removal |
| `WS-CON-001-05B` | Historical legacy economic schema removal | former 05A | Superseded by clean v0.1 CP09 without compatibility/backfill |
| `WS-CON-001-06` | Historical retirement contract for former reviewer claim-time policy lookup | Replaced by CP06 validation + CP07/CP08 persistence -> Submission -> ReviewLease inheritance | Superseded/non-executable retained evidence; do not follow its old 05A reference |
| `03C` | ContributionRecord/CompensationAward persistence | 03B + merged REV Review/ReviewLease/FinalAcceptance targets | Proposed after REV-04B and mandatory before live REV decisions |
| `03D` | Delivery/receipt/status persistence | 03C | Proposed |
| `07` | Atomic flush-only review contribution/award participant | 03C/03D + CP06/CP08 + stable REV revision lineage | Proposed; mandatory before REV-10/first Review commit |
| `02B` | Generic outbox dispatcher/recovery | AUTH dispatcher identity/action/matrix/context/PREP registration | Blocked on AUTH; required later, not before 03A/03B |
| `08A` | Historical outbound compensation delivery contract | old CON-04A/04B prerequisites are superseded | Non-executable retained evidence; requires a fresh current-main replacement after 03D + 07 + 02B + CP02/CP04 + independent delivery authority |
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
  -> 02C ----------------------------------> REV-04B

REV-04B + 03B -> 03C -> 03D
CP01A -> CP01B -> CP01C -> CP02 -> CP03A -> CP03B -> CP04 -> CP05 -> CP06 -> CP07 -> CP08
CP08 -> WS-ARCH-001-03A/03B replacement behavior -> WS-ARCH-001-03C activation -> CP09
task-locked policy lineage -> assignment -> Submission-stamped attempt lineage -> allow_review -> ReviewLease
REV revision lineage + 03C/03D + CP06/CP08 -> 07 -> REV-10 first Review commit

AUTH dispatcher registration -> 02B
03D + 07 + 02B + CP02/CP04 -> fresh delivery replacement -> 08R -> 08B -> 10A -> 10B -> 10C -> 11
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

CON-02C is merged. Do not infer that another CON chunk is active from this
sequence. Binding creation and lifecycle behavior remain deferred and
existing ART/REV identities do not substitute for the future AUTH-approved
compensation adapter contract.
