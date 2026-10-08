#!/bin/sh
set -eu

expected_payload='workstream-pilot00-offline-build'
payload_path='/opt/workstream-pilot00/payload.txt'
digest_path='/opt/workstream-pilot00/payload.sha256'

test "$(id -u)" -ne 0
test -e /proc/gvisor/kernel_is_gvisor
test ! -e /var/run/docker.sock
test "$(sed -n 's/^CapEff:[[:space:]]*//p' /proc/self/status)" = 0000000000000000
test "$(cat "$payload_path")" = "$expected_payload"
(cd /opt/workstream-pilot00 && sha256sum -c payload.sha256)

if wget -T 2 -qO- http://1.1.1.1 >/dev/null 2>&1; then
    echo 'external network unexpectedly reachable' >&2
    exit 71
fi

interface_count="$(awk 'NR > 2 { count += 1 } END { print count + 0 }' /proc/net/dev)"
test "$interface_count" -eq 1
grep -Eq '^[[:space:]]*lo:' /proc/net/dev

printf '%s\n' 'oracle=pass'
