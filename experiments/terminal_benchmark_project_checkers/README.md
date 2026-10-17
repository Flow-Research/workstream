# Terminal benchmark project-checker runtime proof

This experiment supplies the real Docker/gVisor evidence required by the
bounded WS493 checker change. The pull-request workflow is the supported proof
environment: it creates an owned XFS project-quota backing file, mounts it at a
distinct run-named path under ephemeral host `/run`, starts the
trusted networkless DIND harness, registers the pinned `runsc` runtime, builds
the checker from the exact pull-request head, and runs only the public
`ledger-reconcile` package.

The matrix first pauses the trusted Docker wrapper after a labeled builder has
been created and inspected but before the wrapper returns to the Rust service.
It kills only the recorded service PID, observes adapter failure and live ART
workspace unwind, releases the wrapper, and verifies restart cleanup without
removing an unowned control. Restart readiness requires both a new no-follow
socket identity and the exact read-only service health receipt, so the orphan
sweep has completed before the absence check. A second request must build successfully, reject
the unchanged starter with exit 1, and pass three fresh reference containers
with stable observations.

Preparation is the only phase that uses external networking. DIND and all
product sandboxes are externally networkless during execution. The trusted
checksum-pinned crane binary first acquires exact builder/base OCI layouts on
the host, validates the single manifest and every referenced blob, then pushes
them from the externally networkless DIND only to its fixed loopback registry.
Unexpected, non-regular or over-budget layout entries fail before transport.
The trusted cache warmer uses DIND's host network only to read that registry;
the outer DIND has no external interface. Builder and oracle continuation
containers use `--pull=never --network none`; every
product container receives no Docker socket and is inspected for the fixed
runtime, user, capabilities, root mode and mounts. The builder replaces the
pinned debug image's declared `/busybox` volume with a bounded no-exec tmpfs,
so Docker creates no anonymous volume outside the container cleanup path. The
host shell makes no offline claim.

The workflow also proves the production 384 MiB writable-layer option on the
owned XFS backing store: an allocated and fsynced 320 MiB write succeeds and an
allocated 400 MiB write fails. It stages only the fixed nonsecret evidence
allowlist through no-follow file descriptors. Cleanup removes the exact DIND
and run-owned checker/registry transfer image aliases, removes the crane
archive and binary, validates the head-and-run-bound no-follow ownership marker
before deleting the run-named `/run` service control directory, unmounts XFS,
detaches the loop device, deletes raw state, and adds a verified cleanup receipt before
upload. A preexisting, substituted or ambiguously owned control path is never
deleted and makes cleanup fail. The matrix validates the same custody before
its first control-file access and again before each service start. The atomic
installation also no-follow copies the exact Cargo service output to a
root-owned `0555` file under `/run` and does the same for the fixed Docker
wrapper; the marker binds both SHA-256 values and every custody check rehashes
both before use. Preparation also creates a copied-executable Python 3.12 venv
inside the root-owned control tree, synchronizes the frozen backend dev lock
with the pinned `uv`, and executes a fixed-UID import probe before POST. Its
Python sources are a read-only, no-follow copy of only the Git-tracked backend
application, two fixed proof drivers and public package, bounded to 4,096 files
and 64 MiB. The expected HEAD tree selects the files, and every copied source
must match its HEAD blob. The proof revalidates the head-bound exact inventory,
ownership, modes, sizes and hashes before the matrix and each service start.

The evidence, launch-source and matrix-reducer tests require no Docker
resources:

```bash
cd experiments/terminal_benchmark_project_checkers
python3 -m unittest -q test_verify_evidence test_runtime_proof
PYTHONPATH=../../backend:. ../../backend/.venv/bin/python -B -m unittest -q \
  test_execute_post_contract
```

Do not run `proof.sh` on a shared development host. It is intentionally bound
to an ephemeral `ubuntu-24.04` GitHub runner with the resource and timeout
ceilings in `.github/workflows/terminal-benchmark-project-checkers.yml`. The
result is development evidence for the image and service. It is not hosted
deployment or registry-activation evidence.
