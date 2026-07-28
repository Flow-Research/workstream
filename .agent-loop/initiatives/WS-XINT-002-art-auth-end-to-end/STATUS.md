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
  `WS-XINT-002-04B` read/binding. 04A cannot implement or activate until
  ART-03A is rebased onto the merged opaque PREP interface and merged; the
  preserved ART worktree's raw-context/local-authority seam is not activation
  evidence.

This file records only durable merged state and reviewed delivery order. It
does not describe a branch as “in progress”, “merge-pending”, or “active”;
GitHub branches and pull requests are the source of truth for transient work.
That rule prevents a merged PR from carrying stale pre-merge prose onto
`main`. The durable successor order remains in `CHUNK_MAP.md`; this status file
does not duplicate a transient “next chunk” pointer that becomes stale at
merge.
