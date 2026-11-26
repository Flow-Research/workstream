# Workstream example projects

These directories contain reusable project inputs and project-owned checkers.
They are not Workstream services, alternate identity providers or deployment
qualification results. Uploading an example does not register images, approve
policies, grant access or prove a deployment is ready.

| Project | Purpose | Contents |
| --- | --- | --- |
| [Garden](garden/README.md) | GitHub-backed engineering contributions | Guide, manager-authored requirements, sample tasks and GitHub App setup. Its checker source is documented in that guide. |
| [Terminal Systems](terminal_systems/README.md) | Authoring and evaluating terminal benchmark packages | Guide, task examples, independent PRE/POST image source, fixtures and qualification tests. |
| [Incident summary](incident_summary/README.md) | Small deterministic intake-to-outcome example | Guide, supplied events, ZIP packaging, PRE/POST checker and correct/incorrect outputs. No model is required. |

Use the [project operating manual](../docs/operations_project_operating_manual.md)
for authorized setup and policy selection. Setup assistance is optional; it
proposes checks from the guide and examples, never executable image selections.
Engineering builds project-owned images and an authorized manager binds their
exact registered identities and configuration. Shared execution belongs to
[`external_checkers/`](../external_checkers/README.md); deployed authentication
uses [Flow Identity](../deploy/identity/README.md).
