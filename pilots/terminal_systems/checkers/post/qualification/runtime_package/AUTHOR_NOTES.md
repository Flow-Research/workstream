# Exact reproduction procedures

Run the incomplete repair with `sh solution/incomplete.sh` from a fresh state.
Remove required output with `sh tests/remove-output.sh` from a reference state.
Fabricate output with `sh tests/fabricate-output.sh` from a reference state.
Create a controlled interrupted state with `sh tests/interrupt.sh` from a fresh
state, then recover it with `sh tests/restart.sh` using that retained state.

The incomplete, missing, and fabricated states must fail `sh tests/run.sh`.
The reference must pass it in three independently prepared workspaces, and the
restarted interrupted state must pass it.
