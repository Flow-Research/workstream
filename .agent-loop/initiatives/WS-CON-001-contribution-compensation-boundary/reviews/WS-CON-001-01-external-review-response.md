# External Review Response: WS-CON-001-01

## Review Context

- Pull request: `#144`
- Reviewer: CodeRabbit
- Reviewed repair SHA: `a6a88fb42da8ffb37e8293f1495f6be3513e8ad1`
- Trusted base SHA: `053242b90d927ace3fab92eeca72da27a61cecec`

## Comments Addressed

- Thread `PRRT_kwDOSwL_U86R5cTR`: corrected the adapter-binding conformance row.
  Contribution policy definitions and awards hold forward references to a
  binding whose project and instrument identities match; the binding aggregate
  stores no reverse policy or award identifiers.
- Thread `PRRT_kwDOSwL_U86R5cTU`: made receipt redaction vocabulary explicit in
  the canonical specification and ADR 0016 D19. Raw provider secrets,
  authentication tokens, and unbounded provider payloads are prohibited.
  Bounded non-secret `external_event_id` and `external_reference` identifiers
  are allowed only in their canonical receipt/status fields and remain excluded
  from product reads and integration events.

## Comments Deferred

None.

## Current-Main Reconciliation

After both CodeRabbit threads resolved, AUTH-09B PR #143 merged to `main`.
CON-01 pulled that merge and replaced its prior 74/65/9/56 baseline with
74/65/10/55. Only `actor.service.provision` became active. The reconciled
contract records that provisioning creates an approved service actor/link but
does not create a role, grant, assignment, runtime admission, database action
assignment, or executable authority. The current identities/static rows remain
ART-only; future CON services still require separate reviewed AUTH contracts,
provisioning, AUTH-09E, evaluator integration, and activation.

## Human Decisions Needed

The human owner must review and explicitly approve PR #144 before merge. The
external findings did not resolve D11 administrative-role candidates, legacy
economic-row migration, or protected service identity/action/static-row gates.

## Commands Rerun

```text
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
git diff --quiet origin/main...HEAD -- docs/reference_specs
git diff --check
```

Results: Markdown links passed for 18 changed Markdown files and all
stale-contract scans passed; all 80 agent-gate tests and ten focused AUTH
catalogue/static-matrix tests passed; the committed reference-spec diff remained
empty; and diff integrity passed. Senior engineering, QA/test, security/auth,
product/ops, architecture, docs, reuse/dedup, and CI-integrity reviewers all
passed the exact current-main repair SHA with no findings.

## Remaining Risks

- GitHub CI and CodeRabbit must review the pushed evidence/current-main merge.
- The canonical contract is target architecture; runtime remains unchanged and
  hidden until its separately approved implementation and activation chunks.
- The unstaged user-owned reference PDF deletion remains outside this chunk and
  PR.
- Merge and successor start remain explicit human gates.
