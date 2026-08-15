# Discovery: WS-CI-004 Review Evidence Integrity

## Current behavior

The active Agent Gates workflow checks out the exact pull-request head and runs
repository integrity checks, but it does not validate internal reviewer evidence.
Reviewer routing is risk-based and human merge approval remains mandatory.

The nine `.codex/agents/*.toml` files share nearly identical boilerplate. They
require comparison with a base branch but do not require base/head SHAs,
merge-base resolution, dirty-state inspection, end-of-review freshness, prior
finding replay, or evidence provenance in their output.

The problem is not only missing provenance. Generic prompts let a reviewer claim
its specialty without proving that it detects the defects it owns. Documentation
review has missed stale current-state wording; architecture review has missed
private imports, public-port ownership, and ledger asymmetry. No specialty has a
complete isolated must-find and false-positive evaluation suite, so prompt
presence is currently being mistaken for reviewer effectiveness.

## Relevant files and modules

| Path | Current role | Gap |
|---|---|---|
| `.codex/agents/*.toml` | Nine specialty reviewer prompts | Universal review-subject and evidence rules are absent and duplicated |
| `.agents/skills/*-review/SKILL.md` | Specialty review checklists | Broad focus questions; no shared exact-head protocol |
| `.agents/skills/evidence-gate/SKILL.md` | Pre-fanout deterministic checklist | Does not bind results to a revision or verify evidence claims |
| `.agents/skills/task-chunk-loop/SKILL.md` | Bounded implementation workflow | Reruns failed reviewers only; a prior pass may become stale |
| `.agents/skills/plan-review/SKILL.md` | L1 plan review | Does not require consumer/import/ledger/historical-state tracing |
| `.agents/skills/pr-trust-bundle/SKILL.md` | PR evidence summary guidance | Does not require run provenance or one final reviewed head |
| `.agent-loop/templates/INTERNAL_REVIEW_EVIDENCE.md` | Optional durable review template | Records SHA/run IDs, but the active process does not enforce or clearly interpret them |
| `.agent-loop/templates/PR_TRUST_BUNDLE.md` | Canonical trust-bundle template | Has review fields but no freshness/replay rules |
| `.github/workflows/agent-gates.yml` | Exact-head deterministic repository checks | Correctly avoids making AI review merge authority; no internal review freshness check |
| `scripts/workstream_agent_gate.py` | Read-only risk sensor | Useful diff inventory; not a review attestation tool |

## Failure replay

PR #338 initially recorded all internal tracks and deterministic checks as
passing. Five later commits were needed to correct issues that record missed:

1. preserve the tracked CP03 contract path;
2. declare atomic `planned` outcomes rather than future implementation as
   complete;
3. expose ACTORS/PROJECTS public owner ports and keep CON lifecycle truth in CON;
4. preserve completed CP02 history rather than rewriting it;
5. expose `ServiceIdentity` through `actors.api` and retire the exact private
   AUTH import-ledger edges.

Recent PRs #331, #334, and #336 also contain reviewer-pass summaries without one
uniform exact-head/run-provenance format. PR #336 explicitly records that an
earlier pass was superseded by later exact-head QA.

## Historical implementation

The repository previously contained `scripts/check_internal_review_evidence.py`.
Its reusable core required a resolvable reviewed commit, UTC timestamp, reviewer
run references, closed result tokens, no unresolved blocking findings, and
rejected relevant changes after review.

Commit `baffbe8a` removed that checker together with signed starts, active leases,
merge intents, loop memory, recovery certificates, chunk-scope enforcement, and
more than 20,000 lines of combined process machinery. The removal restored the
simple contribution loop because derived state and self-authorizing recovery had
made contribution circular and brittle.

The exact-revision core is useful. The coupled authorization/orchestration system
is not.

## External principles reviewed

- [SLSA's attestation model](https://slsa.dev/attestation-model) (SLSA v1.2,
  accessed 2026-08-15)
  separates the exact subject from the predicate that makes claims about it;
  [SLSA provenance](https://slsa.dev/provenance) (SLSA v1.2, accessed
  2026-08-15) treats provenance as
  verifiable information about where an artifact came from. Applied here, a
  review result needs an unambiguous subject digest: the reviewed Git revision.
- [SLSA specification](https://slsa.dev/spec/) (v1.2, accessed 2026-08-15)
  separates an attestation's
  subject and verified properties. Applied here, commit identity and reviewer
  conclusions must be separate fields rather than one prose claim.
- [GitHub protected-branch guidance](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
  (accessed 2026-08-15)
  records approvals against a diff and supports dismissing stale approvals or
  requiring approval of the latest reviewable push. Internal review should use
  the same freshness principle without replacing GitHub authority.
- [NIST SSDF](https://csrc.nist.gov/projects/ssdf) (accessed 2026-08-15)
  recommends risk-based secure
  development, provenance, documented security requirements/risks/design
  decisions, and continuous improvement rather than a ceremonial checklist.
- [OpenSSF Scorecard](https://github.com/ossf/scorecard) (accessed 2026-08-15)
  treats code review,
  branch protection, and CI as distinct supply-chain signals. Workstream should
  preserve that independence.

## Existing tests and gaps

Current lightweight Agent Gates test repository checks and atomic chunk state.
There is no active test suite for:

- reviewer start/end SHA equality;
- relevant-delta invalidation after a pass;
- reviewer output provenance;
- prior-finding replay;
- false trust-bundle evidence;
- ownership/import/debt-ledger trace expectations;
- all required reviewer results converging on one final head.
- isolated must-find and must-not-flag evaluations for each reviewer specialty;
- cross-specialty routing without invented conclusions.

## Risks discovered

| Risk | Why it matters | Proposed handling |
|---|---|---|
| Self-referential committed evidence | Adding evidence changes the head it describes | Keep internal receipts outside Git; GitHub owns durable evidence |
| Universal fanout | Slows contribution and creates ceremony | Preserve risk routing and invalidate only affected tracks |
| Prompt drift | Nine TOMLs duplicate universal rules | Put universal rules in one mandatory shared skill |
| Prose passes | Claims can outrun proof | Require explicit evidence source and observed result |
| Diff-only review | Unchanged consumer or ledger can invalidate design | Require impact-cone tracing into relevant base code and ledgers |

## Unknowns requiring measurement

- How often final-head changes affect only evidence/docs versus reviewer-owned
  behavior.
- Whether a compact structured review receipt materially improves human review.
- Whether session receipts improve review enough to justify keeping them.

## Existing conventions to preserve

- Review is evidence, not contribution authority.
- Human approval owns merge.
- Internal and external review remain distinct.
- Reviewer routing remains proportionate to risk.
- GitHub open PRs represent transient work; durable files do not imitate a queue.
- No second post-merge memory PR.
