# Chunk Map: WS-POL-003 - Unified Project Guide Compilation

All chunks are L1 and one PR each. Product behavior is built hidden before AUTH
activation; only a later live-cutover chunk exposes it. Open pull requests show
transient work, and no chunk starts automatically.

| Chunk | Purpose | Hard dependency |
|---|---|---|
| `WS-POL-003-01` | Strict unified contracts and read-only pre/post capability projections. Merged PR #299. | Merged ART-04B1 and canonical CHECKER/POL post-submit registry |
| `WS-POL-003-02` | One `compile_project_guide` adapter method and fake-runtime proof. Merged PR #301. | 01 |
| `WS-POL-003-03A` | Hidden immutable attempt/compilation schema, validator, repository, crash fence, and deny-by-default authorization seams. | 02 |
| `WS-AUTH-001-12I` | Register and activate exact PM compilation request/recovery plus fixed-service compilation execute authority. | 03A exact resource/action manifest |
| `WS-POL-003-03B` | Complete authorized immutable compilation persistence; no policy projection or setup-service cutover. POL-04A is the next boundary. | 03A + AUTH-12I satisfied |
| `WS-POL-003-04A` | Complete hidden one-attempt setup orchestrator over the complete result; the three legacy inference methods are denied and unreachable in the candidate call graph. | 03B |
| `WS-POL-003-04A3` | Complete hidden compilation-derived sufficiency/artifact-policy projections with immutable provenance and no model call. | Merged 04A |
| `WS-POL-003-04A2` | Planned hidden purpose-specific setup-ledger finalization with closed outcomes and no live route. | Merged 04A3 |
| `WS-AUTH-001-12J` | Complete exact fixed-service authority for the two compilation-derived projection ports. | Merged 04A3 |
| `WS-AUTH-001-12B2` | Planned exact setup-finalization authority for the future 04A2 manifest. | Planned POL-04A2 prerequisite + completed AUTH-12J |
| `WS-POL-003-04B` | Planned explicit-PM-request live cutover through the hidden projection/finalization chain; remove every legacy inference call from live reachability. | Merged 04A3 + 04A2 + AUTH-12J + AUTH-12B2 |
| `WS-POL-003-05A` | Hidden approval/effective/pre-submit projection behavior over the complete immutable result. | 04B |
| `WS-AUTH-001-12F4` | Activate exact PM approval authority and PREP composition for the hidden 05A manifest. | 05A |
| `WS-POL-003-05B` | Live PM approval and trusted effective/pre-submit projection cutover. | 05A + AUTH-12F4 |
| `WS-POL-003-06A` | Hidden deterministic post-submit projection and separate approval behavior; zero model calls. | 05B |
| `WS-AUTH-001-12G` | Activate exact fixed-service projection plus PM approval/correction authority for the hidden 06A manifest. | 06A |
| `WS-POL-003-06B` | Live deterministic post-submit projection/approval cutover with zero additional inference. | 06A + AUTH-12G |
| `WS-POL-003-07` | One typed checker-service port with one complete pre and one complete post command. | 06B + merged ART-04B1-04B3 execution/evidence contract |
| `WS-AUTH-001-12H` | Activate guide publication only over the complete approved current-generation unified chain and CON clean cut. | 07 + corrected 12B2 + owning CON clean cut |
| `WS-POL-003-08` | Visibility, generation-safe correction, physical legacy inference/parallel-route cleanup, and activation compatibility proof. | Planned after 07 + AUTH-12H + canonical WS-ARCH-001-04E manifest; not a prerequisite for 03A |

## Merged ART admission foundation

ART-04B3, XINT-06A, ART-04C1/04C2 and replacement WS-ARCH-001-02A-02H are
merged. The hidden admission-backed Submission transaction is authorized;
historical XINT-05A/05B and ART-05A/05B are non-executable. The remaining path
to canonical `allow_review` is coordinated by WS-ARCH-001 PLAN2 and does not
run in parallel with a second Submission path.

Once a unified guide generation is active, ART admission must bind only that
generation's approved compilation-derived policy hashes; stale pre-unified or
mixed-generation chains deny through the existing locked-lineage checks.

## Post-submit execution gate

ART post-submit materialization/output behavior may begin only through the
split WS-ARCH-001-04 contracts after POL-06B/07 and task readiness merge.
WS-ARCH-001-04D is the later replacement activation gate. Historical
XINT-06B and AUTH-14 contracts are superseded/non-executable.
