# Chunk Map: WS-POL-003 - Unified Project Guide Compilation

All chunks are L1 and one PR each. Product behavior is built hidden before AUTH
activation; only a later live-cutover chunk exposes it. Open pull requests show
transient work, and no chunk starts automatically.

Use the [current cross-owner dependency contract](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
with this map. ARCH-04A capability proof is independent upstream work, not a
post-task requirement. Historical split parents 05/06 are not extra PRs.

| Chunk | Purpose | Hard dependency |
|---|---|---|
| `WS-POL-003-01` | Strict unified contracts and read-only pre/post capability projections. Merged PR #299. | Merged ART-04B1 and canonical CHECKER/POL post-submit registry |
| `WS-POL-003-02` | One `compile_project_guide` adapter method and fake-runtime proof. Merged PR #301. | 01 |
| `WS-POL-003-03A` | Hidden immutable attempt/compilation schema, validator, repository, crash fence, and deny-by-default authorization seams. | 02 |
| `WS-AUTH-001-12I` | Register and activate exact PM compilation request/recovery plus fixed-service compilation execute authority. | 03A exact resource/action manifest |
| `WS-POL-003-03B` | Complete authorized immutable compilation persistence; no policy projection or setup-service cutover. POL-04A is the next boundary. | 03A + AUTH-12I satisfied |
| `WS-POL-003-04A` | Complete hidden one-attempt setup orchestrator over the complete result; the three legacy inference methods are denied and unreachable in the candidate call graph. | 03B |
| `WS-POL-003-04A3` | Complete hidden compilation-derived sufficiency/artifact-policy projections with immutable provenance and no model call. | Merged 04A |
| `WS-POL-003-04A2` | Complete hidden immutable setup-ledger finalization with closed outcomes and no live route. | Merged 04A3 |
| `WS-AUTH-001-12J` | Complete exact fixed-service authority for the two compilation-derived projection ports. | Merged 04A3 |
| `WS-AUTH-001-12B2` | Complete exact setup-finalization authority (PR #384). | Complete POL-04A2 + AUTH-12J |
| `WS-POL-003-04B1` | Complete hidden automatic request authority and origin custody in the same request operation; current PM replay validation. | AUTH-12I + completed immutable compilation and ART material foundation |
| `WS-POL-003-04B` | Planned automatic initial live cutover with replaceable runtime/model/instructions through the hidden projection/finalization chain; physically delete the three superseded inference methods, prompts, affected consumers and obsolete tests in the same change. | 04B1 + merged 04A3 + 04A2 + AUTH-12J + AUTH-12B2 + ARCH-04A catalogue/schema |
| `WS-POL-003-05A` | Hidden complete review package, PM correction/manual rerun in a new generation, and approval/effective/pre-submit behavior. | 04B |
| `WS-AUTH-001-12F4` | Activate exact review-package read, PM correction/approval and PREP composition for the hidden 05A manifest. | 05A |
| `WS-POL-003-05B` | Live PM approval and trusted effective/pre-submit projection cutover. | 05A + AUTH-12F4 |
| `WS-POL-003-06A` | Hidden deterministic post-submit projection and separate approval behavior; zero model calls. | 05B |
| `WS-AUTH-001-12G` | Activate exact fixed-service projection plus PM approval/correction authority for the hidden 06A manifest. | 06A |
| `WS-POL-003-06B` | Live deterministic post-submit projection/approval cutover with zero additional inference. | 06A + AUTH-12G |
| `WS-POL-003-07` | One typed facade over existing ART pre and CHECKER post contracts; no post-result persistence. | 06B + ARCH-04A registered capability proof + merged ART-04B1-04B3 |
| `WS-AUTH-001-12H` | Complete internal guide activation authority over the approved current-generation unified chain. CP08, ARCH-03A and ARCH-03B1 are delivered. Remaining ARCH-03B queues/actor projections come next; invalidation follows shared committed claims, then ARCH-03C public activation. CP09 remains later. | POL-07 + corrected AUTH-12B2 + CP05 active ContributionPolicy behavior + CP06 validation + CP07 ProjectGuide binding |
| `WS-POL-003-08` | Supplementary visibility; separate remaining cleanup is parked and handled within each affected module. Essential review/correction belongs to 05A/05B and 06A/06B. | Planned after 07 + AUTH-12H + canonical WS-ARCH-001-04E manifest; any separately authorized retained-data change requires CP09's inventory, mapping and readability/recoverability proof for affected facts; no cleanup prerequisite for 04B |

The 04E manifest proves canonical routing, not legacy-history preservation.
Any separately authorized POL-08 data removal must reuse CP09's preservation
proof. Module code cleanup grants no data-deletion authority. This is not a dependency on completing unrelated CP09
deletions; retained history must remain readable/recoverable and must never be
guessed or silently discarded.

## Merged ART admission foundation

ART-04B3, XINT-06A, ART-04C1/04C2 and replacement WS-ARCH-001-02A-02H are
merged. The hidden admission-backed Submission transaction is authorized;
historical XINT-05A/05B and ART-05A/05B are non-executable. The remaining path
to canonical `allow_review` is coordinated by the current WS-ARCH-001 dependency contract and does not
run in parallel with a second Submission path.

Once a unified guide generation is active, ART admission must bind only that
generation's approved compilation-derived policy hashes; stale pre-unified or
mixed-generation chains deny through the existing locked-lineage checks.

## Post-submit execution gate

ARCH-04A contracts/capability conformance precede POL-07 and guide activation.
ART post-submit materialization and durable CHECKER execution follow only through
ARCH-04B/04C after POL-07 and task readiness merge.
WS-ARCH-001-04D is the later replacement activation gate. Historical
XINT-06B and AUTH-14 contracts are superseded/non-executable.
