# Status: WS-AUTH-001 - Workstream Authorization Service

## Current status

Planning merged through PR #91 as
`ad6d6444e497b76d7cb925f3b0999ed4b74a3dac` after required internal reviews,
Agent Gates, and Backend passed. CodeRabbit produced a walkthrough with no
actionable findings, then its final check was cancelled when the PR closed.
D4-D10 were explicitly approved and WS-AUTH-001-01 was started by the user on
2026-07-11. The final branch head `b5217e1` passed required internal reviews,
Agent Gates, Backend, and CodeRabbit, then merged through PR #93 as `772af1d` on
2026-07-11. The user separately started `WS-AUTH-001-02` on 2026-07-11. Its
preimplementation plan review passed, and the user explicitly approved D12's
exact production dependency changes. After a coverage-priority pause, the user
explicitly resumed AUTH in its separate worktree on 2026-07-12. Bounded runtime
implementation and repair review are complete on reviewed code SHA `47dd5a7`;
all required internal tracks passed and PR #107 merged as `060b780` on
2026-07-13. The user then explicitly started `WS-AUTH-001-03`. Its L1
preimplementation plan review passed with conditions. Bounded implementation,
repair, and all required internal reviewer tracks now pass on reviewed code SHA
`8c5334c`, including external repair implementation `4923b67`. PR #108 merged
to `main` as `5c47aba`; that main revision is integrated into AUTH, whose prior
lifecycle reconciliation was reviewed at `a70b89c`. Backend, Agent Gates, and
CodeRabbit passed on final branch head `43ffbfe`, then explicit human approval
merged PR #109 to `main` as `f06532e` on 2026-07-13. AUTH-03 post-merge memory
merged through PR #110 as `1864867`. The user then explicitly started AUTH-04.
Required L1 plan review rejected the combined request/error/rate-control scope
before runtime edits and required a split. AUTH-04A's final repaired contract
passed both required preimplementation reviews at `f98bbfc`. Implementation
candidate `2a129f4` then entered required internal review. Valid OpenAPI,
logging, behavior-proof, and lifecycle-evidence findings were repaired; all
required tracks pass on production SHA `cdcaf77`, and final test-only head
`4fd6db9` passed exact-head confirmation for the additive scalar-context and
logging-state behavior-test repairs plus lifecycle evidence.
Backend, Agent Gates, and CodeRabbit passed on final branch head `36c4aa5`, then
explicit human approval merged PR #111 to `main` as `90c9a28` on 2026-07-13.
AUTH-04A post-merge memory merged through PR #112 as `7749f54`. The user then
explicitly started AUTH-04B; its required L1 preimplementation review rejected
the first activated contract before runtime edits. The second
repaired contract passed all required tracks at `b5dceb1`; bounded runtime
implementation and deterministic evidence are complete, and the candidate is
internally approved at final SHA `922778b`; reviewed production SHA is
`67484b5`. The Backend CI isolation repair passed exact review at `4fb846c`.
Final branch head `94fb2fe` passed Backend, Agent Gates, and CodeRabbit, then
explicit human approval merged PR #113 to `main` as `05a63c8` on 2026-07-14.
AUTH-04B post-merge memory merged through PR #114 as `97cd0f5`. The user then
explicitly started AUTH-05. Required L1 plan review rejected the combined
audit/idempotency contract before runtime edits and required children 05A and
05B. The first repaired AUTH-05A contract passed at `7a9023b`, but exact-SHA
implementation review demonstrated that closed privacy registries and readable
typed/SQL parity require a larger readable contract. The repaired contract
passed at `7cc6058`, but numeric hard stops repeatedly interrupted the atomic
typed/database parity boundary. The human replaced the line cap with AUTH-05A's
semantic scope, acceptance criteria, behavior evidence, and review gates;
runtime repair, deterministic evidence, and required reviews then completed.
Backend passed 949 tests at 82.77 percent global coverage, Agent Gates and
CodeRabbit passed, and explicit human approval merged PR #115 as `8e1cde6` on
2026-07-14. AUTH-05A post-merge memory then merged through PR #116 as `ab49b73`.
The user requested action/resource catalogue reconciliation before AUTH-05B.
That docs-only work passed required internal reviews, Backend, Agent Gates, and
CodeRabbit; explicit human approval merged PR #117 as `4c5d4fc` on 2026-07-14.
Its post-merge memory merged through PR #118 as `eba7e2b`. AUTH-05B's repaired
L1 plan passed before runtime edits. Implementation, repair, focused evidence,
and all required internal review tracks passed at reviewed runtime SHA
`e083890`. Backend passed 965 tests at 83.26 percent global coverage and 91.07
percent artifact-foundation coverage; Agent Gates and CodeRabbit passed. The
user explicitly approved PR #119, which merged as `ad71c7e` on 2026-07-14.

## Active planning chunk

None. AUTH-05B is merged; AUTH-06 remains inactive.

## Active implementation chunk

None. This branch records AUTH-05B post-merge memory only.

## Current implementation branch

`codex/ws-auth-001-05b-post-merge-memory` in
`/home/abiorh/flow/workstream-authorization-service`.

## Chunk status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-AUTH-001-PLAN` | Merged | `authorization-service` | #91 | Merged as `ad6d644`; D4-D10 later approved. |
| `WS-AUTH-001-01` | Merged | `codex/ws-auth-001-01-adopt-authorization-baseline` | #93 | Authorization baseline, Contributor terminology boundary, scanner, and repository contracts; merged as `772af1d`. |
| `WS-AUTH-001-02` | Merged | `codex/ws-auth-001-02-verified-issuer-token` | #107 | Merged as `060b780`; reviewed code SHA `47dd5a7`. |
| `WS-AUTH-001-03` | Merged | `codex/ws-auth-001-03-legacy-actor-classification` | #109 | Merged as `f06532e`; reviewed code `8c5334c`; final branch head `43ffbfe`. |
| `WS-AUTH-001-04` | Split | `codex/ws-auth-001-04-request-api-controls` | - | Parent split before runtime implementation. |
| `WS-AUTH-001-04A` | Merged | `codex/ws-auth-001-04-request-api-controls` | #111 | Merged as `90c9a28`; production review `cdcaf77`; final branch head `36c4aa5`. |
| `WS-AUTH-001-04B` | Merged | `codex/ws-auth-001-04b-postgres-rate-controls` | #113 | Merged as `05a63c8`; production review `67484b5`; final branch head `94fb2fe`. |
| `WS-AUTH-001-05` | Split | `codex/ws-auth-001-05-authority-evidence` | - | Parent split before implementation into 05A and 05B. |
| `WS-AUTH-001-05A` | Merged | `codex/ws-auth-001-05-authority-evidence` | #115 | Merged as `8e1cde6`; reviewed code `ea16fd8`; final branch head `d023952`. |
| `WS-AUTH-001-CAT` | Merged | `codex/ws-auth-001-action-catalogue-reconciliation` | #117 | Merged as `4c5d4fc`; final branch head `5b4ec96`. |
| `WS-AUTH-001-05B` | Merged | `codex/ws-auth-001-05b-idempotency-invalidation` | #119 | Merged as `ad71c7e`; reviewed runtime `e083890`; final branch head `83ca3e2`. |
| `WS-AUTH-001-06` | Proposed | - | - | Canonical actor profile and identity link. |
| `WS-AUTH-001-07` | Proposed | - | - | Authorization kernel and permissions. |
| `WS-AUTH-001-08` | Proposed | - | - | Bootstrap and administrative grants. |
| `WS-AUTH-001-09` | Proposed | - | - | Actor/link states and service actors. |
| `WS-AUTH-001-10` | Proposed | - | - | Project contributor grants. |
| `WS-AUTH-001-11` | Proposed | - | - | Project identity/guide/source/read cutover. |
| `WS-AUTH-001-12` | Proposed | - | - | Project policy/setup mutation cutover. |
| `WS-AUTH-001-13` | Proposed | - | - | Task management and assignment cutover. |
| `WS-AUTH-001-14` | Proposed | - | - | Submission/checker/audit visibility cutover. |
| `WS-AUTH-001-15` | Proposed | - | - | Remaining system worker and obsolete authority removal. |
| `WS-AUTH-001-16` | Proposed | - | - | Conformance and live proof. |

## Blockers

AUTH-05A, CAT post-merge memory, and AUTH-05B have no remaining blocker and are
merged.
The combined AUTH-05 contract
was rejected before runtime changes because shared audit evidence and
idempotency/invalidation were not reviewable as one L1 change. AUTH-05A owns
migration `0018`; merged AUTH-05B owns migration `0019`. Non-test
operators must later supply explicit classification evidence rather than
inferred kinds before the owning canonical actor migration.

The proposed external catalogue cannot be adopted as a normative handoff: it
conflicts with `/api/v1`, AUTH-05A's merged 49-identifier persisted audit base,
current project and artifact models, and staged domain ownership. All 52
permission identifiers remain approved, including
`operations.task.start_override`, `operations.submission_gate.repair`, and
`operations.checker.retry`; the three recovery identifiers receive persisted
parity only in their owning later chunks. `WS-AUTH-001-CAT` retains only safe
registry/conformance rules. This is a scope decision, not an AUTH-05B runtime
blocker. PR #119 is merged as `ad71c7e`. AUTH-06 and POL-002-04 remain inactive
pending their recorded prerequisites and separate explicit user start signals.

AUTH-04B review evidence and its PR trust bundle are recorded at
`reviews/WS-AUTH-001-04B-internal-review-evidence.md` and
`reviews/WS-AUTH-001-04B-pr-trust-bundle.md`.

AUTH-04A review evidence and its PR trust bundle are recorded at
`reviews/WS-AUTH-001-04A-internal-review-evidence.md` and
`reviews/WS-AUTH-001-04A-pr-trust-bundle.md`.

AUTH-03 review evidence and its PR trust bundle are recorded at
`reviews/WS-AUTH-001-03-internal-review-evidence.md` and
`reviews/WS-AUTH-001-03-pr-trust-bundle.md`. Prior AUTH-02 evidence remains at
`reviews/WS-AUTH-001-02-internal-review-evidence.md` and
`reviews/WS-AUTH-001-02-pr-trust-bundle.md`.

Production issuer configuration and legacy non-test actor classification are
future implementation/live-proof inputs and are tracked explicitly in
`DISCOVERY.md` and chunk stop conditions.

The user accepted D13 on 2026-07-13: the target provider-neutral boundary is
`IdentityIssuerVerifier`, extending the shared `ExternalServiceAdapter`
convention and using its typed factory. The current verifier/configuration
names remain functional migration inputs. The atomic AUTH adoption requires
its own reviewed chunk after `WS-ART-001-01C` installs the shared foundation;
it is not part of the size-capped AUTH-04A request/error implementation.
