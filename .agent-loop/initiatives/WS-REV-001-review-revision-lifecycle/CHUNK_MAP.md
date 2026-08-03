# Chunk Map: WS-REV-001 Review And Revision Lifecycle

## Live sequence

Historical PLAN through PLAN3 and retired 02-family records remain evidence.
PLAN4 is the current-main end-to-end refresh after merged AUTH 02D.

| Chunk | Purpose | Gate | Status |
|---|---|---|---|
| `WS-REV-001-PLAN4` | Current-main full lifecycle replan | AUTH 02D merged PR #257 | Proposed planning PR |
| `WS-REV-001-03A1` | Queue and admission-idempotency persistence | PLAN4 approved | First proposed runtime child |
| `WS-REV-001-03A2` | Lease and preference persistence | 03A1 | Skeleton |
| `WS-REV-001-03B` | Normalized packet-manifest persistence | 03A2 + exact ART membership contract | Skeleton |
| `WS-REV-001-04A` | Immutable Review/finding/resolution/decision-request persistence | 03B | Skeleton |
| `WS-REV-001-04B` | FinalAcceptance and shared audit/outbox linkage persistence | 04A + shared audit/outbox | Skeleton |
| `WS-REV-001-05A` | Atomic final `allow_review` admission | 04B + exact TASK/CHECKER/ART handoff | Skeleton |
| `WS-REV-001-05B` | Concealed active-lease/one-offer/none query | 05A | Skeleton |
| `WS-REV-001-06A` | Atomic claim, policy freeze, packet freeze | 05B + 03B + CON freeze + ART packet proof | Skeleton |
| `WS-REV-001-06B` | Owned release and preferred decline | 06A | Skeleton |
| `WS-REV-001-06C` | Preference/lease expiry and lazy recovery | 06B + fixed service admission | Skeleton |
| `WS-REV-001-07A` | Lease-bounded packet/context/chain reads | 06C + ART 07A | Skeleton |
| `WS-REV-001-07B` | Immutable reviewer notes/findings | 07A | Skeleton; no evidence upload |
| `WS-REV-001-08` | Pure decision validator/effect plan | 07B | Skeleton; no canonical write |
| `WS-REV-001-09A1` | Review-rooted revision episode/preparation persistence | 08 + human round/deadline decision | Skeleton |
| `WS-REV-001-09A2` | TASK revision participant and context resolver | 09A1 | Skeleton |
| `WS-REV-001-09A3` | Contributor finding-response records | 09A2 | Skeleton; no evidence upload |
| `WS-REV-001-09A4` | Human prepared N+1 and checker-source XOR | 09A3 + TASK/ART submission cutover | Skeleton |
| `WS-REV-001-09A5` | Replacement-assignment preparation successor | 09A4 + AUTH replacement contract | Skeleton |
| `WS-REV-001-09B` | Finding replay/resolution/preferred return | 09A5 | Skeleton |
| `WS-REV-001-10` | Canonical Review/FinalAcceptance/TASK/CON transaction | 09B + CON participant + audit/outbox | Skeleton; first Review commit |
| `WS-REV-001-11A` | Queue inspection and privileged queue/lease commands | 10 | Skeleton |
| `WS-REV-001-11B` | Revision repair and obligation close | 11A | Skeleton |
| `WS-REV-001-11C` | Reconciliation persistence and service jobs | 11B | Skeleton |
| `WS-REV-001-11D` | Legacy closure and ART recovery delegation | 11C + ART recovery port | Skeleton |
| `WS-REV-001-12P1` | Deterministic projection handler | 11D + shared dispatcher | Skeleton |
| `WS-REV-001-12P2` | Artifact-reference reconciliation/projection rebuild | 12P1 + ART typed repair port | Skeleton |
| `WS-REV-001-12P3` | Notifications, admin reads, metrics, drain facts | 12P2 | Skeleton |
| `WS-REV-001-12A1` | Lifecycle release-controller persistence | 12P3 + dependency manifest | Skeleton |
| `WS-REV-001-12A2` | REV/TASK/CHECKER mutation fences | 12A1 | Skeleton |
| `WS-REV-001-12A3` | CON mutation/cutoff/drain fences | 12A2 + CON hooks | Skeleton |
| `WS-REV-001-12A4` | Operator transitions and crash recovery | 12A3 | Skeleton |
| `WS-REV-001-13A` | Dependency preflight and drill harness | 12A4 | Skeleton |
| `WS-REV-001-13B` | Pre-release docs/generated evidence | 13A | Skeleton |
| `WS-REV-001-13C` | Product routers and final conformance release | 13B + exact AUTH activations | Skeleton; sole release |

## Dependency shape

```text
AUTH 02D -> PLAN4 -> 03A1 -> 03A2
ART membership -> 03B -> 04A -> 04B
TASK/CHECKER/ART admission -> 05A -> 05B
CON freeze + ART packet -> 06A -> 06B -> 06C -> 07A -> 07B -> 08
human decision -> 09A1 -> 09A2 -> 09A3 -> 09A4 -> 09A5 -> 09B
CON decision participant -> 10
11A -> 11B -> 11C -> 11D
12P1 -> 12P2 -> 12P3 -> 12A1 -> 12A2 -> 12A3 -> 12A4
13A -> 13B -> 13C
```

Distinct owner initiatives may progress concurrently. A missing owner gate
blocks only its consumer child, not earlier independent REV persistence.

## Contract rule

Only PLAN4 and 03A1 are concrete in this planning refresh. Every later row is a
reviewed architectural skeleton and must receive an exact current-main child
contract before implementation. That contract must name exact allowed files,
migration head, symbols, tests, reviewers, and owner evidence.

## Stop

Planning does not start implementation. After human approval, start 03A1 only.
