# PR Trust Bundle: WS-XINT-003-01

## Intent and result

Reconcile the complete review/revision authorization contract before runtime
work. The result is one canonical custody inventory, one future policy writer,
and one safe ART evidence-binding activation sequence. No behavior is active.

## Scope

Planning/canonical Markdown only. No backend code, Alembic migration, catalogue
mapping, runtime `ActionOwner`, service provisioning, route, job, or product
lifecycle behavior changed.

## Design

- 19 existing `review.*` actions stay registered planned.
- Four recovery/lifecycle actions stay missing until registration-only 08R.
- REV owns policy semantics and immutable versions; AUTH owns PREP, mutation
  authorization, and decision evidence.
- Existing project ReviewPolicy/RevisionPolicy records are reused. XINT-003-02
  will introduce the sole append-only writer and retire the four named legacy
  callable mutation/construction paths.
- Runtime ART owner remains `WS-XINT-002-07`. Planning sub-wave 07A alone
  activates packet/finding binding; 07B only extends response evaluation.
- Hidden REV obligation/preparation precedes 07B; human response activation
  follows both.

## Proof

The canonical table contains 25 local human/privileged/service rows, four
externally owned shared actions, and 29 matching hidden-feature dependency
rows. It fixes exact principals, scopes, resources, owners, waves, identities,
static membership, forbidden principals, and audit/provenance facts.

Deterministic stale-doc, artifact-contract, Workstream wording, Markdown-link,
and whitespace checks pass. No tests or CI configuration were changed or
weakened. Hosted exact-head Agent Gates and Backend CI remain required.

## Review

Architecture, security/auth, product/operations, QA/test, docs, and
reuse/dedup passed. Senior engineering passed with low stale-wording risks,
which were corrected. The remaining filename observation is documented in the
internal review and does not create duplicate identifiers or behavior.

## Human review focus

Confirm action completeness, the sole policy writer boundary, ART runtime owner
versus sub-wave distinction, the 07B-before-human-activation order, and absence
of runtime activation.

Only the human may merge the PR.
