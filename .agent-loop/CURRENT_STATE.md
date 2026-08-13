# Current Engineering State

This page is the entry point for current engineering work. It separates durable
merged state from transient branch and pull-request activity so historical
plans and reviews cannot be mistaken for work that is still active.

## Sources Of Truth

Use these sources in order:

1. [`docs/roadmap_status.md`](../docs/roadmap_status.md) states the capabilities
   implemented on `main` and the remaining v0.1 milestones.
2. [Open pull requests](https://github.com/Flow-Research/workstream/pulls)
   show work currently under review. An open PR is not implemented behavior.
3. The initiative table below records durable disposition and the next usable
   planning boundary.
4. An initiative's `CHUNK_MAP.md` and chunk contracts explain dependencies and
   scope. They must be checked against current `main` before implementation.
5. Review logs and files under `reviews/` are historical evidence for the exact
   change they reviewed. They never describe current repository state by
   themselves.

Git history is authoritative when a static record conflicts with a merged
commit. GitHub permissions and branch protection govern contribution
authority; these records do not grant or withhold it.

## Initiative Ledger

| Initiative | Durable state on `main` | Remaining boundary |
|---|---|---|
| [WS-ARCH-001](initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md) | Complete through `WS-ARCH-001-02H`, including hidden preparation and atomic consumption/binding activation | Planned WS-ARCH-001-PLAN2 skeletons WS-ARCH-001-03A/03B/03C and WS-ARCH-001-04A/04B/04C/04D/04E/04F define the order through durable current `allow_review`; REV admission follows and `02I` remains later |
| [WS-ART-001](initiatives/WS-ART-001-immutable-artifact-storage/STATUS.md) | Active delivery initiative; verified ready-admission publication, hidden preparation, consumption and binding are merged through ARCH-02H | Implement exact post-submit materialization only after the unified guide/checker and PLAN2 public contracts are executable; live cutover remains later |
| [WS-AUTH-001](initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md) | Active delivery initiative; project-policy authority and unified compilation authorization are merged through `12I` | POL-03B consumes 12I next; remaining AUTH activation chunks wait for their exact hidden owner behavior |
| [WS-CON-001](initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md) | Active delivery initiative; policy persistence and shared lifecycle audit are merged | Complete hidden services, contribution records, conditional awards, fulfillment, and reconciliation after named AUTH and REV gates |
| [WS-AUTH-003](initiatives/WS-AUTH-003-module-boundary-recovery/STATUS.md) | AUTH boundary foundation and first public-capability proof through POL-03A are merged | Repair each touched AUTH capability through `authorization.api` and shrink the canonical AUTH ledger |
| [WS-POL-003](initiatives/WS-POL-003-unified-project-guide-compilation/STATUS.md) | Active delivery initiative; hidden compilation custody and AUTH-12I activation are merged | Implement POL-03B authorized compilation persistence, then continue the reviewed dependency order |
| [WS-REV-001](initiatives/WS-REV-001-review-revision-lifecycle/STATUS.md) | Foundations through queue admission and reviewer-lease persistence are merged through `03A2`; they are not proof of a live canonical entry path | Begin live packet/review lifecycle work only after the WS-ARCH-001-04E admission-backed `allow_review` manifest and its named ART/AUTH gates |
| [WS-QUAL-002](initiatives/WS-QUAL-002-behavior-ownership-catalogue/STATUS.md) | Catalogue foundation `01` and local context evidence `02` are merged through PRs #297 and #303 | Populate subsystem ownership through `03A`-`03D` before completeness or changed-line-aware mutation work |
| [WS-XINT-002](initiatives/WS-XINT-002-art-auth-end-to-end/STATUS.md) | Guide and pre-submit materialization activation is merged | Continue only remaining ART and AUTH activation edges required by the artifact delivery path |
| [WS-XINT-003](initiatives/WS-XINT-003-rev-auth-end-to-end/STATUS.md) | REV authorization readiness through `02D` is merged | Later activation waves resume only against exact merged REV behavior |
| [WS-POL-002](initiatives/WS-POL-002-post-submit-checker-foundation/STATUS.md) | Earlier post-submit foundations are merged; future guide inference is superseded by WS-POL-003 | Reframe remaining executor work against WS-POL-003; do not revive the old inference path |
| [WS-POL-001](initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md) | Foundation initiative complete | Follow-up behavior belongs to current ART, POL, REV, or CON initiatives |
| [WS-QUAL-001](initiatives/WS-QUAL-001-backend-coverage-floor/STATUS.md) | Coverage closure complete; blocking mutation rollout retired | Preserve global 78 percent and protected-subsystem 90 percent floors; mutation needs a fresh changed-line-aware plan |
| [WS-CI-001](initiatives/WS-CI-001-backend-ci-acceleration/STATUS.md) | Semantic distributed backend lanes complete | Treat further CI optimization as a fresh measured bounded change |
| [WS-CI-002](initiatives/WS-CI-002-deterministic-agent-gates/STATUS.md) | `WS-CI-002-01` complete through PR #311; Agent Gates is deterministic per PR head | Preserve protected-branch review as the independent approval authority |
| [WS-CI-003](initiatives/WS-CI-003-atomic-chunk-state/STATUS.md) | `WS-CI-003-01` complete | Require every chunk PR to land its final contract and initiative state atomically |
| [WS-DB-001](initiatives/WS-DB-001-v01-schema-baseline/STATUS.md) | v0.1 schema baseline complete through PRs #316 and #317 | Extend `0001_v01_baseline` only through future bounded migrations |
| [WS-SEC-001](initiatives/WS-SEC-001-dependency-alert-remediation/STATUS.md) | `WS-SEC-001-01` complete on merge with patched runtime and tooling dependencies | Handle future security alerts through fresh bounded dependency changes |
| [WS-DOCS-001](initiatives/WS-DOCS-001-current-v01-documentation/STATUS.md) | Current v0.1 entry documentation complete | Keep current pages synchronized with merged capability changes |
| [WS-DOCS-002](initiatives/WS-DOCS-002-workstream-definition/STATUS.md) | Canonical Workstream definition complete | Preserve terminology across current documentation and generated artifacts |
| [WS-XINT-001](initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/STATUS.md) | Planning reconciliation complete and closed | Owner initiatives implement the resulting boundaries |
| [WS-AUTH-002](initiatives/WS-AUTH-002-authorization-docstring-lint-correction/STATUS.md) | Bounded correction complete | Future lint work is a new bounded change |
| [FN-ART-002](initiatives/FN-ART-002-deferred-flow-node-artifact-store/STATUS.md) | Deferred and outside the Workstream v0.1 delivery path | Reconsider only through a new explicit initiative |
| [WS-ENG-001 through WS-ENG-008](initiatives/README.md#historical-eng-initiatives) | Historical and closed or superseded | Do not use signed-start, loop-memory, recovery, or archive proposals as current instructions |

## How To Start Contributing

1. Pull current `main` and read `CONTRIBUTING.md`, the capability ledger, and
   the relevant canonical specification.
2. Check [open pull requests](https://github.com/Flow-Research/workstream/pulls)
   for overlapping work. Coordinate ownership if paths or behavior overlap.
3. Select a remaining boundary above or propose another bounded improvement.
4. State intent, scope, non-goals, acceptance criteria, verification commands,
   risk, and reviewers. A small change may do this in its PR; non-trivial work
   uses the smallest applicable initiative or chunk artifact.
5. Implement on a branch or fork, test, review, reconcile with current `main`,
   and open a pull request. Human maintainers decide whether it merges.

Distinct initiatives may proceed concurrently. A merge in another initiative
requires integration review only where it changes the current branch's base,
contracts, paths, or evidence—not ceremonial repetition of unaffected work.

## Planned WS-ARCH-001 PLAN2 children

WS-ARCH-001-PLAN2 is planned. WS-ARCH-001-03A is planned.
WS-ARCH-001-03B is planned. WS-ARCH-001-03C is planned.
WS-ARCH-001-04A is planned. WS-ARCH-001-04B is planned.
WS-ARCH-001-04C is planned. WS-ARCH-001-04D is planned.
WS-ARCH-001-04E is planned. WS-ARCH-001-04F is planned.
WS-ART-001-06A is a planned retirement. WS-ART-001-06B is a planned
retirement. WS-AUTH-001-14 is a planned retirement. WS-POL-003-08 is planned
after canonical WS-ARCH-001-04E.
