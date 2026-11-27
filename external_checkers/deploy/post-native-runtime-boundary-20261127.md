# Native POST runtime boundary — 2026-11-27

This change corrects the native ordinary-POST deadline boundary. It is a build
and rollout record, not live qualification evidence.

## Diagnosis

The service previously created `request.deadline_ms` before grant verification,
workspace hashing, Smol machine creation/start, guest bootstrap copy, material
streaming and guest staging. The guest ordinary-project supervisor had no
separate runtime deadline. A 500 MiB incident-summary request could therefore
consume its frozen 30,000 ms checker allowance before the checker entrypoint was
launched. The earlier 462,365,541-byte qualification receipt independently
recorded about 79.9 seconds from `machine exec` through transfer, validation,
staging and checker execution, consistent with this path.

## Corrected boundary

- Grant verification, VM preparation and material staging no longer consume an
  ordinary native checker's registry runtime.
- Smol create/start/copy retain the existing per-control-operation timeout.
  Job/material delivery and the preparation transition use the existing
  progress-reset socket inactivity timeout and still observe caller disconnect.
- After staging, mounts and cgroups are ready, the trusted guest emits exactly
  one `prepared` frame and waits. The host validates it, arms the invocation's
  model relay with `now + deadline_ms`, and sends exactly one `start` frame.
  Only then may the guest fork and exec the checker.
- The host applies that same runtime deadline to capability calls, completion
  and process reaping. Missing, malformed, duplicate and unsolicited control
  frames fail closed.
- Trial executions preserve their existing aggregate envelope. PRE and trusted
  intake retain their existing purpose-specific deadline semantics.
- The guardian follows its exact controller owner pipe instead of the immutable
  original POST lease timestamp. This preserves renewable background work while
  controller EOF/loss still initiates owned cleanup.

## Release procedure

1. Build the service and the static `x86_64-unknown-linux-musl` guest from the
   same reviewed source commit with `--locked`; record SHA-256 and ELF identity.
2. Run the Rust workspace tests plus the maintained PRE and trusted-intake
   compatibility lanes. On a fresh isolated KVM candidate, qualify a maximum
   admitted ordinary POST whose checker runtime is independently observable;
   verify staging can exceed `deadline_ms` while a checker exceeding its own
   runtime still returns `deadline_exceeded`.
3. Drain the runner and prove zero admission, remote sessions, material
   workspaces, leases, VMs and owned cgroups. This is required because the
   unreleased lease JSON drops the superseded fixed-expiry fields.
4. Stop only the runner edge/native units under the reviewed maintenance
   sequence. Preserve byte-identical rollback binaries, guest and node config.
5. Install both reviewed binaries. Replace the guest SHA in all three bindings:
   `smol.guest_sha256`, `pre.guest_sha256`, and
   `trusted_intake.storage_envelope.guest_sha256`. Recompute the closed node
   config digest; do not alter image, Smol, PRE-root or intake identities.
6. Start native then edge, verify authenticated health/config epoch, and run
   unchanged PRE and trusted-intake checks before ordinary POST. Then run the
   500 MiB incident-summary POST and a bounded runtime-overrun case. Confirm
   results, empty workspaces/leases/VMs/cgroups and no error-priority journal.
7. Roll back both binaries and the exact prior config together on any binding,
   readiness, PRE, intake, runtime-deadline or cleanup mismatch.

No app-host configuration, policy, source gate, network or IAM change is part
of this rollout.
