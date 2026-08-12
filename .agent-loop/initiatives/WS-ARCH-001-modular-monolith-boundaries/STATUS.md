# Status: WS-ARCH-001 Modular Monolith Boundaries

- Initiative state: active; boundary foundation complete
- Runtime behavior changed: no
- Canonical target: nine business modules and three supporting modules
- Recovery model: freeze exact debt, prohibit growth, repair touched
  capabilities incrementally
- Existing dependency: WS-AUTH-003 boundary foundation merged
- Reconciled merged overlap: POL-03A PR #307 is the first public AUTH-capability
  proof and owns migration `0062_guide_compilation`
- Completed foundation: WS-ARCH-001-01 installs the canonical registry, exact
  general debt ledger, AUTH-ledger composition, protected-base validator,
  public-API checks, behavior-ownership record, and hosted CI enforcement.
- Approved split: WS-ARCH-001-02 is divided into 02A-02I across TASKS,
  PROJECTS, CHECKERS, ART, AUTH, composition, and the final API clean cut.
- Completed capability foundations: TASKS `02A` merged through PR #314 and
  PROJECTS `02B` merged through PR #315.
- WS-ARCH-001-02C merged through PR #320. It exposes CHECKER-owned
  effective-plan and bounded execution-result contracts without activating the
  contributor preparation route.
- WS-ARCH-001-02D is complete. It moves the hidden preparation
  route to delivery composition, exposes the bounded ART request/result/command
  API, consumes TASK/PROJECT/CHECKER public capabilities, keeps AUTH handles
  opaque, and preserves deny-only availability.
- WS-ARCH-001-02E is complete. ART exposes one deny-by-default
  ready-admission consumption port, validates exact TASK and ART lineage,
  serializes binding identity, persists the consumed Submission id/version,
  creates one provider-neutral generic binding, and proves replay, concurrency,
  rollback, and stable conflicts without activating a route or AUTH action.
- WS-ARCH-001-02F is complete. TASK owns the immutable
  admission-backed Submission command and the adapter owns one hidden root
  transaction; production remains deny-only and route-unreachable.
- Complete on merge: WS-ARCH-001-02G AUTH contributor-preparation
  activation. Open pull requests show transient ownership.
- Complete on merge: WS-ARCH-001-02H activates exact human Submission
  consumption and fixed ART binding authority against the hidden atomic
  transaction. The public route remains unchanged.
- Repository housekeeping after PR #315 found no competing clean-up
  initiative: WS-ARCH-001 remains the general boundary owner, WS-AUTH-003 owns
  AUTH-specific debt, and test-structure repairs remain incremental with the
  capability being touched.
