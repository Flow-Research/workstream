# WS-ARCH-001-02B PROJECT Public Capability Manifest

## Public package

`backend/app/modules/projects/api` exposes only dependency-safe immutable
contracts:

- `ProjectLockedPolicyContextRequest` carries exact TASK-stamped project,
  guide-version, source-snapshot, effective-policy, and pre-submit-policy
  selectors and hashes;
- `CanonicalJsonObject` copies a JSON mapping into canonical immutable text and
  exposes no parsed mutable projection;
- `ProjectLockedPolicyContextFacts` carries the exact guide ID/status,
  snapshot identity, effective-policy identity/status/body, pre-submit-policy
  identity/status/compiler, and compiled bundle;
- `ProjectLockedPolicyContextPort` defines the transaction-bound owner
  capability;
- the three lifecycle aliases and `ProjectLockedPolicyContextUnavailable`
  expose closed historical states and one stable failure code.

The public package imports no ORM model, repository, SQLAlchemy session, TASK,
ART, CHECKER, AUTH, mutable mapping field, guide content, source manifest,
source-item metadata, actor provenance, or audit evidence.

## Owner-local implementation

`ProjectRepository.lock_locked_policy_context(...)` locks rows in this order:

1. exact project;
2. exact project guide by project and version;
3. exact guide-source snapshot ID;
4. exact effective-policy ID;
5. exact pre-submit-policy ID.

It verifies every project, guide, version, snapshot, effective-policy, and
pre-submit-policy cross-link; recomputes the snapshot, effective-policy, and
compiled-bundle hashes; requires complete compiled fields; and returns only
canonical immutable facts.

Locked-context resolution never uses current/latest selectors. Exact rows that
were validly locked remain valid in their canonical `superseded` state.
Current successor substitution, draft/pending/incomplete rows, missing rows,
cross-project lineage, or stored-body/hash drift fail closed.

## Boundary disposition

This chunk changes no route, authorization availability, project lifecycle,
policy compilation, task preparation, ART behavior, or CHECKER behavior. Live
caller composition is deliberately deferred to a later contract with the
necessary application/composition paths. No session, repository, or concrete
PROJECT factory crosses the public boundary.

The eligible PROJECT implementation is registered as lifecycle behavior in the
existing ownership partition and exact additive-transition allowlist.

## Deterministic proof

- public canonical JSON copies nested caller data and exposes immutable text
  only;
- current and exact superseded locked rows resolve to identical canonical
  lineage identities;
- draft, pending, cross-project, successor-substituted, and hash-drifted
  contexts fail closed;
- PostgreSQL state-matrix tests exercise exact historical resolution, a
  two-session test proves pre-submit-row contention, and unit SQL assertions
  prove all five selected queries use `FOR UPDATE`;
- focused public API coverage is 100 percent;
- protected-base module-boundary and behavior-ownership validation pass;
- the focused capability tests live in a bounded PROJECT test module, and the
  frozen test-structure ledger records no new or grown structural debt;
- that bounded module is registered in the existing `project_lifecycle` CI
  lane;
- Ruff, Markdown-link, stale-wording, and diff checks pass.

The PostgreSQL cases run in hosted Backend/Agent Gates because this worktree
has no `WORKSTREAM_TEST_DATABASE_URL`; the chunk command fails fast when that
required database URL is absent.
