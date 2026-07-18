# Risks: WS-AUTH-001 - Workstream Authorization Service

## Classification

- Initiative direction/auth/data-model strategy: L0, human-led; D1-D10 approved
  by the user on 2026-07-11 before `WS-AUTH-001-01` activation
- Bounded implementation chunks: L1 after the L0 planning gate
- SLA: P1
- Work type: architecture, authentication, authorization, migration, audit
- Human gate: required for every implementation PR and merge
- Budget posture: deep reasoning and full required reviewer fanout

## Risk register

| ID | Risk | Impact | Mitigation | Proof |
|---|---|---|---|---|
| A1 | Token roles remain authoritative on one path | Privilege escalation | Remove role-based helpers surface by surface; repository scan gate | Negative token-role tests and zero runtime `require_any_role` uses at final gate |
| A2 | Parallel actor models survive cutover | Ambiguous identity and authority | One migration design, no `V2` model, explicit legacy metadata disposition | Metadata/model inspection and migration tests |
| A3 | Legacy actors are misclassified | Service actor gains human authority or history breaks | No inference from email/subject/roles; fail-closed classification gate | Non-empty ambiguous migration failure test |
| A4 | Bootstrap races or the final Access Administrator is lost | Multiple trust roots or administrative lockout | Bootstrap and every final-admin-removal path lock `AuthorityControl(id=1) FOR UPDATE` before the effective-admin check and mutation | Different-target concurrent bootstrap plus revoke/suspend/deactivate concurrency tests |
| A5 | Cross-project grant or IDOR | Unauthorized project access | Canonical DB resource resolution and composite ownership constraints | Cross-project read/mutation tests |
| A6 | Revocation loses a race to mutation | Revoked actor commits sensitive change | Revalidate grants and state inside sensitive transaction | Grant-revoke versus command concurrency test |
| A7 | Internal service job trusts serialized authority | Stale grant remains effective | Serialized context is evidence only; reload current authority before commit | Revoked queued-command test |
| A8 | JWKS outage weakens verification | Unverifiable token accepted | Pinned algorithms, bounded cache, one refresh, fail closed | Cache/rotation/outage contract tests |
| A9 | Claims or personal data leak | Security/privacy incident | Minimal verified token type, bounded logging, no raw token/JWKS persistence | Log/error/audit redaction tests |
| A10 | Approval provenance breaks | Existing policy activation becomes unreadable or forgeable | Preserve historical values; new actions reference matched local grant | Migration and project approval tests |
| A11 | API namespace forks | Client and documentation drift | Adopt `/api/v1` only and update references together | Route/OpenAPI and stale-reference scan |
| A12 | Existing intake regresses | Project/task/checker pipeline stops | Run full current suite and API drill after actor migration and each cutover surface | Existing backend suite and live drill |
| A13 | Auth initiative becomes one oversized PR | Review failure and hidden coupling | Sixteen bounded implementation chunks, one active at a time | Circuit-breaker and PR-size evidence |
| A14 | Later WS-POL work resumes on obsolete auth | Rework and inconsistent authority | Keep WS-POL-002-04 inactive until PR #90 merges, auth proof exists, and the user starts it | Loop-memory gate |
| A15 | Authority mutation ships before durable evidence | Missing provenance cannot be reconstructed | Introduce correlation/idempotency/shared audit with canonical actor persistence | Atomic state+idempotency+event tests in every authority chunk |
| A16 | Identity-link revocation strands final administrator | Administrative lockout despite active grant row | Apply AuthorityControl lock to link revoke plus grant/profile changes | Mixed concurrent link/grant/profile final-admin tests |
| A17 | Canonical actor migration deletes typed-profile workflow eligibility before task/submission cutover | An intermediate merged release cannot claim, start, or submit work | Bounded non-authoritative workflow-eligibility adapter in chunk 06; remove task consumers in 13 and final consumer plus adapter in 14 | Full suite/API drill after chunks 06, 13, 14, and scanner proof in 15 |
| A18 | Authority evidence is mutable or denial events arrive late | Security decisions cannot be reconstructed | Insert/read-only repository API, database append-only enforcement, per-mutation allowed/denied event proof, operational retention controls | Update/delete rejection plus atomic allowed/denied event tests in owning chunks |
| A19 | Authority invalidation releases a needs-revision task as ordinary ready work | Prior findings, context, supersession, or replay obligations are bypassed | Keep the task in needs_revision with a durable unassigned obligation and controlled replacement assignment | Replacement-contributor revision-context, supersession, and high/medium replay tests |
| A20 | Rate-limit replicas split counters, leak identity keys, lose increments, or retain pseudonymous rows indefinitely | Abuse controls bypassed or privacy/availability incident | Canonical Base64 HMAC secret, exact framed digest, one committed PostgreSQL statement, coordinated quiesced rotation, bounded opportunistic pruning, and operator idle cleanup | Known-answer/privacy tests, synchronized independent-session concurrency, commit-failure proof, rotation runbook, and retention tests |
| A21 | Kernel APIs ship before their grant/resource authority exists | Fabricated authority, deny-only public surfaces, or hidden dual policy | Split AUTH-07 into 07A catalogue/audit and 07B self-only kernel; defer admin definitions to 08 and project context to 10 | Child-contract plan review, exact active-action tables, and no-grant/no-project surface scans |
| A22 | Combined project role couples submitter, reviewer, and adjudicator authority | One revocation removes unrelated capability or forces replacement | One active immutable grant per actor/project/role; no cross-role replacement | Three-role issue/revoke/regrant concurrency and invalidation tests |
| A23 | Service token enters human admission or uses another service row | Privilege escalation across human/service or workload boundaries | AUTH-09E fixed service admission and closed static matrix | Cross-service, human/service, inactive-link, and transaction-revalidation denials |
| A24 | Feature owner labels remain executable activation custody | Dual writer or action activation before behavior exists | Atomic ART/REV owner transfers to exact AUTH chunks | Exact owner/mapping/count parity and all-planned denial |
| A25 | Sensitive feature mutation evaluates stale pre-lock facts or crosses an inverse lock path | Revoked authority commits business state or transactions deadlock | Exact AuthorityControl/principal/profile/link/grant order, code-only service validation, then feature locks through a session/action-bound single-use prepared handle | Crossed link-revoke, suspend/deactivate, grant-revoke, final-admin, authority-loss, handle-reuse, cancellation, and rollback concurrency tests |
| A26 | Current validators keep `both` or replacement evidence | Combined authority survives the clean cut or history is silently converted | AUTH-10 replaces current typed/SQL validators and fails closed on obsolete evidence | Prior-head migration, no-conversion, downgrade-refusal, and stale-token tests |
| A27 | Wrong role invalidation reaches the wrong consumer | Reviewer/adjudicator revocation releases submitter work or one role removes another | Exact role in grant, cause event, obligation, and consumer filter | Three-role revoke/regrant and wrong-consumer negative tests |
| A28 | AUTH invents incomplete REV/ART/CON resource or service contracts | Cross-domain privilege, deadlock, or unreviewable coupling | Block registration until immutable feature manifests name facts, guards, service identity, and transaction owner | Registration gate plus manifest and cross-service parity tests |
| A29 | PR #132 convergence drops reviewed migration or cleanup repairs | Migration replay imports mutable runtime code, wheel installs fail, or cleanup hides the original error | Preserve frozen packaged contract, script-owned root, location-independent replay, same-loop cleanup, and original-exception precedence | Exact-head internal re-review plus wheel replay and cancellation/cleanup tests |
| A30 | Provisioning fabricates service-token verification | An untested service identity appears recently authenticated | Nullable service-link verification timestamp in `0024`, explicit human timestamp writes, and AUTH-09E-only service verification updates | Upgrade/downgrade, create/replay/denial/failure timestamp state-table tests |
| A31 | Service provisioning crosses inverse actor/link locks | Administrative and lifecycle mutations deadlock or admit stale authority | Canonical AuthorityControl -> profile -> exact link -> exact grant order before fixed-identity and issuer/subject advisory locks | Independent-session same-key, identity collision, revoke/lifecycle crossing, rollback, and no-deadlock proof |

## Required reviewers

Every implementation chunk requires:

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- reuse/dedup
- test delta when tests change
- docs when docs or public contracts change
- CI integrity when workflows, scripts, dependencies, or test configuration change
