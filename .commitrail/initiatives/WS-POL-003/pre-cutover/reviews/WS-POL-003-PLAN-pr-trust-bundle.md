# WS-POL-003 Planning PR Trust Bundle

Historical evidence for the original planning PR. The current authoritative
split and dependency graph is `../CHUNK_MAP.md`; this file is not executable.

## Chunk

`WS-POL-003-PLAN` — Unified Project Guide Compilation planning.

## Goal and human-approved intent

Replace three complete Project Guide inference passes with one bounded unified
compilation per immutable setup generation, while retaining separate canonical
policy objects, approvals, authorization boundaries, and checker ownership.

Provide one internal typed checker-service facade with one complete pre-submit
command at sealed-scratch custody and one complete post-submit command after
verified storage/binding. No caller selects or invokes individual checkers.

## What changed and why

- Added the complete WS-POL-003 intent, discovery, plan, decisions, risks,
  status, and eight bounded implementation contracts.
- Consumed merged ART-04B1's exact catalogue/effective-plan contract and
  preserved future ART-04B2/04B3 as the sole pre-submit executor/evidence
  writer, with durable CHECKER/POL as the post-submit owner.
- Added exact future XINT/AUTH compilation request/execute custody before
  persistence can start.
- Made unified agent projections immutable, safe-text bounded, capability
  closed-world, and generation/hash bound.
- Deleted the temporary root planning draft after incorporating its valid intent.

The original draft had the right product direction but stale baseline,
ambiguous correction provenance, under-specified fixed-service authority, and
unclear phase execution/evidence ownership.

## Design and scope control

- One model invocation; no model policy authority.
- ART's complete pre-submit catalogue is consumed unchanged.
- No new checker registry, dynamic plugin, generated code, or compatibility path.
- Pre facade delegates once to ART and persists no duplicate evidence.
- Post facade uses CHECKER's sole durable writer.
- No application code, API, database, migration, workflow, or CI change.

Rejected alternatives include three repeated inference calls, one combined
canonical policy object, in-place edits to agent projections, broad compilation
authority, POL-local pre-submit maps, and per-checker product APIs.

## Acceptance evidence and test delta

This is documentation/planning only. Markdown links, stale wording, and diff
integrity pass. There is no runtime test delta and no CI or coverage weakening.

## Reviewer results and external review

Architecture, security, product/operations, and QA all pass with low residual
dependency-discipline risks after repairs. CodeRabbit and hosted CI are pending
on the PR head.

## Remaining risks and follow-up

- Implementation must honor every dependency gate; planning does not activate
  any action or chunk.
- Exact XINT/AUTH compilation request/execute activation must merge before
  WS-POL-003-03.
- ART-04B2/04B3 must merge and be callable behind merged ART-04B1 before the
  checker facade chunk.
- Each implementation chunk requires separate human start, evidence, review,
  PR, and human merge.

## Human review focus

- Does one unified inference preserve separate policy and approval truth?
- Is ART pre-submit ownership unchanged and free of duplicate evidence?
- Is post-submit authority confined to durable CHECKER/POL ownership?
- Are capability gaps, correction, replay, and stale generation fail-closed?
- Are the eight chunks genuinely bounded and correctly dependency-gated?

## Human merge ownership

This PR must be merged only after explicit human approval. Merge authorizes the
plan record only; it does not start an implementation chunk.
