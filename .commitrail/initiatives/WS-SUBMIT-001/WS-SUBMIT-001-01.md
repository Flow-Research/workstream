# WS-SUBMIT-001-01 — Single-request submission execution

- Initiative: WS-SUBMIT-001
- Durable disposition: Planned
- Intended merge outcome: the complete single-request submission specification, including durable intake, one-session PRE, accepted handoff, finalization, clients and end-to-end proof.

## Intent

Implement the [approved specification](../../../docs/spec_submission_execution.md)
in one PR with focused commits for each stage. The user explicitly requires the
complete end-to-end behavior and tests before requesting merge; intermediate
contract, schema or runtime stages are not separate merge checkpoints.

The first stage gives database, upload and execution owners one representation
of the original command and sealed source, separate from credentials and later
manifest facts.

## Current behavior

`artifacts/submission_admission.py` consumes process-local prepared ZIPs;
`interfaces/artifacts.py` derives keys from content SHA. The new design needs
operation-based keys before bytes are known and exact durable identity afterward.

## Bounded change

### Allowed

- `backend/app/modules/artifacts/api/submission_intake.py`: command and source values.
- `backend/tests/artifacts/test_submission_intake_contracts.py`: pure contract proof.
- `backend/scripts/test_lane_catalogue.py` and `backend/tests/test_ci_lane_catalogue.py`:
  register the new tests in the shared-foundations lane, preserving every existing member.
- `docs/spec_submission_execution.md`: user-supplied specification, with technical
  Celery-worker vocabulary qualified for repository documentation checks.
- `scripts/check_stale_authorization_docs.py`, `scripts/check_stale_review_contracts.py`,
  `scripts/test_lightweight_agent_gates.py` and `scripts/test_stale_review_contracts.py`:
  exact storage example exemptions and tests in already-selected CI modules;
  public API prefix enforcement remains unchanged elsewhere.
- This initiative, index and capability ledger: target and limited delivered scope.

- `backend/scripts/behavior_ownership.py`, its existing test module and
  `.ci/behavior-ownership/partition.v1.json`: register only the new immutable
  contract target in the protected partition after CI exposed the missing entry.

- Existing ART/TASK/AUTH/CHECKERS owners, composition roots, routes, migrations,
  storage/runtime adapters, durable continuation, CLI/MCP and their tests and
  current documentation as required by the specification. Each stage records
  concrete proof; incomplete stages remain unexposed until coordinated cutover.

### Not allowed

- Retained evidence deletion or rewriting, unrelated product changes, fabricated
  deployment defaults or unsupported storage/runtime qualification claims.
- Unrelated preparations or another open PR's branch.

## Design and decisions

Reuse canonical JSON hashing and the archive ceiling. Keys derive from server
UUIDv7 operation identity. Sealed values bind ART's `primary` namespace ID and
fingerprint, provider profile, raw SHA/count,
generation and fence. Metadata identity preserves exact packet and revision
selectors; actor/key scope and locked context remain separate operation facts.
Constructing these internal values grants no authority or provider qualification.

## Acceptance criteria

- [x] Exact metadata round-trip and identity changes for each command selector.
- [x] Packet metadata validation preserves empty-text warning semantics.
- [x] Source keys derive only from UUIDv7; no arbitrary path/URL selection.
- [x] Namespace, generation, bytes and fence remain distinct identity inputs.
- [x] Unknown fields, mutation and coercive values fail closed.
- [ ] Focused tests, lint, boundary/docs checks and scoped frozen-candidate reviews.

## Risk and review routing

- Risk class: L0
- Required reviewers: architecture, security, QA/test_delta, documentation, CI integrity
- Human review focus: authorization, immutable lineage, custody, quota/cleanup,
  atomic handoff, recovery, client truthfulness and complete end-to-end proof.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline | Fetch main and inspect open PRs | Reconciled 94334ccf4 | Recheck before publication |
| Contracts and CI selection | `pytest -q tests/artifacts/test_submission_intake_contracts.py tests/test_ci_lane_catalogue.py`; ruff | 118 tests passed; lint passed | No database/storage/runtime proof |
| Documentation guard regression | `python -m unittest scripts.test_lightweight_agent_gates scripts.test_stale_review_contracts -q` | 35 tests passed | Narrow storage examples only |
| Module boundaries | `python -m scripts.module_boundaries validate --protected-base origin/main` | Passed | Existing private-import debt unchanged |

## Review findings

- Architecture/security found a synthetic UUID namespace fixture incompatible
  with ART's natural singleton ID, and missing fingerprint binding. The value
  now uses `primary` and its fingerprint; an actual adapter-derived namespace
  regression replaces the unsupported assumption. No namespace schema changed.
- Documentation found a mechanically altered implementation path. Restored the
  exact path and scoped the vocabulary exception to that literal token only.
- CI review found the new wording regression unselected. Moved it into existing
  selected suites. Registered backend contracts in the semantic lane catalogue;
  updated only that lane's expected member count/fingerprint.

## Reconciliation

- Current-source reconciliation: rebased onto 94334ccf4 (PR #707); preserved issuer
  profile roadmap changes and schema head 0068. Submission owner contracts unchanged.
- Next implementation stage: durable operation schema and owner commands in
  the same PR, followed by streaming, PRE, handoff/finalization and clients.
- Remaining risks: A01–A35 integration and C01–C07 qualification.
