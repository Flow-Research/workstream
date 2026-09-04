# Chunk Contract: WS-DOCS-001-04 Public v0.1 Roadmap

Status: Complete. Risk: L2. Outcome on merge: complete.

## Intent

Make `docs/roadmap_status.md` sufficient for a human reader to understand the
implemented product, hidden integrations, current critical path, and complete
remaining v0.1 release gates without reading `.agent-loop`.

## Allowed files

- `docs/roadmap_status.md`
- `README.md`
- `.agent-loop/CURRENT_STATE.md`
- `.agent-loop/initiatives/WS-DOCS-001-current-v01-documentation/CHUNK_MAP.md`
- `.agent-loop/initiatives/WS-DOCS-001-current-v01-documentation/STATUS.md`
- this contract

## Not allowed

- Runtime, schema, migration, CI, dependency, or authorization changes.
- Claims that planned or hidden behavior is live.
- Calendar promises or a second transient-work tracker.
- Rewriting historical review or contract evidence.

## Acceptance criteria

- The public roadmap distinguishes live, hidden, next, planned, and deferred.
- Every v0.1 lifecycle stage states implemented behavior and its remaining gate.
- The immediate dependency order through guide activation, task readiness,
  canonical `allow_review`, REV/CON, fulfillment, frontend, and pilot is clear.
- ContributionPolicy inheritance and human-revision rebase semantics match the
  canonical current plans.
- Open pull requests remain the sole transient-work view.
- README and current engineering state point readers to the public roadmap.

## Verification

```bash
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main --head-ref HEAD
python3 scripts/check_active_state_projections.py --base-ref origin/main --head-ref HEAD
```

## Review

Documentation and product/operations review are required. Architecture review
is required only to verify that the roadmap preserves subsystem ownership and
dependency order. No runtime or security claim changes.
