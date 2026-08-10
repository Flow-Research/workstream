# Decisions: WS-ARCH-001 Modular Monolith Boundaries

## D1: Keep twelve existing modules

Keep nine business modules (`actors`, `authorization`, `projects`, `tasks`,
`artifacts`, `checkers`, `reviews`, `contributions`, `compensation`) and three
supporting modules (`audit`, `outbox`, `api_controls`). Do not add a generic
workflow or orchestrator domain module.

## D2: Public API is the only runtime import surface

Outside a module, the only permitted runtime import prefix is
`app.modules.<target>.api`. Public APIs are capability-oriented and introduced
only with a real consumer.

## D3: Coordination does not transfer ownership

One contributor may edit several modules in one bounded cross-module chunk.
The worktree or coordinating initiative does not determine domain ownership.

## D4: Incremental strangler recovery

Freeze exact existing debt, reject new edges, and remove touched edges with
each delivery chunk. Do not perform a repository-wide reorganization.

## D5: Submission belongs to TASKS

TASKS owns immutable Submission creation and its predecessor chain. ART owns
ready-admission consumption and exact artifact binding through public ports.
The composed TASK application command coordinates the final transaction.

## D6: Existing specialist initiatives remain authoritative

`WS-AUTH-003` owns AUTH internals and its private-import ledger.
`WS-QUAL-002` owns behavior/test ownership. WS-ARCH-001 owns the canonical
module map, general cross-module dependency rule, and coordinated debt-removal
sequence.

AUTH edges are never copied into a WS-ARCH ledger. The general validator loads
WS-AUTH-003's canonical ledger through its existing parser and fails if the
AUTH-specific and general views diverge.

## D7: Application wiring is classified, not exempted

API delivery, adapters, durable workers, and legacy shared interfaces are all
scanned. Their current private product imports are protected debt and may not
grow. `backend/app/interfaces/**` is not a permanent public contract surface.
Database metadata discovery is a distinct infrastructure concern: only the
exact registered discovery path may import module model declarations, and that
exception grants no runtime command, repository, service, or authority access.
