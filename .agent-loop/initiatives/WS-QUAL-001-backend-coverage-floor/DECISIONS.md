# Decisions: WS-QUAL-001 Behavior And Mutation Assurance

## D1: Preserve the global 78-percent floor

The user confirmed that 78 percent is the permitted complete-backend baseline.
Named new or materially changed subsystem floors remain at 90 percent.

## D2: Supersede the global-90 floor switch

`WS-QUAL-001-04R` is superseded before implementation. Main already exceeds 90
percent, and raising the floor would not prove assertion sensitivity.

## D3: Make observable behavior the quality claim

Coverage remains a backstop. Behavior evidence identifies the production
target, owning tests, and observable result, denial, persisted fact, mapped
error, idempotent replay, or recovery outcome.

## D4: Pilot mutation testing before blocking

One bounded non-blocking-score pilot must measure compatibility, result noise,
and runtime. Infrastructure failure and invalid evidence still fail the pilot.

## D5: Prefer mutmut provisionally

Current official documentation and project metadata make `mutmut` the leading
candidate for pytest-aware, changed-scope execution on Python 3.11/3.12. The
pilot may reject it if exact pinning, isolation, determinism, or runtime fails.

## D6: Do not use a global mutation percentage

Enforcement is based on complete outcomes for eligible changed targets. A
surviving meaningful mutant is missing behavior proof. Typed equivalent or
non-behavioral classifications may be designed only from pilot evidence.

## D7: Include test-only behavior claims

A test-only PR that claims behavioral or coverage improvement must name bounded
production targets and owning tests; otherwise it cannot bypass mutation
assurance merely because application files did not change.

## D8: Keep mutation work off the Backend critical path

The pilot runs independently with hard command/job limits. A blocking rollout
must preserve the existing complete Backend authority and practical PR latency.

## D9: Require a second human checkpoint

PLAN3 authorizes planning only. Pilot implementation requires its own explicit
instruction, and blocking rollout requires another explicit human decision
after exact hosted pilot evidence is reviewed.
