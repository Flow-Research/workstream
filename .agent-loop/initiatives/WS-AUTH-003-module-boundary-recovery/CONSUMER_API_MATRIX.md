# AUTH Consumer/API Matrix

Checkpoint 1 replaces every `exact types pending` entry before behavior moves.

| Consumer | Current need | Public API family | Forbidden exposure |
|---|---|---|---|
| Actors | actor context/lifecycle authority | exact types pending: actor commands, facts, decisions, port | AUTH models/repositories |
| Audit | bounded action/permission identifiers | action IDs and immutable evidence facts | evaluator/evidence-writer implementation |
| ART | prepared human/fixed-service boundaries | exact types pending: prepared port, opaque handle, ART facts | kernel, capability registry, persistence |
| Projects/POL | create, guide, policy, read, setup authority | exact types pending: prepared/read ports and project facts | repositories/kernel/runtime internals |
| Tasks | request-scoped and prepared submission authority | exact types pending: read/prepared port and task facts | session/repository/model |
| REV | future review authority | no activation; typed API only when owned | ART/AUTH internals |
| CON | future contribution authority | no activation; typed API only when owned | REV/AUTH internals |
| HTTP dependencies | request-scoped AUTH facade | public port and stable errors | product implementation wiring |

`authorization/composition.py` may assemble AUTH-owned services using injected
ports. It may not import concrete ART, REV, CON, project, task, or checker
implementations. The application composition root performs concrete wiring.
