# PILOT-00 offline gVisor build probe

This experiment builds a digest-pinned sample Dockerfile with maintained Kaniko
inside gVisor, then loads the resulting image tar and runs a separate oracle in
a second gVisor sandbox. Both sandboxes have external networking disabled and
receive no Docker or containerd socket. The builder is a non-privileged Docker
container with four capabilities inside gVisor; the oracle runs as UID 65532
with no capabilities and a read-only root filesystem.

The Kaniko builder runs as root inside gVisor because it needs filesystem
ownership operations. Its Docker container is not privileged: all capabilities
are dropped and only `CHOWN`, `DAC_OVERRIDE`, `FOWNER` and `SYS_CHROOT` are
added inside the sandbox. The script records those facts before each build.

The script uses a privileged, networkless Docker-in-Docker container only as a
development harness because an unprivileged user cannot register `runsc` with
the host daemon. That outer harness is trusted infrastructure and is not proof
that the whole deployment is privilege-free. A hosted launcher should instead
run on a dedicated Linux execution node whose administrator has registered `runsc`.

On Linux x86_64 with Docker available to the current user:

```bash
PILOT00_RUN_ID=repro ./experiments/pilot00_gvisor_offline/probe.sh all
PILOT00_RUN_ID=repro ./experiments/pilot00_gvisor_offline/probe.sh cleanup
```

The bounded shell regression for daemon readiness uses stubs and requires no
Docker resources:

```bash
./experiments/pilot00_gvisor_offline/test_probe.sh
```

The WS493 project-checker proof reuses only the harness boundary. It sets
`PILOT00_HARNESS_ONLY=1`, selects the service's fixed `runsc` key with
`PILOT00_RUNTIME_KEY=runsc`, supplies an absolute bind-backed Docker state path
with `PILOT00_DIND_STATE_DIR`, and mirrors `PILOT00_STATE_DIR` at that same
absolute path inside DIND with `PILOT00_SHARED_STATE_PATH`. These inputs leave
the default sample matrix and named-volume behavior unchanged. Harness-only
mode is valid with `prepare` and cannot run the sample `all` action.

`prepare` is the only network-using phase. It downloads the exact gVisor
release, pulls digest-pinned harness/builder/base images, and warms the base
cache. The harness itself starts with `--network none`. `run` mounts the sealed
cache read-only and produces JSON, logs, launch inspection and sampled resource
statistics beneath `/tmp/ws-pilot00-<run-id>/results/`. `cleanup` removes only
the labeled container and volume for that run ID and retains the evidence.

`PILOT00_RUN_ID` accepts a lowercase letter or digit followed by at most 30
lowercase letters, digits or hyphens. The optional `PILOT00_EVIDENCE_ID`
accepts an ASCII letter or digit followed by at most 47 ASCII letters, digits or
hyphens; its default is the UTC timestamp form `YYYYMMDDTHHMMSSZ`. Both values
are rejected before their corresponding resource or evidence path is used.
Harness startup makes 45 bounded inner-daemon readiness attempts and reports a
specific readiness failure before any runtime inventory query.

The probe also distinguishes an intentional Dockerfile exit from cache-miss,
deadline, memory and output-disk failures. It is deliberately small; its
measurements are a feasibility floor, not Terminal-Bench production sizing.
The BuildKit and base-index entries in `tool-inputs.env` bind the alternatives
examined by the engineering result; the executable success path uses the
platform-specific base manifest and Kaniko pins.
