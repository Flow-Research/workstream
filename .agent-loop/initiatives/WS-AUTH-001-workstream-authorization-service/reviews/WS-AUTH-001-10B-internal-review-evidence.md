# WS-AUTH-001-10B Internal Review Evidence

Reviewed code SHA: `746e577adca41d81cc0fbc9ee12dfbab12aac464`

Reviewed planning SHA: `25b6ae134e3e3db4350fbcbb5c7cfeaa9e261044`

Reviewed against trusted main: `92b8a7aa813c5914d8191547b62eb3823a37a140`

Reviewed at: `2026-07-22T00:30:00Z`

Reviewer run IDs: original `auth10_plan_core`, `auth10_plan_security_qa`, and
`auth10_plan_ops_ci_docs`; integration `auth10b1_final_core`,
`auth10b1_final_security_qa`, and `auth10b1_final_ops_docs_ci`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Scope

AUTH-10B is a planning-only parent. It records D33 and splits implementation
into 10B1 durable authorization-read rate control followed by 10B2 privacy-safe
project-role disclosures. It changes no runtime, migration, workflow, test,
public documentation, route, action availability, or authored live status.

## Deterministic evidence

- Stale authorization documentation: PASS.
- Stale Workstream wording: PASS.
- Markdown links: PASS for all nine changed Markdown files.
- Merge-intent validation: PASS; the only new schema-v2 intent names exact
  same-initiative successor `WS-AUTH-001-10B1` and requires explicit start.
- `git diff --check`: PASS.
- `STATUS.md` is byte-identical to trusted main; signed automation remains the
  sole owner of live projection.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Durable counter and disclosure boundaries are independently reviewable. |
| QA/test | PASS AFTER FIXES | none | Migration races, rate ordering, concealment, cursors, schemas, and E2E proof are exact. |
| security/auth | PASS AFTER FIXES | none | Abuse control, audited concealment, minimal disclosure, and cursor secret isolation are fail closed. |
| product/ops | PASS AFTER FIXES | none | Rollout and recovery preserve submitter and project-owner data custody. |
| architecture | PASS AFTER FIXES | none | 10B1 owns persistence/control only; 10B2 owns exactly three reads. |
| CI integrity | PASS AFTER FIXES | none | 10B1 must add a new API-controls 90 percent gate without weakening existing gates. |
| docs | PASS AFTER FIXES | none | D33, plan, map, risks, and child contracts agree. |
| reuse/dedup | PASS AFTER FIXES | none | Existing PostgreSQL limiter is extended; no second limiter or unsigned cursor reuse is allowed. |
| test delta | PASS | none | This planning parent changes no tests or thresholds. |

## Findings resolved

Initial review failed because no reusable read-rate scope existed and current
403/404 translation could not conceal sensitive resources without preserving
denial evidence. The repaired plan originally allocated migration `0032` to
10B1 for one durable `authorization_read` scope and made 10B2 depend on it.
After ART merged its own `0032_artifact_recovery`, the unchanged AUTH migration
was rebased linearly to `0033_authorization_read_rate`. Further review froze
downgrade locking, exact capacity bounds, hosted 90 percent API-controls
coverage, action-aware concealment, nonhuman prelookup behavior, unique
candidate SQL, repository ownership, strict response fields, exact keyset
semantics, complete cursor rejection, operations guidance, and hosted E2E.

Valid findings addressed: yes

Open sub-agent sessions: none after evidence publication

## Remaining gate

GitHub Agent Gates, CodeRabbit, and explicit human review remain. After merge,
signed memory must stop at 10B1; implementation requires a fresh protected
explicit start on exact `main`.
