# Artifact Store Contract Version 1

This directory is the provider-neutral interoperability contract for artifact
stores. `schema/contract.schema.json` uses JSON Schema 2020-12. Every object
schema rejects unknown properties.

`fixtures/valid.json` contains one request and response for every operation.
`fixtures/conformance.json` describes stream and idempotency behavior that JSON
Schema alone cannot express. `fixtures/invalid.json` contains negative schema
and protocol vectors. Consumers resolve each fixture's `schema_ref` against the
contract schema and must verify that every valid fixture passes and every
invalid fixture fails for its declared reason.

## Canonical Digests

Canonical request and response digests are SHA-256 over UTF-8 JSON with object
keys sorted lexicographically and separators `,` and `:`, without whitespace.
The digest field itself is excluded from the value being hashed. The result is
lowercase `sha256:<64 hex>`. `fixtures/canonical-digests.json` provides exact
input, canonical JSON, and output vectors.

## Stream Semantics

Artifact bytes are streamed outside the JSON DTOs. Store requests carry byte
commitments and limits; open responses carry returned-range facts. A range is a
zero-based offset and optional nonnegative length with an exclusive end.
Offset-at-EOF returns an empty stream. Offset-past-EOF is invalid. A truncated
stream never produces a success response.

Confirmed-store recovery is a distinct byte-less operation after Workstream
observed provider success but could not commit transaction B. Its request is the
original store request with both `expected_sha256` and `expected_size` required.
The provider independently reads and verifies the complete object, returns the
original store identity and receipt facts, and sets `replayed` to `true`.
Ambiguous provider failure, cancellation, or an incomplete commitment must use
exact client replay through `store`; a receipt alone is never content truth.

`open` and `stat` run through an adapter or transport already configured with
the Workstream service identity. Their provider-port request DTOs therefore do
not repeat `service_principal`.

Operation identity is the tuple `(service_principal, operation,
idempotency_key)`. It owns exactly one request digest. Exact replay returns the
original immutable receipt and provider effect. A changed digest under that
identity is `artifact_idempotency_mismatch` and creates no second effect.

Provider identifiers and receipt details are opaque. Generic schemas contain no
provider-specific content-addressing, graph, or retention implementation types.
