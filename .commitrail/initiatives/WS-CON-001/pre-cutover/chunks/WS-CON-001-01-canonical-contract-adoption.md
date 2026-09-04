# Chunk Contract: WS-CON-001-01 - Canonical Contract Adoption And Architecture Decision

## Goal

Publish one repository-owned active contribution/compensation specification and
Decision 0016 reconciled with WS-XINT, without editing or restoring archival
inputs.

## Risk

L0 direction executed as L1 specification work; SLA P1.

## Allowed files

```text
docs/spec_contribution_compensation.md
docs/decision_0016_contribution_compensation_boundary.md
README.md only active-spec link/precedence note
active docs/templates explicitly inventoried by the chunk before review
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-01.json
```

## Not allowed

```text
reference-spec bytes, names, checksums, or restoration
backend runtime, migrations, tests, workflows, dependencies
AUTH/ART/REV owned specifications/catalogues or action activation
roadmap changes without synchronized local XLSX/CSV exports
```

## Acceptance criteria

- [ ] Decision number is 0016; 0015 remains independent project contributor
  roles.
- [ ] Active spec defines ContributionPolicy/version/rules/award definitions,
  ProjectCompensationAdapterBinding, ContributionRecord, CompensationAward,
  fulfillment receipts/status, and shared outbox ownership.
- [ ] Retired guide-bound schema removal is complete and split across 05A/05B;
  no alias/fallback survives. Missing ContributionPolicy setup is not silently
  unpaid.
- [ ] Existing versioned Submission is retained. CON copies stabilized
  artifact_hash lineage and performs no core ART/evidence operation.
- [ ] Active spec defines REV-owned accept-only FinalAcceptance with canonical
  `submission_id`, `policy_context_ref`, and `recorded_by`;
  FinalAcceptance-sourced submitter
  contribution; direct Review-sourced reviewer contribution; and one REV-owned
  commit. It adds no SubmissionVersion alias or adjudication dependency.
- [ ] Active spec adopts merged REV PR #128's two ordered operation-specific CON
  inputs: reviewer before branch, accept-only submitter after FinalAcceptance
  and accepted task effects; no nullable omnibus input.
- [ ] Optional evidence is clearly deferred with separate ART/AUTH approval and
  is absent from the core release path.
- [ ] AUTH boundary matches PR #140 (adopting PR #139): independent project grants, fixed-service
  static matrix/AUTH-09E, prepared mutations, AUTH-only activation, complete
  ART/REV custody references, and no service-row startup dependency.
- [ ] Active spec lists the proposed 22 core surface mappings as unregistered,
  non-final identifiers using `contribution.policy.*`; optional evidence is separate; protected handler
  execution actions remain explicit human/AUTH gates until approved.
- [ ] Dispatcher authority is limited to outbox mechanics; delivery,
  reconciliation, rebuild, and callback cannot inherit it.
- [ ] Active spec adopts REV-12A's single shared lifecycle controller/fence,
  immutable monotonic fulfillment-root ordinal, every-writer fence order,
  maximum-ordinal drain observation, and same-generation pre-cutoff completion
  rules without moving controller ownership into CON.
- [ ] Exact D11 outcome and legacy-row decision are recorded before dependent
  implementation.
- [ ] Public prefix is `/api/v1`; provider refs/credentials and settlement
  ledgers are excluded.
- [ ] Conformance matrix maps every normative rule to a chunk/test/final gate.
- [ ] Archival inputs remain byte-for-byte untouched, including the user's
  pre-existing deletion state.

## Verification

Run from the repository root:

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
test -f docs/spec_contribution_compensation.md
test -f docs/decision_0016_contribution_compensation_boundary.md
test "$(rg -c 'docs/spec_contribution_compensation\.md' README.md)" -eq 1
git diff --quiet origin/main...HEAD -- docs/reference_specs
test "$(sha256sum 'docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md' | cut -d ' ' -f1)" = cddbe20f4fadf5307f68519347bdd9520ef49b23fb0b92cad24c31fc9b34c640
test "$(sha256sum 'docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification(2).pdf' | cut -d ' ' -f1)" = ce65e208076769f0bafb09779d60ab6f5fc0c596514d4e8f4cc03690c6e6d457
git diff --check
```

Pass requires every command to exit zero, both active documents to exist, one
README canonical link, no reference-input delta, both present archival hashes
to match, and all repository gates to pass. Required reviewers: senior, QA,
security, product, architecture, docs, reuse, CI integrity, and test delta when
scanners/tests change.

## Stop

Stop after reviewed specification and merge memory. Do not start CON-02A
automatically.
