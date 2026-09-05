---
name: docs-review
description: Review whether a code change requires documentation updates, examples, migration notes, policy docs, or developer onboarding updates.
---

# Docs Review

Review whether docs match the code change.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Apply shared proof fields proportionately; do not require database ceremony for
documentation-only claims. Use compatible inspection or structure proof and
keep product/runtime conclusions with their owning reviewers. These obligations
are adopted through the blind evaluation recorded by `WS-CI-005-03`.

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
capability ledger, and example that could contradict it. Read historical records
only when a current page adopts them; do not demand changes to preserved archives.
Verify lifecycle state and tense independently; a generally correct document
does not excuse one stale authority claim.
Inspect the lead's Markdown-link and stale-wording results bound to this target;
run a focused independent check when a contradiction needs investigation. The
lead owns final CI, PR-summary freshness, and closing reviewer sessions. Report
stale evidence as a readiness handoff, separate from the documentation verdict.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Docs required: yes/no
Missing docs:
Suggested doc locations:
Fact-to-document traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
