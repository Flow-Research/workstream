# Chunk Contract: WS-XINT-001-PLAN Boundary Reconciliation

Initiative: `WS-XINT-001` | Risk: L1 | Status: Active after explicit user start

## Goal

Publish one planning-only source of truth for AUTH, ART, REV, and CON ownership,
activation custody, transaction order, and cross-initiative handoffs.

## Allowed files

- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/**`
- `AGENTS.md` and active `.agent-loop/initiatives/**` planning contracts only
  where stale cross-lifecycle contribution/compensation wording must be
  reconciled
- ART initiative plans, decisions, risks, chunk map, and future chunk contracts
  only where stale activation language must be corrected
- AUTH initiative/specification planning documents where stale feature-owned
  activation, combined project-role, service-principal, or service-admission
  language must be corrected
- `scripts/check_stale_authorization_docs.py`,
  `scripts/check_stale_artifact_contracts.py`,
  `scripts/check_stale_workstream_wording.py`, and
  `scripts/test_agent_gates.py` only for deterministic activation-custody and
  contribution/compensation wording enforcement
- `.agent-loop/WORK_QUEUE.md`, `.agent-loop/REVIEW_LOG.md`, and one merge intent
- `.agent-loop/LOOP_STATE.md` for exact parallel planning-state reconciliation
- active `.agent-loop/policies/*.md` only to reconcile stale human product-role
  and contribution/compensation boundary wording
- `README.md` only to reconcile the repository's public lifecycle summary with
  the same canonical boundary
- directly related active architecture, product, operations, roadmap, template,
  decision, and diagram documents under `docs/` only to reconcile the reviewer
  `completed_review`, submitter `accepted_submission`, conditional compensation,
  independent three-role project authority, and fixed service-admission
  contracts exposed by trusted-main reference specifications

## Not allowed

- backend, frontend, migration, workflow, provider, Celery, action-catalogue,
  grant, evaluator, service-actor, route, review, contribution, or payment code;
- action availability changes;
- edits in another agent's active worktree;
- implementation of any downstream handoff;
- a cross-initiative successor in merge intent.

## Acceptance criteria

- one canonical definition separates feature/resource owner from AUTH activation
  custodian;
- all 25 currently registered ART actions retain exact mappings and receive a
  proposed AUTH custody group;
- all seven fixed artifact service identities and their exact static matrix rows
  are listed;
- one canonical role/service handoff defines `submitter`, `reviewer`, and
  `adjudicator` as independent grants, removes the combined project role, keeps
  adjudication actions unavailable until WS-REV defines the lifecycle and AUTH
  activates exact adjudication actions, defines role-specific invalidation, and
  requires a fixed service runtime-admission path before protected service
  execution;
- Operator retry remains independent from internal service actions;
- ART, REV, AUTH, and CON transaction/commit/audit ownership is explicit;
- ReviewPacketManifest and ReviewEvidenceArtifact remain REV semantic records
  backed by ART bindings/bytes through typed ports;
- review evidence binding has one exact proposed ActionId, existing PermissionId,
  fixed service identity, ART capability owner, and AUTH activation custodian;
- core ContributionRecord creation makes no ART capability/provider call while
  copying canonical `SubmissionVersion.artifact_hash` into
  `ContributionRecord.artifact_hash` lineage;
- every valid human Review creates one reviewer `completed_review`; `accept`
  additionally creates one submitter `accepted_submission`; the applicable
  frozen `ContributionPolicyVersion` is evaluated for each record and may be
  explicitly unpaid;
- payable contribution rules create immutable money and/or project-points
  `CompensationAward` rows; downstream adapters fulfill those awards but never
  decide award eligibility;
- active shared docs use the canonical compensation model:
  `ContributionPolicy`, immutable `ContributionPolicyVersion`,
  `ContributionRule`, `ContributionAwardDefinition`,
  `ProjectCompensationAdapterBinding`, `CompensationAward`,
  `CompensationFulfillmentReceipt`, and `CompensationStatusProjection`;
  `PaymentPolicy` and `PaymentRecord` are retired and removed names; only
  explicit historical/reference removal statements may mention them;
- each parallel agent receives a bounded handoff and no runtime start signal;
- ART plans no longer claim that ART registers or activates authorization;
- Markdown links, stale wording, diff hygiene, and internal review pass.

## Verification

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
git diff --check
```

`check_stale_workstream_wording.py` is the canonical active-contract scan and
must return zero failures. Public review documents are active documentation and
use current terminology; immutable internal review evidence remains historical.

Exact-SHA candidate review necessarily runs before its truthful evidence file
exists. After every required track returns `PASS` with zero findings and all
sessions close, the coordinator records the reviewed SHA and results in the
internal evidence/trust bundle. Publication remains blocked until that final
evidence gate passes; absence of not-yet-producible evidence is not a candidate
code finding during reviewer fanout.

## Required reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, docs, CI integrity, and test delta. A passing final verdict means
zero findings at any severity; `PASS WITH LOW RISKS` is not sufficient.

## Human review focus

- Is AUTH the only activation custodian?
- Can each feature owner implement hidden behavior without an active action?
- Is the transaction order race-safe without mixing persistence ownership?
- Is core contribution creation correctly independent of ART?
- Can all four agents continue in parallel after merge without editing one
  another's runtime code?
- Can submitter, reviewer, and adjudicator authority be granted and revoked
  independently while adjudication actions remain unavailable?
- Can a fixed service execute only its exact action without entering any human
  grant path?

## Stop conditions

Stop if a boundary requires runtime implementation, a new permission, an
unapproved service identity, dual activation ownership, or a direct repository
dependency. Stop after publishing the reviewed planning PR.

## Final Repair Boundary

The final review repair is limited to role ownership and active-contract
consistency in the operations matrix/workflow, authorization specification,
architecture review/brief/data model, Work Queue, stale-contract scanners and
their regression tests, generated architecture PDF, and this initiative's
status/review artifacts. It changes no runtime behavior and introduces no new
role, permission, action, service identity, lifecycle, or cross-initiative
successor.
