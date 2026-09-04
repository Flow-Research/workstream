# Internal Review Evidence: WS-CON-001-01

## Chunk

`WS-CON-001-01` - Canonical Contract Adoption And Architecture Decision

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `a6a88fb42da8ffb37e8293f1495f6be3513e8ad1`

Trusted main SHA: `053242b90d927ace3fab92eeca72da27a61cecec`

Reviewed at: 2026-07-17T23:00:33Z

Reviewer run IDs: senior-engineering/architecture/reuse-dedup=/root/con01_arch_senior_reuse; QA-test/product-ops/docs=/root/con01_qa_product_docs; security-auth/CI-integrity=/root/con01_security_ci

## Reviewed Change

- Published `docs/spec_contribution_compensation.md` as the repository-owned
  active target specification and ADR 0016 as its architecture decision.
- Preserved current-runtime versus target-runtime truth: older guide-bound
  economic fields remain implementation history until CON-05A/05B.
- Fixed REV-owned FinalAcceptance naming to canonical `submission_id`,
  `recorded_by`, and `policy_context_ref`.
- Required one reviewer `completed_review` for every valid Review and one
  accept-only submitter `accepted_submission` sourced from FinalAcceptance.
- Adopted two ordered CON flush-only operations, REV-staged audit/outbox, one
  caller-owned commit, complete rollback, and zero core ART/provider calls.
- Defined policy, freezes, adapter binding, immutable contributions/awards/
  receipts, rebuildable status, and shared outbox/audit ownership.
- Preserved AUTH-only registration, mapping, prepared authorization, service
  admission, evaluator, evidence, activation custody, and availability. All 22
  surface mappings remain unregistered non-final proposals.
- Preserved dispatcher-only authority, ADR 0014 adapters, and REV-12A's sole
  controller, fence, ordinal, cutoff, and drain behavior.
- Added `NUMERIC(38, 18)` quantity semantics, exact unit identity, bounded
  non-secret receipt identifiers, closed failure codes, and raw provider-data
  minimization.
- Added conformance rows for adapter binding, lifecycle audit, ADR 0014,
  quantity/unit copy integrity, receipt redaction, and operations observation.
- Added exactly one schema-v2 merge intent naming same-initiative successor
  `WS-CON-001-02A` with a separate explicit start.
- Reconciled the active contract with merged AUTH-09B: 74 PermissionIds, 65
  ActionIds, ten active and 55 planned; only `actor.service.provision` was newly
  activated.
- Reused AUTH's controlled service ActorProfile/ActorIdentityLink provisioning
  while preserving the separate ServiceIdentity/static-row, AUTH-09E admission,
  evaluator, activation, and cross-service-denial gates for every future CON
  fixed service. The current seven identities and eleven rows remain ART-only.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | The target contract is bounded, maintainable, hidden before activation, and operationally coherent. |
| qa/test | PASS | None | Every chunk acceptance criterion and proof family is explicit and testable. |
| security/auth | PASS | None | AUTH ownership, economic precision, receipt minimization, rollback, and release fencing fail closed. |
| product/ops | PASS | None | Decision behavior, freezes, unpaid semantics, product truth, and human gates match intent. |
| architecture | PASS | None | Cross-domain ownership remains separated with exact interleaving. |
| docs | PASS | None | ADR/spec precedence, target/runtime wording, inventory, status, decisions, and conformance align. |
| reuse/dedup | PASS | None | Existing Submission, ADR 0014, AUTH PREP, shared outbox/audit, and REV controller/fence are reused. |
| ci integrity | PASS | None | No workflow, dependency, test command, runner, threshold, or coverage configuration changed. |

Test delta: not applicable; no test, scanner, workflow, or test configuration
file changed. Existing agent-gate tests were retained and executed unchanged.

## Findings Addressed

- Added missing conformance coverage for adapter-binding lifecycle, shared
  caller-transaction audit, and ADR 0014 typed adapters.
- Updated the inventory to disclose TaskAssignment, FinalAcceptance,
  fixed-point, and receipt corrections.
- Removed free-form `failure_message` from the canonical receipt.
- Bounded event/reference tokens and prohibited raw provider material from
  persistence, logs, events, exports, or responses.
- Added closed Workstream failure codes with generic mapping before persistence.
- Added one `NUMERIC(38, 18)` contract, canonical decimal strings, no floating
  point/rounding/exponent/overflow, ISO 4217 money units, and project-scoped
  points units.
- Bound numeric, unit-copy, receipt, redaction, and operations rules to exact
  implementation chunks and release proof.
- Corrected the adapter-binding conformance row so policy definitions and awards
  hold forward references to a matching project/instrument binding and the
  binding stores no reverse policy or award identifiers.
- Distinguished forbidden raw provider secrets, authentication tokens, and
  unbounded provider payloads from the bounded non-secret event/reference
  identifiers allowed only in canonical receipt/status fields.
- Re-ran every required internal track against the exact repaired SHA after the
  two CodeRabbit findings; all eight tracks passed with no remaining findings.
- Pulled merged AUTH-09B PR #143, replaced the stale 74/65/9/56 baseline with
  74/65/10/55, and made provisioning-versus-execution separation explicit.
- Re-ran all eight internal tracks at the exact current-main reconciliation SHA;
  every track passed with no findings.

## Commands Run

```text
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
test -f docs/spec_contribution_compensation.md
test -f docs/decision_0016_contribution_compensation_boundary.md
test "$(rg -c 'docs/spec_contribution_compensation\.md' README.md)" -eq 1
git diff --quiet origin/main...HEAD -- docs/reference_specs
sha256sum docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md
sha256sum docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification\(2\).pdf
git diff --check
```

Results: Markdown links passed for 18 changed Markdown files; stale Workstream,
AUTH, and ART scans passed; all 80 agent-gate tests and ten focused AUTH
catalogue/static-matrix tests passed; exactly 22 proposed mappings were present;
both present archival hashes matched; the committed diff contained no
reference-spec change; and diff integrity passed. No backend, migration, test,
dependency, workflow, or coverage command changed relative to trusted main.

The local worktree retains one user-owned unstaged deletion of the older
reference PDF. It was excluded from staging, the reviewed commit, every
reviewer verdict, and PR scope.

## Remaining Risks And Human Gates

- The human must approve the specific PR and canonical wording.
- D11 AdminRole candidates remain unresolved before CON-10A/10B.
- Legacy economic rows require deterministic rebuild or classified migration
  before CON-05A/05B.
- New CON service identities/actions/static rows require human/AUTH approval;
  AUTH-09B provisioning alone grants no execution authority.
- AUTH-09C through 09E, AUTH-PREP, project grants, complete REV custody,
  FinalAcceptance runtime, stabilized artifact lineage, and named integration
  chunks remain upstream gates.
- Optional contribution evidence remains deferred.

## Stop Condition

Stop at the CON-01 PR human checkpoint. Do not merge without explicit approval
for that PR and do not start `WS-CON-001-02A` automatically.
