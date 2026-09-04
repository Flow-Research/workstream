# Chunk Contract: WS-CON-001-PLAN - Contribution And Compensation Planning

## Goal

Reconcile WS-CON planning to merged PR #139 / WS-XINT-001 without implementing
runtime behavior, and repair only the exact active-contract scanner
classification/proof required by that reconciliation.

## Risk

L0 architecture/economic/authorization planning plus CI-sensitive scanner
metadata; P1.

## Allowed files

```text
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
scripts/check_stale_workstream_wording.py only exact archival/current-runtime contract rules
scripts/check_stale_authorization_docs.py only exact archival classification
scripts/check_stale_artifact_contracts.py only exact archival classification parity
scripts/check_internal_review_evidence.py only deleted-contract provenance during chunk renames
scripts/test_agent_gates.py only fail-closed gate regressions for these rules
docs/current_system_data_flow.html only remove premature target-runtime type claim
```

## Not allowed

```text
backend application, migrations, runtime tests, workflows, dependencies
AUTH/ART/REV initiative edits
reference-spec byte edits, restoration, rename, or archival replacement
active product documentation adoption
scanner threshold weakening, directory-wide archive exemption, or broad waiver
```

## Acceptance criteria

- [ ] Trusted baseline is `5d353b6`; runtime AUTH remains 74 PermissionIds, 57
  ActionIds, nine active, and 48 planned.
- [ ] Canonical eligibility model is ContributionPolicy/version/rule/award
  definition; CompensationAward remains the evaluated result.
- [ ] Core Review-to-contribution transaction creates no evidence projection,
  makes zero ART calls, and copies stabilized Submission artifact_hash lineage.
- [ ] Project grants are independent submitter/reviewer/adjudicator; fixed
  services use ServiceIdentity/static matrix/AUTH-09E, never persisted action
  rows.
- [ ] ActionOwner is AUTH activation custody; complete ART/REV transfers are
  referenced from WS-XINT rather than partially restated.
- [ ] Shared outbox dispatch cannot authorize protected feature handlers;
  delivery/reconciliation/rebuild/callback identity/action decisions are open
  exact gates.
- [ ] Proposed policy ActionIds use `contribution.policy.*` mapped to stable
  `compensation.policy.manage`. The 22 core surface actions are tested
  separately from optional evidence and unapproved executor candidates.
- [ ] CON-09A/09B are deferred optional and absent from core 10A/B/10C/11 and
  joint release gates.
- [ ] Current chunk map includes independently authorized 10C executors.
- [ ] The pre-existing user deletion of the original PDF remains untouched and
  unstaged.
- [ ] Exact WS-CON reference Markdown is classified historical consistently in
  all three scanners; near misses and new docs remain scanned.
- [ ] Current-runtime scanner recognizes canonical unimplemented contribution/
  award types and fails on premature runtime walkthrough claims.
- [ ] Internal-review evidence discovery recovers a deleted contract heading
  from the index, HEAD, or review base and retains its chunk ID alongside each
  replacement; missing, empty, malformed, unreadable, dangling-symlink, and
  non-file contracts fail closed.
- [ ] Required internal reviewers pass the exact final snapshot and no sessions
  remain open.
- [ ] The repository loop-memory check is run and its only failure is the
  unchanged AUTH status inherited from trusted `main`; this bounded CON chunk
  does not edit another initiative to conceal the upstream failure.

## Verification

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
# Expected inherited failure until AUTH/main repairs its own status:
python3 scripts/check_loop_memory_state.py
git diff --exit-code origin/main -- \
  .agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
git diff --check
test "$(git rev-parse origin/main)" = 5d353b6d3f8a36b9b9ffdc1959487a150ac25fd1
```

## Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, CI integrity, and test-delta.

## Stop

Stop after reviewed planning reconciliation. Do not start CON-01, runtime work,
optional evidence, push, or PR publication without explicit human direction.
