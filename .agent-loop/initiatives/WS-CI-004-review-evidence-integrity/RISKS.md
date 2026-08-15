# Risks: WS-CI-004 Review Evidence Integrity

| Risk | Severity | Mitigation | State |
|---|---:|---|---|
| A pass refers to an older head | Critical | Record start/end head and invalidate on relevant delta | Planned |
| Evidence prose claims a failed or unexecuted command passed | Critical | Separate executed evidence from inspected claims and require provenance | Planned |
| Review misses unchanged consumers or debt ledgers | Critical | Require impact-cone, ownership, public-boundary, and ledger tracing | Planned |
| Prior finding silently disappears | Critical | Stable finding ID and final-head replay disposition | Planned |
| Different reviewers and CI validate different heads | Critical | Final-head convergence barrier before readiness | Planned |
| New protocol recreates signed-state circularity | Critical | Review evidence never authorizes contribution, implementation, or merge | Planned |
| Committed evidence changes its own subject | High | Keep internal receipts outside Git; GitHub owns durable evidence | Planned |
| Untrusted PR/branch identity escapes or collides in receipt custody | High | Typed canonical keys, NFC plus injective base64url encoding, separator/symlink rejection, and resolved-root containment | Planned |
| Dirty local changes share a clean commit target | High | Permit final verdicts only from a clean worktree checked at start and end | Planned |
| Universal reruns make contribution slow | High | Risk-routed affected-review invalidation only | Planned |
| Shared protocol becomes another giant parser | High | Small orthogonal tool, strict line budget, separate concerns and tests | Planned |
| AI reviewers converge on the same blind spot | High | Independent specialties, adversarial replay, external review, human merge | Planned |
| Review records become an active queue | Medium | Historical evidence only; GitHub PRs remain transient-work view | Planned |
