"""Opt-in live qualification on a prepared KVM host; no product API calls.

Run after make_fixture.py has produced valid and missing-file input directories.
The supplied HOME must be a private Smol runtime home used only for this probe.
"""

import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--valid-input", type=Path, required=True)
    parser.add_argument("--invalid-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    probe = str(args.probe.resolve(strict=True))
    base = json.loads((args.valid_input / "config.json").read_text())
    smol = base["smolvm"]
    results = []

    def record(name, **values):
        result = {"case": name, **values}
        results.append(result)
        (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(result), flush=True)

    def cli(*arguments):
        return subprocess.run(
            [smol, "machine", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout

    def inventory():
        return json.loads(cli("ls", "--json"))

    def trial(
        name, source, *, delay=0, timeout=30, transform=lambda x: x, checker=None
    ):
        config = json.loads((source / "config.json").read_text())
        config["deadline_seconds"] = timeout
        if checker:
            config["checker"] = checker
        cp = args.output / (name + ".json")
        cp.write_text(json.dumps(config))
        target = args.output / name
        started = time.monotonic()
        with subprocess.Popen(
            [probe, str(cp), str(target)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            if delay:
                time.sleep(delay)
            try:
                process.communicate(
                    transform((source / "submission.zip").read_bytes()),
                    timeout=timeout + 22,
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise
        report = json.loads((target / "report.json").read_text())
        verdict = (
            json.loads((target / "checker-result.json").read_text())
            if (target / "checker-result.json").exists()
            else None
        )
        owned = json.loads((target / "lease.json").read_text())["name"]
        assert report["cleanup_confirmed"] and (target / "cleanup-confirmed").exists()
        assert not (target / "submission.zip").exists()
        assert not any(row["name"] == owned for row in inventory())
        record(
            name,
            wall_seconds=round(time.monotonic() - started, 3),
            report=report,
            checker=verdict,
        )
        return report, verdict

    report, result = trial("overlap", args.valid_input, delay=3)
    assert result["verdict"] == "passed" and report["outcome"] == "completed"
    assert (
        report["preparation_ms"] < report["upload_ms"]
        and report["post_upload_wait_ms"] < 100
    )
    report, result = trial("invalid_work", args.invalid_input)
    assert (
        result["verdict"] == "failed"
        and result["findings"]
        and report["outcome"] == "completed"
    )
    for name, transform in [
        ("truncated", lambda x: x[:100]),
        ("overlimit", lambda x: x + b"!"),
    ]:
        report, result = trial(name, args.valid_input, delay=3, transform=transform)
        assert (
            report["failure"] == "upload_size_mismatch" and report["execution_ms"] == 0
        )
        assert result is None
    report, result = trial(
        "abandoned", args.valid_input, delay=7, timeout=5, transform=lambda _: b""
    )
    assert report["outcome"] == "infrastructure_failed" and report["execution_ms"] == 0
    assert result is None
    report, result = trial(
        "check_timeout",
        args.valid_input,
        timeout=6,
        checker=["python", "-I", "-c", "import time;time.sleep(90)"],
    )
    assert report["outcome"] == "infrastructure_failed" and result is None

    control_owner = uuid.uuid4().hex
    control = "ws-smol-control-" + control_owner
    # Exact owned control identity, distinct from the probe's lease namespace.
    cli(
        "create",
        "--name",
        control,
        "--label",
        "control-owner=" + control_owner,
        "--image",
        base["image"],
        "--cpus",
        "1",
        "--mem",
        "128",
        "--storage",
        "1",
    )
    try:
        config = dict(base, deadline_seconds=15)
        cp = args.output / "parent_death.json"
        cp.write_text(json.dumps(config))
        target = args.output / "parent_death"
        with (args.output / "parent_death.log").open("wb") as log:
            process = subprocess.Popen(
                [probe, str(cp), str(target)],
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if (target / "lease.json").exists():
                        owned = json.loads((target / "lease.json").read_text())["name"]
                        row = next((x for x in inventory() if x["name"] == owned), None)
                        if row and row.get("state") == "running":
                            break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("running owned VM not observed")
                assert (
                    row["network"] is False and row["mounts"] == 0 and row["ports"] == 0
                )
                # Probe is waiting on upload; no submitted material may have arrived.
                guest = json.loads(
                    cli(
                        "exec",
                        "--name",
                        owned,
                        "--",
                        "python",
                        "-I",
                        "-c",
                        'import json,os;print(json.dumps({"uid":os.getuid(),'
                        '"input_exists":os.path.exists("/work/input"),'
                        '"interfaces":os.listdir("/sys/class/net")}))',
                    )
                )
                assert not guest["input_exists"]
                process.kill()
                process.wait(timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdin.close()
        deadline = time.monotonic() + 35
        while (
            time.monotonic() < deadline and not (target / "cleanup-confirmed").exists()
        ):
            time.sleep(0.1)
        rows = inventory()
        assert not any(x["name"] == owned for x in rows)
        assert any(x["name"] == control for x in rows)
        assert (target / "cleanup-confirmed").exists() and not (
            target / "submission.zip"
        ).exists()
        assert not (target / "checker-result.json").exists()
        record(
            "parent_death",
            cleanup_confirmed=True,
            foreign_control_survived=True,
            owned_vm=owned,
            runtime_inventory=row,
            guest=guest,
        )
    finally:
        row = next((x for x in inventory() if x["name"] == control), None)
        if row is not None:
            assert row["labels"].get("control-owner") == control_owner
            cli("delete", "--name", control, "--force")
        assert not any(x["name"] == control for x in inventory())
    print("Evidence: " + str(args.output), flush=True)


if __name__ == "__main__":
    main()
