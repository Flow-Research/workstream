# PR Trust Bundle: WS-ENG-007-00R5

## Intent

Reconcile exact merged R4 and activate its authority-projection repair without
restoring mutable check authority or starting any successor.

## Scope

- Pin signed basis `a3eecadc…`.
- Recover only PR #191 / R4 / `9bf16d47…`.
- Activate only R5.
- Require merge-bound `agent-gates` and `test` evidence for both records.
- Consume both exemptions before signed publication.

## Reviewed Revision

`10159497b3f3ca3464cbbbfd10f16945ade1879a`

## CI Integrity

- 297 focused tests pass.
- Updater branch coverage is 90.46 percent.
- Independent-checker branch coverage is 90.40 percent.
- No workflow, threshold, permission, required check, signed start, or human
  merge checkpoint is weakened.

## Reviewer Result

All nine required internal tracks passed after rejecting the initial schema-v3
approach. No Critical, High, or Medium finding remains open.

## Human Review Focus

- Confirm schema v5 requires exactly one recovered predecessor and exact signed
  basis.
- Confirm CodeRabbit is supplementary and mutable reruns are not authority.
- Confirm exemptions are exact, adjacent, consumed, and non-replayable.
- Confirm R5 stops and starts neither ENG-006 nor ENG-007-01.

## Remaining Risk

An intervening protected-main merge invalidates adjacency and must require a new
reviewed certificate rather than reinterpretation.
