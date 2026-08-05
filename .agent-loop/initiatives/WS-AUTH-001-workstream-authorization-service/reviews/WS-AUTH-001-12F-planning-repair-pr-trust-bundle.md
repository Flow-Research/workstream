# Workstream PR Trust Bundle

## Chunk

`WS-AUTH-001-12F` — submission-policy planning repair

## Outcome

The unsafe combined runtime chunk is replaced by a zero-activation parent and
four explicit, sequential L1 child contracts:

1. 12F1 — PREP, replay, provenance, and migration foundation.
2. 12F2 — Project Manager manual draft create/update.
3. 12F3 — fixed-service automatic derivation and public inline-route removal.
4. 12F4 — Project Manager approval and atomic effective/pre-submit chain.

## Scope

Planning, custody, decision, risk, canonical authorization specification, and
current/future API documentation, plus one exact technical-path exemption in
the stale-wording scanner. No backend runtime, migration, action availability,
test, workflow, or test-gate change is included.

## Critical decisions

- Automatic service derivation is normal; manual drafting is a governed
  exception with distinct provenance.
- Prepared handles never cross external work, Celery, serialization, session,
  transaction, rollback, or commit.
- Approval locks and commits the complete upstream chain with replay and
  decision evidence.
- Workstream defaults and the immutable checker catalogue cannot be weakened.
- 12F4 owns only bounded downstream invalidation; 12G owns new post-submit
  behavior.
- 12G and 12B2 depend on merged 12F4, not the rejected parent.

## Evidence

```text
stale authorization documentation: passed after vocabulary repair
markdown links: passed
git diff --check: passed
unrelated REV/CI rollback against origin/main: none
all nine required L1 planning reviewer tracks: pass or pass with low risks
```

The roughly four-hour repository-wide backend suite is intentionally delegated
to GitHub Actions. Exact-head Agent Gates and the full hosted Backend matrix are
required before this planning PR is merge-ready.

## Human review focus

- Four-child split and sequencing.
- Fixed-service versus Project Manager authority.
- Exact sufficiency/default-catalogue/compiler custody.
- Approval atomicity and the narrow 12F4/12G boundary.
- Zero activation in this PR.
