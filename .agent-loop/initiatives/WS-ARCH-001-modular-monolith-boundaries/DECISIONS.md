# Decisions: WS-ARCH-001 Modular Monolith Boundaries

## D1: Keep twelve existing modules

Keep nine business modules (`actors`, `authorization`, `projects`, `tasks`,
`artifacts`, `checkers`, `reviews`, `contributions`, `compensation`) and three
supporting modules (`audit`, `outbox`, `api_controls`). Do not add a generic
workflow or orchestrator domain module.

## D2: Public API is the only runtime import surface

Outside a module, the only permitted runtime import prefix is
`app.modules.<target>.api`. Public APIs are capability-oriented and introduced
only with a real consumer.

## D3: Coordination does not transfer ownership

One contributor may edit several modules in one bounded cross-module chunk.
The worktree or coordinating initiative does not determine domain ownership.

## D4: Incremental strangler recovery

Freeze exact existing debt, reject new edges, and remove touched edges with
each delivery chunk. Do not perform a repository-wide reorganization.

## D5: Submission belongs to TASKS

TASKS owns immutable Submission creation and its predecessor chain. ART owns
ready-admission consumption and exact artifact binding through public ports.
The composed TASK application command coordinates the final transaction.

## D6: Existing specialist initiatives remain authoritative

`WS-AUTH-003` owns AUTH internals and its private-import ledger.
`WS-QUAL-002` owns behavior/test ownership. WS-ARCH-001 owns the canonical
module map, general cross-module dependency rule, and coordinated debt-removal
sequence.

AUTH edges are never copied into a WS-ARCH ledger. The general validator loads
WS-AUTH-003's canonical ledger through its existing parser and fails if the
AUTH-specific and general views diverge.

## D7: Application wiring is classified, not exempted

API delivery, adapters, durable workers, and legacy shared interfaces are all
scanned. Their current private product imports are protected debt and may not
grow. `backend/app/interfaces/**` is not a permanent public contract surface.
Database metadata discovery is a distinct infrastructure concern: only the
exact registered discovery path may import module model declarations, and that
exception grants no runtime command, repository, service, or authority access.

## D8: Submission preparation requires PROJECT and CHECKER capabilities

TASKS owns task, assignment, predecessor, and Submission lifecycle facts. It
does not own locked Project Guide/policy persistence or effective checker-plan
compilation. WS-ARCH-001-02 therefore includes explicit PROJECTS and CHECKERS
prerequisite contracts rather than preserving those private imports behind a
TASK facade.

## D9: Activation follows hidden public-boundary proof

Typed owner APIs merge first while operations remain hidden or deny-only.
Contributor preparation activates only after its complete hidden path consumes
public owner capabilities. Binding/human consumption authority activates only
after the hidden TASK/ART transaction is proven. Public reachability changes
last, in the same clean cut that removes legacy input and precheck behavior.

## D10: Composition owns wiring, not lifecycle truth

The application composition root opens the transaction and constructs
transaction-bound port implementations. The TASK-owned application command
sequences Submission creation through injected AUTH and ART ports. AUTH, ART,
PROJECTS, CHECKERS, and TASKS retain their own locks and invariants; the
composition layer contains no product-state branching or authorization policy.

## D11: Public clean cut waits for all submission contexts

Initial preparation may become live behind its hidden surface after 02G, and
the hidden consumption transaction may receive exact authority after 02H. The
public Submission route remains on its guarded legacy path until initial,
checker-remediation, and reviewer-requested revision contexts all use the same
admission-backed contract and post-submit checker/REV handoffs are live. 02I is
therefore deferred across the required WS-ARCH-001-03/04/05 splits; it cannot
strand `needs_revision` contributors or create Submissions that cannot reach
visible checker and reviewer admission facts.

## D12: Canonical allow-review is the upstream completion milestone

The next cross-module milestone is not REV lifecycle implementation and is not
the public 02I cutover. It is one hidden but production-authorized,
admission-backed Submission reaching a durable current post-submit checker
result of `allow_review` through owner public APIs. Existing legacy pre-review
behavior is regression evidence only and cannot satisfy this milestone.

## D13: Separate readiness, review admission, and public release

PROJECT/POL readiness and TASK assignment authority complete first. ART and
CHECKERS then materialize, execute, persist, and expose the exact current
post-submit result. Only after that merged manifest may REV activate admission
for the Submission. Independent REV schema/packet foundations may proceed
earlier. CON participates before assignment, before review claim, and in every
final decision; it is not downstream-only. The admission-only public API clean
cut remains later still, after initial, checker-remediation, and
reviewer-requested revision contexts all use the same path.

## D14: ContributionPolicy is the sole award-governing policy

There is no separate CompensationPolicy or payment policy in the canonical
model. CON owns `ContributionPolicy` and immutable
`ContributionPolicyVersion`; `CompensationAward` is an evaluation result, not
a policy. PLAN2 uses only the exact frozen submitter and reviewer
ContributionPolicyVersion references. Existing runtime and historical
`payment_policy`/`locked_payment_policy_version` vocabulary is legacy debt and
must be removed by owning clean-cut chunks before public release; it is not
authority and receives no compatibility alias or fallback.
