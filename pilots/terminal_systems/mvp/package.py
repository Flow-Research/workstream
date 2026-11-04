"""Build deterministic submission ZIPs from the fixed event file and selected output."""

from pathlib import Path
import argparse
import zipfile

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=("correct", "incorrect", "pre-missing"))
    p.add_argument("output", type=Path)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("output exists")
    paths = {"events.jsonl": ROOT / "events.jsonl"}
    if a.kind != "pre-missing":
        paths["summary.json"] = ROOT / "fixtures" / a.kind / "summary.json"
    with zipfile.ZipFile(a.output, "x", compression=zipfile.ZIP_STORED) as z:
        for name, path in sorted(paths.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, path.read_bytes())
    print(a.output)


if __name__ == "__main__":
    main()
