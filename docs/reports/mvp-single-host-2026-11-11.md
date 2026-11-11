# Single-host MVP qualification

The private operator drill exercised a fresh 2 vCPU/8 GiB Linux amd64 host with
nested virtualization, encrypted 100 GiB gp3 storage and a stable Elastic IP.
It used the repository deployment owners, local PostgreSQL/Redis, the independent
Rust identity issuer, private TLS verification, S3 and real isolated external
PRE/POST images. No paid model inference was used.

## Observed contribution journey

- Fresh issuer accounts logged in and were admitted through public Workstream APIs.
- A manager-authored guide compiled without setup inference; PRE and POST were
  approved separately. The locked review policy selected automatic acceptance.
- Finance published a project policy awarding 10 FLOW points per accepted submission.
- Task claim returned `in_progress` with an active assignment; no separate start call.
- An invalid package returned PRE findings without creating a Submission.
- A structurally valid package passed PRE, acquired verified S3 custody and became
  immutable Submission version 1. Real external POST found incorrect counts and
  routed it to `needs_revision`, with no ContributionRecord or award.
- Corrected version 2 retained its predecessor, passed POST and reached shared
  FinalAcceptance. Contributor and manager reads agreed on the exact artifact,
  assignment, locked ContributionPolicy, one ContributionRecord and one 10 FLOW
  award. No Review or reviewer contribution was fabricated.
- Exact successful Submission replay returned the original receipt.

## Client and restart scope

Selected deployed CLI commands and real SDK MCP tools use fresh Rust logins to
read caller identity, the accepted Submission and its exact ContributionRecord.
Both preserve concealed denial of active work-context access once acceptance
completes the assignment. This is selected workflow proof, not all-tool coverage.

The canonical consumer-first drain completed, followed by an actual host reboot.
The installed recovery unit restored all nine containers and native readiness
without manual service repair. Fresh CLI/MCP logins returned the same accepted
Submission and exact ContributionRecord/award after reboot. Participant account
credentials were held in a private persistent operator store; short-lived login
tokens were regenerated through the issuer. The stable address did not change.

## Resource observations and limits

Nine application/backing containers share the host with the native checker.
The native service cgroup recorded a 1,379,069,952-byte memory peak and no OOM or
OOM-kill events across this drill. These are single-contributor observations,
not a concurrency or production throughput benchmark. Periodic host sampling
was interrupted early; it is not claimed as complete peak-host-memory evidence.
The two owned large boundary-test fixture trees were removed after their reports
were retained. After reboot the filesystem reported 5.5 GiB used and 91 GiB
available (rounded `df -h` values). The separate seven-case intake qualification passed the configured
size/metadata boundaries and verified guest cleanup. The dynamic native disk
overhead is 704 MiB plus the existing bounded package allowance; it does not
reserve the full upload maximum for every small ZIP.

Public DNS and public-certificate participant access remain unqualified. The
private TLS/SSH operator profile retains certificate verification. Native OAuth
MCP access, human review workflows, paid inference, external point fulfillment
and broad load testing are outside this drill. An earned award is not a claim
that external fulfillment occurred.
