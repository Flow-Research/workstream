# First remote PRE launch-failure drill

This is a preparation/review recipe, not an executed receipt. Do not run it while
another journey owns the runner. It changes only the dedicated runner after an
exclusive drained-node window is granted. The API host remains separate and
receives no KVM access, runner filesystem mount or SSH key.

The bounded caller is `public_runtime_trials.public_pre_launch_failure`. Supply
an already publicly approved/claimed task, its assignment and contributor token,
the actual compatible incident-summary ZIP bytes and a `RunnerFaults` instance.
Supply only the isolated fixture launcher's existing owned stop_worker/start_worker
callbacks. The trial pauses that general POST worker and restores it in finally
on success, refusal or unknown outcome; keep the production finalizer running.
Never supply callbacks that stop arbitrary deployed application services. The caller uses public POST/GET and
read-only SQL custody checks; it never injects a T5 task or returns fake results.
From the existing isolated application harness, call it inside the owned HTTP
client/session-factory scope, after creating a fresh task via the same public
setup and packaging the actual `correct` pilot ZIP:

```python
from experiments.pilot04_external_checker_runtime.public_runner_faults import RunnerFaults
from experiments.pilot04_external_checker_runtime.public_runtime_trials import public_pre_launch_failure

result = await public_pre_launch_failure(
    client, factory, task=task_id, assignment=assignment_id, token=contributor_token,
    archive=correct_archive.read_bytes(), runner=RunnerFaults(reviewed_runner_profile),
    stop_worker=stop_owned_general_worker, start_worker=start_owned_general_worker,
)
```

The HTTP timeout remains derived from the existing explicit source execution
profile. Do not use the old operator-local HostedAttachment inspection path,
which assumes local Smol files. Keep the result and tokens in private operator
evidence; never emit token values into the result or logs.
It checks one failed source, exact sealed charge, no accepted handoff, one native
create/start/delete without exec, exact same-key failure replay with no new trace,
then fresh-key202 and real durable T5. Other fault vectors are not selected.

## Runner preparation for review

Known transport pins are runner `13.61.148.238`, user `ubuntu`, identity
`/home/abiorh/flow/workstream_aws_setup_582/ec2-pilot-ssh-key` and known-hosts
`/home/abiorh/flow/workstream_aws_setup_582/runner-20261124-known-hosts`. Never read
or print the identity bytes. Every SSH/SCP command must use the bridge's approved
`-F /dev/null`, explicit identity, `IdentitiesOnly=yes`, `IdentityAgent=none`,
`BatchMode=yes`, `StrictHostKeyChecking=yes`, explicit known-hosts,
`GlobalKnownHostsFile=/dev/null`, `UpdateHostKeys=no`, finite connect/keepalive
options. Do not substitute the application-host SSH destination.

Known unit/config candidates are `workstream-checker.service` and
`/etc/workstream/checker-service.json`. Reconfirm them read-only from the live
unit before selecting a manifest. The intended incident PRE platform digest is
`sha256:b4d1877fabfeacb24c6830469d1d1f057eacb64daecea7b5328f08431fc65721`.
The saved runner setup config contains older cache entries and is not current
custody. Do not modify its cache, permissions or pins to make a check pass.

After owner review, choose one reviewed commit (`REVIEWED_COMMIT`, full hex), one
new canonical run UUID (`RUN_ID`), and the following fresh runner-only paths:

- Source: `/opt/workstream/operator-fault-source/$REVIEWED_COMMIT`.
- Control: `/var/lib/workstream-pre-launch-$RUN_ID` (root-owned `0700`, created by supervisor). Its existing sibling runtime is checker-owned `0700` under the already traversable, root-owned `/var/lib` `0755` parent.
- Independent custody: `/var/lib/workstream-operator/pre-launch-$RUN_ID-custody.json`.
- Finite operator unit: `workstream-operator-pre-launch-$RUN_ID.service`.

The only executable files used by the supervisor are the reviewed
`public_node_faults.py`, `public_fault_files.py` and `public_runtime_wrapper.py`,
under their existing package paths. Stage the exact committed repository rather
than rewriting its Git identity. Prepare locally (no remote side effects):

```sh
test "$(git rev-parse HEAD)" = "$REVIEWED_COMMIT"
git bundle create /tmp/workstream-operator-fault.bundle HEAD
sha256sum /tmp/workstream-operator-fault.bundle
git show "$REVIEWED_COMMIT":experiments/pilot04_external_checker_runtime/public_runtime_wrapper.py | sha256sum
```

Transfer that bundle through the same pinned SSH transport to an exclusive
operator staging directory. Check the independently recorded bundle hash there.
Only after that check, these are the proposed runner commands (variables must be
validated canonical values, not arbitrary shell input):

```sh
sudo -n install -d -m 0755 /opt/workstream/operator-fault-source
sudo -n git clone --no-checkout /absolute/operator-staging/workstream-operator-fault.bundle "/opt/workstream/operator-fault-source/$REVIEWED_COMMIT"
sudo -n git -C "/opt/workstream/operator-fault-source/$REVIEWED_COMMIT" checkout --detach "$REVIEWED_COMMIT"
sudo -n git -C "/opt/workstream/operator-fault-source/$REVIEWED_COMMIT" status --porcelain
sudo -n install -d -m 0700 /var/lib/workstream-operator
```

Before any config write, compare the actual unit MainPID/ControlGroup, process
executable/argv, UID/GID10001, runtime-owned config0400 under root-owned ancestry without
group/other write (or the existing runtime-private0700 anchor), private runtime parent0700,
owner file0600, single slot, exact image cache entry and original config bytes
against independent deployment custody. Hash service, Smol, guest and the
reviewed wrapper against their independently approved artifacts. The root-owned
0600 manifest must contain exactly the fields required by existing `validate_node`:
`unit`, `config`, `socket`, `executable`, `owner`, `config_sha256`, `node_config`,
`service_sha256`, `smol_sha256`, `guest_sha256`, `wrapper_sha256`, `source_tree`.
`source_tree` is the reviewed staged Git commit; `wrapper_sha256` is independently
checked above. This recipe does not synthesize a trusted manifest from whatever
files happen to be present. A missing/mismatched custody value blocks the drill.

Once the manifest is independently reviewed and staged, start only this runner
supervisor, under a distinct finite root-owned unit:

```sh
sudo -n systemd-run --unit="workstream-operator-pre-launch-$RUN_ID" --property=Type=exec --property=RuntimeMaxSec=1200 --property=TimeoutStopSec=90 --property=KillSignal=SIGTERM --property=KillMode=process --property=SendSIGKILL=no /usr/bin/env "PYTHONPATH=/opt/workstream/operator-fault-source/$REVIEWED_COMMIT" /usr/bin/python3 -m experiments.pilot04_external_checker_runtime.public_node_faults --node-config /etc/workstream/checker-service.json --unit workstream-checker.service --root "/var/lib/workstream-pre-launch-$RUN_ID" --owner-manifest "/var/lib/workstream-operator/pre-launch-$RUN_ID-custody.json" --hosted-runtime --run-id "$RUN_ID" --maximum-seconds 900 --image-digest sha256:b4d1877fabfeacb24c6830469d1d1f057eacb64daecea7b5328f08431fc65721
```

The supervisor validates custody, a drained node and exact cached image before
creating its foreign control, installing the wrapper and restarting the existing
checker unit. Read its private `node-binding.json` and compare its canonical JSON
SHA with the independent expected value. Set `RunnerFaultProfile` to that reviewed
SHA, exact run/source/control/image and pinned transport. A ready marker alone is
not custody. Snapshot cursors, not wall/monotonic comparisons across hosts, delimit
request/replay/recovery traces. Uncertain command ACKs preserve their original ID
and stop the trial; use read-only query of that ID before any later operator action.

## Restore and retain evidence

After the caller returns or fails, stop only the operator supervisor unit:

```sh
sudo -n systemctl stop --no-block "workstream-operator-pre-launch-$RUN_ID.service"
```

TERM invokes the existing exact-inode configuration restore, checker restart,
foreign-preservation check and exact foreign cleanup. The unit intentionally does
not SIGKILL cleanup after a local SSH disconnect or stop deadline. This is not a
host-reboot/SIGKILL recovery guarantee. Observe the same run's cleanup receipt via
`RunnerFaults.snapshot()` and require its config hash equals the independently
recorded original config hash, all four owned resource lists empty, and all four
foreign-removal flags true. Independently recheck the original checker config
bytes and unit health. Preserve manifest, commands, caller result, bounded traces,
unit journal and cleanup receipt before removing only the fresh staged source and
run directories. Do not manually copy a saved config over an unverified live inode.
Missing/failed restoration blocks further trials and requires owner recovery.

No commands above have been run by the local caller guards. Source staging,
independent custody, actual runner fault execution, API/runner separation during
the drill and restoration remain live qualification prerequisites.
