"""Create public sample input for the opt-in Smol mechanism probe.

This uses the existing project's checker unchanged. Its minimal fixture request
is not a production invocation or an authorized ART material grant.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smolvm", type=Path, required=True)
    parser.add_argument(
        "--image",
        required=True,
        type=Path,
        help="Absolute path to a prebuilt docker-save archive",
    )
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check",
        choices=("package_layout", "metadata_contract"),
        default="package_layout",
    )
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    archive = args.output / "submission.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for path in sorted(args.sample.rglob("*")):
            if path.is_symlink():
                raise ValueError("Fixture source must not contain links")
            out.write(path, path.relative_to(args.sample).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Exact fields consumed by the real standalone checker; no fake registry
    # publication, policy approval or submission-admission evidence is produced.
    request = {
        "configuration": {"check": args.check},
        "identity": {"phase": "pre_submit"},
        "request_digest": "sha256:" + digest,
        "registry": {
            "registry_entry_id": "00000000-0000-7000-8000-000000000001",
            "entry_digest": "sha256:" + "2" * 64,
        },
    }
    binary = args.smolvm.resolve(strict=True)
    version = subprocess.run(
        [str(binary), "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    image_path = args.image.resolve(strict=True)
    with image_path.open("rb") as image_archive:
        image_archive_sha256 = hashlib.file_digest(image_archive, "sha256").hexdigest()
    config = {
        "smolvm": str(binary),
        "expected_version": version,
        "smolvm_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "image": str(image_path),
        "image_archive_sha256": image_archive_sha256,
        "cpus": 1,
        "memory_mib": 512,
        "disk_gib": 2,
        "deadline_seconds": 120,
        "archive_sha256": digest,
        "archive_bytes": archive.stat().st_size,
        "maximum_expanded_bytes": 64 * 1024 * 1024,
        "maximum_entries": 10000,
        "checker": ["python", "-I", "/opt/terminal-systems/checker.py"],
        "request": request,
    }
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(args.output / "config.json")


if __name__ == "__main__":
    main()
