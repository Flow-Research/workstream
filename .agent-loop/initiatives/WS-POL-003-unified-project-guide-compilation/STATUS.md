# Status: WS-POL-003 - Unified Project Guide Compilation

Status: planning candidate under review; no implementation is active.

Baseline: `origin/main` `e2057d0f39b47cc84fb733f4381ee674028a9a47`.

## Dependency gates

| Dependency | Required before | Current status at baseline |
|---|---|---|
| AUTH-12F | service submission-policy projection writes | Proposed after merged 12E |
| AUTH-12G | service post-submit projection writes | Proposed after 12F |
| AUTH-12B2 | unified Celery call-graph cutover | Proposed after 12F/12G |
| AUTH-12H | terminal activation integration | Proposed after 12B2 |
| ART-04A4 | standalone precheck route clean cut | Merged through PR #273 |
| ART-04B1 complete pre-submit catalogue/effective-plan contract | platform plus closed project-rule projection consumed read-only | Proposed after merged ART-04A4 |
| ART-04B2/04B3 | final execution compatibility proof | Proposed after ART-04B1 |
| CHECKER/POL post-submit catalogue | durable defaults plus registered selectable project rules | Consumed read-only/hardened by POL work |
| CHECKER typed evaluation port | one pre call in scratch and one post call after verified storage/binding | Owned by WS-POL-003-07 |
| XINT/AUTH compilation activation | exact PM request and fixed-service execute actions for immutable compilation custody | Not yet planned/merged |

## Chunk state

All WS-POL-003 chunks are proposed and inactive. Planning does not authorize
implementation. The first implementation chunk requires explicit human start
after this plan and its applicable dependencies are merged.
