# Chunk Contract: WS-REV-001-09A - Revision Context Preparation And Resubmission

## Status

Non-executable split record. Controlled rebase remains rooted only in a human
`Review(needs_revision)`. Checker-caused remediation remains a distinct
CheckerRun-rooted path and is not treated as legacy.

## Children

- `WS-REV-001-09A1`: immutable Review-rooted, task-owned non-branching
  RevisionContextPreparation persistence after human approval of exact round/
  deadline semantics.
- `WS-REV-001-09A2`: task-owned preparation participant and guide-context
  resolver plus Task Context read. The participant uses 09A1 persistence and
  flushes through the caller's session; decision transaction composition and
  the single commit remain in chunk 10.
- `WS-REV-001-09A3`: human Review finding responses/evidence only.
- `WS-REV-001-09A4`: hidden prepared human N+1 task/checker participant. It adds
  the server-selected Submission-to-preparation binding and replaces 02C's
  checker-only N+1 guard with the exact version/source XOR: v1 has neither source;
  human N+1 has only `revision_context_preparation_id`; checker-remediation N+1
  retains only 02C's immutable `remediation_source_checker_run_id`. Later AUTH-14
  owns public request acknowledgement, authorization cutover, and activation
  after its contract amendment merges; it does not own these REV lifecycle
  columns or constraints.
- `WS-REV-001-09A5`: hidden replacement-assignment preparation transfer; later
  AUTH-13 owns public command/cutover/activation after its contract amendment.

Checker remediation creates no Review/finding/reviewer contribution, performs no
guide rebase, consumes no human revision round/deadline, and returns to open
routing. Human Review revision requires blocking-finding responses and later
prefers the prior reviewer.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
