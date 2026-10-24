# Terminal Systems project POST checkers and isolated trial runtime

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Implement source-backed Terminal Systems POST checker images and the generic bounded model/trial capabilities they actually need, then hand exact image/runtime evidence to the separately owned live-project journey.

## Intent

Resume issue #493 from reconciled main `7f6a71a69daf563742b72c706e6d09aa742ac25e`.
Merged PR #656 already supplies the standalone PRE image. The retained setup
handoff identifies two PRE checks, six model POST suggestions, two execution
POST suggestions and two obsolete lifecycle classifications; it is engineering
reference, not current policy. The unchanged guide and a fresh PRE/POST-only
proposal remain the sources to reconcile. This is a real guide-driven project,
not a fixed task-name fixture. Shared model access now covers both POST agents
and setup under #492's one project account; this change consumes that contract
without owning its shared ledger or provider credentials. CHECKERS input/trial
custody adds linear migrations 0063 and 0064 after that dependency.

## Bounded change

Allowed project paths are `pilots/terminal_systems/checkers/**`, the project
README, affected current roadmap/runbook claims, this record and proportionate
test/CI selection for these project assets. Preserve and reuse the delivered
Python PRE image, its exact handoff provenance, samples and recorded evidence.
New project code implements POST rubrics and bounded agent orchestration
independently of named tasks. Shared runtime changes remain generic and are
listed separately below. The unchanged guide, policy authority and lifecycle
operations remain with their existing owners. Schema additions retain exact revision input and trial
evidence; they introduce no new contributor lifecycle.

`.github/workflows/terminal-systems-checkers.yml` runs the project unit and real
image samples on project/contract/tool changes. It adds no model calls, cloud
credentials, deployment, product test exclusions, or replacement required gates.

The remaining POST runtime contract must be reviewed before implementation:
budgeted, invocation-bound model access with credentials outside the sandbox;
isolated execution of submitted environments; trusted trial and revision input.
No claimed passing checker may replace unavailable evaluation with file presence,
untrusted author claims, fixed answers, or manual reviewer findings. Setup-model
budget/effect integration remains owned by #492. No merge, live model spend,
image publication/registration, activation or hosted deployment is authorized
by this record.

### Resumed POST boundary

The retained setup handoff is source-bound engineering input, not current
approved policy. It identifies six model-evaluation and two isolated-execution
POST suggestions from the unchanged guide, but it predates the PRE/POST-only
setup restriction. Engineering preserves those source rules while project setup
obtains a fresh correction; neither the count nor the retained proposal is made
an activation authority by this change.

The first safe POST slice is limited to
`pilots/terminal_systems/checkers/post/**`, this checker README, the existing
Terminal Systems checker workflow, this record, and affected Terminal Systems or
current roadmap claims. It may define source-linked rubrics, bounded project
material tools, strict model-output validation, project image behavior and
offline test doubles. It must consume the generic invocation-local model proxy
contract owned by the concurrent model-runtime change; it must not invent a
second transport, a global bearer token, a provider SDK, provider credentials,
budget storage or a paid-effect ledger. The shared v2 model-session and closed
trial-evidence callback contracts are typed at the existing private proxy boundary; model credentials and ledger
operations remain outside project images.

Generic isolated build/trial support owns the new
`external_checkers/workstream-checker-service/src/trial_relay.rs` module after
coordination with the model-runtime owner. Shared model transport remains in
`model_relay.rs`; this change owns coordinated `main.rs` assembly of the independent trial capability. Model ledger/profile
changes remain in 0062; this change owns only 0063/0064.
`external_checkers/workstream-checker-service/tests/trial_relay.rs` compiles
that otherwise unconnected module and exercises its fake-engine protocol,
identity, bounds, cancellation and cleanup contracts before shared composition.
The concrete generic offline implementation is isolated in
`external_checkers/workstream-checker-service/src/trial_engine.rs` with focused
`external_checkers/workstream-checker-service/tests/trial_engine.rs` launch,
classification, resource, role-projection and cleanup tests. It consumes only
trusted digest-pinned engine inputs and the relay's generic plan; it contains no
Terminal Systems paths, task names, commands or findings.
`external_checkers/workstream-checker-service/src/trial_docker.rs` and
`external_checkers/workstream-checker-service/tests/trial_docker.rs` own the
generic offline Kaniko/descendant-runsc launch policy and a narrow
module-neutral runtime-control seam. This change owns its concrete bounded
command, ownership journal, observation and recovery implementation. The
listed trial-profile, relay and engine files also replace exact fixed slots with
finite ordered slot templates (minimum/maximum occurrences, roles, fresh state
and retainable work outcomes), so source-cited documented procedures remain
variable without becoming an unbounded or project-named shared allowlist.
Composition in `main.rs` is serialized with the shared model transport changes;
this change delivers its own trial engine and callback. The explicit real-engine
qualification entrypoint is
`external_checkers/workstream-checker-service/scripts/qualify_trial_docker.sh`,
backed by the non-production binary
`external_checkers/workstream-checker-service/src/bin/qualify_trial_docker.rs`;
it must exercise the real target with zero silently skipped proof cases.
The trial module publishes a generic typed relay, profile and observation API;
it does not treat relay success as a work verdict. Backend trial authority starts
in `backend/app/modules/checkers/api/trial_profiles.py`,
`backend/app/interfaces/trial_execution.py`, and
`backend/tests/checkers/external/test_trial_profiles.py`. These define a
distinct digest-pinned trusted service-config reader and do not reuse the
monetary model profile. The exact selected-POST, TASK and ART extension files
and typed contracts are listed below, including the two additive owner-custody
migrations. The bridge must keep Docker authority and prepared offline material outside the untrusted project image, expose only
invocation-local bounded tools, and prove aggregate time, CPU, memory, PID and
scratch-disk limits, cancellation, cleanup, no network or host socket in the
nested workload, and trusted infrastructure-versus-work classification. It must
produce authenticated trial evidence rather than accepting contributor-authored
claims. Revision checks additionally require an owner-supplied typed first-versus-
revision context, exact prior material identity and feedback. Missing owner ports
remain explicit infrastructure gaps; project code does not read product tables.

Prohibited changes are migrations outside the two owner additions explicitly
listed below, project-named rules in shared Rust, task-name
allowlists, restoration of the removed private continuation, guide/policy
approval or activation, task import, lifecycle outcome rehearsal, live model
calls, image publication or registration, deployment, and work in the separate
human review/revision initiative. The existing PRE image and its recorded
publication evidence are reused without rebuilding merely to repeat proof.

The intended verification starts with exact handoff/rubric parity, focused
project-rule tests, adversarial malformed or unsupported model-output tests,
bounded material-tool tests and offline fakes. Those are development evidence
only. The reviewable outcome requires the actual generic trial tool plus composed
#492 model flow to produce substantive project findings, including negative,
resource, cancellation, cleanup and replay/substitution controls. Controlled
provider qualification follows the approved shared runtime; live spend and the
project activation/contribution journey remain separately authorized phases.
Real PostgreSQL revision-material qualification also found that migration 0063's
deferred predicate omitted the canonical feedback `schema_version`; a tagged
predicate diagnostic isolated that exact source mismatch. The migration repair
uses the closed `post_submit_current_result_reference` discriminator, after
which the existing three-role MinIO regression must replay against the corrected
schema hash. This is retained validation evidence, not a second test surface.

The shared model invocation lineage now has a foreign key to the external
checker registry. PostgreSQL therefore rejects registry `TRUNCATE` at its
referential-integrity boundary before the registry's immutable statement
trigger runs; `UPDATE` and `DELETE` still exercise that trigger directly. The
regression accepts only those two explicit denial paths and rechecks that the
registry and audit snapshot is unchanged, so this ordering change does not
weaken immutability.

`backend/tests/test_checker_evidence_migrations.py` qualifies retained checker,
checker-model and setup-model ART rows across 0062 to the current head. Current
ORM fixtures may use only nullable projection columns during arrangement; those
columns must remain null and be removed before the exact canonical 0062 schema
is checked and upgraded. Historical checker-run rows are arranged explicitly by
the isolated fixture; this does not restore a production writer for that retired
subject. Its temporarily suspended arrangement guard must be restored before the
canonical schema assertion and upgrade. Compare all retained fields after
upgrade and the new null projections. This is database preservation proof;
public recovery and byte reads remain separate integration checks.

This shared-boundary change also owns `external_checkers/README.md`,
`docs/architecture_checker_framework.md`, `docs/architecture_lockdown.md` and
`docs/decision_0014_external_service_adapter_convention.md`. Before the relay is
composed, those canonical documents and ADR distinguish the typed,
profile-authorized invocation tool from the retired image-output continuation.
An image may submit bounded workload argv, relative selectors and opaque
project-profile roles through `/work/execution.sock`; it may not return a
private plan as its outer result, select a host path, Docker flag, mount,
runtime, image, credential, network or resource enlargement. Shared Rust knows
no Terminal Systems filename, task, trial label or command allowlist. Preserve
the regression that `project_private_plan.v1` outer output is invalid.

## Acceptance criteria

Setup and policy integration use the same generic trial contract. The affected
`project_agents.py` dependency schema and default instructions must describe
`trial_proxy` for nested execution and its prepared offline material. A supported
binding must select the complete trial profile/projection; PRE, partial selectors
and undeclared registry capabilities are rejected. Retained immutable gap
specifications remain readable, but do not become supported bindings. Project
execution specifications can also declare model assistance under #492's existing
model-service dependency. Focused contract tests must exercise these admission
boundaries before the live-project owner generates or approves a fresh proposal.
The matching proposal-reader dependency vocabulary in
`cli/internal/api/guide_proposal.go` and its existing process tests must accept
these exact declarations without relaxing unknown-field or supported-gap rejection.

- PRE layout checks required regular files and directories at the package root,
  accepting arbitrary task subjects and additional useful directories.
- Metadata implements the documented types, path containment, command argument
  arrays, positive integer allowances, platform and extension rules; it never
  runs commands or invents guide size limits.
- Findings identify the documented rule and safe relative location. Resource,
  material or implementation failures remain infrastructure outcomes.
- Use the existing generic image command for real networkless, non-root,
  read-only positive/negative sample execution and exact result identity checks.
  Local Docker evidence is labelled `docker-dev`, never gVisor qualification.
- Produce immutable build and configuration metadata for tested POST images,
  without publishing, registering or activating them in this change.
- Every claimed POST pass must use actual model/trial evidence through the
  supported generic capabilities. Preserve the original guide and immutable
  earlier proposals; keep unsupported revision/prior-work dependencies explicit.
- Hand exact image/runtime evidence and remaining dependencies to #555's owner.
  The live public API/CLI activation and contribution journey are not this
  change's acceptance criterion, and image samples alone are not that proof.

## Risk and review routing

Risk class: L1. Required focused reviews: architecture/plan, security and QA/test
delta; CI review only for changes to CI selection. Human focus: real rule coverage,
generic runtime boundaries, exact cost/custody, and honest qualification limits.

## Plan review

Architecture inspection confirmed that policy duplicate rejection includes
requirement identity. The same registered capability can safely serve the two
requirements with distinct locked configurations and separately counted budgets.
The initial PRE plan has no architecture blocker. Generic POST prerequisites
remain under design review; missing runtime support blocks activation.

## Evidence

Independent review identified noncanonical metadata path aliases and undeclared
fields in the four fixed metadata tables. Two regression cases reproduced eight
incorrect passes before repair. Paths now preserve exact manifest spelling and
supplementary metadata belongs under `extensions`; arbitrary nested extension
data remains supported. The image sample suite includes both rejection cases.
The affected roadmap and project documentation distinguish the retained ten
unbound suggestions, implemented PRE rules, and remaining eight POST rules.

Seventeen rule tests and seven actual networkless Docker samples pass. The
publisher pushed the reviewed image to ECR, verified the immutable manifest,
pulled it back and reran all seven samples. The exact image was registered through
the local Operator CLI. Publication and registry facts are in the checker README;
these do not establish gVisor, policy approval or a completed contribution journey.


## Revision evaluation material: owner-bound read slice

The lead owns the additional files
`backend/app/modules/tasks/api/evaluation_revision.py`,
`backend/app/modules/tasks/evaluation_revision.py`,
`backend/app/modules/checkers/api/revision_feedback.py`,
`backend/app/modules/checkers/revision_feedback.py`, and focused regressions
`backend/tests/tasks/submission_dispatch/test_evaluation_revision.py` and
`backend/tests/checkers/execution/test_revision_feedback.py`.

TASK projects the current immutable Submission and, only for a real revision
within the same assignment, the exact predecessor and consumed revision
preparation. ART supplies the preparation selector from its consumed admission;
TASK validates its own preparation/source/assignment and applied policy lineage.
It never substitutes the latest preparation or reevaluates an already-consumed
revision deadline at read time. A new claimant starts with no predecessor
material even when the task's global Submission version exceeds one.

CHECKERS resolves the exact retained completed source result through a typed
read port, validates its canonical request/result identities, and projects only
bounded normalized findings with requirement/registry/configuration provenance.
These reads grant no authority. Composition must retain existing AUTH and
TASK-before-CHECKERS current-lease custody before selection, close transactions
before storage I/O, and revalidate exact selections afterward. No private
cross-owner table reads, migrations, public contributor surface, lifecycle
changes, partial/truncated feedback, or change to #555 is permitted.

Acceptance is exact initial/revision identity and policy linkage, immutable
retained findings, concealment of cross-project/assignment and stale selectors,
reclaimed-task initial isolation, bounded complete feedback, and no read-time
mutation. Focused positive/negative and PostgreSQL owner proofs precede the ART
projection integration. This staged read slice alone does not deliver the
prior archive to an image or close PILOT-06. Declare the exact ART/grant files
and obtain boundary review before extending that transport.

The next bounded policy slice owns
`backend/app/modules/checkers/api/external_policy.py` and
`backend/tests/checkers/external/test_evaluation_context_selection.py`.
The flat reserved configuration pair
`workstream_evaluation_context_version` / `workstream_evaluation_context_roles`
selects version `v1` and a sorted, unique subset of
`predecessor_submission_archive` and `predecessor_findings`. Empty roles request
only the initial/revision distinction. Both absent means current-only material;
partial, unknown-prefix or PRE selections fail. The immutable registry
configuration schema must explicitly declare both keys as properties as well
as validate the approved values. No policy or schema is injected at runtime.
Focused positive/negative compilation tests must preserve ordinary PRE/POST
bindings and reject permissive schemas that never declared this capability.

## Revision material transport

The next transport slice extends the existing execution/materialization path in
`backend/app/modules/checkers/api/external.py`,
`backend/app/modules/checkers/api/evaluation_context.py`,
`backend/app/modules/checkers/api/materialization.py`,
`backend/app/modules/checkers/api/selected_post_submit.py`,
`backend/app/modules/checkers/execution.py`,
`backend/app/modules/checkers/selected_post_submit_execution.py`,
`backend/app/modules/artifacts/post_submit_selection.py`,
`backend/app/modules/artifacts/post_submit_materialization.py`,
`backend/app/modules/artifacts/preparation.py`, and the existing composition
files `backend/app/adapters/tasks/__init__.py`,
`backend/app/adapters/checkers/__init__.py`, and
`backend/app/adapters/artifacts/__init__.py`.
The shared image wire/grant changes own
`external_checkers/workstream-checker-sdk/src/lib.rs` and the grant verification
and mount construction sections of
`external_checkers/workstream-checker-service/src/main.rs` only. Coordinate
those sections with the model-runtime owner; do not overwrite its capability
composition or the execution agent's trial engine.

An independent scratch reproduction confirmed that the current POST grant
publisher moves the tree on its first use and rejects the second selected
binding. POST uses one v2 aggregate grant workspace for both current-only and
revision material. Archives project once into fixed private role roots; each
binding publishes and revokes only its request-bound manifest. PRE remains its
distinct existing v1 intake protocol. Current material mounts read-only at
`/work/input`; an approved predecessor role mounts read-only at
`/work/context/predecessor`. An image selects neither host paths nor mount flags.
One aggregate reservation applies the existing scratch byte/entry ceilings to
both archives and control entries. There is no second materializer or doubled
per-archive allowance.

The short transaction order is AUTH preparation, TASK current bundle, ART's
nonlocking consumed-preparation selector, TASK revision facts, current CHECKERS
lease custody, requested historical feedback, and complete ART selections.
The exact policy plan and role facts enter the authority digest; commit before
storage I/O. After cancellation-safe cleanup, repeat that order and validate
the original receipt against exact unchanged selections. A missing, excessive
or substituted source is infrastructure failure, never a fallback to less
material. Image context omits contributor identities. Optional member input
receipts are mandatory for context-enabled bindings and omitted canonically
when absent, preserving retained historical result digests without a parallel
execution implementation.

Regression scope also includes
`backend/tests/checkers/external/test_contracts.py`,
`backend/tests/checkers/external/test_selected_post_submit.py`,
`backend/tests/checkers/external/test_runtime.py`,
`backend/tests/checkers/external/test_revision_materialization.py`,
`backend/tests/projects/post_policy/test_compiler.py`,
`backend/tests/test_post_submit_selection.py`,
`backend/tests/test_post_submit_materialization.py`, their existing
`backend/tests/post_submit_materialization_helpers.py` fixture, and
SDK/service inline tests. Prove two sequential bindings with unchanged trees,
current-only hidden-prior isolation, exact revision identity and findings,
rebase/reclaim, denied/substituted grants, aggregate quota/cleanup, retained
result reconstitution, and fresh real PostgreSQL/MinIO materialization. These
changes require architecture, security, QA/test-delta and affected docs review
before the complete issue is represented as ready.

The real approved revision-role fixture exposed a prerequisite in
`backend/app/modules/projects/post_policy/compiler.py`: saved POST configuration
compared JSON lists with typed proposal tuples and rejected identical approved
array parameters. This bounded owner fix compares canonical JSON parameter
values, matching approval compilation. Preserve exact ordering and reject
changed values; do not weaken proposal, registry or approval custody.

Real PostgreSQL terminal publication also requires extending retained input
custody: the existing SQL authorization digest reconstructs only the current
archive and correctly rejects an authority receipt that additionally binds
revision context. Add nullable `checker_runs.input_context_custody`, typed closed
context/prior evidence, and bind it to terminal authorization and replay. Keep
the existing `material_custody` shape and historical receipt digests unchanged.
No context-enabled terminal result may omit the extension or substitute a
different preparation, assignment, predecessor or feedback source.

This extension owns `backend/app/modules/checkers/models.py`,
`backend/app/modules/checkers/api/execution.py`,
`backend/alembic/versions/0063_checker_revision_input.py`,
`backend/alembic/env.py`, `backend/tests/test_alembic.py`,
`backend/scripts/schema_baseline_manifest.py`,
`backend/tests/conftest.py` (expected public-schema fingerprint only),
`backend/tests/checkers/external/test_revision_materialization.py` and affected
schema fingerprints. Migration 0063 follows PILOT-05's shared model owner 0062;
integrate the committed dependency before migration qualification. No competing
head or rewritten retained data is allowed. Prove exact SQL/Python digest
agreement, current-only retained data, selected initial/revised inputs,
substitution/omission denial and rollback on real PostgreSQL.

Trial runtime composition uses the already verified ART request grant and six
flat, approved profile/projection selectors. The trusted service resolves them
against an exact operator-provisioned manifest; partial, unknown, substituted
or PRE selectors confer no execution authority. This owns
`external_checkers/workstream-checker-service/src/trial_profiles.rs` (strict
manifest parser/resolver and inline tests), `src/main.rs`, `src/trial_relay.rs`
and `src/trial_engine.rs` within that same crate (source-role mapping only).
No new dependency is needed. Project paths and execution commands stay in the
project image/projection, outside the shared service. Trial receipt handles
require durable CHECKERS/ART evidence publication before model assessment.

The retained 0001 baseline SQL and its committed manifest remain unchanged.
The additive migration advances the current schema; only the test harness's
current public-schema fingerprint is regenerated from head. Fresh baseline
parity and intermediate-to-head migration tests prove these separately.

Durable trial evidence closes the concrete retry gap between a completed
sandbox trial and paid model assessment. CHECKERS allocates one UUIDv7 evidence
record for an exact submission, binding, trial kind and slot before execution.
Plan/input/material hashes are immutable facts at that address, not additional
keys permitting another trial slot. Original lease/request facts are retained
provenance; each write/read still requires fresh current execution authority.
ART uses its existing generated-output put/verify/bind/recover pipeline with a
typed trial subject. A retry recovers the originally committed receipt bytes;
local scratch handles never become durable references. No paid model effect is
required to publish a trial, avoiding a circular trial-to-assessment dependency.

Exact owner scope: `backend/app/modules/checkers/api/trial_evidence.py`,
`backend/app/modules/checkers/trial_evidence.py`,
`backend/app/modules/checkers/models.py`, and
`backend/tests/checkers/external/test_trial_evidence.py`. The shared ART and AUTH
trial branches belong to this change; additive owner migration 0064 follows
0063. Verify current TASK-before-CHECKERS custody, distinct
contributor isolation, concurrent reservation/first-content pinning, mutation
denial, rollback and loss/recovery of the publication response on PostgreSQL
and MinIO. No trial handle may authorize model spend without verified bytes.

The private trial callback extends the existing framed checker proxy with a
closed `workstream.trial_evidence_proxy.v1` reserve/publish protocol. The trusted
listener allows at most 4 MiB for this protocol, while model frames remain
bounded to 1 MiB. Images never receive the host proxy socket. A reservation
reply either authorizes the one plan or returns the original ART-verified
receipt for replay. Publishing requires exact current execution and the first
pinned content; lost responses recover the existing put/binding. This owns
`backend/app/interfaces/checker_trial_proxy.py`,
`backend/app/adapters/checkers/trial_proxy.py`, and
`backend/tests/checkers/external/test_trial_proxy.py`. Shared transport/runtime
composition is coordinated with PILOT-05. No provider call or network access is
introduced by the trial protocol itself.

Trial owner persistence owns additive
`backend/alembic/versions/0064_checker_trial_evidence.py`, existing migration
preflight/graph tests, and `backend/tests/conftest.py` (head fingerprint and
exact new table reset/deletion inventories). The same migration adds only the
shared ART trial-subject foreign keys agreed with PILOT-05. Retain one linear
chain after 0063, preserve historical model-output rows, and verify supported
intermediate upgrades and immutable terminal evidence without baseline edits.

The trial-specific ART extension belongs to this change after migration 0064,
so the prerequisite model-runtime PR remains independently deployable. Extend
the existing pipeline through explicit checker-model, setup-model and trial subject cases in:
`backend/app/modules/checkers/api/output_custody.py`,
`backend/app/modules/artifacts/api/checker_output_authority.py`,
`backend/app/modules/artifacts/schemas.py`,
`backend/app/modules/artifacts/models.py`,
`backend/app/modules/artifacts/service.py`,
`backend/app/modules/artifacts/checker_output_custody.py`,
`backend/app/modules/artifacts/checker_outputs.py`,
`backend/app/modules/artifacts/checker_output_bindings.py`,
`backend/app/modules/authorization/domain/checker_outputs.py`,
`backend/app/modules/authorization/domain/audit.py`,
`backend/app/modules/authorization/checker_output_authorization.py`,
`backend/app/adapters/artifacts/__init__.py`,
`backend/app/adapters/checkers/__init__.py`,
`backend/app/adapters/checkers/model_runtime.py`,
`backend/app/adapters/checkers/model_proxy_transport.py`, and
`backend/app/core/config.py` (the paired trusted manifest path/digest only).
Keep existing model request/response identities and evidence unchanged. First
trial content is pinned only in the same transaction as ART put admission; the
preparation/probe transaction must not leave an orphan content commitment.

Generated-output composition also updates the existing model caller in
`backend/tests/checkers_model_calls/test_composed_execution.py` to supply its
model owner explicitly. Trial integration proof extends
`backend/tests/checkers/external/test_trial_evidence.py`; both use the same
ART services and independent verification worker.

Trial storage integration and private transport qualification own
`backend/tests/checkers/external/test_trial_artifact_custody.py` and
`backend/tests/checkers/external/test_model_proxy_transport.py`. Prove rollback
of the first content pin, exact replay/read, private protocol routing and
separate model/trial frame ceilings without a live provider call.

The provider-free durable-custody composition proof owns the new focused test
`backend/tests/checkers/external/test_trial_model_custody.py`. It may
reuse the existing PostgreSQL/MinIO material fixture, production private proxy
transport, real CHECKERS/ART trial handler, real model grant/ledger owner, and a
controlled provider from the existing model-call tests. Its Python driver
synthesizes one normalized receipt, then exercises generic trial publication,
receipt-resolved model assessment and exact retained-byte replay without a
second trial or paid effect. It does not prove the Rust relay or engine. It
introduces no live provider call, deployment setting, image publication,
policy activation, or alternative durable acknowledgment.

The complementary service-boundary qualifier owns
`external_checkers/workstream-checker-service/tests/terminal_systems_post_composition.py`.
It launches the production Rust service binary with the actual locally built
Terminal Systems POST image and a closed controlled v2 proxy, proving exact
image identity, request/grant validation, invocation-local socket mounting and
cleanup without a provider call. It is not durable ART custody proof and does
not replace the PostgreSQL/MinIO composition test above or the runsc engine
qualification.

The final controlled-provider qualification owns
`external_checkers/workstream-checker-service/scripts/qualify_terminal_systems_runsc.sh`
and
`external_checkers/workstream-checker-service/tests/terminal_systems_runsc_composition.py`.
Its AR-RD-001 regression may extend only the reusable test-fixture plumbing in
`backend/tests/projects/guide_activation/source_fixtures.py`,
`backend/tests/projects/unified_policy_fixtures.py`,
`backend/tests/selected_policy_fixtures.py`, and
`backend/tests/post_submit_materialization_helpers.py` so one project can
create two genuinely approved POST bindings against the same registered
capability. Default single-binding callers and production proposal APIs remain
unchanged.
Architecture replay also requires exact binding context during catalog
resolution: immutable profile/projection selectors may be reused by different
locked configurations, while a duplicate or conflicting full registry/image/
configuration envelope remains invalid. Trial plans may retain state only from
an earlier completed slot; a slot cannot name itself as its state source, and
that rejection occurs before the engine is called.
The wrapper may reuse only the explicitly prepared PILOT-00 owned DIND state,
temporarily replacing and then byte-for-byte restoring that stopped harness's
daemon configuration. The temporary exact configuration exposes two separately
identified runtimes: the outer checker uses `host-uds=open` for its two exact
invocation-local sockets and submitted-code descendants use a distinct
`host-uds=none` key. The isolated test drives the production Rust service and
project POST image through real PostgreSQL/MinIO trial custody, the generic
offline build/run engine and an offline controlled provider. It stages only the
qualification-only package, never a real Terminal Systems task. The wrapper
must restore the owned harness configuration, stop a previously stopped
harness, and remove only its exact inner registry/checker resources on success
or failure. Docker cleanup commands have finite timeouts, and a conflicting
cleanup container label or image identity must stop cleanup before deletion.
This is no live provider call, deployment, publication, activation,
or contribution rehearsal.

Qualification exposed two runtime-custody defects that this same trial owner
must close before readiness. Disk bytes, entry count, and CPU time are
whole-invocation ceilings: projections, build context, candidate output, every
retained workspace, mutable child writes, builder rootfs, and expanded
candidate layers share one remaining ledger rather than receiving fresh
per-operation limits. The engine must fail closed before another operation when
that ledger is exhausted, while operation receipts retain their exact local
measurements. The runsc builder requires an actually enforced per-container
filesystem byte and inode quota. The pinned runtime drops `nr_inodes` from
Docker-created tmpfs mounts; the digest-pinned trusted launcher must create
the bounded tmpfs inside the sandbox before dropping mount/chroot privileges.
The launcher and its build/qualification assets are part of this generic
runtime scope, with its digest bound in the approved trial profile. It owns
no project rules. Every writable temporary/shared-memory filesystem must be
bounded and reserved in the same ledger;
candidate layers must be streamed and bounded for expanded bytes and entries
before Docker load, using a streaming gzip decoder and binding each layer's
uncompressed digest to the ordered image configuration. The narrowly scoped
`flate2` dependency and Cargo lock update implement that decoder; no layer is
extracted on the host by this scanner. Forced deadline/resource termination must project a
canonical cause without retaining Docker's synthetic exit 137 or inventing an
unobserved signal, and the relay validator must accept that truthful shape.
Focused engine, Docker-control, and relay tests must discriminate aggregate
copies, retained state, child writes, combined CPU, rootfs writes, expanded
layers, OOM, deadline and resource termination. No global daemon change,
provider call, or relaxation of the invocation ceiling is authorized.

The launcher exports private candidate, status and workspace files to the
explicit nonroot service UID/GID, including partial paths so cleanup can run
after failure. Build and step observations share a closed `export_outcome`
field. Unsupported generated state and explicit logical export-cap refusal
retain the real child status; host copy/fsync failures remain infrastructure
failures. Dependent steps cannot use unexported state. The project client must
accept truthful forced-stop observations with an unknown signal and must reject
synthetic exit codes, absent export facts and contradictory outcomes. These
facts do not add project grading or lifecycle decisions to the shared runtime.
