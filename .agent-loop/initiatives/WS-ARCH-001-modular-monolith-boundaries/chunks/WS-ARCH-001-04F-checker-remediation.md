# Chunk Contract: WS-ARCH-001-04F Checker Remediation Handoff

Status: non-executable planning skeleton after 04E. Risk: L1. Outcome: final
current checker outcomes that do not allow review create one bounded,
contributor-readable remediation lineage without entering REV.

Owner: CHECKERS for failure/remediation facts and TASKS for their bounded
projection through public APIs. This chunk must reuse the single POL-003
checker-service port and the immutable current CheckerRun. It must not create
Review, ReviewFinding, RevisionContextPreparation, a second checker command,
or a caller-selected checker route.

Acceptance: a final needs-remediation result binds the exact Submission,
assignment, verified artifact, approved generation, locked post-submit policy,
run and blocking findings; replay and concurrency create one projection;
superseded or stale runs cannot remain current; contributor visibility is
bounded to their own Submission. This chunk is required before public 02I but
does not block REV beginning from the separate canonical `allow_review`
manifest.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head, authorization gates and
reviewers.

## Merge state

- Outcome on merge: `planned`
