# Internal Review Evidence: WS-REV-001-PLAN4

## Scope

Current-main planning-only refresh of the complete REV lifecycle after merged
AUTH 02D at `3479ee71`.

## Results

- Architecture: PASS. REV begins at exact owner-supplied `allow_review` facts,
  preserves all subsystem boundaries, and safely starts with 03A1 persistence.
- QA/product: one high stale-vocabulary verification failure; lifecycle,
  contribution cardinality, checker-remediation separation, and chunk order had
  no blocking finding. The stale phrase was corrected.
- Security/docs/CI: the same high stale-vocabulary verification failure; no
  runtime, migration, test, CI, dependency, or product-doc scope drift. The
  stale phrase was corrected.

The corrected exact diff passes the failed authorization wording command and
the complete deterministic verification set.

## End-to-end owner-plan reconciliation

A second critical review traced AUTH/XINT, ART/XINT, CON, and REV production and
consumption gates. It found three valid planning defects:

- 03A2 had incorrectly been treated as independent even though ReviewLease
  requires CON-03B's non-null canonical ContributionPolicyVersion FK;
- ART-07A and REV-03B formed a packet-contract cycle without a contract-only
  owner precursor; and
- audit/outbox/CON gates and positive AUTH proof were not distinguished
  precisely enough from generic persistence or unavailable-action testing.

The plan now gates 03A2 on CON-03B, requires ART to publish the membership port
before REV-03B, orders REV manifest -> ART-07A materialization -> REV-07A read,
gates 04B on CON-02C, names CON-06/07 and later dispatcher/release dependencies,
and reserves positive authorization proof for matching XINT activation. It also
records stale owner-plan status as an owner gap that each REV consumer must
verify from signed current-main evidence rather than silently repair.

The architecture re-review passed after two low cleanup findings (duplicate
risk IDs and conditional gate wording) were corrected. Security/docs/CI and
QA/product reported no blocking finding. QA's low stale parent-chunk reference
in the conformance matrix was corrected to 03A1, 05A, and 09A4.

## Deterministic evidence

- `python3 scripts/check_stale_review_contracts.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_markdown_links.py`
- `git diff --check`

All passed after correction. This planning chunk changes no runtime code or
tests; GitHub exact-head checks remain required for a PR.
