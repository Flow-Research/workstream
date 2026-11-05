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
   `Workstream-Task: <task UUID>` trailer on the reviewed immutable head commit.
   Extend the existing GitHub facts adapter with bounded head-commit-message
   retrieval and its response hash. Only the external image interprets the
   trailer. Reuse existing PR/CI/review comparisons. Republish affected images
   explicitly; no old-image fallback and no rewrite of retained evidence.
5. Exercise public guide/upload/request/approval/task/submission APIs and durable
   workers for the Garden drill. Distinguish controlled composition proof from
   a real GitHub PR with eligible independent review and merge. Record any human
   step still pending; never fabricate it or claim the live drill passed early.

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
foreign task markers reject. It must exist before the final checks and review.

## Bounded change

### Allowed files and ownership

- PROJECTS guide compilation, setup continuation, guide routes/schemas and their
  composition roots; affected worker dispatch and ART continuation wiring.
- Existing manager-authored runtime and typed request/runtime contracts where
  required for explicit selection; corresponding AUTH admission integrations.
- Existing forge facts contract and GitHub adapter; project-owned external
  checker code, image build definitions, fixtures and composition tests.
- `pilots/garden/` guide/task/ZIP fixtures and bounded drill helpers.
- Focused existing/new tests for these owners, their necessary inventories and
  OpenAPI snapshots. No CI gate or test-selection weakening.
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
  This proves reviewed task association, not GitHub/Workstream actor identity.
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
negative controls first satisfy merge, CI producer, independent current-head
review and proof comparisons, then vary only the marker or trusted task UUID.

The hosted Garden proof requires the read-only GitHub App, a candidate deployment
and a real task-associated PR with independent review and authorized merge. It
must not be inferred from the controlled local facts. Exact check/review freshness
and operational completion evidence belong in the PR.

## Risk and review routing

Plan review before implementation. Focused security/architecture, QA/test-delta,
product-operations and documentation review on the frozen candidate; CI review
only if CI/inventory changes warrant it. Shared checks run once before fanout.
Human focus: no implicit model invocation, a usable direct PM route, exact task
association without project parsing in core, and honest live-drill limitations.
One PR contains implementation, repairs and evidence; human merge remains
required. Readiness and current CI state belong in the PR, not this record.
