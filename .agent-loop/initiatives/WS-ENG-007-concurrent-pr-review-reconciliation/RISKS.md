# Risks: WS-ENG-007 - Concurrent PR Review Reconciliation

| Risk | Severity | Mitigation |
|---|---:|---|
| A semantic dependency is missed despite disjoint paths | Critical | Closed boundary manifests; unknown impact invalidates all tracks. |
| A changed effective PR patch retains approval | Critical | Bind base/head trees and canonical patch manifest; recompute on latest main. |
| Upstream finding is falsely marked resolved | High | Require a deterministic target predicate; `false` reruns the owning track and `unknown` invalidates all tracks. |
| GitHub merge queue bypasses required checks | Critical | Add and test `merge_group` parity before administrative enablement. |
| Review preservation becomes human-approval automation | Critical | Preserve only internal agent tracks; GitHub/human approval remains external and mandatory. |
| Base objects disappear after branch cleanup | High | Store tree/blob manifests and test pruned-object failure/reconstruction boundaries. |
| Conservative rules still cause excess review | Medium | Measure invalidation reasons; refine only with reviewed deterministic rules. |
| Concurrent queue entries interact | High | Validate each exact merge-group SHA and invalidate on queue recomputation. |
