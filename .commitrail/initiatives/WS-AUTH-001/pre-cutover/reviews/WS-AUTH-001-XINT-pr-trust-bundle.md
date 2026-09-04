# WS-AUTH-001-XINT PR Trust Bundle

## Goal

Reconcile the remaining AUTH plan with merged PR #139 before AUTH-09A or any
affected ART, REV, or CON authorization work continues.

## What Changed

- Adopted merged XINT role, fixed-service, activation-custody, prepared-mutation,
  and feature-ownership boundaries throughout the AUTH plan and public docs.
- Kept AUTH-09A through 09E uninterrupted, then placed availability-neutral ART
  and REV custody transfers and PREP before sensitive product cutovers.
- Mapped all 25 ART and 19 REV actions to exact future AUTH custodians without
  changing runtime; retry remains independently proven under the canonical
  Operator owner.
- Made proposed REV and review-evidence registrations feature-manifest gates
  with order-independent deltas and safe downgrade requirements.
- Repaired AUTH-10 through AUTH-16 for independent project roles, exact-role
  invalidation, dormant adjudicator lifecycle, action/migration custody, and
  final conformance proof.
- Addressed external review with exact service-matrix least privilege, complete
  PREP actor/request binding, non-reservation of blocked migration numbers, and
  normative migration `0024` refusal behavior.
- Preserved the exact migration packaging, wheel replay, event-loop cleanup,
  and exception-precedence guarantees that PR #132 must retain when converged.

## Scope Boundary

This PR changes planning, loop memory, and authorization documentation only. It
does not change backend runtime, tests, schemas, migrations, catalogue values,
action availability, service provisioning, or feature behavior.

## Evidence

- Stale wording and authorization-doc checks passed.
- Markdown links and diff integrity passed.
- All 80 agent-gate tests passed.
- Direct typed comparison proved the exact 25 ART / 19 REV custody map and eight
  canonical ART owner groups.
- Required senior, QA, security, product, architecture, CI, docs, and reuse
  tracks passed exact reviewed state SHA `bac3073` after all findings were fixed.

Coverage is not recalculated for a documentation-only change. No threshold or
exclusion changed; future activation contracts require at least 90 percent for
every materially changed subsystem and preservation of the global 78 percent
floor.

## Remaining Risks

- PR #132 is still open and conflicting. It must converge only after this plan
  merges, preserve its reviewed runtime/migration fixes, and pass fresh exact-head
  internal and external review.
- Feature activation contracts remain intentionally unmaterialized until their
  immutable feature manifests and real behavior tests exist.
- PREP remains proposed runtime work; no sensitive consumer may start until its
  lock-order and crossed-concurrency proof merge.

## Human Review Focus

Review the AUTH-09A through 09E sequence, canonical custody mappings, PREP lock
order, independent grant/invalidation semantics, PR #132 preservation list, and
the absence of runtime activation.

## Human Merge Ownership

Only the human may approve and merge this PR. Internal review, GitHub checks,
and CodeRabbit do not authorize merge or start AUTH-09A.
