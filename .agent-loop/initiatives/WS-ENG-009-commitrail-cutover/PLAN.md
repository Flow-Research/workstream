# WS-ENG-009 Plan — Commission Commitrail in Workstream

## Outcome

Replace `.agent-loop` atomically with the reduced Commitrail method, then use a
real Workstream change as a blind end-to-end stress test. The cutover changes
engineering process only and does not touch product behavior.

## Cutover design

### 1. Establish the canonical Commitrail package

Add `.commitrail/README.md`, `INDEX.md`, `CHANGE_TEMPLATE.md`, and
`initiatives/`. Include a repository-owned Workstream operating guide derived
from Commitrail v0.1. Do not describe that copy as Commitrail's canonical public
distribution until the author assigns publication terms and a canonical
location. The Workstream installation may add only the records earned by its
risk; it must not recreate every generic appendix as a required file.

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

Before deletion, produce a machine-readable or reviewable relocation inventory
for every tracked reference from outside `.agent-loop`, naming the destination
or recording that the reference was historical-only. Move categories 1 and 2
deliberately. Delete category 3 from the working tree. No canonical product rule
may depend solely on a deleted historical plan.

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
- Verify the relocation inventory has no unclassified external reference.
- Scan tracked files for legacy names and paths, with narrowly documented
  historical exceptions only if essential.
- Validate all Markdown links.
- Run updated Commitrail validator and its negative regression suite.
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
