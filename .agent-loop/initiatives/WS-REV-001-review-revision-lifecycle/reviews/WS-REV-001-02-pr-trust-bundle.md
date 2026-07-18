# PR Trust Bundle: WS-REV-001-02

## Intent

Make REV-02 implementation-ready without coding against retired contributor
identity storage or combining three L1 migrations in one PR.

## Design

- Parent 02 becomes a non-executable split record.
- 02A owns guide activation sequence, reactivation, publication locking, and
  Task guide stamps.
- 02B owns immutable ReviewPolicy/RevisionPolicy plus dormant terminal Task and
  TaskAssignment schema compatibility.
- 02C owns exact Submission attribution, guide stamps, predecessor lineage, and
  finalized-row protection.
- AUTH retains contributor-field and ActorProfile schema ownership.
- D6 creates no synthetic Review; blocking remains in 09A and explicit
  cancellation remains in 11.

## Scope

Changed only REV planning, contracts, conformance/test design, review evidence,
and one schema-v2 merge intent. No runtime, migration, executable test, route,
workflow, dependency, AUTH, ART, or CON runtime file changed.

## Evidence

- Required internal reviewer tracks: PASS.
- Mandatory stale-contract scanners: PASS.
- Markdown links and diff integrity: PASS.
- Agent gates: 87 passed.
- Merge intent: PASS for `WS-REV-001-02 -> WS-REV-001-02A`, explicit start.

## Risks

- AUTH foundation timing can move the future migration head. REV reserves no
  identifier.
- Historical attribution or guide context may be ambiguous. Future migrations
  fail with remediation rather than guessing.
- Preference/lease defaults remain a human decision before 02B.

## Human review focus

- Accept the 02A/02B/02C split and dependency order.
- Confirm AUTH remains the contributor/canonical-human schema owner.
- Confirm terminal states remain dormant and no synthetic reject exists.
- Confirm the two duration defaults stay unresolved until explicitly approved.

## Stop

Merge planning only with explicit approval. Automated memory must stop at 02A;
do not start runtime automatically.
