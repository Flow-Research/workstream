# Status: WS-POL-003 - Unified Project Guide Compilation

Status: planning candidate under review; no implementation is active.

Baseline: `origin/main` `bb77ff4a0ab61120b94d6d4763934b444c39207d`.

## Dependency gates

| Dependency | Required before | Current status at baseline |
|---|---|---|
| AUTH-12F | service submission-policy projection writes | Proposed after merged 12E |
| AUTH-12G | service post-submit projection writes | Proposed after 12F |
| AUTH-12B2 | unified Celery call-graph cutover | Proposed after 12F/12G |
| AUTH-12H | terminal activation integration | Proposed after 12B2 |
| ART PLAN5 / 04A4 | 04A4 superseded; standalone precheck clean cut moved to ART-05B | PLAN5 merged through PR #273 |
| ART-04B1 complete pre-submit catalogue/effective-plan contract | exact immutable platform plus closed project-rule projection consumed read-only | Merged through PR #276 |
| ART-04B2/04B3 | sealed execution and immutable evidence writer used behind the pre facade | Proposed after merged ART-04B1 |
| ART-05B | standalone precheck and legacy Submission path clean cut | Proposed after ART/XINT admission sequence |
| CHECKER/POL post-submit catalogue | durable defaults plus registered selectable project rules | Consumed read-only/hardened by POL work |
| CHECKER typed evaluation port | one pre call in scratch and one post call after verified storage/binding | Owned by WS-POL-003-07 |
| XINT/AUTH compilation activation | exact PM request and fixed-service execute actions for immutable compilation custody | Not yet planned/merged |

## Chunk state

All WS-POL-003 chunks are proposed and inactive. Planning does not authorize
implementation. The first implementation chunk requires explicit human start
after this plan and its applicable dependencies are merged.
