# Chunk Map: WS-POL-003 - Unified Project Guide Compilation

All chunks are L1, one PR each, proposed, and inactive. Product behavior is
built hidden before AUTH activation; only a later live-cutover chunk exposes
it. No chunk starts automatically.

| Chunk | Purpose | Hard dependency |
|---|---|---|
| `WS-POL-003-01` | Strict unified contracts and read-only pre/post capability projections. | Merged ART-04B1 and canonical CHECKER/POL post-submit registry |
| `WS-POL-003-02` | One `compile_project_guide` adapter method and fake-runtime proof. | 01 |
| `WS-POL-003-03A` | Hidden immutable attempt/compilation schema, validator, repository, crash fence, and deny-by-default authorization seams. | 02 |
| `WS-AUTH-001-12I` | Register and activate exact PM compilation request/recovery plus fixed-service compilation execute authority. | 03A exact resource/action manifest |
| `WS-POL-003-03B` | Consume 12I to make immutable compilation parent/result persistence usable; no policy projection or setup-service cutover. | 03A + AUTH-12I |
| `WS-POL-003-04A` | Hidden one-attempt setup orchestrator over the complete result, with all three legacy inference methods denied/unreachable in the candidate call graph. | 03B |
| `WS-AUTH-001-12B2` | Activate only setup-ledger mutation and its fixed-service adapter for the reviewed unified setup-service manifest. | 04A |
| `WS-POL-003-04B` | Live one-call setup cutover; persist complete result, sufficiency, and artifact-policy projections; remove every legacy inference call from live reachability. | 04A + AUTH-12B2 |
| `WS-POL-003-05A` | Hidden approval/effective/pre-submit projection behavior over the complete immutable result. | 04B |
| `WS-AUTH-001-12F4` | Activate exact PM approval authority and PREP composition for the hidden 05A manifest. | 05A |
| `WS-POL-003-05B` | Live PM approval and trusted effective/pre-submit projection cutover. | 05A + AUTH-12F4 |
| `WS-POL-003-06A` | Hidden deterministic post-submit projection and separate approval behavior; zero model calls. | 05B |
| `WS-AUTH-001-12G` | Activate exact fixed-service projection plus PM approval/correction authority for the hidden 06A manifest. | 06A |
| `WS-POL-003-06B` | Live deterministic post-submit projection/approval cutover with zero additional inference. | 06A + AUTH-12G |
| `WS-POL-003-07` | One typed checker-service port with one complete pre and one complete post command. | 06B + merged ART-04B1-04B3 execution/evidence contract |
| `WS-AUTH-001-12H` | Activate guide publication only over the complete approved current-generation unified chain and CON clean cut. | 07 + corrected 12B2 + owning CON clean cut |
| `WS-POL-003-08` | Visibility, generation-safe correction, physical legacy inference/parallel-route cleanup, and activation compatibility proof. | 07 + AUTH-12H + ART-05B |

## Parallel ART admission path

The ART admission sequence remains independent and may proceed concurrently:

```text
merged ART-04B3
-> merged XINT-06A
-> ART-04C1 -> ART-04C2
-> XINT-05A -> ART-05A -> XINT-05B -> ART-05B
```

Once a unified guide generation is active, ART admission must bind only that
generation's approved compilation-derived policy hashes; stale pre-unified or
mixed-generation chains deny through the existing locked-lineage checks.

## Post-submit execution gate

ART-06A/06B may build hidden materialization/output behavior after ART-05B,
but XINT-06B must not activate it until POL-06B and POL-07 have merged. AUTH-14
then owns only bounded live authorization/visibility over the sole
admission-backed Submission and checker paths.
