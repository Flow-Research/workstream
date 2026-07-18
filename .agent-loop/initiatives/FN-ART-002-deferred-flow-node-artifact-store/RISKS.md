# Risks: FN-ART-002

| Risk | Severity | Mitigation |
|---|---:|---|
| Operating cost exceeds value | High | Require measured v0.1 need before activation. |
| Flow Node leaks product authority | Critical | Byte-only port; Workstream owns all semantics. |
| CID/DAG details pollute generic contract | High | Keep details bounded and provider-specific. |
| Human tokens reach provider | Critical | Fixed service principal; never forward bearer tokens. |
| Dual runtime diverges | Critical | Maintenance cutover; no fallback or dual write. |
| Migrated bytes differ | Critical | Complete read/hash/size verification per object. |
| Provider outage blames contributor | Critical | Preserve artifact infrastructure failure semantics. |
| Old exploratory evidence treated as approval | High | New exact-head reviews for every future chunk. |
