# Discovery: WS-ENG-006 - Contributor Engineering Onboarding

Discovery was performed read-only against trusted `main` on 2026-07-22.

## Current behavior

- `AGENTS.md` is the strongest summary of the engineering rules and uses the
  canonical `Automated Merge Memory` loop wording.
- Trusted loop state is signed and generated on `automation/loop-memory`.
- Starts are initiative-local and distinct initiatives may run concurrently.
- Internal review evidence and one schema-v2 merge intent are required before a
  PR can complete the engineering loop.
- There is no root `CONTRIBUTING.md`.
- `README.md` and `.agent-loop/README.md` still say `Memory Update` rather than
  `Automated Merge Memory`.
- `docs/operations_post_merge_memory.md` contains an obsolete requirement that
  all signed initiatives be idle before a start, despite later documenting
  initiative-local concurrency.
- The PR template captures the chunk and reviewed SHA but does not visibly ask
  for signed-start run provenance, authorized main SHA, phase, or contract blob.
- A brand-new initiative cannot currently place its first contract on trusted
  `main` without circular authority: writer-directed selection reads only exact
  current-main contracts, while post-04B merge policy requires a prior active
  signed start.

## Relevant files/modules

| Path | Purpose | Notes |
|---|---|---|
| `AGENTS.md` | Mandatory repository instructions for coding agents | Complete but dense; not a human onboarding guide. |
| `README.md` | Public repository entry point | Links loop policy but not a contribution guide; loop wording is stale. |
| `.agent-loop/README.md` | Durable loop overview | Too brief for newcomer operations; loop wording is stale. |
| `.agent-loop/policies/repository-engineering-policy.md` | Canonical engineering boundaries | Correct concurrency model; needs a contribution entry-point reference. |
| `docs/operations_post_merge_memory.md` | Signed merge/start/cancel runbook | One stale global-idle sentence conflicts with initiative-local concurrency. |
| `.github/pull_request_template.md` | Human PR trust-bundle prompt | Strong review/evidence sections; missing visible signed-start provenance. |
| `.agent-loop/templates/PR_TRUST_BUNDLE.md` | Canonical trust-bundle template | Must remain synchronized with the GitHub template. |
| `scripts/test_agent_gates.py` | Deterministic repository-policy assertions | Does not currently protect a root contribution guide or canonical loop/concurrency wording across entry docs. |
| `scripts/check_markdown_links.py` | Changed-Markdown local-link check | Suitable verification for the new guide and synchronized docs. |

## Current tests

| Test path | What it covers | Gaps |
|---|---|---|
| `scripts/test_agent_gates.py` | Merge intents, internal-review evidence, loop state, workflows, templates, coverage commands | No contribution-guide contract; no cross-document loop/concurrency assertion. |
| `scripts/check_markdown_links.py` | Local links in changed Markdown files | Runs only for changed Markdown; it does not enforce policy semantics. |
| `scripts/check_stale_workstream_wording.py` | Retired product terminology | Does not cover engineering-loop drift. |

## Dependencies/integrations

- GitHub Actions `Loop Memory Explicit Event` authenticates signed starts and
  cancellations.
- GitHub Actions `Loop Memory` reconciles trusted merges into the signed
  generated branch.
- Agent Gates enforce repository-authored process evidence and policy invariants.
- GitHub branch permissions determine who can satisfy start authority; docs do
  not grant repository permission.

## Risks discovered

| Risk | Why it matters | Suggested handling |
|---|---|---|
| Product Contributor and repository contributor terminology collide | A newcomer may confuse runtime authority with GitHub contribution rights. | Define the distinction at the top of `CONTRIBUTING.md`. |
| Documentation creates an apparent bypass for existing patches | Retroactive authorization would undermine scope and review custody. | State that patches are preserved as discovery input and adopted only after signed start. |
| Narrative docs drift from workflows | Humans may follow stale global-idle or manual-memory instructions. | Add exact cross-document assertions in Agent Gates. |
| PR template records mutable prose only | Reviewers may not see the signed-start binding. | Add explicit provenance fields while keeping workflow state canonical. |
| Over-documentation duplicates policy | Multiple prose copies can drift. | Keep `CONTRIBUTING.md` operational and link canonical policy/runbooks for detail. |

## Unknowns/questions for human

| Question | Why it matters | Needed before chunk? |
|---|---|---|
| What public repository route may a contributor without write permission use to request planning and maintainer adoption? | No existing issue template or other canonical intake path was found; private chat cannot be the durable authority promised by the initiative. | Yes. |
| How can the first reviewed contract of a new initiative enter trusted `main` without an earlier signed start? | Current contract resolution and post-04B merge rules are circular. | Yes; a separately reviewed loop design is required before this initiative can publish. |

## Existing conventions to preserve

- One bounded chunk and one immutable merge-intent file per PR.
- No implementation before an exact reviewed contract and signed start.
- Required internal reviewer tracks finish before push, PR, or review request.
- External checks supplement rather than replace internal reviews.
- Only trusted automation writes canonical post-merge memory.
- Explicit user approval is required for the specific PR merge.
