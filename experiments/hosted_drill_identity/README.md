# Isolated hosted drill identity

This operator fixture supplies simulated identities to the **unchanged Flow token
verifier** for the temporary Workstream journey drill. It is not Flow Identity,
Workstream login, or evidence of integration with the actual Flow issuer.

Use the backend's locked Python environment; no additional dependency is needed.
From the repository root:

```sh
python experiments/hosted_drill_identity/fixture.py init --directory /private/drill-issuer
python experiments/hosted_drill_identity/fixture.py mint \
  --directory /private/drill-issuer --identity contributor \
  --output /private/drill-issuer/contributor.jwt
```

The parent directory must already exist. Initialization exclusively creates its
private directory; it never replaces an existing issuer. Token output must be a
new file in an owned mode-0700 directory. Files are mode 0400. Keep this directory
outside the checkout; do not print, paste, commit or export its contents.

The fixed human inventory is access-admin, manager, finance, operator,
contributor and foreign-contributor. These are operator labels, **not roles**.
Each has a stable random subject. Tokens contain only `iss`, `sub`, `aud`, `iat`,
`nbf`, `exp`, a fresh `jti`, `subject_kind=human` and `scope=workstream:access`.
RS256 tokens last 900 seconds and are replayable until expiry. Mint a fresh file
when needed; delete retained token files after the drill. There is no online
minting, revocation or introspection service.

A valid human token can trigger existing first-access admission, creating an
active actor and identity link. Project roles and administrative grants still
require Workstream's existing authorized operations. Extra role claims do not
enter the verified authority contract. Unprovisioned service subjects remain
denied by the actor owner. The signing-key custodian can sign arbitrary subjects
outside this tool; the inventory limits the tool, not the verifier's issuer trust.
Treat that key as privileged drill operator material.

## Private HTTPS composition

Copy **only** `jwks.json`, `tls.pem` and `tls-key.pem` into separate owned private
server mounts. The server needs neither `signer.pem` nor `subjects.json`. Its one
fixed response contains public key fields only; it does not serve a directory.
The TLS leaf key is a separate mount from JWKS. Do not mount the JWT signing key
in the server or application. Do not publish a host port.

Run on a private Docker bridge with network alias `flow-drill.test`:

```sh
python experiments/hosted_drill_identity/fixture.py serve --jwks /public/jwks.json \
  --certificate /tls/tls.pem --key /tls/tls-key.pem --bind 0.0.0.0 --port 8443
```

The command above uses the repository-root path and locked backend environment.
The release image does **not** contain experiment files. For a container, bind
mount this reviewed script read-only at `/fixture/fixture.py`, mount the three
server files individually, and override the entrypoint with
`/opt/venv/bin/python /fixture/fixture.py serve` followed by the same file and
network arguments. Use the existing digest-qualified backend image; never mount
the whole operator directory or checkout.

Run as the owner of the mounted files, read-only, with dropped capabilities,
`no-new-privileges`, bounded CPU/memory and no Docker socket. Use a separate
experiment composition, not changes to the production deployment profile.
The server is deliberately single-threaded with bounded socket timeouts and
intended for a handful of drill identities, not general issuer traffic.

Configure the real application verifier:

```dotenv
WORKSTREAM_AUTH_PROVIDER=flow
WORKSTREAM_TOKEN_ISSUER=https://flow-drill.test:8443
WORKSTREAM_TOKEN_AUDIENCE=workstream-drill
WORKSTREAM_TOKEN_JWKS_URL=https://flow-drill.test:8443/jwks.json
WORKSTREAM_TOKEN_ALGORITHMS=RS256
WORKSTREAM_TOKEN_CLOCK_SKEW_SECONDS=0
WORKSTREAM_TOKEN_INTROSPECTION_MODE=disabled
WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON=isolated simulated issuer drill; short-lived tokens; no revocation proof
```

The verifier uses `trust_env=False`: `SSL_CERT_FILE` alone has no effect. In the
experiment only, concatenate the image's existing `certifi.where()` public CA
bundle with `ca.pem`, then mount that combined public bundle read-only over that
exact image path. Preserve ordinary roots. Do not change the host trust store,
disable certificate verification, or alter production verifier code. The TLS CA
lasts seven days and leaf three days; the CA signing key is not retained.

## Renew HTTPS transport while retaining identities

Expired transport must be renewed explicitly. Keep the original `signer.pem`,
`jwks.json` and `subjects.json` unchanged: initializing a new issuer would generate
different subjects and signing material for already admitted identities.

Create a new, exclusive transport directory; its parent must already exist:

```sh
python experiments/hosted_drill_identity/fixture.py init-transport \
  --directory /private/drill-transport-2
```

This writes only `ca.pem`, `tls.pem` and `tls-key.pem`, with the same seven-day CA,
three-day leaf and private file permissions. It retains no CA signing key and
refuses an existing target directory. Retain the original transport generation
as evidence; do not overwrite files in the original issuer directory.

Serve the **original JWKS** through the new certificate and leaf key:

```sh
python experiments/hosted_drill_identity/fixture.py serve \
  --jwks /private/drill-issuer/jwks.json \
  --certificate /private/drill-transport-2/tls.pem \
  --key /private/drill-transport-2/tls-key.pem --bind 0.0.0.0 --port 8443
```

For the private server container, update its two individual TLS mounts while
retaining its original JWKS mount, network alias and issuer URL. Its signing key
and subject inventory remain outside the server. Continue minting tokens from
the original directory:

```sh
python experiments/hosted_drill_identity/fixture.py mint \
  --directory /private/drill-issuer --identity contributor \
  --output /private/drill-issuer/contributor-renewed.jwt
```

Update the application's explicit drill trust to the new CA while preserving
ordinary public roots. For the hosted drill's CA-only fixture images, rebuild
that layer over the reviewed canonical backend SDK images with the new `ca.pem`,
publish new digest pins and run the
[canonical native-hosted image verifier](../../deploy/hosted/README.md#prepare-source-images)
against those exact images. Preserve the CA-only recipe and all application
source and dependency checks. A composition using the read-only combined-bundle
mount instead requires a new combined bundle containing the new CA and the
image's ordinary public roots.

Retain old image and trust fingerprints, then qualify and apply the reviewed
release/trust change through the existing
[hosted preflight and startup sequence](../../deploy/hosted/README.md#start-and-inspect).
Do not patch a running container's trust store or disable certificate checks.
Before resuming the drill, verify HTTPS returns the exact original JWKS and that
the unchanged production verifier accepts a freshly minted original-identity
token with the new trust. The old CA must not validate the new transport.

Transport renewal leaves the database, admitted actors, identity links, grants,
locked policies and model budget intact. It does not repeat first-access
admission, create replacement identities or establish integration with the
actual Flow issuer.

## Verification and evidence boundary

```sh
PYTHONPATH=backend python -m pytest experiments/hosted_drill_identity/test_fixture.py -q
```

Tests use actual HTTPS and the default production verifier client factory. They
cover valid identities, expiry, wrong signature/issuer/audience/scope, missing
`jti`, untrusted TLS, minimal identity projection, bearer replay, exclusive files,
and a server running without the JWT signing key. Existing actor tests retain
first-access and unprovisioned-service proofs:

- [Human admission](../../backend/tests/actors/test_first_access_postgresql.py)
- [Service denial](../../backend/tests/actors/test_self_api_lifecycle.py)
- [Minimal token contract](../../backend/tests/authentication/test_token_contract.py)

These tests are not a completed hosted contribution journey. Record remote
verification separately, without JWTs, subjects, private keys, or request headers.
Observe first-access admission and absence of grants before explicit bootstrap
and role operations during the hosted drill. No result here closes actual Flow
interoperability, project setup, ZIP custody, checker execution or acceptance.
