# WS-ENG-009-01 — Atomic Commitrail Cutover

## Goal

Commission Commitrail as Workstream's only active engineering method and remove
`.agent-loop` without changing product behavior or losing current normative
facts.

## Allowed files

- `.commitrail/**`
- `.agent-loop/**` for removal and this chunk's final projection
- `.agents/skills/**`
- `.codex/**`
- `.github/pull_request_template.md`
- `.github/workflows/agent-gates.yml`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md`
- `docs/**` where engineering-method or relocated normative references require it
- `scripts/**` for Commitrail validation and regression tests
- Existing architecture/test files only where they assert the retired path

## Not allowed

- Backend or frontend product behavior
- Database models or migrations
- API, authorization, artifact, review, contribution, or compensation behavior
- Coverage-floor reduction, test deselection, or check bypass
- Compatibility aliases or dual active engineering methods
- Copying the full `.agent-loop` tree into another archive directory

## Acceptance criteria

- `.commitrail` provides the canonical entry point, index, combined change
  template, and concise overviews for current multi-PR initiatives.
- Repository guidance, skills, reviewer agents, PR template, checks, and tests
  consistently use Commitrail.
- Still-normative facts formerly cited from `.agent-loop` are owned by current
  specifications, ADRs, or concise Commitrail decisions.
- A relocation inventory classifies every pre-cutover reference originating
  outside `.agent-loop` and identifies its destination or historical-only
  disposition.
- `.agent-loop` is absent from the final candidate.
- No active tracked file instructs a contributor to use retired signed-loop,
  merge-intent, queue, recovery-certificate, or projection machinery.
- Commitrail validation preserves bounded scope, evidence adequacy,
  exact-target review, proportional routing, durable dispositions, and human
  merge authority without creating contribution permission.
- Other worktrees receive explicit rebase/translation guidance.

## Risk class

L1 engineering-process, CI-integrity, and repository-navigation change. No
product behavior is in scope.

## Verification commands

```bash
test ! -e .agent-loop
git grep -n -E '\.agent-loop|signed loop|loop memory|merge-intent|recovery certificate'
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 -m unittest -v scripts.test_commitrail_contracts scripts.test_reviewer_contracts scripts.test_review_target scripts.test_lightweight_agent_gates
```

The legacy-wording scan must return no active dependency; any intentional
historical quotation requires explicit reviewer acceptance.

## Required reviewers

- Architecture
- CI integrity
- Documentation
- QA
- Reuse/deduplication
- Security
- Senior engineering

Product-operations review is not required unless the diff touches Workstream
product lifecycle language beyond link relocation. Test-delta review is
required only if existing assertions are removed or materially rewritten.

## Human review focus

- Does the cutover preserve useful controls while materially reducing burden?
- Is any product truth lost or silently moved into process ownership?
- Can an unfamiliar contributor start without private instructions?
- Does any hidden dual system remain?
- Is the Workstream operating copy clearly distinguished from a future
  canonically licensed public Commitrail distribution?

## Merge state

- Outcome on merge: `planned`

The implementation contract becomes executable only after explicit human
approval. Its implementation PR must express its final disposition using the
current method until that same PR atomically replaces it.
