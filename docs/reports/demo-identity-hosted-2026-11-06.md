# External identity issuer: private hosted proof

The Rust issuer runs on the drill host with persisted accounts and signing state.
This proves the private deployment; public DNS/TLS and the active Workstream
issuer cutover are still pending.

Verified through the real hosted image and HTTPS:

- Administrator login and participant creation; duplicate accounts reject.
- Participant login and password replacement; the old password stops working.
- Container restart preserves credentials, subject and public signing keys.
- The unchanged Workstream verifier accepts participant tokens issued before
  and after restart and rejects the separate issuer-administrator token.
- Caddy forwards login and public JWKS over verified upstream TLS. Unsupported
  routes/methods and oversized bodies reject; substituting an unrelated upstream
  trust certificate returns 502. The temporary private Caddy listener was stopped.
- Existing Workstream API, worker, Beat, parser and model-proxy containers and
  the active release marker were unchanged. Account/signing state was preserved
  during the network correction.

The image was built from the issuer inputs at `e327e60d6`; its runtime
configuration and all filesystem layer hashes were compared across Docker
import. The hosted immutable image digest is
`sha256:7a9161177a59b61074abbb3a448e441b4cb7ed68bef15c9e10a55e218642faa5`.
The qualified Compose/preflight source is `933fec47f`. Caddy is 2.11.9; its
binary SHA-256 is
`a563843e11cbce39c557bd429ebb787d56f49d51d9bbb3292cd9b36b37a60cdf`.
The supplied host unit and configuration validated on the actual host. Its
public service remains stopped until DNS is available.

Two regressions protect issues found during integration: the previous shared
proxy-peer bucket locks out valid login, and Docker's internal network suppresses
the required host port. Each repaired test fails at the intended boundary when
its prior behavior is restored. CI now exercises the actual image and overlay,
not only their rendered configuration.

Remaining proof: publicly trusted `identity.flowresearch.tech`, actual Workstream
HTTP authentication and explicit grants for the new actors, retirement of the
fixture issuer/keys/tokens, rejection of old credentials and fresh login-based
access. Existing Garden actor history and contribution facts must remain intact.
