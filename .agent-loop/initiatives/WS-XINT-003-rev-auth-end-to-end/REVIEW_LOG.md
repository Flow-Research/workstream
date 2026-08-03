# Review Log: WS-XINT-003 REV-AUTH End-to-End Contract

## AUTH-readiness sequencing amendment — 2026-08-03

Post-02B review found a circular delivery dependency absent from the corrected
ART-AUTH model: REV needed stable AUTH contracts to implement, but most AUTH
contracts and principals were deferred until activation after REV merged. The
amendment adds unavailable 02C catalogue/principal readiness and 02D PREP/read
contract readiness, moves the four deferred actions forward, separates queue
read/claim/release-and-decline/timers by exact REV evidence, waits for REV-10
before decision activation, and reserves product-route release to REV-13C.

Architecture, security, and product/ops reviewers initially returned FAIL and
identified the circular dependency, deferred identities/actions, bundled
activation gates, premature REV-08 decision gate, and missing release fence.
Their required changes were incorporated before re-review.

## Initial review round

Architecture, security, product/ops, QA, and senior engineering returned FAIL;
docs returned PASS WITH CONDITIONS. Valid findings were:

- duplicate custody of XINT-002 packet/evidence and revision submission actions;
- response evidence incorrectly sequenced before human revision preparation;
- four privileged actions lacked a registration-only wave;
- two services sharing `review.reconcile.run` were split across activation;
- reviewer current-work and atomic packet-manifest semantics were incomplete;
- contributor Task Context, checker remediation, lifecycle recovery, and
  contribution/award conformance proof were incomplete;
- future planning skeletons were not clearly marked non-implementable; and
- canonical AUTH/role docs and links were missing from reconciliation scope.

The draft was revised to address every item. A second focused review round is
required before the planning PR is considered ready.

## Final review round

- Architecture: PASS after the human-REV versus XINT-002 ART/shared-submission
  custody split, 08R registration seam, and single `review.reconcile.run` wave.
- Security: PASS WITH LOW RISKS; the response-evidence lifecycle order and
  privileged registration gaps are resolved. Its informational discovery
  wording note was corrected.
- Product/ops: PASS WITH LOW RISKS; reviewer current-work, atomic packet
  manifest, contributor Task Context, checker remediation, CON source integrity,
  and shutdown/crash/reactivation proof are explicit. Its low wording note was
  corrected.
- QA: PASS WITH LOW RISKS; dependencies, global ActionId activation, 08R, denial
  proof, and non-implementable skeleton labeling are testable. Its informational
  XINT-002 wording note was corrected.
- Senior engineering: PASS WITH LOW RISKS; planning custody versus runtime owner
  evidence and XINT-002 boundaries are explicit. Its low wording note was
  corrected.
- Docs: PASS; canonical docs scope, links, terminology, and current process
  wording are aligned.

No reviewer finding remains open.

External CI and CodeRabbit results belong to the planning PR trust bundle and
external-review response.

PR #237 CodeRabbit review at head
`8250adf3ac52bc4bfee69fd5299dd70f21fb3ad1` found four valid documentation
integrity issues. The response reconciled 05A/05B availability versus 05D
revision evaluator extension, preserved the registration-only 08R boundary,
removed wording that implied 07A runtime activation, and recorded exact-head
review evidence. No comment was deferred.

The final CodeRabbit pass added two valid evidence clarifications: immutable
check-run IDs are now recorded for reviewed head `8250adf3`, and the external
response explicitly leaves the required human review open. Neither automated
review nor this response substitutes for human approval of the named contract
boundaries.

## WS-XINT-003-01 contract reconciliation

Architecture, security/auth, product/operations, QA/test, senior engineering,
docs, and reuse/dedup reviewed the completed docs-only reconciliation. Valid
findings corrected fixed-service identity drift, ART global-matrix wording,
runtime owner versus sub-wave ambiguity, missing per-action dependencies,
07B/human activation order, and obsolete signed-start gates. All tracks passed;
the final evidence is in `reviews/WS-XINT-003-01-internal-review.md`.

## WS-XINT-003-02A immutable policy identity and lineage

Architecture, security/auth, product/operations, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity reviewed the completed runtime
chunk. Valid findings corrected guide-selection freezing and exact joins,
CheckerRun-to-Submission Task binding, stale active E2E/docs surfaces, vacuous
legacy assertions, asymmetric immutability proof, and the final schema
fingerprint. All tracks passed after correction; no finding remains open. The
final evidence is in `reviews/WS-XINT-003-02A-internal-review.md`.

CodeRabbit's PR #242 review found missing ORM identity-shape metadata, overly
broad joined row locks, invalid active-guide fixture ordering, and a duplicated
test semantics mapping. Its post-main-merge review also found that the guide
sufficiency migration test did not protect cleanup when the initial downgrade
failed. All findings were valid and corrected; the exact response is in
`reviews/WS-XINT-003-02A-external-review-response.md`.

## WS-XINT-003-02B guide-bound policy mutation activation

Architecture, security/auth, product/operations, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity reviewed the completed runtime
chunk. Valid findings corrected full PREP and denial binding, replay-before-PREP
ordering, same-actor replay, exact opaque selectors, route rollback, database
successor/predecessor custody, live fixture bypasses, and operator docs. All
tracks passed after correction; no finding remains open. Final evidence is in
`reviews/WS-XINT-003-02B-internal-review.md`.

The first hosted Backend run failed the unchanged docstring gate because 22 new
02B callables reduced coverage to 79.7 percent. The new surface was documented,
and the same local gate passes at 80.5 percent without a threshold or workflow
change. External evidence is in
`reviews/WS-XINT-003-02B-external-review-response.md`.

CodeRabbit's first pass found valid replay timestamp immutability, downgrade
locking, historical trigger allow-list, fixture-copy, and replacement-selector
documentation issues. Its related indexing, typing, exact-exception,
constraint-shape, and reservation-branch notes were also valid. All were fixed;
none was deferred.

CodeRabbit's second pass found a valid post-lock guide-version revalidation gap;
it now denies before PREP consumption. Hosted migration evidence then exposed a
stale 0047 head constant and an incorrect unprefixed constraint lookup. The
0048 head is now exact, the installed constraint is behaviorally exercised for
independent and partial selector cases, and the focused isolated PostgreSQL
round trip passes.

PR #248 merged the completed chunk as `25fc27c4` on 2026-08-03. Backend, Agent
Gates, and CodeRabbit passed on the final PR head. No review/revision lifecycle
action was activated, and no successor chunk starts automatically.

## WS-XINT-003-02C AUTH catalogue and principal readiness

Architecture, security/auth, product/operations, QA, senior engineering, CI
integrity, reuse/dedup, test-delta, and docs reviewers examined the bounded 02C
implementation. Valid findings corrected the focused async-test selector,
canonical catalogue counts and fixed-service documentation, exact PostgreSQL
constraint-closure proof, no-grant provisioning proof, and operator-facing
0049 downgrade guidance. The four new actions remain planned/unavailable; the
six REV identities are registry and matrix values only, with no seeded
principal or lifecycle behavior.

Focused catalogue/service/custody tests pass (33 tests). Changed-module
coverage is 100.00 percent for `service_identities.py` and 97.89 percent for
`catalogue.py`. Ruff, mypy, collection, stale authorization/review scans, and
Markdown links pass. Local PostgreSQL execution is unavailable because this
worktree has no `WORKSTREAM_TEST_DATABASE_URL`; the exact 16 database-backed
tests collect cleanly and remain assigned to hosted schema and semantic lanes.

The first hosted semantic lanes exposed the expected post-0049 public-schema
fingerprint change before running product tests. The chunk contract now permits
only that exact `tests/conftest.py` fingerprint update; no reset allow-list or
schema-integrity behavior changed.

## WS-XINT-003-02D AUTH PREP integration readiness

Architecture, security/auth, product/operations, QA, senior engineering, CI
integrity, reuse/dedup, test-delta, and docs reviewers examined the inert typed
contract manifest. Valid findings split concealed no-work results from queue
lineage, made initial and revised decisions mutually exclusive, bound exact
revision predecessor/response facts, required lifecycle adjacency proof, and
closed lease, preference, and revision-preparation state vocabularies.

The manifest covers all 23 `review.*` actions while every row remains planned.
The two future evidence-ingest actions remain unsupported, XINT-002 actions are
reference-only, and no evaluator, route, background execution code, migration, or REV lifecycle
behavior is added. Fifteen contract tests and three existing PREP regression
tests pass; changed-module coverage is 100.00 percent. External exact-head CI
and CodeRabbit evidence remain pending the PR.
