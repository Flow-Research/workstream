# Active private Rust issuer cutover

The EC2 Workstream deployment switched to the external Rust account issuer on
November 7, 2026. This is the normal API and durable worker deployment, not the
temporary API used by the earlier compatibility and client proofs. Public DNS and
publicly trusted participant access remain separate, unproven boundaries.

## Release and preservation

The deployment configuration came from `c7f61b01b`; the unchanged backend images
came from the recorded `d8daf19f6` clean bases with only the new private TLS
certificate added to their normal trust bundles. The old fixture CA is absent.
These are different provenance claims. No backend verifier code, schema or
native checker service changed.

The existing deployment owners drained execution, preserved the retained database
and eight pending delivery rows, sealed a new release, and completed its real AWS
proof before API/worker startup. Exact retained-data checks passed before the
public API authorization proof; subsequent self/grant reads legitimately record
authorization evidence and are not compared away. Beat and the release-bound AWS
proof timer resumed only after that proof passed.

## Active authentication

Fresh password logins supplied the two existing Rust accounts. The active API:

- returned their original admitted actor IDs;
- allowed the explicitly granted administrator to read administrative grants;
- denied the unprivileged participant the same administrative read;
- rejected the issuer-administration token as a Workstream access token;
- rejected an old fixture access token that the previous active API had accepted,
  while that token was still unexpired.

The canonical HTTPS issuer/JWKS hostname resolves to the host gateway only inside
the API overlay. Caddy serves verified private HTTPS on 443 and verifies its
loopback issuer upstream. An explicitly shared same-host TLS identity is confined
to private issuer/ingress files; JWT signing keys and account storage are not
shared. A container on the API network proved successful trusted JWKS retrieval
and rejection using unmodified public roots. TLS verification was never disabled.

## Clients against the active API

The compiled CLI and actual MCP SDK client used fresh Rust login tokens through
an owned SSH tunnel to the active API. Both accounts resolved to their existing
actors. The administrator's permission discovery succeeded; the participant's
returned `403 permission_not_granted`. Both new explicit guide commands/tools
reached the API and returned `404 proposal_unavailable` for the ungranted Garden
project. These denials do not prove successful guide compilation.

The MCP adapter advertised 132 tools, including assistance and inference-free
requirements compilation, using protocol `2026-07-28`. This is SDK integration,
not a native ChatGPT/Codex connector or a live execution of all 132 tools. No new
project grants, task effects or inference calls occurred. Public participant
access still needs DNS/TLS; standard remote MCP OAuth is not implemented by the
custom bearer-header adapter.

## Credential retirement

After the active proof passed, a reviewed, hash-guarded retirement removed the two
old fixture containers, eight known remote signing/TLS private-key copies, the
saved old control token, and two local private-key copies. Fresh Rust login,
administrator access and participant denial passed again afterward. The deleted
paths and containers were verified absent. AWS Roles Anywhere, SSH, GitHub App
and Rust issuer credentials were outside the deletion boundary.

The inventory covered known operator/configuration roots and archive member
names. It found no additional embedded copies in the scanned text. Source
checkouts, dependency caches and Git bundles were excluded; this is bounded
credential retirement, not a claim that every possible backup was searched or
securely erased. Existing actors, identity links and contribution history remain.

The active client proof's temporary tokens were deleted and its SDK adapter and
SSH tunnel were stopped; both local ports were verified closed. The normal API,
Rust issuer, workers and scheduler remain running. The deployment's private
Caddy ingress is active; it has not yet proved public DNS/certificate issuance.

The private operator startup plan no longer launches the fixture JWKS service.
Its obsolete bootstrap writer and offline mint/admission functions were removed;
native startup commands and historical readers remain unchanged. Retained old
journey procedures are historical evidence, not a supported login path. They
were not remapped to new accounts; current client proofs obtain tokens by login.
