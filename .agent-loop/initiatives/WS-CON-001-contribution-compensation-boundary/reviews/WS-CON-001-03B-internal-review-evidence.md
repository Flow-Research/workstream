# Internal Review Evidence: WS-CON-001-03B

## Scope

03B adds schema-only contribution-policy persistence: policy/version/rule/
award-definition lineage, project-configured compensation units, an immutable
migration-owned ISO 4217 registry, exact quantity validation, and PostgreSQL
guards. It adds no service, route, claim, award result, adapter execution,
AUTH/ART behavior, or public API.

Trusted main baseline: `b224971d9f207e7aa0925fcc12dad15900375a51`.
The user-owned archival PDF deletion is excluded from this chunk.

## Deterministic Evidence

```text
44 focused isolated PostgreSQL tests passed
1 additional isolated active-selector negative regression passed
1 canonical Alembic head upgrade/downgrade test passed
33 semantic-lane integrity tests passed
contributions module coverage: 95% (required at least 90%)
Ruff: passed
git diff --check: passed
Markdown links: passed
stale Workstream/review/authorization/artifact scans: passed
Alembic head: 0054_contribution_policy
```

The PostgreSQL proof covers complete and incomplete policy graphs, configured
unit provenance, exact decimal boundaries without typemod rounding, whole
project points, published/retired immutability, reparent rejection, truncate
rejection, active-selector uniqueness, and publish/child-mutation races.

## Review Results

| Track | Result | Resolution |
|---|---|---|
| Senior engineering | PASS | Null ISO bypass closed; reparent and migration concerns resolved. |
| QA/test | PASS | Independent graph, numeric, immutability, unit, and race proof added. |
| Security | PASS | Truncate bypass closed across every economic/provenance table. |
| Product/ops | PASS | Project-configured ISO/points semantics align with the canonical contract. |
| Architecture | PASS | Schema-only boundary and future REV FK remain stable. |
| Docs | PASS | Canonical spec, data model detail, and entity overview align. |
| Reuse/dedup | PASS | Shared compensation instrument enum reused. |
| Test delta | PASS | No removed, skipped, weakened, or masked coverage remains. |
| CI integrity | PASS | Fixed 90% hosted coverage gate and exact shared-foundations lane assignment added. |

## Deferred Boundary

Authorized policy mutation belongs to 04B. Contribution records and awards
remain in 03C after REV supplies stable Review, ReviewLease, and
FinalAcceptance targets. No next chunk starts automatically.
