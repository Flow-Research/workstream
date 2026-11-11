# WS-SUBMIT-001-01 — Immutable intake command and source identities

- Initiative: WS-SUBMIT-001
- Durable disposition: Planned
- Intended merge outcome: closed immutable ART command/source values with exact canonical identities and rejection tests.

## Intent

Give database, upload and execution owners one representation of the original
command and sealed source, separate from credentials and later manifest facts.
This is the first portion of specification section 22 step 1.

## Current behavior

`artifacts/submission_admission.py` consumes process-local prepared ZIPs;
`interfaces/artifacts.py` derives keys from content SHA. The new design needs
operation-based keys before bytes are known and exact durable identity afterward.

## Bounded change

### Allowed

- `backend/app/modules/artifacts/api/submission_intake.py`: command and source values.
- `backend/tests/artifacts/test_submission_intake_contracts.py`: pure contract proof.
- `docs/spec_submission_execution.md`: user-supplied specification, with technical
  Celery-worker vocabulary qualified for repository documentation checks.
- `scripts/check_stale_authorization_docs.py` and
  `scripts/test_submission_spec_wording.py`: exact object-key example exemption;
  public API prefix enforcement remains unchanged elsewhere.
- This initiative, index and capability ledger: target and limited delivered scope.

### Not allowed

- Routes, migrations, orchestration, provider I/O or claims of database enforcement.
- Historical data changes, new authority, runtime changes or deployment defaults.
- Unrelated preparations or another open PR's branch.

## Design and decisions

Reuse canonical JSON hashing and the archive ceiling. Keys derive from server
UUIDv7 operation identity. Sealed values bind namespace/profile, raw SHA/count,
generation and fence. Metadata identity preserves exact packet and revision
selectors; actor/key scope and locked context remain separate operation facts.
Constructing these internal values grants no authority or provider qualification.

## Acceptance criteria

- [ ] Exact metadata round-trip and identity changes for each command selector.
- [ ] Packet/framing metadata validation preserves empty-text warning semantics.
- [ ] Source keys derive only from UUIDv7; no arbitrary path/URL selection.
- [ ] Namespace, generation, bytes and fence remain distinct identity inputs.
- [ ] Unknown fields, mutation and coercive values fail closed.
- [ ] Focused tests, lint, boundary/docs checks and scoped frozen-candidate reviews.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, QA/test_delta, documentation, CI integrity
- Human review focus: exact identities and limited contract-only scope.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline | Fetch main and inspect open PRs | Reconciled a4e485ed | Recheck before publication |
| Contracts | Focused pytest and ruff | 56 tests passed; lint passed | No database/storage/runtime proof |
| Module boundaries | `python -m scripts.module_boundaries validate --protected-base origin/main` | Passed | Existing private-import debt unchanged |

## Review findings

No findings recorded yet.

## Reconciliation

- Current-source reconciliation: deployment delta and header mismatch inspected.
- Next usable boundary: durable operation schema and owner commands.
- Remaining risks: A01–A35 integration and C01–C07 qualification.
