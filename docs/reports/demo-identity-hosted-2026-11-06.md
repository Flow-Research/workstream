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
- Existing Workstream API, Celery execution, Beat, parser and model-proxy containers and
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

On November 7, a temporary API using the deployed backend's clean base image
proved the new issuer through real Workstream HTTP routes against the existing
database. It used the exact issuer hostname, a trusted private certificate and
private HTTPS JWKS port 8443; no verifier code or signature checks were changed.
The normal API and background execution remained unchanged.

- Both login accounts were admitted through `/actors/me`, without administrative
  authority. Issuer administration alone did not grant Workstream authority.
- The existing Access Administrator explicitly granted the new administrator
  account authority through the existing public mutation.
- That account issued a temporary participant grant; exact replay returned the
  same grant. Revocation succeeded, the retained grant read reported `revoked`,
  and the participant's self projection excluded the revoked role.
- The candidate rejected old fixture tokens and issuer-administration tokens;
  the existing API rejected new-issuer tokens, as its unchanged pin requires.
- No existing actor identity was remapped. This proof did not re-run or compare
  the complete Garden contribution history.

The temporary API, private environment file and temporary trust bundle were
removed; its port closed and the issuer bridge again contains only the issuer.
The new accounts and explicitly granted administrator remain for cutover.

At completion of this earlier proof, active cutover and credential retirement
remained outstanding. The subsequent [active private cutover](demo-identity-active-cutover-2026-11-07.md)
records the normal deployment separately. Publicly trusted participant access
still requires DNS/TLS qualification.
