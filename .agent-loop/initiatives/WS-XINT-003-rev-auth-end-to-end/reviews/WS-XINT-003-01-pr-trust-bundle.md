# PR Trust Bundle: WS-XINT-003-01

## Chunk

`WS-XINT-003-01` — REV-AUTH Contract Reconciliation.

## Goal

Settle complete action custody, the sole review/revision policy writer path,
and the safe ART finding/response activation order before runtime work.

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

## Acceptance criteria proof

- All 19 registered planned REV actions, four missing registration actions,
  two policy actions, and four XINT-002 shared actions are classified.
- Every action has an exact hidden-feature dependency; every fixed service has
  an exact identity, membership, mode/scope, forbidden principals, and audit
  facts.
- REV-03P/AUTH-12D2 name one external service and internal repository writer
  path plus the exact legacy mutators to retire.
- Runtime ART owner remains `WS-XINT-002-07`; 07A alone changes availability,
  and 07B is evaluator-only after hidden REV obligation/preparation behavior.
- All runtime actions remain planned/unavailable and four actions remain
  unregistered.

## Commands run

- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_markdown_links.py`
- `git diff --check`

## Test delta

No test, skip, exclusion, or assertion changed. The hosted Backend semantic-
lane suite and coverage gate run on the exact PR head.

## CI integrity

No workflow, dependency, test runner, Ruff rule, coverage threshold, or package
script changed. Agent Gates and Backend must pass on the exact final head.

Deterministic stale-doc, artifact-contract, Workstream wording, Markdown-link,
and whitespace checks pass. No tests or CI configuration were changed or
weakened. Hosted exact-head Agent Gates and Backend CI remain required.

## Review

Architecture, security/auth, product/operations, QA/test, docs, and
reuse/dedup passed. Senior engineering passed with low stale-wording risks,
which were corrected. The remaining filename observation is documented in the
internal review and does not create duplicate identifiers or behavior.

## External review

CodeRabbit is required. Every valid comment must be fixed or explicitly
resolved before human merge.

## Remaining risks

This PR defines future enforcement but activates none. Each later runtime chunk
must refresh exact current-main symbols, migration head, hidden feature
manifest, and denial/concurrency proof before activation.

## Follow-up work

After human merge and a separate explicit request, refresh WS-XINT-003-02. Do
not begin runtime policy work automatically.

## Human review focus

Confirm action completeness, the sole policy writer boundary, ART runtime owner
versus sub-wave distinction, the 07B-before-human-activation order, and absence
of runtime activation.

## Human merge ownership

Only the human may merge this PR.
