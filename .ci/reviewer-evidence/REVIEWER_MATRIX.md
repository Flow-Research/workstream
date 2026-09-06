# Reviewer Responsibility And Evaluation Matrix

The shared evidence protocol owns target, provenance, freshness, finding, and
output mechanics. It also owns the closed proof-strength vocabulary and stable
escaped-failure pattern registry; `scripts/reviewer_contracts.py` owns their
deterministic compatibility validation. Each custom agent and matching
repository skill must prove the distinct specialty value below.

## Agent-to-skill map

This table is the single canonical reviewer registry. The deterministic
validator derives reviewer IDs and agent/skill paths directly from these rows;
there is no separately maintained code registry.

| Reviewer | Canonical ID | Custom agent | Repository skill |
|---|---|---|---|
| Architecture | `architecture` | `.codex/agents/architecture-reviewer.toml` | `.agents/skills/architecture-review/SKILL.md` |
| CI integrity | `ci_integrity` | `.codex/agents/ci-integrity-reviewer.toml` | `.agents/skills/ci-integrity-review/SKILL.md` |
| Documentation | `documentation` | `.codex/agents/docs-reviewer.toml` | `.agents/skills/docs-review/SKILL.md` |
| Product/operations | `product_ops` | `.codex/agents/product-ops-reviewer.toml` | `.agents/skills/product-ops-review/SKILL.md` |
| QA | `qa` | `.codex/agents/qa-reviewer.toml` | `.agents/skills/qa-review/SKILL.md` |
| Reuse/dedup | `reuse_dedup` | `.codex/agents/reuse-dedup-reviewer.toml` | `.agents/skills/reuse-dedup-review/SKILL.md` |
| Security | `security` | `.codex/agents/security-reviewer.toml` | `.agents/skills/security-review/SKILL.md` |
| Senior engineering | `senior_engineering` | `.codex/agents/senior-engineer-reviewer.toml` | `.agents/skills/senior-engineer-review/SKILL.md` |
| Test delta | `test_delta` | `.codex/agents/test-delta-reviewer.toml` | `.agents/skills/test-delta-review/SKILL.md` |

`plan-review` remains outside this nine-pair map because it has no matching
custom reviewer agent.

Use only the canonical IDs above in machine-readable reviewer and handoff
fields. Human-readable labels may still appear in prose.

## Adopted proof-quality responsibilities

### Dispatch and shared work

The lead selects specialties from the changed behavior, not a fixed nine-agent
checklist. Architecture/public ports route to architecture; authorization or
untrusted evidence to security; test/proof changes to QA and test delta; CI or
deterministic gates to CI integrity; current documentation to documentation.
Add product/operations, reuse, or senior engineering only for their actual
impact. One bounded assignment may cover related tracks, but must explicitly
apply each named skill and report each track's findings without inventing a
second independent review.

Give each reviewer a clean base/head, current record, owned impact cone, bounded
prior findings, and shared command artifacts—not the full conversation. The
shared protocol is loaded once, then the specialty skill. The lead owns common
checks and GitHub monitoring; reviewers independently inspect and run only
needed falsification probes. Collect findings before batching fixes and replay
only affected tracks against the new frozen target, including formerly passing
ones. Configure delegates as `gpt-5.6-sol` high and the lead as `gpt-6-astra`.

Historical blind adoption results below prove their original instruction
versions, not every later edit. Instruction changes need fresh scoped blind
exercises before claiming improved reviewer effectiveness.

All nine pairs consume the shared proof vocabulary, compatibility rules,
failure-pattern IDs, and discriminating test-of-the-test contract. They must not
infer custody from names or narrative evidence. Specialty additions are adopted
through the blind evaluation recorded by `WS-CI-005-03`:

| Reviewer | Adopted specialty obligation |
|---|---|
| Architecture | Composite ownership, schema/model/database parity, syntax-aware private edges, and composition-root wiring |
| CI integrity | Actual selected-test, service/PostgreSQL, session, artifact, coverage, aggregation, and required-status custody |
| Documentation | Proportionate structure/inspection proof without irrelevant database ceremony |
| Product/operations | Proportionate product evidence without database ceremony or leakage into product decisions |
| QA | A simulated pre-fix defect that the exact named test must detect |
| Reuse/dedup | Canonical-rule comparison across schema, service, public API, migration, and database constraint |
| Security | Actor/tenant/resource substitution, fail-open state, replay, concealment, and composite ownership |
| Senior engineering | Permissive-fake and misleading-abstraction probes balanced against proof cost |
| Test delta | Direct comparison with the pre-fix defect and a discriminating assertion |

| Reviewer | Must inspect | Representative must-find evaluation | Must-not-flag control |
|---|---|---|---|
| Architecture | ownership, public ports, private imports, dependency direction, ADRs, ledgers, scope | private cross-owner import or asymmetric owner/debt ledger | valid dependency through the canonical public port |
| CI integrity | workflows, commands, coverage floors, skips, runners, trust boundary | required gate weakened or PR-controlled code executed by a privileged workflow | separate advisory check that cannot mask required gates |
| Documentation | README, contributor path, current-state pages, glossary, links, historical/current distinction | merged capability still described as planned or a stale timeline presented as authority | clearly labeled historical evidence intentionally preserved |
| Product/operations | project manager, contributor, review assignee, revision, contribution, compensation, audit flow | engineering findings leaking into product review decisions | engineering evidence that does not change product lifecycle truth |
| QA | acceptance criteria, behavior, edges, negative paths, regressions | acceptance claim without a behavior test or a missed boundary case | implementation detail change with unchanged verified behavior |
| Reuse/dedup | existing ports, helpers, policies, templates, schemas, duplicated semantics | second target resolver, evidence schema, or owner adapter | specialty extension of the canonical abstraction |
| Security | authentication, authorization, data, secrets, untrusted input, audit, privilege | fail-open authorization or execution of untrusted PR content | read-only parsing of untrusted evidence with no execution |
| Senior engineering | simplicity, maintainability, operational failure, size, ownership | monolithic gate with coupled responsibilities and no rollback boundary | cohesive module within its explicit size and ownership contract |
| Test delta | weakened assertions, skips, deselection, coverage gaming, behavior fidelity | test rewritten to accept broken behavior or coverage-only assertions | refactor preserving assertions and observable behavior |

## Evaluation contract

Every reviewer/skill pair is evaluated independently with raw artifacts and
minimal task context. Each row requires:

1. a positive must-find fixture;
2. a negative false-positive control;
3. a stale-target or prior-finding replay fixture;
4. a malformed or incomplete receipt fixture;
5. a cross-specialty case proving the reviewer reports its own portion and
   routes, rather than invents, the other specialty's conclusion.

Fixtures record the expected finding class; prompts do not leak the prose answer.
Results bind to the exact review target. Repeated misses or invented evidence
prevent that reviewer/skill pair from being marked adopted.
The first adoption evidence must verify every path pair above exists, remains
one-to-one, and loads the shared evidence protocol.

## Historical replay set

The first suite includes the PR #338 misses: contract-path continuity, invalid
atomic outcomes, owner/public-port and private-import violations, mutation of
completed history, and machine/human debt-ledger asymmetry. It also includes a
stale README/current-state fixture and a CI gate-weakening fixture so docs and CI
reviewers prove distinct value rather than sharing architecture's examples.
