# WS-ENG-009 Planning External Review Response

## Target

- Pull request: `#359`
- Reviewed head: `5f9bf82aed646baec31523abd4b9f7c8945b9227`
- Reviewer: CodeRabbit

## Comments addressed

1. **Current initiative ledger custody — addressed.** The cutover inventory now
   requires a row-by-row disposition for every non-historical
   `CURRENT_STATE.md` entry.
2. **Complete Agent Gates equivalence — addressed.** `PLAN.md` maps every
   existing gate to its preserved or explicit Commitrail successor, and the
   cutover contract lists the complete post-cutover command set.
3. **Permanent legacy-path prevention — addressed.** A repository-owned
   negative regression check in Agent Gates must reject restoration of
   `.agent-loop` and retired signed-loop machinery.
4. **Intent scope contradiction — addressed.** Product/runtime/API behavior is
   immutable; engineering-process and CI enforcement are explicitly allowed to
   change while protections and human authority remain effective.
5. **Public-status gate — addressed.** Publication terms, canonical location,
   and blind stress-test evaluation evidence are all required.
6. **Internal record custody — addressed.** The inventory covers every tracked
   internal record containing normative or durable material, not only files
   referenced from outside the directory.
7. **Plan scope contradiction — addressed.** The outcome now distinguishes
   unchanged product behavior from intentional process/CI enforcement change.
8. **Validator coverage — addressed.** Positive single-record and multi-PR
   cases cover all durable dispositions; negative cases cover missing fields,
   invalid dispositions, transient state, inconsistent projections, and legacy
   restoration.

## Comments deferred

None.

## Human decisions needed

Human approval of the planning PR remains required. Public Commitrail release
terms and canonical distribution remain a later human decision and cannot be
inferred from this Workstream adoption.

## Commands rerun

- `python3 scripts/check_chunk_state_sync.py --base-ref edacdfdbb485f6959cb5d5f4f4def82bb713e1dd`
- `python3 scripts/check_active_state_projections.py`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `git diff --check`

## Remaining risks

The implementation must prove the relocation inventory is complete and that
the replacement validator preserves every mapped gate. This response approves
no implementation and is not merge authority.
