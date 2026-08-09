# Discovery

## Existing normative intent

- `.agent-loop/policies/architecture-boundaries.md` declares Workstream a
  modular monolith.
- `WS-AUTH-001/PLAN.md` says AUTH must not duplicate project/task queries,
  import feature repositories, or own feature mutations.
- `WS-AUTH-001-PREP` explicitly forbids feature repository imports in AUTH.
- `docs/spec_authorization_service.md` requires feature-owned resource loading
  and typed context composition.

The recovery restores existing intent; it does not introduce a new architecture.

## Current AUTH shape

AUTH is a flat package containing large mixed-responsibility files, including:

| File | Approximate lines |
|---|---:|
| `authorization/runtime.py` | 1,703 |
| `authorization/router.py` | 1,642 |
| `authorization/kernel.py` | 1,603 |
| `authorization/repository.py` | 789 |
| `authorization/prepared.py` | 940 |
| `authorization/catalogue.py` | 1,103 |

Large functions include the prepared binding composer and prelocked kernel
paths. Size is evidence of mixed responsibilities, not by itself the boundary
definition.

## Concrete dependency violations

Read-only import analysis found:

- ART has 20 direct import sites into AUTH internals.
- Projects have 29 direct import sites into AUTH internals.
- AUTH directly imports actor, audit, and project implementation; its project
  imports include project repositories/models.
- ART directly imports project, task, and checker implementation.
- Tasks and checkers directly import each other's and project implementation.

This initiative fixes the AUTH side first. It must define a reference pattern
that later initiatives apply to other modules.

## Existing useful seams

- `app.interfaces.auth` correctly isolates external token verification.
- Prepared authorization already has typed facts, opaque handles, single-use
  consumption, and caller-owned transaction semantics.
- Several feature paths already compose typed resource contexts before AUTH.
- The external adapter factory convention is established.

These behaviors evolve in place; no parallel evaluator, verifier, handle, audit
ledger, or transaction protocol is allowed.

## Test debt relevant to AUTH

- `test_authorization.py`: about 13,448 lines and 163 tests.
- `test_auth.py`: about 7,425 lines and 74 tests.
- Individual AUTH tests exceed 500 and 1,000 lines.

Tests combine setup, API calls, concurrency, persistence, and assertions. They
must be moved by behavioral ownership without deleting or weakening proof.

## Preserved work

Unfinished `WS-POL-003-03A` work is preserved on
`codex/ws-pol-003-03a-hidden-compilation-foundation` at commit `1a7242f2`. It is
not merged or claimed complete and must be rebased/adapted only after recovery.

## Unknowns to resolve in the foundation chunk

- The exact smallest stable public AUTH type set.
- Which current consumers can migrate mechanically and which require a
  feature-owned context loader.
- Whether actor and audit are platform foundations or must also be represented
  by injected ports at the AUTH boundary.
- Exact import exceptions needed during transition; the completed ledger must
  contain none.
