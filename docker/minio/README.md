# MinIO for local development and CI

This is the real MinIO S3-compatible server, built from its upstream source.
It replaces the unavailable vendor container download, not the storage provider.
Hosted Workstream continues to use AWS S3 behind `ArtifactStore`.

The Dockerfile pins upstream commit
`7aac2a2c5b7c882e68c1ce017d8256be2feea27f` and verifies its source archive with
SHA-256 `71794c2df26aad0cc99e8421c58b7aa2dd55969f979b0e7d1e931042e9fabcd6`.
The Go builder and Debian runtime images are digest-pinned. Go dependencies use
the upstream module checksums, `go mod verify`, and a read-only build; automatic
toolchain downloads are disabled. The runtime includes the upstream license,
notice, source archive and source-revision labels. Debian package installation
uses its signed package repository; this recipe does not claim bit-for-bit
reproducible images.

Use Docker with BuildKit (the default in current Docker/Compose):

```sh
docker compose up -d --wait minio
```

Compose builds the shared recipe and retains the existing named artifact volume,
loopback port, credentials and health check. The recipe does not reset that
volume. Fresh-volume CI does not certify an upgrade of retained storage; back up
and verify retained data before changing its running image. The first build
requires network access and Go compilation resources; do not launch it on an
already memory-constrained workstation.
Subsequent builds reuse Docker layers.

Backend CI builds or restores one image cache keyed by the exact Git commit,
this directory's contents and runner platform. Older PR commits cannot supply a
cached executable to a new commit; retries of the same commit can reuse its
image. CI verifies server startup, then supplies a checksummed image
artifact to the existing lanes and aggregate job. Jobs never substitute a mock
storage provider. A missing build, artifact or health check fails verification.
The source-image artifact is independent of test/coverage evidence and cannot
make a failed test lane pass.

When updating upstream source, update the commit, archive checksum, provenance
and relevant build pins together. Require a fresh image build, health check and
the existing real S3 integration tests. Do not replace the immutable source pin
with `master`, `latest`, or an unverified prebuilt binary.
