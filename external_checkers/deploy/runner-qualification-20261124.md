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

The follow-up crash-recovery guard admits no new session when `workspaces`
contains residue. Reconciliation is a separate stopped-native operation:

```sh
sudo systemctl stop workstream-checker.service workstream-remote-node.service
sudo -u '#10001' /usr/bin/python3 /opt/workstream/bin/workstream-remote-node \
  --config /etc/workstream/remote-node.json --reconcile-stale-workspaces
sudo systemctl start workstream-remote-node.service workstream-checker.service
```

The command refuses an existing native socket, a non-private or foreign-owned
root, more than one residue, unknown names, links, special files, foreign-owned
members, more than 14,000 members or more than 1 GiB plus the bounded control
envelope. It never deletes an active or uncertain grant. The focused restart
proof covers both `.incoming-*` and renamed `extract_*` residue, refusal while
the native socket exists, exact removal after confirmed stop, and clean restart.

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
