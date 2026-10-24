# WS-GHPROOF-001-01 — Record the GitHub proof facts initiative

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: The repository records the intent, owner decisions, security limits and six-chunk plan for checking Harnessy proof against GitHub facts.

## Intent

Contributors need one durable entry point before the GitHub facts adapter,
checker comparison mode and POST wiring land in separate pull requests. The
owner refinements of 24 October 2026 change the earlier design, so they must be
recorded where implementers will read them.

## Current behavior

- `external_checkers/harnessy_proof/checker.py` validates only the shape of
  `proof.json` and states this trust limit in its header.
- `docs/engineering/local-agent-loop.md` documents the same limit.
- No GitHub client, setting or port exists under `backend/app`.

## Bounded change

### Allowed

- `.commitrail/initiatives/WS-GHPROOF-001/OVERVIEW.md`, this record and one
  `.commitrail/INDEX.md` row.

### Not allowed

- Product code, tests, configuration, documentation outside `.commitrail`, or
  roadmap edits.

## Design and decisions

The overview records the six chunks, their dependencies on PRs #676 and #677,
the security notes, the owner decisions and the eight integrity layers from
owner decision 20 (24 October 2026), with the chunk that owns each layer. Chunks 02 and 03 branch from this
record independently, so either can merge first.

The roadmap ledger is unchanged: this record adds no capability, exposure or
dependency on `main`.

## Acceptance criteria

- [x] The overview names intent, non-goals, the chunk map, dependencies,
  security notes and the dated owner decisions.
- [x] The index row and overview share the `Planned` disposition.
- [x] The overview lists every integrity layer, the deferred GitHub-side
  hardening and the current binding of required checks.

## Risk and review routing

- Risk class: L2, planning record only.
- Required reviewers: documentation.
- Human review focus: the owner decisions and the chunk order.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Records satisfy Commitrail structure | `python3 scripts/check_commitrail_records.py --base-ref origin/main` | Passes locally | Hosted Agent Gates owns the final result |
| Links resolve | `python3 scripts/check_markdown_links.py` | Passes locally | None |

## Review findings

None recorded.

## Reconciliation

- Current-source reconciliation: based on `main` after PR #674.
- Next usable boundary: chunks 02 and 03.
- Remaining risks: None introduced by this record.
