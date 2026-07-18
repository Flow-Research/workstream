# WS-AUTH-001-09D-A External Review Response

PR: `#148`

External review basis: branch head `e7f54c374482d097d8ecec77ba059448fa4b9a9f`

## Valid Findings

### Database And API Reason Normalization Differed

CodeRabbit correctly found that `ActorLifecycleBody` uses Python `str.strip()`
while the PostgreSQL lifecycle constraints used one-argument `btrim`, which
removes ordinary spaces but not tab or newline padding. A direct database write
could therefore persist a reason the public API would normalize.

The repair gives both ActorProfile and ActorIdentityLink lifecycle constraints
the exact 29 code points treated as whitespace by `str.strip()` across the
currently supported Python runtimes, including ASCII whitespace, non-breaking
space, Unicode separators, and ideographic space. Migration `0026` uses the
same expression for its pre-DDL dirty-row refusal and installed constraints.
Direct-write tests cover
all five lifecycle reason fields plus non-breaking space, and previous-head
dirty-row cases prove ASCII and Unicode padding stop the upgrade without
changing revision, schema, or data.

### Internal Review Evidence Was Stale

CodeRabbit and both GitHub workflows correctly found that the evidence file's
reviewed SHA preceded later non-evidence state changes. The evidence table also
placed an unrecognized `migration/data integrity` row between canonical rows,
causing the deterministic parser to stop before CI integrity, docs,
reuse/dedup, and test delta.

The repair requires all reviewer tracks to rerun against the final candidate.
The regenerated evidence will use only recognized canonical rows in its table,
record migration/data-integrity proof outside that table, and name the exact
reviewed SHA. No global queue or review-log file will change after that SHA.

### Full-Suite Migration Fixture Used An Invalid Reactivation

The replacement Backend run exposed one historical migration test helper that
reset a revoked identity link by clearing revocation fields directly. Migration
`0026` correctly rejected that unattributed reactivation. The first failure
left the shared migration fixture inactive, which caused the remaining 18
Alembic failures and 354 downstream setup errors.

The test-only repair disables both lifecycle history guards for explicit
fixture cleanup, restores profile and identity-link status plus all lifecycle
provenance to the neutral active state, and re-enables both guards in `finally`.
The original rollback-refusal assertion and the immediately following migration
test pass together, proving clean state transfer between tests. Production
guards and migration behavior are unchanged.

## Non-Actionable Warning

CodeRabbit's generic diff-local docstring percentage is not a configured
Workstream gate and does not distinguish production APIs from migration and
behavior-test helpers. Adding narration-only docstrings would not improve the
public contract or behavior proof. Existing repository Ruff, coverage, review,
and documentation gates remain authoritative and unchanged.

## Repair Evidence

- Direct installed-constraint and previous-head dirty-row migration nodes:
  `2 passed in 111.55s`.
- Full five-node lifecycle migration suite: `5 passed in 250.95s`.
- Historical rollback-guard cleanup plus following migration node:
  `2 passed in 110.04s`.
- Strict lifecycle request-schema node: `1 passed in 9.46s`.
- Focused Ruff and `git diff --check`: passed.
- Required exact-head internal review, replacement GitHub checks, CodeRabbit,
  and explicit human merge approval remain required.
