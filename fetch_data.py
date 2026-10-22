"""Restore the exact public data snapshot bundled with this project."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
COMMIT = "3bde2d0f9b256ffc800932ac8574a695909f59a5"
REPO = "https://github.com/Green-AI-Hub-Mittelstand/Reduce-Foodwaste-Dataset"
RAW = f"https://raw.githubusercontent.com/Green-AI-Hub-Mittelstand/Reduce-Foodwaste-Dataset/{COMMIT}/"
NAMES = ("train.csv", "README.md", "LICENSE")


def record_source(folder: Path) -> dict:
    metadata = {
        "repository": REPO, "commit": COMMIT,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot": "train.csv only; the original competition test and truth files are not used",
        "license_file": "LICENSE", "source_readme": "README.md",
        "files": {name: {"url": RAW + name,
                         "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest(),
                         "bytes": (folder / name).stat().st_size} for name in NAMES},
    }
    (folder / "source.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace bundled data files with the pinned snapshot")
    args = parser.parse_args()
    folder = ROOT / "data"
    folder.mkdir(exist_ok=True)
    if not args.force and any((folder / name).exists() for name in NAMES):
        raise SystemExit("Data is already bundled. Use --force only to restore the pinned original files.")
    # Fetch all files before replacing any existing ones. No synthetic fallback.
    contents = {}
    for name in NAMES:
        with urllib.request.urlopen(RAW + name, timeout=30) as response:
            contents[name] = response.read()
    for name, content in contents.items():
        (folder / name).write_bytes(content)
    record_source(folder)
    print(f"Saved the pinned public dataset to {folder}")


if __name__ == "__main__":
    main()
