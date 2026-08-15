# Status: WS-ARCH-001 Modular Monolith Boundaries

- Initiative state: active; boundary foundation complete
- Runtime behavior changed: hidden CON adapter-binding behavior only; no route or action activation
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
- WS-ARCH-001-PLAN2 is planned and lands as the current-main planning
  reconciliation. Planned non-executable skeletons WS-ARCH-001-03A,
  WS-ARCH-001-03B, WS-ARCH-001-03C, WS-ARCH-001-04A, WS-ARCH-001-04B,
  WS-ARCH-001-04C, WS-ARCH-001-04D, WS-ARCH-001-04E, and WS-ARCH-001-04F
  record its dependency order. The next product
  milestone is one admission-backed immutable Submission reaching a durable
  current `allow_review` result through PROJECTS/TASKS/ART/CHECKERS/AUTH public
  APIs. REV admission follows that manifest; the public 02I cutover remains
  later.
- Repository housekeeping after PR #315 found no competing clean-up
  initiative: WS-ARCH-001 remains the general boundary owner, WS-AUTH-003 owns
  AUTH-specific debt, and test-structure repairs remain incremental with the
  capability being touched.
- PLAN3 corrects PLAN2's first implementation dependency. CON-05A is not a
  valid direct start: missing AUTH registration/activation and hidden CON
  behavior must precede owner-separated guide/task lineage. CP01 is the
  non-executable split parent; CP01A is complete on merge with its four actions
  registered/unavailable, CP01B is complete on merge with five policy actions
  registered/unavailable. CP02 is complete on merge with hidden CON behavior
  while its AUTH actions remain unavailable; CP03 is split with executable
  CP03A/CP03B contracts complete on merge, while CP04-CP09 remain
  non-executable skeletons.
- [WS-ARCH-001-PLAN4](chunks/WS-ARCH-001-PLAN4-incremental-debt-retirement.md) is planned on merge
  and changes no runtime. It makes the existing incremental strangler
  operational: unrelated frozen debt cannot block delivery, new debt is
  prohibited, directly touched debt must shrink, and unsafe adjacent debt is
  recorded for a later owner-sized closure without widening the feature PR.
  Current baselines are 115 general protected private edges, 99 AUTH-ledger
  edges reported separately, and 89 AUTH structural findings. These measures
  overlap and are never summed into one repository total.

## Planned PLAN3 children

- WS-ARCH-001-PLAN3 is planned; its planning merge changed no runtime behavior.
- WS-ARCH-001-CP01 is a planned split and non-executable. Current-main discovery proved
  adapter binding and ContributionPolicy are distinct resource/action families.
- WS-ARCH-001-CP01A is complete on merge: exact adapter-binding identifiers,
  mappings, typed facts, and digests are registered while unavailable.
- WS-ARCH-001-CP01B is complete on merge: exact unavailable
  ContributionPolicy registration.
- WS-ARCH-001-CP01C is complete on merge: unavailable adapter-binding facts
  match exact binding identity and lifecycle generation without a unit alias.
- WS-ARCH-001-CP02 is complete on merge: hidden, route-unreachable
  adapter-binding behavior while its AUTH actions remain unavailable.
- WS-ARCH-001-CP03 is a planned split/non-executable parent. CP03A's executable
  contract specifies the closed compensation-adapter target identity and
  PROJECTS/ACTORS owner eligibility while actions remain unavailable. CP03B's
  executable contract specifies and requires proof of exact Finance Authority
  activation without adding a route or adjacent compensation authority.
- WS-ARCH-001-CP03A is planned with an executable implementation contract.
- WS-ARCH-001-CP03B is planned with an executable implementation contract after
  merged CP03A.
- WS-ARCH-001-CP04 is proposed: hidden ContributionPolicy behavior.
- WS-ARCH-001-CP05 is proposed: exact ContributionPolicy activation.
- WS-ARCH-001-CP06 is proposed: CON policy-validation port.
- WS-ARCH-001-CP07 is proposed: PROJECT guide binding.
- WS-ARCH-001-CP08 is proposed: TASK/Assignment/Submission lineage persistence
  and public facts only.
- WS-ARCH-001-CP09 is proposed: clean legacy economic-path removal after
  WS-ARCH-001-03C activates the replacement.

## Planned PLAN2 children

- WS-ARCH-001-03A is planned.
- WS-ARCH-001-03B is planned.
- WS-ARCH-001-03C is planned.
- WS-ARCH-001-04A is planned.
- WS-ARCH-001-04B is planned.
- WS-ARCH-001-04C is planned.
- WS-ARCH-001-04D is planned.
- WS-ARCH-001-04E is planned.
- WS-ARCH-001-04F is planned.
