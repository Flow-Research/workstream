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
