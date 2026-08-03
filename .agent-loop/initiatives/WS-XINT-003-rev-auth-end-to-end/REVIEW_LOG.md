# Review Log: WS-XINT-003 REV-AUTH End-to-End Contract

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
