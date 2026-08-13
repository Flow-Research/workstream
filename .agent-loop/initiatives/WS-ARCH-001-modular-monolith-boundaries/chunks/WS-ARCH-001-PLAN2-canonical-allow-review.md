# Chunk Contract: WS-ARCH-001-PLAN2 Canonical Allow-Review Reconciliation

Status: planned; planning-only. Risk: L1. Outcome on merge: repository plans
name one dependency-ordered path from current `main` through canonical
`allow_review`; no runtime behavior changes.

## Allowed files

- `.agent-loop/CURRENT_STATE.md`
- `docs/roadmap_status.md`
- WS-ARCH-001 planning, status, risk, decision, chunk and review files
- directly stale WS-POL-003, WS-ART-001, WS-AUTH-001 and WS-REV-001 status or
  chunk-map wording required for parity

## Not allowed

- Application, migration, workflow, dependency or test-runtime changes
- Action activation, route exposure or lifecycle-state changes
- Claiming that legacy `allow_review` satisfies the canonical milestone

## Acceptance criteria

1. The plan separates guide/task readiness, canonical checker completion, REV
   admission and later public cutover.
2. Every future child has one owner, one PR outcome and explicit dependencies;
   each is marked non-executable until a current-main contract supplies exact,
   non-overlapping file boundaries and runnable commands.
3. Technical-debt repair remains incremental and mandatory for touched edges.
4. Current-state and capability-ledger wording match merged 02H behavior.

## Verification and reviewers

Run Markdown-link and stale-wording checks plus `git diff --check`. Required
reviews: architecture, security, product/operations, senior engineering, docs
and reuse. Human focus: dependency truth and whether canonical `allow_review`
is the correct pre-REV milestone. Before readiness is reported, inspect the
collaboration session registry and record in the internal-review evidence that
all required reviewer sessions have returned final results and none remain
open.

## Merge state

- Outcome on merge: `planned`
