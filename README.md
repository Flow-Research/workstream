# Workstream

Workstream is software that manages work done by people, AI agents, or both.
It checks submitted work and makes a permanent record of the result.

A project sets the rules for its work. A contributor does a task and submits
the result. Workstream checks the result against the project rules. When the
work is accepted, Workstream makes a record that shows who did what, under
which rules, and with what result. Other systems can then use that record.
For example, a payment system can use it to pay the contributor.

Workstream is two things:

- **A shared protocol.** The protocol is the set of rules for valid work. It
  defines how tasks are assigned, how work is submitted, checked, and reviewed,
  and which records are made.
- **The software that applies those rules.** This repository contains that
  software.

The protocol does not yet have a separate, versioned specification or a
conformance test suite. That work is still to be done. For more information,
see [Protocol And Implementation](docs/protocol-and-implementation.md).

## How Workstream works

Each piece of work goes through these steps:

1. **A project sets its rules.** A project manager uploads a project guide.
   Workstream helps turn the guide into versioned policies. Approved policies
   are locked, so later changes do not affect work that has already started.
2. **A contributor gets a task.** A contributor claims a ready task.
3. **The contributor prepares the work.** The contributor puts the work into
   one ZIP file.
4. **Workstream checks the package before it accepts the submission.** These
   are the *pre-submission checks*. If the package has a problem, the
   contributor gets feedback and no submission is made.
5. **Workstream stores the submission.** After a submission is stored, nobody
   can change it.
6. **Workstream checks the submitted work.** These are the *post-submission
   checks*. They compare the work with the project's requirements.
7. **The work is accepted, sent back, or rejected.** By default, a project
   requires a human reviewer to make this decision. Live human review is not
   complete yet. A project can turn off human review. If it does, work that
   passes all required checks is accepted automatically. Failed checks can
   send the work back. On the last permitted attempt, failed checks reject
   the work.
8. **The contributor revises the work if necessary.** When the work is sent
   back, the contributor can submit a new version. The project sets the
   maximum number of revisions and a deadline.
9. **Workstream makes permanent records.** Every valid human review makes a
   reviewer contribution record. An accepted submission also makes a
   `FinalAcceptance` record and a contribution record for the contributor.

Workstream keeps the full history. It does not overwrite submissions,
findings, reviews, or records.

### Key terms

| Term | Meaning |
|---|---|
| Project guide | The document that describes the work a project wants. |
| Policy | A versioned set of rules made from the project guide, for example the checks to run. |
| Task | One unit of work that a contributor does. |
| Submission | The work a contributor sends for a task. A submission cannot be changed. |
| Pre-submission check | A check on the ZIP package before Workstream accepts it as a submission. |
| Post-submission check | A check on the stored submission against the project requirements. |
| Review | A decision by an authorized reviewer: `accept`, `needs_revision`, or `reject`. |
| `FinalAcceptance` | The record that a submission is accepted, by a reviewer or automatically. Only this record can make a contribution record for accepted work. |
| `ContributionRecord` | A permanent record of accepted work or of a valid human review. Nobody can create or edit it directly. |

The [glossary](docs/glossary.md) defines all Workstream terms.

### What Workstream does not do

- **It does not do the work.** People and agents use their own tools.
  Workstream receives and checks the result.
- **It does not log users in.** An external service verifies who a user is.
  For v0.1, that service is Flow Identity. Workstream itself decides what
  each user is permitted to do.
- **It does not send payments.** Workstream records the contributions that a
  project can pay for. Payment delivery is planned, not available.
- **It does not depend on one application.** Any application, organization,
  or industry can use the same steps.

## Current status

Workstream is in development. Version 0.1 is not released.

These parts work in a local test run:

- Set up a project from a guide, with separate approval of the pre-submission
  and post-submission policies.
- Create tasks, one at a time or in batches.
- Claim a task, submit a ZIP file, and get check results.
- Accept work automatically when a project turns off human review.
- Make contribution records and conditional awards for accepted work.

The local test run used recorded AI model output. It does not prove project
setup with a live AI model.

An isolated hosted API/Celery/Smol/AWS run also passed both review-policy
branches. A separate live OpenRouter POST reached automatic acceptance with
recorded model usage and replay protection. These runs used fixture identity
and engineering submissions; they do not prove the full real-project journey.

These parts are not complete:

- Live human review and revision after a human decision.
- Reviewer contribution records, because live human review is not complete.
- Proof of project setup with a live AI model.
- The full hosted project journey with production Flow identity.
- Payment delivery.

The [v0.1 Roadmap And Capability Status](docs/roadmap_status.md) gives the
full, current status. Read it before you rely on a feature.

## Run Workstream on your computer

This quick start uses Docker. For other setups, read the full
[Developer Setup](docs/engineering/developer-setup.md) guide.

You need Git, Docker Engine, and Docker Compose v2.

1. Copy the example configuration file:

   ```bash
   cp .env.example .env
   ```

2. Make the file private:

   ```bash
   chmod 600 .env
   ```

   This command works on Linux, macOS, and Git Bash. On PowerShell, make the
   file readable only by your Windows user before you add secrets.

3. In `.env`, give `COMPOSE_PROJECT_NAME` a unique value.

4. In `.env`, replace every `change-me` value with your own secret. The
   [local pilot runbook](docs/engineering/local-pilot.md) tells you how to
   make the secrets.

5. In `.env`, select host ports that no other program uses.

6. Build and start Workstream:

   ```bash
   docker compose --profile backend up --build --wait
   ```

   This command starts the API, the background worker, the scheduler,
   PostgreSQL, Redis, and MinIO (local file storage).

7. Make sure the API is running. Replace `<WORKSTREAM_API_HOST_PORT>` with the
   port that you selected in `.env`. On macOS, Linux, or Git Bash:

   ```bash
   curl --fail http://127.0.0.1:<WORKSTREAM_API_HOST_PORT>/api/v1/health
   ```

   On PowerShell:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:<WORKSTREAM_API_HOST_PORT>/api/v1/health
   ```

   The correct response is `{"status":"ok"}`.

8. To stop Workstream:

   ```bash
   docker compose --profile backend down
   ```

## Use the command-line client

The [Workstream CLI](cli/README.md) is a terminal client for the public API.
Download published binaries from [GitHub Releases](https://github.com/Flow-Research/workstream/releases)
and follow the [installation and verification instructions](cli/README.md#install-a-released-binary).
Linux x86-64, Windows x86-64, Intel Mac and Apple Silicon are supported.
A successful build or release tag is not a published download: the release
workflow waits for independent human approval before publishing. A CLI release
does not deploy the backend or certify the whole service for production.

You can use it to set up projects, find and claim tasks, submit work, read
authorized task audit context and evidence, and export contribution records.
It sends your Flow token, from
`WORKSTREAM_TOKEN`, with each request.

## Repository layout

| Folder | Contents |
|---|---|
| `backend/` | The Workstream API and background workers (Python and FastAPI). |
| `cli/` | The command-line client (Go). |
| `mcp_server/` | The authenticated MCP adapter exposing Workstream operations to agent clients. |
| `external_checkers/` | The service and SDK that run external checker images (Rust). |
| `contracts/` | Shared data contracts. |
| `docs/` | Product, architecture, and operations documents. |
| `docker/` | Container builds for development and release. |
| `deploy/` | Hosted deployment, ingress and Flow Identity configuration. |
| `packages/` | Shared typed external-service adapter contracts, installed by the backend and MCP packages. |
| `.ci/` and `.github/` | Validation contracts, test inventories and hosted workflows. |
| `.agents/` and `.codex/` | Repository skills and reviewer configuration. |
| `scripts/` | Scripts that check the repository and its documents. |
| `examples/` | Project guides, sample submissions and project-owned checker examples. |
| `.commitrail/` | Engineering records about changes to this repository. |

## Learn more

| If you want to | Read |
|---|---|
| Understand the product | [Product Brief](docs/product_brief.md) and [Product Principles](docs/product_principles.md) |
| Read the detailed lifecycle and implementation notes | [Workstream Technical Reference](docs/workstream_reference.md) |
| Understand the architecture | [System Architecture](docs/architecture_system_architecture.md) and [Architecture Lockdown](docs/architecture_lockdown.md) |
| See what works now | [v0.1 Roadmap And Capability Status](docs/roadmap_status.md) |
| Find a term | [Glossary](docs/glossary.md) |
| See all documents | [Documentation index](docs/README.md) |

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) before you change this repository.
Each change follows this sequence:

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> Pull Request -> Human Merge
```

For complete local commands, environment settings and troubleshooting, use
[Developer Setup](docs/engineering/developer-setup.md). Hosted deployment has its
own [runbook](deploy/hosted/README.md). Project setup and policy approval are in the
[Project Operating Manual](docs/operations_project_operating_manual.md); model
access and budgets are in [Checker Model Operations](docs/operations_checker_models.md).
The [Technical Reference](docs/workstream_reference.md) explains the lifecycle;
the [capability ledger](docs/roadmap_status.md) distinguishes delivered behavior
from remaining work.

## License

Workstream is licensed under the
[GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`).

You may change Workstream and let users use your changed version over a
network. If you do, AGPLv3 requires you to offer those users the corresponding
source code under the license terms. Third-party packages and included material stay
under their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
