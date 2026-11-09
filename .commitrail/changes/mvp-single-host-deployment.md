# Repeatable single-host MVP deployment

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Operators can install the existing Workstream runtime
  on a clean single host using repository-owned instructions and bounded setup
  commands, without private drill scripts or retained demo state.

## Intent

Replace the one-off deployment procedure with a supported clean-install path in
`deploy/hosted`. The approved target is Linux amd64, 2 vCPU, 8 GiB RAM, encrypted
100 GiB gp3 storage and a stable Elastic IP. AWS reports nested virtualization
support for m7i.large; actual capacity remains subject to a complete runtime
drill. Keep Smol local and retain existing isolation and typed capabilities.

The user explicitly discarded the previous demo database and accounts and does
not require a migration or backup of that disposable state. This authorization
does not apply to unrelated resources or deletion of the S3 bucket. Production
operators still need backup/restore guidance; do not remove it from shared docs.

## Bounded change

1. Map current Compose, native runtime, identity, storage proof and bootstrap
   owners. Identify the private-only steps that prevent a clean public install.
2. Extend those existing owners with a small, explicit single-host setup path:
   persistent PostgreSQL/Redis, private credentials, native prerequisites,
   pinned images, independent identity initialization and ordered activation.
3. Document stable ingress, resource limits, log/image retention, restart and
   operator troubleshooting. Build images away from the application host.
4. Exercise clean configuration and refusal cases locally, then provision the
   approved host after the required scoped IAM permissions are available.
5. Prove fresh identity login and the public contribution journey, cleanup and
   restart on the small host. Retire the superseded deployment only within the
   explicitly authorized scope. Record actual limits and remaining DNS needs.

## Allowed files

- `deploy/hosted/**`: existing deployment composition, templates, preflight,
  clean-install helpers and operator instructions.
- `scripts/test_hosted_release_config.py` and focused adjacent hosted-deployment
  tests when required for the changed behavior.
- `README.md`, `docs/roadmap_status.md`, directly affected operations documents
  and this record.
- Private AWS provisioning files and deployment receipts outside Git; never
  commit account credentials, private keys, participant passwords or host state.

## Prohibited changes

No remote-checker subsystem, Kubernetes, autoscaling, product policy or AUTH
changes, weaker storage/identity/isolation guards, old fixture tokens, public
database/Redis ports, embedded private account configuration, broad resource
deletion, new payment/review features or unrelated CI changes. No claim that
2 vCPU/8 GiB is qualified before measured runtime proof.

## Acceptance criteria

- A clean operator can follow one documented order using checked-in commands;
  the procedure neither imports old demo records nor relies on private scripts.
- Persistent backing services and account state survive restart; credentials
  remain private and images have exact immutable identities.
- Missing prerequisites, placeholders and incompatible resource envelopes fail
  before application activation; setup does not repeat uncertain cloud creates.
- Existing canonical release/AWS proof and Smol preflight remain authoritative.
- Fresh CLI/MCP login, claim, malformed PRE/no Submission, valid intake/S3,
  external POST, automatic acceptance/contribution/award and exact replay pass.
- Measure peak memory, actual disk use and temporary-resource cleanup with
  conservative concurrency. No assumed capacity or broad performance claim.
- Run affected tests, link/stale-wording/Commitrail checks and reconcile current
  roadmap exposure against the actual deployed result.

## Risk and review routing

Risk: L1 deployment, authentication secrets and destructive environment reset.
Required focused review: security/architecture plan and implementation;
QA/test-delta and documentation for clean installation and proof claims. Add
CI-integrity review only if CI configuration changes become necessary.
Human focus: clean-install usability, exact resource deletion scope, credential
handling, stable ingress and measured small-host limits. Human merge remains
required; live cloud operations follow the user's explicit deployment authority.

## Evidence

The focused deployment configuration and initialization suite exercises closed
Compose inputs, secret isolation, fresh-state refusal, and consumer-first drain.
Real container qualification additionally checks PostgreSQL/Redis startup,
restricted application access and persisted state after restart. Those results
are separate from the required fresh-host public journey and resource proof;
no configuration test qualifies the proposed smaller host.
