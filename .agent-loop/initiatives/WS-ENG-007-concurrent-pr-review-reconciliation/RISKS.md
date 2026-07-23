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
| Planning intake cannot enter signed history | Critical | Filter only validated directory entries from the GitHub recursive tree map, preserve every validated supported non-tree leaf identity, reject unsupported entries, and recover exact PR `#187` plus 00R1 through a consumed two-merge certificate. |
| Recovery becomes a reusable bypass | Critical | Bind schema-v1 recovery to PR #187 merge `8928ba80eeaf31e609dbdeda7d2cc22e9ea482c8` and the exact 00R1 activation identity; require the ordered two-merge plan, successful checks, full consumption, and no persisted exemption. |
| Legitimate check reruns block signed memory | Critical | Validate every same-name candidate, order completed trusted invocations by parsed start instant and positive check-run ID, then require the unique latest candidate to succeed. |
| A stale success hides a later failure | Critical | Latest validated run wins; an in-progress, failed, cancelled, foreign-app, malformed, or timestamp-ambiguous latest run fails closed. |
| Three-merge repair becomes general authority | Critical | Schema v3 permits at most two recovered merges and production names only PR #187, PR #188, and 00R2; require exact first-parent adjacency, unique identities, full consumption before signing, and no serialization. |
