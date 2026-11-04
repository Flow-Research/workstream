# Build, test and publish a project checker

Keep the checker in its project's repository, with its own Dockerfile,
dependencies and samples. The shared Rust runner does not contain project rules.
The image can use any language that implements the
[external checker request/result contract](../architecture_checker_framework.md).

From a Workstream checkout, build and test it:

```bash
./scripts/checker-image /path/to/project/checkers/pre
```

To also publish the tested image:

```bash
./scripts/checker-image /path/to/project/checkers/pre --publish --account-id 123456789012
```

The default AWS region is `eu-north-1`. The project name and phase in
`checker.json` determine the repository:

- `workstream-checker-pre-<project>` for `pre_submit`;
- `workstream-checker-post-<project>` for `post_submit`.

Each release uses a unique tag. Workstream registration and policies use the
verified platform-manifest **digest**, never that tag. Releasing another version
does not require another repository or a Workstream source change or rebuild.

## Prerequisites

Install `uv` and Docker using the [developer setup](developer-setup.md).
Publishing requires Docker API 1.46 or later for an explicit single-platform
[push](https://docs.docker.com/reference/cli/docker/image/push/).
The command uses the locked backend environment solely for the existing public
checker validation contracts; it starts no API, database or Celery process. The project
image itself does not depend on the Workstream backend or Rust SDK.

Docker must use a local Unix socket so the sample bind mounts resolve on the
same machine. The default target is `linux/amd64`; use `--platform linux/arm64`
when that is the runner's platform. Dry run makes no AWS calls. Building may
download base images and dependencies; sample execution has no network.

Publishing additionally requires the AWS CLI, an authenticated AWS profile or
role, and the selected private ECR repository. `AWS_PROFILE` selects the AWS
identity in the usual way. `--account-id` must match the intended account; the
command refuses mismatched credentials before login or push. Set up the repository once, for example:

```bash
aws ecr create-repository --region eu-north-1 \
  --repository-name workstream-checker-pre-terminal-systems \
  --image-tag-mutability IMMUTABLE
```

The publisher needs repository inspection, authorization-token, image upload,
manifest read and image pull permissions. It does not create repositories,
change IAM or install credentials into the image. ECR authentication uses a
private temporary Docker configuration that is removed when the command ends.
Builds and samples use a Docker client configuration containing only the host
plugin search paths (including user-installed Buildx), so host proxy
credentials and registry logins are not inherited. Base images must be locally
cached or publicly pullable; private-base authentication is outside this command.
See AWS's [private image push instructions](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html)
for the required account setup.

## Project descriptor

Put `checker.json` beside the Dockerfile. For example:

```json
{
  "project": "terminal-systems",
  "capability_id": "terminal_systems.package",
  "capability_version": "v1",
  "phase": "pre_submit",
  "configuration_schema": {"type": "object", "additionalProperties": false},
  "input_schema": {"type": "object"},
  "resources": {
    "cpu_millis": 500,
    "memory_bytes": 134217728,
    "deadline_ms": 30000,
    "maximum_output_bytes": 32768
  },
  "samples": [
    {
      "name": "complete-package",
      "directory": "samples/complete",
      "expected": "passed",
      "expected_codes": [],
      "configuration": {},
      "input": {}
    },
    {
      "name": "missing-required-file",
      "directory": "samples/missing-file",
      "expected": "failed",
      "expected_codes": ["terminal_systems.required_file_missing"],
      "configuration": {},
      "input": {}
    }
  ]
}
```

This is a descriptor example, not a supplied Terminal Systems implementation or
an approved project policy. Choose the schemas, limits, findings and representative
samples from the actual project's requirements. Include at least one passing and
one failing sample. Every failing sample names its expected finding codes; a crash,
infrastructure failure, unrelated error or incomplete coverage cannot satisfy it.
Expected codes match the complete set of returned finding codes, including warnings.

Samples are directories inside the build context. Their contents are copied to
private scratch, then mounted read-only at `/work/input`. Links and special files
are refused. The development harness bounds each sample to 128 MiB and 10,000
entries; these are test-harness ceilings, not project submission policy. Exclude
samples, local outputs and credentials from the built image with the project's
`.dockerignore`; only the implementation and its runtime dependencies belong in
the image. Images must not declare `VOLUME` mounts or an active `HEALTHCHECK`.

The image reads one normalized request from stdin and writes one normalized JSON
result to stdout. Protocol identities are synthetic for these tests; no registry,
assignment, Submission or artifact record is created. Material digests identify
the copied sample inventory; archive size/identity fields are synthetic and do
not prove real ZIP custody. The registered result contract remains the standard
normalized Workstream result. Schemas and digest values are validated through
the existing public CHECKERS contracts.

## What success proves

The command builds once and tests the immutable local image ID. Each test runs
as non-root, without network, with a read-only root and input mount, no Linux
capabilities, no privilege escalation, finite CPU/memory/PID limits, a bounded
temporary filesystem and one aggregate output/time budget covering image inspection,
creation, execution, state inspection and cleanup. Emergency cleanup after budget
exhaustion cannot qualify a sample as passed. Container cleanup must be
confirmed before proceeding. Image compatibility testing does not execute the
Rust service's ART grant checks or the live Workstream journey.

Default isolation is explicitly reported as `docker-dev`. For a host with gVisor
installed, use `--isolation gvisor`; it requires Docker's `runsc` runtime and
never falls back to `runc`. Publishing a `docker-dev` result does not establish
hosted gVisor readiness. Qualify on the intended execution platform before
approving a production policy.

After samples pass, publishing tags and pushes that same local image ID. It reads
the raw ECR manifest, verifies its SHA-256 and configuration image ID, rejects
image indexes, pulls by digest and verifies the daemon's identity. It then repeats
the samples with the final registry image digest in their requests. The local
published tag and digest remain cached; removing the last local repository tag
can also remove its digest association. Containers, scratch and temporary login
configuration are cleaned up.

Outputs go to a new `.checker-images/<unique-id>/` directory, or the new directory
selected by `--out`. Existing directories are never overwritten:

- `receipt.json`: isolation, tested image ID, sample outcomes and publication state;
- `cache-entry.json`: one entry for the existing runner's image cache;
- `registry.json`: the exact immutable `ExternalCheckerRegistrySpec` to register.

Dry run emits only the receipt. A failed final check emits no registration/cache
inputs. A failure during or after push may leave an image in ECR: the receipt
records the repository, unique tag and digest when known. It is checkpointed
before push and again when the digest is known. Do not treat that receipt as
qualification success or automatically retry an uncertain push. Inspect the
recorded ECR identity first. Checker output and credentials are never copied into
the receipt.

## Connect the image to a project

1. On the execution host, authenticate to ECR and pull the exact `repository@sha256:...`.
2. Add the verified cache entry to the existing service configuration and restart
   the service through the normal operator procedure. A publishing machine's cache
   is not the execution host's cache.
3. Register `registry.json` using the existing Operator checker registry command
   or API, with an explicit idempotency key. An image change requires a new
   capability version; retained registrations and policies remain immutable.
4. Have the Project Manager supply the registered images and configuration in
   the approval request's explicit `pre_submit_attachments` and
   `post_submit_attachments` lists, then approve and activate through the PM flow.
   Both lists are required; `[]` records a deliberate choice. Registering images
   does not change the proposal or require another setup run.

The publisher performs none of those authority-bearing steps. The complete live
journey still needs the actual guide, task, ZIP intake, selected PRE/POST images
and governed contribution outcome.
