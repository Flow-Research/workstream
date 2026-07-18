# WS-AUTH-001-XINT Internal Review Evidence

Reviewed code SHA: `bac3073b147a923a4f8d6479cf4ce8710df2ed49`
Reviewed at: `2026-07-17T06:13:00Z`
Reviewer run IDs: auth_xint_roles, auth_xint_art_service,
auth_xint_rev_con
Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, and reuse/dedup

## Deterministic Evidence

- Stale Workstream wording and stale authorization documentation checks passed.
- Markdown links passed for all changed Markdown files.
- All 80 agent-gate tests passed.
- Merge-intent validation passes with a null successor because trusted `main`
  does not contain an exact AUTH-09A contract; runtime priority remains a human
  work-queue decision.
- CodeRabbit's nine comments were triaged individually: eight valid contract,
  least-privilege, migration, and Markdown findings are fixed; the requested
  runtime `AuthorityClaimHandle` rewrite was rejected because it conflated the
  current idempotency proof with the future PREP capability.
- Exact external-repair review proves the future non-Pydantic
  `PreparedAuthorizationHandle` is bound to session/action/actor/idempotency/
  request identity without introducing a runtime change in this planning PR.
- A typed catalogue comparison proved the custody map contains exactly all 25
  current ART actions and all 19 current REV actions, with the canonical eight
  ART custody groups.
- `git diff --check` passed against trusted main `5d353b6`.
- No runtime, schema, migration, test, workflow, dependency, package, coverage
  configuration, or gate-script file changed.
- No local roadmap XLSX exists in this worktree, so spreadsheet verification was
  not applicable.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Reduced speculative contract fanout and retained only four executable bounded contracts. |
| QA/test | PASS AFTER FIXES | none | Catalogue deltas are order-independent, adjudicator invalidation stays dormant, and future activation requires real feature behavior proof. |
| security/auth | PASS AFTER FIXES | none | PREP has exact database lock ordering, crossed concurrency, caller-owned commit, and rollback requirements. |
| product/ops | PASS AFTER FIXES | none | Independent submitter, reviewer, and adjudicator grants and exact invalidation ownership match merged XINT. |
| architecture | PASS AFTER FIXES | none | The final map preserves XINT's canonical eight ART owners and feature/AUTH transaction boundaries. |
| CI integrity | PASS | none | No CI, test, coverage, dependency, workflow, or gate configuration changed or weakened. |
| docs | PASS AFTER FIXES | none | Public docs distinguish current historical owners from the post-custody invariant and use delta-based future counts. |
| reuse/dedup | PASS AFTER FIXES | none | Premature duplicated activation contracts were removed; future contracts materialize only from immutable feature manifests. |

## Findings Resolved

The first review rejected stale absolute catalogue totals, insertion of custody
inside AUTH-09A through 09E, an incorrect ART behavior owner, missing contract
sections, duplicated speculative activation contracts, an incomplete PREP lock
protocol, insufficient PR #132 convergence guarantees, unsafe additive-action
downgrade proof, weak feature activation test requirements, and premature
adjudicator obligation creation. Each finding was repaired before re-review.

The second review caught one remaining canonical mapping drift: retry had been
split into a ninth ART owner even though merged XINT assigns it to the Operator
custodian. The final head restores eight owners while requiring retry's own
evaluator, guards, behavior tests, and explicit availability assertion. It also
clarifies the current historical-owner exception in the operations runbook.

External review then tightened fixed-service versus human-only matrix proof,
PREP actor/request binding and substitution tests, blocked migration allocation,
exact-project role wording, migration `0024` refusal parity, and Markdown PR
references. The distinct future `PreparedAuthorizationHandle` is now explicit;
the existing runtime `AuthorityClaimHandle` remains the separate idempotency
reservation contract.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining Gate

PR publication, GitHub checks, CodeRabbit, and explicit human merge approval
remain pending. PR #132 must not merge until this reconciliation merges and its
runtime branch converges from trusted main with all reviewed migration and
cleanup guarantees preserved.
