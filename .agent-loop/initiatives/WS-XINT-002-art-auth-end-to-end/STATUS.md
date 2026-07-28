# Status: WS-XINT-002 ART-AUTH End-to-End Contract

## Durable completed state

- `WS-XINT-002-PLAN` is merged.
- `WS-XINT-002-01` is merged on `main` at merge commit `89956cff`; the closed
  ART catalogue and fixed-service matrix are reconciled without activating any
  new action.
- `WS-XINT-002-02` is merged on `main` at merge commit `f4cebb08`; durable ART
  mutation requests use the opaque transaction-bound PREP interface.
- `WS-XINT-002-03` is merged on `main` at merge commit `4336664a`; verifier,
  scheduler scan, and put-resolver authority are active with hosted artifact
  coverage at 90.02 percent.
- Guide activation is split into `WS-XINT-002-04A` ingest and
  `WS-XINT-002-04B` read/binding. ART-03A merged through PR #215 at `bb9082a7`
  and provides the PREP-compatible guide-ingest seam. Pre-implementation review
  for 04A found two required corrections: add the existing ingest permission to
  the canonical Project Manager policy, and complete ART-owned final lineage
  locking across the project, draft guide, snapshot, and item. The corrected
  04A contract owns those narrow changes before activating guide ingest.

This file records only durable merged state and reviewed delivery order. It
does not describe a branch as “in progress”, “merge-pending”, or “active”;
GitHub branches and pull requests are the source of truth for transient work.
That rule prevents a merged PR from carrying stale pre-merge prose onto
`main`. The durable successor order remains in `CHUNK_MAP.md`; this status file
does not duplicate a transient “next chunk” pointer that becomes stale at
merge.
