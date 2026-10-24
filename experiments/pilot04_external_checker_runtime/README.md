# PILOT-04 external checker runtime probe

This fixture is only for the bounded local service proof. Its image is pushed
to an isolated local registry so Docker exposes an OCI repository digest. The
Rust service starts it by that exact platform-manifest digest in explicit
`docker-dev` mode, with no network, a read-only root, no capabilities, numeric
UID/GID 65532, bounded resources, and the callback-scoped ART workspace as its
only read-only material mount.

The checker returns the published `external_checker_result.v1` envelope. It
fails its own result if the expected verified file differs, effective
capabilities are nonzero, a Docker socket exists, the root is writable, or a
network connection succeeds. This small Linux fixture does not establish
hosted gVisor readiness, representative checker sizing, or product routing.

`run_selected_post_probe.py` composes the same service with the selected POST
owner against an already migrated isolated PostgreSQL database. It registers
the supplied platform-manifest digest, builds a real locked policy, creates an
immutable Submission through the existing TASK/ART path, mounts the verified
archive through the callback-scoped POST grant, and requires the normalized
result, isolation receipt, database finalization, and workspace cleanup. The
database must be disposable and independently cleaned by the caller; the probe
does not create or drop it.

`run_selected_end_to_end_probe.py` exercises PostgreSQL and MinIO through
selected PRE admission, immutable Submission/initial dispatch and production
request/completion handlers. It requires default-secret rejection and an actual
external PRE image rejection to preserve `in_progress` with no new Submission.
The latter uses `project-rejected.txt` as a fixture project rule, implemented
only inside the image. It also tests unavailable-service recovery through fresh
verified bytes and restarted completion delivery with exact replay. This hidden
owner drill does not provide public contributor upload/CLI, false-guide
activation or hosted gVisor deployment proof. Run it through the isolated-test
runner so owned database, role and MinIO cleanup are checked.

The companion `run_public_journey_probe.py` starts with public project/guide
creation, original synthetic Markdown bytes and two task examples. The public
upload dispatches real Celery setup. Its explicit `guide_worker` entry point
selects a recorded inference adapter through the existing typed runtime port;
production composition has no test switch. The adapter reads the actual scoped
ART document grant and checks exact bytes, normalized examples and correction
feedback. Stored source commitments and the runtime-observed canonical input
hash must agree. This proves integration, not model reasoning or hosted inference.

The manager configures review/revision policies through public conditional PUTs,
reads the proposal, separately approves PRE and POST, and activates the exact
publicly discovered context. Finance creates and publishes ContributionPolicy
through its public API. The human-review branch also exercises a manual setup
correction, successor discovery, predecessor preservation and request replay.
Infrastructure prerequisites are the immutable PRE/POST image registrations,
local Flow-compatible human/service identities and, for the compensated branch,
a project points unit and existing AUTH-governed adapter binding. They do not
inject guide, proposal, policy, Task, Submission, acceptance or award facts.
Locally signed tokens do not certify the hosted Flow Identity service.

The companion uses a live loopback API,
the public manager guide activation, project submitter grant, and task lifecycle, contributor ZIP
preparation and canonical Submission POST, and a real Redis-backed prefork
Celery worker and Beat scheduler for artifact and outbox delivery. The isolated
run sets the supported artifact scan interval to 10 seconds and requires a
retained scheduler audit before public intake; no manual scanner dispatch can
make a preparation ready. After a bounded timeout, the probe may publish the
exact pending verifier for private diagnosis and then unconditionally fails.
OUTBOX keeps its production 60-second Beat scan. The probe only observes its
ordinary first delivery and due retry through retained project-scoped worker
attempts and dispatch decisions; it publishes a duplicate message only after
acknowledgment to prove replay refusal.
It checks actionable intake
failure from both Workstream defaults and the selected external PRE image,
verified immutable admission, a selected POST failure routed to
`needs_revision` and an exact public replacement, and passing POST routing under
both locked review modes. It checks exact false-mode FinalAcceptance and
submitter contribution/award evidence and replay. The false-mode completion
first runs while the acceptance lifecycle is legitimately in shadow, requiring
one known safe OUTBOX retry with no governed effects. The probe stops the
owned prefork worker, moves the authorized lifecycle to live, then restarts a
fresh worker while Beat remains active; the same due event must succeed exactly
once through ordinary scheduled delivery. It then moves the authorized
lifecycle through draining, disabled, and shadow, submits a second public task,
and waits for its real selected POST result and first known non-live completion
retry. With the worker stopped, a Flow-linked access administrator publicly
revokes the fixed routing service link. The lifecycle returns to live before a
fresh worker starts; scheduled redelivery must close as an unknown invocation,
with no second-task routing, acceptance, contribution, or award and no change
to the first task's accepted evidence. This exercises revocation after checker
I/O, not a fabricated checker result or direct database mutation. The phase-aware
`post-rejected.txt` rule lives only in this small checker fixture. The drill
must keep guide activation guards and database triggers
enabled. PostgreSQL, MinIO, Redis, the digest registry, Rust checker service,
and API/worker/Beat processes belong to one disposable local run; the isolated-test
runner owns database/role/MinIO namespace cleanup. This still does not certify
hosted gVisor, arbitrary checker quality, live human review, or deployment.

Run from `backend/` on a dedicated Linux x86-64 KVM host with disposable
PostgreSQL, MinIO and Redis. Provision the [Smol node](../../external_checkers/README.md#smol-microvm-engine)
with `maximum_parallel=1`, the pinned trusted intake image and this directory's
project fixture image. Both are operator-provisioned cache entries; no registry
or Docker socket is needed by the API/worker or running guests. Build the Rust
service and native guest from this checkout. The probe takes the exact node
configuration and checks both typed adapter identities before starting services.

The public drill deliberately injects faults. Start `public_node_faults.py` on
the host against **only the dedicated drill unit**, with `--node-config`, `--unit`
and `--root <work-dir>/node-control`, plus `--owner-manifest <custody.json>`.
Run it with the repository root on `PYTHONPATH`. The fresh control directory
must be mode `0700` with no symlink or writable ancestor; control files are
mode `0600` and accessed relative to its retained directory descriptor. It installs a pinned test-only Smol wrapper,
records exact project launch attempts and preserves trusted-intake availability.
It restores the original config and restarts that same unit on SIGTERM/exit.
Keep its parent supervisor alive and always terminate/wait for it in a shell
`trap` after the probe, including failures. Propagate a nonzero supervisor exit;
require its `supervisor-cleanup.json` receipt, matching original config hash and
empty owned-resource inventory. The receipt must also confirm the exact foreign
fixture VM/disk/cgroup/process is gone. The fixture uses exact-name noninteractive
`--force` deletion only after checking its label. Never target a shared production node.
The operator supplies a private custody manifest from independently verified
build/provisioning records. It contains `unit`, absolute `config`, `socket` and
`executable`, the preserved `owner`, `config_sha256`, the complete original
`node_config`, `service_sha256`, `smol_sha256`, `guest_sha256`, `wrapper_sha256`
and the clean `source_tree` commit. The supervisor checks live unit PID/argv,
delegated cgroup, configuration, owner and binary hashes before changing anything.
The probe receives that same manifest read-only through `--expected-custody`;
it permits only the recorded test wrapper substitution and compares the host
validation receipt. Do not generate expected binary hashes from an unverified
node and call that independent build custody.

The API proof entry point records genuine intake readiness/cleanup acknowledgements;
it delegates to the production adapter and is never imported by production.

```sh
PYTHONPATH=.:tests:.. .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /tmp/guide-journey-cleanup.json --timeout-seconds 1500 \
  --lane guide_journey -- \
  .venv/bin/python ../experiments/pilot04_external_checker_runtime/run_public_journey_probe.py \
  --image-reference 'workstream-test/public-journey@sha256:<manifest-digest>' \
  --node-config /absolute/private-node/service.json \
  --expected-custody /absolute/private-node/custody.json \
  --broker-url redis://127.0.0.1:<owned-port>/0 \
  --work-dir /absolute/private-guide-journey
```

Use a new metadata path, work directory and private broker for each run. The
isolated runner owns database/role/bucket/prefix cleanup. The probe stops its API,
worker and Beat; the host supervisor owns node configuration and restart. Remove
only the drill's own infrastructure after verifying both cleanup receipts. Do
not remove retained product evidence or use broad container/volume pruning.

The expanded cases cover authenticated upload readiness before the last byte,
disconnect cleanup, no unauthenticated allocation, default-only and two ordered
project PRE bindings, stopping at the first failed binding, bounded pre-launch
retry/exhaustion, controller loss, same-key infrastructure replay and fresh-request
recovery. POST outage uses the existing **public Operator discovery/retry routes**
and observes the next durable generation before governed acceptance. The prior
non-live routing retry remains a separate trial. Check the final JSON cases and
`cleanup_complete`, `database_cleanup_complete` and `minio_cleanup_complete`;
a partial run is not evidence for its unexecuted cases.

The final JSON records source/image identities, public receipts, exact selected
attempts and governed outcomes. Private logs contain diagnostic metadata, never
provider credentials. The Flow signer and guide inference are explicit fixtures;
this proves self-hosted execution through real API/PG/MinIO/Celery owners, not
production Flow, live model quality, native AWS S3 activation or hosted deployment.
