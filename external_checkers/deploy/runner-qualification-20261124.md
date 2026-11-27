# Dedicated runner qualification — 2026-11-24

This is the non-secret deployment receipt for the first dedicated hosted Smol
node. It records observed identities and exact digests; it does not contain TLS,
SSH or AWS credential material.

## AWS resources

- runner instance: `i-0936c305f8f67d835`, on-demand `m7i.large`,
  `eu-north-1a`, private address `172.31.21.182`
- runner security group: `sg-06167eb0a825ed79a`
- encrypted 100 GiB gp3 volume: `vol-0cd68046697a4b662`
- app instance (unchanged): `i-000b0c090ddc142bd`, private address
  `172.31.17.97`, security group `sg-015b341d9f8d39117`
- shared VPC: `vpc-049ecd21b84781a6a`

The required private application rule is TCP 9443 on the runner security group
with source `sg-015b341d9f8d39117`. No public 9443 ingress is required.

## Pinned runtime

- service source: reviewed integration descendant of `99049d0c25d177500e733f8e14659f83ff0cb53e`
- qualified service binary: `sha256:d792b8f84f44ab495c3369b865f55f8d4b8901b3d14b0a3299238df20f27538f`
- guest: `sha256:ded79cf4f7d4a29a4a3571f9427ef63a86ae8ad34f9d5ef9af79a25265e2e476`
- Smol v1.31.4 binary: `sha256:b67b25f363403e19deceb6897e5a4d94be30a079f8cb751372782f17fc99003a`
- checker image/config: `sha256:526f081b8f2a86b7e7b5d1963a96fdcd179c989db3c9d64ca70ec209c945b87f` /
  `sha256:8b19b951a661dfdf23808252eb74b883a11078e23c6e9ff11507be9ee2b6d07c`
- trusted intake image/config: `sha256:f77b5470b269ebce8ab2b467fcf0c52be814c2db9e5306aab090f45e7e2d8b81` /
  `sha256:6a83910f3989fb657a405188d9b84b1815993be7af11bb399246a0d30100c5b0`
- PRE root: 462,365,541 bytes,
  `sha256:b87e18c8713f2a80f03b0f358ef44338aaa5e851d5570573d31ee979b5cc6509`
- installed service config:
  `sha256:c35de5c4f38db8c5b9d003e47d4bf9e4310f22549c6e8dde65bdd27d57ecf5a6`
- repaired authenticated edge from reviewed commit `a64729edc`:
  `sha256:4c487d108b33f4a30bef220c95eb2b9d9483874e0a6e0ac9a5887fec1c68af6d`
- retained pre-repair rollback edge:
  `/opt/workstream/bin/workstream-remote-node.rollback-20261124-7fb81d74`

## Live receipts

TLS 1.3 mutual authentication reported Linux amd64, Smol microVM isolation,
two cached platform manifests, and sandbox uid/gid 10001.

The real POST returned a completed, request-bound result from the pinned image:

- request: `sha256:43179e023a83ff620ae9b1b0c8922f42bab8880c2bf8d9a9f3a8ddcc0c926db7`
- outcome/verdict: `completed` / `failed`
- expected finding: `harnessy.proof.missing` from the deliberately empty material

The real streamed-ZIP PRE returned a completed native receipt:

- source: `sha256:d99e15d519bfbfd3b579336e074a05a89018be10392491437a96072babf40f79`
- request: `sha256:fb0a937904f8371031b93d9989c6accd50ab67a3960b983a24da255140611c8f`
- outcome: `completed`; selected checker: `completed` / `failed`
- isolation: `smolvm` / `smol-microvm`
- cleanup: `destroyed`
- timings in milliseconds: admission 0, preparation 3395, execution 78916,
  cleanup 124, total 82437

After POST and PRE, the material workspace, model relay and Smol lease roots were
empty. Both `workstream-remote-node.service` and
`workstream-checker.service` remained active with one task each.

The repaired edge was qualified again after the crash-recovery and
same-connection callback changes. The request-bound POST completed through the
pinned checker image with the expected deliberately-empty-material result:

- request: `sha256:336944f608f0933300666e28e3087bf0b4b31d670ef07853f81cfd18ee97018f`
- outcome/verdict: `completed` / `failed`
- expected finding: `harnessy.proof.missing`
- isolation: `smolvm` / `smol-microvm`

The repaired streamed-ZIP PRE also completed and destroyed its cleanup
obligation:

- source: 261 bytes,
  `sha256:0359882cbc4c194551d439d227e606f6c4d1783c5061e6474d3f8cee2f6654ea`
- request: `sha256:da14d383a6162a3019eb4af296453882e289535a3123f8a3207f133892a51a71`
- outcome/cleanup: `completed` / `destroyed`
- selected checker: `completed` / `failed`, expected
  `harnessy.proof.missing`
- timings in milliseconds: admission 0, preparation 3377, execution 79922,
  cleanup 123, total 83424

The preparation interval includes Smol machine creation, start and guest copy.
The execution interval begins at `machine exec` and includes delivery, spooling,
validation and staging of the 462,365,541-byte trusted root (459,170,607 expanded
bytes), followed by source and worker/project execution. The code has 2 ms I/O
polling but no configured fixed wait in that path; its aggregate and guest
timeout is 120 seconds. The receipt has no finer substage timings, so the trusted
root is the dominant-size code-path explanation for the 79.9-second execution,
not a separately measured attribution.

The final check found zero children in `materials/workspaces`, `model-relay` and
`smol-leases`. Both services were loaded, enabled and active. The restored unit
files matched their retained root-private backups exactly:

- `workstream-remote-node.service`:
  `sha256:6e0854001756bb359907479b5b33bd51554031de7f05209ee980c507299968d0`
- `workstream-checker.service`:
  `sha256:6dc65ad632417984b1add1788b41553305f9cea879ed4c26bc29dc27e54eef8a`
- backups: `/etc/workstream/maintenance-backups/20261124-a64729edc/`

## Stale-workspace maintenance qualification

The crash-recovery guard admits no new session when `workspaces` contains
residue. Ordinary startup remains fail closed on any existing native socket;
connection refusal alone is not evidence that the native owner is stopped.
Reconciliation is an operator-only stopped-native procedure, not a product
startup fallback.

The live maintenance qualification used this bounded sequence:

1. Stop both runner units. Preserve the exact two local unit files, modes and
   hashes under a unique root-private, same-filesystem backup directory.
2. Apply runtime masks. Because local unit files in `/etc/systemd/system` take
   precedence over `/run` masks, atomically move only those two verified unit
   files outside systemd search paths, reload, and require both effective
   `LoadState=masked` and inactive state.
3. Require the exact private runtime parent (uid/gid 10001, mode 0700), exact
   known checker socket (uid/gid 10001, mode 0600, one link, socket type), no
   listener, no owning process and `ECONNREFUSED`. Only then unlink that one
   verified inode. Do not infer this permission from `ECONNREFUSED` alone.
4. Run the unchanged bounded reconciler as uid 10001. Abort without deleting
   anything on any identity, ownership, type, link-count, state or bound
   mismatch.
5. Restore the byte-identical unit files and metadata, reload, remove the
   runtime masks, and start the edge before the checker. Recheck hashes, loaded
   state, enabled state and active state. Keep the backups.

The observed stale checker socket was inode 303586 with uid/gid 10001, mode
0600, one link and no listener or owner. After its exact removal the clean
reconciler reported zero removals. A controlled
`.incoming-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` directory containing one 4096-byte
regular file then proved that normal edge startup refused with `workspace root
requires reconciliation`. With both units stopped and effectively masked, the
reconciler removed exactly one owned residue; the workspace was empty before
the unit files were restored and the services restarted.

The underlying bounded reconciliation command is:

```sh
sudo -u '#10001' /usr/bin/python3 /opt/workstream/bin/workstream-remote-node \
  --config /etc/workstream/remote-node.json --reconcile-stale-workspaces
```

It must only be invoked after the preceding stopped-and-masked ownership checks.
The command refuses an existing native socket, a non-private or foreign-owned
root, more than one residue, unknown names, links, special files, foreign-owned
members, more than 14,000 members or more than 1 GiB plus the bounded control
envelope. It never deletes an active or uncertain grant. Focused tests cover
both `.incoming-*` and renamed `extract_*` residue, refusal while the native
socket exists, exact removal after confirmed stop, and clean restart.

## Incident-summary qualification cache

After the hosted profile repair was frozen and integrated, coordinated
runner-only maintenance installed one additive successful-checker image for the
governed public journey. The two existing checker/intake entries remained first
and byte-identical. The new closed cache entry is:

- repository: `docker.io/library/workstream-incident-summary`
- platform manifest: `sha256:b4d1877fabfeacb24c6830469d1d1f057eacb64daecea7b5328f08431fc65721`
- image config: `sha256:ad76a4e619ec4a72db898650d01b789a0144c765676af2189f144c36e8db4939`
- canonical USTAR: 129,095,680 bytes,
  `sha256:c71509d7bc9771a6205429267ec911407913e70a4b33b6f0376eca580fac3ff2`

The archive/config are owned by uid/gid 10001, regular single-link files with
mode 0400. Active checker config is
`sha256:c3f8fb85ab2cc3b27ddf8da6db1e483aae9880b23918822c241d6864322a3dcd`.
The byte-identical prior two-entry config remains mode 0400 at
`/etc/workstream/maintenance-backups/20261124-incident-summary-cache/checker-service.json`
with digest
`sha256:c35de5c4f38db8c5b9d003e47d4bf9e4310f22549c6e8dde65bdd27d57ecf5a6`.

Only the runner edge/native units stopped during the install. Both returned
active with no error-priority journal entry. An app-origin TLS 1.3 health
exchange reported ready Linux/amd64 `smolvm`/`smol-microvm`, sandbox uid/gid
10001 and three cached manifests. Material workspaces and model-relay roots were
empty afterward. Installation is cache readiness, not project policy activation
or proof of the later public acceptance journey.

## App deployment handoff

The read-only app inspection found instance `i-000b0c090ddc142bd` healthy on
immutable release `/opt/workstream/releases/013ffbac2291179c03ff6d832f52efee9382322d`.
`workstream-hosted.service` and `workstream-identity-ingress.service` were
loaded, enabled and active. API and worker used the digest-pinned backend image
`094032936130.dkr.ecr.eu-north-1.amazonaws.com/workstream-backend@sha256:83744f1c16dd77e81555f613019898b1cca7d278a585749d2084de90ea3172a3`.
The app has no EC2 instance role; its existing direct S3 credential path remains
unchanged. Its observed source profile is hosted `app`, store backend
`s3_compatible`, provider `aws_s3`, credential mode `aws_access_key` and virtual
addressing. Keep those values and the existing credential mount unchanged; the
separate AWS source-admission gate remains closed pending qualification.
The installed image records SDK environment `agents`, runtime
`openai_agents_sdk`, provider `openrouter` and API `chat_completions`; a candidate
backend build must use `WORKSTREAM_PROJECT_AGENT_SDK_ENVIRONMENT=agents`.

The installed release predates the remote-runner wiring. Its release environment
contains no external-runner or trusted-intake keys, API and worker have no
runner TLS mounts, and `/etc/workstream/runner-tls` is absent. The worker's
existing app-local callback socket is healthy at
`/var/lib/workstream/model-runtime/model.sock` (uid/gid 10001, mode 0600, one
link); the API intentionally has no model callback socket.

The exact non-secret release additions are:

```dotenv
WORKSTREAM_EXTERNAL_RUNNER_ENDPOINTS=[{"host":"172.31.21.182","port":9443,"server_name":"runner.workstream.internal","config_sha256":"sha256:<reviewed-loaded-node-config-digest>"}]
WORKSTREAM_EXTERNAL_RUNNER_CA_FILE=/etc/workstream/runner-tls/ca.crt
WORKSTREAM_EXTERNAL_RUNNER_CERTIFICATE_FILE=/etc/workstream/runner-tls/app.crt
WORKSTREAM_EXTERNAL_RUNNER_PRIVATE_KEY_FILE=/etc/workstream/runner-tls/app.key
WORKSTREAM_ARTIFACT_INTAKE_IMAGE_DIGEST=sha256:f77b5470b269ebce8ab2b467fcf0c52be814c2db9e5306aab090f45e7e2d8b81
WORKSTREAM_ARTIFACT_INTAKE_CONFIG_DIGEST=sha256:6a83910f3989fb657a405188d9b84b1815993be7af11bb399246a0d30100c5b0
```

The three staged TLS inputs are present only in the operator-owned setup
directory. The CA is valid through 2036; the client certificate is valid
through 2029, has client-auth extended usage, chains to that CA and matches the
staged private key. Install distinct copies on the app as uid/gid 10001, mode
0400, without logging their contents. The reviewed Compose file mounts all
three as mode-0400 secrets into API and worker only. The worker also retains its
read-only app-local model socket; no runner secret or callback socket reaches
Beat, MCP, parser or model proxy.

Both instances are in `vpc-049ecd21b84781a6a`. A live TCP probe from the app to
`172.31.21.182:9443` timed out. Control-plane readback showed that runner group
`sg-06167eb0a825ed79a` has only operator SSH ingress. The one required network
mutation is a TCP 9443 ingress rule on that runner group whose source is app
group `sg-015b341d9f8d39117` (a security-group reference, not a CIDR). No public
9443 rule and no app-group ingress change are needed.

The bounded activation sequence is:

1. Freeze the exact clean integrated commit and build/publish its backend image
   under a new digest. The inspected candidate was `ccda21802`; deployment must
   record the actual later head and image digest rather than reuse that mutable
   observation.
2. Copy that exact source to a new root-owned `/opt/workstream/releases/<commit>`
   directory. Preserve the current release and image for forward-repair or
   supported rollback; do not modify the installed release in place.
3. Install the three TLS files with the ownership/mode above. Add only the eight
   environment values listed above to a private staged release file, plus the
   new release ID and backend image digest. Preserve all existing S3 direct-key
   values and mounts.
4. Authorize exactly the app-group-to-runner-group TCP 9443 rule after confirming
   it is still absent. Re-read the rule, verify private TCP reachability, then run
   an mTLS runner-health probe from the app using the candidate backend image.
   Require Linux/amd64, `smolvm`, `smol-microvm`, two cached manifests and
   sandbox uid/gid 10001.
5. Run the candidate `compose.py` environment/render/private-input preflight
   against the staged file before stopping any current container. Verify the
   rendered environment and mode-0400 secrets appear on API and worker only,
   and the model callback socket remains worker-only.
6. After the root owner coordinates a release window, use the documented
   consumer-first drain and forward migration/upgrade procedure. Reconcile the
   candidate release, wait for all container health checks, then verify the API
   and worker both reach runner health over the private address. Only after
   success should the hosted systemd unit be repointed to the new immutable
   release and reconciled.

The deployed API has no submission execution or source-cleanup profile and was
not changed. Candidate hosted configuration now requires both JSON profiles,
runs their canonical strict validators from the pinned backend image before
full preflight, `up` or reboot reconciliation, and refuses missing/malformed
values. It supplies dedicated exclusive finalization and source-cleanup workers;
the latter alone receives the distinct cleanup IAM credential. No profile value
was invented or installed. C01-C06 remain unresolved deployment decisions; do
not claim public source execution ready until approved values and the AWS source
qualification exist.

## Hosted submission topology preparation

The candidate app release now exposes
`WORKSTREAM_SUBMISSION_EXECUTION_PROFILE` and
`WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE` to backend Settings. The release
template contains explicit replacement sentinels, not operational defaults.
Static preflight requires bounded JSON objects, a distinct exact cleanup IAM
user ARN and credential path, and a cleanup `upload_principal` equal to the
normal runtime/upload ARN. Full preflight and activation additionally run
`SubmissionExecutionProfile` with the selected PRE source-contract context and
`SubmissionSourceCleanupProfile` inside the pinned backend image; validation
output is suppressed and the failing profile is named without disclosing its
body.

The general worker remains limited to `celery,workstream.outbox`. A one-process
prefork worker consumes only `workstream.submission_finalization` with the
normal runtime S3 credential. A second one-process prefork worker consumes only
`workstream.source_cleanup`, substitutes the distinct cleanup IAM ARN and is
the only service mounting its credential. Beat receives the required cleanup
profile, so omission can no longer silently remove the 12-hour cleanup schedule.
The consumer-first shutdown drains the general worker and both bounded exclusive
workers before their dependencies. The app host was not activated or restarted.

Focused hosted configuration verification passed 61 tests in 91.66 seconds.
It covers required/malformed profile refusal, upload/cleanup identity separation,
one-queue worker commands, credential confinement, fixed image-owned validation,
rendered topology, shutdown order and every prior hosted regression. Python
compilation, Ruff and whitespace checks also passed. The two remaining links to
the retired single-host guide were replaced with the current app-host release
sequence.

Remaining approval/measurement decisions are unchanged:

- C01: aggregate PRE hard deadline and public HTTP envelope.
- C02: default PRE/POST CPU, memory, disk, process, output and log profiles.
- C03: upload total/idle, part size and related transport bounds.
- C04: API/PRE/POST/finalization concurrency and physical capacity allocation.
- C05: retry/backoff/lease/heartbeat/stall and operator retry authority.
- C06: runtime lifetime/reaper plus cleanup batch, retry and retention envelope.

## App connection preparation receipt

After explicit coordination, the one private runner rule was created through
the isolated AWS provisioner wrapper and read back:

- security-group rule: `sgr-0374858efbff06c93`
- runner group: `sg-06167eb0a825ed79a`
- protocol/port: TCP 9443
- source group: `sg-015b341d9f8d39117`
- description: `Workstream app to runner mTLS`

There is no CIDR source and no public 9443 rule. The three TLS files were copied
to `/etc/workstream/runner-tls` without printing their contents. The directory is
root-owned mode 0700; `ca.crt`, `app.crt` and `app.key` are regular, single-link,
nonempty files owned by uid/gid 10001 with mode 0400. The certificate chain and
client private-key match passed on the app host.

A direct health exchange originating on the app host negotiated TLS 1.3 with
certificate name `runner.workstream.internal` and returned exact ready identity:
Linux/amd64, `smolvm`, `smol-microvm`, two cached manifests and sandbox uid/gid
10001. This proves app-host network, mTLS and protocol reachability only; the
deployed API and worker still use the old image and have not received runner
configuration.

Clean tracked source commit `08066c81a7a1d6c2b58676677b5c77cd970fbd86` was
atomically staged, root-owned and non-writable by group/other at
`/opt/workstream/releases/08066c81a7a1d6c2b58676677b5c77cd970fbd86` (3,950
files). Its Compose wrapper, Compose file and preflight hashes match the local
commit. It is only a candidate snapshot: the active unit still points to
`013ffbac2291179c03ff6d832f52efee9382322d`, no candidate backend image was built
on the live t3 app, and no environment, container, unit, IAM or source-gate state
changed. Root must freeze the eventual exact integration head and build its
`agents` image elsewhere before activation.

## Evidence and secret locations

- this saved non-secret receipt:
  `external_checkers/deploy/runner-qualification-20261124.md`
- live runner logs: system journal units `workstream-remote-node.service` and
  `workstream-checker.service`
- live configs: `/etc/workstream/remote-node.json` and
  `/etc/workstream/checker-service.json`
- pinned SSH host keys:
  `/home/abiorh/flow/workstream_aws_setup_582/runner-20261124-known-hosts`
- staged app client TLS files:
  `/home/abiorh/flow/workstream_aws_setup_582/runner-20261124-assets/tls/ca.crt`,
  `app.crt`, and `app.key`

`app.key` is private and must be installed as a mode-0400 Compose secret without
printing or copying its contents into reviews or logs.

Successful governed acceptance and an actual provider-backed model callback are
separate integration qualifications; the transport smoke does not claim either.
