# WS-REV-001-01 PR Trust Bundle

## Chunk

`WS-REV-001-01`: Canonical Contract Adoption And Dependency Conformance.

## Goal

Preserve the supplied WS-REV and WS-IMP archival pairs byte-for-byte, adopt one
reconciled active review/revision contract, and align every active contract and
gate before runtime implementation.

## Human-Approved Intent

Every valid reviewer decision, submitted finding, and later resolution is
immutable. Accept additionally creates FinalAcceptance, which alone sources the
submitter contribution. Needs-revision prepares the next attempt against the
current Project Guide when required. Adjudication and reputation mutation are
not v0.1 behavior.

## What Changed

- Added `docs/spec_review_lifecycle.md` as the active normative contract.
- Reconciled architecture, ADRs, operations, templates, roadmaps, and diagrams.
- Added a fail-closed stale review-contract scanner and adversarial gate tests.
- Added registered structural regressions for canonical accept ordering,
  CheckerRun admission, and checker-versus-human revision lineage.
- Preserved and proved all supplied archival inputs.
- Added deterministic pinned rendering for the lifecycle and two changed
  context diagrams.
- Reconciled merged AUTH-09B's controlled provisioning capability and exact
  `65 / 10 active / 55 planned` catalogue without activating any REV identity
  or action.
- Reconciled merged AUTH-09C's two bounded actor-registry reads and exact
  `65 / 12 active / 53 planned` catalogue while keeping all 24 REV
  dependencies unavailable.
- Reconciled merged CON-01's active specification and ADR 0016 while retaining
  its no-runtime status and downstream persistence/participant gates.
- Reconciled merged ART-02A3's active byte-only v2 LocalStorage clean cut while
  preserving later S3, submission/checker, packet-read, and evidence gates.
- Addressed external lifecycle, checker-admission, ART terminology, rendering,
  template, and revision-policy findings without expanding runtime scope.
- Added an exact 71-entry A/M scope manifest so additions, deletions, renames,
  and status drift fail the final Chunk 01 review comparison.

## Why It Changed

Merged AUTH, ART, CON, and WS-XINT boundaries superseded parts of the archival
specification and older active docs. Runtime work needs one exact contract with
no contradictory status, transaction, identity, storage, or contribution
semantics.

## Design Chosen

REV owns immutable Review and FinalAcceptance facts plus lifecycle
orchestration. AUTH owns prepared authority and activation. ART v2 owns bytes
and typed artifact capabilities. CON joins the REV-owned caller transaction as
an ordered flush-only participant. The route or service command commits once.

## Alternatives Rejected

Editing archival inputs, direct Review-to-submitter contribution, review-time
guide rebasing, raw ArtifactStore access, CON-owned commits, synthetic reject,
mandatory payment, v0.1 adjudication/reputation, and early action activation
were rejected because they violate approved ownership or lifecycle boundaries.

## Scope Control

This is an L1 specification/architecture chunk. It changes no backend,
migration, frontend, AUTH, ART, or CON runtime implementation. All changed paths
and their exact added/modified statuses are listed by the chunk contract's
reviewed-scope manifest; exactly one merge intent is present.

## Product Behavior

No endpoint or action becomes available. The contract fixes the future behavior
for concealed current-work reads, claims, immutable decisions, accept,
needs-revision, reject, revision preparation, evidence access, contributions,
and payable-only awards.

## Acceptance Criteria Proof

Literal archive hashes and trusted-base diffs pass. Active documents and
roadmaps are scanner-clean. AUTH PREP and lock ordering are exact. Diagrams and
the architecture PDF reproduce byte-for-byte with the pinned renderer. Local
roadmap exports remain absent.

## Tests/Checks Run

`87 agent gate tests passed`; exact status-scope comparison and adversarial
status/removal/rename/addition probes, Ruff format/lint, four stale-contract
families, Markdown links, archive checksums/base diffs, PDF attributes, pinned
double render, spreadsheet absence, merge-intent count, and `git diff --check`
passed.

## Test Delta

The agent-gate suite gains table-driven prohibited-category coverage,
adversarial lexical decoys, exact archival classification, and fail-closed
discovery coverage. No test or assertion was removed or weakened.

## CI Integrity

No workflow, package script, coverage threshold, or existing gate was weakened.
This chunk adds a mandatory scanner invoked by the existing agent-gate suite.

## Reviewer Results

The plan gate and all nine required reviewer tracks passed exact SHA
`e239282e7d2a2b4d46137707f673f76fda55e4b8` against trusted main
`0ffdabf3dbb77e4e066683fde1a095d744ff1f43`: senior engineering, QA/test,
security/auth, product/ops, architecture, docs, reuse/dedup, test delta, and CI
integrity. No blocking findings remain.

## External Review

PR #145's initial Agent Gates run found a successor-heading/merge-intent title
mismatch, which was repaired without starting Chunk 02. After its cooldown,
CodeRabbit reported nine actionable findings and one Markdown lint nit. All
were addressed: accept ordering, exact checker guards, TaskAssignment and ART
wording, renderer source generation, template table structure, PlantUML
preconditions, and explicit false revision-limit configuration. The resulting
scanner also rejects quoted and unquoted truthy variants. The prior published
backend and Agent Gates runs passed. ART-02A3 then advanced main and was
reconciled through a fresh exact-SHA internal loop; replacement checks on the
new head remain external gates. CodeRabbit's later fail-closed scope comment
was addressed with an exact status manifest and an explicit current-main versus
archival-base rationale. Internal review caught and repaired the first
path-only version before publication. External checks supplement internal
review and do not replace it.

AUTH-09C then advanced main and conflicted only in the shared agent-gate
lifecycle test. The resolution preserves all 80 main tests plus seven REV tests,
adopts the merged AUTH/ART state, and retains the earlier ART fallback branches.
Three stale catalogue-provenance statements found internally were corrected
before the final exact-SHA review.

CodeRabbit then identified the dirty-worktree gap in the committed-range scope
proof. The final command requires a clean staged, unstaged, and untracked state
before comparing exact path statuses; isolated negative probes and a fresh
nine-track exact-SHA review pass.

## Remaining Risks

Runtime database, concurrency, rollback, and dependency integration proof is
deferred to its owning implementation chunks. Scanner fixtures may need updates
when future terminology changes.

## Follow-Up Work

`WS-REV-001-02` is the same-initiative successor but requires a separate
explicit human start after this PR merges and automated merge memory records it.

## Human Review Focus

Confirm archival provenance, active-contract precedence, AUTH/ART/CON ownership,
FinalAcceptance lineage, rebase semantics, unavailable v0.1 boundaries, and the
absence of unintended runtime work.

## Human Merge Ownership

Only the human may approve and merge this PR. Internal and external PASS results
do not authorize merge.
