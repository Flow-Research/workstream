# Intent: WS-ARCH-001 Modular Monolith Boundaries

## Human goal

Make the existing Workstream backend a strict modular monolith without pausing
v0.1 delivery or rewriting the repository at once. New work may span several
modules, but every fact and mutation must be implemented inside its owning
module and every cross-module call must use a typed public API.

## Success state

- The nine business modules and three supporting modules have one canonical
  ownership map.
- Cross-module runtime imports use only the target module's `api` package.
- Concrete implementations meet only in the application composition root or
  the exact same-owner `backend/app/adapters/<owner>/__init__.py` composition
  root; nested adapters and cross-owner private imports remain prohibited.
- Existing private-import debt is frozen as exact source-to-target edges.
- Every feature chunk repairs the capabilities and debt edges it touches.
- No debt count grows, and final closure requires an empty private-import
  ledger.
- Product delivery has one explicit upstream milestone before live REV work:
  an admission-backed immutable Submission, bound to the exact verified ZIP
  and current approved guide/policy generation, produces one durable current
  post-submit checker result whose routing recommendation is `allow_review`.
- That milestone uses only owner public APIs across PROJECTS, TASKS, ART,
  CHECKERS, and AUTH. It does not rely on the legacy Submission route or grant
  REV a private-import exception.
- CON is a mandatory earlier participant: it validates the one
  ContributionPolicyVersion bound at guide activation. TASK locks that version
  before claimability; assignment copies it, Submission stamps the attempt
  value, and ReviewLease copies that immutable stamp without claim-time
  selection. CON later stages ContributionRecord/CompensationAward
  consequences atomically with every final review decision. Only accept adds
  FinalAcceptance and the submitter record.

## Non-goals

- No repository-wide move or package rename in one PR.
- No new distributed service, generic orchestrator module, service locator, or
  compatibility facade.
- No change to product ownership, authorization semantics, or lifecycle state
  merely to make imports pass.
- No empty public API packages before a real consumer needs them.

## Human decisions already made

- The existing modules are sufficient.
- A coordinating agent may implement code across modules, but code is placed
  only in the module that owns the behavior.
- Boundary debt is removed incrementally alongside delivery chunks.
- Canonical `allow_review` gates live REV admission/claim/processing, not
  independent REV schema or packet foundations.
- CON validates one policy version at guide activation and is mandatory again
  in every final Review commit. TASK and REV inherit the immutable version;
  neither claim performs CON policy selection.

## PLAN3 intent

Turn PLAN2's correct ContributionPolicy lifecycle into an executable,
non-circular sequence. Success means AUTH registers before behavior, each CON
behavior activates only after hidden proof, CON exposes validation without
writing foreign aggregates, PROJECTS binds the guide, TASKS carries immutable
attempt lineage, and the retired guide-bound economic path is removed without
compatibility or invented historical migration work.

PLAN3 changes planning only. It does not register an action, activate a route,
write policy behavior, mutate schema, or start a runtime child.

CP04 planning succeeds when editable draft behavior and irreversible
publication are separately reviewable, every mutation is replay-safe and
transaction-bound, publication authority is derived only from locked
server-owned graph facts, and production remains deny-default until CP05.
It does not authorize a route, guide/task/review write, contribution/award
creation, fulfillment, or compatibility path.
