# Chunk Contract: WS-XINT-003-08A — Human And Operator Recovery Activation

## Status and risk

Non-implementable planning skeleton after 08R. Refresh exact files and commands
on current main before an explicit user request. REV recovery behavior must
remain hidden. L1 privileged lifecycle recovery.

## Goal

Activate bounded queue inspection, force release, routing override/correction,
queue close, revision-context repair/legacy close, and revision-obligation close.

## Allowed files

Enumerate exact REV recovery commands, AUTH contexts/candidates, routes, audit,
tests, docs, migration parity, and evidence at current-main start.

## Not allowed

Operator review decisions, generic project or artifact authority, fabricated
Review/reject, history rewrite, silent repair, or broad recovery permission.

## Acceptance criteria

- Each command has its own ActionId, typed resource, exact Project Manager or
  Operator candidate, canonical reason, idempotency, and bounded audit event.
- Covered Project Managers repair/close only their exact project and cannot use
  Operator legacy/queue powers. Operators cannot decide reviews or mutate
  ordinary project policy.
- Recovery locks and revalidates the exact stale/broken condition; live valid
  commands win or conflict deterministically without dual effects.
- Reads conceal/redact before counts; mutations preserve immutable history and
  never create synthetic judgment or contribution.
- No route or command exists until 08R's exact planned catalogue rows,
  permission mappings, migration parity, and denial tests have merged.

## Verification and reviewers

Role/scope/reason matrices, crossed live-vs-recovery races, audit/redaction,
coverage/hosted gates; full L1 reviewer set.

## Stop

Merge and stop before remaining service activation.
