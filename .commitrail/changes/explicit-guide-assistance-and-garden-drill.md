# Explicit guide assistance and Garden drill

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Explicit PM setup requests and provider-free rules use one authorized pipeline; Garden has a small documented contribution drill and independently verified task-associated PR evidence.
- Risk: L1 — authorization, immutable guide inputs and external evidence

## Intent

Uploading a guide must not invoke inference. A Project Manager explicitly
requests optional assistance: the agent receives the assigned guide documents
and task examples, plus PM feedback only on an explicit correction. It proposes
PRE/POST requirements; it neither selects images nor controls lifecycle policy.
PM-authored requirements must also reach the existing validation, independent
PRE/POST approvals and activation without paying for or invoking a model.

Prepare one small, real Garden engineering drill in this same PR. Workstream
owns task/assignment/submission/acceptance truth. Garden owns its code, project
guide and external evaluation. GitHub supplies independently retrieved facts.
The ZIP contains claims in `proof.json`, not another copy of the repository.

The user subsequently clarified that this test drill does not require an
independent GitHub review. Garden's image must support an explicitly selected
zero-approval requirement while retaining real merge, trusted CI, repository,
commit and task-association checks. Omission continues to require one approval;
Harnessy's existing minimum remains one. This is a project-checker policy
choice, not permission to manufacture review facts or bypass Workstream's
locked ReviewPolicy. Previously registered images and activated guides remain
immutable; publish the changed image and approve a new guide for the drill.

## Implementation plan

1. Extend existing PM compilation request/dispatch custody for initial explicit
   requests. Reuse its transaction, live authority, replay and durable worker.
   Retain the setup row needed by document-upload custody; uploading or scanning
   complete documents must not manufacture a request. Recovery may republish
   only committed explicit requests. Corrections retain their exact predecessor.
2. Expose a provider-free PM-authored requirements operation through the same
   compilation/approval path, reusing the existing manager-authored rules
   runtime and exact original-document evidence. Do not require changing global
   runtime settings to choose this path. Document the rules input honestly;
   do not manufacture model provenance or approve requirements automatically.
3. Prepare Garden guide and a few bounded task/negative-fixture definitions
   from current repository documentation. Prefer a genuine documentation fix
   for the first successful task; do not recycle an unrelated merged PR.
4. Verify task association in Garden's external image using one canonical
   `Workstream-Task: <task UUID>` trailer on the immutable PR head commit.
   Extend the existing GitHub facts adapter with bounded head-commit-message
   retrieval and its response hash. Only the external image interprets the
   trailer. Reuse existing PR/CI/review comparisons. Republish affected images
   explicitly; no old-image fallback and no rewrite of retained evidence.
5. Connect the existing GitHub App adapter to the hosted release using the
   existing private secret-file mechanism. Forward only required App settings
   only to the outbox worker that retrieves forge facts; never expose the key to checker
   images, model proxy, release metadata or logs. Validate complete optional
   configuration and preserve releases that do not use forge checking.
6. Exercise public guide/upload/request/approval/task/submission APIs and durable
   workers for the Garden drill. Distinguish controlled composition proof from
   a real GitHub PR with authorized merge and its configured approval count. Record any human
   step still pending; never fabricate it or claim the live drill passed early.

For the clarified zero-approval drill, extend the shared evaluator with an
explicit minimum-approval argument used only by the Garden entry point, keeping
the Harnessy default and validation unchanged. Garden's registration schema
allows zero; negative, boolean and excessive values reject. Test explicit zero
against authentic-shaped facts with no reviews, omission against those same
facts, and retained merge/CI/task failure boundaries. Update Garden's guide,
rules and publisher fixtures together; no Workstream core or AUTH relaxation.
Requalify the image and retain all previous deployed evidence under its actual
identities. A new claimed task must bind the new guide; do not reinterpret the
existing claimed task's policy.

The revised drill also tests project-point awards. The first hosted Garden
policy was unpaid and does not prove awards. Configure a fixed 100-point test
award for `accepted_submission` through the existing authorized points-unit,
adapter-binding and Finance policy operations before the new task locks its
policy; leave `completed_review` unpaid. Preserve the prior published policy.
On acceptance, verify the exact point unit and quantity, award-definition and
ContributionRecord linkage, locked policy version and atomic FinalAcceptance.
PRE/POST rejection must earn no award; exact submission/acceptance replay must
not create another award or contribution. This proves an earned award, not
external fulfillment, a wallet balance or a money payment. No new compensation
subsystem or external payment delivery belongs in this repair.

Two same-head hosted schema-lane runs reached the unchanged 1,500-second
limit at different completed-test boundaries. Rebalance the existing post-submit
authorization migration/receipt and review-packet storage modules into the
existing shared-foundation partitions. Change only
`backend/scripts/test_lane_catalogue.py` and its exact allocation tests; retain
all 17 lanes, test nodes, execution kinds, timeouts and completeness/coverage
collection. Compare full collection manifests before and after and prove that
only the intended 33 existing nodes change lane ownership. Timing projections
are estimates; only a complete hosted run can establish the repair. No test
deletion, skips or timeout increase is authorized by this repair.

### Closed request and delivery contract

The explicit initial operation selects only assistance or manager-authored
rules. Composition owns all provider/profile/instruction settings. Resolve and
bind that choice before reservation; same-key mode substitution is a conflict
after fresh authorization. Delivery/recovery reads only retained configuration.
A delivery without an exact committed PM request must reject, including direct
worker calls. Historical automatic-request evidence remains readable but cannot
authorize new inference. Worker topology must enforce bounded Redis/prefork
execution for an inference attempt independently of global runtime selection.

The reused manual format is exactly one uploaded `text/markdown` original whose
complete body is the `workstream.project_guide_rules.v1` JSON object, alongside
the guide originals. Supply a valid documented fixture; ordinary prose alone is
not this format. Manual rules changes use a new guide version, not an inference
correction or fabricated feedback run. This is provider-free compilation.

The Garden marker grammar is exactly one standalone
`Workstream-Task: <canonical lowercase UUID>` line in the final commit trailer
block. Duplicate reserved occurrences anywhere, malformed values, missing or
foreign task markers reject. It must exist before final checks and any reviews required by the locked count.

## Bounded change

### Allowed files and ownership

- PROJECTS guide compilation, setup continuation, guide routes/schemas and their
  composition roots; affected worker dispatch and ART continuation wiring.
- Existing manager-authored runtime and typed request/runtime contracts where
  required for explicit selection; corresponding AUTH admission integrations.
- Existing forge facts contract and GitHub adapter; project-owned external
  checker code, image build definitions, fixtures and composition tests.
- `pilots/garden/` guide/task/ZIP fixtures and bounded drill helpers.
- Hosted Compose/preflight/entrypoint and existing deployment tests for the
  missing GitHub App secret-file wiring; reuse existing secret validation.
  Use one conditional worker-only Compose overlay; API/migration, beat, parser,
  model proxy and proof roles receive neither the key nor its selectors.
- Focused existing/new tests for these owners, their necessary inventories and
  OpenAPI snapshots. No CI gate or test-selection weakening. Refresh exact UUID-generation and
  AUTH test-structure inventories after reconciling affected owner call sites;
  keep test payloads out of parameter IDs so exact selected nodes fit process
  argument limits without changing assertions or execution selection.
- Existing CI lane catalogue and its allocation tests for the measured
  three-module redistribution described above; no workflow/gate relaxation.
- This record, affected current README/spec/runbook/roadmap claims and local
  roadmap exports if present. A migration only if an identified persisted
  invariant needs enforcement; preserve retained records.

### Prohibited changes

No issue synchronization, source-adapter framework, TUI/CLI expansion, new
acceptance workflow, contributor/GitHub identity mapping, automatic AI approval,
unrestricted sandbox networking or repository-wide cleanup. No new auto/manual
policy flag. No model spend beyond the already authorized budget. No GitHub
approval, merge, contribution or evaluation facts invented for the drill.

## Acceptance criteria

- Completed uploads and periodic recovery invoke no provider without an explicit
  authorized PM request. Forged worker deliveries cannot create that authority.
- Initial request replay, duplicate delivery, revocation, project isolation,
  incomplete sources, rollback and broker failure preserve existing guarantees.
- Provider-free PM rules and explicit assistance both reach the same review and
  activation gates; default-true and false human-review branches remain intact.
- Existing correction feedback stays explicit and excludes image/registry data.
- Forge retrieval is scoped to the locked repository and actual head SHA,
  bounded before full response allocation, and rejects inconsistent facts.
- A valid Garden PR proof passes its trusted task and fails another; missing,
  duplicate or malformed task trailers and failed CI reject with findings.
  This proves declared head-commit task association, not GitHub/Workstream actor identity or a human review when the configured count is zero.
- Hosted forge configuration requires paired App identity and private key,
  admits only the intended consuming roles, and does not disclose secret bytes
  through rendered configuration, errors or release evidence.
- Actual offline image composition covers locator and evaluation. Live drill
  evidence identifies exact images, guide/policies, artifact and durable outcome;
  an accepted path must yield the actual submitter ContributionRecord.
- Remove affected obsolete auto-start behavior/tests, retaining authorization,
  immutable evidence and data-preservation proof. Tests must discriminate the
  reported defects, not fail on unrelated validation first.

## Evidence

Verification uses focused pytest selections for PROJECTS request,
delivery, recovery and public dispatch; manager-authored runtime tests; worker
topology tests; `backend/tests/test_github_facts_adapter.py`; external image unit
tests and existing actual-image forge composition; module-boundary, markdown-link
and Commitrail checks; `git diff --check`; full hosted suite. Local PostgreSQL
proof covers explicit request/replay, source and authority isolation, shared
execution, broker recovery and provider-free compilation. Real MinIO proofs
cover original-byte upload and concurrent delivery without automatic admission.
Actual offline image and native-service composition prove controlled Garden
facts and foreign-task rejection, not live GitHub access. Full public-API
fixture sequence is upload
all originals -> assert no attempt/provider call -> explicit authorized request
-> durable worker -> proposal -> separate policy approvals -> activation. Forge
negative controls first satisfy merge, CI producer, the configured approval
count and proof comparisons, then vary only the marker or trusted task UUID.

The hosted Garden proof requires the read-only GitHub App, a candidate deployment
and a real task-associated PR with authorized merge and configured checks. The
explicit zero-approval test does not require or fabricate a GitHub review;
omission/positive counts retain their review requirement. Guide v2 and capability
v2 require new approvals and a new task; retain the earlier records and leave PR
#287 open as requested. A successful outcome must not be inferred from controlled
facts or open work. Exact check/review freshness
and operational completion evidence belong in the PR.

## Risk and review routing

Plan review before implementation. Focused security/architecture, QA/test-delta,
product-operations and documentation review on the frozen candidate; CI review
only if CI/inventory changes warrant it. Shared checks run once before fanout.
Human focus: no implicit model invocation, a usable direct PM route, exact task
association without project parsing in core, and honest live-drill limitations.
One PR contains implementation, repairs and evidence; human merge remains
required. Readiness and current CI state belong in the PR, not this record.

### Authenticated project-points operator prerequisite

The approved 100 project-points drill requires supported hosted provisioning of
its unit and binding. This bounded auth repair replaces the existing local
script's trusted Finance UUID/local admin-subject assumptions with one standard:
a private bounded bearer-token file, the configured Flow verifier, exact ACTORS
issuer/subject resolution and canonical AUTH/PREP Finance create-scope fences
before every discovery/replay and committed step. Adapter identity is provisioned
separately through the existing Access Administrator public route; no adapter
runtime or external delivery capability is fabricated.

Allowed files for this repair are `backend/scripts/provision_project_points.py`,
`backend/tests/test_provision_project_points.py`,
`backend/app/modules/compensation/service.py` and the existing focused binding
recovery tests (the existing create-scope fence moves after the operation lock
and before replay; read authorization remains), the project-points sections of
`docs/engineering/local-agent-loop.md`, `docs/operations_project_operating_manual.md`
and `docs/spec_contribution_compensation.md`, and this record. No new public
route, authorization action, compatibility mode, environment bypass, migration,
fulfillment behavior or direct product-row insert is allowed. Risk is L1
(identity/Finance authorization); focused security/architecture plan review
passed with root review of the final implementation still required.

Acceptance requires actual verified human identity and current Finance scope for
new and existing resources, token re-verification for each committed step,
owner-mediated exact replay, current active unit/binding/adapter eligibility,
private secret-free errors/receipts, and unchanged atomic award ownership.
Verification uses focused pure token-file/Flow checks plus the existing isolated
PostgreSQL provisioner suite for permissions, isolation, replay, expiry/revocation,
rollback and committed-step reporting; lint and diff checks follow. Hosted
mutations and publication remain separate explicitly invoked operator actions.

### Fixed hosted points operator invocation

The authenticated provisioner also needs the deployed API role's Docker network,
file-backed secrets and Flow TLS trust. A standalone host interpreter does not
supply that environment. Extend the existing hosted Compose command allowlist
with exactly `provision-project-points`, taking required structured
`--project-id`, `--adapter-actor-id`, `--unit-code`, `--route-key` and
`--finance-token-file` inputs. No caller command, entrypoint, image, source mount,
Compose override, arbitrary environment or generic `run` is admitted.

Hosted feasibility requires an immutable backend image containing the reviewed
authenticated provisioner and binding replay fence. An older deployed backend
image is insufficient; no source mount, entrypoint override or image substitution
is permitted to work around that prerequisite.

Allowed files are `deploy/hosted/compose.py`, `deploy/hosted/preflight.py`,
`scripts/test_hosted_release_config.py`, `deploy/hosted/README.md`, the hosted-use
paragraph of `docs/engineering/local-agent-loop.md`, and this record. Risk remains
L1 (deployment/Finance authentication). Security/architecture plan review precedes
implementation, then focused source/QA review binds the final candidate. Human
focus is one fixed immutable-image command and token-only mount, preserving the
existing application/native identities and caller-owned Finance transactions.

The wrapper validates the same release environment, rendered API topology and
static private host inputs as the fixed migration operation; it does not require
or start checker execution. It constructs only an API-role one-off invocation
with `--rm`, `--no-deps`, `--pull never`, the existing release entrypoint, and
`python scripts/provision_project_points.py` with the validated selectors.
The sole extra mount is the selected token file read-only at the fixed container
path `/run/secrets/points_finance_token`. Its host path must be canonical,
absolute, free of Compose-volume delimiters, a bounded nonempty single-link
regular file owned by runtime UID/GID 10001:10001, mode 0400 or 0600, with no
symlink traversal. The provisioner independently rechecks token custody and Flow
identity inside the container. The wrapper does not read, log or interpolate the
token. The existing hosted proof pattern supplies a generated, non-caller-chosen
container name, an inner 120-second TERM deadline with a five-second kill grace,
a 150-second outer wait, and a ten-second exact owned-container cleanup reserve.
Normal completion uses Compose `--rm`; exceptional cleanup targets only that
invocation's name, and a timeout never means ready.

Acceptance requires rejecting unknown, duplicate, malformed or missing arguments
before operator execution; immutable backend image and inherited API role,
secrets/network/TLS remain unchanged; no dependency/service startup or application
source/image override is possible. Tests assert the exact generated argv,
allowlisted subprocess environment, fixed mount target and read-only mode,
private-file failure boundaries, bounded cleanup, absence of credentials in
argv/errors, and continued rejection of generic `run`/entrypoint/source controls.
Verification uses the existing hosted configuration test module plus targeted
script/entrypoint contracts, lint, Markdown links and diff checks. No live
provisioning or deployment is part of this implementation proof.
