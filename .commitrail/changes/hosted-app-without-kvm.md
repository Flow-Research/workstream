# App-only hosted release profile

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: The permanent Workstream services can boot and process ordinary durable work while checker execution is offline.

## Intent and current behavior

Run the main API, MCP, Flow Identity, PostgreSQL, Redis, guide parser, and
inference proxy on an app host without KVM. The current
[hosted composition](../../deploy/hosted/README.md) checks for native Smol
before running the API or worker. The shared [outbox scan](../../backend/app/workers/outbox.py)
currently delivers checker requests through the same queue and PostgreSQL
delivery owner as ordinary assignment, revision and completion effects.

## Bounded change

- Add an explicit hosted app profile in `deploy/hosted/{compose.py,preflight.py,compose.yml,release.env.example}`
  and an overlay for native-only configuration if needed. The app profile
  preserves existing API, parser, inference proxy, provider proof, database,
  broker, and identity validation and activates without local checker files,
  mounts, native systemd start, or KVM readiness. Reject conflicting native or
  trial configuration in this profile. Keep the existing single-host mode.
- Compose a fixed checker-delivery exclusion in `backend/app/core/config.py`,
  `backend/app/adapters/outbox/__init__.py`,
  `backend/app/modules/outbox/delivery.py` and `delivery_repository.py`. Filter
  the exact checker request and reconciliation event types before candidate
  pagination, including expired claims, and enforce the same filter before
  claim or recovery. Retain ordinary and unsupported expired recovery.
- Update the existing hosted release preflight test and relevant existing
  backend test owners. Document the app profile and its offline limits in
  `deploy/hosted/README.md` and reconcile the affected part of
  `docs/roadmap_status.md`.

The same public ZIP preparation route resolves the absent typed intake before
reading bytes and returns the existing retryable 503. MCP continues calling
that API. Keep event schemas, authority, receipts, lease owner, and public
contracts. Existing checker rows remain available for a later checker worker.
Private second-node routing, model relay wiring, provisioning and cloud
changes are outside this migration prerequisite.

## Acceptance criteria and verification

- [x] App-only preflight and startup select the complete ordinary stack with
  no checker config, socket, image assets, or hardware. They enforce archive
  provider proof, runtime identity, parser and enabled model-proxy custody.
- [x] Authorized ZIP preparation without intake returns the existing 503
  without opening the ZIP stream, creating a PRE record, or creating a Submission.
- [x] An app-only scan omits selected POST request/reconciliation work,
  including expired claims, while ordinary events progress. Direct stale
  deliveries cannot mutate the retained checker rows. The regular topology
  can subsequently select and recover those rows.
- [x] The regular hosted profile still requires native prerequisites and
  the same dedicated model credentials, intake image, and active readiness.

| Claim | Evidence |
|---|---|
| Render, preflight and startup roles | 85 hosted configuration tests passed, using real Compose rendering and controlled startup dependencies. |
| Existing retryable API contract | 53 ART tests passed, including the mounted upload route with real command composition and a guarded byte source. |
| Durable event filtering and wrong-role refusal | The repository's isolated PostgreSQL 16 runner passed the focused outbox test covering checker and completion events, due and expired states, and keyset selection. |
| Static checks | Affected backend lint, stale wording, Markdown links and whitespace passed. |

## Risk and review

- Risk class: L1.
- Required reviewers: architecture, security, QA, product/operations, documentation, test delta.
- Human review focus: preserved AWS and identity startup gates, explicit
  offline response, inference availability, and retained checker delivery.
- Current-source reconciliation: verified against `a2154e8a`.
- Next usable boundary: qualify private checker-host ingress and worker attachment to the same durable owners.
