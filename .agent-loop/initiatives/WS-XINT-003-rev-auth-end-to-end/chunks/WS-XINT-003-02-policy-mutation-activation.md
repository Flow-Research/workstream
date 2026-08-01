# Chunk Contract: WS-XINT-003-02 — Policy Persistence And Mutation Split Record

## Status

Non-executable parent. Current-main discovery at `ad8da7e5` split implementation
into 02A persistence adoption and 02B prepared mutation activation.

## Goal

Deliver one immutable/versioned REV policy persistence path and one
AUTH-prepared covered-project mutation surface without a dual-writer interval.

## Risk class

L1 policy and authorization mutation.

## Child sequence

1. `WS-XINT-003-02A`: adopt immutable persistence and remove unused legacy
   writer/construction callables; keep both actions planned and add no route.
2. `WS-XINT-003-02B`: add the sole mutation service/routes, AUTH PREP
   consumption, append-only repository calls, atomic decision evidence, and the
   exact two action activations.

## Not allowed

Queue, lease, Review, finding, revision execution, artifact, CON, adjudication,
reputation, frontend, duplicate policy tables, or legacy writer compatibility.

## Acceptance criteria

- Only a covered Project Manager with the exact project grant may update the
  review or revision policy for that project and guide lineage.
- The actions remain distinct: `project.review_policy.update` and
  `project.revision_policy.update`.
- Final PREP consumption binds actor/link/grant, project, guide/version,
  existing/reserved policy identity, operation, request digest, idempotency,
  session, transaction, and server-validated policy facts.
- Cross-project, stale guide, wrong policy/action, revoked, replayed, copied, or
  concurrent changed requests deny with no policy/audit partial state.
- The previous embedded or duplicate writer path is removed without backward
  compatibility.
- No review lifecycle action is activated.

## Shared invariants

- Existing ReviewPolicy and RevisionPolicy tables remain the only records.
- REV owns policy meaning/history; AUTH owns authority/PREP/evidence.
- ART, Task, Submission, Review execution, revision execution, and CON are not
  modified by either child.
- PR #195 is discovery/preservation input only. No historical migration SHA,
  stale base, old writer, merge intent, or signed-start evidence is adopted.

## Stop condition

Do not implement this parent. Implement one child per PR and stop after each.
