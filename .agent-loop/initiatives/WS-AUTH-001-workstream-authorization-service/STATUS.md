# Status: WS-AUTH-001 - Workstream Authorization Service

WS-XINT-003-01 reconciles future REV activation custody and policy-writer
ownership. It changes no catalogue/runtime state: all registered REV actions
remain planned and four lifecycle actions remain unregistered.

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
L1 plan, implementation, repair, focused evidence, and required review tracks
passed before explicit human approval merged PR #119 as `ad71c7e`.
AUTH-06 then established canonical actor profiles and identity links. Its
runtime, migration, compatibility, privacy, and API evidence passed required
internal and external checks; explicit human approval merged PR #124 as
`f599551` on 2026-07-15. Signed automated memory stopped with AUTH-07 requiring
a separate start. The user explicitly started AUTH-07 on 2026-07-15; discovery
and required L1 plan review are complete. The repaired AUTH-07A contract passed
all required tracks at `beb85ac`; implementation, repair, deterministic
evidence, and required internal review pass at `478a819`. The canonical
review/revision amendment then passed exact-head review at `160af8a`, with 74
PermissionIds and 50 planned ActionIds.
That review rejected the combined AUTH-07 contract before runtime edits because
grant-backed/project APIs preceded their authority sources and the audit/API
ownership files were incomplete. Parent AUTH-07 is now split into 07A catalogue
and audit parity, followed by 07B kernel and actor self-action cutover. AUTH-07A
merged through PR #126 as `e9d72a1`; signed schema-v2 state verified that merge,
and the user explicitly started AUTH-07B. Its required L1 preimplementation
review passed with conditions. Implementation, deterministic evidence, review
repair, and all required internal reviewer tracks passed, then PR #130 merged
as `90eca12`. Signed schema-v2 memory verified that merge and stopped at
AUTH-08. The user explicitly started AUTH-08. Its inherited L1 contract failed
initial security/architecture, QA/product, and senior/CI/docs review before
runtime edits. The repaired contract passed all required preimplementation
tracks at `cbe7c6c`; bounded AUTH-08 implementation later merged through PR #131
as `aa0fdcd`. AUTH-09 was split before runtime implementation. PR #140 merged
the authoritative AUTH XINT reconciliation as `d541521`; PR #132 then merged
AUTH-09A as `299363a`. Signed memory stopped, and the user explicitly started
AUTH-09B from that trusted head. Its bounded implementation, external-review
repair, coverage repair, and required checks passed before PR #143 merged as
`053242b`. Signed memory stopped, and the user explicitly started AUTH-09C.
Its bounded implementation and external repair passed before PR #146 merged as
`0ffdabf`; signed schema-v2 memory at `eeb3dc2` recorded completion and stopped.
The user explicitly started AUTH-09D. Required L1 preimplementation review
rejected the combined lifecycle contract before runtime edits, so the parent was
split into 09D-A and 09D-B. After bounded external repair and exact-head review,
PR #148 merged AUTH-09D-A as `99ae4c9`; signed schema-v2 memory `cf8a3e8`
recorded the stopped gate and named 09D-B. The user explicitly started 09D-B
from that trusted head. Exact contract `9ec6390b` passed required L1
preimplementation review. Implementation, deterministic proof, required
internal review, and external checks passed before PR #152 merged as
`93dd392`; signed memory `912a6254` stopped and named the contributor
foundation. The user explicitly started that chunk; exact contract `2a21166d`
passed required L1 review. Initial exact-SHA implementation review found
diagnostic-privacy and proof gaps; bounded repair and deterministic evidence are
complete, and exact code SHA `4d1fc507` passed all nine internal tracks. PR #153
merged the contributor foundation as `8d5eb15` on 2026-07-19. No service caller
or consumer feature action is active.

## Active planning chunk

`WS-AUTH-001-12`; the user started it on 2026-07-29. Required L1
preimplementation review rejected the inherited combined runtime contract
before application-code edits. The repaired planning parent now splits runtime
work into 12A through 12H plus 12B2 and 12D2. All nine exact-plan reviewer
tracks passed after action-custody, canonical-lineage reuse, and fixed-service
setup-run binding findings were repaired.

## Active implementation chunk

None. Planning reconciliation is active after merged PR #295. No runtime chunk
may start until the unified `WS-POL-003` dependency graph and remaining AUTH,
ART, XINT, REV, and downstream contracts are reviewed and merged.
The concise new 12I/12B2/12F4/12G/12H records are dependency skeletons, not
implementation authority; each requires a then-current executable contract
with explicit path scope, commands, and named reviewers before human start.

## Current review branch

`codex/ws-pol-003-auth-plan-reconciliation`.

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
| `WS-AUTH-001-05B` | Merged | `codex/ws-auth-001-05b-idempotency-invalidation` | #119 | Merged as `ad71c7e`; reviewed runtime SHA `e083890`. |
| `WS-AUTH-001-06` | Merged | `codex/ws-auth-001-06-canonical-actor-profile` | #124 | Merged as `f599551`; final PR head `4a2193f`. |
| `WS-AUTH-001-07` | Split | `codex/ws-auth-001-07-authorization-kernel` | - | Required L1 review rejected the combined contract before runtime edits. |
| `WS-AUTH-001-07A` | Merged | `codex/ws-auth-001-07-authorization-kernel` | #126 | Merged as `e9d72a1`; 74 permissions, 50 planned actions, and action-aware audit parity only. |
| `WS-AUTH-001-07B` | Merged | `codex/ws-auth-001-07b-deny-default-kernel` | #130 | Merged as `90eca12`; signed memory passed. |
| `WS-AUTH-001-08` | Merged | `codex/ws-auth-001-08-bootstrap-admin-grants` | #131 | Merged as `aa0fdcd`; signed memory passed. |
| `WS-AUTH-001-XINT` | Merged | `codex/ws-auth-001-xint-reconciliation` | #140 | Merged as `d541521`; signed schema-v2 memory passed. |
| `WS-AUTH-001-09` | Split | - | - | Split into 09A through 09E before runtime implementation. |
| `WS-AUTH-001-09A` | Merged | `codex/ws-auth-001-09-actor-state-service-actors` | #132 | Merged as `299363a`; signed memory passed. |
| `WS-AUTH-001-09B` | Merged | `codex/ws-auth-001-09b-controlled-service-provisioning` | #143 | Merged as `053242b`; signed memory passed. |
| `WS-AUTH-001-09C` | Merged | `codex/ws-auth-001-09c-actor-identity-admin-reads` | #146 | Merged as `0ffdabf`; signed memory `eeb3dc2` passed and stopped. |
| `WS-AUTH-001-09D` | Split | `codex/ws-auth-001-09d-actor-identity-lifecycle` | - | Required L1 review rejected the combined contract before runtime edits. |
| `WS-AUTH-001-09D-A` | Merged | `codex/ws-auth-001-09d-actor-identity-lifecycle` | #148 | Merged as `99ae4c9`; signed memory `cf8a3e8` passed and stopped. |
| `WS-AUTH-001-09D-B` | Merged | `codex/ws-auth-001-09d-b-identity-link-lifecycle` | #152 | Merged as `93dd392`; signed memory `912a6254` passed and stopped. |
| `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` | Merged | `codex/ws-auth-001-contributor-foundation` | #153 | Merged as `8d5eb15b`; signed memory `66ab58d` passed and stopped. |
| `WS-AUTH-001-09E` | Merged | `codex/ws-auth-001-09e-fixed-service-runtime-admission` | #157 | Merged as `42a89b2d` on 2026-07-20. |
| `WS-AUTH-001-ART-CUSTODY` | Merged | `codex/ws-auth-001-art-custody` | #158 | Merged as `be2a79a2` on 2026-07-20; all 25 ART actions remain planned. |
| `WS-AUTH-001-REV-CUSTODY` | Merged | `codex/ws-auth-001-rev-custody` | #160 | Merged as `fe0e4492` on 2026-07-20; all 19 REV actions remain planned. |
| `WS-AUTH-001-PREP` | Merged | `codex/ws-auth-001-prep` | #162 | Merged as `c559d556` on 2026-07-21; adds no feature consumer or activation. |
| `WS-AUTH-001-10` | Proposed | - | - | Project contributor grants. |
| `WS-AUTH-001-11` | Planning split authored | `codex/ws-auth-001-11-project-read-cutover` | - | Exact hard-cutover inventory split into 11A, 11B, 11C1, and 11C2; signed automation remains the live-state authority. |
| `WS-AUTH-001-11A` | Merged | `codex/ws-auth-001-11a-project-read-catalogue` | #208 | Registered the project-read catalogue and migration `0035`; no activation. |
| `WS-AUTH-001-11B` | Merged | `codex/ws-auth-001-11b-project-identity-context` | #214 | Project identity and self authorization-context hard cutover; merged as `033654ac`. |
| `WS-AUTH-001-11C1` | Merged | `codex/ws-auth-001-11c1-setup-diagnostic-reads` | #216 | Setup-diagnostic read hard cutover merged as `2965a9f9` on 2026-07-28. |
| `WS-AUTH-001-11C2` | Merged | `codex/ws-auth-001-11c2-effective-policy-active-guide-reads` | #221 | Effective-policy and active-guide read cutover merged as `3fc323d7` on 2026-07-29. |
| `WS-AUTH-001-12` | Planning repair | `codex/ws-auth-001-12-project-mutation-cutover` | - | Combined runtime contract rejected; planning parent split into 12A-12H plus 12B2/12D2 before code. |
| `WS-AUTH-001-12A` | Merged | `codex/ws-auth-001-12a-project-mutation-catalogue` | #226 | Exact 18-action planned catalogue, typed resource/PREP scope, and migration `0041`; merged as `64dd9c98` with zero activation. |
| `WS-AUTH-001-12B` | Merged | `codex/ws-auth-001-12b-project-setup-service` | #227 | Fixed project-setup service identity and planned matrix only; zero activation and no actor/link seed. |
| `WS-AUTH-001-12B2` | Proposed | - | - | Setup-ledger activation after hidden POL-04A; POL-04B owns the live worker cutover. |
| `WS-AUTH-001-12C` | Merged | `codex/ws-auth-001-12c-project-create` | #229 | System-scoped project creation cutover merged as `67f2c14b`. |
| `WS-AUTH-001-12D` | Merged | `codex/ws-auth-001-12d-guide-draft-source` | #232 | Draft guide and source metadata mutation cutover merged as `99dc0b34`. |
| `WS-AUTH-001-12D2` | Superseded | - | #248 | XINT-003-02A/02B own immutable review/revision policy lineage and the sole authorized mutation path; 02B merged as `25fc27c4`. |
| `WS-AUTH-001-12E` | Merged | `codex/ws-auth-001-12e-guide-sufficiency` | #263 | Three guide-sufficiency actions plus fixed setup-service run PREP merged as `b510bc4f`. |
| `WS-AUTH-001-12F` | Planning split | `codex/ws-auth-001-12f-submission-artifact-policy` | - | Combined contract failed required L1 pre-start review; parent now activates nothing and delegates to 12F1-12F4. |
| `WS-AUTH-001-12F1` | Merged | `codex/ws-auth-001-12f1-submission-policy-foundation` | #286 | Submission-policy PREP, replay, provenance, and audit custody foundation merged as `5a4186cc`; zero activation. |
| `WS-AUTH-001-12F2` | Merged | `codex/ws-auth-001-12f2-manual-submission-policy` | #292 | Governed Project Manager append-only manual-draft create/update cutover merged as `81f281bd`. |
| `WS-AUTH-001-12F3` | Merged; transitional | `codex/ws-auth-001-12f3-service-derivation` | #295 | Merged as `99c0aaf0`; authority/provenance is reused, while its separate inference entry point is removed at POL-04B. |
| `WS-AUTH-001-12I` | Proposed | - | - | Activates hidden unified compilation request/execute only. |
| `WS-AUTH-001-12F4` | Proposed | - | - | Activates approval of the stored unified pre-submit component; no inference. |
| `WS-AUTH-001-12G` | Proposed | - | - | Activates deterministic stored post-submit projection; zero model calls. |
| `WS-AUTH-001-12H` | Proposed | - | - | Activates only a complete approved unified guide lineage. |
| `WS-AUTH-001-13` | Proposed | - | - | Task management and assignment cutover. |
| `WS-AUTH-001-14` | Proposed | - | - | Submission/checker/audit visibility cutover. |
| `WS-AUTH-001-15` | Proposed | - | - | Remaining internal service and obsolete authority removal. |
| `WS-AUTH-001-16` | Proposed | - | - | Conformance and live proof. |

Feature-gated registration and activation chunks are enumerated in
`CHUNK_MAP.md` and `ACTIVATION_CUSTODY.md`. Actions remain inactive until their
bounded implementation and required evidence are reviewed and human-merged;
planning artifacts do not activate or lock work.

## Blockers

AUTH-09C has no remaining blocker. PR #146 merged as `0ffdabf`; PR #148 merged
AUTH-09D-A as `99ae4c9`; and PR #152 merged AUTH-09D-B as `93dd392`. Signed
memory `912a6254` passed and stopped. The user explicitly started the
contributor foundation. Its first L1 review rejected an underspecified
identity-link race, migration diagnostic, resource-lock, clean-cut, and CI
contract before runtime edits. Exact repaired contract `2a21166d` passed every
required L1 track. Initial implementation candidate `e41c33c0` failed privacy,
proof, docs, and evidence review. Bounded repair and deterministic evidence are
complete; exact code SHA `4d1fc507` passed all nine internal tracks. PR/external
checks are current and aggregate coverage remains mandatory in Backend.
The user explicitly started AUTH-09E after contributor foundation PR #153 and
signed memory completed. Its first preimplementation review rejected missing
verification commands and an overbroad feature-resource revalidation claim.
The refreshed contract limits this chunk to AUTH-owned service authority
resolution/revalidation, defers feature-row recomposition to later activation
chunks, and passed all nine required L1 tracks. Runtime implementation is
merged through PR #157 as `42a89b2d`; all feature actions remain planned.

The four proposed REV lifecycle actions and review-evidence binding action are
blocked on complete feature-owned typed manifests. REV fixed services are also
blocked on exact identity-to-ActionId contracts. These are deliberate
registration gates, not reasons to weaken AUTH or invent catch-all authority.

AUTH-10 through AUTH-15 require exact action enumeration before each starts.
AUTH-10 additionally owns the clean cut across the typed `ProjectRole`, audit,
and idempotency contracts plus the current PostgreSQL validators recreated by
migration `0022`, removing obsolete `ProjectRole.BOTH` and replacement evidence.
AUTH-09B owns migration `0024` for service-link verification timestamp
semantics, ART owns `0025` for the ArtifactStore v2 clean cut, and AUTH-09D-A
owns `0026` for lifecycle evidence and profile reactivation provenance repair.
The contributor foundation allocates the then-current next migration after
09D-B merges. AUTH-10 through AUTH-15 no longer reserve fixed migration numbers;
each allocates from trusted `main` when its contract becomes executable.

AUTH-05A and CAT post-merge memory have no remaining blocker and are merged.
The combined AUTH-05 contract
was rejected before runtime changes because shared audit evidence and
idempotency/invalidation were not reviewable as one L1 change. AUTH-05A owns
migration `0018`; merged AUTH-05B owns migration `0019`. Non-test
operators must later supply explicit classification evidence rather than
inferred kinds before the owning canonical actor migration.

The proposed external catalogue cannot be adopted as a normative handoff: it
conflicts with `/api/v1`, AUTH-05A's merged 49-identifier persisted audit base,
current project and artifact models, and staged domain ownership. All 74
permission identifiers are approved, including
`operations.task.start_override`, `operations.submission_gate.repair`, and
`operations.checker.retry`; AUTH-07A gives those recovery identifiers exact
typed/PostgreSQL parity while AUTH-13/14 retain action activation and feature
behavior ownership. `WS-AUTH-001-CAT` retains only safe registry/conformance
rules. This is a scope decision, not an AUTH-05B runtime
blocker. PR #118, AUTH-05B PR #119, and AUTH-06 PR #124 are merged. AUTH-07 has
an explicit user start. Required review split it before runtime implementation;
the repaired 07A contract passed all required tracks at `beb85ac`; implementation
and repair passed at `478a819`, and the review/revision amendment passed at
`160af8a`. AUTH-07A then merged through PR #126. AUTH-07B has an explicit user
start and no prerequisite blocker; POL-002-04 remains inactive pending its own
authorization prerequisites and explicit start.

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
its own reviewed chunk after `WS-ART-001-02A1` installs the shared foundation;
it is not part of the size-capped AUTH-04A request/error implementation.
