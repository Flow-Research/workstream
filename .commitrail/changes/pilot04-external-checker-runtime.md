# [PILOT-04] Add The External Checker Service Boundary

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Add one unselected Rust checker service and SDK,
  one typed Python Unix-socket client, and one ART-owned ephemeral material
  grant that prove a digest-pinned checker can consume verified files in a
  bounded read-only sandbox without activating either checker phase.

## Intent

The merged PILOT-04 registry and normalized request/result contract identify an
exact external checker image and its limits, but Workstream has no external
service that can execute that contract. This chunk supplies that hidden service
boundary and the minimum real ART transport needed to test it. It does not
select a checker, route production work, persist a run, or change admission.

PILOT-00 established the usable isolation shape: administrator-registered
`runsc` on a dedicated Linux node, a separate gVisor sandbox with no network or
host socket, a non-root checker, no capabilities, a read-only root and bounded
CPU, memory, PIDs and scratch. Its privileged networkless Docker-in-Docker
container was a development harness, not the hosted deployment. The Rust
service introduced here is the trusted node component that alone may access the
container engine. Python product code never becomes a Docker launcher.

## Bounded change

### Allowed

- `.commitrail/changes/pilot04-external-checker-runtime.md` for this intent,
  acceptance, evidence and final reconciliation.
- `external_checkers/**` for one Rust workspace containing:
  - `workstream-checker-sdk`, the strict normalized checker wire types and
    result builder used by external images; and
  - `workstream-checker-service`, the long-lived Unix-socket service whose
    private executor resolves trusted cached images and owns Docker/runsc
    launch, health, deadline, bounded output and cleanup.
- A typed `ExternalCheckerExecutionAdapter` port under
  `backend/app/interfaces/**`, one Unix-socket client and explicit
  `ExternalServiceAdapterFactory` registration under
  `backend/app/adapters/checkers/**`, and the minimum bounded settings in
  `backend/app/core/config.py`. The adapter remains absent from product-flow
  composition roots.
- `backend/app/modules/artifacts/preparation.py`,
  `backend/app/modules/artifacts/submission_materialization.py`, the existing
  checker materialization API, and artifact adapter composition only to extend
  `ArtifactScratchManager` with the callback-scoped external material grant
  described below. This is the existing pre-admission
  `PreparedSubmissionBundlePreparationCommand` ->
  `PreparedBundleMaterializationService` ->
  `ArtifactPreparationService._process_prepared_submission` path; it neither
  requires nor fabricates a `Submission`.
- Focused Rust and Python tests and shared golden JSON fixtures for protocol
  parity, grant custody, factory construction, digest/cache selection, health,
  sandbox arguments, timeout/cleanup, output bounds and closed failure mapping.
  Register only the new modules and tests in the existing ownership and lane
  catalogues.
- `.github/workflows/backend.yml`, `scripts/test_lightweight_agent_gates.py`
  and the existing CI catalogue regression only to require the locked Rust
  workspace format and test commands in Backend's aggregate result and prove
  that its fan-in fails closed; no lane, service, timeout or Python selection
  changes.
- A bounded local probe under `experiments/pilot04_external_checker_runtime/**`
  only if needed to reproduce the real service request and its cleanup without
  adding a product caller or deployment surface.
- `docs/decision_0014_external_service_adapter_convention.md`,
  `docs/architecture_checker_framework.md` and the exact PILOT-04 lines in
  `docs/roadmap_status.md` for the delivered hidden mechanism and remaining
  cutover.

### Not allowed

- No project policy binding, F-020 activation guard, Workstream default checker,
  public route, CLI, scheduler, worker selection, durable run/lease/result
  storage or current pre/post caller activation.
- No deletion, bypass or parallel execution of the current pre-submit or
  post-submit catalogues. A later replacement PR must prove the complete new
  flow and remove both catalogues in one clean cutover.
- No database migration or durable ART lifecycle, and no `Submission`, TASK,
  routing, review, acceptance, contribution, compensation or payment mutation.
- No image build or pull, mutable tag or `latest` resolution, caller-selected
  platform, arbitrary host path, plugin discovery, global registration,
  service locator, fallback constructor or second transport.
- No Docker or containerd socket in a checker sandbox. Local `docker-dev` is an
  explicit development isolation result and can never be reported as hosted
  gVisor isolation.
- No deployment, PR merge, issue closure, held PILOT-05/PILOT-06/PILOT-09 work,
  test skip or CI weakening.

## Design and decisions

### Service and image identity

The typed Python adapter sends one already validated
`ExternalCheckerExecutionRequest`, one ART grant identifier and its binding
digest over a private Unix socket. The long-lived Rust service owns readiness,
Docker/runsc access, container creation and cleanup. Hosted readiness fails
closed unless the configured runtime is registered as `runsc`. Local
`docker-dev` is an explicit mode in configuration, health and the returned
isolation receipt.

The registry `image_digest` is interpreted as the exact OCI platform-manifest
digest. A trusted administrator-populated cache index binds repository plus
platform-manifest digest to one OS, architecture and observed Docker config
image ID. The service accepts no tag or caller-selected platform, never pulls,
and rejects a missing, ambiguous or substituted manifest, platform or config
identity. The receipt records the platform-manifest digest, OS/architecture,
config image ID, runtime and isolation mode. An OCI multi-platform index digest
is not silently treated as a platform manifest.

### ART-owned material grant

The only source of pre-submit material is the existing pre-admission preparation
path. `ArtifactPreparationService` has already hashed the received ZIP,
`SubmissionArchiveInspector` has rejected unsafe entries and produced the
server-computed manifest, and `PreparedBundleMaterializationService` has
consumed the exact TASK/AUTH preparation facts before it enters
`_process_prepared_submission`. Inside that existing callback lifetime,
`ArtifactScratchManager` may publish one opaque grant for the already projected
tree. No `Submission` exists or is invented.

The grant identifier has a closed grammar and names a private directory beneath
the manager's configured scratch root. ART writes a canonical grant manifest
with create-exclusive, descriptor-relative operations and binds:

- grant identifier and protocol version;
- external request digest and prepared generation/attempt identity;
- archive digest, byte count and semantic manifest digest; and
- every normalized file path, byte count, SHA-256 and executable bit.

The binding digest covers the canonical grant manifest. Python sends the opaque
identifier and binding digest, never a filesystem path. The service and ART are
configured with the same fixed absolute host scratch root on the dedicated
node; the Unix-socket service resolves `<root>/<grant>/workspace` itself, and
the Docker daemon receives that exact host path as a read-only mount. Config
validation rejects differing, relative, symlinked or permissive roots.

ART creates the root and projected entries without symlinks, seals directories
and files before publishing the manifest, and retains the live callback and
scratch reservation throughout service execution. The Rust service opens and
walks every component beneath the fixed root without following symlinks,
recomputes the manifest and binding immediately before container creation, and
rejects changed type, mode, size or digest. No untrusted actor can write the
private root; the checker sees only the read-only mount. The service terminates
the container before returning. ART then revokes the grant and uses the existing
scratch cleanup/TTL owner; missing, expired or changed grants map to
`material_unavailable`. This adds no durable artifact record or second cleanup
lifecycle.

### Protocol and failures

Shared golden fixtures exercise Python and Rust parsing, canonical JSON numeric
encoding, NUL rejection, strict extra-field behavior, byte ceilings, derived
request/result digests and normalized outcome shapes. The SDK constructs only
the existing `external_checker_result.v1` family. Python revalidates the result
against the original request after the service response.

The checker sandbox uses no network, a read-only root, non-root UID/GID, all
capabilities dropped, `no-new-privileges`, the verified workspace read-only, a
bounded no-exec temporary filesystem and the registry's CPU, memory, deadline,
output and derived PID ceilings. No socket, secret or other project material is
mounted. The service owns one uniquely labelled container, terminates it on
deadline or output violation, and removes only that container.

Transport failures use the existing closed result family: missing service,
runtime or cached image is `implementation_unavailable`; absent or invalid
material is `material_unavailable`; deadline is `deadline_exceeded`;
OOM/resource exhaustion is `capacity_exceeded`; malformed, mismatched or
oversized output is `invalid_output`. Completed findings remain work results.
No database transaction crosses the client call.

## Acceptance criteria

- [x] Rust SDK and Python accept identical golden
  `external_checker_request.v1` and `external_checker_result.v1` bytes and
  reject changed numeric canonicalization, bounds, NULs, extra fields and
  derived digests.
- [x] The explicit Python factory constructs only the configured typed Unix-
  socket adapter and rejects unknown, duplicate and identity-mismatched
  providers without plugin discovery or mutable global state.
- [x] Service health and hosted execution refuse missing or substituted runsc;
  local Docker mode is explicit and cannot claim hosted isolation.
- [x] Cache resolution binds one repository/platform-manifest digest to exact
  OS/architecture and config image ID; tags, index substitution, platform
  substitution, missing images and pulls are rejected.
- [x] A focused pre-admission test uses an actual `PreparedArtifact`, inspected
  ZIP and prepared-attempt facts to issue the callback grant without creating a
  `Submission`. The service accepts the exact request-digest binding while the
  callback is live, and missing, changed, symlinked, replayed-after-close and
  wrong-request grants fail closed with cleanup confirmed.
- [x] A real service request over the Unix socket runs a digest-pinned cached
  checker with the fixed ART root mounted read-only. The probe records user,
  capabilities, network, socket absence, root/input modes, concrete platform
  and image identities, enforced resource/output/deadline behavior and owned
  cleanup. Hosted-grade proof uses gVisor; local runc proof is qualified.
- [x] Completed and infrastructure outputs are bounded and Python revalidates
  them against the exact request. No infrastructure outcome can become a pass.
- [x] Product code does not invoke the adapter; neither catalogue, policy hash,
  database schema, public behavior nor default-checker behavior changes.
- [x] ADR 0014, checker architecture and roadmap distinguish the hidden runtime
  from later policy binding, default-checker implementation, caller-atomic
  intake, F-020 and clean removal of both catalogues.

## Risk and review routing

- Risk class: L1 with a high-impact untrusted-execution and private-material
  boundary.
- Required reviewers: architecture, security, reuse_dedup, qa, test_delta,
  product_ops, documentation, ci_integrity.
- Human review focus: service privilege separation; exact OCI platform/config
  identity; hosted runsc fail-closed; ART grant lineage, path confinement,
  TOCTOU and cleanup; no-network/no-socket sandbox; resource/output/deadline
  enforcement; Rust/Python parity; closed failure mapping; absence of product
  activation or a second scheduler/store/lifecycle.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline and owner map | Implementation began at merged registry main `3110353363547e603e7527a782467f95c00cb1f7`; final reconciliation merges current completion-delivery main `a51cf06ccb5ab85f2c41528855f537d4362ec26b` without changing the runtime sources | Complete | Later product selection and hosted deployment remain outside this chunk |
| Rust SDK and service | `cd external_checkers && cargo fmt --all --check && cargo test --workspace --locked` | Thirteen tests pass: shared Python fixtures, exact numeric/NUL/extra-field and Unicode controls, closed cache/runtime health, absolute request/response-frame budgets, bounded process/client-disconnect behavior, uncertain-create cleanup, directory inventory and missing-image outcome | Cargo and hosted CI remain required on the final reviewed commit |
| Numeric parity discriminator | The SDK numeric fixture test was also run against the reviewer's 2,000 finite-float Python corpus before restoring the checked-in representative fixture | All 2,000 canonical encodings match Python, including `203472594891988.12`, which the predecessor emitted as `203472594891988.13` | The retained fixture keeps representative boundary cases rather than the generated review corpus |
| Python transport and ART grant | Locked review environment Ruff plus `pytest -q tests/checkers/external/test_runtime.py` | Eight tests pass: cross-language fixtures, complete settings, typed health/execute/factory and cancellation, actual prepared ZIP callback grant, live-owner enforcement, semantic-manifest substitution and symlink rejection | Product caller is intentionally absent |
| Test and owner routing | Exact lane ownership regression, module boundary, test-structure and behavior-ownership validators | Pass after registering the new runtime test and two new Python owner paths | Full hosted lane evidence remains required |
| CI fan-in regression | `python3 -m unittest -v scripts.test_commitrail_contracts scripts.test_commitrail_contribution_paths scripts.test_commitrail_archive_batch scripts.test_commitrail_markdown_structure scripts.test_lightweight_agent_gates` | The lightweight gate requires the Rust runtime job in the aggregate dependencies and exercises success plus each failure/cancelled/skipped/empty/unknown result without weakening another required job | Full hosted lane evidence remains required |
| Real local service | Isolated registry `ws-pilot-backend-p04-registry` on loopback port `35104`; `/tmp/ws-pilot04-runtime-repair-probe.json` SHA-256 `873b7455be71a8a19a43d00a98dcb5a335b2627c317e1e4692183c0fa3ea7a42` was produced by the checked-in probe | Digest-pinned Linux/amd64 manifest `sha256:8fe601562e34c74bb90943c5ae5cdce12d51ac6e827cbd19113adfe77ffd59ba` and config ID `sha256:43d669716bb289c21d5cc926692dd21e564c339b65d849fef342e13b4a4a4114` returned `passed`; changed/expired grants mapped to `material_unavailable`, deadline to `deadline_exceeded`, oversized output to `invalid_output`; exact workspace and labelled-container cleanup confirmed | Explicit `docker-dev`/runc proof only; hosted runsc deployment and representative workload sizing remain unproved |

## Review findings

- Initial plan treated the runtime as a one-shot launcher and named no real
  cross-process ART transport. The scope now requires a long-lived Rust service
  and a request-bound callback grant owned by the existing scratch manager.
- Focused execution found that a fixed container UID could not read ART's
  owner-only sealed files. Configuration now binds one nonzero sandbox UID/GID,
  the service verifies that owner on every material entry, Docker uses the same
  numeric identity, and health/isolation receipts retain it.
- The executor originally observed output only after process exit and mapped
  every nonzero exit to capacity exhaustion. It now polls both private output
  files, kills on the registered ceiling, retains OOM-only capacity mapping and
  maps other malformed/crashed output to `invalid_output`, with cleanup owned by
  an RAII guard.
- Empty directories and manifest media type were initially implicit. Grant
  custody now binds exact directory inventory, and the trusted cache and receipt
  distinguish a bounded single-platform OCI/Docker manifest from an index while
  separately retaining the Docker config image ID.
- Final source inspection found the service read the grant manifest by pathname
  after validating only its parent. It now rejects symlinks, wrong owner/mode,
  oversized bytes and inode/device substitution before parsing the manifest;
  the retained real service probe passes through that stricter read.
- Docker repository input initially rejected only whitespace and `@`. Both the
  Rust cache and Python receipt now enforce a lowercase component grammar,
  numeric registry ports and no tags or option-like leading components before a
  repository is ever passed as a process argument.
- Independent process probes found that stdin delivery preceded the checker
  deadline, Docker control commands were unbounded, final output reads escaped
  their cap, and a partial Unix-socket frame monopolized the sequential
  service. The repaired service starts one deadline before image inspection,
  writes stdin nonblocking, bounds every Docker child and both output streams,
  observes client disconnect, requires confirmed container removal, and bounds
  socket reads and writes so a later client can recover.
- Independent grant substitution probes found that the low-level scratch
  publisher accepted caller-claimed preparation and semantic identities while
  the service compared only request and binding digests. Grant publication now
  requires the live `PreparedArtifact` callback and its server commitment; the
  service matches prepared generation, attempt, attempt digest, archive bytes
  and the recomputed canonical semantic manifest to the normalized pre-submit
  request. Post-submit grants remain unavailable until a real post-submit ART
  custody owner exists.
- Cross-language probes found that default `serde_json` rounded integers above
  `u64` and Rust counted UTF-8 bytes where Python counts finding characters.
  The locked Rust JSON parser retains numeric lexemes, shared number goldens
  cover large integers, decimal/exponent forms and negative zero, and finding
  character ceilings now match Python while the aggregate byte cap remains.
- A later cross-language float corpus found a distinct shortest-decimal choice:
  Python retained `203472594891988.12` while Rust displayed the same IEEE-754
  value as `203472594891988.13`. The SDK now selects the first correctly
  rounded significant-digit representation that round-trips to the original
  bits before applying Workstream's fixed-decimal encoding; the 2,000-value
  review corpus and retained representative boundaries agree with Python.
- Socket timeouts were initially per-system-call, so a client sending one byte
  before each timeout could monopolize the sequential listener. Request header
  plus body now share one absolute frame deadline, response header plus body
  receive a fresh absolute deadline after checker execution, and the trickle
  regression proves the service returns within the request budget and serves a
  healthy connection without waiting for the trickle schedule to complete.
- An actual prepared ZIP containing both `src.txt` and `src/main.txt` exposed
  depth-first grant inventory ordering where the typed request requires one
  global normalized-path order. ART now sorts its descriptor-walked file and
  directory identities before exact comparison and publication; the retained
  callback test proves the root file and nested file share one valid grant.
- Hosted Agent Gates found that the lightweight workflow regression still
  expected the predecessor aggregate dependency list and did not provide the
  new Rust job result to its fail-closed shell probe. The regression now binds
  the exact dependency and rejects every non-success Rust result alongside the
  existing preflight, semantic-lane and CLI requirements.
- Hosted schema contracts found that the unselected external factory was
  assembled inside its concrete Unix-socket module rather than the existing
  CHECKER composition root. Factory registration and settings mapping now live
  in `app.adapters.checkers`; the architecture regression owns that fourth
  root and rejects a concrete checker adapter or factory constructed elsewhere.
  The checked-in local probe imports that owner root as well, with no
  compatibility export left in the concrete transport module.

## Reconciliation

- Current-source reconciliation: branch `codex/pilot04-external-runtime`
  started at merged PR #521 and merged current main
  `a51cf06ccb5ab85f2c41528855f537d4362ec26b`; the incoming CLI approval,
  inspection, hidden routing-outcome and completion-delivery files, ownership
  metadata and roadmap statements are preserved.
- Parallel-lane reconciliation: PILOT-02 owns task-import product and ART source
  code. Its migration is authored separately by this lane as the next linear revision after merged routing
  revision 0030 and is not part of this runtime PR. No PILOT-02 worktree is edited here.
- Remaining PILOT-04 work: one Workstream default checker implementing all four
  confirmed blocking behaviors, project image policy binding, full pre/post
  caller integration, caller-atomic admission, durable attempt/isolation
  receipt custody, F-020, public PILOT-12 surface and clean removal of both
  catalogues. Summary and attestation remain warnings only.
