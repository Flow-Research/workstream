# Terminal Systems checker implementation

These are project-owned images. They use the standard request/result protocol
and verified read-only material mounted at `/work/input`; they do not import
Workstream, modify the shared Rust service, or depend on the five initial tasks.

## How the parts fit together

The project guide defines the work. Setup proposes PRE and POST check
specifications from that guide; engineering implements the project images and
the PM approves their policy bindings. Setup does not decide revision limits or
task lifecycle rules.

Workstream supplies shared budgeted model access and stores verified evidence.
The external Rust service supplies isolated execution. This project's Python
POST image decides what to inspect and how to assess it against the project
requirements. A different project supplies its own rules and image.

Here, a **trial** is one isolated execution of submitted code, such as a build
or test run. The `trial_*` modules implement its transport, limits, execution,
and evidence handling; they are not separate services or product lifecycles.
`post/qualification/runtime_package` is an engineering test fixture, not the
real project guide or a live pilot task. The runtime qualification limits below
remain distinct from a completed live project journey.

## Source specification

[`setup-handoff.json`](setup-handoff.json) retains the actual final reviewed
setup requirements and capability suggestions from compilation
`01a165a2-7cde-7277-b789-7013d7a2088d`. Its source block identifies the unchanged
guide and full result hash. This is an engineering handoff, not an approved
policy or evidence that any proposed capability is already registered.

## PRE image

The `terminal_systems.package_intake@v1` capability supports two distinct locked
configurations:

| Configuration | Evaluation |
|---|---|
| `{"check":"package_layout"}` | Required regular files and directories directly at the package root; useful extra material is allowed. |
| `{"check":"metadata_contract"}` | The documented TOML format, values, declared file/directory types, contained paths and argument-array shape. Commands are never executed. |

Bind each original requirement separately. Each binding uses its own exact
configuration hash and execution budget. The same image may serve both; this
does not collapse the two invocations. The supplied material tree is already
verified/extracted by ART and the shared runner. Project checks inspect its
actual entry types; they do not repeat archive extraction or custody checks.

From the Workstream checkout:

```bash
python3 -m unittest discover -s pilots/terminal_systems/checkers/pre -p 'test_*.py' -v
./scripts/checker-image pilots/terminal_systems/checkers/pre
```

The image has no network, host socket, secrets or writable submission mount.
Python and its TOML parser are packaged in its pinned base. No Rust or backend
package is needed inside the image. Its metadata parser has a 4 MiB execution
capacity; exceeding it produces `capacity_exceeded`, never a contributor size
violation. Platform upload limits remain owned by Workstream.

The sample directories prove structural intake behavior only. Their short
documents and environment placeholders are explicitly not completed task
packages, semantic review evidence, or a substitute for the real project journey.
The image build excludes samples and tests. Findings contain fixed messages and
safe project-relative paths, never raw TOML, commands or exception traces.

Publish through the same command with `--publish --account-id` and the intended
AWS account. Its default destination is `workstream-checker-pre-terminal-systems`
in `eu-north-1`. The reviewed implementation was published on 2026-10-23 as:

```text
094032936130.dkr.ecr.eu-north-1.amazonaws.com/workstream-checker-pre-terminal-systems@sha256:24d8d0ad46e1f10c85d8883ddd29bcc7708501e560df067cdd3fdab34785a83c
```

The publisher pulled that exact manifest back and passed all seven samples with
config image ID `sha256:85f32d02a7febd1b476810f5cb7cd0b6056a9b29c377f78e492b005b23a81aef`.
The local rehearsal registry entry is `01a1665b-892e-7a56-a511-6fd9be45a60a`,
created through the Operator CLI. These are image publication and registry facts,
not deployment or activation. Runner cache provisioning, corrected proposal
approval and activation remain separate operations. Local `docker-dev` samples
do not establish the intended hosted Smol isolation.

## POST prerequisites

POST engineering is in progress against the retained six model and two execution
suggestions; those counts describe the historical handoff, not an eligibility
set or approval. The project agent now has strict material/rubric validation, a
bounded source-cited plan, invocation-local model-session and execution-socket
clients, protected build/state projections, and receipt-bound runtime and author
assessment cores. Controlled interruption now inherits the verified third
reference workspace; restart inherits its exact retained export, followed by
the full verifier. These steps expose only protected verification material,
while incomplete repair still starts fresh. A failed restart verifier contradicts
an all-pass model assessment; a documented signalled interruption is allowed.
The [repair record](../../../.commitrail/changes/terminal-systems-repaired-recovery-trial.md)
records local subprocess and false-pass proof. This changes the projection
digest: use a new immutable image/projection registration and approved binding
for runtime qualification; existing locked bindings remain historical.
The shared runner implements generic offline image building
and trials in Smol sibling microVMs, with resource, cancellation, cleanup and
recovery controls. Native build `b2ce3fa45` passed controlled-provider KVM
composition 013: trusted intake, two verified ART trial receipts of 17 steps,
four controlled model effects and replay without new calls. Both builder and
candidate-step paths checked the shared syscall filter. Direct KVM proof 36
also qualified distinct predecessor custody and guest resource ceilings.
Exact pins, cleanup and limits are in the
[qualification record](../../../.commitrail/changes/terminal-systems-project-checkers.md#repaired-confinement-and-resource-qualification-on-real-kvm).
Active nested caller cancellation, exact child VMM death and controller death/restart
also passed in physical cases 026–028 at test proof source `8012f2792`, using the
same native build. Each reached a filtered workload, admitted no trial receipt or
false completion, cleaned owned VM/relay resources and reused both admission slots.
See the [scoped interruption evidence](../../../.commitrail/changes/terminal-systems-project-checkers.md#active-nested-interruption-qualification-on-real-kvm).

The earlier gVisor composition at `3e67d39c8` applies only to that historical
implementation. Smol is the deployment target, with no Docker/runsc trial
fallback. These native proofs use a qualification package, not the real
Terminal Systems contribution journey. Hosted Smol composition and its scoped
AWS proof are tracked separately in [PR #692](https://github.com/Flow-Research/workstream/pull/692);
that owned baseline passed with its disclosed fixture identity. Live-provider/model-quality
proof and full project qualification remain separate. The real Terminal Systems
project has no qualified POST binding or activation. Registration and guide
authority in a model-only engineering fixture do not establish that project.

[`post/model/execution-rubrics.json`](post/model/execution-rubrics.json) is an
exact semantic projection of that historical handoff. Its
`post_submit_capability_gap` disposition records the source proposal's state; it
is not a current policy binding or a claim that the implemented trial runtime is
unavailable. Qualification constructs a separate typed specification declaring
the outer `isolated_execution/current_runner`, nested
`nested_sandbox/trial_proxy`, and receipt assessment
`model_service/model_proxy` dependencies. A future #555 correction must review
that current dependency shape before it can bind or approve it.

The locked POST configuration schema must declare all six flat trial selectors:
`trial_profile_id`, `trial_profile_version`, `trial_profile_digest`,
`trial_projection_id`, `trial_projection_version`, and
`trial_projection_digest`. They are selected together and resolved against the
exact operator-provisioned authority manifest entry already bound to the
registry entry, checker image and configuration hashes. Missing, partial,
unknown or noncanonical `trial_*` fields fail closed. Final qualification
evidence must carry the exact image digest, profile/projection digests, runtime
configuration and engine/platform identities, offline builder/cache/base
identities, canonical retained receipt digest and ART binding identities.

The project image and production service boundary have a separate explicit
Docker-development qualifier:

```bash
python3 external_checkers/workstream-checker-service/tests/terminal_systems_post_composition.py \
  --service external_checkers/target/debug/workstream-checker-service
```

On 2026-10-23 it rebuilt the pinned Dockerfile offline from locally verified
base layers (60.29 KiB context), selected project image ID
`sha256:cd11dc1125a96527641cf9a1e5c99d947b3566cb07bb51bbae086d369476126d`,
and passed an assessed v2 model-session request through the production Rust
service. The qualifier checks exact immutable image selection, verified
read-only material, network-disabled/read-only/capability-free containment,
invocation-local socket mounting, and container/relay cleanup. Its result
deliberately records `durable_art_proven=false`, `trial_proven=false`, and
`runsc_proven=false`; the PostgreSQL/MinIO custody journey and PILOT-00 runsc
trial qualification are distinct evidence lanes.

The composed qualifier is an explicit operator test on a separately provisioned
Linux/KVM node. It uses the native Smol service, sealed local images/cache and
isolated PostgreSQL/MinIO endpoints. It does not alter shared services or pull
images. Provision a delegated service cgroup and build the service, guest and
trusted launcher from the same clean commit. The required static ext4 tool is
built with the generic [filesystem tool helper](../../../external_checkers/workstream-checker-service/scripts/build_smol_filesystem_tool.sh).

```bash
python3 external_checkers/workstream-checker-service/scripts/qualify_terminal_systems_smol.py \
  --expected-head "$(git rev-parse HEAD)" \
  --expected-tree "$(git rev-parse 'HEAD^{tree}')" \
  --node-config /absolute/prepared/node.json \
  --build-manifest /absolute/prepared/build-manifest.json \
  --service /absolute/prepared/workstream-checker-service \
  --python /absolute/backend-venv/bin/python \
  --root /absolute/fresh-composition-root \
  --evidence /absolute/fresh-evidence-directory \
  --platform-identity sha256:<verified-platform-identity> \
  --cache-digest sha256:<sealed-cache-manifest> \
  --checker-digest sha256:<project-image-platform-manifest>
```

Supply the isolated-test PostgreSQL and MinIO environment documented in the
backend testing guide. The build manifest records `source_head`, `source_tree`
and a `binaries` map with the SHA-256 identities of `service`, `guest`, `launcher`
and `filesystem_tool`. The wrapper checks those against the actual files and
node pins before and after execution. Source and prepared node configuration
must remain unchanged. Missing prerequisites fail the run; they never skip it.
Logs and failure status are retained. Success requires the exact completed test,
no skips or failures, database/MinIO cleanup, verified trial/model custody,
zero extra model calls on replay and removal of owned VM resources.

The test uses `post/qualification/runtime_package`: a deliberately small package
with a pinned Dockerfile, reference, negative mutations, interruption and restart
procedures. Its explicit 2 GiB total trial disk ceiling covers pinned builder,
cache, material and export copies as well as mutable work. The generic runtime
checks that aggregate budget; it does not add an implicit tool allowance.
This is controlled-provider image/service/runtime/custody evidence, not a
project task or #555's public activation-to-contribution journey. Historical
runsc results do not qualify the Smol target. No live provider is called.

The author-accuracy draft adds `reproduction_procedure_unavailable` for the
narrow case where an absent or ambiguous exact procedure prevents authenticated
comparison. It reports incomplete coverage; it does not call healthy runtime
infrastructure unavailable, invent an unobserved discrepancy, add a guide duty,
or reuse another requirement's finding. The retained setup handoff remains
byte-for-byte historical. The #555 owner must include this exact draft finding
and image contract in a fresh PRE/POST proposal for review before any binding or
activation.

The shared model-account owner retains provider budget/effect custody and the
durable receipt resolver. TASK/ART/CHECKERS owners supply authenticated revision
context and predecessor material; project code does not query their private
tables. Credentials stay outside the sandbox, nested submitted code receives no
relay sockets, and all model/trial unavailability remains infrastructure rather
than a contributor finding. Do not publish passing substitutes or treat this
engineering checkpoint as the live contribution journey.
