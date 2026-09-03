# WS-ENG-009 Plan — Commission Commitrail in Workstream

## Outcome

Replace `.agent-loop` atomically with the reduced Commitrail method, then use a
real Workstream change as a blind end-to-end stress test. Workstream product,
runtime, database, and API behavior remain unchanged. Engineering-process and
CI enforcement intentionally change from the legacy projection model to the
Commitrail record model while preserving existing quality and human-authority
protections.

## Cutover design

### 1. Establish the canonical Commitrail package

Add `.commitrail/README.md`, `INDEX.md`, `CHANGE_TEMPLATE.md`, and
`initiatives/`. Include a repository-owned Workstream operating guide derived
from Commitrail v0.1. Do not describe that copy as Commitrail's canonical public
distribution until the author assigns publication terms and a canonical
location and the blind stress test produces evaluation evidence. The Workstream
installation may add only the records earned by its risk; it must not recreate
every generic appendix as a required file.

### 2. Distil current truth

Build `.commitrail/INDEX.md` from current `main`, `docs/roadmap_status.md`, open
GitHub work, and the active initiative ledger. Record only durable initiative
disposition and the next usable boundary. Open PRs remain GitHub data.

For active multi-PR initiatives, create one short overview containing intent,
current boundary, governing specifications, material decisions, and remaining
risks. Do not copy old review bundles, merge intents, queues, or redundant
status prose.

### 3. Preserve only normative material

Classify references into:

1. product truth that belongs in an owning specification or ADR;
2. current engineering navigation that belongs in `.commitrail`;
3. historical evidence recoverable from Git history.

Before deletion, produce a reviewable relocation inventory that:

- classifies every tracked reference originating outside `.agent-loop`;
- gives every non-historical row in `.agent-loop/CURRENT_STATE.md` an explicit
  `.commitrail` or owning-specification destination;
- enumerates every tracked `.agent-loop` record containing normative or durable
  material—including initiative status and chunk records—regardless of whether
  another file links to it; and
- names the destination or an explicit historical-only disposition for every
  inventory entry.

The inventory must have no unclassified entry before removal. Move categories
1 and 2 deliberately. Delete category 3 from the working tree. No canonical
product rule may depend solely on a deleted historical plan.

### 4. Cut every active integration point

Update `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, relevant docs, PR template,
skills, reviewer definitions, scripts, CI, and tests in the same PR. Replace
mandatory triple state projection with validation of one change record and,
only for multi-PR work, its initiative overview/index entry.

The validator must enforce useful invariants without treating records as
permission:

- non-trivial implementation changes have one bounded change record;
- allowed and prohibited scope, acceptance criteria, verification, risk,
  reviewers, and intended merge outcome are explicit;
- durable dispositions use `Planned`, `Complete`, `Stopped`, or `Superseded`;
- transient review/CI/approval state is not committed as current truth;
- no `.agent-loop` path or retired signed-loop mechanism can be reintroduced.

The repository-owned validator must include executable positive cases for a
valid single-record change and a valid multi-PR initiative. Together those
cases cover `Planned`, `Complete`, `Stopped`, and `Superseded`. Negative cases
must reject missing required fields, unknown dispositions, committed transient
review/CI/approval state, inconsistent overview/index entries, and every
attempt to restore `.agent-loop` or retired signed-loop paths.

### Agent Gates preservation map

| Existing protection | Post-cutover disposition |
|---|---|
| Markdown links | Preserve `check_markdown_links.py` |
| Workstream stale wording | Preserve `check_stale_workstream_wording.py` |
| Authorization documentation | Preserve `check_stale_authorization_docs.py` |
| Artifact contracts | Preserve `check_stale_artifact_contracts.py` |
| Guide-extractor dependencies | Preserve `backend/scripts/check_guide_extractor_dependencies.py` |
| Atomic chunk-state projections | Replace with the Commitrail record/index validator |
| Active-state projections | Replace with durable-disposition and transient-state Commitrail validation |
| Reviewer contracts | Preserve and update `reviewer_contracts.py` for Commitrail terminology |
| Stale review contracts | Preserve `check_stale_review_contracts.py` |
| Reviewer and exact-target tests | Preserve `test_reviewer_contracts` and `test_review_target` |
| Lightweight workflow regression | Update it to assert the complete post-cutover command set |

The implementation may consolidate commands, but each row requires an
executable successor in Agent Gates; no protection disappears implicitly.

### 5. Remove `.agent-loop`

Delete the directory atomically after all live references and needed facts have
been migrated. Git history is the historical archive; no repository copy of
the entire old tree will be created.

### 6. Reconcile other worktrees

After cutover merges, each active worktree rebases on current `main`, removes
old-method changes, and translates only its current bounded work into the
Commitrail record. Unaffected test evidence remains valid only if the rebase
does not change its impact cone.

### 7. Blind stress test

Select the next already-needed Workstream bounded change. Its owner uses only
the published Commitrail entry path without private coaching or compatibility
files. Measure record count, preparation effort, reviewer routing, stale-state
failures, rebase handling, and whether a new contributor can identify current
and remaining work. The stress-test PR records findings but does not mix
Commitrail implementation corrections into the product change. A demonstrated
method defect earns a later bounded correction only if needed.

## Verification strategy

- Assert `.agent-loop` does not exist at the candidate head.
- Verify the relocation inventory has no unclassified external reference,
  current-ledger row, or internal normative/durable record.
- Scan tracked files for legacy names and paths, with narrowly documented
  historical exceptions only if essential.
- Validate all Markdown links.
- Run updated Commitrail validator and its positive and negative regression
  suite across every supported durable disposition.
- Run reviewer-contract and exact-target review tests.
- Run Agent Gates and all workflow/schema validation affected by path changes.
- Run architecture, CI-integrity, docs, QA, reuse, and senior-engineering
  review for the cutover; security review applies to trusted-base and evidence
  handling changes.
- Complete the live stress-test PR and capture measured findings in its one
  change record.

## Rejected approaches

- No compatibility symlink, alias, or permanent `.agent-loop` reader.
- No automatic migration of all 1,246 initiative files.
- No signed local authority, start token, merge-intent queue, or second
  permission system.
- No mandatory fixed reviewer count.
- No second post-merge reconciliation PR.

## Rollback

Before merge, revert the candidate branch. After merge, restore only through a
new human-approved PR. Git history retains the former records, but the old
runtime process must not silently reactivate.
