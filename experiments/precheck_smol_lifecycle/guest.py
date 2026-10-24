"""Probe-only guest staging. Never imported by the production artifact owner."""

import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile


def extract(archive, destination, *, maximum_bytes, maximum_entries):
    """Reject ambiguous paths and bound actual decompression inside the guest."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o755)
    seen = set()
    expanded = 0
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > maximum_entries:
            raise ValueError("archive_entry_limit")
        for item in entries:
            raw = item.filename
            name = raw[:-1] if item.is_dir() else raw
            parts = name.split("/")
            mode = item.external_attr >> 16
            if (
                not name
                or "\\" in name
                or "\x00" in item.orig_filename
                or any(part in {"", ".", ".."} for part in parts)
                or ":" in parts[0]
                or name in seen
                or stat.S_ISLNK(mode)
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                or item.flag_bits & 1
            ):
                raise ValueError("archive_entry_invalid")
            seen.add(name)
            target = destination.joinpath(*parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, target.open("xb") as sink:
                while chunk := source.read(65536):
                    expanded += len(chunk)
                    if expanded > maximum_bytes:
                        raise ValueError("archive_expansion_limit")
                    sink.write(chunk)
            target.chmod(0o555 if mode & 0o111 else 0o444)
    for directory, _, _ in os.walk(destination, topdown=False):
        Path(directory).chmod(0o555)
    return expanded


def main():
    settings = json.loads(Path("/tmp/probe-input.json").read_text())
    archive = Path("/tmp/submission.zip")
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        while chunk := source.read(65536):
            digest.update(chunk)
    if digest.hexdigest() != settings["archive_sha256"]:
        raise ValueError("archive_digest_mismatch")
    extract(
        archive,
        Path("/work/input"),
        maximum_bytes=settings["maximum_expanded_bytes"],
        maximum_entries=settings["maximum_entries"],
    )
    # The existing checker runs unchanged, as a non-root user, with the usual
    # /work/input path and stdin/stdout JSON. This fixture is not an ART grant.
    os.setgroups([])
    os.setgid(65532)
    os.setuid(65532)
    os.execvpe(settings["checker"][0], settings["checker"], os.environ)


if __name__ == "__main__":
    main()
