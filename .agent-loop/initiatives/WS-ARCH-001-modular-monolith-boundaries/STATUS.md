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
- Planning in review: WS-ARCH-001-02 is split into 02A-02I across TASKS,
  PROJECTS, CHECKERS, ART, AUTH, composition, and the final API clean cut.
- Next implementation boundary after plan approval: WS-ARCH-001-02A only.
