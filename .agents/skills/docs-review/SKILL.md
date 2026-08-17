---
name: docs-review
description: Review whether a code change requires documentation updates, examples, migration notes, policy docs, or developer onboarding updates.
---

# Docs Review

Review whether docs match the code change.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged entry and authority pages, replay prior findings,
separate executed from inspected evidence, state uncertainty and freshness, and
hand off non-documentation findings without inventing another specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.
Atomize every material criterion. For every behavior atom, record its owner, implementation source, named proof,
execution custody, and result. Missing or narrative-only rows block PASS.

## Focus

- Public behavior changes
- API/schema changes
- New commands
- New environment variables
- New policy behavior
- Migration notes
- Developer onboarding impact
- README or runbook updates
- Architecture decision records

## Completeness probe

Map each changed fact to every current entry page, canonical specification,
status projection, example, and historical record that could contradict it.
Verify lifecycle state and tense independently; a generally correct document
does not excuse one stale authority claim.
Run the repository Markdown-link and stale-wording checks when those scripts
exist, and record their executed results. Confirm all requested sub-agent
sessions are closed as review evidence; this is a state observation, not a
shell command.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Docs required: yes/no
Missing docs:
Suggested doc locations:
Fact-to-document traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
