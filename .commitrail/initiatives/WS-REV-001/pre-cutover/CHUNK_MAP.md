# Chunk Map: WS-REV-001 Review And Revision Lifecycle

REV owns review/revision lifecycle behavior, not guide compilation or checker
orchestration. Every eligible Submission and packet retains the exact
`WS-POL-003` compilation, component, catalogue, and compiled-plan lineage.

## Live sequence

Historical PLAN through PLAN3 and retired 02-family records remain evidence.
PLAN4 is the current-main end-to-end refresh after merged AUTH 02D.

| Chunk | Purpose | Gate | Status |
|---|---|---|---|
| `WS-REV-001-PLAN4` | Current-main full lifecycle replan | AUTH 02D merged PR #257 | Merged PR #258 |
| `WS-REV-001-03A1` | Queue and admission-idempotency persistence | PLAN4 approved | Merged PR #262 |
| `WS-REV-001-03A2` | REV-owned lease and preference persistence | Merged 03A1 + CON-03B PR #274 policy-version FK target | Merged PR #280 |
| `WS-REV-001-03B` | Normalized packet-manifest persistence | 03A2 + ART-owned contract-only packet membership port published before ART-07A runtime | Skeleton |
| `WS-REV-001-04A` | Immutable Review/finding/resolution/decision-request persistence | 03B | Skeleton |
| `WS-REV-001-04B` | FinalAcceptance and shared audit/outbox linkage persistence | 04A + CON-02A outbox persistence + CON-02C audit participant | Skeleton; enables CON-03C schema work |
| `WS-REV-001-05A` | Atomic final `allow_review` admission | 04B + canonical WS-ARCH-001-04E admission-backed manifest carrying exact TASK/CHECKER/ART/AUTH facts and frozen submitter ContributionPolicyVersion lineage | Skeleton |
| `WS-REV-001-05B` | Concealed active-lease/one-offer/none query | 05A | Skeleton |
| `WS-REV-001-06A` | Atomic claim and REV-owned lease/packet freezes, including exact inherited `ReviewLease.reviewer_contribution_policy_version_id` | 05B + 03B + Submission-stamped attempt policy lineage in canonical admission + exact ART packet proof | Skeleton; claim performs no current-policy lookup |
| `WS-REV-001-06B` | Owned release and preferred decline | 06A | Skeleton |
| `WS-REV-001-06C` | Preference/lease expiry and lazy recovery | 06B + fixed service admission | Skeleton |
| `WS-REV-001-07A` | Lease-bounded packet/context/chain reads | 06C + ART 07A | Skeleton |
| `WS-REV-001-07B` | Immutable reviewer notes/findings | 07A | Skeleton; no evidence upload |
| `WS-REV-001-08` | Pure decision validator/effect plan | 07B | Skeleton; no canonical write |
| `WS-REV-001-09A1` | Review-rooted revision episode/preparation persistence | 08 + human round/deadline decision | Skeleton |
| `WS-REV-001-09A2` | TASK complete-context revision participant and resolver | 09A1 + TASK-owned locked/prepared-context contract; TASK internally validates policy through the CON-05A port | Skeleton; REV has no direct CON selection dependency |
| `WS-REV-001-09A3` | Contributor finding-response records | 09A2 | Skeleton; no evidence upload |
| `WS-REV-001-09A4` | Human prepared N+1 and checker-source XOR | 09A3 + TASK/ART submission cutover | Skeleton |
| `WS-REV-001-09A5` | Replacement-assignment preparation successor | 09A4 + AUTH replacement contract | Skeleton |
| `WS-REV-001-09B` | Finding replay/resolution/preferred return | 09A5 | Skeleton |
| `WS-REV-001-10` | Canonical Review/FinalAcceptance/TASK/CON transaction | 09B + CON-03C persistence + CON-07 participant + shared audit/outbox | Planned; first Review commit; every decision creates reviewer record, accept additionally creates submitter record |
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
AUTH 02D -> PLAN4 -> 03A1
CON-03B publishes FK target + REV-03A1 -> REV-03A2 owns lease persistence
ART contract-only membership port + 03A2 -> 03B -> 04A
CON-02A + CON-02C + 04A -> 04B -> CON-03C
TASK/CHECKER/ART admission manifest carrying frozen submitter policy version -> 05A -> 05B
Submission-stamped attempt policy lineage + ART packet proof -> 06A -> 06B -> 06C
REV lease/manifest -> ART-07A -> REV-07A -> 07B -> 08
human decision -> 09A1 -> 09A2 -> 09A3 -> 09A4 -> 09A5 -> 09B
REV Review/ReviewLease/FinalAcceptance schema -> CON-03C -> CON-07 decision participant -> 10
11A -> 11B -> 11C -> 11D
12P1 -> 12P2 -> 12P3 -> 12A1 -> 12A2 -> 12A3 -> 12A4
13A -> 13B -> 13C
```

Distinct owner initiatives may progress concurrently. A missing owner gate
blocks only its consumer child, not earlier independent REV persistence.
Current AUTH/XINT/CON status prose is not uniformly refreshed to current main;
each child must verify signed merge evidence and runtime symbols at start.

## Contract rule

PLAN4, 03A1, and 03A2 are merged. The next REV planning boundary is 03B. Every
later row remains an architectural skeleton and must receive an exact
current-main child contract before implementation. That contract must name
exact allowed files, migration head, symbols, tests, reviewers, and owner
evidence.

## Stop

Planning does not start implementation. Before implementing 03B, replace its
skeleton with a current-main executable contract and obtain human approval.
