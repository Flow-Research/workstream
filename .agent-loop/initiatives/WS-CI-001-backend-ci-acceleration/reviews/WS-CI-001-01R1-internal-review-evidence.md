# Internal Review Evidence: WS-CI-001-01R1

Open sub-agent sessions: none

Valid findings addressed: yes

Reviewed code SHA: `5ec228960392cb87cf35852392ba25971a991f6f`

Reviewed at: 2026-07-20T18:28:58Z

Reviewer run IDs: senior-engineering/architecture/docs/reuse-dedup=`timeout_senior_docs`; QA/test/CI-integrity/test-delta=`timeout_ci_qa`; security/auth/product/ops=`timeout_sec_ops`

Final evidence head: `5ec228960392cb87cf35852392ba25971a991f6f`

## Binding

- Base: `b0f9ad6476bb836a99c0adac7073705eb5206f4c`
- Contract: `WS-CI-001-01R1 — Timeout Cleanup Repair`
- Scope: two child-timeout reductions, workflow regression assertions, and
  bounded R1 process evidence; no backend product runtime change

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS | None | Minimal repair with operationally sufficient observed runtime headroom. |
| QA/test | PASS | None | Values and minimum configured gaps are regression-bound. |
| security/auth | PASS | None | Cleanup remains exact; no auth, secret, or permission change. |
| product/ops | PASS | None | Operational headroom is distinguished from guaranteed cleanup duration. |
| architecture | PASS AFTER FIXES | None | R1 was added to the durable chunk map after PR #163 merge state was corrected. |
| CI integrity | PASS | None | No threshold, selection, required-check, or propagation weakening. |
| docs | PASS AFTER FIXES | None | Contract, chunk map, external response, and trust bundle agree. |
| reuse/dedup | PASS | None | Existing runner and workflow test boundary were reused. |
| test delta | PASS | None | One assertion set strengthened; no tests removed or skipped. |

## Findings repaired

- CodeRabbit found shard/API child timeouts exceeding their GitHub job budgets.
- Reduced shard child timeout from 12,600 to 4,800 seconds within 90 minutes.
- Reduced API child timeout from 3,600 to 1,500 seconds within 30 minutes.
- Added assertions binding both values and configured 600/300-second gaps.
- After PR #163 merged, rebased the repair onto trusted `main`, created bounded
  R1 artifacts and exactly one merge intent, and corrected the chunk map.
- Clarified that configured gaps provide operational headroom but are not
  guaranteed cleanup durations because setup consumes job time.

## Deterministic evidence

```text
Ruff formatting and lint: passed
shard + coverage-contract tests: 204 passed
isolated database runner against PostgreSQL: 16 passed
agent-gate workflow tests: 91 passed
Markdown links: passed
stale wording: passed
loop-memory state: passed
git diff --check: passed
```

## Hosted evidence

Initial repair PR #164 runs `29767792824` and `29767792536` failed fast because
this R1-specific internal-review evidence file was missing. No shard ran. This
file repairs that process-evidence gate; exact-head hosted rerun remains pending.

## Remaining gate

Hosted Backend, Agent Gates, CodeRabbit, human review, and explicit merge
approval remain mandatory.
